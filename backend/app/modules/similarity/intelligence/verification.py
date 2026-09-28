"""Bounded token alignment with offsets in the original stored strings."""

from collections import defaultdict
from types import SimpleNamespace

from app.modules.similarity.intelligence.contract import Candidate, VerificationResult
from app.modules.similarity.intelligence.normalization import normalize_text, word_spans
from app.modules.similarity.models import SimilarityType

MIN_EVIDENCE_WORDS = 5


class DeterministicVerifier:
    """Emit contiguous lexical evidence; never infer copying from text shape."""

    name = "token-span-verifier-v2"

    def verify_all(
        self, target_text: str, candidate: Candidate
    ) -> tuple[VerificationResult, ...]:
        target = word_spans(target_text)
        source = word_spans(candidate.text)
        left = [normalize_text(target_text[a:b]) for a, b in target]
        right = [normalize_text(candidate.text[a:b]) for a, b in source]
        source_grams: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for index in range(len(right) - MIN_EVIDENCE_WORDS + 1):
            source_grams[tuple(right[index : index + MIN_EVIDENCE_WORDS])].append(index)
        blocks = []
        position = 0
        while position <= len(left) - MIN_EVIDENCE_WORDS:
            best_start, best_size = 0, 0
            for start in source_grams.get(
                tuple(left[position : position + MIN_EVIDENCE_WORDS]), []
            ):
                size = MIN_EVIDENCE_WORDS
                while (
                    position + size < len(left)
                    and start + size < len(right)
                    and left[position + size] == right[start + size]
                ):
                    size += 1
                if size > best_size:
                    best_start, best_size = start, size
            if best_size:
                blocks.append(SimpleNamespace(a=position, b=best_start, size=best_size))
                position += best_size
            else:
                position += 1
        results = []
        for block in blocks:
            ta, tb = target[block.a][0], target[block.a + block.size - 1][1]
            sa, sb = source[block.b][0], source[block.b + block.size - 1][1]
            if target_text == candidate.text and block.size == len(target):
                ta, tb, sa, sb = 0, len(target_text), 0, len(candidate.text)
            exact = target_text[ta:tb] == candidate.text[sa:sb]
            lexical = len(set(left) & set(right)) / max(1, len(set(left) | set(right)))
            results.append(
                VerificationResult(
                    match_type=(
                        SimilarityType.EXACT if exact else SimilarityType.NEAR_DUPLICATE
                    ),
                    target_span=(ta, tb),
                    source_span=(candidate.start_char + sa, candidate.start_char + sb),
                    scores={
                        "retrieval": candidate.retrieval_score,
                        "lexical": lexical,
                        "ngram": block.size / max(1, min(len(left), len(right))),
                        "structural": 0.0,
                        "verification": 1.0,
                    },
                    confidence=0.0,
                    evidence=(
                        f"contiguous_normalized_words={block.size}",
                        "raw_offsets_preserved",
                    ),
                    limitations=(
                        "Similarity is not a plagiarism determination.",
                        "Only contiguous lexical matches of at least five words are counted; semantic paraphrases are not tested.",
                        "No calibrated confidence is available. Token alignment is evidence, not an authorship probability.",
                    ),
                    verification_methods=(self.name,),
                )
            )
        return tuple(results)

    def verify(
        self, target_text: str, candidate: Candidate
    ) -> VerificationResult | None:
        results = self.verify_all(target_text, candidate)
        return (
            max(results, key=lambda item: item.target_span[1] - item.target_span[0])
            if results
            else None
        )


class SpanVerifierV2:
    """Align bounded passages; semantic scores are recomputed on exact sentences."""

    name = "span-alignment-v3"

    def __init__(self, provider):
        self.provider = provider
        self.lexical = DeterministicVerifier()

    def verify_all(self, target_text, candidate, structure=None):
        from difflib import SequenceMatcher
        from collections import Counter

        target, source = word_spans(target_text), word_spans(candidate.text)
        left = [normalize_text(target_text[a:b]) for a, b in target]
        right = [normalize_text(candidate.text[a:b]) for a, b in source]
        if not left or not right:
            return ()
        matcher = SequenceMatcher(None, left, right, autojunk=False)
        blocks = [b for b in matcher.get_matching_blocks() if b.size]
        if not blocks:
            return self._semantic(target_text, candidate, structure)
        matched = sum(b.size for b in blocks)
        order_score = 2 * matched / (len(left) + len(right))
        overlap = sum((Counter(left) & Counter(right)).values())
        lexical_score = 2 * overlap / (len(left) + len(right))
        # Near duplicates tolerate bounded edits. Lexical matches require real
        # ordered token alignments; shared length/punctuation alone never qualifies.
        if matched >= 6 and (
            (
                order_score >= 0.82
                and min(len(left), len(right)) / max(len(left), len(right)) >= 0.7
            )
            or (order_score >= 0.55 and lexical_score >= 0.55)
        ):
            first, last = blocks[0], blocks[-1]
            ta, tb = target[first.a][0], target[last.a + last.size - 1][1]
            sa, sb = source[first.b][0], source[last.b + last.size - 1][1]
            if left == right:
                # Identical chunk strings retain complete punctuation.
                if target_text == candidate.text:
                    ta, tb, sa, sb = 0, len(target_text), 0, len(candidate.text)
                kind = (
                    SimilarityType.EXACT
                    if target_text[ta:tb] == candidate.text[sa:sb]
                    else SimilarityType.NEAR_DUPLICATE
                )
            else:
                kind = (
                    SimilarityType.NEAR_DUPLICATE
                    if order_score >= 0.82
                    else SimilarityType.LEXICAL
                )
            coverage = tuple(
                (
                    target[b.a][0],
                    target[b.a + b.size - 1][1],
                    candidate.start_char + source[b.b][0],
                    candidate.start_char + source[b.b + b.size - 1][1],
                )
                for b in blocks
            )
            # An interval envelope may include edits. Exact token coverage is
            # stored separately so unmatched words never inflate the percentage.
            return (
                VerificationResult(
                    kind,
                    (ta, tb),
                    (candidate.start_char + sa, candidate.start_char + sb),
                    {
                        "retrieval": candidate.retrieval_score,
                        "lexical": lexical_score,
                        "ngram": order_score,
                        "structural": 0.0,
                        "verification": order_score,
                        "fingerprint": candidate.retrieval_scores.get("minhash", 0.0),
                    },
                    0.0,
                    (f"aligned_words={matched}", "explicit_alignment_spans"),
                    (
                        "Similarity is not a plagiarism determination.",
                        "Token alignment has no calibrated confidence.",
                        "Envelope spans may contain edits; only aligned words count as overlap.",
                    ),
                    (self.name,),
                    coverage_spans=coverage,
                ),
            )
        exact = self.lexical.verify_all(target_text, candidate)
        if exact:
            return exact
        return self._semantic(target_text, candidate, structure)

    def _semantic(self, target_text, candidate, structure):
        if (
            not self.provider.available
            or candidate.retrieval_scores.get("vector", 0.0) < 0.78
        ):
            return ()
        # The immutable parser decides sentence boundaries. Legacy spans without
        # stored sentence mapping abstain rather than silently being reparsed.
        targets = (structure or {}).get("sentences", [])[:8]
        sources = candidate.structure.get("sentences", [])[:8]
        targets = [
            s
            for s in targets
            if len(word_spans(target_text[s["start"] : s["end"]])) >= 6
        ]
        sources = [
            s
            for s in sources
            if len(word_spans(candidate.text[s["start"] : s["end"]])) >= 6
        ]
        if not targets or not sources:
            return ()
        vectors = self.provider.encode(
            [target_text[s["start"] : s["end"]] for s in targets]
            + [candidate.text[s["start"] : s["end"]] for s in sources]
        )
        result = []
        for i, target in enumerate(targets):
            best = max(
                range(len(sources)),
                key=lambda j: sum(
                    a * b for a, b in zip(vectors[i], vectors[len(targets) + j])
                ),
            )
            score = sum(a * b for a, b in zip(vectors[i], vectors[len(targets) + best]))
            if score < 0.82:
                continue
            source = sources[best]
            # Embedding similarity is passage evidence, not verified equivalence
            # or paraphrasing intent. STRUCTURAL/PROBABLE_PARAPHRASE abstain.
            result.append(
                VerificationResult(
                    SimilarityType.SEMANTIC,
                    (target["start"], target["end"]),
                    (
                        candidate.start_char + source["start"],
                        candidate.start_char + source["end"],
                    ),
                    {
                        "retrieval": candidate.retrieval_score,
                        "lexical": 0.0,
                        "ngram": 0.0,
                        "structural": 0.0,
                        "semantic": min(1.0, score),
                        "verification": min(1.0, score),
                    },
                    0.0,
                    ("sentence_embedding_cosine_recomputed_on_exact_spans",),
                    (
                        "Experimental semantic similarity is not calibrated confidence or a plagiarism determination.",
                        "Embeddings do not establish factual equivalence, source attribution or probable paraphrasing.",
                        "Semantic spans do not contribute unverified words to lexical overlap percentage.",
                    ),
                    ("local-sentence-span-cosine-v1",),
                    coverage_spans=(),
                )
            )
        return tuple(result)

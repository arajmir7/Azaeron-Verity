"""Reproducible similarity views. All percentages reduce exact target word spans."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.similarity.intelligence.normalization import word_spans

RULES_VERSION = "similarity-review-rules-v1"
GROUPS = {
    "UNCITED_UNQUOTED": "No citation or complete quotation detected",
    "MISSING_QUOTATIONS": "Citation marker present; quotation needs review",
    "MISSING_CITATIONS": "Quoted; no nearby citation detected",
    "CITED_QUOTED": "Quotation and nearby citation marker detected",
}
INTERPRETATION = (
    "Similarity measures overlapping words in the available workspace sources, not plagiarism or intent. "
    "A nearby citation marker does not prove attribution to the matched source. "
    "Quotation and citation findings are review prompts, not misconduct decisions."
)


class ExclusionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude_quotes: bool = False
    exclude_cited: bool = False
    exclude_bibliography: bool = True
    min_match_words: int = Field(default=5, ge=5, le=100)
    excluded_source_version_ids: list[str] = Field(default_factory=list, max_length=100)

    def canonical(self) -> dict:
        return {
            **self.model_dump(),
            "excluded_source_version_ids": sorted(
                set(self.excluded_source_version_ids)
            ),
            "rules_version": RULES_VERSION,
        }

    def fingerprint(self, analysis_id: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {"analysis_id": analysis_id, **self.canonical()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()


@dataclass
class TextAnnotations:
    text: str

    def __post_init__(self):
        self.words = word_spans(self.text)
        self.starts = [a for a, _ in self.words]
        self.ends = [b for _, b in self.words]
        self.quotes = [
            (m.start(1), m.end(1))
            for pattern in (
                r'"([^"\n]+)"',
                r"“([^”]+)”",
                r"(?<!\w)\u2018([^\u2019]+)\u2019(?!\w)",
                r"(?<!\w)'([^'\n]+)'(?!\w)",
                r"^\s*>[ \t]?(.*)$",
            )
            for m in re.finditer(pattern, self.text, re.MULTILINE)
        ]
        header = re.search(
            r"^\s*(?:references|bibliography|works cited)\s*:?[ \t]*$",
            self.text,
            re.IGNORECASE | re.MULTILINE,
        )
        self.bibliography = [(header.start(), len(self.text))] if header else []
        # Restrict citation association to a sentence/line containing a marker.
        # Neither marker syntax nor proximity verifies the identity of a source.
        self.cited = []
        citation = re.compile(
            r"\[\d+(?:\s*[,–-]\s*\d+)*\]|\([^()\n]{0,100}\b(?:19|20)\d{2}[a-z]?[^()\n]{0,40}\)"
        )
        for sentence in re.finditer(r"[^.!?\n]+(?:[.!?]|$)", self.text):
            if citation.search(sentence.group()):
                self.cited.append((sentence.start(), sentence.end()))
        self.quoted_words = self.indices(self.quotes)
        self.cited_words = self.indices(self.cited)
        self.bibliography_words = self.indices(self.bibliography)

    def indices(self, intervals: list[tuple[int, int]]) -> set[int]:
        result: set[int] = set()
        for start, end in intervals:
            result.update(
                range(bisect_right(self.ends, start), bisect_left(self.starts, end))
            )
        return result

    def classify(self, start: int, end: int) -> dict:
        words = self.indices([(start, end)])
        quoted = words & self.quoted_words
        quotation = (
            "QUOTED"
            if words and quoted == words
            else "PARTIALLY_QUOTED" if quoted else "UNQUOTED"
        )
        cited = bool(words & self.cited_words)
        group = (
            ("CITED_QUOTED" if cited else "MISSING_CITATIONS")
            if quotation == "QUOTED"
            else ("MISSING_QUOTATIONS" if cited else "UNCITED_UNQUOTED")
        )
        flags = []
        if quotation != "QUOTED":
            flags.append(
                {
                    "code": "MISSING_QUOTATION_REVIEW",
                    "explanation": "At least five matching words include text outside recognized quotation marks; check whether quotation is needed.",
                }
            )
        if not cited:
            flags.append(
                {
                    "code": "MISSING_CITATION_REVIEW",
                    "explanation": "No supported citation marker was found in the matched sentence; check attribution.",
                }
            )
        return {
            "quotation_status": quotation,
            "citation_status": (
                "CITATION_MARKER_PRESENT" if cited else "NO_CITATION_DETECTED"
            ),
            "group": group,
            "flags": flags,
            "matched_words": len(words),
        }

    def excluded_words(self, policy: ExclusionPolicy) -> set[int]:
        result: set[int] = set()
        for enabled, words in (
            (policy.exclude_quotes, self.quoted_words),
            (policy.exclude_cited, self.cited_words),
            (policy.exclude_bibliography, self.bibliography_words),
        ):
            if enabled:
                result.update(words)
        return result


def reduce_matches(text: str, matches: list[dict], policy: ExclusionPolicy) -> dict:
    """Linear word/interval reduction; sources and groups are not additive."""
    annotations = TextAnnotations(text)
    excluded = annotations.excluded_words(policy)
    eligible_count = len(annotations.words) - len(excluded)
    union: set[int] = set()
    group_words: dict[str, set[int]] = {key: set() for key in GROUPS}
    group_counts = {key: 0 for key in GROUPS}
    source_words: dict[str, set[int]] = {}
    source_info: dict[str, dict] = {}
    reviewed = []
    flag_counts: dict[str, int] = {}
    for match in matches:
        start, end = match["document_span_start"], match["document_span_end"]
        annotation = match.get("review") or annotations.classify(start, end)
        annotation = {
            **annotation,
            "flags": [
                {
                    **flag,
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"{match['id']}:{flag['code']}:{RULES_VERSION}",
                        )
                    ),
                    "evidence_node_id": str(match.get("evidence_node_id") or ""),
                }
                for flag in annotation["flags"]
            ],
        }
        words = annotations.indices([(start, end)])
        included = words - excluded
        reasons = []
        for enabled, spans, label in (
            (policy.exclude_quotes, annotations.quoted_words, "QUOTED_TEXT"),
            (policy.exclude_cited, annotations.cited_words, "CITATION_CONTEXT"),
            (
                policy.exclude_bibliography,
                annotations.bibliography_words,
                "BIBLIOGRAPHY",
            ),
        ):
            if enabled and words & spans:
                reasons.append(label)
        if len(words) < policy.min_match_words:
            included = set()
            reasons.append("SMALL_MATCH")
        source_id = match["source_document_version_id"]
        if source_id in policy.excluded_source_version_ids:
            included = set()
            reasons.append("SOURCE_EXCLUDED")
        item = {
            **match,
            **annotation,
            "included_words": len(included),
            "excluded": not bool(included),
            "exclusion_reasons": reasons,
        }
        reviewed.append(item)
        union.update(included)
        group_words[annotation["group"]].update(included)
        group_counts[annotation["group"]] += bool(included)
        for flag in annotation["flags"]:
            if included:
                flag_counts[flag["code"]] = flag_counts.get(flag["code"], 0) + 1
        source_words.setdefault(source_id, set()).update(included)
        source_info.setdefault(
            source_id,
            {
                "source_document_version_id": source_id,
                "source_document_id": match["source_document_id"],
                "title": match["source_title"],
                "category": "WORKSPACE_DOCUMENT",
                "corpus_state": "PRIVATE_WORKSPACE",
                "content_hash": match["source_content_hash"],
                "retrieved_at": match["retrieved_at"],
                "match_count": 0,
            },
        )["match_count"] += bool(included)

    def percentage(count):
        return round(100 * count / eligible_count, 2) if eligible_count else None

    sources = [
        {
            **source_info[key],
            "matched_words": len(words),
            "percentage": percentage(len(words)),
            "excluded": key in policy.excluded_source_version_ids,
        }
        for key, words in source_words.items()
    ]
    sources.sort(
        key=lambda item: (-item["matched_words"], item["source_document_version_id"])
    )
    for rank, source in enumerate(sources, 1):
        source["rank"] = rank
    return {
        "summary": {
            "total_words": len(annotations.words),
            "eligible_words": eligible_count,
            "excluded_words": len(excluded),
            "matched_words": len(union),
            "percentage": percentage(len(union)),
            "included_match_count": sum(not m["excluded"] for m in reviewed),
            "recorded_match_count": len(reviewed),
        },
        "groups": [
            {
                "key": key,
                "label": label,
                "matches": group_counts[key],
                "matched_words": len(group_words[key]),
                "percentage": percentage(len(group_words[key])),
            }
            for key, label in GROUPS.items()
        ],
        "flags": [
            {"code": key, "match_count": count}
            for key, count in sorted(flag_counts.items())
        ],
        "matches": reviewed,
        "sources": sources,
    }

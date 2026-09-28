"""Deterministic, baseline-relative authorship consistency statistics.

This module measures style distance only. It never identifies a person and it
never converts stylistic deviation into an AI-writing conclusion.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping, Sequence

FEATURE_VERSION = "authorship-features-v2"
MIN_BASELINE_DOCUMENTS = 3
MIN_BASELINE_WORDS = 500
MIN_DOCUMENT_WORDS = 80

FUNCTION_WORDS = (
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "him",
    "his",
    "if",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "which",
    "who",
    "with",
    "would",
    "you",
    "your",
)
DISCOURSE_MARKERS = (
    "although",
    "because",
    "consequently",
    "however",
    "indeed",
    "moreover",
    "otherwise",
    "similarly",
    "therefore",
    "thus",
    "while",
    "whereas",
)
PUNCTUATION = (".", ",", ";", ":", "!", "?", "-", "(", ")", "'", '"')
SCALAR_GROUPS: Mapping[str, tuple[str, ...]] = {
    "sentence_structure": (
        "mean_sentence_length",
        "sentence_length_stddev",
        "sentence_length_median",
    ),
    "syntax": (
        "clause_marker_rate",
        "subordination_marker_rate",
        "sentence_complexity_proxy",
    ),
    "vocabulary_richness": (
        "type_token_ratio",
        "hapax_ratio",
        "mean_word_length",
        "long_word_ratio",
    ),
}


def _tokens(text: str) -> list[str]:
    return re.findall(
        r"[\wÀ-ÖØ-öø-ÿ]+(?:['’\-][\wÀ-ÖØ-öø-ÿ]+)?", text.casefold(), flags=re.UNICODE
    )


def _sentences(text: str) -> list[str]:
    return [
        part.strip() for part in re.findall(r"[^.!?]+(?:[.!?]|$)", text) if part.strip()
    ]


def _normalized_distribution(
    values: Iterable[str], limit: int = 100
) -> dict[str, float]:
    counts = Counter(values)
    total = sum(counts.values())
    if not total:
        return {}
    return {key: round(value / total, 8) for key, value in counts.most_common(limit)}


def _mean_distributions(
    distributions: Sequence[Mapping[str, float]],
) -> dict[str, float]:
    keys = {key for distribution in distributions for key in distribution}
    if not distributions:
        return {}
    result = {
        key: mean(distribution.get(key, 0.0) for distribution in distributions)
        for key in keys
    }
    total = sum(result.values())
    if total:
        result = {key: round(value / total, 8) for key, value in result.items()}
    return result


def _l1_distance(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    return min(
        1.0,
        sum(
            abs(left.get(key, 0.0) - right.get(key, 0.0))
            for key in set(left) | set(right)
        )
        / 2.0,
    )


def _jensen_shannon_distance(
    left: Mapping[str, float], right: Mapping[str, float]
) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    midpoint = {key: (left.get(key, 0.0) + right.get(key, 0.0)) / 2 for key in keys}

    def kl(distribution: Mapping[str, float]) -> float:
        return sum(
            value * math.log2(value / midpoint[key])
            for key, value in ((key, distribution.get(key, 0.0)) for key in keys)
            if value > 0 and midpoint[key] > 0
        )

    return min(1.0, math.sqrt(max(0.0, (kl(left) + kl(right)) / 2)))


def _round(value: float) -> float:
    return round(float(value), 6)


@dataclass(frozen=True)
class FeatureVector:
    """A versioned, JSON-safe stylometric feature vector."""

    source_id: str
    word_count: int
    sentence_count: int
    paragraph_count: int
    scalars: Mapping[str, float]
    lexical_distribution: Mapping[str, float]
    function_word_distribution: Mapping[str, float]
    punctuation_distribution: Mapping[str, float]
    discourse_distribution: Mapping[str, float]
    phrase_distribution: Mapping[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_version": FEATURE_VERSION,
            "source_id": self.source_id,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "paragraph_count": self.paragraph_count,
            "scalars": dict(self.scalars),
            "lexical_distribution": dict(self.lexical_distribution),
            "function_word_distribution": dict(self.function_word_distribution),
            "punctuation_distribution": dict(self.punctuation_distribution),
            "discourse_distribution": dict(self.discourse_distribution),
            "phrase_distribution": dict(self.phrase_distribution),
        }


class AuthorshipFeatureAnalyzer:
    """Extract features, build a baseline, and compare a target document."""

    feature_version = FEATURE_VERSION

    @staticmethod
    def extract(
        text: str, source_id: str = "target", structure: Mapping[str, Any] | None = None
    ) -> FeatureVector:
        normalized = text or ""
        words = _tokens(normalized)
        sentences = (
            [normalized[item["start"] : item["end"]] for item in structure["sentences"]]
            if structure
            else _sentences(normalized)
        )
        paragraphs = (
            [
                normalized[item["start"] : item["end"]]
                for item in structure["paragraphs"]
            ]
            if structure
            else [
                part.strip()
                for part in re.split(r"\n\s*\n", normalized)
                if part.strip()
            ]
        )
        sentence_lengths = [len(_tokens(sentence)) for sentence in sentences]
        mean_sentence_length = mean(sentence_lengths) if sentence_lengths else 0.0
        sentence_length_stddev = (
            pstdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
        )
        sentence_length_median = (
            sorted(sentence_lengths)[len(sentence_lengths) // 2]
            if sentence_lengths
            else 0.0
        )
        word_counts = Counter(words)
        bigrams = [f"{left} {right}" for left, right in zip(words, words[1:])]
        clause_markers = sum(
            normalized.casefold().count(marker)
            for marker in (
                ",",
                ";",
                " which ",
                " that ",
                " because ",
                " although ",
                " while ",
            )
        )
        subordination_markers = sum(
            normalized.casefold().count(marker)
            for marker in (
                " because ",
                " although ",
                " while ",
                " whereas ",
                " unless ",
                " if ",
            )
        )
        punctuation_values = [
            character for character in normalized if character in PUNCTUATION
        ]
        function_values = [word for word in words if word in FUNCTION_WORDS]
        discourse_values = [
            marker
            for marker in DISCOURSE_MARKERS
            for _ in range(normalized.casefold().count(f" {marker} "))
        ]
        unique_words = len(word_counts)
        scalars = {
            "mean_sentence_length": _round(mean_sentence_length),
            "sentence_length_stddev": _round(sentence_length_stddev),
            "sentence_length_median": _round(sentence_length_median),
            "clause_marker_rate": _round(clause_markers / max(1, len(words))),
            "subordination_marker_rate": _round(
                subordination_markers / max(1, len(words))
            ),
            "sentence_complexity_proxy": _round(
                clause_markers / max(1, len(sentences))
            ),
            "type_token_ratio": _round(unique_words / max(1, len(words))),
            "hapax_ratio": _round(
                sum(count == 1 for count in word_counts.values()) / max(1, unique_words)
            ),
            "mean_word_length": _round(
                sum(len(word) for word in words) / max(1, len(words))
            ),
            "long_word_ratio": _round(
                sum(len(word) >= 8 for word in words) / max(1, len(words))
            ),
        }
        punctuation_distribution = _normalized_distribution(
            punctuation_values, limit=len(PUNCTUATION)
        )
        for mark in PUNCTUATION:
            punctuation_distribution.setdefault(mark, 0.0)
        function_distribution = _normalized_distribution(
            function_values, limit=len(FUNCTION_WORDS)
        )
        for word in FUNCTION_WORDS:
            function_distribution.setdefault(word, 0.0)
        discourse_distribution = _normalized_distribution(
            discourse_values, limit=len(DISCOURSE_MARKERS)
        )
        for marker in DISCOURSE_MARKERS:
            discourse_distribution.setdefault(marker, 0.0)
        return FeatureVector(
            source_id=source_id,
            word_count=len(words),
            sentence_count=len(sentences),
            paragraph_count=len(paragraphs),
            scalars=scalars,
            lexical_distribution=_normalized_distribution(words),
            function_word_distribution=function_distribution,
            punctuation_distribution=punctuation_distribution,
            discourse_distribution=discourse_distribution,
            phrase_distribution=_normalized_distribution(bigrams),
        )

    def build_baseline(
        self,
        texts: Sequence[tuple[str, str]],
        structures: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        vectors = [
            self.extract(text, source_id, (structures or {}).get(source_id))
            for source_id, text in texts
            if text and text.strip()
        ]
        total_words = sum(vector.word_count for vector in vectors)
        min_words = min((vector.word_count for vector in vectors), default=0)
        reasons: list[str] = []
        if len(vectors) < MIN_BASELINE_DOCUMENTS:
            reasons.append(
                f"at least {MIN_BASELINE_DOCUMENTS} baseline documents are required"
            )
        if total_words < MIN_BASELINE_WORDS:
            reasons.append(f"at least {MIN_BASELINE_WORDS} baseline words are required")
        if min_words < MIN_DOCUMENT_WORDS:
            reasons.append(
                f"each baseline document must contain at least {MIN_DOCUMENT_WORDS} words"
            )
        quality = (
            "INSUFFICIENT"
            if reasons
            else "STRONG" if len(vectors) >= 5 and total_words >= 1500 else "ADEQUATE"
        )
        scalar_keys = (
            set().union(*(vector.scalars.keys() for vector in vectors))
            if vectors
            else set()
        )
        scalar_stats = {
            key: {
                "mean": _round(
                    mean(vector.scalars.get(key, 0.0) for vector in vectors)
                ),
                "stddev": _round(
                    pstdev([vector.scalars.get(key, 0.0) for vector in vectors])
                    if len(vectors) > 1
                    else 0.0
                ),
            }
            for key in sorted(scalar_keys)
        }
        bundle = {
            "feature_version": FEATURE_VERSION,
            "baseline_quality": quality,
            "quality_reasons": reasons,
            "sample_count": len(vectors),
            "total_words": total_words,
            "min_document_words": min_words,
            "source_ids": [vector.source_id for vector in vectors],
            "source_fingerprint": hashlib.sha256(
                "|".join(vector.source_id for vector in vectors).encode()
            ).hexdigest(),
            "scalar_stats": scalar_stats,
            "distributions": {
                "lexical_distribution": _mean_distributions(
                    [vector.lexical_distribution for vector in vectors]
                ),
                "function_word_distribution": _mean_distributions(
                    [vector.function_word_distribution for vector in vectors]
                ),
                "punctuation_distribution": _mean_distributions(
                    [vector.punctuation_distribution for vector in vectors]
                ),
                "discourse_distribution": _mean_distributions(
                    [vector.discourse_distribution for vector in vectors]
                ),
                "phrase_distribution": _mean_distributions(
                    [vector.phrase_distribution for vector in vectors]
                ),
            },
        }
        return bundle

    def compare(
        self, target: FeatureVector, baseline: Mapping[str, Any]
    ) -> dict[str, Any]:
        quality = str(baseline.get("baseline_quality") or "INSUFFICIENT")
        if (
            quality not in {"ADEQUATE", "STRONG"}
            or target.word_count < MIN_DOCUMENT_WORDS
        ):
            reasons = list(baseline.get("quality_reasons") or [])
            if target.word_count < MIN_DOCUMENT_WORDS:
                reasons.append(
                    f"target document must contain at least {MIN_DOCUMENT_WORDS} words"
                )
            return {
                "eligible": False,
                "baseline_quality": quality,
                "quality_reasons": reasons,
                "target_features": target.as_dict(),
                "signals": [],
                "family_scores": {},
                "stylistic_deviation": None,
            }

        signals: list[dict[str, Any]] = []
        scalar_stats = baseline.get("scalar_stats") or {}
        for family, keys in SCALAR_GROUPS.items():
            deviations = []
            details = []
            for key in keys:
                stats = scalar_stats.get(key) or {"mean": 0.0, "stddev": 0.0}
                value = float(target.scalars.get(key, 0.0))
                base_mean = float(stats.get("mean", 0.0))
                scale = max(float(stats.get("stddev", 0.0)), abs(base_mean) * 0.1, 0.01)
                z_score = abs(value - base_mean) / scale
                deviation = min(1.0, z_score / 3.0)
                deviations.append(deviation)
                details.append(
                    {
                        "feature": key,
                        "target": _round(value),
                        "baseline_mean": _round(base_mean),
                        "baseline_stddev": _round(float(stats.get("stddev", 0.0))),
                        "z_score": _round(z_score),
                    }
                )
            signals.append(
                {
                    "family": family,
                    "signal_name": family,
                    "deviation": _round(mean(deviations) if deviations else 0.0),
                    "method": "baseline_standardized_absolute_deviation",
                    "details": details,
                    "summary": f"{family.replace('_', ' ').capitalize()} was compared with the validated baseline distribution.",
                }
            )

        distributions = baseline.get("distributions") or {}
        distribution_specs = (
            (
                "lexical",
                "lexical_distribution",
                _jensen_shannon_distance,
                "Jensen-Shannon distance",
            ),
            (
                "function_words",
                "function_word_distribution",
                _l1_distance,
                "normalized L1 distance",
            ),
            (
                "punctuation",
                "punctuation_distribution",
                _l1_distance,
                "normalized L1 distance",
            ),
            (
                "discourse",
                "discourse_distribution",
                _l1_distance,
                "normalized L1 distance",
            ),
            (
                "phrase_patterns",
                "phrase_distribution",
                _l1_distance,
                "normalized L1 distance",
            ),
        )
        for family, feature_name, distance, method in distribution_specs:
            target_distribution = getattr(target, feature_name)
            baseline_distribution = distributions.get(feature_name) or {}
            deviation = distance(target_distribution, baseline_distribution)
            signals.append(
                {
                    "family": family,
                    "signal_name": feature_name,
                    "deviation": _round(deviation),
                    "method": method,
                    "target": dict(target_distribution),
                    "baseline": dict(baseline_distribution),
                    "summary": f"{family.replace('_', ' ').capitalize()} distribution distance was measured against the baseline.",
                }
            )

        family_scores = {
            family: _round(
                mean(
                    signal["deviation"]
                    for signal in signals
                    if signal["family"] == family
                )
            )
            for family in {signal["family"] for signal in signals}
        }
        weighted_families = {
            "lexical": 0.15,
            "function_words": 0.15,
            "sentence_structure": 0.15,
            "syntax": 0.10,
            "punctuation": 0.10,
            "vocabulary_richness": 0.15,
            "discourse": 0.10,
            "phrase_patterns": 0.10,
        }
        score = sum(
            family_scores.get(family, 0.0) * weight
            for family, weight in weighted_families.items()
        )
        return {
            "eligible": True,
            "baseline_quality": quality,
            "quality_reasons": [],
            "target_features": target.as_dict(),
            "signals": signals,
            "family_scores": family_scores,
            "stylistic_deviation": _round(score),
            "comparison_method": "weighted_baseline_relative_statistics-v1",
        }


def data_adequacy_confidence(
    baseline: Mapping[str, Any], target_word_count: int
) -> float | None:
    """Return data sufficiency, explicitly not authorship probability."""

    if (
        baseline.get("baseline_quality") == "INSUFFICIENT"
        or target_word_count < MIN_DOCUMENT_WORDS
    ):
        return None
    sample_factor = min(1.0, float(baseline.get("sample_count", 0)) / 8.0)
    baseline_word_factor = min(1.0, float(baseline.get("total_words", 0)) / 3000.0)
    target_word_factor = min(1.0, target_word_count / 1000.0)
    return _round(
        0.2
        + 0.3 * sample_factor
        + 0.3 * baseline_word_factor
        + 0.2 * target_word_factor
    )

"""Independent, auditable signal providers.

These providers expose descriptive measurements only. They intentionally do
not convert style measurements into an authorship label.
"""

from collections import Counter
import math
import re
from typing import Any, Mapping, Protocol, Sequence

from app.modules.detection.intelligence.contract import (
    AnalysisSegment,
    InferenceContext,
    ProviderOutput,
    SignalEvidence,
    SignalStatus,
)


class SignalProvider(Protocol):
    provider_id: str
    provider_version: str
    family: str

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput: ...


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w’'-]+\b", text.lower(), flags=re.UNICODE)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _entropy(values: Sequence[str]) -> float:
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return round(
        -sum((count / total) * math.log2(count / total) for count in counts.values()), 6
    )


class LinguisticSignalProvider:
    provider_id = "linguistic-signals"
    provider_version = "linguistic-signals-v1"
    family = "linguistic"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        text = " ".join(
            segment.text for segment in segments if segment.segment_type == "document"
        )
        words = _words(text)
        sentences = [
            segment for segment in segments if segment.segment_type == "sentence"
        ]
        lengths = [len(_words(segment.text)) for segment in sentences]
        mean = sum(lengths) / len(lengths) if lengths else 0.0
        variance = (
            sum((length - mean) ** 2 for length in lengths) / len(lengths)
            if lengths
            else 0.0
        )
        unique = len(set(words))
        bigrams = list(zip(words, words[1:]))
        repetition = 1 - _ratio(len(set(bigrams)), len(bigrams))
        features = {
            "word_count": len(words),
            "vocabulary_diversity": _ratio(unique, len(words)),
            "lexical_entropy_bits": _entropy(words),
            "mean_sentence_length": round(mean, 6),
            "sentence_length_stddev": round(math.sqrt(variance), 6),
            "repetition_ratio": round(repetition, 6),
        }
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                "vocabulary_diversity",
                "Unique-word ratio was measured from the normalized document.",
                SignalStatus.OBSERVED,
                features["vocabulary_diversity"],
                metadata={"word_count": len(words)},
            ),
            SignalEvidence(
                self.family,
                "document",
                "lexical_entropy",
                "Lexical entropy was measured; it is descriptive and domain-sensitive.",
                SignalStatus.OBSERVED,
                features["lexical_entropy_bits"],
            ),
            SignalEvidence(
                self.family,
                "document",
                "repetition_ratio",
                "Adjacent-token repetition was measured without assigning an authorship label.",
                SignalStatus.OBSERVED,
                features["repetition_ratio"],
            ),
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.OBSERVED,
            features,
            evidence,
        )


class StylometricSignalProvider:
    provider_id = "stylometric-signals"
    provider_version = "stylometric-signals-v1"
    family = "stylometric"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        text = " ".join(
            segment.text for segment in segments if segment.segment_type == "document"
        )
        words = _words(text)
        characters = [char for char in text if not char.isspace()]
        function_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "if",
            "to",
            "of",
            "in",
            "on",
            "for",
            "with",
            "is",
            "are",
            "was",
            "were",
        }
        features = {
            "mean_word_length": _ratio(sum(len(word) for word in words), len(words)),
            "function_word_ratio": _ratio(
                sum(word in function_words for word in words), len(words)
            ),
            "punctuation_density": _ratio(
                sum(char in ",.;:!?" for char in text), len(characters)
            ),
            "uppercase_ratio": _ratio(
                sum(char.isupper() for char in text), len(characters)
            ),
            "long_word_ratio": _ratio(
                sum(len(word) >= 8 for word in words), len(words)
            ),
        }
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                "mean_word_length",
                "Mean token length was measured.",
                SignalStatus.OBSERVED,
                features["mean_word_length"],
            ),
            SignalEvidence(
                self.family,
                "document",
                "function_word_ratio",
                "Function-word usage was measured.",
                SignalStatus.OBSERVED,
                features["function_word_ratio"],
            ),
            SignalEvidence(
                self.family,
                "document",
                "punctuation_density",
                "Punctuation density was measured.",
                SignalStatus.OBSERVED,
                features["punctuation_density"],
            ),
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.OBSERVED,
            features,
            evidence,
        )


class SyntacticSignalProvider:
    provider_id = "syntactic-signals"
    provider_version = "syntactic-signals-v1"
    family = "syntactic"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        text = " ".join(
            segment.text for segment in segments if segment.segment_type == "document"
        ).lower()
        connectors = (
            "however",
            "therefore",
            "because",
            "although",
            "while",
            "moreover",
            "although",
            "which",
        )
        connector_count = sum(text.count(connector) for connector in connectors)
        clauses = sum(
            text.count(marker)
            for marker in (",", ";", " which ", " that ", " because ")
        )
        features = {
            "discourse_connector_count": connector_count,
            "clause_marker_count": clauses,
            "connector_rate": _ratio(connector_count, len(_words(text))),
        }
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                "discourse_connectors",
                "A deterministic connector count was measured.",
                SignalStatus.OBSERVED,
                float(connector_count),
            ),
            SignalEvidence(
                self.family,
                "document",
                "clause_markers",
                "A conservative clause-marker proxy was measured.",
                SignalStatus.OBSERVED,
                float(clauses),
            ),
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.OBSERVED,
            features,
            evidence,
        )


class SegmentSignalProvider:
    provider_id = "segment-signals"
    provider_version = "segment-signals-v1"
    family = "segment-level"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        sentence_segments = [
            segment for segment in segments if segment.segment_type == "sentence"
        ]
        features: dict[str, Any] = {
            "segment_count": len(sentence_segments),
            "segments": [],
        }
        evidence: list[SignalEvidence] = []
        for segment in sentence_segments:
            tokens = _words(segment.text)
            diversity = _ratio(len(set(tokens)), len(tokens))
            features["segments"].append(
                {
                    "index": segment.index,
                    "word_count": len(tokens),
                    "vocabulary_diversity": diversity,
                }
            )
            evidence.append(
                SignalEvidence(
                    self.family,
                    "segment",
                    "segment_vocabulary_diversity",
                    "Segment vocabulary diversity was measured.",
                    SignalStatus.OBSERVED,
                    diversity,
                    segment.index,
                )
            )
        status = (
            SignalStatus.OBSERVED if sentence_segments else SignalStatus.UNAVAILABLE
        )
        if not sentence_segments:
            evidence.append(
                SignalEvidence(
                    self.family,
                    "segment",
                    "segment_vocabulary_diversity",
                    "No sentence segments were available.",
                    status,
                )
            )
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            status,
            features,
            evidence,
        )


class DocumentSignalProvider:
    provider_id = "document-signals"
    provider_version = "document-signals-v1"
    family = "document-level"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        document = next(
            (segment for segment in segments if segment.segment_type == "document"),
            None,
        )
        paragraphs = [
            segment for segment in segments if segment.segment_type == "paragraph"
        ]
        sentences = [
            segment for segment in segments if segment.segment_type == "sentence"
        ]
        text = document.text if document else ""
        features = {
            "character_count": len(text),
            "word_count": len(_words(text)),
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
        }
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                name,
                f"{name.replace('_', ' ').capitalize()} was recorded from segmentation.",
                SignalStatus.OBSERVED,
                float(value),
            )
            for name, value in features.items()
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.OBSERVED,
            features,
            evidence,
        )


class UnavailableSignalProvider:
    def __init__(
        self,
        provider_id: str,
        family: str,
        reason: str,
        provider_version: str = "unavailable-v1",
    ):
        self.provider_id = provider_id
        self.provider_version = provider_version
        self.family = family
        self.reason = reason

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                self.provider_id,
                self.reason,
                SignalStatus.UNAVAILABLE,
            )
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.UNAVAILABLE,
            {},
            evidence,
        )


class AuthorshipConsistencyProvider(UnavailableSignalProvider):
    def __init__(self) -> None:
        super().__init__(
            "authorship-consistency",
            "authorship-consistency",
            "No validated author baseline was supplied; authorship consistency is not tested.",
            "authorship-consistency-unavailable-v1",
        )


class RevisionProvenanceProvider:
    provider_id = "revision-provenance"
    provider_version = "revision-provenance-v1"
    family = "revision/provenance"

    def extract(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> ProviderOutput:
        metadata = dict(context.metadata)
        if "revision_count" not in metadata and "input_fingerprint" not in metadata:
            evidence = [
                SignalEvidence(
                    self.family,
                    "document",
                    "revision_history",
                    "Revision history was not supplied; provenance was not tested.",
                    SignalStatus.UNAVAILABLE,
                )
            ]
            return ProviderOutput(
                self.provider_id,
                self.provider_version,
                self.family,
                SignalStatus.UNAVAILABLE,
                {},
                evidence,
            )
        features = {
            "revision_count": metadata.get("revision_count"),
            "input_fingerprint_present": bool(metadata.get("input_fingerprint")),
        }
        evidence = [
            SignalEvidence(
                self.family,
                "document",
                "revision_history",
                "Available revision metadata was recorded; it does not establish authorship.",
                SignalStatus.OBSERVED,
                metadata.get("revision_count"),
                metadata=dict(features),
            )
        ]
        return ProviderOutput(
            self.provider_id,
            self.provider_version,
            self.family,
            SignalStatus.OBSERVED,
            features,
            evidence,
        )


def default_signal_providers() -> list[SignalProvider]:
    return [
        LinguisticSignalProvider(),
        StylometricSignalProvider(),
        SyntacticSignalProvider(),
        SegmentSignalProvider(),
        DocumentSignalProvider(),
        UnavailableSignalProvider(
            "semantic-signals",
            "semantic",
            "Semantic-model analysis is unavailable until a validated model is registered.",
            "semantic-signals-unavailable-v1",
        ),
        AuthorshipConsistencyProvider(),
        RevisionProvenanceProvider(),
    ]

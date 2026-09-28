"""Conservative, explainable editorial rules for AZAERON WRITE.

These rules improve observable mechanics and phrasing only. They do not score,
hide, or optimize text against any detector or provenance system.
"""

from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
import re
from typing import Callable, Iterable

from app.modules.aegiswrite.models import EditType
from app.modules.aegiswrite.invariants import protected_spans, ProtectionIndex

EDITORIAL_ENGINE_VERSION = "editorial-rules-v2-protected-spans"


@dataclass(frozen=True)
class EditorialChange:
    edit_type: EditType
    dimension: str
    original: str
    revision: str
    reason: str
    span_start: int
    span_end: int
    metadata: dict[str, str]


Rule = Callable[[str, bool], Iterable[EditorialChange]]


def _case_preserving(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _phrase_rule(
    text: str,
    edit_type: EditType,
    dimension: str,
    pattern: str,
    replacement: str,
    reason: str,
) -> Iterable[EditorialChange]:
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        original = match.group(0)
        revision = _case_preserving(original, replacement)
        if original == revision:
            continue
        yield EditorialChange(
            edit_type=edit_type,
            dimension=dimension,
            original=original,
            revision=revision,
            reason=reason,
            span_start=match.start(),
            span_end=match.end(),
            metadata={"rule": "phrase_substitution"},
        )


def _spacing_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    for match in re.finditer(r"[ \t]{2,}", text):
        yield EditorialChange(
            edit_type=EditType.GRAMMAR,
            dimension="grammar",
            original=match.group(0),
            revision=" ",
            reason="Normalized repeated spaces without changing the author’s wording.",
            span_start=match.start(),
            span_end=match.end(),
            metadata={"rule": "repeated_spacing"},
        )


def _punctuation_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    for match in re.finditer(r"\s+([,.;:!?])", text):
        yield EditorialChange(
            edit_type=EditType.GRAMMAR,
            dimension="grammar",
            original=match.group(0),
            revision=match.group(1),
            reason="Removed whitespace before punctuation while preserving the sentence.",
            span_start=match.start(),
            span_end=match.end(),
            metadata={"rule": "punctuation_spacing"},
        )
    for match in re.finditer(r"([!?])\1+", text):
        yield EditorialChange(
            edit_type=EditType.GRAMMAR,
            dimension="grammar",
            original=match.group(0),
            revision=match.group(1),
            reason="Reduced repeated terminal punctuation to one mark.",
            span_start=match.start(),
            span_end=match.end(),
            metadata={"rule": "repeated_punctuation"},
        )


def _duplicate_word_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    for match in re.finditer(
        r"\b([A-Za-z][A-Za-z'-]*)\s+\1\b", text, flags=re.IGNORECASE
    ):
        first, second = match.span(1), match.span(0)
        original = text[second[0] : second[1]]
        word = text[first[0] : first[1]]
        yield EditorialChange(
            edit_type=EditType.GRAMMAR,
            dimension="grammar",
            original=original,
            revision=word,
            reason="Removed an adjacent repeated word while preserving the sentence meaning.",
            span_start=second[0],
            span_end=second[1],
            metadata={"rule": "duplicate_word"},
        )


def _concision_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    replacements = (
        (
            r"\bin order to\b",
            "to",
            "Replaced a wordy connector with a direct equivalent.",
        ),
        (
            r"\bdue to the fact that\b",
            "because",
            "Replaced a wordy causal phrase with a direct equivalent.",
        ),
        (
            r"\bat this point in time\b",
            "now",
            "Removed a time-based filler without changing the claim.",
        ),
        (r"\ba wide range of\b", "many", "Made a broad quantity phrase more concise."),
    )
    for pattern, replacement, reason in replacements:
        yield from _phrase_rule(
            text, EditType.CONCISION, "conciseness", pattern, replacement, reason
        )


def _clarity_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    yield from _phrase_rule(
        text,
        EditType.CLARITY,
        "clarity",
        r"\bit is important to note that\b",
        "notably,",
        "Removed a padded opening so the sentence reaches its point sooner.",
    )


def _tone_rule(text: str, preserve_voice: bool) -> Iterable[EditorialChange]:
    # Tone edits are opt-in through EditType.TONE. Even then, preserve_voice
    # limits changes to conventional formal contractions.
    if not preserve_voice:
        return
    replacements = {
        "can't": "cannot",
        "won't": "will not",
        "don't": "do not",
        "doesn't": "does not",
        "isn't": "is not",
        "aren't": "are not",
        "it's": "it is",
        "we're": "we are",
    }
    for source, replacement in replacements.items():
        yield from _phrase_rule(
            text,
            EditType.TONE,
            "academic_tone",
            rf"\b{re.escape(source)}\b",
            replacement,
            "Expanded a contraction for a more formal academic register while preserving the author’s voice and meaning.",
        )


def _structure_rule(text: str, _preserve_voice: bool) -> Iterable[EditorialChange]:
    for match in re.finditer(r"\n{3,}", text):
        yield EditorialChange(
            edit_type=EditType.STRUCTURE,
            dimension="paragraph_organization",
            original=match.group(0),
            revision="\n\n",
            reason="Normalized excessive paragraph spacing without changing paragraph boundaries.",
            span_start=match.start(),
            span_end=match.end(),
            metadata={"rule": "paragraph_spacing"},
        )


RULES: tuple[Rule, ...] = (
    _spacing_rule,
    _punctuation_rule,
    _duplicate_word_rule,
    _concision_rule,
    _clarity_rule,
    _tone_rule,
    _structure_rule,
)


def analyze_editorial_changes(
    text: str,
    edit_types: set[EditType],
    preserve_voice: bool = True,
    span_start: int = 0,
    span_end: int | None = None,
    locked_spans: Iterable[tuple[int, int]] = (),
) -> list[EditorialChange]:
    """Return bounded, non-overlapping changes supported by observable text."""
    end = len(text) if span_end is None else span_end
    protected = ProtectionIndex(protected_spans(text, locked_spans))
    changes = [
        change
        for rule in RULES
        for change in rule(text, preserve_voice)
        if change.edit_type in edit_types
        and span_start <= change.span_start
        and change.span_end <= end
        and not protected.overlaps(change.span_start, change.span_end)
    ]
    changes.sort(key=lambda item: (item.span_start, item.span_end, item.dimension))
    selected: list[EditorialChange] = []
    for change in changes:
        if selected and change.span_start < selected[-1].span_end:
            continue
        selected.append(change)
    return selected


def apply_editorial_changes(
    text: str,
    changes: Iterable[EditorialChange],
    locked_spans: Iterable[tuple[int, int]] = (),
) -> str:
    ordered = sorted(changes, key=lambda item: item.span_start)
    protected = protected_spans(text, locked_spans)
    protection = ProtectionIndex(protected)
    previous_end = 0
    parts: list[str] = []
    offsets = [0]
    for change in ordered:
        if (
            not previous_end <= change.span_start < change.span_end <= len(text)
            or text[change.span_start : change.span_end] != change.original
        ):
            raise ValueError("Editorial changes do not match the original text")
        if protection.overlaps(change.span_start, change.span_end):
            raise ValueError("Editorial change would alter protected material")
        parts.extend((text[previous_end : change.span_start], change.revision))
        offsets.append(offsets[-1] + len(change.revision) - len(change.original))
        previous_end = change.span_end
    parts.append(text[previous_end:])
    revised = "".join(parts)
    ends = [change.span_end for change in ordered]
    for span in protected:
        offset = offsets[bisect_right(ends, span.start)]
        if revised[span.start + offset : span.end + offset] != span.value:
            raise ValueError("Protected material failed post-edit verification")
    return revised

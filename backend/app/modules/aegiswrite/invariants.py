"""Conservative protected spans; this does not claim semantic verification."""

from dataclasses import dataclass
import re
from typing import Iterable
from bisect import bisect_left


@dataclass(frozen=True)
class ProtectedSpan:
    start: int
    end: int
    kind: str
    value: str


PATTERNS = (
    ("negation", r"\b(?i:not|no|never|without|cannot)\b|(?i:n['’]t)\b"),
    (
        "causal_qualifier",
        r"\b(?i:may|might|could|approximately|estimated|possibly|unless|at least|at most|associated with|correlated with|because|causes?|caused)\b",
    ),
    (
        "date",
        r"\b(?i:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,?\s+\d{4})?\b",
    ),
    ("code", r"```[^\n]*\n[\s\S]*?(?:```|\Z)|~~~[^\n]*\n[\s\S]*?(?:~~~|\Z)|`[^`\n]+`"),
    (
        "quotation",
        r'"[^"\n]+"|“[^”]+”|(?<!\w)‘[^’]+’(?!\w)|(?<!\w)\x27[^\x27\n]+\x27(?!\w)|^[ \t]*>[^\n]*',
    ),
    (
        "identifier",
        r"https?://[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b10\.\d{4,9}/[^\s<>]+",
    ),
    (
        "citation",
        r"\[[^\]\n]{1,200}\]|\([^()\n]{0,100}\b(?:19|20)\d{2}[a-z]?[^()\n]{0,40}\)",
    ),
    ("number", r"(?<!\w)[+-]?(?:[$€£₹][ \t]*)?\d+(?:[.,:/-]\d+)*(?:[ \t]*%)?"),
    ("math", r"\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]"),
    (
        "reference",
        r"^[ \t]*(?:#{1,6}[ \t]+)?(?i:references|bibliography|works cited)[ \t]*:?[ \t]*$[\s\S]*",
    ),
    # A conservative proper-name guard, not a claim of comprehensive NER.
    ("name", r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+\b"),
)


def protected_spans(
    text: str, locked_spans: Iterable[tuple[int, int]] = ()
) -> tuple[ProtectedSpan, ...]:
    spans = [
        ProtectedSpan(m.start(), m.end(), kind, m.group())
        for kind, pattern in PATTERNS
        for m in re.finditer(pattern, text, re.MULTILINE)
    ]
    for start, end in locked_spans:
        if not 0 <= start < end <= len(text):
            raise ValueError("Locked span is outside the submitted text")
        spans.append(ProtectedSpan(start, end, "locked", text[start:end]))
    return tuple(sorted(spans, key=lambda span: (span.start, span.end)))


class ProtectionIndex:
    """Merge overlapping ranges once; check edits in logarithmic time."""

    def __init__(self, spans: Iterable[ProtectedSpan]):
        ranges: list[tuple[int, int]] = []
        for span in sorted(spans, key=lambda item: item.start):
            if ranges and span.start <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], span.end))
            else:
                ranges.append((span.start, span.end))
        self.starts = [start for start, _ in ranges]
        self.ends = [end for _, end in ranges]

    def overlaps(self, start: int, end: int) -> bool:
        index = bisect_left(self.starts, end) - 1
        return index >= 0 and self.ends[index] > start

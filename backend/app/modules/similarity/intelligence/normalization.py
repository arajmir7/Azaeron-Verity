"""Deterministic, versioned text normalization for retrieval."""

from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import re
import unicodedata
from typing import Iterable

NORMALIZATION_VERSION = "unicode-casefold-whitespace-v1"
_TOKEN_RE = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)?", re.UNICODE)


@dataclass(frozen=True)
class NormalizedChunk:
    text: str
    normalized_text: str
    start_char: int
    end_char: int
    chunk_index: int
    tokens: tuple[str, ...]
    ngrams: tuple[str, ...]


def normalize_text(text: str) -> str:
    """Normalize only for comparison; never replace the stored source text."""

    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(normalize_text(text)))


def word_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Offsets in stored text, independent of normalization length."""
    return tuple((match.start(), match.end()) for match in _TOKEN_RE.finditer(text))


def token_ngrams(tokens: Iterable[str], n: int = 3) -> tuple[str, ...]:
    values = tuple(tokens)
    if len(values) < n:
        return ()
    return tuple(
        " ".join(values[index : index + n]) for index in range(len(values) - n + 1)
    )


def chunk_text(text: str, *, chunk_size: int = 500) -> tuple[NormalizedChunk, ...]:
    """Overlapping windows limit boundary losses and retain original offsets."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    chunks: list[NormalizedChunk] = []
    spans = word_spans(text)
    starts, ends = [a for a, _ in spans], [b for _, b in spans]
    step = max(1, chunk_size - min(100, chunk_size // 5))
    for requested_start in range(0, len(text), step):
        first = bisect_left(starts, requested_start)
        last = bisect_right(ends, requested_start + chunk_size) - 1
        if first >= len(spans) or last < first:
            continue
        start = 0 if requested_start == 0 else starts[first]
        end = len(text) if requested_start + chunk_size >= len(text) else ends[last]
        raw = text[start:end]
        normalized = normalize_text(raw)
        tokens = tokenize(raw)
        chunks.append(
            NormalizedChunk(
                text=raw,
                normalized_text=normalized,
                start_char=start,
                end_char=end,
                chunk_index=len(chunks),
                tokens=tokens,
                ngrams=token_ngrams(tokens),
            )
        )
    return tuple(chunks)

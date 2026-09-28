"""Similarity-specific windows over the frozen document structure, never reparse."""

from dataclasses import dataclass
import hashlib
from app.modules.similarity.intelligence.normalization import (
    NormalizedChunk,
    chunk_text,
)

INDEX_VERSION = "hybrid-structured-index-v2"
CHUNK_VERSION = "structured-windows-v1"


@dataclass(frozen=True)
class StructuredChunk(NormalizedChunk):
    structure: dict


def structured_chunks(text: str, structure: dict | None) -> tuple[StructuredChunk, ...]:
    # Paragraphs are the authoritative boundary; overlapping windows only split
    # long paragraphs. Include headings as separately addressable chunks.
    blocks = sorted(
        (structure or {}).get("paragraphs", []) + (structure or {}).get("headings", []),
        key=lambda b: b["start"],
    )
    if not blocks:
        blocks = [{"start": 0, "end": len(text), "id": None}]
    result: list[StructuredChunk] = []
    for block in blocks:
        a, b = block["start"], block["end"]
        for window in chunk_text(text[a:b], chunk_size=700):
            start, end = a + window.start_char, a + window.end_char
            result.append(
                StructuredChunk(
                    text=window.text,
                    normalized_text=window.normalized_text,
                    start_char=start,
                    end_char=end,
                    chunk_index=len(result),
                    tokens=window.tokens,
                    ngrams=window.ngrams,
                    structure={
                        "block_id": block.get("id"),
                        "section_ids": block.get("section_ids", []),
                        "page_numbers": block.get("page_numbers", []),
                        "kind": block.get("kind", "legacy_window"),
                        "parser_version": (structure or {}).get("parser_version"),
                        "structure_fingerprint": (structure or {}).get("fingerprint"),
                        "sentences": [
                            {
                                "id": s["id"],
                                "start": max(start, s["start"]) - start,
                                "end": min(end, s["end"]) - start,
                            }
                            for s in (structure or {}).get("sentences", [])
                            if s["start"] < end and start < s["end"]
                        ],
                    },
                )
            )
    return tuple(result)


def fingerprint_bands(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """16 deterministic MinHash values, eight bands of two, over token triples."""
    shingles = {" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)}
    if not shingles:
        return ()
    values = [
        min(
            hashlib.blake2b(f"{seed}:{s}".encode(), digest_size=8).hexdigest()
            for s in shingles
        )
        for seed in range(16)
    ]
    return tuple(f"{i//2}:{values[i]}:{values[i+1]}" for i in range(0, 16, 2))

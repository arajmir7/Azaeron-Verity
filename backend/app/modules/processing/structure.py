"""Versioned document structure in one immutable Unicode coordinate system.

No statistical model participates in normalization or boundary identification.
Extraction coordinates describe extracted source text, never invented byte/PDF
glyph offsets. Physical page/bounding boxes are recorded only by PDF extraction.
"""

from dataclasses import dataclass, field
from bisect import bisect_right
import hashlib
import json
import re
import uuid
from typing import Any

PARSER_VERSION = "document-structure-v1"
SCHEMA_VERSION = "normalized-document-v1"
REFERENCE_HEADER = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:references|bibliography|works cited)[ \t]*:?[ \t]*$",
    re.I | re.M,
)
CITATION_PATTERN = re.compile(
    r"\[(?P<numeric>\d+(?:\s*[,–-]\s*\d+)*)\]|\((?P<author>[^()\n]{1,160}?\b(?:19|20)\d{2}[a-z]?(?:\s*;\s*[^()\n]*)?)\)"
)
ABBREVIATIONS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "fig",
    "eq",
    "al",
    "vs",
    "e.g",
    "i.e",
    "no",
    "vol",
    "pp",
}


@dataclass
class ExtractedDocument:
    text: str
    format: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def normalize_source(raw: str) -> tuple[str, list[dict[str, int]]]:
    """Normalize line endings only; retain every other character and its offset.

    Compact segments map normalized character ranges to extracted source ranges.
    A normalized newline can map to two CRLF source characters.
    """
    parts, mapping = [], []
    source_cursor = target_cursor = 0
    for match in re.finditer(r"\r\n?", raw):
        if match.start() > source_cursor:
            value = raw[source_cursor : match.start()]
            parts.append(value)
            mapping.append(
                {
                    "start": target_cursor,
                    "end": target_cursor + len(value),
                    "source_start": source_cursor,
                    "source_end": match.start(),
                }
            )
            target_cursor += len(value)
        parts.append("\n")
        mapping.append(
            {
                "start": target_cursor,
                "end": target_cursor + 1,
                "source_start": match.start(),
                "source_end": match.end(),
            }
        )
        target_cursor += 1
        source_cursor = match.end()
    if source_cursor < len(raw):
        parts.append(raw[source_cursor:])
        mapping.append(
            {
                "start": target_cursor,
                "end": target_cursor + len(raw) - source_cursor,
                "source_start": source_cursor,
                "source_end": len(raw),
            }
        )
    return "".join(parts), mapping


def sentence_spans(
    text: str, start: int = 0, end: int | None = None
) -> list[tuple[int, int]]:
    """Conservative deterministic boundaries, retaining punctuation and quotes."""
    end = len(text) if end is None else end
    result = []
    cursor = start
    for match in re.finditer(r"[.!?]+[”’\"\']*(?=\s|$)|\n[ \t]*\n|\f", text[start:end]):
        boundary = start + match.end()
        punctuation = match.group().startswith((".", "!", "?"))
        before = text[cursor : start + match.start()]
        token = re.search(r"([\w.]+)$", before)
        if match.group().startswith(".") and token:
            word = token.group(1)
            if word.casefold() in ABBREVIATIONS or (len(word) == 1 and word.isupper()):
                continue
        stop = boundary if punctuation else start + match.start()
        a, b = trimmed_span(text, cursor, stop)
        if a < b:
            result.append((a, b))
        cursor = boundary
    a, b = trimmed_span(text, cursor, end)
    if a < b:
        result.append((a, b))
    return result


def trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def build_structure(
    extracted: ExtractedDocument,
    organization_id: str,
    document_id: str,
    version_id: str,
    content_hash: str,
    *,
    parser_version: str = PARSER_VERSION,
) -> tuple[str, dict]:
    text, source_map = normalize_source(extracted.text)
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    identity = f"{organization_id}:{document_id}:{version_id}:{parser_version}:{SCHEMA_VERSION}"
    normalized_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{identity}:{text_hash}"))
    source_starts = [item["source_start"] for item in source_map]
    target_starts = [item["start"] for item in source_map]

    def normalize_offset(offset: int) -> int:
        if offset == len(extracted.text):
            return len(text)
        if not source_map:
            return 0
        item = source_map[max(0, bisect_right(source_starts, offset) - 1)]
        return item["start"] + min(
            offset - item["source_start"], item["end"] - item["start"]
        )

    def source_offset(offset: int, *, end: bool = False) -> int:
        if offset == len(text):
            return len(extracted.text)
        if not source_map:
            return 0
        item = source_map[max(0, bisect_right(target_starts, offset) - 1)]
        return item["source_start"] + offset - item["start"]

    pages: list[dict[str, Any]] = []
    raw_pages = extracted.pages
    if not raw_pages and "\f" in extracted.text:
        boundaries = [0] + [m.end() for m in re.finditer("\f", extracted.text)]
        raw_pages = [
            {
                "start": a,
                "end": (
                    boundaries[i + 1] - 1
                    if i + 1 < len(boundaries)
                    else len(extracted.text)
                ),
                "page": i + 1,
                "basis": "EXPLICIT_PAGE_BREAK",
            }
            for i, a in enumerate(boundaries)
        ]

    def element(kind: str, start: int, end: int, salt: str = "", **extra) -> dict:
        span_text = text[start:end]
        element_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{identity}:{kind}:{start}:{end}:{salt}:{hashlib.sha256(span_text.encode()).hexdigest()}",
            )
        )
        return {
            "id": element_id,
            "kind": kind,
            "start": start,
            "end": end,
            "text": span_text,
            "source_start": source_offset(start),
            "source_end": source_offset(end, end=True),
            "page_numbers": [
                p["page"] for p in pages if p["start"] < end and start < p["end"]
            ],
            **extra,
        }

    for i, page in enumerate(raw_pages):
        pages.append(
            element(
                "page",
                normalize_offset(page["start"]),
                normalize_offset(page["end"]),
                str(i),
                **{k: v for k, v in page.items() if k not in ("start", "end")},
            )
        )
    headings, paragraphs, tables = [], [], []
    blocks = extracted.blocks or [
        {"start": m.start(), "end": m.end(), "kind": "paragraph"}
        for m in re.finditer(r"[^\n\f]+(?:\n(?![ \t]*\n)[^\n\f]+)*", extracted.text)
    ]
    for i, block in enumerate(blocks):
        a, b = trimmed_span(
            text, normalize_offset(block["start"]), normalize_offset(block["end"])
        )
        if a >= b:
            continue
        # Text/PDF may contain a standalone heading within a larger block.
        boundaries = [a, b]
        for line in re.finditer(r"[^\n\f]+", text[a:b]):
            raw = line.group().strip()
            if (
                re.match(r"^#{1,6}\s+\S", raw)
                or REFERENCE_HEADER.fullmatch(raw)
                or raw.casefold()
                in {
                    "abstract",
                    "introduction",
                    "methods",
                    "methodology",
                    "results",
                    "discussion",
                    "conclusion",
                    "conclusions",
                }
            ):
                boundaries.extend([a + line.start(), a + line.end()])
        boundaries = sorted(set(boundaries))
        for j, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
            left, right = trimmed_span(text, left, right)
            if left >= right:
                continue
            raw = text[left:right]
            heading = block.get("heading_level") or (
                len(raw) - len(raw.lstrip("#"))
                if re.match(r"^#{1,6}\s+", raw)
                else None
            )
            if (
                heading
                or REFERENCE_HEADER.fullmatch(raw)
                or raw.casefold()
                in {
                    "abstract",
                    "introduction",
                    "methods",
                    "methodology",
                    "results",
                    "discussion",
                    "conclusion",
                    "conclusions",
                }
            ):
                headings.append(
                    element(
                        "heading",
                        left,
                        right,
                        f"{i}:{j}",
                        level=heading or 1,
                        source_path=block.get("source_path"),
                        recognition=(
                            "STYLE" if block.get("heading_level") else "TEXT_RULE"
                        ),
                    )
                )
            else:
                paragraphs.append(
                    element(
                        "paragraph",
                        left,
                        right,
                        f"{i}:{j}",
                        source_path=block.get("source_path"),
                    )
                )
    headings.sort(key=lambda item: item["start"])
    sections = []
    for i, heading in enumerate(headings):
        end = next(
            (h["start"] for h in headings[i + 1 :] if h["level"] <= heading["level"]),
            len(text),
        )
        sections.append(
            element(
                "section",
                heading["start"],
                end,
                heading["id"],
                heading_id=heading["id"],
                level=heading["level"],
            )
        )
    sentences = []
    for paragraph in paragraphs:
        paragraph["section_ids"] = [
            s["id"] for s in sections if s["start"] <= paragraph["start"] < s["end"]
        ]
        for a, b in sentence_spans(text, paragraph["start"], paragraph["end"]):
            sentences.append(
                element("sentence", a, b, paragraph["id"], paragraph_id=paragraph["id"])
            )
    for i, table in enumerate(extracted.tables):
        cells = []
        for j, cell in enumerate(table.get("cells", [])):
            if cell.get("start") is not None and cell.get("end") is not None:
                mapped = element(
                    "table_cell",
                    normalize_offset(cell["start"]),
                    normalize_offset(cell["end"]),
                    f"{i}:{j}",
                    **{
                        k: v
                        for k, v in cell.items()
                        if k not in ("start", "end", "text")
                    },
                )
            else:
                mapped = {
                    **cell,
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL, f"{identity}:unmapped-cell:{i}:{j}"
                        )
                    ),
                    "mapping_state": "UNAVAILABLE",
                }
            cells.append(mapped)
        tables.append(
            element(
                "table",
                normalize_offset(table["start"]),
                normalize_offset(table["end"]),
                str(i),
                cells=cells,
                **{
                    k: v for k, v in table.items() if k not in ("start", "end", "cells")
                },
            )
        )
    header = REFERENCE_HEADER.search(text)
    body_end = header.start() if header else len(text)
    references = []
    if header:
        for i, line in enumerate(re.finditer(r"[^\n\f]+", text[header.end() :])):
            a, b = trimmed_span(
                text, header.end() + line.start(), header.end() + line.end()
            )
            if a < b:
                references.append(
                    element("reference", a, b, str(i), recognition="BIBLIOGRAPHY_LINE")
                )
    citations = [
        element(
            "citation",
            m.start(),
            m.end(),
            str(i),
            key=(m.group("numeric") or m.group("author")).strip(),
            citation_type="numeric" if m.group("numeric") else "author_year",
            sentence_id=next(
                (
                    s["id"]
                    for s in sentences
                    if s["start"] <= m.start() and m.end() <= s["end"]
                ),
                None,
            ),
        )
        for i, m in enumerate(CITATION_PATTERN.finditer(text[:body_end]))
    ]
    locations = [
        {
            **item,
            "start": normalize_offset(item["start"]),
            "end": normalize_offset(item["end"]),
        }
        for item in extracted.locations
    ]
    structure = {
        "id": normalized_id,
        "schema_version": SCHEMA_VERSION,
        "parser_version": parser_version,
        "parser_dependencies": extracted.dependencies,
        "organization_id": organization_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "source_content_hash": content_hash,
        "normalized_content_hash": text_hash,
        "coordinate_system": "UNICODE_CODE_POINT_ZERO_BASED_END_EXCLUSIVE",
        "source_basis": "EXTRACTED_SOURCE_TEXT",
        "source_format": extracted.format,
        "page_mapping": (
            "PHYSICAL"
            if extracted.pages
            else "EXPLICIT_BREAKS_ONLY" if pages else "UNAVAILABLE"
        ),
        "pages": pages,
        "headings": headings,
        "sections": sections,
        "paragraphs": paragraphs,
        "sentences": sentences,
        "tables": tables,
        "references": references,
        "citations": citations,
        "body_end": body_end,
        "source_map": source_map,
        "source_locations": locations,
        "limitations": extracted.limitations
        + [
            "Text heading, sentence, reference and citation rules are deterministic heuristics; unsupported structures remain unclassified."
        ],
    }
    structure["fingerprint"] = digest(structure)
    return text, structure

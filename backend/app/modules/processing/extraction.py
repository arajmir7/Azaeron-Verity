"""Format adapters preserving extraction order and available source locations."""

import io
import re
import zipfile
from importlib.metadata import version as package_version
from typing import Any

from app.core.config import settings
from app.modules.processing.structure import ExtractedDocument


def extract_document(content: bytes, extension: str) -> ExtractedDocument:
    try:
        result = _extract_document(content, extension)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Could not extract text from document") from exc
    if len(result.text) > settings.MAX_DOCUMENT_TEXT_CHARS:
        raise ValueError(
            "Extracted document text exceeds the configured processing limit"
        )
    if not result.text.strip():
        raise ValueError("Could not extract text from document")
    return result


def _extract_document(content: bytes, extension: str) -> ExtractedDocument:
    extension = extension.lower()
    if extension in ("txt", "md"):
        text = content.decode("utf-8", errors="replace")
        return ExtractedDocument(
            text,
            extension,
            limitations=[
                "Plain text has no physical page or table geometry. Form-feed characters indicate explicit page breaks.",
                *(
                    [
                        "Invalid UTF-8 bytes were replaced; character offsets refer to decoded extracted text."
                    ]
                    if "\ufffd" in text
                    else []
                ),
            ],
        )
    if extension == "pdf":
        return extract_pdf(content)
    if extension == "docx":
        return extract_docx(content)
    if extension == "html":
        return extract_html(content)
    raise ValueError("Unsupported document format")


def extract_html(content: bytes) -> ExtractedDocument:
    from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, Tag

    soup = BeautifulSoup(content, "html.parser")
    for hidden in soup.find_all(["script", "style", "head", "template"]):
        hidden.decompose()
    text = ""
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []

    def append_block(value: str, path: str, heading: int | None = None):
        nonlocal text
        if not value.strip():
            return
        start = len(text)
        text += value + "\n\n"
        blocks.append(
            {
                "start": start,
                "end": start + len(value),
                "source_path": path,
                "heading_level": heading,
            }
        )

    def visit(node, path: str):
        nonlocal text
        if isinstance(node, (Comment, Doctype)):
            return
        if isinstance(node, NavigableString):
            append_block(str(node).strip(), path)
            return
        if not isinstance(node, Tag):
            return
        if node.name == "table":
            start, cells = len(text), []
            rows = [
                row
                for row in node.find_all("tr")
                if isinstance(row, Tag) and row.find_parent("table") is node
            ]
            for row_index, row in enumerate(rows):
                row_cells = [
                    cell
                    for cell in row.find_all(["td", "th"], recursive=False)
                    if isinstance(cell, Tag)
                ]
                for column, cell in enumerate(row_cells):
                    value = cell.get_text(separator=" ", strip=True)
                    cell_start = len(text)
                    text += value
                    location = {
                        "start": cell_start,
                        "end": len(text),
                        "row": row_index,
                        "column": column,
                        "rowspan": cell.get("rowspan", "1"),
                        "colspan": cell.get("colspan", "1"),
                        "source_path": f"{path}:row:{row_index}:cell:{column}",
                    }
                    cells.append(location)
                    blocks.append({**location, "kind": "table_cell"})
                    text += "\t" if column < len(row_cells) - 1 else "\n"
            tables.append(
                {"start": start, "end": len(text), "cells": cells, "source_path": path}
            )
            text += "\n"
        elif node.name in ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"):
            append_block(
                node.get_text(separator=" ", strip=True),
                path,
                int(node.name[1]) if re.fullmatch(r"h[1-6]", node.name) else None,
            )
        else:
            for index, child in enumerate(node.children):
                visit(child, f"{path}:{index}")

    visit(soup.body or soup, "html:body")
    return ExtractedDocument(
        text,
        "html",
        blocks=blocks,
        tables=tables,
        dependencies={"beautifulsoup4": package_version("beautifulsoup4")},
        limitations=[
            "HTML pagination and geometry are unavailable; extracted DOM text order is preserved.",
            "Table cells retain declared row/column spans; nested table text is flattened within its parent cell.",
        ],
    )


def extract_docx(content: bytes) -> ExtractedDocument:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        if len(members) > 10_000:
            raise ValueError("DOCX contains too many archive members")
        if (
            sum(member.file_size for member in members)
            > settings.MAX_DOCX_UNCOMPRESSED_MB * 1024 * 1024
        ):
            raise ValueError("DOCX exceeds the configured uncompressed size limit")
        if any(
            member.filename.startswith(("/", "\\"))
            or ".." in member.filename.replace("\\", "/").split("/")
            or member.filename.lower().endswith("vbaproject.bin")
            for member in members
        ):
            raise ValueError("DOCX contains an unsafe archive member")
    from docx import Document
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    doc = Document(io.BytesIO(content))
    text, blocks, tables = "", [], []

    def paragraph_text(paragraph) -> str:
        parts = []
        for node in paragraph._p.iter():
            if node.tag == qn("w:t"):
                parts.append(node.text or "")
            elif node.tag == qn("w:tab"):
                parts.append("\t")
            elif node.tag in (qn("w:br"), qn("w:cr")):
                parts.append("\f" if node.get(qn("w:type")) == "page" else "\n")
        return "".join(parts)

    for i, node in enumerate(doc.element.body):
        if node.tag == qn("w:p"):
            paragraph = Paragraph(node, doc)
            value = paragraph_text(paragraph)
            start = len(text)
            text += value + "\n\n"
            style = paragraph.style.name if paragraph.style else ""
            heading = re.match(r"Heading\s+(\d+)", style, re.I)
            blocks.append(
                {
                    "start": start,
                    "end": start + len(value),
                    "source_path": f"docx:body:{i}",
                    "heading_level": int(heading.group(1)) if heading else None,
                }
            )
        elif node.tag == qn("w:tbl"):
            table = Table(node, doc)
            start, cells = len(text), []
            for row_index, row in enumerate(table.rows):
                for column_index, cell in enumerate(row.cells):
                    value = "\n".join(paragraph_text(p) for p in cell.paragraphs)
                    cell_start = len(text)
                    text += value
                    location = {
                        "start": cell_start,
                        "end": len(text),
                        "row": row_index,
                        "column": column_index,
                        "source_path": f"docx:body:{i}:row:{row_index}:cell:{column_index}",
                    }
                    cells.append(location)
                    blocks.append({**location, "kind": "table_cell"})
                    text += "\t" if column_index < len(row.cells) - 1 else "\n"
            tables.append(
                {
                    "start": start,
                    "end": len(text),
                    "cells": cells,
                    "source_path": f"docx:body:{i}",
                }
            )
            text += "\n"
    return ExtractedDocument(
        text,
        "docx",
        blocks=blocks,
        tables=tables,
        dependencies={"python-docx": package_version("python-docx")},
        limitations=[
            "DOCX physical pagination is unavailable without a layout engine; only explicit page breaks are mapped.",
            "Body paragraphs and table cells retain XML order. Headers, footers, floating text boxes and tracked-change layout are not extracted.",
        ],
    )


def extract_pdf(content: bytes) -> ExtractedDocument:
    import pdfplumber

    text, pages, tables, locations = "", [], [], []
    limitations = [
        "PDF reading order follows the recorded extractor; scanned images have no text without OCR.",
        "PDF word bounding boxes are provided only for unambiguous exact strings in extracted page text.",
    ]
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) > settings.MAX_DOCUMENT_PAGES:
            raise ValueError("PDF exceeds the configured page limit")
        for number, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            start = len(text)
            text += page_text
            pages.append(
                {
                    "start": start,
                    "end": len(text),
                    "page": number,
                    "width": page.width,
                    "height": page.height,
                    "basis": "PDF_PHYSICAL_PAGE",
                }
            )
            cursor = 0
            for word in page.extract_words(x_tolerance=3, y_tolerance=3):
                offset = page_text.find(word["text"], cursor)
                if offset < 0 or page_text.count(word["text"]) != 1:
                    continue
                cursor = offset + len(word["text"])
                locations.append(
                    {
                        "start": start + offset,
                        "end": start + cursor,
                        "page": number,
                        "bbox": [word["x0"], word["top"], word["x1"], word["bottom"]],
                        "basis": "PDF_WORD",
                    }
                )
            for index, table in enumerate(page.find_tables()):
                cells: list[dict[str, Any]] = []
                for row_index, row in enumerate(table.extract()):
                    for column_index, value in enumerate(row):
                        value = value or ""
                        # Repeated/line-wrapped cell strings cannot be located unambiguously.
                        offset = (
                            page_text.find(value)
                            if value and page_text.count(value) == 1
                            else -1
                        )
                        cells.append(
                            {
                                "start": start + offset if offset >= 0 else None,
                                "end": (
                                    start + offset + len(value) if offset >= 0 else None
                                ),
                                "text": value,
                                "row": row_index,
                                "column": column_index,
                                "page": number,
                            }
                        )
                mapped = [cell for cell in cells if cell["start"] is not None]
                tables.append(
                    {
                        "start": min((c["start"] for c in mapped), default=start),
                        "end": max((c["end"] for c in mapped), default=start),
                        "cells": cells,
                        "page": number,
                        "bbox": list(table.bbox),
                        "source_path": f"pdf:page:{number}:table:{index}",
                        "mapping_state": (
                            "PARTIAL" if len(mapped) < len(cells) else "EXACT"
                        ),
                    }
                )
            text += "\f" if number < len(pdf.pages) else ""
    return ExtractedDocument(
        text,
        "pdf",
        pages=pages,
        tables=tables,
        locations=locations,
        dependencies={"pdfplumber": package_version("pdfplumber")},
        limitations=limitations,
    )

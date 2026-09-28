"""Immutable document parsing and authoritative structural analysis input."""

import hashlib
import re
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.modules.documents.models import Document
from app.modules.documents.target import AnalysisTarget
from app.modules.processing.extraction import extract_document
from app.modules.processing.models import ProcessedDocument
from app.modules.processing.structure import (
    PARSER_VERSION,
    build_structure,
    sentence_spans,
)

logger = get_logger(__name__)
PIPELINE_VERSION = "document-processing-v4"


class DocumentProcessingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_document(
        self,
        document: Document,
        content: bytes,
        document_version_id: Optional[str] = None,
    ) -> ProcessedDocument:
        if not document_version_id:
            raise ValueError(
                "Document processing requires an immutable document version"
            )
        target = await AnalysisTarget.resolve(
            self.db,
            str(document.organization_id),
            str(document.id),
            document_version_id,
            lock=True,
        )
        if hashlib.sha256(content).hexdigest() != target.version.sha256_fingerprint:
            raise ValueError(
                "Document bytes do not match the immutable version fingerprint"
            )
        existing = (
            await self.db.execute(
                select(ProcessedDocument).where(
                    ProcessedDocument.organization_id == target.organization_id,
                    ProcessedDocument.document_id == str(document.id),
                    ProcessedDocument.document_version_id == document_version_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # First completed parse is authoritative, including after parser upgrades.
            return existing
        extension = target.version.storage_path.rsplit(".", 1)[-1].lower()
        if extension not in ("txt", "md", "pdf", "docx", "html"):
            extension = document.extension.lower()
        extracted = extract_document(content, extension)
        if not extracted.text.strip():
            raise ValueError("Could not extract text from document")
        if len(extracted.text) > settings.MAX_DOCUMENT_TEXT_CHARS:
            raise ValueError(
                "Extracted document text exceeds the configured processing limit"
            )
        cleaned, structure = build_structure(
            extracted,
            target.organization_id,
            str(document.id),
            document_version_id,
            target.version.sha256_fingerprint,
            parser_version=PARSER_VERSION,
        )
        words = re.findall(r"[^\W_]+", cleaned, re.UNICODE)
        sentences, paragraphs = structure["sentences"], structure["paragraphs"]
        try:
            import textstat

            flesch, fk_grade = textstat.flesch_reading_ease(
                cleaned
            ), textstat.flesch_kincaid_grade(cleaned)
        except Exception:
            flesch, fk_grade = None, None
        processed = ProcessedDocument(
            id=structure["id"],
            document_id=str(document.id),
            organization_id=target.organization_id,
            document_version_id=document_version_id,
            pipeline_version=PIPELINE_VERSION,
            parser_version=PARSER_VERSION,
            normalized_content_hash=structure["normalized_content_hash"],
            structure_fingerprint=structure["fingerprint"],
            structure_json=structure,
            raw_text=extracted.text,
            cleaned_text=cleaned,
            paragraphs=[{"index": i, **item} for i, item in enumerate(paragraphs)],
            sentences=[{"index": i, **item} for i, item in enumerate(sentences)],
            sections=structure["sections"],
            word_count=len(words),
            sentence_count=len(sentences),
            paragraph_count=len(paragraphs),
            avg_sentence_length=len(words) / len(sentences) if sentences else 0,
            avg_word_length=sum(map(len, words)) / len(words) if words else 0,
            readability_flesch=flesch,
            readability_flesch_kincaid=fk_grade,
            lexical_diversity=(
                len({w.casefold() for w in words}) / len(words) if words else 0
            ),
        )
        self.db.add(processed)
        await self.db.flush()
        logger.info(
            "document_processed",
            document_id=str(document.id),
            document_version_id=document_version_id,
            parser_version=PARSER_VERSION,
            word_count=len(words),
        )
        return processed

    def _extract_text(self, document: Document, content: bytes) -> str:
        return extract_document(content, document.extension).text

    def _clean_text(self, text: str) -> str:
        from app.modules.processing.structure import normalize_source

        return normalize_source(text)[0]

    def _segment_paragraphs(self, text: str) -> list[str]:
        return [p.strip() for p in re.split(r"\n[ \t]*\n|\f", text) if p.strip()]

    def _segment_sentences(self, text: str) -> list[str]:
        return [text[a:b] for a, b in sentence_spans(text)]

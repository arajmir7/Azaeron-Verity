"""Tenant/version-scoped similarity report, derived from a frozen evidence set."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import lazyload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentVersion
from app.modules.processing.models import ProcessedDocument
from app.modules.evidence.models import EvidenceNode
from app.modules.similarity.models import SimilarityAnalysis, SimilarityMatch
from app.modules.similarity.review import (
    ExclusionPolicy,
    INTERPRETATION,
    reduce_matches,
)
from app.modules.similarity.schemas import (
    SimilarityWorkflowResponse,
    SimilarityMatchPage,
    SimilaritySourcePage,
)
from app.modules.similarity.service import PIPELINE_VERSION


class SimilarityReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def context(self, document_id: str, org: str, version_id: str | None):
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(
                    Document.id == document_id,
                    Document.organization_id == org,
                )
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(404, "Document not found")
        query = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id
        )
        if version_id:
            query = query.where(DocumentVersion.id == version_id)
        version = (
            await self.db.execute(
                query.order_by(DocumentVersion.version_number.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(404, "Document version not found")
        processed = (
            await self.db.execute(
                select(ProcessedDocument).where(
                    ProcessedDocument.organization_id == org,
                    ProcessedDocument.document_id == document_id,
                    ProcessedDocument.document_version_id == version.id,
                )
            )
        ).scalar_one_or_none()
        if processed is None:
            raise HTTPException(
                409,
                "This version has not finished text extraction. Try again when processing completes.",
            )
        return document, version, processed

    async def build(
        self,
        document_id: str,
        org: str,
        version_id: str | None,
        policy: ExclusionPolicy,
        page: int = 1,
        page_size: int = 20,
        source_page: int = 1,
        source_page_size: int = 10,
        group: str | None = None,
        source_version_id: str | None = None,
        show_excluded: bool = True,
        match_id: str | None = None,
    ) -> SimilarityWorkflowResponse:
        _, version, processed = await self.context(document_id, org, version_id)
        analysis = (
            await self.db.execute(
                select(SimilarityAnalysis).where(
                    SimilarityAnalysis.organization_id == org,
                    SimilarityAnalysis.document_version_id == version.id,
                    SimilarityAnalysis.pipeline_version == PIPELINE_VERSION,
                )
            )
        ).scalar_one_or_none()
        text = processed.cleaned_text or ""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        if analysis and analysis.text_hash != text_hash:
            raise HTTPException(
                409,
                "Stored text no longer matches the analyzed fingerprint; evidence is withheld.",
            )
        rows = []
        if analysis:
            rows = list(
                (
                    await self.db.execute(
                        select(SimilarityMatch, EvidenceNode.node_id)
                        .outerjoin(
                            EvidenceNode,
                            (EvidenceNode.id == SimilarityMatch.evidence_id)
                            & (EvidenceNode.organization_id == org),
                        )
                        .where(
                            SimilarityMatch.organization_id == org,
                            SimilarityMatch.document_id == document_id,
                            SimilarityMatch.document_version_id == version.id,
                            SimilarityMatch.analysis_id == analysis.id,
                        )
                        .order_by(
                            SimilarityMatch.document_span_start, SimilarityMatch.id
                        )
                    )
                ).all()
            )
        matches = []
        for match, node_id in rows:
            meta = match.metadata_json or {}
            if (
                text[match.document_span_start : match.document_span_end]
                != match.matched_text
            ):
                raise HTTPException(
                    409,
                    "A match does not resolve to its recorded target text; evidence is withheld.",
                )
            matches.append(
                {
                    "id": str(match.id),
                    "review": meta.get("review"),
                    "evidence_id": match.evidence_id,
                    "evidence_node_id": node_id,
                    "document_version_id": str(version.id),
                    "source_document_id": str(match.source_document_id),
                    "source_document_version_id": str(match.source_document_version_id),
                    "match_type": match.match_type.value,
                    "document_span_start": match.document_span_start,
                    "document_span_end": match.document_span_end,
                    "source_span_start": match.source_span_start,
                    "source_span_end": match.source_span_end,
                    "matched_text": match.matched_text or "",
                    "source_text": match.source_text or "",
                    "context_before": match.context_before or "",
                    "context_after": match.context_after or "",
                    **{
                        key: meta.get(key, "")
                        for key in (
                            "source_title",
                            "source_category",
                            "corpus_state",
                            "source_content_hash",
                            "source_text_hash",
                            "target_content_hash",
                            "target_text_hash",
                            "retrieved_at",
                            "source_uploaded_at",
                            "source_context_before",
                            "source_context_after",
                        )
                    },
                }
            )
        reduced = reduce_matches(text, matches, policy)
        available = bool(analysis and analysis.corpus_version_count)
        if not available:
            reduced["summary"]["percentage"] = None
            for item in reduced["groups"]:
                item["percentage"] = None
        filtered = [
            m
            for m in reduced["matches"]
            if (not group or m["group"] == group)
            and (
                not source_version_id
                or m["source_document_version_id"] == source_version_id
            )
            and (show_excluded or not m["excluded"])
            and (not match_id or m["id"] == match_id)
        ]
        if match_id and not filtered:
            raise HTTPException(
                404, "Similarity match not found in this version and view"
            )
        limits = [
            "Only indexed private workspace documents were compared. Public metadata is not a full-text similarity corpus; no external scholarly corpus is connected.",
            "Contiguous lexical matches shorter than five words and semantic paraphrases are not tested. Bounded overlapping windows can miss longer or rearranged passages.",
            "Quote and citation-marker rules are experimental. A nearby marker is not verified attribution to the matched source; block formatting and citation styles may be missed.",
            "Sources and match groups can overlap; their percentages must not be added. Filters paginate the frozen result set; exclusions recalculate the whole summary.",
            "The recorded corpus is a snapshot. Sources added later are not silently incorporated into this version's completed analysis.",
        ]
        if processed.pipeline_version not in {
            "document-processing-v3",
            "document-processing-v4",
        }:
            limits.append(
                "This older processed text may have lost line boundaries. Bibliography and block-quotation recognition may be incomplete."
            )
        if analysis and analysis.truncated:
            limits.append(
                "A retrieval, verification, chunk or match bound was reached. Coverage is a lower bound from the recorded evidence, not an exhaustive corpus search."
            )
        return SimilarityWorkflowResponse(
            document_id=document_id,
            document_version_id=str(version.id),
            version_number=version.version_number,
            analysis_id=str(analysis.id) if analysis else None,
            analysis_state=(
                "NOT_ANALYZED"
                if not analysis
                else "BOUNDED" if analysis.truncated else "READY"
            ),
            analyzed_at=analysis.completed_at if analysis else None,
            pipeline_version=PIPELINE_VERSION,
            text_hash=text_hash,
            content_hash=version.sha256_fingerprint,
            corpus=[
                {
                    "category": "WORKSPACE_DOCUMENT",
                    "label": "Private workspace documents",
                    "state": analysis.corpus_state if analysis else "UNAVAILABLE",
                    "indexed_versions": (
                        analysis.corpus_version_count if analysis else 0
                    ),
                    "searched": bool(analysis),
                },
                {
                    "category": "PUBLIC_METADATA",
                    "label": "Public bibliographic metadata",
                    "state": "PUBLIC_METADATA",
                    "searched": False,
                    "note": "Metadata-only capability in citation analysis; no full text compared here.",
                },
                {
                    "category": "AUTHORIZED_CORPUS",
                    "label": "Authorized external corpus",
                    "state": "UNAVAILABLE",
                    "searched": False,
                    "note": "No authorized external full-text corpus is connected.",
                },
            ],
            summary=reduced["summary"],
            groups=reduced["groups"],
            flags=reduced["flags"],
            exclusions=policy.canonical(),
            exclusions_hash=policy.fingerprint(
                str(analysis.id) if analysis else f"{version.id}:{text_hash}"
            ),
            matches=SimilarityMatchPage.model_validate(
                {
                    "items": filtered[(page - 1) * page_size : page * page_size],
                    "total": len(filtered),
                    "page": page,
                    "page_size": page_size,
                }
            ),
            sources=SimilaritySourcePage.model_validate(
                {
                    "items": reduced["sources"][
                        (source_page - 1)
                        * source_page_size : source_page
                        * source_page_size
                    ],
                    "total": len(reduced["sources"]),
                    "page": source_page,
                    "page_size": source_page_size,
                }
            ),
            interpretation=INTERPRETATION,
            calculation="100 × unique included target words / eligible target words. Quotes, citation-containing sentences and bibliography exclusions remove words from both numerator and denominator. Source and small-match exclusions remove matches only. Words are Unicode word tokens, offsets are zero-based Python Unicode character offsets in stored processed text.",
            limitations=limits,
        )

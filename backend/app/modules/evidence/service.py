"""Canonical, tenant-scoped evidence graph services."""

from __future__ import annotations

from typing import Any, Sequence
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.core.logging import get_logger
from app.modules.authorship.models import AuthorshipSignal
from app.modules.citations.models import (
    Citation,
    CitationFinding,
    Claim,
    Reference,
    Source,
)
from app.modules.detection.models import DetectionResult, DetectionSegment
from app.modules.documents.models import Document, DocumentVersion
from app.modules.documents.target import AnalysisTarget
from app.modules.evidence.models import (
    CanonicalEvidenceNodeType,
    EvidenceEdge,
    EvidenceEdgeType,
    EvidenceNode,
    EvidenceNodeType,
)
from app.modules.evidence.report_models import IntegrityReport
from app.modules.provenance.models import ProvenanceEvent, ProvenanceReport
from app.modules.similarity.models import SimilarityMatch
from app.modules.evidence.schemas import (
    EvidenceGraphResponse,
    EvidenceNodeResponse,
    EvidenceEdgeResponse,
)

logger = get_logger(__name__)

GRAPH_SCHEMA_VERSION = "evidence-graph-v2"

_LEGACY_TO_CANONICAL = {
    EvidenceNodeType.DOCUMENT.value: CanonicalEvidenceNodeType.DOCUMENT.value,
    EvidenceNodeType.CLAIM.value: CanonicalEvidenceNodeType.CLAIM.value,
    EvidenceNodeType.CITATION.value: CanonicalEvidenceNodeType.CITATION.value,
    EvidenceNodeType.SOURCE.value: CanonicalEvidenceNodeType.SOURCE.value,
    EvidenceNodeType.SIMILARITY.value: CanonicalEvidenceNodeType.SIMILARITY_MATCH.value,
    EvidenceNodeType.AUTHORSHIP.value: CanonicalEvidenceNodeType.AUTHORSHIP_SIGNAL.value,
    EvidenceNodeType.PROVENANCE.value: CanonicalEvidenceNodeType.PROVENANCE_EVENT.value,
    EvidenceNodeType.DETECTION.value: CanonicalEvidenceNodeType.AI_SIGNAL.value,
    EvidenceNodeType.REVISION.value: CanonicalEvidenceNodeType.DOCUMENT_VERSION.value,
}


class EvidenceService:
    """Persist and traverse evidence without cross-tenant or orphan edges."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._graph_state: dict[str, Any] | None = None

    async def _document(
        self, document_id: str, organization_id: str | None = None
    ) -> Document:
        if self._graph_state:
            document = self._graph_state["document"]
            if str(document.id) == document_id and (
                organization_id is None
                or str(document.organization_id) == organization_id
            ):
                return document
        query = (
            select(Document).options(lazyload("*")).where(Document.id == document_id)
        )
        if organization_id:
            query = query.where(Document.organization_id == organization_id)
        document = (await self.db.execute(query)).scalar_one_or_none()
        if not document:
            raise ValueError(f"Document {document_id} not found")
        return document

    async def _version(
        self, document_id: str, document_version_id: str | None
    ) -> DocumentVersion:
        if self._graph_state:
            version = self._graph_state["version"]
            if (
                str(version.document_id) == document_id
                and str(version.id) == document_version_id
            ):
                return version
        if document_version_id:
            version = (
                await self.db.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == document_version_id,
                        DocumentVersion.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()
        else:
            version = (
                await self.db.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == document_id)
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if not version:
            raise ValueError("Evidence requires an immutable document version")
        return version

    @staticmethod
    def _canonical_type(
        node_type: EvidenceNodeType,
        canonical_type: str | CanonicalEvidenceNodeType | None,
    ) -> str:
        if canonical_type:
            return (
                canonical_type.value
                if isinstance(canonical_type, CanonicalEvidenceNodeType)
                else str(canonical_type)
            )
        raw = (
            node_type.value
            if isinstance(node_type, EvidenceNodeType)
            else str(node_type)
        )
        return _LEGACY_TO_CANONICAL.get(raw, CanonicalEvidenceNodeType.FINDING.value)

    @staticmethod
    def _entity_type(canonical_type: str) -> str:
        return canonical_type.lower()

    async def add_node(
        self,
        document_id: str,
        node_type: EvidenceNodeType,
        title: str,
        description: str | None = None,
        span_start: int | None = None,
        span_end: int | None = None,
        span_text: str | None = None,
        confidence: float = 1.0,
        severity: str | None = None,
        metadata: dict[str, Any] | None = None,
        document_version_id: str | None = None,
        finding_type: str | None = None,
        source_id: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        pipeline_version: str | None = None,
        entity_id: str | None = None,
        entity_type: str | None = None,
        canonical_type: str | CanonicalEvidenceNodeType | None = None,
    ) -> EvidenceNode:
        if not description or not description.strip():
            raise ValueError("Evidence node requires a non-empty explanation")
        if not document_version_id:
            raise ValueError(
                "Evidence writes require an explicit immutable document version"
            )
        document = await self._document(document_id)
        version = await self._version(document_id, document_version_id)
        canonical = self._canonical_type(node_type, canonical_type)
        if (span_start is None) != (span_end is None):
            raise ValueError("Evidence span requires both span_start and span_end")
        if (
            span_start is not None
            and span_end is not None
            and (span_start < 0 or span_end < span_start)
        ):
            raise ValueError("Evidence span is invalid")
        if confidence < 0 or confidence > 1:
            raise ValueError("Evidence confidence must be between 0 and 1")
        resolved_entity_id = entity_id or source_id
        if not resolved_entity_id:
            if canonical == CanonicalEvidenceNodeType.DOCUMENT.value:
                resolved_entity_id = str(document.id)
            elif canonical == CanonicalEvidenceNodeType.DOCUMENT_VERSION.value:
                resolved_entity_id = str(version.id)
        if not resolved_entity_id:
            raise ValueError("Evidence node requires an entity identity")

        node_key = (canonical, str(resolved_entity_id))
        graph = self._graph_state
        cached_scope = graph is not None and str(graph["version"].id) == str(version.id)
        if cached_scope and graph is not None:
            existing = graph["nodes"].get(node_key)
        else:
            existing = (
                await self.db.execute(
                    select(EvidenceNode).where(
                        EvidenceNode.document_id == document_id,
                        EvidenceNode.document_version_id == str(version.id),
                        EvidenceNode.canonical_type == canonical,
                        EvidenceNode.entity_id == str(resolved_entity_id),
                    )
                )
            ).scalar_one_or_none()
        if existing:
            return existing

        node = EvidenceNode(
            document_id=document_id,
            organization_id=str(document.organization_id),
            document_version_id=str(version.id),
            finding_type=finding_type or canonical.lower(),
            source_id=source_id,
            model_id=model_id,
            model_version=model_version,
            pipeline_version=pipeline_version or GRAPH_SCHEMA_VERSION,
            node_type=node_type,
            node_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{document.organization_id}:{document_id}:{version.id}:{canonical}:{resolved_entity_id}",
                )
            ),
            canonical_type=canonical,
            entity_id=str(resolved_entity_id),
            entity_type=entity_type or self._entity_type(canonical),
            title=title,
            description=description,
            span_start=span_start,
            span_end=span_end,
            span_text=span_text,
            confidence=confidence,
            severity=severity,
            metadata_json=metadata or {},
        )
        self.db.add(node)
        await self.db.flush()
        if cached_scope and graph is not None:
            graph["nodes"][node_key] = node
            graph["by_id"][str(node.node_id)] = node
        else:
            await self.db.refresh(node)
        return node

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str | EvidenceEdgeType,
        weight: float = 1.0,
        description: str | None = None,
        organization_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceEdge:
        edge_value = (
            edge_type.value
            if isinstance(edge_type, EvidenceEdgeType)
            else str(edge_type)
        )
        if edge_value not in {item.value for item in EvidenceEdgeType}:
            raise ValueError(f"Unsupported evidence edge type: {edge_value}")
        graph = self._graph_state
        if graph and source_id in graph["by_id"] and target_id in graph["by_id"]:
            source, target = graph["by_id"][source_id], graph["by_id"][target_id]
        else:
            source = (
                await self.db.execute(
                    select(EvidenceNode).where(EvidenceNode.node_id == source_id)
                )
            ).scalar_one_or_none()
            target = (
                await self.db.execute(
                    select(EvidenceNode).where(EvidenceNode.node_id == target_id)
                )
            ).scalar_one_or_none()
        if not source or not target:
            raise ValueError("Evidence edges require two existing graph nodes")
        if str(source.organization_id) != str(target.organization_id):
            raise ValueError("Evidence edges cannot cross organizations")
        if (
            source.document_id != target.document_id
            or source.document_version_id != target.document_version_id
        ):
            raise ValueError("Evidence edges cannot cross analysis document versions")
        if organization_id and str(source.organization_id) != str(organization_id):
            raise ValueError("Evidence edge organization does not match its nodes")
        if weight < 0 or weight > 1:
            raise ValueError("Evidence edge weight must be between 0 and 1")
        edge_key = (source_id, target_id, edge_value)
        cached_scope = graph is not None and str(graph["version"].id) == str(
            source.document_version_id
        )
        if cached_scope and graph is not None:
            existing = graph["edges"].get(edge_key)
        else:
            existing = (
                await self.db.execute(
                    select(EvidenceEdge).where(
                        EvidenceEdge.source_node_id == source_id,
                        EvidenceEdge.target_node_id == target_id,
                        EvidenceEdge.edge_type == edge_value,
                    )
                )
            ).scalar_one_or_none()
        if existing:
            return existing
        edge = EvidenceEdge(
            organization_id=str(source.organization_id),
            source_node_id=source_id,
            document_id=str(source.document_id),
            document_version_id=str(source.document_version_id),
            target_node_id=target_id,
            edge_type=edge_value,
            weight=weight,
            description=description,
            metadata_json=metadata or {},
        )
        self.db.add(edge)
        await self.db.flush()
        if cached_scope and graph is not None:
            graph["edges"][edge_key] = edge
        return edge

    async def add_finding(
        self,
        *,
        document_id: str,
        document_version_id: str,
        title: str,
        explanation: str,
        finding_type: str,
        derived_from: Sequence[str],
        supported_by: Sequence[str] = (),
        confidence: float = 0.0,
        span_start: int | None = None,
        span_end: int | None = None,
        span_text: str | None = None,
        source_id: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        pipeline_version: str | None = None,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceNode:
        if not derived_from:
            raise ValueError(
                "A finding must be derived from at least one evidence node"
            )
        document = await self._document(document_id)
        node = await self.add_node(
            document_id=document_id,
            document_version_id=document_version_id,
            node_type=EvidenceNodeType.CLAIM,
            canonical_type=CanonicalEvidenceNodeType.FINDING,
            entity_id=entity_id or source_id,
            entity_type="finding",
            title=title,
            description=explanation,
            finding_type=finding_type,
            span_start=span_start,
            span_end=span_end,
            span_text=span_text,
            source_id=source_id,
            confidence=confidence,
            metadata=metadata,
            model_id=model_id,
            model_version=model_version,
            pipeline_version=pipeline_version,
        )
        for parent_id in dict.fromkeys(derived_from):
            await self.add_edge(
                parent_id,
                str(node.node_id),
                EvidenceEdgeType.GENERATED_FINDING,
                organization_id=str(document.organization_id),
            )
        for support_id in dict.fromkeys(supported_by):
            await self.add_edge(
                str(node.node_id),
                support_id,
                EvidenceEdgeType.SUPPORTED_BY,
                organization_id=str(document.organization_id),
            )
        return node

    async def materialize_document_graph(
        self,
        document_id: str,
        organization_id: str,
        document_version_id: str | None = None,
    ) -> EvidenceGraphResponse:
        # Only cache inside this invocation while holding the immutable target's
        # parent/version locks. Never carry ORM state across transactions/retries.
        target = await AnalysisTarget.resolve(
            self.db, organization_id, document_id, document_version_id, lock=True
        )
        version_id = str(target.version.id)
        nodes = (
            await self.db.scalars(
                select(EvidenceNode).where(
                    EvidenceNode.organization_id == organization_id,
                    EvidenceNode.document_id == document_id,
                    EvidenceNode.document_version_id == version_id,
                )
            )
        ).all()
        edges = (
            await self.db.scalars(
                select(EvidenceEdge).where(
                    EvidenceEdge.organization_id == organization_id,
                    EvidenceEdge.document_id == document_id,
                    EvidenceEdge.document_version_id == version_id,
                )
            )
        ).all()
        self._graph_state = {
            "document": target.document,
            "version": target.version,
            "nodes": {(n.canonical_type, str(n.entity_id)): n for n in nodes},
            "by_id": {str(n.node_id): n for n in nodes},
            "edges": {
                (e.source_node_id, e.target_node_id, e.edge_type): e for e in edges
            },
        }
        try:
            return await self._materialize_document_graph(
                document_id, organization_id, version_id
            )
        finally:
            self._graph_state = None

    async def _materialize_document_graph(
        self,
        document_id: str,
        organization_id: str,
        document_version_id: str | None = None,
    ) -> EvidenceGraphResponse:
        """Materialize canonical graph nodes/edges from real analysis records."""
        target = await AnalysisTarget.resolve(
            self.db, organization_id, document_id, document_version_id, lock=True
        )
        document, version = target.document, target.version
        version_id = str(version.id)
        document_node = await self.add_node(
            document_id=document_id,
            document_version_id=version_id,
            node_type=EvidenceNodeType.DOCUMENT,
            canonical_type=CanonicalEvidenceNodeType.DOCUMENT,
            entity_id=document_id,
            entity_type="document",
            finding_type="document",
            title=document.title or document.original_filename,
            description="Tenant-scoped document identity",
            confidence=1.0,
            source_id=document_id,
        )
        version_node = await self.add_node(
            document_id=document_id,
            document_version_id=version_id,
            node_type=EvidenceNodeType.REVISION,
            canonical_type=CanonicalEvidenceNodeType.DOCUMENT_VERSION,
            entity_id=version_id,
            entity_type="document_version",
            finding_type="document_version",
            title=f"Document version {version.version_number}",
            description=version.change_summary or "Immutable document version",
            confidence=1.0,
            source_id=version_id,
            metadata={
                "content_hash": version.content_hash,
                "lifecycle_state": version.lifecycle_state,
            },
        )
        await self.add_edge(
            str(document_node.node_id),
            str(version_node.node_id),
            EvidenceEdgeType.CONTAINS,
            organization_id=organization_id,
        )
        await self.add_edge(
            str(version_node.node_id),
            str(document_node.node_id),
            EvidenceEdgeType.VERSION_OF,
            organization_id=organization_id,
        )

        async def contains(node: EvidenceNode) -> EvidenceNode:
            await self.add_edge(
                str(version_node.node_id),
                str(node.node_id),
                EvidenceEdgeType.CONTAINS,
                organization_id=organization_id,
            )
            return node

        claims = (
            (
                await self.db.execute(
                    select(Claim).where(
                        Claim.document_id == document_id,
                        Claim.organization_id == organization_id,
                        Claim.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        claim_nodes: dict[str, EvidenceNode] = {}
        for claim in claims:
            claim_nodes[str(claim.id)] = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.CLAIM,
                    canonical_type=CanonicalEvidenceNodeType.CLAIM,
                    entity_id=str(claim.id),
                    entity_type="claim",
                    finding_type=claim.claim_type or "claim",
                    title="Claim",
                    description=claim.text,
                    span_start=claim.span_start,
                    span_end=claim.span_end,
                    span_text=claim.text,
                    confidence=claim.confidence,
                    source_id=str(claim.id),
                    model_version=claim.model_version,
                    pipeline_version=claim.pipeline_version,
                )
            )

        references = (
            (
                await self.db.execute(
                    select(Reference).where(
                        Reference.document_id == document_id,
                        Reference.organization_id == organization_id,
                        Reference.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        sources = (
            (
                await self.db.execute(
                    select(Source).where(
                        Source.organization_id == organization_id,
                        Source.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        source_nodes: dict[str, EvidenceNode] = {}
        for source in sources:
            source_nodes[str(source.id)] = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.SOURCE,
                    canonical_type=CanonicalEvidenceNodeType.SOURCE,
                    entity_id=str(source.id),
                    entity_type="source",
                    finding_type="source",
                    title=source.title or source.source_key,
                    description="Source metadata and retrieved evidence preserved without fabrication.",
                    confidence=1.0 if source.retrieval_status == "RETRIEVED" else 0.0,
                    source_id=str(source.id),
                    model_id="citation-intelligence",
                    model_version=source.model_version,
                    pipeline_version=source.pipeline_version,
                    metadata={
                        "source_key": source.source_key,
                        "retrieval_status": source.retrieval_status,
                        "doi": source.doi,
                        "url": source.url,
                    },
                )
            )

        citations = (
            (
                await self.db.execute(
                    select(Citation).where(
                        Citation.document_id == document_id,
                        Citation.organization_id == organization_id,
                        Citation.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        citation_nodes: dict[str, EvidenceNode] = {}
        for citation in citations:
            citation_node = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.CITATION,
                    canonical_type=CanonicalEvidenceNodeType.CITATION,
                    entity_id=str(citation.id),
                    entity_type="citation",
                    finding_type="citation",
                    title=f"Citation {citation.citation_key or citation.raw_text}",
                    description=citation.raw_text,
                    span_start=citation.span_start,
                    span_end=citation.span_end,
                    span_text=citation.raw_text,
                    confidence=1.0 if citation.reference_id else 0.0,
                    source_id=str(citation.id),
                    model_version=citation.model_version,
                    pipeline_version=citation.pipeline_version,
                )
            )
            citation_nodes[str(citation.id)] = citation_node
            if citation.claim_id and str(citation.claim_id) in claim_nodes:
                await self.add_edge(
                    str(claim_nodes[str(citation.claim_id)].node_id),
                    str(citation_node.node_id),
                    EvidenceEdgeType.CITES,
                    organization_id=organization_id,
                )
            if citation.source_id and str(citation.source_id) in source_nodes:
                await self.add_edge(
                    str(citation_node.node_id),
                    str(source_nodes[str(citation.source_id)].node_id),
                    EvidenceEdgeType.CITES,
                    organization_id=organization_id,
                )
        for reference in references:
            if reference.source_id and str(reference.source_id) in source_nodes:
                await self.add_edge(
                    str(version_node.node_id),
                    str(source_nodes[str(reference.source_id)].node_id),
                    EvidenceEdgeType.CITES,
                    organization_id=organization_id,
                )

        findings = (
            (
                await self.db.execute(
                    select(CitationFinding).where(
                        CitationFinding.document_id == document_id,
                        CitationFinding.organization_id == organization_id,
                        CitationFinding.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        claim_by_id = {str(item.id): item for item in claims}
        citation_by_id = {str(item.id): item for item in citations}
        for finding in findings:
            derived = [
                str(node.node_id)
                for node in (
                    claim_nodes.get(str(finding.claim_id)),
                    citation_nodes.get(str(finding.citation_id)),
                )
                if node
            ] or [str(version_node.node_id)]
            supported = (
                [str(source_nodes[str(finding.source_id)].node_id)]
                if finding.source_id and str(finding.source_id) in source_nodes
                else []
            )
            span_start = span_end = None
            span_text = None
            if finding.claim_id and str(finding.claim_id) in claim_by_id:
                claim = claim_by_id[str(finding.claim_id)]
                span_start, span_end, span_text = (
                    claim.span_start,
                    claim.span_end,
                    claim.text,
                )
            elif finding.citation_id and str(finding.citation_id) in citation_by_id:
                citation = citation_by_id[str(finding.citation_id)]
                span_start, span_end, span_text = (
                    citation.span_start,
                    citation.span_end,
                    citation.raw_text,
                )
            await self.add_finding(
                document_id=document_id,
                document_version_id=version_id,
                entity_id=str(finding.id),
                source_id=str(finding.id),
                title=f"Citation finding: {finding.finding_type}",
                explanation=finding.message,
                finding_type=finding.finding_type,
                derived_from=derived,
                supported_by=supported,
                confidence=finding.confidence,
                span_start=span_start,
                span_end=span_end,
                span_text=span_text,
                model_id="citation-intelligence",
                model_version=finding.model_version,
                pipeline_version=finding.pipeline_version,
                metadata={
                    "finding_id": str(finding.id),
                    "support_status": finding.support_status.value,
                    "evidence": finding.evidence_json or {},
                },
            )

        matches = (
            (
                await self.db.execute(
                    select(SimilarityMatch).where(
                        SimilarityMatch.document_id == document_id,
                        SimilarityMatch.organization_id == organization_id,
                        SimilarityMatch.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for match in matches:
            match_node = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.SIMILARITY,
                    canonical_type=CanonicalEvidenceNodeType.SIMILARITY_MATCH,
                    entity_id=str(match.id),
                    entity_type="similarity_match",
                    finding_type="similarity_match",
                    title=f"Verified {match.match_type.value} similarity",
                    description="Similarity is evidence of overlap, not a plagiarism determination.",
                    span_start=match.document_span_start,
                    span_end=match.document_span_end,
                    span_text=match.matched_text,
                    confidence=match.confidence,
                    source_id=str(match.id),
                    model_id="similarity-retrieval-pipeline",
                    model_version=match.model_version,
                    pipeline_version=match.pipeline_version,
                    metadata=match.metadata_json or {},
                )
            )
            source_node_ids: list[str] = []
            if match.source_document_id and match.source_document_version_id:
                source_document = (
                    await self.db.execute(
                        select(Document)
                        .options(lazyload("*"))
                        .where(
                            Document.id == match.source_document_id,
                            Document.organization_id == organization_id,
                        )
                    )
                ).scalar_one_or_none()
                if source_document:
                    source_query = select(DocumentVersion).where(
                        DocumentVersion.document_id == str(source_document.id)
                    )
                    if match.source_document_version_id:
                        source_query = source_query.where(
                            DocumentVersion.id == match.source_document_version_id
                        )
                    source_version = (
                        await self.db.execute(
                            source_query.order_by(
                                DocumentVersion.version_number.desc()
                            ).limit(1)
                        )
                    ).scalar_one_or_none()
                    if source_version:
                        source_doc_node = await self.add_node(
                            document_id=document_id,
                            document_version_id=version_id,
                            node_type=EvidenceNodeType.SOURCE,
                            canonical_type=CanonicalEvidenceNodeType.SOURCE,
                            entity_id=f"workspace-source:{source_version.id}",
                            entity_type="source_version",
                            finding_type="source_document",
                            title=source_document.title
                            or source_document.original_filename,
                            description="Tenant-local source document referenced by a verified similarity match.",
                            confidence=1.0,
                            source_id=str(source_document.id),
                            metadata={
                                "source_document_id": str(source_document.id),
                                "source_document_version_id": str(source_version.id),
                                "source_content_hash": source_version.content_hash,
                                "corpus_state": "PRIVATE_WORKSPACE",
                            },
                        )
                        source_node_ids.append(str(source_doc_node.node_id))
                        await self.add_edge(
                            str(match_node.node_id),
                            str(source_doc_node.node_id),
                            EvidenceEdgeType.SIMILAR_TO,
                            organization_id=organization_id,
                            metadata={
                                "source_span": [
                                    match.source_span_start,
                                    match.source_span_end,
                                ],
                                "match_type": match.match_type.value,
                            },
                        )
            await self.add_finding(
                document_id=document_id,
                document_version_id=version_id,
                entity_id=f"{match.id}:finding",
                source_id=str(match.id),
                title=f"Similarity finding: {match.match_type.value}",
                explanation="A bounded retrieval candidate passed the configured verification pipeline; similarity is not plagiarism.",
                finding_type="similarity_match",
                derived_from=[str(match_node.node_id)],
                supported_by=source_node_ids,
                confidence=match.confidence,
                span_start=match.document_span_start,
                span_end=match.document_span_end,
                span_text=match.matched_text,
                model_id="similarity-retrieval-pipeline",
                model_version=match.model_version,
                pipeline_version=match.pipeline_version,
                metadata=match.metadata_json or {},
            )

        detections = (
            (
                await self.db.execute(
                    select(DetectionResult)
                    .where(
                        DetectionResult.document_id == document_id,
                        DetectionResult.document_version_id == version_id,
                    )
                    .order_by(DetectionResult.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        for detection in detections:
            signal_node = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.DETECTION,
                    canonical_type=CanonicalEvidenceNodeType.AI_SIGNAL,
                    entity_id=str(detection.id),
                    entity_type="ai_signal",
                    finding_type="ai_signal",
                    title="AI-writing signal",
                    description=detection.explanation,
                    confidence=detection.confidence or 0.0,
                    source_id=str(detection.id),
                    model_id="ai-writing-ensemble",
                    model_version=detection.model_version,
                    pipeline_version=detection.pipeline_version,
                    metadata={
                        "verdict": detection.overall_verdict.value,
                        "abstained": detection.abstained,
                        "limitations": detection.limitations,
                    },
                )
            )
            await self.add_edge(
                str(version_node.node_id),
                str(signal_node.node_id),
                EvidenceEdgeType.HAS_SIGNAL,
                organization_id=organization_id,
                description="Document version has an AI-writing signal",
            )
            segments: list[DetectionSegment | None] = list(
                detection.segments or []
            ) or [None]
            for index, segment in enumerate(segments):
                await self.add_finding(
                    document_id=document_id,
                    document_version_id=version_id,
                    entity_id=f"{detection.id}:finding:{index}",
                    source_id=str(detection.id),
                    title="AI-writing signal finding",
                    explanation=detection.explanation
                    or "The AI-writing signal was recorded with its configured uncertainty state.",
                    finding_type="ai_signal",
                    derived_from=[str(signal_node.node_id)],
                    confidence=(
                        segment.confidence if segment else detection.confidence or 0.0
                    ),
                    span_start=segment.span_start if segment else None,
                    span_end=segment.span_end if segment else None,
                    span_text=segment.text if segment else None,
                    model_id="ai-writing-ensemble",
                    model_version=detection.model_version,
                    pipeline_version=detection.pipeline_version,
                    metadata={
                        "verdict": (
                            segment.verdict.value
                            if segment
                            else detection.overall_verdict.value
                        ),
                        "abstention_reason": detection.abstention_reason,
                        "segment_type": segment.segment_type if segment else "document",
                    },
                )

        authorship_signals = (
            (
                await self.db.execute(
                    select(AuthorshipSignal).where(
                        AuthorshipSignal.document_id == document_id,
                        AuthorshipSignal.organization_id == organization_id,
                        AuthorshipSignal.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for signal in authorship_signals:
            signal_node = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.AUTHORSHIP,
                    canonical_type=CanonicalEvidenceNodeType.AUTHORSHIP_SIGNAL,
                    entity_id=str(signal.id),
                    entity_type="authorship_signal",
                    finding_type="authorship_consistency",
                    title="Authorship consistency signal",
                    description=signal.explanation,
                    confidence=signal.confidence or 0.0,
                    source_id=str(signal.id),
                    model_id="authorship-consistency",
                    model_version=signal.model_version,
                    pipeline_version=signal.pipeline_version,
                    metadata={
                        "verdict": signal.verdict,
                        "baseline_quality": signal.baseline_quality,
                        "limitations": signal.limitations,
                    },
                )
            )
            await self.add_edge(
                str(version_node.node_id),
                str(signal_node.node_id),
                EvidenceEdgeType.HAS_SIGNAL,
                organization_id=organization_id,
                description="Document version has an authorship consistency signal",
            )
            await self.add_finding(
                document_id=document_id,
                document_version_id=version_id,
                entity_id=f"{signal.id}:finding",
                source_id=str(signal.id),
                title="Authorship consistency finding",
                explanation=signal.explanation
                or "Authorship consistency statistics were recorded.",
                finding_type="authorship_consistency",
                derived_from=[str(signal_node.node_id)],
                confidence=signal.confidence or 0.0,
                model_id="authorship-consistency",
                model_version=signal.model_version,
                pipeline_version=signal.pipeline_version,
                metadata={
                    "verdict": signal.verdict,
                    "baseline_quality": signal.baseline_quality,
                    "identity_claim_not_made": True,
                },
            )

        events = (
            (
                await self.db.execute(
                    select(ProvenanceEvent).where(
                        ProvenanceEvent.document_id == document_id,
                        ProvenanceEvent.organization_id == organization_id,
                        ProvenanceEvent.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for event in events:
            event_node = await self.add_node(
                document_id=document_id,
                document_version_id=version_id,
                node_type=EvidenceNodeType.PROVENANCE,
                canonical_type=CanonicalEvidenceNodeType.PROVENANCE_EVENT,
                entity_id=str(event.id),
                entity_type="provenance_event",
                finding_type="provenance_event",
                title=f"Provenance event: {event.event_type.value}",
                description=event.description,
                confidence=1.0,
                source_id=str(event.id),
                model_id="provenance-lineage",
                model_version=event.model_version,
                pipeline_version=event.pipeline_version,
                metadata=event.metadata_json or {},
            )
            await contains(event_node)

        integrity_report = (
            await self.db.execute(
                select(IntegrityReport).where(
                    IntegrityReport.document_id == document_id,
                    IntegrityReport.organization_id == organization_id,
                    IntegrityReport.document_version_id == version_id,
                )
            )
        ).scalar_one_or_none()
        if integrity_report:
            report_node = await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.REVISION,
                    canonical_type=CanonicalEvidenceNodeType.REPORT,
                    entity_id=str(integrity_report.id),
                    entity_type="report",
                    finding_type="integrity_report",
                    title="Integrity report",
                    description="Aggregated report over versioned evidence.",
                    confidence=1.0,
                    source_id=str(integrity_report.id),
                    model_id="integrity-report",
                    model_version=integrity_report.model_version,
                    pipeline_version=integrity_report.pipeline_version,
                    metadata=integrity_report.report_data or {},
                )
            )
            finding_nodes = (
                (
                    await self.db.execute(
                        select(EvidenceNode).where(
                            EvidenceNode.document_id == document_id,
                            EvidenceNode.document_version_id == version_id,
                            EvidenceNode.canonical_type
                            == CanonicalEvidenceNodeType.FINDING.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for finding_node in finding_nodes:
                await self.add_edge(
                    str(report_node.node_id),
                    str(finding_node.node_id),
                    EvidenceEdgeType.DERIVED_FROM,
                    organization_id=organization_id,
                )

        provenance_report = (
            await self.db.execute(
                select(ProvenanceReport).where(
                    ProvenanceReport.document_id == document_id,
                    ProvenanceReport.organization_id == organization_id,
                    ProvenanceReport.document_version_id == version_id,
                )
            )
        ).scalar_one_or_none()
        if provenance_report:
            await contains(
                await self.add_node(
                    document_id=document_id,
                    document_version_id=version_id,
                    node_type=EvidenceNodeType.REVISION,
                    canonical_type=CanonicalEvidenceNodeType.REPORT,
                    entity_id=str(provenance_report.id),
                    entity_type="report",
                    finding_type="provenance_report",
                    title="Provenance report",
                    description="Immutable report snapshot over the document provenance timeline.",
                    confidence=1.0,
                    source_id=str(provenance_report.id),
                    model_id="provenance-report",
                    model_version=provenance_report.model_version,
                    pipeline_version=provenance_report.pipeline_version,
                    metadata={"report_hash": provenance_report.report_hash},
                )
            )

        existing_nodes = (
            (
                await self.db.execute(
                    select(EvidenceNode).where(
                        EvidenceNode.document_id == document_id,
                        EvidenceNode.document_version_id == version_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for node in existing_nodes:
            if node.node_id not in {document_node.node_id, version_node.node_id}:
                await self.add_edge(
                    str(version_node.node_id),
                    str(node.node_id),
                    EvidenceEdgeType.CONTAINS,
                    organization_id=organization_id,
                )
        await self.db.flush()
        return await self.build_evidence_graph(document_id, organization_id, version_id)

    async def build_evidence_graph(
        self,
        document_id: str,
        organization_id: str | None = None,
        document_version_id: str | None = None,
    ) -> EvidenceGraphResponse:
        document = await self._document(document_id, organization_id)
        version = await self._version(document_id, document_version_id)
        document_version_id = str(version.id)
        query = select(EvidenceNode).where(
            EvidenceNode.document_id == document_id,
            EvidenceNode.organization_id == str(document.organization_id),
            EvidenceNode.document_version_id == document_version_id,
        )
        nodes = (
            (
                await self.db.execute(
                    query.order_by(EvidenceNode.created_at.asc(), EvidenceNode.node_id)
                )
            )
            .scalars()
            .all()
        )
        base_ids = {str(node.node_id) for node in nodes}
        edges: Sequence[EvidenceEdge] = []
        if base_ids:
            edges = (
                (
                    await self.db.execute(
                        select(EvidenceEdge)
                        .where(
                            EvidenceEdge.organization_id
                            == str(document.organization_id),
                            EvidenceEdge.document_id == document_id,
                            EvidenceEdge.document_version_id == document_version_id,
                            EvidenceEdge.source_node_id.in_(base_ids),
                            EvidenceEdge.target_node_id.in_(base_ids),
                        )
                        .order_by(EvidenceEdge.created_at.asc(), EvidenceEdge.id)
                    )
                )
                .scalars()
                .all()
            )
        node_ids = {str(node.node_id) for node in nodes}
        edges = [
            edge
            for edge in edges
            if str(edge.source_node_id) in node_ids
            and str(edge.target_node_id) in node_ids
        ]
        generated_targets = {
            str(edge.target_node_id)
            for edge in edges
            if edge.edge_type == EvidenceEdgeType.GENERATED_FINDING.value
        }
        orphan_findings = [
            str(node.node_id)
            for node in nodes
            if node.canonical_type == CanonicalEvidenceNodeType.FINDING.value
            and str(node.node_id) not in generated_targets
        ]
        return EvidenceGraphResponse(
            schema_version=GRAPH_SCHEMA_VERSION,
            document_id=str(document.id),
            document_version_id=document_version_id,
            complete=not orphan_findings,
            orphan_finding_node_ids=orphan_findings,
            nodes=[EvidenceNodeResponse.model_validate(node) for node in nodes],
            edges=[EvidenceEdgeResponse.model_validate(edge) for edge in edges],
            limitations=[
                "Graph relationships describe traceability and evidence lineage; they do not convert statistical signals into objective authorship claims.",
                "A graph is complete only when every FINDING node has a GENERATED_FINDING parent edge.",
            ],
        )

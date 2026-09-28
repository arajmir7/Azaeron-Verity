"""Evidence-first report aggregation with explicit availability states."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from app.modules.evidence.models import CanonicalEvidenceNodeType
from app.modules.evidence.schemas import (
    EvidenceFirstReportResponse,
    EvidenceGraphResponse,
    ReportDimension,
    ReportEvidence,
    ReportHighlight,
)
from app.modules.evidence.service import EvidenceService

DIMENSIONS = (
    (
        "originality",
        "Originality",
        "Review highlighted overlap evidence; similarity is not a plagiarism finding.",
    ),
    (
        "similarity",
        "Similarity",
        "Compare each highlighted target span with its preserved source context.",
    ),
    (
        "ai_writing_signals",
        "AI-writing signals",
        "Treat statistical signals as review evidence; do not assert authorship or AI use.",
    ),
    (
        "authorship_consistency",
        "Authorship consistency",
        "Supply a minimum-quality historical baseline or leave this dimension untested.",
    ),
    (
        "citation_integrity",
        "Citation integrity",
        "Review unsupported or unverifiable claims and preserve the cited evidence trail.",
    ),
    (
        "source_quality",
        "Source quality",
        "Verify source metadata and retrieval status through a trusted source before relying on it.",
    ),
    (
        "provenance",
        "Provenance",
        "Retain the analyzed version fingerprint and export the immutable timeline when needed.",
    ),
)


class EvidenceFirstReportService:
    def __init__(self, db):
        self.db = db
        self.evidence = EvidenceService(db)

    async def build(
        self,
        document_id: str,
        organization_id: str,
        document_version_id: str | None = None,
    ) -> EvidenceFirstReportResponse:
        graph = await self.evidence.materialize_document_graph(
            document_id, organization_id, document_version_id
        )
        dimensions = [
            self._dimension(key, label, action, graph)
            for key, label, action in DIMENSIONS
        ]
        highlights = self._highlights(graph, dimensions)
        limitations = list(
            dict.fromkeys(
                [
                    "This report presents evidence and operational maturity, not a single authorship or AI percentage.",
                    "Missing, abstained, or unvalidated analyses remain explicitly unscored.",
                ]
                + graph.limitations
                + [item for dimension in dimensions for item in dimension.limitations]
            )
        )
        return EvidenceFirstReportResponse(
            document_id=document_id,
            document_version_id=graph.document_version_id,
            generated_at=datetime.now(timezone.utc),
            dimensions=dimensions,
            highlights=highlights,
            limitations=limitations,
            graph=graph,
        )

    @staticmethod
    def _node_dimension(node) -> str | None:
        if node.canonical_type == CanonicalEvidenceNodeType.SIMILARITY_MATCH.value:
            return "similarity"
        if node.canonical_type == CanonicalEvidenceNodeType.AI_SIGNAL.value:
            return "ai_writing_signals"
        if node.canonical_type == CanonicalEvidenceNodeType.AUTHORSHIP_SIGNAL.value:
            return "authorship_consistency"
        if node.canonical_type in {
            CanonicalEvidenceNodeType.CLAIM.value,
            CanonicalEvidenceNodeType.CITATION.value,
        }:
            return "citation_integrity"
        if node.canonical_type == CanonicalEvidenceNodeType.SOURCE.value:
            return "source_quality"
        if node.canonical_type in {
            CanonicalEvidenceNodeType.DOCUMENT_VERSION.value,
            CanonicalEvidenceNodeType.PROVENANCE_EVENT.value,
        }:
            return "provenance"
        if node.canonical_type == CanonicalEvidenceNodeType.FINDING.value:
            finding = (node.finding_type or "").lower()
            if "similarity" in finding:
                return "similarity"
            if "ai_signal" in finding or "detection" in finding:
                return "ai_writing_signals"
            if "author" in finding:
                return "authorship_consistency"
            if finding not in {"", "document", "document_version"}:
                return "citation_integrity"
        return None

    @staticmethod
    def _status(key: str, nodes: list) -> tuple[str, str, str]:
        if key == "provenance":
            return (
                "PRODUCTION",
                "Versioned hashes and append-only events are available.",
                "HASHED_LINEAGE",
            )
        if not nodes:
            return (
                "INSUFFICIENT_EVIDENCE",
                "No evidence was recorded for this dimension.",
                "UNAVAILABLE",
            )
        if key in {"ai_writing_signals", "authorship_consistency"}:
            return (
                "EXPERIMENTAL",
                "Evidence was recorded, but this capability is not a validated production classifier.",
                "EXPERIMENTAL",
            )
        if key in {"originality", "similarity"}:
            return (
                "EXPERIMENTAL",
                "Bounded retrieval and verification evidence is available; semantic validation is limited.",
                "EXPERIMENTAL_VERIFIER",
            )
        if key in {"citation_integrity", "source_quality"}:
            return (
                "EXPERIMENTAL",
                "Structured citation/source evidence is available; unsupported claims remain review items.",
                "EVIDENCE_RECORD",
            )
        return (
            "EXPERIMENTAL",
            "Evidence is available with configured limitations.",
            "UNAVAILABLE",
        )

    def _dimension(
        self, key: str, label: str, action: str, graph: EvidenceGraphResponse
    ) -> ReportDimension:
        nodes = [node for node in graph.nodes if self._node_dimension(node) == key]
        if key == "originality":
            nodes = [
                node
                for node in graph.nodes
                if node.canonical_type
                == CanonicalEvidenceNodeType.SIMILARITY_MATCH.value
                or node.finding_type == "similarity_match"
            ]
        status, default_summary, reliability = self._status(key, nodes)
        evidence = self._evidence_for(nodes, graph)
        confidence_values = [
            item.confidence
            for item in evidence
            if item.confidence is not None and item.confidence > 0
        ]
        confidence = (
            round(sum(confidence_values) / len(confidence_values), 6)
            if confidence_values and status == "EXPERIMENTAL"
            else None
        )
        limitations = self._limitations(key, nodes, graph)
        if key in {"originality", "similarity"} and nodes:
            summary = f"{len(nodes)} overlap evidence record(s) require review; no plagiarism conclusion is made."
        elif key == "provenance":
            summary = "Immutable document-version lineage and provenance events are available."
        elif nodes:
            summary = f"{len(nodes)} evidence record(s) are available for review."
        else:
            summary = default_summary
        return ReportDimension(
            key=key,
            label=label,
            status=status,
            summary=summary,
            confidence=confidence,
            confidence_reliability=(
                reliability if confidence is not None else "UNAVAILABLE"
            ),
            evidence=evidence[:30],
            limitations=limitations,
            recommended_action=action,
        )

    @staticmethod
    def _limitations(key: str, nodes: list, graph: EvidenceGraphResponse) -> list[str]:
        limitations: list[str] = []
        if key in {"originality", "similarity"}:
            limitations.extend(
                [
                    "Similarity indicates overlap evidence, not plagiarism.",
                    "Semantic embedding and cross-encoder verification are not asserted unless present in the evidence metadata.",
                ]
            )
        elif key == "ai_writing_signals":
            limitations.extend(
                [
                    "The configured detector remains experimental and may abstain.",
                    "A writing signal does not establish that an author used AI.",
                ]
            )
        elif key == "authorship_consistency":
            limitations.extend(
                [
                    "Style deviation does not identify a person.",
                    "Confidence is baseline-data adequacy, not identity probability.",
                ]
            )
        elif key == "citation_integrity":
            limitations.append(
                "A citation is not treated as supporting a claim without recorded evidence."
            )
        elif key == "source_quality":
            limitations.append(
                "Source quality is not converted into a fabricated score when retrieval evidence is absent."
            )
        elif key == "provenance":
            limitations.append(
                "Hashes establish content identity and ordering; they do not establish authorship."
            )
        if not nodes:
            limitations.append(
                "NOT TESTED or no matching evidence was recorded for this document version."
            )
        return limitations

    def _evidence_for(
        self, nodes: list, graph: EvidenceGraphResponse
    ) -> list[ReportEvidence]:
        node_by_id = {node.node_id: node for node in graph.nodes}
        outgoing: dict[str, list] = defaultdict(list)
        incoming: dict[str, list] = defaultdict(list)
        for edge in graph.edges:
            outgoing[edge.source_node_id].append(edge)
            incoming[edge.target_node_id].append(edge)
        evidence: list[ReportEvidence] = []
        for node in nodes:
            # Walk only the evidence-bearing relationship types. This keeps a
            # report local to a finding while preserving paths such as
            # finding -> claim -> citation -> source and
            # finding -> similarity match -> source.
            related = {node.node_id}
            pending = [node.node_id]
            while pending:
                current = pending.pop()
                adjacent = [(edge, edge.target_node_id) for edge in outgoing[current]]
                adjacent += [(edge, edge.source_node_id) for edge in incoming[current]]
                for edge, adjacent_id in adjacent:
                    if edge.edge_type not in {
                        "GENERATED_FINDING",
                        "SUPPORTED_BY",
                        "CITES",
                    }:
                        continue
                    if adjacent_id not in related:
                        related.add(adjacent_id)
                        pending.append(adjacent_id)
            related_nodes = [node_by_id[item] for item in related if item in node_by_id]
            source_nodes = [
                item
                for item in related_nodes
                if item.canonical_type == CanonicalEvidenceNodeType.SOURCE.value
            ]
            claim_nodes = [
                item
                for item in related_nodes
                if item.canonical_type == CanonicalEvidenceNodeType.CLAIM.value
            ]
            citation_nodes = [
                item
                for item in related_nodes
                if item.canonical_type == CanonicalEvidenceNodeType.CITATION.value
            ]
            explanation = node.description or node.title
            evidence.append(
                ReportEvidence(
                    evidence_node_id=node.node_id,
                    canonical_type=node.canonical_type,
                    title=node.title,
                    explanation=explanation,
                    span_start=node.span_start,
                    span_end=node.span_end,
                    span_text=node.span_text,
                    confidence=node.confidence if node.confidence > 0 else None,
                    confidence_reliability=(
                        "EXPERIMENTAL" if node.confidence > 0 else "UNAVAILABLE"
                    ),
                    source_ids=[item.entity_id for item in source_nodes],
                    source_titles=[item.title for item in source_nodes],
                    claim_ids=[item.entity_id for item in claim_nodes],
                    citation_ids=[item.entity_id for item in citation_nodes],
                )
            )
        return evidence

    def _highlights(
        self, graph: EvidenceGraphResponse, dimensions: list[ReportDimension]
    ) -> list[ReportHighlight]:
        status_by_key = {item.key: item.status for item in dimensions}
        candidates = [
            node
            for node in graph.nodes
            if node.canonical_type == CanonicalEvidenceNodeType.FINDING.value
            and node.span_text
        ]
        highlights: list[ReportHighlight] = []
        for node in candidates:
            key = self._node_dimension(node) or "citation_integrity"
            evidence = self._evidence_for([node], graph)[0]
            segment_type = str((node.metadata_json or {}).get("segment_type") or "span")
            highlights.append(
                ReportHighlight(
                    **evidence.model_dump(),
                    dimension=key,
                    segment_type=segment_type,
                    status=status_by_key.get(key, "INSUFFICIENT_EVIDENCE"),
                )
            )
        return highlights[:200]

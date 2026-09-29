"""Import every ORM model before Alembic or mapper configuration runs."""

# The imports are intentional: SQLAlchemy relationships use the shared registry.
from app.modules.auth.models import ApiKey, RefreshToken, User
from app.modules.auth.identity_models import IdentityToken, IdentityMail
from app.modules.organizations.models import Membership, Organization
from app.modules.assignments.models import Assignment, Submission
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs.models import Job
from app.modules.processing.models import ProcessedDocument
from app.modules.similarity.models import (
    DocumentChunk,
    SimilarityIndexEntry,
    SimilarityMatch,
    SimilarityAnalysis,
)
from app.modules.citations.models import (
    Citation,
    Claim,
    CitationFinding,
    Reference,
    Source,
    SupportStatus,
)
from app.modules.detection.models import DetectionResult, DetectionSegment
from app.modules.authorship.models import AuthorshipProfile, AuthorshipSignal
from app.modules.provenance.models import (
    ProvenanceEvent,
    ProvenanceReport,
    ProvenanceExport,
)
from app.modules.evidence.models import EvidenceEdge, EvidenceNode
from app.modules.evidence.report_models import IntegrityReport
from app.modules.audit.models import AuditLog
from app.modules.compliance.models import BillingEvent, ComplianceReport
from app.modules.aegiswrite.models import AegisEdit
from app.modules.governance.models import (
    AnalysisRun,
    AnalysisLineageMixin,
    EvaluationDataset,
    EvaluationExample,
    ModelRegistry,
)

from app.modules.privacy.models import ErasureRequest
from app.modules.billing.models import UsageBucket, UsageOperation
from app.modules.agent.models import (
    VoiceProfile,
    Conversation,
    Message,
    AgentRun,
    ToolCall,
    ToolResult,
    DocumentAttachment,
    AgentEvent,
    ActionReceipt,
)

__all__ = [name for name in globals() if name[0].isupper()]

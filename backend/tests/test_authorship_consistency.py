import hashlib
import uuid

from app.modules.auth.models import User
from app.modules.authorship.intelligence import AuthorshipFeatureAnalyzer
from app.modules.authorship.models import AuthorshipProfile
from app.modules.authorship.service import AuthorshipService
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.organizations.models import Organization
from app.modules.processing.models import ProcessedDocument

BASELINE_TEXT = (
    "The research team recorded seasonal water levels across the basin during the field study. "
    "Measurements were reviewed by two analysts before the values were entered into the report. "
    "The results show gradual variation between sites and a stable pattern across the observation period. "
    "These observations support careful comparison between the upstream and downstream locations. "
    "The team documented each decision so that later reviewers could reproduce the analysis. "
    "Additional samples were collected when the first reading appeared inconsistent with nearby records. "
    "The final summary describes the method, the observed limits, and the remaining uncertainty. "
    "No conclusion was extended beyond the measurements available in the historical record. "
    "The authors used plain descriptions and short transitions between the main sections. "
    "The report was revised after the technical review and retained the original data notes. "
) * 2


def test_baseline_quality_gate_requires_multiple_sufficient_samples():
    analyzer = AuthorshipFeatureAnalyzer()
    baseline = analyzer.build_baseline([("one", BASELINE_TEXT), ("two", BASELINE_TEXT)])

    assert baseline["baseline_quality"] == "INSUFFICIENT"
    comparison = analyzer.compare(analyzer.extract(BASELINE_TEXT), baseline)
    assert comparison["eligible"] is False
    assert comparison["stylistic_deviation"] is None


async def test_authorship_abstains_without_baseline_and_links_evidence(db_session):
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    db_session.add_all(
        [
            Organization(
                id=org_id, name="Authorship test org", slug=f"authorship-{org_id[:8]}"
            ),
            User(
                id=user_id,
                email=f"authorship-{org_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
        ]
    )
    await db_session.flush()
    fingerprint = hashlib.sha256(BASELINE_TEXT.encode()).hexdigest()
    db_session.add(
        Document(
            id=document_id,
            organization_id=org_id,
            owner_id=user_id,
            filename="target.txt",
            original_filename="target.txt",
            file_size=len(BASELINE_TEXT),
            mime_type="text/plain",
            extension=".txt",
            sha256_fingerprint=fingerprint,
            storage_path=f"authorship/{document_id}",
            status=DocumentStatus.PROCESSING,
        )
    )
    db_session.add(
        DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            storage_path=f"authorship/{document_id}",
            sha256_fingerprint=fingerprint,
            content_hash=fingerprint,
            created_by_id=user_id,
        )
    )
    await db_session.flush()
    processed = ProcessedDocument(
        document_id=document_id,
        organization_id=org_id,
        document_version_id=version_id,
        pipeline_version="document-processing-v2",
        model_version="processor-v2",
        raw_text=BASELINE_TEXT,
        cleaned_text=BASELINE_TEXT,
        word_count=len(BASELINE_TEXT.split()),
        sentence_count=20,
        paragraph_count=1,
    )
    db_session.add(processed)
    await db_session.flush()

    signal = await AuthorshipService(db_session).analyze_authorship(
        document_id, processed
    )

    assert signal.verdict == "INSUFFICIENT_DATA"
    assert signal.baseline_quality == "MISSING_BASELINE"
    assert signal.confidence is None
    assert signal.evidence_id is not None
    assert signal.ai_writing_signal["status"] == "NOT_TESTED"
    assert signal.stylistic_deviation["status"] == "INSUFFICIENT_DATA"


async def test_profile_baseline_returns_consistency_and_separates_ai_signal(db_session):
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    db_session.add_all(
        [
            Organization(
                id=org_id, name="Profile test org", slug=f"profile-{org_id[:8]}"
            ),
            User(
                id=user_id,
                email=f"profile-{org_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
        ]
    )
    await db_session.flush()

    processed_documents = []
    for index in range(4):
        document_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        fingerprint = hashlib.sha256(
            f"{document_id}:{BASELINE_TEXT}".encode()
        ).hexdigest()
        db_session.add(
            Document(
                id=document_id,
                organization_id=org_id,
                owner_id=user_id,
                filename=f"sample-{index}.txt",
                original_filename=f"sample-{index}.txt",
                file_size=len(BASELINE_TEXT),
                mime_type="text/plain",
                extension=".txt",
                sha256_fingerprint=fingerprint,
                storage_path=f"authorship/{document_id}",
                status=DocumentStatus.PROCESSING,
            )
        )
        db_session.add(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                storage_path=f"authorship/{document_id}",
                sha256_fingerprint=fingerprint,
                content_hash=fingerprint,
                created_by_id=user_id,
            )
        )
        processed_documents.append(
            ProcessedDocument(
                document_id=document_id,
                organization_id=org_id,
                document_version_id=version_id,
                pipeline_version="document-processing-v2",
                model_version="processor-v2",
                raw_text=BASELINE_TEXT,
                cleaned_text=BASELINE_TEXT,
                word_count=len(BASELINE_TEXT.split()),
                sentence_count=20,
                paragraph_count=1,
            )
        )
    db_session.add_all(processed_documents)
    await db_session.flush()
    profile = AuthorshipProfile(
        organization_id=org_id,
        user_id=user_id,
        name="Historical baseline",
        baseline_document_ids=[],
    )
    db_session.add(profile)
    await db_session.flush()
    service = AuthorshipService(db_session)
    await service.build_profile(profile, processed_documents[:3])
    signal = await service.analyze_authorship(
        str(processed_documents[3].document_id), processed_documents[3], str(profile.id)
    )

    assert signal.verdict == "CONSISTENT"
    assert signal.baseline_quality in {"ADEQUATE", "STRONG"}
    assert signal.confidence is not None
    assert signal.confidence_type == "data_adequacy_not_identity_probability"
    assert signal.ai_writing_signal["status"] == "NOT_TESTED"
    assert signal.stylistic_deviation["signals"]
    assert signal.evidence_id is not None

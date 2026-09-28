from datetime import datetime, timezone
import hashlib
import uuid

from app.modules.auth.models import User
from app.modules.citations.models import CitationFinding, SupportStatus
from app.modules.citations.resolver import ResolvedSource
from app.modules.citations.service import CitationService
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.organizations.models import Organization
from app.modules.processing.models import ProcessedDocument


class StaticResolver:
    name = "static-test-resolver"

    async def resolve(self, doi: str):
        return ResolvedSource(
            title="River basin ecology",
            authors=["Jane Smith"],
            publisher="Test Publisher",
            doi=doi,
            url=f"https://doi.org/{doi}",
            abstract_text="River basins support diverse habitats and seasonal migration patterns across connected ecosystems.",
            retrieval_timestamp=datetime.now(timezone.utc),
            payload_hash=hashlib.sha256(doi.encode()).hexdigest(),
            provider=self.name,
        )


def test_support_is_fail_closed_without_retrieved_source():
    support, evidence = CitationService(None)._assess_support(
        "A claim without source content", None
    )

    assert support is SupportStatus.UNVERIFIABLE
    assert evidence["source_excerpt"] is None
    assert evidence["retrieval_status"] == "NO_SOURCE"


async def test_citation_analysis_links_claim_reference_source_and_evidence(db_session):
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    text = (
        "A study shows river basins support diverse habitats and seasonal migration patterns (Smith, 2020). "
        "The second factual claim has no supporting citation and requires review.\n\n"
        "References\n"
        "Smith, J. (2020). River basin ecology. https://doi.org/10.1234/river.1\n"
        "Smith, J. (2020). River basin ecology. https://doi.org/10.1234/river.1"
    )
    db_session.add_all(
        [
            Organization(
                id=org_id, name="Citation test org", slug=f"citation-test-{org_id[:8]}"
            ),
            User(
                id=user_id,
                email=f"citation-{org_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Document(
                id=document_id,
                organization_id=org_id,
                owner_id=user_id,
                filename="citation.txt",
                original_filename="citation.txt",
                file_size=len(text),
                mime_type="text/plain",
                extension=".txt",
                sha256_fingerprint=hashlib.sha256(text.encode()).hexdigest(),
                storage_path=f"citation/{document_id}",
                status=DocumentStatus.PROCESSING,
            ),
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                storage_path=f"citation/{document_id}",
                sha256_fingerprint=hashlib.sha256(text.encode()).hexdigest(),
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
                created_by_id=user_id,
            ),
        ]
    )
    await db_session.flush()
    processed = ProcessedDocument(
        document_id=document_id,
        organization_id=org_id,
        document_version_id=version_id,
        pipeline_version="document-processing-v2",
        model_version="processor-v2",
        raw_text=text,
        cleaned_text=text,
        word_count=len(text.split()),
        sentence_count=2,
        paragraph_count=2,
    )
    db_session.add(processed)
    await db_session.flush()

    citations = await CitationService(
        db_session, resolver=StaticResolver()
    ).analyze_citations(document_id, processed)
    findings = list(
        (await db_session.execute(CitationFinding.__table__.select())).mappings()
    )

    assert len(citations) == 1
    assert citations[0].support_status is SupportStatus.SUPPORTED
    assert citations[0].source_id is not None
    assert citations[0].reference_id is not None
    assert citations[0].evidence_id is not None
    assert citations[0].title == "River basin ecology"
    assert any(row["finding_type"] == "MISSING_CITATION" for row in findings)
    assert any(row["finding_type"] == "DUPLICATE_REFERENCE" for row in findings)
    assert all(row["evidence_id"] is not None for row in findings)

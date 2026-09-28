"""Auditable claim -> citation -> reference -> source intelligence."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Iterable, List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.citations.models import (
    Citation,
    CitationFinding,
    CitationStatus,
    Claim,
    Reference,
    Source,
    SupportStatus,
)
from app.modules.citations.resolver import (
    DOI_PATTERN,
    CrossrefSourceResolver,
    ResolvedSource,
    SourceResolver,
)
from app.modules.evidence.models import EvidenceNodeType
from app.modules.evidence.service import EvidenceService
from app.modules.processing.models import ProcessedDocument
from app.modules.documents.target import require_processed_target
from app.modules.processing.structure import (
    REFERENCE_HEADER as STRUCTURE_REFERENCE_HEADER,
)

logger = get_logger(__name__)

PIPELINE_VERSION = "citation-intelligence-v2"
MODEL_VERSION = "claim-citation-source-v1"
REFERENCE_MODEL_VERSION = "reference-parser-v1"


@dataclass(frozen=True)
class ParsedReference:
    key: str
    raw_text: str
    authors: list[str]
    title: str | None
    year: int | None
    doi: str | None
    url: str | None
    publisher: str | None
    metadata_issues: tuple[str, ...]


class CitationService:
    """Extract, resolve, and evidence-link citation findings.

    The default resolver only queries Crossref for a validated DOI. Arbitrary
    URLs are preserved but not fetched. Missing metadata and missing source
    content remain UNVERIFIABLE rather than being upgraded to support.
    """

    INLINE_PATTERNS = (
        re.compile(r"\[(?P<key>\d+(?:\s*,\s*\d+)*)\]"),
        re.compile(
            r"\((?P<key>[^()\n]{1,160}?\b(?:19|20)\d{2}[a-z]?(?:\s*;\s*[^()\n]*)?)\)"
        ),
    )
    REFERENCE_HEADER = STRUCTURE_REFERENCE_HEADER
    DOI_RE = re.compile(
        r"(?:https?://doi\.org/)?(10\.\d{4,9}/[^\s<>\"']+)", re.IGNORECASE
    )
    URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
    YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
    CLAIM_CUES = re.compile(
        r"\b(is|are|was|were|has|have|shows?|found|finds?|suggests?|demonstrates?|increases?|decreases?|causes?|leads?|requires?|according|study|research|evidence|significant|percent|claim|citation|support(?:s|ing)?|%)\b|\b\d+(?:\.\d+)?%?\b",
        re.IGNORECASE,
    )

    def __init__(self, db: AsyncSession, resolver: SourceResolver | None = None):
        self.db = db
        self.resolver = resolver or CrossrefSourceResolver()

    async def analyze_citations(
        self, document_id: str, processed: ProcessedDocument
    ) -> List[Citation]:
        text = processed.cleaned_text or ""
        self._require_lineage(processed)
        require_processed_target(document_id, processed)
        if not text.strip():
            return []

        structure = processed.structure_json or {}
        body_end = structure.get("body_end", self._body_end(text))
        body = text[:body_end]
        inline_matches = (
            [
                {
                    "start": c["start"],
                    "end": c["end"],
                    "raw_text": c["text"],
                    "key": c["key"],
                }
                for c in structure["citations"]
            ]
            if structure.get("body_end") is not None
            else self._inline_matches(body)
        )
        sentence_spans = (
            [
                (
                    s["start"],
                    min(s["end"], body_end),
                    text[s["start"] : min(s["end"], body_end)],
                )
                for s in structure["sentences"]
                if s["start"] < body_end
            ]
            if structure.get("sentences")
            else self._sentence_spans(body)
        )
        claims: list[Claim] = []
        for start, end, sentence in sentence_spans:
            contained = [
                item
                for item in inline_matches
                if start <= item["start"] and item["end"] <= end
            ]
            if not contained and not self._looks_like_claim(sentence):
                continue
            claims.append(
                Claim(
                    document_id=document_id,
                    organization_id=str(processed.organization_id),
                    document_version_id=str(processed.document_version_id),
                    pipeline_version=PIPELINE_VERSION,
                    model_version=MODEL_VERSION,
                    text=sentence,
                    claim_type="factual_or_research_claim",
                    span_start=start,
                    span_end=end,
                    has_citation=bool(contained),
                    support_status=SupportStatus.UNVERIFIABLE,
                    confidence=0.0,
                )
            )
        self.db.add_all(claims)
        await self.db.flush()

        references = await self._store_references(
            document_id, processed, self._parse_references(text, body_end)
        )
        source_by_reference: dict[str, Source] = {}
        source_cache: dict[str, Source] = {}
        for stored_reference in references:
            key = self._source_key(stored_reference)
            source = source_cache.get(key)
            if source is None:
                source = await self._create_source(stored_reference, processed, key)
                source_cache[key] = source
            stored_reference.source_id = str(source.id)
            source_by_reference[str(stored_reference.id)] = source
        await self.db.flush()

        citations: list[Citation] = []
        claim_citations: dict[str, list[Citation]] = defaultdict(list)
        reference_usage: dict[str, list[tuple[Claim, Citation]]] = defaultdict(list)
        for item in inline_matches:
            claim = self._claim_for_span(claims, item["start"], item["end"])
            reference = self._match_reference(item["key"], references)
            citation = Citation(
                document_id=document_id,
                organization_id=str(processed.organization_id),
                document_version_id=str(processed.document_version_id),
                pipeline_version=PIPELINE_VERSION,
                model_version=MODEL_VERSION,
                claim_id=str(claim.id) if claim else None,
                reference_id=str(reference.id) if reference else None,
                source_id=(
                    str(reference.source_id)
                    if reference and reference.source_id
                    else None
                ),
                raw_text=item["raw_text"],
                citation_key=item["key"],
                citation_type=(
                    "numeric" if item["key"].strip().isdigit() else "author_year"
                ),
                authors=reference.authors if reference else None,
                title=reference.title if reference else None,
                year=reference.year if reference else None,
                doi=reference.doi if reference else None,
                url=reference.url if reference else None,
                publisher=reference.publisher if reference else None,
                status=(
                    CitationStatus.UNVERIFIED if reference else CitationStatus.BROKEN
                ),
                support_status=SupportStatus.UNVERIFIABLE,
                span_start=item["start"],
                span_end=item["end"],
            )
            self.db.add(citation)
            citations.append(citation)
            if claim:
                claim_citations[str(claim.id)].append(citation)
            if claim and reference:
                reference_usage[str(reference.id)].append((claim, citation))
        await self.db.flush()

        for claim in claims:
            claim_key = str(claim.id)
            linked = claim_citations.get(claim_key, [])
            if not linked:
                await self._record_finding(
                    document_id=document_id,
                    processed=processed,
                    claim=claim,
                    finding_type="MISSING_CITATION",
                    support_status=SupportStatus.UNVERIFIABLE,
                    message="This factual or research-like claim has no detected in-text citation.",
                    evidence={
                        "claim_text": claim.text,
                        "reason": "no_inline_citation_detected",
                    },
                )
                continue

            statuses: list[SupportStatus] = []
            for citation in linked:
                reference = await self._reference_by_id(
                    references, citation.reference_id
                )
                source = (
                    source_by_reference.get(str(reference.id)) if reference else None
                )
                if reference is None:
                    await self._record_finding(
                        document_id=document_id,
                        processed=processed,
                        claim=claim,
                        citation=citation,
                        finding_type="BROKEN_REFERENCE",
                        support_status=SupportStatus.UNVERIFIABLE,
                        message=f"Citation {citation.raw_text} does not resolve to a bibliography reference.",
                        evidence={
                            "citation_text": citation.raw_text,
                            "citation_key": citation.citation_key,
                        },
                    )
                    await self._record_finding(
                        document_id=document_id,
                        processed=processed,
                        claim=claim,
                        citation=citation,
                        finding_type="CITATION_REFERENCE_MISMATCH",
                        support_status=SupportStatus.UNVERIFIABLE,
                        message="The in-text citation key and bibliography entries do not match.",
                        evidence={"citation_key": citation.citation_key},
                    )
                    statuses.append(SupportStatus.UNVERIFIABLE)
                    continue

                if reference.metadata_json and reference.metadata_json.get(
                    "metadata_issues"
                ):
                    await self._record_finding(
                        document_id=document_id,
                        processed=processed,
                        claim=claim,
                        citation=citation,
                        reference=reference,
                        source=source,
                        finding_type="INCORRECT_METADATA",
                        support_status=SupportStatus.UNVERIFIABLE,
                        message="The bibliography metadata is incomplete or malformed.",
                        evidence={
                            "metadata_issues": reference.metadata_json[
                                "metadata_issues"
                            ]
                        },
                    )

                support, evidence = self._assess_support(claim.text, source)
                statuses.append(support)
                citation.support_status = support
                citation.status = (
                    CitationStatus.VALID
                    if support is SupportStatus.SUPPORTED
                    else CitationStatus.UNVERIFIED
                )
                citation.retrieval_timestamp = (
                    source.retrieval_timestamp if source else None
                )
                citation.verification_data = evidence
                await self._record_finding(
                    document_id=document_id,
                    processed=processed,
                    claim=claim,
                    citation=citation,
                    reference=reference,
                    source=source,
                    finding_type="SOURCE_SUPPORT_ASSESSMENT",
                    support_status=support,
                    message=self._support_message(support),
                    evidence=evidence,
                )
                if support is not SupportStatus.SUPPORTED:
                    await self._record_finding(
                        document_id=document_id,
                        processed=processed,
                        claim=claim,
                        citation=citation,
                        reference=reference,
                        source=source,
                        finding_type=(
                            "WEAK_SOURCE_SUPPORT"
                            if support is SupportStatus.PARTIALLY_SUPPORTED
                            else "UNSUPPORTED_CLAIM"
                        ),
                        support_status=support,
                        message="The available source evidence is insufficient to establish this claim.",
                        evidence=evidence,
                    )
            claim.support_status = self._aggregate_support(statuses)
            claim.citation_supports_claim = (
                True
                if claim.support_status is SupportStatus.SUPPORTED
                else (
                    False
                    if claim.support_status
                    in {SupportStatus.NOT_SUPPORTED, SupportStatus.PARTIALLY_SUPPORTED}
                    else None
                )
            )

        duplicate_groups: dict[str, list[Reference]] = defaultdict(list)
        for reference in references:
            duplicate_groups[self._source_key(reference)].append(reference)
        for duplicate_key, duplicate_references in duplicate_groups.items():
            if len(duplicate_references) <= 1:
                continue
            uses = [
                use
                for reference in duplicate_references
                for use in reference_usage.get(str(reference.id), [])
            ]
            if not uses:
                continue
            claim, citation = uses[0]
            reference = duplicate_references[0]
            source = source_by_reference.get(str(reference.id))
            await self._record_finding(
                document_id=document_id,
                processed=processed,
                claim=claim,
                citation=citation,
                reference=reference,
                source=source,
                finding_type="DUPLICATE_REFERENCE",
                support_status=SupportStatus.UNVERIFIABLE,
                message="The same bibliography reference is cited more than once in the reference list or citation mapping.",
                evidence={
                    "reference_key": reference.reference_key,
                    "source_key": duplicate_key,
                    "duplicate_count": len(duplicate_references),
                    "usage_count": len(uses),
                },
            )

        await self.db.flush()
        logger.info(
            "citation_intelligence_complete",
            document_id=document_id,
            claims=len(claims),
            citations=len(citations),
            references=len(references),
            resolver=self.resolver.name,
        )
        return citations

    async def _store_references(
        self,
        document_id: str,
        processed: ProcessedDocument,
        parsed: Sequence[ParsedReference],
    ) -> list[Reference]:
        references = [
            Reference(
                document_id=document_id,
                organization_id=str(processed.organization_id),
                document_version_id=str(processed.document_version_id),
                pipeline_version=PIPELINE_VERSION,
                model_version=REFERENCE_MODEL_VERSION,
                reference_key=item.key,
                raw_text=item.raw_text,
                authors=item.authors,
                title=item.title,
                year=item.year,
                doi=item.doi,
                url=item.url,
                publisher=item.publisher,
                metadata_json={"metadata_issues": list(item.metadata_issues)},
            )
            for item in parsed
        ]
        structural_references = (processed.structure_json or {}).get("references", [])
        for reference, structural in zip(references, structural_references):
            if reference.raw_text == structural["text"]:
                reference.metadata_json = {
                    **(reference.metadata_json or {}),
                    "structure_element_id": structural["id"],
                    "span_start": structural["start"],
                    "span_end": structural["end"],
                    "page_numbers": structural.get("page_numbers", []),
                    "parser_version": processed.parser_version,
                    "normalized_content_hash": processed.normalized_content_hash,
                }
        self.db.add_all(references)
        await self.db.flush()
        return references

    async def _create_source(
        self, reference: Reference, processed: ProcessedDocument, source_key: str
    ) -> Source:
        source = Source(
            document_id=str(processed.document_id),
            organization_id=str(processed.organization_id),
            document_version_id=str(processed.document_version_id),
            pipeline_version=PIPELINE_VERSION,
            model_version=MODEL_VERSION,
            source_key=source_key,
            title=reference.title,
            authors=reference.authors,
            publisher=reference.publisher,
            doi=reference.doi,
            url=reference.url,
            retrieval_status="NOT_RETRIEVED",
            metadata_json={"provided_metadata": self._reference_metadata(reference)},
        )
        resolved: ResolvedSource | None = None
        if reference.doi and DOI_PATTERN.fullmatch(reference.doi):
            resolved = await self.resolver.resolve(reference.doi)
        if resolved:
            # The reference preserves what the document supplied; the source
            # record reflects resolver-confirmed metadata when it exists.
            source.title = resolved.title or source.title
            source.authors = resolved.authors or source.authors
            source.publisher = resolved.publisher or source.publisher
            source.doi = resolved.doi or source.doi
            source.url = resolved.url or source.url
            source.abstract_text = resolved.abstract_text
            source.retrieval_timestamp = resolved.retrieval_timestamp
            source.retrieved_payload_hash = resolved.payload_hash
            source.retrieval_status = "RETRIEVED"
            source.metadata_json = {
                **(source.metadata_json or {}),
                "resolver": resolved.provider,
                "retrieved_metadata": {
                    "title": resolved.title,
                    "authors": resolved.authors,
                    "publisher": resolved.publisher,
                    "doi": resolved.doi,
                    "url": resolved.url,
                },
            }
        elif reference.doi:
            source.retrieval_status = "UNAVAILABLE"
            source.metadata_json = {
                **(source.metadata_json or {}),
                "resolver": self.resolver.name,
            }
        self.db.add(source)
        await self.db.flush()
        return source

    async def _record_finding(
        self,
        *,
        document_id: str,
        processed: ProcessedDocument,
        claim: Claim | None,
        finding_type: str,
        support_status: SupportStatus,
        message: str,
        evidence: dict[str, Any],
        citation: Citation | None = None,
        reference: Reference | None = None,
        source: Source | None = None,
    ) -> CitationFinding:
        finding = CitationFinding(
            document_id=document_id,
            organization_id=str(processed.organization_id),
            document_version_id=str(processed.document_version_id),
            pipeline_version=PIPELINE_VERSION,
            model_version=MODEL_VERSION,
            claim_id=str(claim.id) if claim else None,
            citation_id=str(citation.id) if citation else None,
            reference_id=str(reference.id) if reference else None,
            source_id=str(source.id) if source else None,
            finding_type=finding_type,
            support_status=support_status,
            message=message,
            evidence_json=evidence,
            confidence=0.0,
        )
        self.db.add(finding)
        await self.db.flush()
        node = await EvidenceService(self.db).add_node(
            document_id=document_id,
            node_type=EvidenceNodeType.CLAIM if claim else EvidenceNodeType.CITATION,
            canonical_type="FINDING",
            entity_type="finding",
            title=f"Citation finding: {finding_type}",
            description=message,
            span_start=(
                claim.span_start if claim else citation.span_start if citation else None
            ),
            span_end=(
                claim.span_end if claim else citation.span_end if citation else None
            ),
            span_text=claim.text if claim else citation.raw_text if citation else None,
            confidence=0.0,
            metadata={
                "finding_id": str(finding.id),
                "claim_id": finding.claim_id,
                "citation_id": finding.citation_id,
                "reference_id": finding.reference_id,
                "source_id": finding.source_id,
                "support_status": support_status.value,
                "evidence": evidence,
                "source_support_is_not_inferred": support_status
                is not SupportStatus.SUPPORTED
                or not evidence.get("source_excerpt"),
            },
            document_version_id=str(processed.document_version_id),
            finding_type=finding_type,
            source_id=str(finding.id),
            model_id="citation-intelligence",
            model_version=MODEL_VERSION,
            pipeline_version=PIPELINE_VERSION,
        )
        finding.evidence_id = str(node.id)
        if claim:
            claim.evidence_id = str(node.id)
        if citation:
            citation.evidence_id = str(node.id)
        await self.db.flush()
        return finding

    def _assess_support(
        self, claim_text: str, source: Source | None
    ) -> tuple[SupportStatus, dict[str, Any]]:
        if source is None or not source.abstract_text:
            return SupportStatus.UNVERIFIABLE, {
                "method": "no_retrieved_source_content",
                "source_excerpt": None,
                "retrieval_status": source.retrieval_status if source else "NO_SOURCE",
                "retrieval_timestamp": (
                    source.retrieval_timestamp.isoformat()
                    if source and source.retrieval_timestamp
                    else None
                ),
                "limitations": [
                    "Source content was not retrieved; support was not inferred from metadata."
                ],
            }
        claim_terms = self._content_terms(claim_text)
        source_terms = self._content_terms(source.abstract_text)
        overlap = len(claim_terms & source_terms) / max(1, len(claim_terms))
        status = (
            SupportStatus.SUPPORTED
            if overlap >= 0.70
            else (
                SupportStatus.PARTIALLY_SUPPORTED
                if overlap >= 0.30
                else SupportStatus.NOT_SUPPORTED
            )
        )
        return status, {
            "method": "retrieved-abstract-lexical-overlap-v1",
            "overlap": round(overlap, 6),
            "source_excerpt": source.abstract_text[:1200],
            "source_payload_hash": source.retrieved_payload_hash,
            "retrieval_timestamp": (
                source.retrieval_timestamp.isoformat()
                if source.retrieval_timestamp
                else None
            ),
            "limitations": [
                "This is lexical evidence from a retrieved abstract, not semantic entailment or proof of factual truth."
            ],
        }

    @staticmethod
    def _support_message(status: SupportStatus) -> str:
        return {
            SupportStatus.SUPPORTED: "Retrieved source evidence contains substantial lexical support for the claim; semantic entailment was not tested.",
            SupportStatus.PARTIALLY_SUPPORTED: "Retrieved source evidence overlaps with part of the claim, but does not establish the full statement.",
            SupportStatus.NOT_SUPPORTED: "Retrieved source evidence did not provide sufficient lexical support for the claim.",
            SupportStatus.UNVERIFIABLE: "The available source metadata or content was insufficient to assess support.",
        }[status]

    @staticmethod
    def _aggregate_support(statuses: Iterable[SupportStatus]) -> SupportStatus:
        values = list(statuses)
        if not values or all(status is SupportStatus.UNVERIFIABLE for status in values):
            return SupportStatus.UNVERIFIABLE
        if any(status is SupportStatus.NOT_SUPPORTED for status in values):
            return SupportStatus.NOT_SUPPORTED
        if any(status is SupportStatus.PARTIALLY_SUPPORTED for status in values):
            return SupportStatus.PARTIALLY_SUPPORTED
        return SupportStatus.SUPPORTED

    @classmethod
    def _parse_references(cls, text: str, body_end: int) -> list[ParsedReference]:
        section = text[body_end:]
        lines = [line.strip() for line in section.splitlines() if line.strip()]
        parsed: list[ParsedReference] = []
        for line in lines:
            if cls.REFERENCE_HEADER.fullmatch(line):
                continue
            number = re.match(r"^\[?(\d{1,4})\]?\s*(?:[.)-]\s*)?(.+)$", line)
            key = number.group(1) if number else cls._author_year_key(line)
            raw = number.group(2) if number else line
            year_match = cls.YEAR_RE.search(raw)
            year = int(year_match.group(1)) if year_match else None
            doi_match = cls.DOI_RE.search(raw)
            doi = doi_match.group(1).rstrip(".,;") if doi_match else None
            url_match = cls.URL_RE.search(raw)
            url = url_match.group(0).rstrip(".,;") if url_match else None
            author_text = raw.split(".", 1)[0].strip()
            authors = [author_text] if author_text else []
            title = cls._reference_title(raw, author_text, year, doi, url)
            issues = cls._metadata_issues(authors, title, year, doi, url)
            parsed.append(
                ParsedReference(key, line, authors, title, year, doi, url, None, issues)
            )
        return parsed

    @classmethod
    def _metadata_issues(
        cls,
        authors: Sequence[str],
        title: str | None,
        year: int | None,
        doi: str | None,
        url: str | None,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        if not authors:
            issues.append("missing_authors")
        if not title:
            issues.append("missing_title")
        if year is None and not doi and not url:
            issues.append("missing_year_or_identifier")
        if doi and not DOI_PATTERN.fullmatch(doi):
            issues.append("malformed_doi")
        if url and not re.match(r"^https?://", url, re.IGNORECASE):
            issues.append("malformed_url")
        return tuple(issues)

    @classmethod
    def _reference_title(
        cls,
        raw: str,
        author_text: str,
        year: int | None,
        doi: str | None,
        url: str | None,
    ) -> str | None:
        value = raw
        if author_text:
            value = value[len(author_text) :].lstrip(" .,")
        if year is not None:
            value = re.sub(rf"^\s*\(\s*{year}\s*\)\s*[.\-:]?\s*", "", value, count=1)
            value = re.sub(rf"^\s*{year}\s*[.\-:]?\s*", "", value, count=1)
        if url:
            value = value.replace(url, "")
        if doi:
            value = value.replace(doi, "")
        value = re.sub(r"https?://doi\.org/\s*$", "", value, flags=re.IGNORECASE)
        return value.strip(" .,:;()[]") or None

    @classmethod
    def _author_year_key(cls, raw: str) -> str:
        year_match = cls.YEAR_RE.search(raw)
        year = year_match.group(1) if year_match else "unknown"
        first = re.sub(
            r"[^A-Za-zÀ-ÖØ-öø-ÿ-]", "", raw.split(",", 1)[0].split(".", 1)[0]
        )
        return f"{first.casefold() or 'unknown'}-{year}"

    @classmethod
    def _match_reference(
        cls, key: str, references: Sequence[Reference]
    ) -> Reference | None:
        value = key.strip()
        if re.fullmatch(r"\d+", value):
            return next(
                (
                    reference
                    for reference in references
                    if reference.reference_key == value
                ),
                None,
            )
        year_match = cls.YEAR_RE.search(value)
        year = year_match.group(1) if year_match else None
        surname = re.sub(
            r"[^A-Za-zÀ-ÖØ-öø-ÿ-]", "", value.split(",", 1)[0].split(";", 1)[0]
        ).casefold()
        for reference in references:
            if year and reference.year and str(reference.year) != year:
                continue
            if surname and surname in (reference.raw_text.casefold()):
                return reference
        return None

    @classmethod
    def _source_key(cls, reference: Reference) -> str:
        if reference.doi:
            return f"doi:{reference.doi.casefold()}"
        if reference.url:
            return f"url:{reference.url.casefold()}"
        digest = hashlib.sha256(
            " ".join(reference.raw_text.casefold().split()).encode("utf-8")
        ).hexdigest()
        return f"reference:{digest}"

    @classmethod
    def _inline_matches(cls, body: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for pattern in cls.INLINE_PATTERNS:
            for match in pattern.finditer(body):
                span = (match.start(), match.end())
                if span in seen:
                    continue
                seen.add(span)
                matches.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "raw_text": match.group(0),
                        "key": match.group("key").strip(),
                    }
                )
        return sorted(matches, key=lambda item: (item["start"], item["end"]))

    @classmethod
    def _sentence_spans(cls, body: str) -> list[tuple[int, int, str]]:
        results = []
        for match in re.finditer(r"[^.!?]+(?:[.!?]|$)", body):
            raw = match.group(0)
            left_trimmed = raw.lstrip()
            sentence = left_trimmed.strip()
            if not sentence:
                continue
            start = match.start() + len(raw) - len(raw.lstrip())
            results.append((start, start + len(sentence), sentence))
        return results

    @classmethod
    def _body_end(cls, text: str) -> int:
        header = cls.REFERENCE_HEADER.search(text)
        return header.start() if header else len(text)

    @classmethod
    def _looks_like_claim(cls, sentence: str) -> bool:
        words = re.findall(r"\b\w+\b", sentence)
        return len(words) >= 8 and bool(cls.CLAIM_CUES.search(sentence))

    @staticmethod
    def _claim_for_span(claims: Sequence[Claim], start: int, end: int) -> Claim | None:
        return next(
            (
                claim
                for claim in claims
                if claim.span_start <= start and end <= claim.span_end
            ),
            None,
        )

    @staticmethod
    async def _reference_by_id(
        references: Sequence[Reference], reference_id: str | None
    ) -> Reference | None:
        if not reference_id:
            return None
        return next(
            (
                reference
                for reference in references
                if str(reference.id) == str(reference_id)
            ),
            None,
        )

    @staticmethod
    def _content_terms(text: str) -> set[str]:
        return {word.casefold() for word in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{4,}", text)}

    @staticmethod
    def _reference_metadata(reference: Reference) -> dict[str, Any]:
        return {
            "title": reference.title,
            "authors": reference.authors,
            "publisher": reference.publisher,
            "doi": reference.doi,
            "url": reference.url,
            "year": reference.year,
        }

    @staticmethod
    def _require_lineage(processed: ProcessedDocument) -> None:
        if (
            not processed.organization_id
            or not processed.document_version_id
            or not processed.pipeline_version
        ):
            raise ValueError("Citation analysis requires complete document lineage")

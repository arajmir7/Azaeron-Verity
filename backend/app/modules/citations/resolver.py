"""Source metadata resolver interfaces.

Only DOI metadata is resolved by the default provider. Arbitrary URLs are not
fetched, which avoids SSRF and prevents a page's untrusted content from being
treated as support without an explicit provider.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import hashlib
import json
import re
from typing import Protocol

import httpx
from bs4 import BeautifulSoup
from app.core.config import settings

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedSource:
    title: str | None
    authors: list[str]
    publisher: str | None
    doi: str | None
    url: str | None
    abstract_text: str | None
    retrieval_timestamp: datetime
    payload_hash: str
    provider: str


class SourceResolver(Protocol):
    name: str

    async def resolve(self, doi: str) -> ResolvedSource | None:
        """Return only metadata actually received from the source provider."""


class CrossrefSourceResolver:
    """Resolve DOI metadata through Crossref's fixed HTTPS API host."""

    name = "crossref-doi-metadata-v1"
    endpoint = "https://api.crossref.org/works/"

    async def resolve(self, doi: str) -> ResolvedSource | None:
        normalized_doi = (
            doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        )
        if not DOI_PATTERN.fullmatch(normalized_doi):
            return None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.HEALTHCHECK_TIMEOUT_SECONDS + 3),
                    follow_redirects=False,
                ) as client:
                    response = await client.get(self.endpoint + normalized_doi)
                    if response.status_code == 429 or response.status_code >= 500:
                        response.raise_for_status()
                    response.raise_for_status()
                    payload = response.json()
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 and exc.response.status_code != 429:
                    return None
                if attempt == 2:
                    return None
                await asyncio.sleep(min(2**attempt, 4) * 0.2)
            except (httpx.TimeoutException, httpx.NetworkError, ValueError):
                if attempt == 2:
                    return None
                await asyncio.sleep(min(2**attempt, 4) * 0.2)

        message = payload.get("message") or {}
        authors = []
        for author in message.get("author") or []:
            name = " ".join(
                part for part in (author.get("given"), author.get("family")) if part
            )
            if name:
                authors.append(name)
        abstract = message.get("abstract")
        if abstract:
            abstract = BeautifulSoup(abstract, "html.parser").get_text(" ", strip=True)
        canonical_payload = json.dumps(
            message, sort_keys=True, separators=(",", ":"), default=str
        )
        return ResolvedSource(
            title=(message.get("title") or [None])[0],
            authors=authors,
            publisher=message.get("publisher"),
            doi=message.get("DOI") or normalized_doi,
            url=message.get("URL") or f"https://doi.org/{normalized_doi}",
            abstract_text=abstract,
            retrieval_timestamp=datetime.now(timezone.utc),
            payload_hash=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
            provider=self.name,
        )

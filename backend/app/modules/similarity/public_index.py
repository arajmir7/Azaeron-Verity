"""Offline indexing of operator-supplied, licensed public text snapshots.

No network, crawling, model downloads, tenant documents or request-time indexing.
Rights assertions are prerequisites, not automated legal clearance. Deployment
approval and a production retrieval adapter are separate release gates.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.similarity.corpus import CorpusClass

INDEX_VERSION = "licensed-offline-shingles-1"


class PublicSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corpus: CorpusClass
    url: str = Field(max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=50, max_length=200_000)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    license: str = Field(min_length=1, max_length=1000)
    permission_reference: str = Field(min_length=1, max_length=1000)
    rights_review_reference: str = Field(min_length=1, max_length=1000)
    captured_at: datetime
    index_allowed: bool
    display_passages_allowed: bool
    paywalled: bool = False

    @model_validator(mode="after")
    def rights(self):
        if self.corpus == CorpusClass.PRIVATE_WORKSPACE:
            raise ValueError("Tenant content cannot enter the public index")
        if not self.index_allowed or not self.display_passages_allowed:
            raise ValueError(
                "Documented indexing and passage-display rights are required"
            )
        if self.paywalled and self.corpus != CorpusClass.LICENSED_SCHOLARLY:
            raise ValueError("Paywalled content requires the licensed corpus boundary")
        if hashlib.sha256(self.text.encode()).hexdigest() != self.content_sha256:
            raise ValueError("Source hash mismatch")
        if self.captured_at.tzinfo is None:
            raise ValueError("Capture timestamp must have a timezone")
        canonical_url(self.url)
        return self


def canonical_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an attributed HTTP(S) source URL")
    # Queries remain: removing them could merge distinct documents. No URL is fetched.
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def tokens(text):
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def shingles(text):
    words = tokens(text)
    return set(" ".join(words[i : i + 5]) for i in range(max(0, len(words) - 4)))


def signature(values):
    return [
        min(
            (
                int.from_bytes(
                    hashlib.blake2b(
                        (str(seed) + ":" + value).encode(), digest_size=8
                    ).digest(),
                    "big",
                )
                for value in values
            ),
            default=0,
        )
        for seed in range(32)
    ]


def build_index(bundle: Path, output: Path):
    if output.exists():
        raise ValueError(
            "Create a new immutable index path; never overwrite an existing snapshot"
        )
    if bundle.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Bundle exceeds the offline batch bound")
    sources = [
        PublicSource.model_validate_json(line)
        for line in bundle.read_text().splitlines()
        if line.strip()
    ]
    if not sources or len(sources) > 1000:
        raise ValueError("Use 1 to 1000 reviewed sources per snapshot")
    db = sqlite3.connect(output)
    try:
        db.executescript(
            "CREATE TABLE sources(id TEXT PRIMARY KEY,url TEXT UNIQUE,corpus TEXT,title TEXT,text TEXT,content_hash TEXT UNIQUE,rights TEXT,minhash TEXT); CREATE TABLE terms(term TEXT,source_id TEXT,PRIMARY KEY(term,source_id)); CREATE INDEX term_lookup ON terms(term);"
        )
        inserted = 0
        for source in sorted(sources, key=lambda item: canonical_url(item.url)):
            normalized = " ".join(tokens(source.text))
            digest = hashlib.sha256(normalized.encode()).hexdigest()
            if db.execute(
                "SELECT 1 FROM sources WHERE content_hash=? OR url=?",
                (digest, canonical_url(source.url)),
            ).fetchone():
                continue
            rights = source.model_dump(mode="json", exclude={"text"})
            marks = shingles(source.text)
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)",
                (
                    digest,
                    canonical_url(source.url),
                    source.corpus.value,
                    source.title,
                    source.text,
                    digest,
                    json.dumps(rights, sort_keys=True),
                    json.dumps(signature(marks)),
                ),
            )
            db.executemany(
                "INSERT INTO terms VALUES(?,?)",
                [
                    (hashlib.sha256(mark.encode()).hexdigest(), digest)
                    for mark in sorted(marks)
                ],
            )
            inserted += 1
        db.commit()
    finally:
        db.close()
    output.chmod(0o400)
    return {
        "status": "BUILT_OFFLINE_NOT_DEPLOYED",
        "sources": inserted,
        "pipeline": INDEX_VERSION,
        "input_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "index_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "semantic_retrieval": "UNAVAILABLE",
        "production_approved": False,
    }


def retrieve(index: Path, query: str, limit=10):
    if not 1 <= limit <= 25 or len(query) > 60_000:
        raise ValueError("Bounded retrieval required")
    marks = sorted(
        hashlib.sha256(mark.encode()).hexdigest() for mark in shingles(query)
    )[:500]
    if not marks:
        return []
    db = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT s.url,s.corpus,s.title,s.text,s.rights,count(*) FROM terms t JOIN sources s ON s.id=t.source_id WHERE t.term IN (SELECT value FROM json_each(?)) GROUP BY s.id ORDER BY count(*) DESC,s.id LIMIT ?",
            (json.dumps(marks), limit),
        ).fetchall()
        return [
            {
                "url": url,
                "corpus": corpus,
                "title": title,
                "text": content,
                "rights": json.loads(rights),
                "matched_shingles": count,
                "limitation": "Candidate overlap only; passage alignment and citation review remain required.",
            }
            for url, corpus, title, content, rights, count in rows
        ]
    finally:
        db.close()

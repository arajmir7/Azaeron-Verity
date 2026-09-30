"""Truthful provider states: local embeddings and a future full-text boundary."""

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Protocol, Sequence
from urllib.parse import urlsplit

from app.core.config import settings


class ExternalCorpusProvider(Protocol):
    name: str
    availability: str

    async def retrieve(
        self, *, organization_id: str, text: str, limit: int
    ) -> Sequence[dict]: ...


class UnavailableExternalCorpus:
    name = "authorized-external-full-text"
    availability = "UNAVAILABLE"

    async def retrieve(
        self, *, organization_id: str, text: str, limit: int
    ) -> Sequence[dict]:
        return ()


class LocalEmbeddingProvider:
    """Use a pinned, explicitly installed local asset. Never download at runtime."""

    dimension = 384

    def __init__(self, path: str, *, baseline: bool = False):
        self.model = None
        self.model_id = None
        self.reason = "The configured local embedding asset is unavailable."
        if not baseline or settings.ENVIRONMENT == "production":
            self.reason = "No production-approved embedding model is registered; semantic verification is unavailable."
            return
        folder = Path(path)
        manifest = folder / "verity-model-manifest.json"
        if not manifest.is_file():
            return
        try:
            data = json.loads(manifest.read_text())
            if data["dimension"] != self.dimension:
                raise ValueError("Embedding dimension mismatch")
            for name, expected in data["files"].items():
                target = (folder / name).resolve()
                if (
                    not target.is_relative_to(folder.resolve())
                    or hashlib.sha256(target.read_bytes()).hexdigest() != expected
                ):
                    raise ValueError("Embedding asset fingerprint mismatch")
            import torch
            from sentence_transformers import SentenceTransformer

            torch.set_num_threads(1)
            self.model = SentenceTransformer(
                str(folder.resolve()),
                device="cpu",
                trust_remote_code=False,
                local_files_only=True,
            )
            self.model_id = f"{data['model']}@{data['revision']}"
            self.reason = "Local sentence embeddings are experimental similarity signals, not calibrated match probabilities."
        except Exception as error:
            self.reason = f"Local embedding asset could not be loaded ({type(error).__name__}); semantic verification is unavailable."

    @property
    def available(self) -> bool:
        return self.model is not None

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if self.model is None:
            return []
        vectors = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        ).tolist()
        if any(
            len(v) != self.dimension or not all(math.isfinite(x) for x in v)
            for v in vectors
        ):
            raise ValueError("Embedding provider returned invalid vectors")
        return vectors

    def state(self) -> dict:
        return {
            "provider": "local-sentence-embeddings",
            "state": "EXPERIMENTAL" if self.available else "UNAVAILABLE",
            "model_id": self.model_id,
            "dimension": self.dimension,
            "note": self.reason,
        }


@lru_cache(maxsize=2)
def _embedding_provider(path: str) -> LocalEmbeddingProvider:
    return LocalEmbeddingProvider(path)


def embedding_provider() -> LocalEmbeddingProvider:
    return _embedding_provider(settings.SIMILARITY_MODEL_PATH)


def source_metadata(document, version, processed, retrieved_at: str) -> dict:
    # Metadata is a supplied document record, never inferred from a matching title
    # or author-year citation in a different document.
    try:
        supplied = json.loads(document.metadata_json or "{}")
        if not isinstance(supplied, dict):
            supplied = {}
    except (ValueError, TypeError):
        supplied = {}

    def known(key):
        value = supplied.get(key)
        return (
            value.strip()[:1000] if isinstance(value, str) and value.strip() else None
        )

    url = known("url")
    if url and urlsplit(url).scheme not in ("http", "https"):
        url = None
    return {
        "source_id": str(version.id),
        "title": document.title or document.original_filename,
        "author": known("author"),
        "publisher": known("publisher"),
        "url": url,
        "domain": urlsplit(url).hostname if url else None,
        "doi": known("doi"),
        "source_type": "WORKSPACE_DOCUMENT",
        "retrieved_at": retrieved_at,
        "content_hash": version.sha256_fingerprint,
        "normalized_content_hash": processed.normalized_content_hash,
        "availability": "PRIVATE_WORKSPACE",
        "metadata_basis": "SUPPLIED_DOCUMENT_RECORD",
        "metadata_availability": (
            "PARTIAL"
            if any(known(k) for k in ("author", "publisher", "doi", "url"))
            else "TITLE_ONLY"
        ),
    }

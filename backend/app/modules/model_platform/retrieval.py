"""Bounded document RAG through the approved Azaeron embedding route only."""

import asyncio
import hashlib
import json
import re

from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable


async def document_context(private, identity, question, source):
    model = private.router.route("embed")
    # Unicode code points can occupy four UTF-8 bytes. Never silently truncate.
    size = min(1000, max(1, (model.context_limit - 16) // 4))
    chunks = [
        {
            "start": start,
            "end": min(len(source), start + size),
            "text": source[start : start + size],
        }
        for start in range(0, len(source), size)
    ]
    words = set(re.findall(r"\w+", question.casefold()))
    # At most eight candidate passages reach neural inference; stable offsets
    # break ties and record the resulting, explicitly bounded retrieval scope.
    ranked = sorted(
        chunks,
        key=lambda c: (
            -len(words & set(re.findall(r"\w+", c["text"].casefold()))),
            c["start"],
        ),
    )[:8]

    async def embed(text):
        result = await private.run(
            AzaeronInferenceJob(
                **identity, task="embed", text=text, max_output_tokens=1
            )
        )
        return json.loads(result.output)["embedding"]

    vectors = await asyncio.gather(
        embed(question), *(embed(chunk["text"]) for chunk in ranked)
    )
    query = vectors[0]
    if any(len(v) != len(query) for v in vectors):
        raise InferenceUnavailable("embedding_dimensions_mismatch")
    for chunk, vector in zip(ranked, vectors[1:], strict=True):
        chunk["score"] = sum(a * b for a, b in zip(query, vector, strict=True))
    selected = sorted(
        sorted(ranked, key=lambda c: (-c["score"], c["start"]))[:4],
        key=lambda c: c["start"],
    )
    return "\n\n".join(c["text"] for c in selected), {
        "method": "bounded-lexical-prefilter-azaeron-embed-v1",
        "model_id": model.model_id,
        "model_revision": model.revision,
        "total_chunks": len(chunks),
        "candidates_embedded": len(ranked),
        "limited_coverage": len(selected) < len(chunks),
        "passages": [
            {
                "start": c["start"],
                "end": c["end"],
                "sha256": hashlib.sha256(c["text"].encode()).hexdigest(),
            }
            for c in selected
        ],
    }

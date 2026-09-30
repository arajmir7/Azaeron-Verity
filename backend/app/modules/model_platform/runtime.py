"""Private native runtime. CLI requires verified bundles and client certificates."""

import argparse
import asyncio
import codecs
import json
from pathlib import Path
import ssl

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.modules.inference.registry import AzaeronModelRegistry, verify_artifacts
from .policy import digest, verify_release_files


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern=r"^(system|user)$")
    content: str = Field(max_length=200_000)


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    messages: list[Message] = Field(min_length=2, max_length=2)
    max_tokens: int = Field(ge=1, le=16384)
    temperature: float = Field(ge=0, le=0)
    stream: bool = False
    stream_options: dict | None = None


class SpecialistInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    input: str = Field(min_length=1, max_length=200_000)


def create_runtime(catalog, task, bundle):
    import torch
    from .network import load_network, encode, padded, VERIFIER_LABELS, TOKENIZER
    from .predict import generate, tokens

    record = catalog.select(task)
    verify_artifacts(record, bundle)
    verify_release_files(record, bundle)
    model = load_network(bundle)
    if (
        model.architecture.family != record.lineage.family
        or model.architecture.context != record.context_limit
    ):
        raise ValueError("runtime_architecture_mismatch")
    if digest(bundle / "tokenizer.json") != record.tokenizer_revision:
        raise ValueError("tokenizer_lineage_mismatch")
    if json.loads((bundle / "tokenizer.json").read_bytes()) != TOKENIZER:
        raise ValueError("native_tokenizer_contract_mismatch")
    torch.set_num_threads(1)
    calibration = None
    if record.lineage.family in {"detector", "verifier"}:
        calibration = json.loads((bundle / "calibration.json").read_bytes())
        if (
            calibration["checkpoint_sha256"] != record.lineage.checkpoint_sha256
            or calibration["purpose"] != "PRODUCTION"
        ):
            raise ValueError("calibration_lineage_mismatch")
        if (
            not 0.1 <= calibration["temperature"] <= 10
            or not 0.9 <= calibration["threshold"] <= 1
        ):
            raise ValueError("unsafe_calibration_parameters")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(1)

    @app.get("/health")
    def health():
        return {
            "status": "AVAILABLE",
            "model": record.model_id,
            "revision": record.revision,
        }

    def identity(identifier):
        if identifier != record.model_id:
            raise HTTPException(404, "Model unavailable")

    def vector_or_logits(text):
        with torch.inference_mode():
            tokens = padded([encode(text, record.context_limit)], "cpu")
            return model(tokens)[0], tokens.shape[1]

    @app.post("/v1/chat/completions")
    async def completion(data: Completion):
        identity(data.model)
        if record.lineage.family not in {"writer", "verifier"}:
            raise HTTPException(422, "Wrong specialist route")
        if data.stream:
            if record.lineage.family != "writer":
                raise HTTPException(422, "Only the writer supports token streaming")
            prompt = json.dumps(
                [m.model_dump() for m in data.messages],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            try:
                prompt_count = len(encode(prompt, record.context_limit))
                if prompt_count + data.max_tokens > record.context_limit:
                    raise ValueError("context_limit")
            except ValueError:
                raise HTTPException(422, "Invalid inference input") from None

            async def stream():
                async with slots:
                    decoder = codecs.getincrementaldecoder("utf-8")("replace")
                    count, last = 0, None
                    for token in tokens(model, prompt, max_tokens=data.max_tokens):
                        count, last = count + 1, token
                        content = (
                            decoder.decode(bytes([token - 4]))
                            if token >= 4
                            else decoder.decode(b"", final=True)
                        )
                        if content:
                            yield "data: " + json.dumps(
                                {
                                    "model": record.model_id,
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {"content": content},
                                            "finish_reason": None,
                                        }
                                    ],
                                }
                            ) + "\n\n"
                        await asyncio.sleep(0)
                    yield "data: " + json.dumps(
                        {
                            "model": record.model_id,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop" if last == 2 else "length",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": prompt_count,
                                "completion_tokens": count,
                            },
                        }
                    ) + "\n\n"
                    yield "data: [DONE]\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")
        async with slots:
            try:
                if record.lineage.family == "writer":
                    prompt = json.dumps(
                        [m.model_dump() for m in data.messages],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    result = await asyncio.to_thread(
                        generate, model, prompt, max_tokens=data.max_tokens
                    )
                else:
                    if calibration is None:
                        raise HTTPException(503, "Calibration unavailable")
                    logits, count = vector_or_logits(data.messages[-1].content)
                    probabilities = (logits / calibration["temperature"]).softmax(-1)
                    label = VERIFIER_LABELS[int(probabilities.argmax())]
                    uncertain = (
                        float(probabilities.max()) < calibration["threshold"]
                        or label == "uncertain"
                    )
                    result = {
                        "text": json.dumps(
                            {
                                "equivalent": label == "equivalent" and not uncertain,
                                "contradiction": label == "contradiction",
                                "unsupported_additions": label == "unsupported",
                                "uncertain": uncertain,
                            }
                        ),
                        "prompt_tokens": count,
                        "completion_tokens": 0,
                        "finish_reason": "stop",
                    }
            except ValueError:
                raise HTTPException(422, "Invalid inference input") from None
        return {
            "model": record.model_id,
            "choices": [
                {
                    "finish_reason": result["finish_reason"],
                    "message": {"content": result["text"]},
                }
            ],
            "usage": {k: result[k] for k in ["prompt_tokens", "completion_tokens"]},
        }

    async def specialist(data, family):
        identity(data.model)
        if record.lineage.family != family:
            raise HTTPException(422, "Wrong specialist route")
        async with slots:
            try:
                values, count = vector_or_logits(data.input)
            except ValueError:
                raise HTTPException(422, "Invalid inference input") from None
        if family == "embed":
            result = {"embedding": values.tolist()}
        else:
            if calibration is None:
                raise HTTPException(503, "Calibration unavailable")
            probabilities = (values / calibration["temperature"]).softmax(-1).tolist()
            abstained = (
                max(probabilities) < calibration["threshold"]
                or len(data.input.split()) < 50
            )
            result = {
                "label": (
                    "INDETERMINATE"
                    if abstained
                    else ["human", "ai", "mixed"][
                        max(range(3), key=probabilities.__getitem__)
                    ]
                ),
                "probabilities": probabilities,
                "abstained": abstained,
                "checkpoint_sha256": record.lineage.checkpoint_sha256,
                "calibration_sha256": digest(bundle / "calibration.json"),
                "limitations": [
                    "Statistical evidence does not establish authorship. Uncertain and short inputs abstain; domain shift remains a limitation."
                ],
            }
        return {
            "model": record.model_id,
            "revision": record.revision,
            "result": result,
            "usage": {"prompt_tokens": count, "completion_tokens": 0},
        }

    @app.post("/v1/embeddings")
    async def embeddings(data: SpecialistInput):
        return await specialist(data, "embed")

    @app.post("/v1/classifications")
    async def classifications(data: SpecialistInput):
        return await specialist(data, "detector")

    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["registry", "bundle", "cert", "key", "ca"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_runtime(
        AzaeronModelRegistry.load(args.registry), args.task, args.bundle
    )
    # Intended for an internal Docker/Kubernetes network; certificates are mandatory.
    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104 -- private deployment; mandatory client TLS
        port=args.port,
        ssl_certfile=str(args.cert),
        ssl_keyfile=str(args.key),
        ssl_ca_certs=str(args.ca),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        access_log=False,
        log_level="warning",
        limit_concurrency=8,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()

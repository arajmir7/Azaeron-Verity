"""Explicitly unapproved localhost MLX transport for development only."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.modules.inference.gateway import (
    AzaeronInferenceJob,
    AzaeronInferenceResult,
    RuntimeUsage,
    TASK_INSTRUCTIONS,
)
from app.modules.inference.registry import InferenceUnavailable

MODEL_ID = "Qwen/Qwen3-4B-MLX-4bit"
PROMPT_VERSION = "dev-mlx-qwen3-no-thinking-1"
_SLOTS = asyncio.Semaphore(1)  # Shared across requests on a 16 GB development host.


class _Visible:
    """Drop reasoning fields and split <think> blocks before emitting any delta."""

    def __init__(self):
        self.pending = ""
        self.inside = False

    def feed(self, chunk: str, *, final: bool = False) -> str:
        self.pending += chunk
        output = ""
        while self.pending:
            if self.inside:
                end = self.pending.find("</think>")
                if end < 0:
                    self.pending = self.pending[-7:]
                    break
                self.pending = self.pending[end + len("</think>") :]
                self.inside = False
            else:
                start = self.pending.find("<think>")
                if start >= 0:
                    output += self.pending[:start]
                    self.pending = self.pending[start + len("<think>") :]
                    self.inside = True
                elif final:
                    output += self.pending
                    self.pending = ""
                elif len(self.pending) > len("<think>") - 1:
                    emit = len(self.pending) - (len("<think>") - 1)
                    output += self.pending[:emit]
                    self.pending = self.pending[emit:]
                else:
                    break
        return output


class DevMlxGateway:
    dev_only = True

    def __init__(
        self,
        endpoint: str,
        *,
        model_id: str = MODEL_ID,
        timeout: float = 90,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if (
            endpoint.rstrip("/")
            not in {
                "http://127.0.0.1:8080",
                "http://host.docker.internal:8080",
            }
            or model_id != MODEL_ID
        ):
            raise InferenceUnavailable("dev_runtime_endpoint_forbidden")
        self.endpoint = endpoint.rstrip("/")
        self.model_id = model_id
        self.timeout = timeout
        self.transport = transport

    def _identity_present(self, body: object) -> bool:
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            return False
        return any(
            isinstance(item, dict) and item.get("id") == self.model_id
            for item in body["data"]
        )

    async def health(self) -> dict[str, str]:
        try:
            if urlsplit(self.endpoint).hostname == "host.docker.internal":
                from app.modules.inference.gateway import resolve_private

                await resolve_private("host.docker.internal", 8080)
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=2,
                transport=self.transport,
            ) as client:
                response = await client.get(self.endpoint + "/v1/models")
                if response.status_code == 200 and self._identity_present(
                    response.json()
                ):
                    return {"status": "AVAILABLE"}
        except (InferenceUnavailable, httpx.HTTPError, ValueError, TypeError):
            pass
        return {"status": "UNAVAILABLE"}

    async def run(
        self,
        job: AzaeronInferenceJob,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> AzaeronInferenceResult:
        if job.task not in {"chat", "summarize", "refine"}:
            raise InferenceUnavailable("dev_task_unavailable")
        if len(job.text.encode()) > 16_000 or job.max_output_tokens > 2048:
            raise InferenceUnavailable("dev_request_limit")
        started = time.monotonic()
        instructions = TASK_INSTRUCTIONS[job.task]
        if job.task == "refine":
            instructions += (
                " Preserve every protected fact and return only the edited text."
            )
            instructions += " Focus: " + job.focus + "."
            if job.voice_style:
                instructions += (
                    " Approved style statistics: " + job.voice_style.model_dump_json()
                )
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": job.text},
            ],
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0,
            "max_tokens": job.max_output_tokens,
            "stream": on_delta is not None,
        }
        if on_delta is not None:
            payload["stream_options"] = {"include_usage": True}
        try:
            async with asyncio.timeout(self.timeout):
                async with _SLOTS:
                    async with httpx.AsyncClient(
                        trust_env=False,
                        follow_redirects=False,
                        timeout=self.timeout,
                        transport=self.transport,
                    ) as client:
                        if urlsplit(self.endpoint).hostname == "host.docker.internal":
                            from app.modules.inference.gateway import resolve_private

                            await resolve_private("host.docker.internal", 8080)
                        # Identity is checked on each call; a substituted local server fails closed.
                        models = await client.get(self.endpoint + "/v1/models")
                        models.raise_for_status()
                        if not self._identity_present(models.json()):
                            raise InferenceUnavailable("dev_model_identity_mismatch")
                        async with client.stream(
                            "POST",
                            self.endpoint + "/v1/chat/completions",
                            json=payload,
                            headers={"X-Request-ID": str(job.operation_id)},
                        ) as response:
                            if response.status_code != 200:
                                raise InferenceUnavailable("dev_runtime_failed")
                            if on_delta is None:
                                raw = await response.aread()
                                if len(raw) > 262_144:
                                    raise InferenceUnavailable("dev_output_too_large")
                                body = json.loads(raw)
                                if (
                                    body.get("model") != self.model_id
                                    or len(body["choices"]) != 1
                                ):
                                    raise ValueError("model identity")
                                choice = body["choices"][0]
                                message = choice["message"]
                                if message.get("tool_calls") or message.get(
                                    "function_call"
                                ):
                                    raise ValueError("tool output")
                                visible = _Visible()
                                output = visible.feed(
                                    message.get("content") or "", final=True
                                )
                                if visible.inside:
                                    raise ValueError("unfinished reasoning block")
                                usage = body["usage"]
                                finish = choice["finish_reason"]
                            else:
                                output, usage, finish = await self._stream(
                                    response, on_delta
                                )
            tokens = RuntimeUsage.model_validate(usage)
            if (
                finish != "stop"
                or not output.strip()
                or len(output) > 32_000
                or tokens.completion_tokens > job.max_output_tokens
                or tokens.prompt_tokens > 16_000
            ):
                raise ValueError("invalid completion")
            result = AzaeronInferenceResult(
                operation_id=job.operation_id,
                model_id=self.model_id,
                model_revision="DEV_ONLY_UNATTESTED_RUNTIME",
                prompt_version=PROMPT_VERSION + ":" + job.task,
                input_sha256=hashlib.sha256(job.text.encode()).hexdigest(),
                output=output,
                input_tokens=tokens.prompt_tokens,
                output_tokens=tokens.completion_tokens,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            from app.modules.billing.usage import record_model_call

            record_model_call(result)
            return result
        except (TimeoutError, httpx.TimeoutException):
            raise InferenceUnavailable("dev_runtime_timeout") from None
        except (httpx.HTTPError, OSError):
            raise InferenceUnavailable("dev_runtime_unavailable") from None
        except (
            ValueError,
            KeyError,
            TypeError,
            IndexError,
            AttributeError,
            ValidationError,
        ):
            raise InferenceUnavailable("dev_runtime_invalid_output") from None

    async def _stream(self, response, on_delta):
        total = 0
        output = ""
        usage = None
        finish = None
        done = False
        visible = _Visible()
        async for line in response.aiter_lines():
            total += len(line.encode())
            if total > 262_144:
                raise InferenceUnavailable("dev_output_too_large")
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: ") or done:
                raise ValueError("invalid stream")
            frame = line[6:]
            if frame == "[DONE]":
                done = True
                continue
            item = json.loads(frame)
            if item.get("model") != self.model_id:
                raise ValueError("model identity")
            if item.get("usage") is not None:
                if usage is not None:
                    raise ValueError("duplicate usage")
                usage = item["usage"]
            choices = item.get("choices", [])
            if len(choices) > 1:
                raise ValueError("multiple choices")
            if choices:
                choice = choices[0]
                delta = choice.get("delta", {})
                if (
                    finish is not None
                    or choice.get("index") != 0
                    or delta.get("tool_calls")
                    or delta.get("function_call")
                ):
                    raise ValueError("invalid delta")
                content = delta.get("content") or ""
                if not isinstance(content, str):
                    raise ValueError("invalid content")
                safe = visible.feed(content)
                if safe:
                    output += safe
                    if len(output) > 32_000:
                        raise ValueError("output limit")
                    await on_delta(safe)
                if choice.get("finish_reason") is not None:
                    finish = choice["finish_reason"]
        tail = visible.feed("", final=True)
        if visible.inside:
            raise ValueError("unfinished reasoning block")
        if tail:
            output += tail
            await on_delta(tail)
        if not done or usage is None or finish is None:
            raise ValueError("incomplete stream")
        return output, usage, finish

"""Bounded native inference; no hosted service, tools, downloads or retries."""

import torch

from .network import encode, decode, padded


def tokens(model, prompt, *, max_tokens=256):
    context = model.architecture.context
    values = encode(prompt, context)[:-1] + [3]
    if max_tokens < 1 or len(values) + max_tokens > context:
        raise ValueError("context_limit")
    for _ in range(max_tokens):
        with torch.inference_mode():
            logits = model(padded([values], next(model.parameters()).device))[0, -1]
            logits[[0, 1, 3]] = -torch.inf
            token = int(logits.argmax())
        values.append(token)
        yield token
        if token == 2:
            break


def generate(model, prompt, *, max_tokens=256):
    output = list(tokens(model, prompt, max_tokens=max_tokens))
    return {
        "text": decode(output),
        "prompt_tokens": len(encode(prompt, model.architecture.context)),
        "completion_tokens": len(output),
        "finish_reason": "stop" if output[-1] == 2 else "length",
    }

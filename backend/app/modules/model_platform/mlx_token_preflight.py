"""Run in the pinned MLX environment to reject examples MLX-LM would truncate."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from transformers import AutoTokenizer  # type: ignore[import-not-found]  # separate MLX environment


def check(model: Path, data: Path, maximum: int):
    tokenizer = AutoTokenizer.from_pretrained(
        model,
        revision="1cfa9a7208912126459214e8b04321603b3df60c",
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    for split in ("train", "valid"):
        rows = (data / f"{split}.jsonl").read_text().splitlines()
        if not rows:
            raise ValueError("empty_mlx_training_split")
        for row in rows:
            value = json.loads(row)
            messages = [
                {"role": "user", "content": value["prompt"]},
                {"role": "assistant", "content": value["completion"]},
            ]
            tokens = tokenizer.apply_chat_template(messages, return_dict=False)
            prompt = tokenizer.apply_chat_template(
                messages[:-1], add_generation_prompt=True, return_dict=False
            )
            if (
                len(tokens) > maximum
                or len(prompt) >= len(tokens) - 1
                or tokens[: len(prompt)] != prompt
            ):
                raise ValueError("mlx_training_example_overflow_or_empty_target")


if __name__ == "__main__":
    check(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))

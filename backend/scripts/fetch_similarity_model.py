"""Fetch the already configured MiniLM embedding asset at an immutable revision.

Explicit build/setup step only. No runtime model downloads or remote code.
"""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FILES = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "1_Pooling/config.json",
    "model.safetensors",
    "README.md",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default="model_assets/all-MiniLM-L6-v2")
    args = parser.parse_args()
    destination = Path(args.destination)
    hashes = {}
    for name in FILES:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(
            f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}", timeout=120
        ) as response:
            data = response.read()
        path.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
        print(f"{name}: {len(data)} bytes", flush=True)
    (destination / "verity-model-manifest.json").write_text(
        json.dumps(
            {
                "model": MODEL,
                "revision": REVISION,
                "dimension": 384,
                "source": f"https://huggingface.co/{MODEL}/tree/{REVISION}",
                "files": hashes,
                "purpose": "similarity embeddings; not an AI-writing detector",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

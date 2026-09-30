"""Original byte-token Transformer family. Optional isolated PyTorch dependency.

These architectures make no pretrained-quality claim. Four independently trained
checkpoints are required; a writer cannot act as its own verifier or detector.
"""

from dataclasses import asdict, dataclass
import json

import torch
from torch import nn
from torch.nn import functional as F

TOKENIZER = {
    "name": "azaeron-byte-v1",
    "vocab_size": 260,
    "pad": 0,
    "bos": 1,
    "eos": 2,
    "separator": 3,
    "byte_offset": 4,
}
VERIFIER_LABELS = ["equivalent", "contradiction", "unsupported", "uncertain"]
DETECTOR_LABELS = ["human", "ai", "mixed"]


@dataclass(frozen=True)
class Architecture:
    family: str
    width: int = 256
    heads: int = 8
    layers: int = 4
    context: int = 1024
    embedding_size: int = 128

    def validate(self):
        if self.family not in {"writer", "verifier", "detector", "embed"}:
            raise ValueError("unknown_family")
        if (
            not 16 <= self.width <= 4096
            or self.width % self.heads
            or not 1 <= self.heads <= 32
        ):
            raise ValueError("invalid_attention_dimensions")
        if (
            not 1 <= self.layers <= 48
            or not 32 <= self.context <= 32768
            or not 8 <= self.embedding_size <= self.width
        ):
            raise ValueError("invalid_architecture")


def encode(text, limit):
    raw = text.encode("utf-8")
    if len(raw) + 2 > limit:
        raise ValueError("context_overflow_no_silent_truncation")
    return [1, *[b + 4 for b in raw], 2]


def decode(values):
    return bytes(v - 4 for v in values if 4 <= v < 260).decode(
        "utf-8", errors="replace"
    )


def padded(rows, device):
    values = torch.zeros(
        (len(rows), max(map(len, rows))), dtype=torch.long, device=device
    )
    for i, row in enumerate(rows):
        values[i, : len(row)] = torch.tensor(row, device=device)
    return values


class FamilyNetwork(nn.Module):
    def __init__(self, architecture: Architecture):
        super().__init__()
        architecture.validate()
        self.architecture = architecture
        self.tokens = nn.Embedding(260, architecture.width, padding_idx=0)
        self.positions = nn.Embedding(architecture.context, architecture.width)
        layer = nn.TransformerEncoderLayer(
            architecture.width,
            architecture.heads,
            architecture.width * 4,
            dropout=0,
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            layer, architecture.layers, enable_nested_tensor=False
        )
        self.norm = nn.LayerNorm(architecture.width)
        output = {
            "writer": 260,
            "verifier": 4,
            "detector": 3,
            "embed": architecture.embedding_size,
        }[architecture.family]
        self.head = nn.Linear(architecture.width, output)

    def forward(self, tokens):
        length = tokens.shape[1]
        if length > self.architecture.context:
            raise ValueError("context_overflow")
        positions = torch.arange(length, device=tokens.device)
        hidden = self.tokens(tokens) + self.positions(positions)
        causal = self.architecture.family == "writer"
        mask = (
            torch.ones(length, length, dtype=torch.bool, device=tokens.device).triu(1)
            if causal
            else None
        )
        hidden = self.norm(
            self.encoder(
                hidden, mask=mask, src_key_padding_mask=tokens.eq(0), is_causal=causal
            )
        )
        if causal:
            return self.head(hidden)
        valid = tokens.ne(0).unsqueeze(-1)
        pooled = (hidden * valid).sum(1) / valid.sum(1).clamp_min(1)
        output = self.head(pooled)
        return (
            F.normalize(output, dim=-1)
            if self.architecture.family == "embed"
            else output
        )


def training_loss(model, rows, device):
    family, context = model.architecture.family, model.architecture.context
    if family == "writer":
        sequences, writer_labels = [], []
        for row in rows:
            prompt = encode(row["input"], context)[:-1] + [3]
            answer = encode(row["target"], context)[1:]
            sequence = prompt + answer
            if len(sequence) > context:
                raise ValueError("context_overflow_no_silent_truncation")
            sequences.append(sequence[:-1])
            writer_labels.append([-100] * (len(prompt) - 1) + answer)
        tokens = padded(sequences, device)
        targets = torch.full_like(tokens, -100)
        for i, values in enumerate(writer_labels):
            targets[i, : len(values)] = torch.tensor(values, device=device)
        return F.cross_entropy(
            model(tokens).flatten(0, 1), targets.flatten(), ignore_index=-100
        )
    tokens = padded([encode(row["input"], context) for row in rows], device)
    if family in {"verifier", "detector"}:
        class_labels = VERIFIER_LABELS if family == "verifier" else DETECTOR_LABELS
        targets = torch.tensor(
            [class_labels.index(row["target"]) for row in rows], device=device
        )
        return F.cross_entropy(model(tokens), targets)
    if len(rows) < 2 or len({row["target"] for row in rows}) != len(rows):
        raise ValueError("contrastive_batch_requires_distinct_positives")
    positives = padded([encode(row["target"], context) for row in rows], device)
    scores = model(tokens) @ model(positives).T / 0.07
    pair_labels = torch.arange(len(rows), device=device)
    return (
        F.cross_entropy(scores, pair_labels) + F.cross_entropy(scores.T, pair_labels)
    ) / 2


def load_network(root, device="cpu"):
    from safetensors.torch import load_file

    architecture = Architecture(**json.loads((root / "architecture.json").read_text()))
    model = FamilyNetwork(architecture).to(device)
    model.load_state_dict(
        load_file(str(root / "checkpoint.safetensors"), device=device), strict=True
    )
    model.eval()
    return model

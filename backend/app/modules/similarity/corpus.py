"""Corpus classes describe actual coverage, never imply a web-wide index."""

from enum import Enum
from dataclasses import dataclass, asdict


class CorpusClass(str, Enum):
    PRIVATE_WORKSPACE = "PRIVATE_WORKSPACE"
    PUBLIC_WEB = "PUBLIC_WEB"
    OPEN_SCHOLARLY = "OPEN_SCHOLARLY"
    LICENSED_SCHOLARLY = "LICENSED_SCHOLARLY"


@dataclass(frozen=True)
class CorpusCoverage:
    corpus: CorpusClass
    state: str
    description: str
    index_revision: str | None = None


def coverage():
    return [
        asdict(
            CorpusCoverage(
                kind,
                "AVAILABLE" if kind == CorpusClass.PRIVATE_WORKSPACE else "UNAVAILABLE",
                (
                    "Authorized workspace sources only."
                    if kind == CorpusClass.PRIVATE_WORKSPACE
                    else "No licensed, reviewed corpus snapshot is deployed."
                ),
            )
        )
        for kind in CorpusClass
    ]

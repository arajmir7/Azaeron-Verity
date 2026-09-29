"""Closed tool schemas. Tool choice comes from an authenticated user request."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attachment(Strict):
    document_id: UUID
    document_version_id: UUID


class SearchTool(Strict):
    name: Literal["document.search"]
    query: str = Field(min_length=1, max_length=200)


class ReadTool(Attachment):
    name: Literal[
        "document.read",
        "document.summarize",
        "detection.analyze",
        "similarity.analyze",
        "citation.inspect",
    ]


class CompareTool(Attachment):
    name: Literal["document.compare"]
    other: Attachment


class RefineTool(Attachment):
    name: Literal["writing.refine"]
    locked_spans: list[tuple[int, int]] = Field(default_factory=list, max_length=1000)
    focus: Literal["clarity", "shorten", "expand", "simplify", "humanise"] = "clarity"
    selection: tuple[int, int] | None = None
    voice_profile_id: UUID | None = None


class ResolveTool(Attachment):
    name: Literal["similarity.resolve"]
    match_id: UUID
    action: Literal[
        "add_citation",
        "quote_and_cite",
        "paraphrase_with_attribution",
        "remove_duplicate",
        "keep_legitimate",
    ]
    citation: str = Field(default="", max_length=2000)
    rationale: str = Field(min_length=1, max_length=1000)


class VersionTool(Attachment):
    name: Literal["document.create_version"]
    # Only an already persisted assistant message can be proposed for saving.
    message_id: UUID


Tool = Annotated[
    SearchTool | ReadTool | CompareTool | RefineTool | ResolveTool | VersionTool,
    Field(discriminator="name"),
]


class ConversationCreate(Strict):
    title: str = Field(
        default="New conversation",
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00-\x1f]+$",
    )


class MessageCreate(Strict):
    operation_id: UUID
    content: str = Field(min_length=1, max_length=8000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=8)
    tool: Tool | None = None
    replaces_message_id: UUID | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.content.strip():
            raise ValueError("Enter a message")
        return self


class ReceiptDecision(Strict):
    decision: Literal["ACCEPTED", "REJECTED"]
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class VoiceCreate(Strict):
    name: str = Field(min_length=1, max_length=100)
    samples: list[Attachment] = Field(min_length=1, max_length=5)
    approved: Literal[True]

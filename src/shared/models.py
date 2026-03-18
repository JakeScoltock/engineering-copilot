"""Shared Pydantic models used across ingestion and query pipelines."""

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A loaded document with its raw content and source metadata."""

    source: str = Field(description="File name of the source document.")
    content: str = Field(description="Full raw text content of the document.")


class DocumentChunk(BaseModel):
    """A chunk of a document, carrying enough metadata for source attribution."""

    source: str = Field(description="Repo-relative file path of the source document.")
    chunk_index: int = Field(description="Zero-based index of this chunk within its source document.")
    text: str = Field(description="Chunk text, prefixed with '# File: <source>' header.")
    line_count: int = Field(description="Number of source lines in this chunk (excluding header).")
    start_line: int = Field(description="Zero-based index of the first source line in this chunk.")
    end_line: int = Field(description="Zero-based index (exclusive) of the last source line in this chunk.")
    language: str = ""


class IngestionStatus(str, Enum):
    """Lifecycle states for a repo ingestion job."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class RepoJob(BaseModel):
    """Tracks the state of a repo ingestion job stored in DynamoDB."""

    repo_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    github_url: str
    status: IngestionStatus = IngestionStatus.PENDING
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceRef(BaseModel):
    """A reference to the source chunk that contributed to an answer."""

    file: str = Field(description="Repo-relative file path of the source chunk.")
    chunk_index: int = Field(description="Zero-based chunk index within that file.")


class QueryRequest(BaseModel):
    """Body for POST /repos/{repo_id}/query."""

    question: str = Field(description="Natural-language question about the repo.")


class QueryResponse(BaseModel):
    """Response from POST /repos/{repo_id}/query."""

    answer: str = Field(description="Claude's answer, grounded in the retrieved chunks.")
    sources: list[SourceRef] = Field(description="Chunks used to produce the answer.")

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class TextImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=2, max_length=2_000_000)
    campus_id: str | None = None
    publisher: str = Field(default="", max_length=255)


class UrlImportRequest(BaseModel):
    url: HttpUrl
    campus_id: str | None = None
    publisher: str = Field(default="", max_length=255)


class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(private|pending|approved|rejected)$")
    verification_method: str = Field(min_length=2, max_length=100)
    verified_fields: list[str] = Field(min_length=1, max_length=50)
    evidence: str = Field(default="", max_length=5000)
    note: str = Field(default="", max_length=5000)
    confirmed: bool = False


class KnowledgeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campus_id: str | None
    title: str
    publisher: str
    url: str
    visibility: str
    review_status: str
    source_type: str
    original_filename: str
    content_hash: str
    chunk_count: int
    extracted_metadata: dict = Field(default_factory=dict)
    data_status: str
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceDetail(KnowledgeSourceRead):
    content: str


class ImportResult(BaseModel):
    job_id: str
    imported: int
    duplicates: int
    failed: int
    document_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class KnowledgeSearchResult(BaseModel):
    document_id: str
    title: str
    snippet: str
    score: float
    publisher: str
    url: str
    visibility: str
    source_type: str
    created_at: datetime


class ReindexResult(BaseModel):
    indexed_documents: int

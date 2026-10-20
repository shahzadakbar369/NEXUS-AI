"""Pydantic request/response models for the REST API."""
from typing import Literal

# pyrefly: ignore[missing-import]
from pydantic import BaseModel, Field, field_validator


class ChatCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    use_documents: bool | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("title must not be blank")
        return v.strip() if v else v


class Chat(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    use_documents: bool
    has_summary: bool = False


class Source(BaseModel):
    n: int
    document_id: str
    filename: str
    page: int
    score: float
    text: str


class Message(BaseModel):
    id: int
    chat_id: str
    role: Literal["user", "assistant"]
    content: str
    status: str
    sources: list[Source] = []
    context_info: dict = {}
    created_at: str


class Document(BaseModel):
    id: str
    chat_id: str
    filename: str
    kind: str
    size_bytes: int
    status: Literal["processing", "ready", "failed"]
    error: str
    pages: int
    chunks: int
    created_at: str


class ChatDetail(Chat):
    messages: list[Message]
    documents: list[Document]


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=32_000)
    regenerate: bool = False

    @field_validator("content")
    @classmethod
    def not_blank_unless_regenerate(cls, v: str, info) -> str:  # noqa: ANN001
        return v.strip()

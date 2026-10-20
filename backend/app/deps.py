"""Wires the services together. Routes get them through FastAPI dependencies,
which lets tests swap in a temporary database and a fake LLM."""
from __future__ import annotations

from dataclasses import dataclass

# pyrefly: ignore[missing-import]
from fastapi import Request

from app.config import Settings
from app.db import Database
from app.services.chat_service import ChatService
from app.services.embeddings import EmbeddingService
from app.services.groq_client import GroqClient
from app.services.vector_store import VectorStore


@dataclass
class Container:
    settings: Settings
    db: Database
    llm: GroqClient
    embedder: EmbeddingService
    store: VectorStore
    chat: ChatService


def build_container(settings: Settings, llm: GroqClient | None = None, embedder: EmbeddingService | None = None) -> Container:
    for d in (settings.data_dir, settings.uploads_dir, settings.index_dir):
        d.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    llm = llm or GroqClient(settings)
    embedder = embedder or EmbeddingService(settings.embedding_model)
    store = VectorStore(settings.index_dir, embedder)
    return Container(settings, db, llm, embedder, store, ChatService(settings, db, llm, store))


def get_container(request: Request) -> Container:
    return request.app.state.container

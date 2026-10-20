"""Shared fixtures: temp data dir, fake LLM (no Groq key needed), fake embedder (no model download)."""
import re
import zlib

# pyrefly: ignore[missing-import]
import numpy as np
# pyrefly: ignore[missing-import]
import pytest
# pyrefly: ignore[missing-import]
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import build_container
from app.main import create_app
from app.services.groq_client import LLMError


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder; similar texts share words -> high cosine."""
    model_name = "fake"
    loaded = True

    def embed(self, texts):
        out = np.zeros((len(texts), 256), dtype="float32")
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z]{3,}", t.lower()):
                out[i, zlib.crc32(w.encode()) % 256] += 1
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return out / norms


class FakeLLM:
    configured = True

    def __init__(self):
        self.calls: list[list[dict]] = []
        self.fail: LLMError | None = None

    async def list_models(self):
        return ["test-model"]

    async def complete(self, messages, max_tokens):
        self.calls.append(messages)
        return "summary of older turns"

    async def stream(self, messages, max_tokens):
        self.calls.append(messages)
        if self.fail:
            raise self.fail
        for t in ["Hello", " from", " fake"]:
            yield t


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, groq_api_key="x", groq_model="test-model", data_dir=tmp_path, max_upload_mb=1)


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(settings, fake_llm):
    container = build_container(settings, llm=fake_llm, embedder=FakeEmbedder())
    app = create_app(settings, container)
    with TestClient(app) as c:
        c.container = container
        yield c

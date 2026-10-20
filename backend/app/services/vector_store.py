"""Persistent per-document vector indexes (FAISS) and semantic retrieval.

Layout on disk:  data/indexes/<document_id>/vectors.npy  +  chunks.json
(the embeddings are persisted; an exact FAISS IndexFlatIP is rebuilt in memory
from them on first use, which takes milliseconds and avoids FAISS file-format
coupling).
Each document is embedded exactly once at upload time. At question time we embed
only the question and search the indexes of the chat's ready documents, so
documents are never re-embedded and are only searchable inside their own chat.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
from pathlib import Path

import numpy as np

from app.services.embeddings import EmbeddingService

log = logging.getLogger(__name__)

try:
    import faiss  # type: ignore

    HAS_FAISS = True
except ImportError:  # pragma: no cover - documented fallback
    faiss = None
    HAS_FAISS = False
    log.warning("faiss not installed; using exact NumPy search instead (same results, fine for small corpora).")


class _DocIndex:
    def __init__(self, vectors: np.ndarray, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.vectors = vectors
        self.faiss_index = None
        if HAS_FAISS:
            self.faiss_index = faiss.IndexFlatIP(vectors.shape[1])
            self.faiss_index.add(vectors)

    def search(self, q: np.ndarray, k: int) -> list[tuple[float, dict]]:
        k = min(k, len(self.chunks))
        if self.faiss_index is not None:
            scores, ids = self.faiss_index.search(q.reshape(1, -1), k)
            pairs = zip(scores[0].tolist(), ids[0].tolist())
        else:
            sims = self.vectors @ q
            top = np.argsort(-sims)[:k]
            pairs = ((float(sims[i]), int(i)) for i in top)
        return [(s, self.chunks[i]) for s, i in pairs if i >= 0]


class VectorStore:
    def __init__(self, root: Path, embedder: EmbeddingService) -> None:
        self.root = root
        self.embedder = embedder
        self._cache: dict[str, _DocIndex] = {}
        self._lock = threading.Lock()
        root.mkdir(parents=True, exist_ok=True)

    def _dir(self, doc_id: str) -> Path:
        if not doc_id.isalnum():  # doc ids are uuid hex; guards against path tricks
            raise ValueError("invalid document id")
        return self.root / doc_id

    def add_document(self, doc_id: str, filename: str, chunks: list[dict]) -> int:
        texts = [c["text"] for c in chunks]
        vectors = self.embedder.embed(texts)
        meta = [{"document_id": doc_id, "filename": filename, "page": c["page"], "chunk": i, "text": c["text"]}
                for i, c in enumerate(chunks)]
        d = self._dir(doc_id)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / "vectors.npy", vectors)
        (d / "chunks.json").write_text(json.dumps(meta), encoding="utf-8")
        with self._lock:
            self._cache[doc_id] = _DocIndex(vectors, meta)
        return len(meta)

    def _load(self, doc_id: str) -> _DocIndex | None:
        with self._lock:
            if doc_id in self._cache:
                return self._cache[doc_id]
        d = self._dir(doc_id)
        if not (d / "vectors.npy").exists():
            return None
        idx = _DocIndex(np.load(d / "vectors.npy"), json.loads((d / "chunks.json").read_text(encoding="utf-8")))
        with self._lock:
            self._cache[doc_id] = idx
        return idx

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            self._cache.pop(doc_id, None)
        shutil.rmtree(self._dir(doc_id), ignore_errors=True)

    def search(self, query: str, doc_ids: list[str], top_k: int, min_score: float) -> list[dict]:
        """Top-k chunks across the given documents with cosine similarity >= min_score."""
        if not doc_ids:
            return []
        q = self.embedder.embed([query])[0]
        results: list[tuple[float, dict]] = []
        for did in doc_ids:
            idx = self._load(did)
            if idx:
                results.extend(idx.search(q, top_k))
        results.sort(key=lambda r: r[0], reverse=True)
        return [{**c, "score": round(s, 4)} for s, c in results[:top_k] if s >= min_score]

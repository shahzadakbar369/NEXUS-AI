"""Local sentence-transformers embeddings (loaded lazily, once per process)."""
from __future__ import annotations

import logging
import threading

# pyrefly: ignore[missing-import]
import numpy as np

log = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                # pyrefly: ignore[missing-import]
                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model %s (first run downloads it)...", self.model_name)
                self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns L2-normalised float32 vectors, so inner product == cosine similarity."""
        model = self._load()
        vecs = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype="float32")

"""Application settings, loaded from environment variables / backend/.env.

Every limit that affects the LLM context is configurable here, because different
Groq models have different context windows.
"""
from functools import lru_cache
from pathlib import Path

# pyrefly: ignore[missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # --- Groq ---
    groq_api_key: str = ""
    # No default model on purpose: set GROQ_MODEL in .env (see .env.example / README).
    groq_model: str = ""
    groq_timeout_seconds: float = 60.0

    # --- Context window management (all values are *estimated* tokens) ---
    model_context_window: int = 8192  # set to your model's real limit
    max_response_tokens: int = 1024
    history_token_budget: int = 3000  # recent turns (+ summary) budget
    rag_token_budget: int = 2000  # retrieved document passages budget
    recent_messages_to_keep: int = 6  # never summarized while history fits
    summary_max_tokens: int = 400

    # --- RAG ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size_chars: int = 1000
    chunk_overlap_chars: int = 200
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.30  # cosine similarity threshold

    # --- Uploads / storage ---
    max_upload_mb: int = 15
    data_dir: Path = BACKEND_DIR / "data"
    tesseract_cmd: str = ""  # optional explicit path to tesseract.exe

    # --- Server ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "nexus.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

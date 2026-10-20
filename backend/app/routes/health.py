# pyrefly: ignore[missing-import]
from fastapi import APIRouter, Depends

from app.deps import Container, get_container
from app.services import ocr
from app.services.groq_client import LLMError
from app.services.vector_store import HAS_FAISS

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(c: Container = Depends(get_container)) -> dict:
    s = c.settings
    groq: dict = {"configured": c.llm.configured, "model": s.groq_model or None, "model_available": None, "error": None}
    if c.llm.configured:
        try:
            models = await c.llm.list_models()
            groq["model_available"] = s.groq_model in models
            if not groq["model_available"]:
                groq["error"] = f"Model '{s.groq_model}' is not available to this API key. Change GROQ_MODEL."
                groq["available_models"] = models
        except LLMError as exc:
            groq["error"] = exc.message
    else:
        groq["error"] = "Set GROQ_API_KEY and GROQ_MODEL in backend/.env, then restart the backend."
    return {
        "status": "ok",
        "groq": groq,
        "ocr_available": ocr.ocr_available(),
        "vector_backend": "faiss" if HAS_FAISS else "numpy",
        "embedding_model": s.embedding_model,
        "limits": {
            "context_window": s.model_context_window,
            "max_response_tokens": s.max_response_tokens,
            "history_token_budget": s.history_token_budget,
            "rag_token_budget": s.rag_token_budget,
            "max_upload_mb": s.max_upload_mb,
        },
    }

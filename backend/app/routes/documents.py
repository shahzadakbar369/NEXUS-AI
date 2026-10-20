import asyncio
import logging
from pathlib import Path
    
# pyrefly: ignore[missing-import]
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from app.deps import Container, get_container
from app.schemas import Document
from app.services import document_processor as dp

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats/{chat_id}/documents", tags=["documents"])


def _require_chat(c: Container, chat_id: str) -> None:
    if not c.db.get_chat(chat_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")


def process_document(c: Container, doc: dict, path: Path) -> None:
    """Runs in a background thread: extract -> chunk -> embed -> index."""
    try:
        pages = dp.extract_pdf(path) if doc["kind"] == "pdf" else dp.extract_image(path)
        chunks = dp.chunk_pages(pages, c.settings.chunk_size_chars, c.settings.chunk_overlap_chars)
        n = c.store.add_document(doc["id"], doc["filename"], chunks)
        if not c.db.get_document(doc["chat_id"], doc["id"]):  # deleted while processing
            c.store.delete_document(doc["id"])
            return
        c.db.update_document(doc["id"], status="ready", pages=len(pages), chunks=n)
        log.info("Indexed %s: %d pages, %d chunks", doc["filename"], len(pages), n)
    except dp.DocumentError as exc:
        c.db.update_document(doc["id"], status="failed", error=str(exc))
    except Exception:  # noqa: BLE001
        log.exception("Processing failed for %s", doc["filename"])
        c.db.update_document(doc["id"], status="failed", error="Unexpected error while processing this file.")


@router.post("", response_model=Document, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(chat_id: str, file: UploadFile, background: BackgroundTasks,
                          c: Container = Depends(get_container)) -> dict:
    _require_chat(c, chat_id)
    filename = Path(file.filename or "upload").name[:200]
    limit = c.settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"File is larger than the {c.settings.max_upload_mb} MB limit.")
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file is empty.")
    try:
        kind = dp.detect_kind(filename, data[:16])
    except dp.DocumentError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    if kind == "image":
        from app.services import ocr
        if not ocr.ocr_available():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Image text extraction needs Tesseract OCR, which is not installed on the server. "
                                "See README (Optional: image OCR). PDFs and normal chat still work.")

    doc = c.db.add_document(chat_id, filename, kind, len(data))
    # Stored under a server-generated name; the file is only ever parsed, never executed.
    path = c.settings.uploads_dir / f"{doc['id']}{Path(filename).suffix.lower()}"
    await asyncio.to_thread(path.write_bytes, data)
    background.add_task(process_document, c, doc, path)
    return doc


@router.get("", response_model=list[Document])
def list_documents(chat_id: str, c: Container = Depends(get_container)) -> list[dict]:
    _require_chat(c, chat_id)
    return c.db.list_documents(chat_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(chat_id: str, document_id: str, c: Container = Depends(get_container)) -> None:
    _require_chat(c, chat_id)
    if not c.db.delete_document(chat_id, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    c.store.delete_document(document_id)
    for f in c.settings.uploads_dir.glob(f"{document_id}.*"):
        f.unlink(missing_ok=True)

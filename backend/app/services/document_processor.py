"""Validates uploads, extracts text (PDF via PyMuPDF, images via optional OCR) and chunks it."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

# pyrefly: ignore[missing-import]
import fitz  # PyMuPDF

from app.services import ocr

log = logging.getLogger(__name__)

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
# Magic bytes -- we check content, not just the extension.
IMAGE_MAGIC = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpeg", b"RIFF": "webp", b"BM": "bmp", b"II*\x00": "tiff", b"MM\x00*": "tiff"}

MIN_CHARS_PER_DOC = 20


class DocumentError(Exception):
    """Validation/processing problem that is safe to show to the user."""


@dataclass
class Page:
    page: int
    text: str


def detect_kind(filename: str, head: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in PDF_EXT:
        if not head.startswith(b"%PDF-"):
            raise DocumentError("This file has a .pdf extension but is not a valid PDF.")
        return "pdf"
    if ext in IMAGE_EXT:
        if not any(head.startswith(m) for m in IMAGE_MAGIC):
            raise DocumentError("This file does not look like a valid image.")
        return "image"
    raise DocumentError("Unsupported file type. Upload a PDF or an image (PNG, JPG, WEBP, BMP, TIFF).")


def extract_pdf(path: Path) -> list[Page]:
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise DocumentError("The PDF could not be opened. It may be corrupted.") from exc
    try:
        if doc.needs_pass:
            raise DocumentError("The PDF is password-protected. Remove the password and upload again.")
        if doc.page_count == 0:
            raise DocumentError("The PDF has no pages.")
        pages = [Page(i + 1, _clean(p.get_text("text"))) for i, p in enumerate(doc)]
    finally:
        doc.close()
    if sum(len(p.text) for p in pages) < MIN_CHARS_PER_DOC:
        raise DocumentError(
            "No extractable text was found. The PDF is empty or scanned (image-only). "
            "Scanned PDFs need OCR, which is not supported for PDFs in this version.")
    return [p for p in pages if p.text]


def extract_image(path: Path) -> list[Page]:
    text = _clean(ocr.image_to_text(path))
    if len(text) < MIN_CHARS_PER_DOC:
        raise DocumentError("OCR found no readable text in this image.")
    return [Page(1, text)]


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[dict]:
    """Split each page into overlapping character windows, preferring whitespace boundaries.

    Chunks never cross page boundaries, so every chunk has one exact page number.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    chunks: list[dict] = []
    for pg in pages:
        text, start = pg.text, 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                ws = text.rfind(" ", start + size // 2, end)
                if ws != -1:
                    end = ws
            piece = text[start:end].strip()
            if piece:
                chunks.append({"page": pg.page, "text": piece})
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks

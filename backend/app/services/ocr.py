"""Optional OCR via a locally installed Tesseract binary (free, offline)."""
from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

WINDOWS_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


@lru_cache
def tesseract_path() -> str | None:
    configured = get_settings().tesseract_cmd
    for candidate in (configured, shutil.which("tesseract"), str(WINDOWS_DEFAULT)):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def ocr_available() -> bool:
    try:
        # pyrefly: ignore[missing-import]
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return tesseract_path() is not None


def image_to_text(path: Path) -> str:
    from app.services.document_processor import DocumentError

    if not ocr_available():
        raise DocumentError(
            "Image text extraction needs Tesseract OCR, which is not installed on the server. "
            "See README > Optional: image OCR. PDFs and normal chat still work.")
    # pyrefly: ignore[missing-import]
    import pytesseract
    # pyrefly: ignore[missing-import]
    from PIL import Image, UnidentifiedImageError

    pytesseract.pytesseract.tesseract_cmd = tesseract_path()
    try:
        with Image.open(path) as img:
            img.load()
            if img.width * img.height > 40_000_000:
                raise DocumentError("Image resolution is too large to process.")
            return pytesseract.image_to_string(img.convert("RGB"))
    except UnidentifiedImageError as exc:
        raise DocumentError("The image could not be decoded. It may be corrupted.") from exc

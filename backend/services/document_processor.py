"""
services/document_processor.py

Pipeline:
  1. Open PDF with PyMuPDF
  2. Extract text per page
  3. Detect low-text pages → apply Tesseract OCR
  4. Validate document is not empty
  5. Clean and normalize text
  6. Chunk text with overlap
  7. Return structured chunks
"""
import os
import re
import logging
from dataclasses import dataclass
from typing import Generator

import fitz                  # PyMuPDF

# pytesseract and Pillow are optional (not available on Vercel serverless)
# OCR is skipped gracefully when these are absent; digital PDFs still work fine.
try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

import io

logger = logging.getLogger(__name__)

CHUNK_SIZE      = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP   = int(os.getenv("CHUNK_OVERLAP", "100"))
OCR_DPI         = 300
MIN_TEXT_CHARS_PER_PAGE = 30  # below this → page is considered scanned/image


@dataclass(frozen=True)
class TextChunk:
    text: str
    page: int
    chunk_index: int
    char_start: int
    char_end: int


class DocumentProcessingError(Exception):
    pass


class EmptyDocumentError(DocumentProcessingError):
    pass


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_page_text_native(page: fitz.Page) -> str:
    return page.get_text("text").strip()


def _extract_page_text_ocr(page: fitz.Page) -> str:
    """Render page to image and OCR it. Returns '' if OCR deps not available."""
    if not _OCR_AVAILABLE:
        logger.warning("OCR skipped — pytesseract/Pillow not installed (serverless environment)")
        return ""
    mat = fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    try:
        text = pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        return text.strip()
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract not installed — OCR unavailable")
        return ""


def extract_text_from_pdf(file_path: str) -> tuple[list[tuple[int, str]], bool]:
    """
    Returns:
        pages:    list of (page_number, text)
        ocr_used: whether OCR was applied to any page
    """
    if not os.path.exists(file_path):
        raise DocumentProcessingError(f"File not found: {file_path}")

    ocr_used = False
    pages: list[tuple[int, str]] = []

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise DocumentProcessingError(f"Cannot open PDF: {e}") from e

    with doc:
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = _extract_page_text_native(page)

            if len(text) < MIN_TEXT_CHARS_PER_PAGE:
                logger.info("Page %d below text threshold — applying OCR", page_num + 1)
                text = _extract_page_text_ocr(page)
                ocr_used = True

            pages.append((page_num + 1, text))

    return pages, ocr_used


# ── Text cleaning ─────────────────────────────────────────────────────────────

_MULTI_SPACE   = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    text = _CONTROL_CHARS.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def merge_pages(pages: list[tuple[int, str]]) -> str:
    """Merge page texts with page markers for later traceability."""
    parts = []
    for page_num, text in pages:
        cleaned = clean_text(text)
        if cleaned:
            parts.append(f"[PAGE {page_num}]\n{cleaned}")
    return "\n\n".join(parts)


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(full_text: str) -> list[TextChunk]:
    """
    Word-boundary-aware chunking with overlap.
    Preserves page markers in metadata by tracking char offsets.
    """
    words = full_text.split()
    if not words:
        raise EmptyDocumentError("Document produced no extractable text after cleaning.")

    chunks: list[TextChunk] = []
    chunk_index = 0
    word_pos = 0  # index into words[]

    while word_pos < len(words):
        end_pos = min(word_pos + CHUNK_SIZE, len(words))
        chunk_words = words[word_pos:end_pos]
        chunk_text_str = " ".join(chunk_words)

        # Find page number by looking at nearest [PAGE N] marker
        page_num = _find_page_for_chunk(full_text, chunk_words)

        char_start = full_text.find(chunk_words[0]) if chunk_words else 0
        char_end   = char_start + len(chunk_text_str)

        chunks.append(TextChunk(
            text=chunk_text_str,
            page=page_num,
            chunk_index=chunk_index,
            char_start=char_start,
            char_end=char_end,
        ))

        chunk_index += 1
        advance = CHUNK_SIZE - CHUNK_OVERLAP
        word_pos += max(advance, 1)  # guard against infinite loop

    return chunks


def _find_page_for_chunk(full_text: str, chunk_words: list[str]) -> int:
    """Best-effort: find which [PAGE N] the first word of the chunk falls under."""
    if not chunk_words:
        return 1
    first_word = chunk_words[0]
    idx = full_text.find(first_word)
    if idx == -1:
        return 1
    preceding = full_text[:idx]
    page_markers = re.findall(r"\[PAGE (\d+)\]", preceding)
    return int(page_markers[-1]) if page_markers else 1


# ── Public entry point ────────────────────────────────────────────────────────

def process_document(file_path: str) -> dict:
    """
    Full pipeline. Returns:
    {
        chunks:    [TextChunk, ...],
        page_count: int,
        ocr_used:  bool,
        char_count: int,
    }
    Raises DocumentProcessingError / EmptyDocumentError on failure.
    """
    pages, ocr_used = extract_text_from_pdf(file_path)

    total_text = sum(len(t) for _, t in pages)
    if total_text < 50:
        raise EmptyDocumentError(
            "Document appears empty or unreadable. "
            "Ensure it contains selectable text or legible scanned pages."
        )

    full_text = merge_pages(pages)
    chunks    = chunk_text(full_text)

    if not chunks:
        raise EmptyDocumentError("No text chunks could be produced from this document.")

    return {
        "chunks":     chunks,
        "page_count": len(pages),
        "ocr_used":   ocr_used,
        "char_count": len(full_text),
    }

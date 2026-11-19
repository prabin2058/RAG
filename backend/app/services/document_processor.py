"""Multi-format document text extraction and chunking."""

import csv
import re
from abc import ABC, abstractmethod

CHUNK_WORDS = 400
OVERLAP_WORDS = 50
MIN_CHUNK_WORDS = 50


class DocumentProcessor(ABC):
    """Base class for document processors."""

    @abstractmethod
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        """Extract text as list of (page_number, text) tuples (1-indexed)."""
        ...


class PDFProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        import pdfplumber

        pages = []
        try:
            with pdfplumber.open(filepath) as pdf:
                if len(pdf.pages) == 0:
                    raise ValueError("The PDF contains no pages.")
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    text = " ".join(text.split())
                    if text:
                        pages.append((i, text))
        except Exception as e:
            raise ValueError(f"Could not read the PDF: {e}") from e

        if not pages:
            raise ValueError("No readable text was found in the PDF.")
        return pages


class DocxProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        try:
            from docx import Document as DocxDocument
        except ImportError as exc:
            raise ValueError(
                "python-docx is not installed. Install it with: pip install python-docx"
            ) from exc

        try:
            doc = DocxDocument(filepath)
        except Exception as e:
            raise ValueError(f"Could not read the DOCX file: {e}") from e

        full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        full_text = " ".join(full_text.split())

        if not full_text:
            raise ValueError("No readable text was found in the DOCX file.")

        # Split into ~1000-word "pages" since DOCX has no native page concept
        words = full_text.split()
        PAGE_SIZE = 1000
        pages = []
        for i in range(0, len(words), PAGE_SIZE):
            page_text = " ".join(words[i : i + PAGE_SIZE])
            pages.append((len(pages) + 1, page_text))
        return pages


class CsvProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            raise ValueError(f"Could not read the CSV file: {e}") from e

        if not rows:
            raise ValueError("The CSV file is empty.")

        # Use first row as headers
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []

        if not data_rows:
            raise ValueError("The CSV file contains no data rows.")

        # Convert each row to a text record: "col1: value1, col2: value2, ..."
        records = []
        for row in data_rows:
            parts = []
            for h, v in zip(headers, row, strict=False):
                v = v.strip()
                if v:
                    parts.append(f"{h}: {v}" if h else v)
            if parts:
                records.append(", ".join(parts))

        if not records:
            raise ValueError("No readable data was found in the CSV file.")

        # Group records into pages (~1000 records per page)
        PAGE_SIZE = 1000
        pages = []
        for i in range(0, len(records), PAGE_SIZE):
            page_text = "\n".join(records[i : i + PAGE_SIZE])
            pages.append((len(pages) + 1, page_text))
        return pages


class TxtProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            raise ValueError(f"Could not read the text file: {e}") from e

        text = " ".join(text.split())
        if not text:
            raise ValueError("The text file is empty.")

        # Split into ~1000-word pages
        words = text.split()
        PAGE_SIZE = 1000
        pages = []
        for i in range(0, len(words), PAGE_SIZE):
            page_text = " ".join(words[i : i + PAGE_SIZE])
            pages.append((len(pages) + 1, page_text))
        return pages


class ExcelProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str) -> list[tuple[int, str]]:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError(
                "openpyxl is not installed. Install it with: pip install openpyxl"
            ) from exc

        try:
            wb = load_workbook(filepath, read_only=True, data_only=True)
        except Exception as e:
            raise ValueError(f"Could not read the Excel file: {e}") from e

        records = []
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                parts = []
                for cell in row:
                    if cell is not None:
                        text = str(cell).strip()
                        if text:
                            parts.append(text)
                if parts:
                    records.append(", ".join(parts))
        wb.close()

        if not records:
            raise ValueError("No readable data was found in the Excel file.")

        PAGE_SIZE = 1000
        pages = []
        for i in range(0, len(records), PAGE_SIZE):
            page_text = "\n".join(records[i : i + PAGE_SIZE])
            pages.append((len(pages) + 1, page_text))
        return pages


# Registry: extension → processor
_PROCESSORS: dict[str, DocumentProcessor] = {
    ".pdf": PDFProcessor(),
    ".docx": DocxProcessor(),
    ".csv": CsvProcessor(),
    ".txt": TxtProcessor(),
    ".xlsx": ExcelProcessor(),
}

ALLOWED_EXTENSIONS = set(_PROCESSORS.keys())


def get_processor(filename: str) -> DocumentProcessor:
    """Return the appropriate processor for the given filename."""
    ext = _get_extension(filename)
    if ext not in _PROCESSORS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file format: {ext}. Allowed: {allowed}")
    return _PROCESSORS[ext]


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension including the dot."""
    idx = filename.rfind(".")
    if idx == -1:
        return ""
    return filename[idx:].lower()


# --- Chunking (shared across all formats) ---


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using common sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """Split text into semantically meaningful chunks at sentence boundaries.

    Returns a list of dicts: {text, page_number, chunk_index}.
    """
    chunks = []
    chunk_index = 0

    for page_number, text in pages:
        sentences = _split_sentences(text)
        current_chunk_words = []
        current_word_count = 0

        for sentence in sentences:
            sentence_words = sentence.split()
            sentence_word_count = len(sentence_words)

            if current_word_count + sentence_word_count > CHUNK_WORDS and current_chunk_words:
                chunk_text = " ".join(current_chunk_words)
                if chunk_text and current_word_count >= MIN_CHUNK_WORDS:
                    chunks.append({
                        "text": chunk_text,
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

                if current_word_count > OVERLAP_WORDS:
                    overlap_words = current_chunk_words[-OVERLAP_WORDS:]
                else:
                    overlap_words = []
                current_chunk_words = overlap_words
                current_word_count = len(overlap_words)

            current_chunk_words.extend(sentence_words)
            current_word_count += sentence_word_count

        if current_chunk_words:
            chunk_text = " ".join(current_chunk_words)
            if chunk_text and current_word_count >= MIN_CHUNK_WORDS:
                chunks.append({
                    "text": chunk_text,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

    return chunks

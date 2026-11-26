"""Multi-format document text extraction and chunking."""

import csv
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable

log = logging.getLogger(__name__)

# The embedding model reads at most 512 tokens. English prose is ~1.3 tokens
# per word, but tables and numbers can be 2-4, so chunks are kept well under
# that and any chunk that is still too long is split (see chunk_pages).
CHUNK_WORDS = 250
OVERLAP_WORDS = 40
# A trailing piece smaller than this is merged into the previous chunk of the
# same page instead of becoming its own tiny chunk. Nothing is ever dropped.
MIN_CHUNK_WORDS = 40

# Table blocks inside a page's text start with this marker so the chunker can
# split them by rows instead of by sentences.
TABLE_MARKER = "[[TABLE]]"

# A PDF page with fewer characters than this but with images is treated as scanned.
SCANNED_MAX_CHARS = 20
OCR_DPI = 200

ProgressCallback = Callable[[int, int], None]  # (pages_done, total_pages)


class DocumentProcessor(ABC):
    """Base class for document processors.

    A new instance is created per document, so per-run state such as
    ``warnings`` and ``total_pages`` is safe to keep on the instance.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.total_pages: int | None = None

    @abstractmethod
    def extract_pages(
        self, filepath: str, on_progress: ProgressCallback | None = None
    ) -> list[tuple[int, str]]:
        """Extract text as list of (page_number, text) tuples (1-indexed)."""
        ...


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _format_table(rows: list[list[str | None]], page_number: int, table_number: int) -> str | None:
    """Turn a pdfplumber table into a text block: a title line, then one line per row.

    When the first row looks like a header, every row is written as
    "Header: value | Header: value" so each line makes sense on its own.
    """
    cleaned = [[_clean(c) for c in row] for row in rows if row]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return None

    header = cleaned[0] if len(cleaned) > 1 and sum(bool(c) for c in cleaned[0]) >= max(
        1, len(cleaned[0]) // 2 + 1
    ) else None
    body = cleaned[1:] if header else cleaned

    title = f"{TABLE_MARKER} Table {table_number} on page {page_number}."
    if header:
        title += " Columns: " + " | ".join(h for h in header if h)

    lines = []
    for row in body:
        if header:
            parts = [f"{h}: {v}" if h else v for h, v in zip(header, row, strict=False) if v]
        else:
            parts = [v for v in row if v]
        if parts:
            lines.append(" | ".join(parts))
    if not lines and header:
        lines.append(" | ".join(h for h in header if h))
    return "\n".join([title, *lines])


def _get_ocr() -> Callable | None:
    """Return an OCR function if pytesseract and the tesseract binary are installed."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:
        return None

    def ocr(page) -> str:
        image = page.to_image(resolution=OCR_DPI).original
        return _clean(pytesseract.image_to_string(image))

    return ocr


def _extract_pdf_page(page, page_number: int) -> tuple[str, list[str]]:
    """Return (prose text, table blocks) for one pdfplumber page.

    Text that sits inside a detected table is left out of the prose so it is
    not stored twice.
    """
    try:
        tables = page.find_tables()
    except Exception:
        tables = []

    prose_page = page
    if tables:
        boxes = [t.bbox for t in tables]

        def outside_tables(obj) -> bool:
            if "x0" not in obj or "top" not in obj:
                return True
            cx = (obj["x0"] + obj["x1"]) / 2
            cy = (obj["top"] + obj["bottom"]) / 2
            return not any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in boxes)

        prose_page = page.filter(outside_tables)

    text = _clean(prose_page.extract_text())

    blocks = []
    for n, table in enumerate(tables, start=1):
        try:
            block = _format_table(table.extract(), page_number, n)
        except Exception:
            block = None
        if block:
            blocks.append(block)
    return text, blocks


class PDFProcessor(DocumentProcessor):
    def extract_pages(
        self, filepath: str, on_progress: ProgressCallback | None = None
    ) -> list[tuple[int, str]]:
        import pdfplumber

        pages = []
        scanned_skipped = 0
        ocr_used = 0
        ocr = None
        ocr_checked = False

        try:
            with pdfplumber.open(filepath) as pdf:
                total = len(pdf.pages)
                if total == 0:
                    raise ValueError("The PDF contains no pages.")
                self.total_pages = total

                for i, page in enumerate(pdf.pages, start=1):
                    try:
                        text, tables = _extract_pdf_page(page, i)

                        if len(text) < SCANNED_MAX_CHARS and not tables and page.images:
                            if not ocr_checked:
                                ocr, ocr_checked = _get_ocr(), True
                            if ocr:
                                try:
                                    text = ocr(page)
                                    ocr_used += 1
                                except Exception as e:
                                    log.warning("OCR failed on page %d: %s", i, e)
                            else:
                                scanned_skipped += 1

                        content = "\n\n".join(part for part in [text, *tables] if part)
                        if content:
                            pages.append((i, content))
                    finally:
                        # Free pdfplumber's per-page cache — matters for 2000-page files.
                        page.close()

                    if on_progress:
                        on_progress(i, total)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Could not read the PDF: {e}") from e

        install_hint = "Install OCR with: brew install tesseract && pip install pytesseract"
        if not pages:
            if scanned_skipped:
                raise ValueError(f"This PDF looks scanned (images only). {install_hint}")
            raise ValueError("No readable text was found in the PDF.")
        if scanned_skipped:
            self.warnings.append(
                f"{scanned_skipped} page(s) look scanned and were skipped because OCR "
                f"is not installed. {install_hint}"
            )
        if ocr_used:
            self.warnings.append(f"{ocr_used} scanned page(s) were read with OCR.")
        return pages



class DocxProcessor(DocumentProcessor):
    def extract_pages(self, filepath: str, on_progress=None) -> list[tuple[int, str]]:
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
    def extract_pages(self, filepath: str, on_progress=None) -> list[tuple[int, str]]:
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
    def extract_pages(self, filepath: str, on_progress=None) -> list[tuple[int, str]]:
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
    def extract_pages(self, filepath: str, on_progress=None) -> list[tuple[int, str]]:
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

# Registry: extension → processor class (a fresh instance per document)
_PROCESSORS: dict[str, type[DocumentProcessor]] = {
    ".pdf": PDFProcessor,
    ".docx": DocxProcessor,
    ".csv": CsvProcessor,
    ".txt": TxtProcessor,
    ".xlsx": ExcelProcessor,
}

ALLOWED_EXTENSIONS = set(_PROCESSORS.keys())


def get_processor(filename: str) -> DocumentProcessor:
    """Return a new processor for the given filename."""
    ext = _get_extension(filename)
    if ext not in _PROCESSORS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file format: {ext}. Allowed: {allowed}")
    return _PROCESSORS[ext]()


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


def _chunk_prose(text: str) -> list[str]:
    """Split prose into ~CHUNK_WORDS-word chunks at sentence boundaries, with overlap.

    Very long "sentences" (e.g. text with no full stops) are cut into
    smaller pieces. A small leftover at the end is merged into the
    previous chunk; a short page on its own (a caption, a heading) is kept.
    """
    # Long pieces are cut small enough that piece + overlap still fits in one chunk.
    max_unit = CHUNK_WORDS - OVERLAP_WORDS
    units: list[list[str]] = []
    for sentence in _split_sentences(text):
        words = sentence.split()
        for i in range(0, len(words), max_unit):
            units.append(words[i : i + max_unit])

    chunks: list[list[str]] = []
    current: list[str] = []
    new_words = 0  # words in `current` that are not overlap from the previous chunk
    for words in units:
        if current and len(current) + len(words) > CHUNK_WORDS:
            chunks.append(current)
            current = current[-OVERLAP_WORDS:] if len(current) > OVERLAP_WORDS else []
            new_words = 0
        current = current + words
        new_words += len(words)

    if new_words:
        if chunks and new_words < MIN_CHUNK_WORDS:
            chunks[-1] = chunks[-1] + current[-new_words:]
        else:
            chunks.append(current)
    return [" ".join(c) for c in chunks]


def _chunk_table(block: str) -> list[str]:
    """Split a table block by rows; every chunk repeats the title and column names."""
    lines = block.split("\n")
    title = lines[0].replace(TABLE_MARKER, "", 1).strip()
    rows = lines[1:]
    title_words = len(title.split())

    chunks: list[str] = []
    current: list[str] = []
    count = title_words
    for row in rows:
        n = len(row.split())
        if current and count + n > CHUNK_WORDS:
            chunks.append("\n".join([title, *current]))
            current, count = [], title_words
        current.append(row)
        count += n
    if current or not chunks:
        chunks.append("\n".join([title, *current]))
    return chunks


def _split_to_fit(
    text: str, is_table: bool, count_tokens: Callable[[str], int], max_tokens: int
) -> list[str]:
    """Halve a chunk until every piece fits the embedding model's token limit.

    Tables are halved by rows and keep their title line; prose by words.
    A single word that is still too long is kept as it is.
    """
    if count_tokens(text) <= max_tokens:
        return [text]
    lines = text.split("\n")
    if is_table and len(lines) > 2:
        title, rows = lines[0], lines[1:]
        mid = len(rows) // 2
        halves = ["\n".join([title, *rows[:mid]]), "\n".join([title, *rows[mid:]])]
    else:
        words = text.split()
        if len(words) < 2:
            return [text]
        mid = len(words) // 2
        halves = [" ".join(words[:mid]), " ".join(words[mid:])]
        is_table = False
    return [p for h in halves for p in _split_to_fit(h, is_table, count_tokens, max_tokens)]


def chunk_pages(
    pages: list[tuple[int, str]],
    count_tokens: Callable[[str], int] | None = None,
    max_tokens: int | None = None,
) -> list[dict]:
    """Split page text into chunks. Prose is split by sentences, tables by rows.

    With ``count_tokens`` and ``max_tokens`` (the embedding model's limit),
    any chunk that is still too long is split further, so no text is cut off
    when it is embedded.

    Returns a list of dicts: {text, page_number, chunk_index}.
    """
    chunks = []
    chunk_index = 0

    for page_number, text in pages:
        blocks = text.split("\n\n") if TABLE_MARKER in text else [text]
        for block in blocks:
            if not block.strip():
                continue
            is_table = block.startswith(TABLE_MARKER)
            pieces = _chunk_table(block) if is_table else _chunk_prose(block)
            if count_tokens is not None and max_tokens is not None:
                pieces = [
                    p for piece in pieces
                    for p in _split_to_fit(piece, is_table, count_tokens, max_tokens)
                ]
            for piece in pieces:
                chunks.append({
                    "text": piece,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

    return chunks

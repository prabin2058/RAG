"""PDF text extraction and chunking."""

import pdfplumber

CHUNK_WORDS = 800  # target words per chunk (~800 tokens)
OVERLAP_WORDS = 100  # words shared between consecutive chunks


def extract_pages(filepath: str) -> list[tuple[int, str]]:
    """Extract text page-by-page.

    Returns a list of (page_number, text) tuples (1-indexed). Pages with no
    extractable text are skipped. Raises ValueError on unreadable/corrupt PDFs.
    """
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
        raise ValueError(f"Could not read the PDF: {e}")

    if not pages:
        raise ValueError("No readable text was found in the PDF.")
    return pages


def chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """Split each page's text into overlapping word-count chunks.

    Returns a list of dicts: {text, page_number, chunk_index}.
    """
    chunks = []
    chunk_index = 0
    for page_number, text in pages:
        words = text.split()
        start = 0
        while start < len(words):
            end = start + CHUNK_WORDS
            chunk_text = " ".join(words[start:end])
            if chunk_text:
                chunks.append(
                    {
                        "text": chunk_text,
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1
            start += CHUNK_WORDS - OVERLAP_WORDS
    return chunks
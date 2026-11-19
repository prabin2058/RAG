"""PDF text extraction and chunking."""

import re

import pdfplumber

CHUNK_WORDS = 400  # smaller chunks = more precise retrieval
OVERLAP_WORDS = 50
MIN_CHUNK_WORDS = 50  # don't create tiny chunks


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
        raise ValueError(f"Could not read the PDF: {e}") from e

    if not pages:
        raise ValueError("No readable text was found in the PDF.")
    return pages


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using common sentence boundaries."""
    # Split on sentence-ending punctuation followed by space or end of string
    sentences = re.split(r'(?<=[.!?])\s+', text)
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

            # If adding this sentence would exceed chunk size, finalize current chunk
            if current_word_count + sentence_word_count > CHUNK_WORDS and current_chunk_words:
                chunk_text = " ".join(current_chunk_words)
                if chunk_text and current_word_count >= MIN_CHUNK_WORDS:
                    chunks.append({
                        "text": chunk_text,
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

                # Keep last N words for overlap
                if current_word_count > OVERLAP_WORDS:
                    overlap_words = current_chunk_words[-OVERLAP_WORDS:]
                else:
                    overlap_words = []
                current_chunk_words = overlap_words
                current_word_count = len(overlap_words)

            current_chunk_words.extend(sentence_words)
            current_word_count += sentence_word_count

        # Finalize remaining text on this page
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

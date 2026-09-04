"""
Extractors turn a messy input file into raw text that the AI parser can
reason about. They deliberately do NOT try to interpret structure — that's
the AI parser's job. A "scrambled" CSV with inconsistent delimiters or a
PDF with misaligned columns will break a naive `pandas.read_csv` or
`pdfplumber.extract_table`, so extraction here is intentionally dumb and
literal: pull out everything readable, preserve layout hints (line breaks,
spacing) where possible, and hand it off.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".tsv", ".txt"}


class ExtractionError(Exception):
    """Raised when a file can't be read at all (corrupt, unsupported, empty)."""


def extract_text(file_path: str | Path) -> str:
    """Read any supported messy file and return its raw text content.

    Args:
        file_path: path to a .pdf, .csv, .tsv, or .txt file.

    Returns:
        Raw text extracted from the file, layout preserved as best-effort.

    Raises:
        ExtractionError: if the file is missing, unsupported, or unreadable.
    """
    path = Path(file_path)
    if not path.exists():
        raise ExtractionError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(
            f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    if suffix == ".pdf":
        text = _extract_pdf_text(path)
    else:
        text = _extract_plain_text(path)

    if not text or not text.strip():
        raise ExtractionError(f"No readable content found in {path}")

    return text


def _extract_pdf_text(path: Path) -> str:
    """Pull raw text from every page of a PDF, preserving line layout.

    Uses `layout=True` so that columns that are visually aligned on the
    page stay roughly aligned in the extracted text — this is what lets an
    LLM later infer column boundaries from a PDF that has no real table
    structure (e.g. a scanned-looking invoice built from text boxes).
    """
    pages_text = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text(layout=True) or ""
            pages_text.append(f"--- Page {i + 1} ---\n{page_text}")
    return "\n\n".join(pages_text)


def _extract_plain_text(path: Path) -> str:
    """Read a CSV/TSV/TXT file as raw text, tolerating bad encodings.

    We do not attempt to parse delimiters or columns here — a "scrambled"
    CSV may have ragged rows, mixed delimiters, or stray commas inside
    unquoted fields that would make `pandas.read_csv` choke or silently
    misalign columns. Handing the AI parser the raw lines lets it reason
    about what each row probably means instead.
    """
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: replace undecodable bytes rather than failing outright.
    return path.read_bytes().decode("utf-8", errors="replace")

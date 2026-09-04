import pytest

from ai_data_cleaner.extractors import ExtractionError, extract_text
from .conftest import SAMPLE_DIR


def test_extract_pdf_returns_nonempty_text():
    text = extract_text(SAMPLE_DIR / "nightmare_invoice.pdf")
    assert "BRIGHTPATH" in text
    assert "TOTAL DUE" in text


def test_extract_csv_returns_raw_text_unparsed():
    text = extract_text(SAMPLE_DIR / "scrambled_expenses.csv")
    # The raw text should preserve the ragged structure verbatim -
    # extraction must NOT try to parse/align columns itself.
    assert "zoom webinar addon; one-time; 55" in text
    assert "LinkedIn Ads" in text


def test_missing_file_raises():
    with pytest.raises(ExtractionError):
        extract_text(SAMPLE_DIR / "does_not_exist.pdf")


def test_unsupported_extension_raises(tmp_path):
    bad_file = tmp_path / "notes.docx"
    bad_file.write_text("hello")
    with pytest.raises(ExtractionError):
        extract_text(bad_file)


def test_empty_file_raises(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("   \n\n  ")
    with pytest.raises(ExtractionError):
        extract_text(empty_file)

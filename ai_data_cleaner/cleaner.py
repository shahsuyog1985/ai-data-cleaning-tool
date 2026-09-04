"""
Orchestrates the full pipeline: messy file -> raw text -> AI-structured line
items -> pandas DataFrame -> written output (CSV/Excel), plus a summary of
where a human should double-check the AI's work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ai_parser import ParseResult, parse_document
from .categories import DEFAULT_CATEGORIES
from .extractors import extract_text

LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class CleaningSummary:
    document_type: str
    row_count: int
    overall_confidence: float
    low_confidence_rows: int
    category_totals: dict[str, float]
    issues: list[str]
    truncated: bool
    model: str


def clean_file(
    input_path: str | Path,
    categories: list[str] | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[pd.DataFrame, CleaningSummary]:
    """Run the full pipeline on a single messy file.

    Returns a (DataFrame, CleaningSummary) pair. The DataFrame has one row
    per line item; the summary is meant for a human reviewer or a CLI
    report, highlighting anything the AI flagged as uncertain.
    """
    categories = categories or DEFAULT_CATEGORIES
    raw_text = extract_text(input_path)

    kwargs = {"categories": categories}
    if model:
        kwargs["model"] = model
    if api_key:
        kwargs["api_key"] = api_key

    result = parse_document(raw_text, **kwargs)
    return _result_to_dataframe(result), _summarize(result)


def result_to_dataframe_and_summary(result: ParseResult) -> tuple[pd.DataFrame, CleaningSummary]:
    """Same conversion as clean_file, but starting from an already-parsed
    ParseResult (used by --demo mode, which replays a cached result instead
    of calling the API)."""
    return _result_to_dataframe(result), _summarize(result)


def _result_to_dataframe(result: ParseResult) -> pd.DataFrame:
    rows = [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "total": item.total,
            "category": item.category,
            "confidence": round(item.confidence, 2),
            "needs_review": item.confidence < LOW_CONFIDENCE_THRESHOLD,
            "notes": item.notes,
            "raw_text": item.raw_text,
        }
        for item in result.line_items
    ]
    columns = [
        "description",
        "quantity",
        "unit_price",
        "total",
        "category",
        "confidence",
        "needs_review",
        "notes",
        "raw_text",
    ]
    return pd.DataFrame(rows, columns=columns)


def _summarize(result: ParseResult) -> CleaningSummary:
    category_totals: dict[str, float] = {}
    low_confidence_rows = 0
    for item in result.line_items:
        if item.total is not None:
            category_totals[item.category] = category_totals.get(item.category, 0.0) + item.total
        if item.confidence < LOW_CONFIDENCE_THRESHOLD:
            low_confidence_rows += 1

    return CleaningSummary(
        document_type=result.document_type,
        row_count=len(result.line_items),
        overall_confidence=round(result.overall_confidence, 2),
        low_confidence_rows=low_confidence_rows,
        category_totals={k: round(v, 2) for k, v in category_totals.items()},
        issues=result.issues,
        truncated=result.truncated,
        model=result.model,
    )


def write_output(df: pd.DataFrame, output_path: str | Path) -> Path:
    """Write the cleaned DataFrame to CSV or Excel based on the output extension."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False)
    return path

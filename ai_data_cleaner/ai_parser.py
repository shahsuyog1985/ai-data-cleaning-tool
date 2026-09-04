"""
The core "AI" of ai-data-cleaner: hands raw, disorganized text to Claude and
gets back a structured table of line items, each tagged with a business
category and a confidence score.

Design notes
------------
Rather than asking the model to free-write JSON (which invites trailing
commentary, markdown fences, or subtly invalid JSON), this uses Claude's
tool-use feature: we define a `record_line_items` tool with a strict JSON
schema and force the model to call it (`tool_choice`). The model's tool
call input IS the parsed data, so there's no brittle string-scraping.

The model is asked to:
1. Split the raw text into individual line items (rows of a table),
   however irregular the source layout was.
2. Reconstruct description / quantity / unit_price / total for each item,
   using `null` for anything it can't confidently determine.
3. Assign each item to one of the caller-supplied business categories.
4. Give a 0-1 confidence score per item AND an overall document score,
   plus a short list of anything ambiguous or guessed — this is what
   makes the output auditable rather than a black box.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .categories import DEFAULT_CATEGORIES

DEFAULT_MODEL = os.environ.get("AI_DATA_CLEANER_MODEL", "claude-3-5-haiku-20241022")
MAX_INPUT_CHARS = 60_000  # keeps a single call well within context; see README for chunking notes.


class AIParsingError(Exception):
    """Raised when the model can't be reached or returns something unusable."""


@dataclass
class LineItem:
    raw_text: str
    description: str | None
    quantity: float | None
    unit_price: float | None
    total: float | None
    category: str
    confidence: float
    notes: str | None = None


@dataclass
class ParseResult:
    document_type: str
    line_items: list[LineItem]
    overall_confidence: float
    issues: list[str] = field(default_factory=list)
    model: str = DEFAULT_MODEL
    truncated: bool = False


def _build_tool_schema(categories: list[str]) -> dict[str, Any]:
    return {
        "name": "record_line_items",
        "description": (
            "Record the cleaned, structured line items extracted from a messy "
            "source document, along with a category and confidence for each."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "description": (
                        "Best guess at what kind of document this is, e.g. "
                        "'invoice', 'receipt', 'expense_report', 'general_table', 'unknown'."
                    ),
                },
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "raw_text": {
                                "type": "string",
                                "description": "The original messy text this row was reconstructed from.",
                            },
                            "description": {
                                "type": ["string", "null"],
                                "description": "Cleaned, human-readable description of the line item.",
                            },
                            "quantity": {
                                "type": ["number", "null"],
                                "description": "Numeric quantity if present, else null.",
                            },
                            "unit_price": {
                                "type": ["number", "null"],
                                "description": "Price per unit if determinable, else null.",
                            },
                            "total": {
                                "type": ["number", "null"],
                                "description": "Line total if present or derivable, else null.",
                            },
                            "category": {
                                "type": "string",
                                "enum": categories,
                                "description": "Best-fit business category for this line item.",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "0.0-1.0 confidence in this row's accuracy.",
                            },
                            "notes": {
                                "type": ["string", "null"],
                                "description": "Anything ambiguous, guessed, or worth a human double-checking.",
                            },
                        },
                        "required": ["raw_text", "category", "confidence"],
                    },
                },
                "overall_confidence": {
                    "type": "number",
                    "description": "0.0-1.0 confidence across the whole document.",
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Document-level problems encountered (garbled OCR, missing headers, etc).",
                },
            },
            "required": ["document_type", "line_items", "overall_confidence"],
        },
    }


SYSTEM_PROMPT = """You are a meticulous data-entry specialist. You will be given raw, \
messy text extracted from a disorganized source file (a poorly-formatted PDF invoice, \
a scrambled CSV with inconsistent columns, etc). Your job is to reconstruct it into \
clean, structured line items.

Rules:
- Find every distinct line item / row, even if the source formatting is inconsistent, \
misaligned, or split across lines.
- Do not invent data. If a field can't be determined, use null rather than guessing a \
specific number.
- If quantity and unit_price are both known but total is missing, you may compute total. \
Do the reverse too if it lets you fill in a genuinely missing field from the other two.
- Assign each item to the single best-fit category from the provided list. Use \
"Other / Uncategorized" only when nothing else is a reasonable fit.
- Confidence should reflect real uncertainty: a clearly-labeled row gets high confidence; \
a row you had to guess at (merged cells, truncated OCR, ambiguous units) gets lower \
confidence, and you should explain why in `notes`.
- Ignore document furniture that isn't a line item: page headers/footers, column \
headers, subtotal/tax/total summary rows (call those out in `issues` instead if useful), \
signatures, boilerplate.
- Always call the record_line_items tool exactly once with the complete result."""


def parse_document(
    raw_text: str,
    categories: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_retries: int = 3,
) -> ParseResult:
    """Send raw messy text to Claude and get back structured, categorized line items.

    Args:
        raw_text: text pulled from the source file by an extractor.
        categories: business categories to classify each line item into.
        model: Claude model id to use.
        api_key: Anthropic API key; falls back to ANTHROPIC_API_KEY env var.
        max_retries: transient-error retry attempts before giving up.

    Returns:
        A ParseResult with structured, categorized, confidence-scored line items.

    Raises:
        AIParsingError: on missing credentials, exhausted retries, or a
            response that doesn't match the expected schema.
    """
    categories = categories or DEFAULT_CATEGORIES
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AIParsingError(
            "No Anthropic API key found. Set ANTHROPIC_API_KEY (see .env.example), "
            "or run `ai-data-clean demo` to see cached sample output instead."
        )

    truncated = False
    if len(raw_text) > MAX_INPUT_CHARS:
        raw_text = raw_text[:MAX_INPUT_CHARS]
        truncated = True

    client = anthropic.Anthropic(api_key=key)
    tool = _build_tool_schema(categories)

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=[tool],
                tool_choice={"type": "tool", "name": "record_line_items"},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Categories to choose from: {json.dumps(categories)}\n\n"
                            f"Raw extracted text:\n---\n{raw_text}\n---"
                        ),
                    }
                ],
            )
            return _to_parse_result(response, model, truncated)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 8))
                continue
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise AIParsingError(f"Model returned an unusable response: {exc}") from exc

    raise AIParsingError(f"Anthropic API call failed after {max_retries} attempts: {last_error}")


def _to_parse_result(response: Any, model: str, truncated: bool) -> ParseResult:
    tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
    if not tool_use_blocks:
        raise AIParsingError("Model did not return a tool_use block as expected.")

    data = tool_use_blocks[0].input
    items = [
        LineItem(
            raw_text=item.get("raw_text", ""),
            description=item.get("description"),
            quantity=item.get("quantity"),
            unit_price=item.get("unit_price"),
            total=item.get("total"),
            category=item.get("category", "Other / Uncategorized"),
            confidence=float(item.get("confidence", 0.0)),
            notes=item.get("notes"),
        )
        for item in data.get("line_items", [])
    ]

    return ParseResult(
        document_type=data.get("document_type", "unknown"),
        line_items=items,
        overall_confidence=float(data.get("overall_confidence", 0.0)),
        issues=data.get("issues", []) or [],
        model=model,
        truncated=truncated,
    )

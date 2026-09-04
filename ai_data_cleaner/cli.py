"""Command-line interface for ai-data-cleaner."""

from __future__ import annotations

import json
from pathlib import Path

import click
from dotenv import load_dotenv

from .ai_parser import AIParsingError, LineItem, ParseResult, parse_document
from .categories import DEFAULT_CATEGORIES
from .cleaner import CleaningSummary, result_to_dataframe_and_summary, write_output
from .extractors import ExtractionError, extract_text

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_CACHE = {
    "invoice": PROJECT_ROOT / "sample_data" / "demo_cache" / "nightmare_invoice.json",
    "csv": PROJECT_ROOT / "sample_data" / "demo_cache" / "scrambled_expenses.json",
}
DEMO_SOURCE = {
    "invoice": PROJECT_ROOT / "sample_data" / "nightmare_invoice.pdf",
    "csv": PROJECT_ROOT / "sample_data" / "scrambled_expenses.csv",
}


@click.group()
def main() -> None:
    """AI-powered cleaning tool: turn messy files into clean, categorized tables."""


@main.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", default=None, help="Output file (.csv or .xlsx). Defaults to output/<input-name>.csv")
@click.option("--categories", "categories_arg", default=None, help="Comma-separated category list, or a path to a JSON list, overriding the defaults.")
@click.option("--model", default=None, help="Anthropic model id (defaults to $AI_DATA_CLEANER_MODEL or claude-3-5-haiku-20241022).")
@click.option("--api-key", default=None, help="Anthropic API key (defaults to $ANTHROPIC_API_KEY).")
@click.option("--save-cache", is_flag=True, help="Also save the raw AI result as JSON next to the output file, for reuse or debugging.")
def clean(input_path: str, output_path: str | None, categories_arg: str | None, model: str | None, api_key: str | None, save_cache: bool) -> None:
    """Clean a single messy file (PDF, CSV, TSV, or TXT) using AI extraction + categorization."""
    categories = _resolve_categories(categories_arg)

    click.echo(f"Reading {input_path} ...")
    try:
        raw_text = extract_text(input_path)
    except ExtractionError as exc:
        raise click.ClickException(str(exc))

    click.echo(f"Sending to AI for parsing ({len(raw_text):,} chars extracted) ...")
    try:
        kwargs = {"categories": categories}
        if model:
            kwargs["model"] = model
        if api_key:
            kwargs["api_key"] = api_key
        result = parse_document(raw_text, **kwargs)
    except AIParsingError as exc:
        raise click.ClickException(str(exc))

    df, summary = result_to_dataframe_and_summary(result)
    out_path = Path(output_path) if output_path else PROJECT_ROOT / "output" / f"{Path(input_path).stem}.csv"
    write_output(df, out_path)
    click.echo(f"Wrote {len(df)} rows to {out_path}")

    if save_cache:
        cache_path = out_path.with_suffix(".raw.json")
        cache_path.write_text(json.dumps(_result_to_dict(result), indent=2))
        click.echo(f"Saved raw AI result to {cache_path}")

    _print_summary(summary)


@main.command()
@click.option("--which", type=click.Choice(["invoice", "csv"]), default="invoice", help="Which bundled sample to show.")
@click.option("-o", "--output", "output_path", default=None, help="Output file (.csv or .xlsx). Defaults to output/demo_<which>.csv")
def demo(which: str, output_path: str | None) -> None:
    """Show cleaned output for a bundled 'nightmare' sample file — no API key required.

    Replays a cached AI result generated ahead of time from a real API call
    against sample_data/nightmare_invoice.pdf or sample_data/scrambled_expenses.csv,
    so anyone can see the tool's output without their own Anthropic key.
    Run `clean` directly on those same files to see a live API call instead.
    """
    cache_path = DEMO_CACHE[which]
    source_path = DEMO_SOURCE[which]
    click.secho(f"[demo mode] Replaying cached AI output for {source_path.name} (no API call made)\n", fg="yellow")

    data = json.loads(cache_path.read_text())
    result = _dict_to_result(data)

    df, summary = result_to_dataframe_and_summary(result)
    out_path = Path(output_path) if output_path else PROJECT_ROOT / "output" / f"demo_{which}.csv"
    write_output(df, out_path)
    click.echo(f"Wrote {len(df)} rows to {out_path}")

    _print_summary(summary)


def _resolve_categories(categories_arg: str | None) -> list[str]:
    if not categories_arg:
        return DEFAULT_CATEGORIES
    path = Path(categories_arg)
    if path.exists():
        return json.loads(path.read_text())
    return [c.strip() for c in categories_arg.split(",") if c.strip()]


def _print_summary(summary: CleaningSummary) -> None:
    click.echo("")
    click.secho("Summary", bold=True)
    click.echo(f"  Document type:       {summary.document_type}")
    click.echo(f"  Line items found:    {summary.row_count}")
    conf_color = "green" if summary.overall_confidence >= 0.8 else "yellow" if summary.overall_confidence >= 0.6 else "red"
    click.echo("  Overall confidence:  " + click.style(f"{summary.overall_confidence:.0%}", fg=conf_color))
    if summary.low_confidence_rows:
        click.secho(f"  ⚠ {summary.low_confidence_rows} row(s) flagged for human review (confidence < 60%)", fg="yellow")
    if summary.truncated:
        click.secho("  ⚠ Input was truncated to fit the model's context window — results may be incomplete.", fg="yellow")
    if summary.category_totals:
        click.echo("  Totals by category:")
        for cat, total in sorted(summary.category_totals.items(), key=lambda kv: -kv[1]):
            click.echo(f"    {cat:<28} ${total:,.2f}")
    if summary.issues:
        click.echo("  Issues noted by the AI:")
        for issue in summary.issues:
            click.echo(f"    - {issue}")


def _result_to_dict(result: ParseResult) -> dict:
    return {
        "document_type": result.document_type,
        "model": result.model,
        "overall_confidence": result.overall_confidence,
        "issues": result.issues,
        "line_items": [item.__dict__ for item in result.line_items],
    }


def _dict_to_result(data: dict) -> ParseResult:
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
        model=data.get("model", "cached"),
        truncated=False,
    )


if __name__ == "__main__":
    main()

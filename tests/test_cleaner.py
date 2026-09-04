import pandas as pd

from ai_data_cleaner.ai_parser import LineItem, ParseResult
from ai_data_cleaner.cleaner import result_to_dataframe_and_summary, write_output


def _make_result():
    return ParseResult(
        document_type="invoice",
        line_items=[
            LineItem(
                raw_text="raw a",
                description="Item A",
                quantity=1,
                unit_price=10.0,
                total=10.0,
                category="Office Supplies",
                confidence=0.95,
            ),
            LineItem(
                raw_text="raw b",
                description="Item B",
                quantity=2,
                unit_price=5.0,
                total=10.0,
                category="Office Supplies",
                confidence=0.4,
                notes="guessed unit price",
            ),
            LineItem(
                raw_text="raw c",
                description="Item C",
                quantity=None,
                unit_price=None,
                total=100.0,
                category="Travel",
                confidence=0.9,
            ),
        ],
        overall_confidence=0.75,
        issues=["Something was ambiguous."],
        model="test-model",
        truncated=False,
    )


def test_result_to_dataframe_has_expected_columns_and_rows():
    df, summary = result_to_dataframe_and_summary(_make_result())

    assert list(df.columns) == [
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
    assert len(df) == 3
    assert df.iloc[0]["description"] == "Item A"


def test_low_confidence_rows_flagged_for_review():
    df, summary = result_to_dataframe_and_summary(_make_result())

    assert df.iloc[1]["needs_review"] == True  # noqa: E712 (confidence 0.4 < 0.6 threshold)
    assert df.iloc[0]["needs_review"] == False  # noqa: E712
    assert summary.low_confidence_rows == 1


def test_category_totals_sum_correctly():
    _, summary = result_to_dataframe_and_summary(_make_result())

    assert summary.category_totals == {"Office Supplies": 20.0, "Travel": 100.0}
    assert summary.row_count == 3
    assert summary.overall_confidence == 0.75
    assert summary.issues == ["Something was ambiguous."]


def test_write_output_csv(tmp_path):
    df, _ = result_to_dataframe_and_summary(_make_result())
    out = write_output(df, tmp_path / "out.csv")

    assert out.exists()
    reloaded = pd.read_csv(out)
    assert len(reloaded) == 3


def test_write_output_xlsx(tmp_path):
    df, _ = result_to_dataframe_and_summary(_make_result())
    out = write_output(df, tmp_path / "out.xlsx")

    assert out.exists()
    reloaded = pd.read_excel(out)
    assert len(reloaded) == 3

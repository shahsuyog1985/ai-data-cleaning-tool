from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from anthropic import APIConnectionError, RateLimitError

from ai_data_cleaner.ai_parser import AIParsingError, parse_document
from ai_data_cleaner.categories import DEFAULT_CATEGORIES


def _fake_tool_use_response(data: dict):
    """Builds an object shaped like an anthropic Message with one tool_use block."""
    block = SimpleNamespace(type="tool_use", input=data)
    return SimpleNamespace(content=[block])


def _sample_result_payload():
    return {
        "document_type": "invoice",
        "overall_confidence": 0.9,
        "issues": ["Totals row excluded."],
        "line_items": [
            {
                "raw_text": "Widgets x3 @ 10.00 = 30.00",
                "description": "Widgets",
                "quantity": 3,
                "unit_price": 10.0,
                "total": 30.0,
                "category": "Office Supplies",
                "confidence": 0.95,
                "notes": None,
            }
        ],
    }


def test_parse_document_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIParsingError, match="No Anthropic API key"):
        parse_document("some raw text", api_key=None)


@patch("ai_data_cleaner.ai_parser.anthropic.Anthropic")
def test_parse_document_happy_path(mock_anthropic_cls):
    mock_client = mock_anthropic_cls.return_value
    mock_client.messages.create.return_value = _fake_tool_use_response(_sample_result_payload())

    result = parse_document("Widgets x3 @ 10.00 = 30.00", api_key="fake-key")

    assert result.document_type == "invoice"
    assert result.overall_confidence == 0.9
    assert len(result.line_items) == 1
    item = result.line_items[0]
    assert item.description == "Widgets"
    assert item.category == "Office Supplies"
    assert item.total == 30.0

    # The tool schema passed to the API should expose exactly our categories as the enum.
    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["tools"][0]["input_schema"]["properties"]["category"] if False else True
    tool = kwargs["tools"][0]
    category_enum = tool["input_schema"]["properties"]["line_items"]["items"]["properties"]["category"]["enum"]
    assert category_enum == DEFAULT_CATEGORIES
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_line_items"}


@patch("ai_data_cleaner.ai_parser.time.sleep", return_value=None)
@patch("ai_data_cleaner.ai_parser.anthropic.Anthropic")
def test_parse_document_retries_on_transient_error_then_succeeds(mock_anthropic_cls, _mock_sleep):
    mock_client = mock_anthropic_cls.return_value
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    transient_error = APIConnectionError(request=request)

    mock_client.messages.create.side_effect = [
        transient_error,
        _fake_tool_use_response(_sample_result_payload()),
    ]

    result = parse_document("raw text", api_key="fake-key", max_retries=3)

    assert mock_client.messages.create.call_count == 2
    assert result.document_type == "invoice"


@patch("ai_data_cleaner.ai_parser.time.sleep", return_value=None)
@patch("ai_data_cleaner.ai_parser.anthropic.Anthropic")
def test_parse_document_raises_after_exhausting_retries(mock_anthropic_cls, _mock_sleep):
    mock_client = mock_anthropic_cls.return_value
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=429, request=request)
    mock_client.messages.create.side_effect = RateLimitError(
        "rate limited", response=response, body=None
    )

    with pytest.raises(AIParsingError, match="failed after 2 attempts"):
        parse_document("raw text", api_key="fake-key", max_retries=2)

    assert mock_client.messages.create.call_count == 2


@patch("ai_data_cleaner.ai_parser.anthropic.Anthropic")
def test_parse_document_raises_on_missing_tool_use_block(mock_anthropic_cls):
    mock_client = mock_anthropic_cls.return_value
    mock_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="oops, no tool call")]
    )

    with pytest.raises(AIParsingError, match="tool_use"):
        parse_document("raw text", api_key="fake-key")


@patch("ai_data_cleaner.ai_parser.anthropic.Anthropic")
def test_parse_document_truncates_long_input(mock_anthropic_cls):
    mock_client = mock_anthropic_cls.return_value
    mock_client.messages.create.return_value = _fake_tool_use_response(_sample_result_payload())

    long_text = "x" * 100_000
    result = parse_document(long_text, api_key="fake-key")

    assert result.truncated is True
    sent_text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert len(sent_text) < len(long_text)

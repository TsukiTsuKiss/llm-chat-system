"""Display formatting for step and session metrics."""

from __future__ import annotations

from studio.display import (
    format_by_model_markdown_table,
    format_session_end_lines,
    format_step_metrics_line,
)


def test_format_step_metrics_line_with_model_and_api_source() -> None:
    line = format_step_metrics_line(
        {
            "assistant": "ChatGPT",
            "model": "gpt-5.5",
            "elapsed": 2.084,
            "tokens": {"in": 2530, "out": 48, "source": "api"},
            "cost": 0.002674,
        }
    )
    assert line == "[ChatGPT/gpt-5.5] | 2.084s | in=2530 out=48 (api) | 23.0 tok/s | $0.002674"


def test_format_step_metrics_line_without_model() -> None:
    line = format_step_metrics_line(
        {
            "assistant": "mock",
            "elapsed": 0.0,
            "tokens": {"in": 0, "out": 0, "source": "none"},
            "cost": 0.0,
        }
    )
    assert "[mock]" in line
    assert "in=0 out=0 (none)" in line
    assert "$0.000000" in line


def test_format_session_end_lines_includes_by_model_markdown_table() -> None:
    lines = format_session_end_lines(
        {
            "total_elapsed": 51.7,
            "total_cost": 0.017794,
            "by_model": {
                "ChatGPT/gpt-5.5": {
                    "requests": 2,
                    "tokens_in": 3728,
                    "tokens_out": 551,
                    "cost": 0.005381,
                }
            },
        }
    )
    text = "\n".join(lines)
    assert "session end" in text
    assert "--- by model ---" in text
    assert "| model | req | in | out | cost (USD) |" in text
    assert "| ChatGPT/gpt-5.5 | 2 | 3728 | 551 | 0.005381 |" in text


def test_format_by_model_markdown_table_empty() -> None:
    assert format_by_model_markdown_table({}) == ""

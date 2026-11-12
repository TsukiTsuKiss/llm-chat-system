"""CLI / summary formatting for session metrics."""

from __future__ import annotations

from typing import Any

from studio.logging import DEFAULT_CURRENCY, format_money

SPEAKER_EMOJIS = [
    "🔵", "🟠", "🟢", "🟣",
    "🔴", "🟡", "🟤", "⚫",
    "🔷", "🚨", "💠", "🟩",
]


def format_step_metrics_line(payload: dict[str, Any]) -> str:
    assistant = payload.get("assistant") or "?"
    model = payload.get("model")
    label = f"{assistant}/{model}" if model else assistant

    tokens = payload.get("tokens") or {}
    tokens_in = int(tokens.get("in") or 0)
    tokens_out = int(tokens.get("out") or 0)
    source = tokens.get("source") or "none"

    elapsed = float(payload.get("elapsed") or 0.0)
    cost = float(payload.get("cost") or 0.0)

    parts = [
        f"[{label}]",
        f"{elapsed:.3f}s",
        f"in={tokens_in} out={tokens_out} ({source})",
    ]
    if elapsed > 0 and tokens_out > 0:
        parts.append(f"{tokens_out / elapsed:.1f} tok/s")
    parts.append(format_money(cost, payload.get("currency") or DEFAULT_CURRENCY))
    return " | ".join(parts)


def format_total_cost(payload: dict[str, Any]) -> str:
    """session_end の合計費用。USD の合計に、他の通貨（total_cost_other）を続けて示す。"""
    parts = [format_money(float(payload.get("total_cost") or 0), DEFAULT_CURRENCY)]
    for currency, amount in (payload.get("total_cost_other") or {}).items():
        parts.append(format_money(float(amount), currency))
    return " + ".join(parts)


def format_by_model_markdown_table(by_model: dict[str, dict[str, Any]]) -> str:
    """Markdown table for CLI session summary (stdout only; JSONL is unchanged)."""
    if not by_model:
        return ""
    mixed = any((stats.get("currency") or DEFAULT_CURRENCY) != DEFAULT_CURRENCY for stats in by_model.values())
    lines = [
        "",
        "| model | req | in | out | cost |" if mixed else "| model | req | in | out | cost (USD) |",
        "|---|---:|---:|---:|---:|",
    ]
    for key in sorted(by_model):
        stats = by_model[key]
        cost = stats.get("cost", 0)
        cost_text = format_money(cost, stats.get("currency") or DEFAULT_CURRENCY) if mixed else f"{cost:.6f}"
        lines.append(
            f"| {key} | {stats.get('requests', 0)} | "
            f"{stats.get('tokens_in', 0)} | {stats.get('tokens_out', 0)} | "
            f"{cost_text} |"
        )
    return "\n".join(lines)


def format_session_end_lines(payload: dict[str, Any]) -> list[str]:
    lines = [
        (
            f"\n=== session end === {payload.get('total_elapsed', 0):.1f}s "
            f"| total={format_total_cost(payload)}"
        )
    ]
    table = format_by_model_markdown_table(payload.get("by_model") or {})
    if table:
        lines.append("--- by model ---")
        lines.append(table)
    if payload.get("artifact_dir"):
        lines.append(f"成果物: {payload['artifact_dir']}")
    return lines

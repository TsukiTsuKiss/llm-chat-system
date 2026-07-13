"""Session report generation parity tests."""

from __future__ import annotations

import json
from pathlib import Path

from studio.session_report import (
    export_session_markdown,
    generate_session_markdown,
    list_sessions,
    load_session_markdown,
    parse_session_timestamp,
    read_jsonl,
    summarize_session,
)


def _write_sample_log(path: Path) -> None:
    records = [
        {
            "type": "session_meta",
            "organization": "solo",
            "workflow": None,
            "parent_session_id": None,
            "talents": {"solo_bot": "ソロBot"},
            "models": {"solo_bot": {"assistant": "mock"}},
            "generation": {"stream": True, "temperature": 0.7},
        },
        {"type": "user_input", "text": "hello"},
        {
            "type": "step",
            "talent_id": "solo_bot",
            "assistant": "mock",
            "action": "reply",
            "text": "MOCK:solo_bot:step1",
            "stream": True,
            "elapsed": 0.0,
            "tokens": {"in": 0, "out": 0, "source": "none"},
            "cost": 0.0,
        },
        {
            "type": "session_end",
            "total_elapsed": 0.1,
            "total_cost": 0.0,
            "by_model": {},
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_parse_session_timestamp() -> None:
    assert parse_session_timestamp("20260714_020216") == "2026-07-14 02:02:16"


def test_list_sessions_newest_first(tmp_path: Path) -> None:
    older = tmp_path / "sessions" / "20260101_120000.jsonl"
    newer = tmp_path / "sessions" / "20260201_120000.jsonl"
    _write_sample_log(older)
    _write_sample_log(newer)

    summaries = list_sessions(tmp_path)
    assert [item.session_id for item in summaries] == ["20260201_120000", "20260101_120000"]


def test_summarize_session_label(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "20260714_020216.jsonl"
    _write_sample_log(path)
    summary = summarize_session(path)
    assert summary is not None
    assert summary.organization == "solo"
    assert "2026-07-14 02:02:16" in summary.label
    assert "solo" in summary.label


def test_generate_session_markdown_includes_mermaid_and_table(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "20260714_020216.jsonl"
    _write_sample_log(path)
    markdown = generate_session_markdown(read_jsonl(path), session_id=path.stem)
    assert "```mermaid" in markdown
    assert "%%{init:" in markdown
    assert "primaryTextColor" in markdown
    assert "flowchart TD" in markdown
    assert "## 応答時間サマリ" in markdown
    assert "MOCK:solo_bot:step1" in markdown
    assert "hello" in markdown


def test_generate_session_markdown_mermaid_parallel_branch(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "20260713_161936.jsonl"
    records = [
        {
            "type": "session_meta",
            "organization": "nokuru",
            "workflow": "meeting",
            "parent_session_id": None,
            "talents": {"hinata": "ひなた", "satsuki": "さつき", "kaede": "かえで"},
            "models": {},
            "generation": {"stream": False, "temperature": 0.7},
        },
        {"type": "user_input", "text": "秋キャンプ"},
        {
            "type": "step",
            "talent_id": "hinata",
            "assistant": "mock",
            "action": "議題提示",
            "text": "論点",
            "stream": False,
            "elapsed": 0.0,
            "tokens": {"in": 0, "out": 0, "source": "none"},
            "cost": 0.0,
            "phase_type": "serial",
        },
        {
            "type": "step",
            "talent_id": "satsuki",
            "assistant": "mock",
            "action": "意見",
            "text": "A",
            "stream": False,
            "elapsed": 0.0,
            "tokens": {"in": 0, "out": 0, "source": "none"},
            "cost": 0.0,
            "phase_type": "parallel",
        },
        {
            "type": "step",
            "talent_id": "kaede",
            "assistant": "mock",
            "action": "意見",
            "text": "B",
            "stream": False,
            "elapsed": 0.0,
            "tokens": {"in": 0, "out": 0, "source": "none"},
            "cost": 0.0,
            "phase_type": "parallel",
        },
        {
            "type": "session_end",
            "total_elapsed": 1.0,
            "total_cost": 0.0,
            "by_model": {},
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    markdown = generate_session_markdown(records, session_id=path.stem)
    assert "parallel" in markdown
    assert "sync" in markdown
    assert "satsuki" in markdown
    assert "kaede" in markdown


def test_generate_session_markdown_mermaid_dark_theme(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "20260714_020216.jsonl"
    _write_sample_log(path)
    markdown = generate_session_markdown(
        read_jsonl(path),
        session_id=path.stem,
        flow_theme="dark",
    )
    assert '"darkMode": true' in markdown
    assert "#f8fafc" in markdown


def test_load_and_export_session_markdown(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "20260714_020216.jsonl"
    _write_sample_log(path)
    markdown = load_session_markdown(tmp_path, "20260714_020216")
    assert "セッションレポート" in markdown

    exported = export_session_markdown(tmp_path, "20260714_020216")
    assert exported.is_file()
    assert exported.name == "20260714_020216.md"
    assert "セッションレポート" in exported.read_text(encoding="utf-8")

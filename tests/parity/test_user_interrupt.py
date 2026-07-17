"""Tests for user interrupt (design.md §6.7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.interrupt import (
    DEFAULT_INTERRUPT_MARKER,
    USER_INTERRUPT_DISPLAY,
    matched_interrupt_marker,
    normalize_interrupt_markers,
    resolve_interrupt_markers,
    workflow_has_interrupt_on,
)
from studio.loader import load_session_context
from studio.validation import StudioValidationError
from studio.web_ui import WebSession, handle_chat_submit


def test_normalize_and_match_interrupt_markers() -> None:
    assert normalize_interrupt_markers("【ユーザー確認】") == ["【ユーザー確認】"]
    assert normalize_interrupt_markers(["A", ""]) == ["A"]
    assert matched_interrupt_marker("ご確認ください 【ユーザー確認】", ["【ユーザー確認】"]) == "【ユーザー確認】"
    assert matched_interrupt_marker("plain", ["【ユーザー確認】"]) is None


def test_resolve_interrupt_markers_from_workflow() -> None:
    workflow = {"interrupt_on": [DEFAULT_INTERRUPT_MARKER, "【確認】"]}
    assert resolve_interrupt_markers(workflow) == [DEFAULT_INTERRUPT_MARKER, "【確認】"]
    assert workflow_has_interrupt_on(workflow) is True
    assert workflow_has_interrupt_on({}) is False


def _write_interrupt_demo(studio_root: Path) -> None:
    wf_dir = studio_root / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "interrupt_demo.json").write_text(
        json.dumps(
            {
                "name": "割り込みデモ",
                "interrupt_on": "【ユーザー確認】",
                "slots": {
                    "host": {"description": "司会", "count": "1"},
                },
                "phases": [
                    {
                        "type": "serial",
                        "steps": [
                            {
                                "slot": "host",
                                "action": "ユーザーへ回答形式を確認する",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    org = {
        "talent_ids": ["solo_bot"],
        "workflow_bindings": {"interrupt_demo": {"host": ["solo_bot"]}},
    }
    org_dir = studio_root / "organizations" / "solo"
    org_dir.mkdir(parents=True, exist_ok=True)
    (org_dir / "config.json").write_text(
        json.dumps(org, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (org_dir / "model_mapping.json").write_text(
        json.dumps({"solo_bot": {"assistant": "mock"}}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_engine_interrupt_await_text_and_resume(studio_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_interrupt_demo(studio_root)
    monkeypatch.setenv("STUDIO_MOCK_INTERRUPT", "【ユーザー確認】")
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root, workflow_id="interrupt_demo")

    replies: list[str] = []

    def responder(event) -> str:
        if event.type == "await_text" and event.payload.get("interrupt"):
            replies.append(event.payload.get("prior_text", ""))
            return "はい、了解です"
        return ""

    events = collect_events(
        SessionEngine(ctx),
        "クイズを始めて",
        stream=False,
        responder=responder,
    )

    await_events = [e for e in events if e.type == "await_text"]
    assert len(await_events) == 1
    assert await_events[0].payload["interrupt"] is True
    assert await_events[0].payload["display_name"] == USER_INTERRUPT_DISPLAY
    assert "【ユーザー確認】" in await_events[0].payload["prior_text"]

    step_dones = [e for e in events if e.type == "step_done"]
    assert len(step_dones) == 1
    assert any(e.type == "session_done" for e in events)

    log_lines = (studio_root / "sessions").glob("*.jsonl")
    log_path = next(log_lines)
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("type") == "user_interrupt" and r.get("text") == "はい、了解です" for r in records)


def test_quiz_workflow_declares_interrupt_on() -> None:
    repo = Path(__file__).resolve().parents[2]
    quiz = json.loads((repo / "workflows" / "quiz.json").read_text(encoding="utf-8"))
    assert quiz.get("interrupt_on") == "【ユーザー確認】"


def test_batch_rejects_interrupt_workflow(studio_root: Path) -> None:
    _write_interrupt_demo(studio_root)
    ctx = load_session_context("solo", studio_root, workflow_id="interrupt_demo")
    from MultiRoleStudio import validate_batch_mode

    with pytest.raises(StudioValidationError) as exc:
        validate_batch_mode(ctx, "topic")
    assert "interrupt_on" in exc.value.format_all()


def test_web_interrupt_pending_and_resume(studio_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_interrupt_demo(studio_root)
    monkeypatch.setenv("STUDIO_MOCK_INTERRUPT", "【ユーザー確認】")
    MockAssistant.reset()
    session = WebSession(root=studio_root)

    gen = handle_chat_submit(
        session,
        "開始",
        org_id="solo",
        workflow_value="interrupt_demo",
        stream=False,
        temperature=0.7,
        user_context=False,
    )
    messages = []
    for messages, status, show_choice, placeholder, _ in gen:
        if session.pending is not None:
            break
    assert session.pending is not None
    assert session.pending.kind == "await_text"
    assert session.pending.event.payload.get("interrupt") is True

    final_messages = messages
    for final_messages, *_ in handle_chat_submit(
        session,
        "選択肢Aです",
        org_id="solo",
        workflow_value="interrupt_demo",
        stream=False,
        temperature=0.7,
        user_context=False,
    ):
        pass
    assert session.pending is None
    assert any("質問" in m.get("content", "") for m in final_messages)
    assert any(
        m.get("role") == "user" and "選択肢Aです" in m.get("content", "")
        for m in final_messages
    )

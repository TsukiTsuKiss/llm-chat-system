"""Phase 1 direct-send + mock execution parity tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context


def _event_types(events) -> list[str]:
    return [e.type for e in events]


def test_direct_send_mock_batch(studio_root: Path) -> None:
    MockAssistant.reset()
    os.environ.pop("STUDIO_MOCK_INJECT_TEMP_ERROR", None)

    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    events = collect_events(engine, "こんにちは", stream=False)

    types = _event_types(events)
    assert types[0] == "session_start"
    assert "step_start" in types
    assert "step_done" in types
    assert types[-1] == "session_done"

    step_done = next(e for e in events if e.type == "step_done")
    assert step_done.payload["text"] == "MOCK:solo_bot:step1"
    assert step_done.payload["assistant"] == "mock"
    assert step_done.payload["tokens"]["source"] == "none"
    assert step_done.payload["cost"] == 0


def test_jsonl_log_structure(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "log test", stream=False)

    log_path = engine.state.logger.log_path
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    types = [row["type"] for row in lines]
    assert types[0] == "session_meta"
    assert "user_input" in types
    assert "step" in types
    assert "state_snapshot" in types
    assert types[-1] == "session_end"

    meta = lines[0]
    assert meta["organization"] == "solo"
    assert meta["workflow"] is None
    assert "generation" in meta

    step = next(row for row in lines if row["type"] == "step")
    assert step["assistant"] == "mock"
    assert "model" not in step
    assert step["tokens"]["source"] == "none"


def test_streaming_chunks_match_step_done(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    events = collect_events(engine, "stream", stream=True)

    chunks = "".join(e.payload["text"] for e in events if e.type == "chunk")
    step_done = next(e for e in events if e.type == "step_done")
    assert chunks == step_done.payload["text"]


def test_mock_temperature_fallback(studio_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    MockAssistant.reset()
    monkeypatch.setenv("STUDIO_MOCK_INJECT_TEMP_ERROR", "1")

    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    events = collect_events(engine, "temp fallback", stream=False)

    step_done = next(e for e in events if e.type == "step_done")
    assert step_done.payload["text"] == "MOCK:solo_bot:step1"
    assert not any(e.type == "step_error" for e in events)

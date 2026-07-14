"""Phase 5a session resume / branch tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from studio.assistants import MockAssistant
from studio.engine import EngineState, SessionEngine, collect_events
from studio.loader import load_session_context
from studio.session_resume import (
    load_effective_records,
    load_resumed_session,
    rebuild_histories,
)


def test_branch_session_creates_parent_link(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "first turn", stream=False)
    parent_id = engine.state.logger.session_id

    resumed = load_resumed_session(studio_root, parent_id)
    assert resumed.org_id == "solo"
    assert resumed.step_number >= 1
    assert resumed.replay_messages

    engine2 = SessionEngine(ctx)
    engine2.state = EngineState(
        ctx=ctx,
        logger=None,
        histories=resumed.histories,
        step_number=resumed.step_number,
        parent_session_id=resumed.parent_session_id,
        session_wall_start=time.perf_counter(),
    )
    events = collect_events(engine2, "second turn", stream=False)
    child_id = events[0].payload["session_id"]
    child_meta = json.loads(
        (studio_root / "sessions" / f"{child_id}.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert child_meta["parent_session_id"] == parent_id

    parent_types = [
        json.loads(line)["type"]
        for line in (studio_root / "sessions" / f"{parent_id}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert parent_types.count("user_input") == 1
    child_types = [
        json.loads(line)["type"]
        for line in (studio_root / "sessions" / f"{child_id}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert child_types.count("user_input") == 1


def test_effective_records_merge_parent_chain(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)

    engine = SessionEngine(ctx)
    collect_events(engine, "turn one", stream=False)
    parent_id = engine.state.logger.session_id

    resumed = load_resumed_session(studio_root, parent_id)
    engine2 = SessionEngine(ctx)
    engine2.state = EngineState(
        ctx=ctx,
        logger=None,
        histories=resumed.histories,
        step_number=resumed.step_number,
        parent_session_id=resumed.parent_session_id,
        session_wall_start=time.perf_counter(),
    )
    collect_events(engine2, "turn two", stream=False)
    child_id = engine2.state.logger.session_id

    effective = load_effective_records(studio_root, child_id)
    user_texts = [r["text"] for r in effective if r.get("type") == "user_input"]
    assert user_texts == ["turn one", "turn two"]


def test_rebuild_histories_has_messages(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "hello", stream=False)
    parent_id = engine.state.logger.session_id
    records = load_effective_records(studio_root, parent_id)
    histories = rebuild_histories(records)
    history = histories.for_talent("solo_bot")
    assert len(history.get_messages()) >= 2

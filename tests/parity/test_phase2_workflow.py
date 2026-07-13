"""Phase 2 workflow and parallel execution parity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.validation import StudioValidationError


@pytest.fixture
def trio_root(studio_root: Path) -> Path:
    for name in ("workflows", "organizations/trio", "talents"):
        src = Path(__file__).resolve().parents[2] / name
        dest = studio_root / name
        if src.is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                import shutil

                shutil.copytree(src, dest)
            else:
                for p in src.glob("*.json"):
                    import shutil

                    shutil.copy2(p, dest / p.name)

    mapping = {
        "alpha": {"assistant": "mock"},
        "beta": {"assistant": "mock"},
        "gamma": {"assistant": "mock"},
    }
    (studio_root / "organizations" / "trio" / "model_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return studio_root


def test_discussion_serial_three_steps(trio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("trio", trio_root, workflow_id="discussion")
    engine = SessionEngine(ctx)
    events = collect_events(engine, "議題テスト", stream=False)

    step_dones = [e for e in events if e.type == "step_done"]
    assert len(step_dones) == 3
    assert step_dones[0].payload["text"] == "MOCK:alpha:step1"
    assert step_dones[1].payload["text"] == "MOCK:beta:step2"
    assert step_dones[2].payload["text"] == "MOCK:gamma:step3"

    types = [e.type for e in events]
    assert types.count("phase_start") == 1


def test_quiz_serial_parallel_serial(trio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("trio", trio_root, workflow_id="quiz")
    events = collect_events(engine := SessionEngine(ctx), "クイズ", stream=False)

    phase_types = [e.payload.get("phase_type") for e in events if e.type == "phase_start"]
    assert phase_types == ["serial", "parallel", "serial"]

    step_dones = [e for e in events if e.type == "step_done"]
    assert len(step_dones) == 4
    assert step_dones[0].payload["talent_id"] == "alpha"
    parallel_ids = {step_dones[1].payload["talent_id"], step_dones[2].payload["talent_id"]}
    assert parallel_ids == {"beta", "gamma"}
    assert step_dones[3].payload["talent_id"] == "alpha"

    parallel_steps = [e for e in events if e.type == "step_done" and e.payload["talent_id"] in parallel_ids]
    for step in parallel_steps:
        assert step.payload["stream"] is False


def test_quiz_binding_missing_reports_e301(trio_root: Path) -> None:
    config_path = trio_root / "organizations" / "trio" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["workflow_bindings"] = {}
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(StudioValidationError) as exc:
        load_session_context("trio", trio_root, workflow_id="quiz")
    assert any(e.code == "E301" for e in exc.value.errors)


def test_org_mission_in_prompt(trio_root: Path) -> None:
    from studio.prompts import build_system_prompt

    ctx = load_session_context("trio", trio_root, workflow_id="discussion")
    prompt = build_system_prompt(ctx.talents["alpha"], ctx.org, ctx.org_id, "alpha")
    assert "【ミッション】" in prompt
    assert "多様な視点" in prompt

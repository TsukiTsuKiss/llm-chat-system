"""Phase 3 loop, meeting, dev workflow and artifact parity tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.artifacts import extract_code_artifacts, normalize_artifact_paths, save_session_artifacts
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.logging import StepMetrics
from studio.validation import StudioValidationError


@pytest.fixture
def nokuru_root(studio_root: Path) -> Path:
    repo = Path(__file__).resolve().parents[2]
    for name in (
        "workflows",
        "organizations/nokuru",
        "talents/hinata.json",
        "talents/satsuki.json",
        "talents/kaede.json",
    ):
        src = repo / name
        if src.is_file():
            dest = studio_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(src, dest)
        elif src.is_dir():
            dest = studio_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                import shutil

                shutil.copytree(src, dest)
            else:
                for p in src.glob("*.json"):
                    import shutil

                    shutil.copy2(p, dest / p.name)

    mapping = {
        "hinata": {"assistant": "mock"},
        "satsuki": {"assistant": "mock"},
        "kaede": {"assistant": "mock"},
    }
    (studio_root / "organizations" / "nokuru" / "model_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return studio_root


def test_meeting_marker_early_exit(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_MOCK_MARKER", "【結論】")
    MockAssistant.reset()
    ctx = load_session_context("nokuru", nokuru_root, workflow_id="meeting")
    events = collect_events(SessionEngine(ctx), "キャンプ議題", stream=False)

    loop_checks = [e for e in events if e.type == "loop_check"]
    assert len(loop_checks) == 1
    assert loop_checks[0].payload["result"] == "exit"
    assert loop_checks[0].payload["exit_type"] == "marker"

    step_dones = [e for e in events if e.type == "step_done"]
    assert any("【結論】" in e.payload["text"] for e in step_dones)


def test_meeting_max_iterations_without_marker(
    nokuru_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STUDIO_MOCK_MARKER", raising=False)
    MockAssistant.reset()
    ctx = load_session_context("nokuru", nokuru_root, workflow_id="meeting")
    events = collect_events(SessionEngine(ctx), "キャンプ議題", stream=False)

    loop_checks = [e for e in events if e.type == "loop_check"]
    assert len(loop_checks) == 3
    assert all(e.payload["result"] == "continue" for e in loop_checks[:2])


def test_dev_judge_loop_and_artifacts(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_MOCK_JUDGE_EXIT", "1")
    monkeypatch.setenv("STUDIO_MOCK_EMIT_CODE", "1")
    MockAssistant.reset()
    ctx = load_session_context("nokuru", nokuru_root, workflow_id="dev")
    engine = SessionEngine(ctx)
    events = collect_events(engine, "hello 関数", stream=False)

    loop_checks = [e for e in events if e.type == "loop_check"]
    assert loop_checks[-1].payload["result"] == "exit"
    assert loop_checks[-1].payload["exit_type"] == "judge"

    session_done = [e for e in events if e.type == "session_done"][-1]
    assert session_done.payload.get("artifact_dir")

    artifact_dir = Path(session_done.payload["artifact_dir"])
    assert (artifact_dir / "hello.py").exists()
    assert "print('hello')" in (artifact_dir / "hello.py").read_text(encoding="utf-8")


def test_extract_code_artifacts_from_steps() -> None:
    steps = [
        StepMetrics(
            talent_id="kaede",
            assistant="mock",
            model=None,
            action="implement",
            text='ファイル名: src/app.py\n```python\nx = 1\n```',
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        )
    ]
    files = extract_code_artifacts(steps)
    assert files["src/app.py"] == "x = 1"


def test_extract_multiple_files_from_backticks_and_comments() -> None:
    text = (
        "`hello.py`\n```python\n# hello.py\n"
        'def hello():\n    return "hi"\n```\n\n'
        "`test_hello.py`\n```python\n# test_hello.py\n"
        "from hello import hello\n\ndef test_hi():\n    assert hello()\n```"
    )
    steps = [
        StepMetrics(
            talent_id="kaede",
            assistant="mock",
            model=None,
            action="implement",
            text=text,
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        )
    ]
    files = extract_code_artifacts(steps)
    assert "hello.py" in files
    assert "test_hello.py" in files
    assert 'return "hi"' in files["hello.py"]
    assert "from hello import hello" in files["test_hello.py"]


def test_nested_package_gets_init_and_run_script_sets_pythonpath(tmp_path: Path) -> None:
    steps = [
        StepMetrics(
            talent_id="kaede",
            assistant="mock",
            model=None,
            action="implement",
            text=(
                "`src/hello.py`\n```python\n"
                "def hello():\n    return 'hi'\n```\n\n"
                "`tests/test_hello.py`\n```python\n"
                "from src.hello import hello\n\ndef test_hi():\n    assert hello() == 'hi'\n```"
            ),
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        )
    ]
    session_dir = save_session_artifacts(tmp_path, "test_nested", steps)
    assert session_dir is not None
    assert (session_dir / "src" / "__init__.py").exists()
    run_all = (session_dir / "run_all.sh").read_text(encoding="utf-8")
    assert "export PYTHONPATH=." in run_all
    assert 'cd "$(dirname "$0")"' in run_all


def test_normalize_infers_src_layout_from_test_imports() -> None:
    files = normalize_artifact_paths(
        {
            "code_kaede_block_00.py": (
                'def hello(name: str = "World") -> str:\n    return f"Hello, {name}!"\n'
            ),
            "code_kaede_block_01.py": (
                "import pytest\nfrom src.hello import hello\n\ndef test_x():\n    assert hello()\n"
            ),
        }
    )
    assert "src/hello.py" in files
    assert "tests/test_hello.py" in files
    assert "code_kaede_block_00.py" not in files
    assert "def hello" in files["src/hello.py"]


def test_extract_skips_reviewer_and_judge_steps() -> None:
    steps = [
        StepMetrics(
            talent_id="kaede",
            assistant="mock",
            model=None,
            action="要件に沿ったコードを出力する",
            text="`hello.py`\n```python\ndef hello():\n    return 'ok'\n```",
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        ),
        StepMetrics(
            talent_id="satsuki",
            assistant="mock",
            model=None,
            action="実装をレビューし、指摘を述べる",
            text=(
                "例:\n```python\n"
                "def test_space():\n    assert hello('  ') == 'x'\n```"
            ),
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        ),
        StepMetrics(
            talent_id="satsuki",
            assistant="mock",
            model=None,
            action="終了条件: 指摘事項がすべて解消されること",
            text=(
                "【判定】継続\n```python\n"
                "def hello():\n    raise ValueError('bad')\n```"
            ),
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        ),
    ]
    files = extract_code_artifacts(steps)
    assert list(files) == ["hello.py"]
    assert "def hello" in files["hello.py"]


def test_prune_drops_incomplete_reviewer_style_snippets() -> None:
    steps = [
        StepMetrics(
            talent_id="kaede",
            assistant="mock",
            model=None,
            action="implement",
            text=(
                "`hello.py`\n```python\ndef hello():\n    return 'hi'\n```\n\n"
                "`tests/test_hello.py`\n```python\n"
                "from hello import hello\n\ndef test_hi():\n    assert hello()\n```"
            ),
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        ),
        StepMetrics(
            talent_id="satsuki",
            assistant="mock",
            model=None,
            action="実装をレビューし、指摘を述べる",
            text="ignored by filter",
            stream=False,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
        ),
    ]
    # Simulate pre-filter junk that normalize would not remove on its own
    raw = extract_code_artifacts(steps)
    raw["code_satsuki_実装をレビューし_00.py"] = (
        'def test_space():\n    assert hello("  ") == "x"\n'
    )
    from studio.artifacts import _prune_junk_artifacts

    files = _prune_junk_artifacts(normalize_artifact_paths(raw))
    assert "code_satsuki_実装をレビューし_00.py" not in files
    assert "tests/test_hello.py" in files


def test_e304_judge_slot_missing(nokuru_root: Path) -> None:
    bad = {
        "name": "bad",
        "slots": {"worker": {"description": "w", "count": "1"}},
        "phases": [
            {
                "type": "loop",
                "max_iterations": 2,
                "exit": {"type": "judge", "slot": "reviewer", "criteria": "ok"},
                "phases": [{"type": "serial", "steps": [{"slot": "worker", "action": "go"}]}],
            }
        ],
    }
    path = nokuru_root / "workflows" / "bad_judge.json"
    path.write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(StudioValidationError) as exc:
        load_session_context("nokuru", nokuru_root, workflow_id="bad_judge")
    assert any(e.code == "E304" for e in exc.value.errors)


def test_batch_rejects_user_exit_workflow(nokuru_root: Path) -> None:
    from MultiRoleStudio import validate_batch_mode

    user_wf = {
        "name": "user loop",
        "slots": {"member": {"description": "m", "count": "1+"}},
        "phases": [
            {
                "type": "loop",
                "exit": {"type": "user", "prompt": "続ける？"},
                "phases": [
                    {"type": "serial", "steps": [{"slot": "member", "action": "speak"}]}
                ],
            }
        ],
    }
    path = nokuru_root / "workflows" / "user_loop.json"
    path.write_text(json.dumps(user_wf), encoding="utf-8")
    ctx = load_session_context("nokuru", nokuru_root, workflow_id="user_loop")

    with pytest.raises(StudioValidationError) as exc:
        validate_batch_mode(ctx, "topic")
    assert any(e.code == "E402" for e in exc.value.errors)

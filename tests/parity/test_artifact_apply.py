"""Phase 5c artifact apply tests (design.md §7.6)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from studio.artifacts import (
    apply_commit_message,
    apply_session_artifacts,
    list_sandbox_artifact_files,
    sandbox_session_dir,
)
from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.vcs import has_uncommitted_changes, is_git_repo


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
            shutil.copy2(src, dest)
        elif src.is_dir():
            dest = studio_root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copytree(src, dest)
            else:
                for p in src.glob("*.json"):
                    shutil.copy2(p, dest / p.name)

    mapping = {"hinata": {"assistant": "mock"}, "satsuki": {"assistant": "mock"}, "kaede": {"assistant": "mock"}}
    (studio_root / "organizations" / "nokuru" / "model_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return studio_root


def _init_clean_git(root: Path) -> None:
    (root / ".gitignore").write_text("sessions/\nsandbox/\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _run_dev_session(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("STUDIO_MOCK_JUDGE_EXIT", "1")
    monkeypatch.setenv("STUDIO_MOCK_EMIT_CODE", "1")
    MockAssistant.reset()
    ctx = load_session_context("nokuru", nokuru_root, workflow_id="dev")
    engine = SessionEngine(ctx)
    collect_events(engine, "hello world サンプル", stream=False)
    return engine.state.logger.session_id


def test_list_sandbox_artifact_files_skips_run_all(tmp_path: Path) -> None:
    session_dir = tmp_path / "sandbox" / "session_test"
    session_dir.mkdir(parents=True)
    (session_dir / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (session_dir / "run_all.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    files = list_sandbox_artifact_files(session_dir)
    assert len(files) == 1
    assert files[0].name == "hello.py"


def test_apply_copies_from_sandbox(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _run_dev_session(nokuru_root, monkeypatch)
    session_dir = sandbox_session_dir(nokuru_root, session_id)
    assert session_dir.is_dir()
    assert list_sandbox_artifact_files(session_dir)

    result = apply_session_artifacts(nokuru_root, session_id, commit=False)
    assert result.ok, result.message
    assert result.paths
    for path in result.paths:
        assert path.is_file()
        assert path.is_relative_to(nokuru_root)


def test_apply_from_log_when_sandbox_missing(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _run_dev_session(nokuru_root, monkeypatch)
    session_dir = sandbox_session_dir(nokuru_root, session_id)
    assert session_dir.is_dir()

    import shutil

    shutil.rmtree(session_dir)
    assert not session_dir.exists()

    result = apply_session_artifacts(nokuru_root, session_id, commit=False)
    assert result.ok, result.message
    assert session_dir.is_dir()
    assert list_sandbox_artifact_files(session_dir)


def test_apply_aborts_when_dirty(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_clean_git(nokuru_root)
    session_id = _run_dev_session(nokuru_root, monkeypatch)
    (nokuru_root / "dirty.txt").write_text("x", encoding="utf-8")
    assert has_uncommitted_changes(nokuru_root)

    result = apply_session_artifacts(nokuru_root, session_id, commit=True)
    assert not result.ok
    assert "未コミット" in result.message
    assert not (nokuru_root / "hello.py").exists()


def test_apply_git_commit_when_clean(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_clean_git(nokuru_root)
    session_id = _run_dev_session(nokuru_root, monkeypatch)
    assert not has_uncommitted_changes(nokuru_root)

    result = apply_session_artifacts(nokuru_root, session_id, commit=True)
    assert result.ok, result.message
    assert result.git is not None
    assert result.git.ok, result.git.message
    assert result.git.commit_hash
    assert not has_uncommitted_changes(nokuru_root)


def test_apply_git_skipped_when_not_repo(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _run_dev_session(nokuru_root, monkeypatch)
    assert not is_git_repo(nokuru_root)

    result = apply_session_artifacts(nokuru_root, session_id, commit=True)
    assert result.ok, result.message
    assert result.git is not None
    assert not result.git.ok
    assert "スキップ" in result.git.message


def test_apply_commit_message_uses_user_input() -> None:
    records = [
        {"type": "session_meta", "organization": "solo"},
        {"type": "user_input", "text": "バグ修正のテスト"},
    ]
    msg = apply_commit_message("abc123", records)
    assert "apply:" in msg
    assert "バグ修正" in msg
    assert "abc123" in msg


def test_apply_with_new_branch(nokuru_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init_clean_git(nokuru_root)
    session_id = _run_dev_session(nokuru_root, monkeypatch)

    result = apply_session_artifacts(
        nokuru_root,
        session_id,
        commit=True,
        new_branch=f"studio/{session_id}",
    )
    assert result.ok, result.message
    assert result.git is not None and result.git.ok

    show = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=nokuru_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert show.stdout.strip() == f"studio/{session_id}"

"""Phase 5b meeting minutes tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.minutes import (
    default_topic_slug,
    document_to_markdown,
    load_existing_minutes,
    mock_minutes_document,
    save_minutes_from_session,
    slugify_topic,
)
from studio.vcs import has_uncommitted_changes

REPO_ROOT = Path(__file__).resolve().parents[2]


def _init_clean_git(root: Path) -> None:
    (root / ".gitignore").write_text("sessions/\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _run_session(studio_root: Path, user_text: str) -> str:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, user_text, stream=False)
    return engine.state.logger.session_id


def test_slugify_topic() -> None:
    assert slugify_topic("Camp Planning!") == "camp_planning"
    assert slugify_topic("   ") == "session"
    assert slugify_topic("a" * 100).endswith("a")
    assert len(slugify_topic("a" * 100)) <= 64


def test_mock_minutes_document_from_session(studio_root: Path) -> None:
    session_id = _run_session(studio_root, "来週のキャンプ計画")
    from studio.session_resume import load_effective_records

    records = load_effective_records(studio_root, session_id)
    doc = mock_minutes_document(
        org_id="solo",
        topic="camp_planning",
        session_id=session_id,
        records=records,
    )
    assert doc["topic"] == "camp_planning"
    assert session_id in doc["source_sessions"]
    assert doc["minutes"]["decisions"]
    assert doc["minutes"]["evidence"]


def test_save_minutes_writes_json_and_md(studio_root: Path) -> None:
    session_id = _run_session(studio_root, "議事録テスト")
    result = save_minutes_from_session(
        studio_root,
        session_id,
        topic="minutes_test",
        commit=False,
    )
    assert result.ok, result.message
    assert result.path is not None and result.path.is_file()
    assert result.md_path is not None and result.md_path.is_file()
    data = json.loads(result.path.read_text(encoding="utf-8"))
    assert data["topic"] == "minutes_test"
    md = result.md_path.read_text(encoding="utf-8")
    assert "# 議事録:" in md
    assert "## 決定事項" in md
    assert session_id in data["source_sessions"]


def test_save_minutes_merges_existing(studio_root: Path) -> None:
    session_id = _run_session(studio_root, "first topic")
    first = save_minutes_from_session(
        studio_root,
        session_id,
        topic="merge_topic",
        commit=False,
    )
    assert first.ok
    existing = load_existing_minutes(first.path)
    assert existing is not None
    existing["minutes"]["decisions"].append("既存の決定")
    first.path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    session_id2 = _run_session(studio_root, "second topic")
    second = save_minutes_from_session(
        studio_root,
        session_id2,
        topic="merge_topic",
        commit=False,
    )
    assert second.ok
    merged = json.loads(second.path.read_text(encoding="utf-8"))
    assert "既存の決定" in merged["minutes"]["decisions"]
    assert session_id in merged["source_sessions"]
    assert session_id2 in merged["source_sessions"]


def test_minutes_document_validates_against_schema(studio_root: Path) -> None:
    session_id = _run_session(studio_root, "schema check")
    result = save_minutes_from_session(studio_root, session_id, commit=False)
    assert result.ok
    schema = json.loads((REPO_ROOT / "schemas" / "minutes.schema.json").read_text(encoding="utf-8"))
    document = json.loads(result.path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(document)


def test_git_commit_when_clean(studio_root: Path) -> None:
    _init_clean_git(studio_root)
    session_id = _run_session(studio_root, "git commit test")
    assert not has_uncommitted_changes(studio_root)

    result = save_minutes_from_session(
        studio_root,
        session_id,
        topic="git_topic",
        commit=True,
    )
    assert result.ok
    assert result.git is not None
    assert result.git.ok
    assert result.git.commit_hash
    assert not has_uncommitted_changes(studio_root)


def test_git_commit_skipped_when_dirty(studio_root: Path) -> None:
    _init_clean_git(studio_root)
    session_id = _run_session(studio_root, "dirty tree")
    (studio_root / "dirty.txt").write_text("x", encoding="utf-8")
    assert has_uncommitted_changes(studio_root)

    result = save_minutes_from_session(
        studio_root,
        session_id,
        topic="dirty_topic",
        commit=True,
    )
    assert result.ok
    assert result.path is not None and result.path.is_file()
    assert result.git is not None
    assert not result.git.ok
    assert "未コミット" in result.git.message


def test_document_to_markdown_renders_sections() -> None:
    doc = {
        "topic": "camp_planning",
        "updated_at": "2026-07-14T12:00:00+09:00",
        "source_sessions": ["20260714_120000"],
        "minutes": {
            "decisions": ["行き先を3候補に絞る"],
            "open_issues": ["予算"],
            "actions": [{"owner": "hinata", "task": "アンケート", "due": "2026-07-20"}],
            "evidence": [{"session": "20260714_120000", "turns": [1, 2]}],
            "next_agenda": ["最終決定"],
        },
    }
    md = document_to_markdown(doc)
    assert "## 決定事項" in md
    assert "行き先を3候補に絞る" in md
    assert "| hinata | アンケート | 2026-07-20 |" in md
    assert "20260714_120000" in md


def test_default_topic_from_first_user_input(studio_root: Path) -> None:
    session_id = _run_session(studio_root, "Auto Topic Name")
    from studio.session_resume import load_effective_records

    records = load_effective_records(studio_root, session_id)
    slug = default_topic_slug(records, session_id)
    assert slug == "auto_topic_name"

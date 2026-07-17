"""Fixed sample data under samples/ (design.md §10.5)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.minutes import document_to_markdown, mock_minutes_document
from studio.session_report import generate_session_markdown, read_jsonl
from studio.session_resume import load_effective_records, load_resumed_session

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SESSION_PATH = REPO_ROOT / "samples" / "sessions" / "nokuru_camp_planning.jsonl"
SAMPLE_MINUTES_PATH = REPO_ROOT / "samples" / "minutes" / "nokuru" / "camp_planning.json"
SAMPLE_SESSION_ID = "20260714_120000"


def _sample_records() -> list[dict]:
    return read_jsonl(SAMPLE_SESSION_PATH)


@pytest.fixture
def nokuru_mock_mapping(studio_root: Path) -> Path:
    repo = REPO_ROOT
    for name in (
        "workflows",
        "organizations/nokuru",
        "talents/hinata.json",
        "talents/satsuki.json",
        "talents/kaede.json",
        "samples",
    ):
        src = repo / name
        dest = studio_root / name
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        elif src.is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
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


def test_sample_session_jsonl_structure() -> None:
    records = _sample_records()
    types = [r["type"] for r in records]
    assert types[0] == "session_meta"
    assert types[-1] == "session_end"
    meta = records[0]
    assert meta["organization"] == "nokuru"
    assert meta["workflow"] == "meeting"
    assert records[1]["type"] == "user_input"
    assert records[1]["text"] == "秋キャンプの行き先"
    steps = [r for r in records if r["type"] == "step"]
    assert [s["talent_id"] for s in steps] == ["hinata", "satsuki", "kaede", "hinata"]
    assert any("【結論】" in s["text"] for s in steps)


def test_sample_session_markdown_report() -> None:
    records = _sample_records()
    markdown = generate_session_markdown(records, session_id=SAMPLE_SESSION_ID)
    assert "```mermaid" in markdown
    assert "秋キャンプの行き先" in markdown
    assert "MOCK:hinata:step1" in markdown


def test_sample_minutes_validates_schema() -> None:
    document = json.loads(SAMPLE_MINUTES_PATH.read_text(encoding="utf-8"))
    schema = json.loads(
        (REPO_ROOT / "schemas" / "minutes.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(document)
    assert document["topic"] == "camp_planning"
    assert SAMPLE_SESSION_ID in document["source_sessions"]
    md = document_to_markdown(document)
    assert "## 決定事項" in md
    assert "候補地3件のアンケート作成" in md


def test_sample_session_resume_from_copy(nokuru_mock_mapping: Path) -> None:
    sessions_dir = nokuru_mock_mapping / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_SESSION_PATH, sessions_dir / f"{SAMPLE_SESSION_ID}.jsonl")

    resumed = load_resumed_session(nokuru_mock_mapping, SAMPLE_SESSION_ID)
    assert resumed.org_id == "nokuru"
    assert resumed.workflow_id == "meeting"
    assert resumed.replay_messages
    assert any("秋キャンプ" in m.get("content", "") for m in resumed.replay_messages)


def test_sample_minutes_mock_matches_session(nokuru_mock_mapping: Path) -> None:
    sessions_dir = nokuru_mock_mapping / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_SESSION_PATH, sessions_dir / f"{SAMPLE_SESSION_ID}.jsonl")
    records = load_effective_records(nokuru_mock_mapping, SAMPLE_SESSION_ID)
    doc = mock_minutes_document(
        org_id="nokuru",
        topic="camp_planning",
        session_id=SAMPLE_SESSION_ID,
        records=records,
    )
    committed = json.loads(SAMPLE_MINUTES_PATH.read_text(encoding="utf-8"))
    assert doc["topic"] == committed["topic"]
    assert committed["minutes"]["decisions"][0] in doc["minutes"]["decisions"]


def test_regenerate_sample_session_matches_committed(
    nokuru_mock_mapping: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard: mock 再実行結果が committed sample と同型・同順序であること。"""
    monkeypatch.setenv("STUDIO_MOCK_MARKER", "【結論】")
    MockAssistant.reset()
    ctx = load_session_context("nokuru", nokuru_mock_mapping, workflow_id="meeting")
    engine = SessionEngine(ctx)
    collect_events(engine, "秋キャンプの行き先", stream=False, no_user_context=True)
    fresh = read_jsonl(engine.state.logger.log_path)
    committed = _sample_records()

    assert len(fresh) == len(committed)
    for fresh_row, committed_row in zip(fresh, committed, strict=True):
        assert fresh_row["type"] == committed_row["type"]
        if fresh_row["type"] == "session_end":
            assert fresh_row["total_cost"] == committed_row["total_cost"]
            continue
        if fresh_row["type"] in ("session_meta", "state_snapshot"):
            assert fresh_row == committed_row
            continue
        if fresh_row["type"] == "step":
            assert fresh_row["talent_id"] == committed_row["talent_id"]
            assert fresh_row["phase_type"] == committed_row["phase_type"]
            continue
        assert fresh_row == committed_row

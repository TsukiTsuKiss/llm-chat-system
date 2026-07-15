"""Phase 5d-b user_context update / summary tests."""

from __future__ import annotations

import json
from pathlib import Path

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.user_context import load_user_context_text, resolve_user_context
from studio.user_context_update import (
    apply_context_draft,
    draft_path,
    merge_draft_into_context,
    mock_context_draft,
    save_context_draft_from_session,
    save_summary_from_context,
)


def test_mock_context_draft_has_proposal_section() -> None:
    records = [
        {"type": "user_input", "text": "失敗学について"},
        {"type": "step", "talent_id": "solo_bot", "text": "応答"},
    ]
    draft = mock_context_draft(session_id="sess1", records=records)
    assert "## 提案追記（蓄積メモへ）" in draft
    assert "失敗学について" in draft


def test_merge_draft_appends_to_accumulation_section() -> None:
    current = "# ctx\n\n## 蓄積メモ\n\n- 既存\n"
    draft = (
        "# draft\n\n## 提案追記（蓄積メモへ）\n\n"
        "- （セッション `s1`）気づき: テスト\n"
    )
    merged = merge_draft_into_context(current, draft, "s1")
    assert "## 蓄積メモ" in merged
    assert "既存" in merged
    assert "気づき: テスト" in merged
    assert "session `s1`" in merged


def test_save_and_apply_context_draft(studio_root: Path) -> None:
    MockAssistant.reset()
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text(
        "# my\n\n## 蓄積メモ\n\n",
        encoding="utf-8",
    )
    (studio_root / "studio_config.json").write_text(
        json.dumps({"user_context": {"enabled": True, "path": "user_context/my_context.md"}}),
        encoding="utf-8",
    )

    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "hello context", stream=False)
    session_id = engine.state.logger.session_id

    draft_result = save_context_draft_from_session(studio_root, session_id)
    assert draft_result.ok
    assert draft_path(studio_root, session_id).is_file()

    apply_result = apply_context_draft(studio_root, session_id)
    assert apply_result.ok
    text = (uc_dir / "my_context.md").read_text(encoding="utf-8")
    assert "hello context" in text or "議題" in text


def test_summary_fallback_when_over_max_chars(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    long_body = "- " + ("あ" * 200) + "\n" * 40
    (uc_dir / "my_context.md").write_text(
        f"# ctx\n\n## 興味\n\n{long_body}",
        encoding="utf-8",
    )
    (uc_dir / "my_context.summary.md").write_text(
        "# 要約\n\n- 短い要約\n",
        encoding="utf-8",
    )
    config = {
        "user_context": {
            "enabled": True,
            "path": "user_context/my_context.md",
            "max_chars": 100,
        }
    }
    loaded = load_user_context_text(studio_root, config)
    assert loaded is not None
    assert "短い要約" in loaded
    assert len(loaded) < len(long_body)


def test_save_summary_from_context(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text(
        "# ctx\n\n## 興味\n\n- 天体写真\n",
        encoding="utf-8",
    )
    (studio_root / "studio_config.json").write_text(
        json.dumps(
            {
                "default_org": "solo",
                "user_context": {"enabled": True, "path": "user_context/my_context.md"},
            }
        ),
        encoding="utf-8",
    )
    result = save_summary_from_context(studio_root)
    assert result.ok
    summary = uc_dir / "my_context.summary.md"
    assert summary.is_file()
    assert "天体写真" in summary.read_text(encoding="utf-8")


def test_resolve_user_context_loaded_with_summary_path(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("- item\n", encoding="utf-8")
    config = {"user_context": {"enabled": True, "path": "user_context/my_context.md"}}
    resolution = resolve_user_context(studio_root, config)
    assert resolution.enabled
    assert resolution.loaded
    assert resolution.text is not None

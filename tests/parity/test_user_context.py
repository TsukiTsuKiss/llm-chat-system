"""Phase 5d-a user context tests (design.md Appendix D)."""

from __future__ import annotations

import json
from pathlib import Path

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.prompts import build_system_prompt
from studio.user_context import (
    load_user_context_text,
    resolve_user_context,
    session_user_context_enabled,
)


def test_build_system_prompt_injects_user_context() -> None:
    talent = {"personality": "P", "system_prompt": "SP"}
    org = {"mission": "M", "culture": ["C1"]}
    prompt = build_system_prompt(
        talent,
        org,
        "solo",
        "bot",
        user_context_text="失敗＝予測と現実のズレ",
    )
    assert "【ユーザーコンテキスト】" in prompt
    assert "失敗＝予測と現実のズレ" in prompt
    assert prompt.index("【ミッション】") < prompt.index("【ユーザーコンテキスト】")


def test_build_system_prompt_omits_user_context_when_none() -> None:
    talent = {"system_prompt": "SP"}
    org = {}
    prompt = build_system_prompt(talent, org, "solo", "bot", user_context_text=None)
    assert "【ユーザーコンテキスト】" not in prompt


def test_resolve_user_context_loads_file(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("テスト用コンテキスト\n", encoding="utf-8")
    studio_root.joinpath("studio_config.json").write_text(
        json.dumps({"user_context": {"enabled": True, "path": "user_context/my_context.md"}}),
        encoding="utf-8",
    )

    resolution = resolve_user_context(
        studio_root,
        json.loads((studio_root / "studio_config.json").read_text(encoding="utf-8")),
    )
    assert resolution.enabled
    assert resolution.loaded
    assert resolution.text == "テスト用コンテキスト"


def test_no_user_context_disables_injection(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ignored\n", encoding="utf-8")

    resolution = resolve_user_context(
        studio_root,
        {"user_context": {"enabled": True}},
        no_user_context=True,
    )
    assert not resolution.enabled
    assert resolution.text is None


def test_session_meta_records_user_context_flag(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ctx\n", encoding="utf-8")

    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "hello", stream=False)
    log_path = engine.state.logger.log_path  # type: ignore[union-attr]
    meta = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["generation"]["user_context"] is True


def test_session_meta_user_context_false_with_cli_flag(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    uc_dir.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ctx\n", encoding="utf-8")

    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "hello", stream=False, no_user_context=True)
    log_path = engine.state.logger.log_path  # type: ignore[union-attr]
    meta = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["generation"]["user_context"] is False


def test_session_user_context_enabled_respects_global_off() -> None:
    assert not session_user_context_enabled({"user_context": {"enabled": False}})
    assert session_user_context_enabled({"user_context": {"enabled": True}})
    assert not session_user_context_enabled(
        {"user_context": {"enabled": True}},
        no_user_context=True,
    )


def test_load_user_context_text_missing_file(studio_root: Path) -> None:
    assert load_user_context_text(studio_root, {"user_context": {"enabled": True}}) is None

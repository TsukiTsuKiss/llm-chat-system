"""Phase 4a Web UI event rendering parity tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.engine import EngineEvent, SessionEngine, collect_events
from studio.loader import load_session_context
from studio.web_ui import (
    ChatEventRenderer,
    FILE_ONLY_DEFAULT,
    IDLE_STATUS,
    WebSession,
    handle_chat_submit,
    list_organizations,
    list_workflows,
    resolve_user_input_with_attachments,
    workflow_available_for_org,
    workflow_dropdown_choices,
    workflow_dropdown_choices_for_org,
    resolve_workflow_value_for_org,
)


def test_list_organizations_and_workflows(studio_root: Path) -> None:
    orgs = list_organizations(studio_root)
    assert "solo" in orgs
    wfs = list_workflows(studio_root)
    assert isinstance(wfs, list)
    choices = workflow_dropdown_choices(studio_root)
    assert choices[0][1] == ""


def _copy_nokuru_tree(studio_root: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    import json
    import shutil

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
                for path in src.glob("*.json"):
                    shutil.copy2(path, dest / path.name)

    mapping = {
        "hinata": {"assistant": "mock"},
        "satsuki": {"assistant": "mock"},
        "kaede": {"assistant": "mock"},
    }
    (studio_root / "organizations" / "nokuru" / "model_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_workflow_dropdown_choices_for_org_marks_unbound(studio_root: Path) -> None:
    _copy_nokuru_tree(studio_root)
    choices = workflow_dropdown_choices_for_org(studio_root, "nokuru")
    labels = {label for label, _ in choices}
    values = {value for _, value in choices}
    assert "quiz" in values
    assert any("quiz" in label and "未設定" in label for label in labels)
    assert "meeting" in values
    assert resolve_workflow_value_for_org(studio_root, "nokuru", "quiz") == "meeting"
    assert workflow_available_for_org(studio_root, "nokuru", "quiz") is False
    assert workflow_available_for_org(studio_root, "nokuru", "meeting") is True
    assert workflow_available_for_org(studio_root, "nokuru", "discussion") is True


def test_renderer_step_done_includes_display_name() -> None:
    renderer = ChatEventRenderer()
    renderer.apply(
        EngineEvent(
            "step_start",
            {"talent_id": "solo_bot", "display_name": "ソロBot", "action": "reply"},
        )
    )
    renderer.apply(
        EngineEvent(
            "step_done",
            {
                "talent_id": "solo_bot",
                "display_name": "ソロBot",
                "assistant": "mock",
                "text": "hello",
                "elapsed": 0.0,
                "tokens": {"in": 0, "out": 0, "source": "none"},
                "cost": 0.0,
            },
        )
    )
    assert len(renderer.messages) == 1
    assert "ソロBot" in renderer.messages[0]["content"]
    assert "hello" in renderer.messages[0]["content"]


def test_renderer_streaming_chunks() -> None:
    renderer = ChatEventRenderer()
    renderer.apply(
        EngineEvent("step_start", {"talent_id": "a", "display_name": "A", "action": "x"})
    )
    renderer.apply(EngineEvent("chunk", {"talent_id": "a", "text": "hel"}))
    renderer.apply(EngineEvent("chunk", {"talent_id": "a", "text": "lo"}))
    renderer.apply(
        EngineEvent(
            "step_done",
            {
                "talent_id": "a",
                "display_name": "A",
                "assistant": "mock",
                "text": "hello",
                "elapsed": 0.1,
                "tokens": {"in": 1, "out": 2, "source": "none"},
                "cost": 0.0,
            },
        )
    )
    assert "hello" in renderer.messages[0]["content"]


def test_web_session_direct_chat_mock(studio_root: Path) -> None:
    MockAssistant.reset()
    session = WebSession(root=studio_root)
    updates = list(
        handle_chat_submit(
            session,
            "こんにちは",
            org_id="solo",
            workflow_value="",
            stream=False,
            temperature=0.7,
        )
    )
    assert updates
    messages, status, show_choice, _placeholder, clear_upload = updates[-1]
    assert any(m["role"] == "user" and "こんにちは" in m["content"] for m in messages)
    assert any(m["role"] == "assistant" for m in messages)
    assert show_choice is False
    assert status == IDLE_STATUS
    assert status != "実行中…"
    assert clear_upload is False
    assert session.engine is not None


def test_web_session_workflow_discussion(studio_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workflows_src = Path(__file__).resolve().parents[2] / "workflows"
    if workflows_src.is_dir():
        dest = studio_root / "workflows"
        dest.mkdir(exist_ok=True)
        for wf in workflows_src.glob("*.json"):
            (dest / wf.name).write_text(wf.read_text(encoding="utf-8"), encoding="utf-8")

    trio_src = Path(__file__).resolve().parents[2] / "organizations" / "trio"
    if trio_src.is_dir():
        import shutil

        shutil.copytree(trio_src, studio_root / "organizations" / "trio", dirs_exist_ok=True)
        talents_src = Path(__file__).resolve().parents[2] / "talents"
        for name in ("alpha.json", "beta.json", "gamma.json"):
            src = talents_src / name
            if src.exists():
                shutil.copy2(src, studio_root / "talents" / name)

    mapping = {
        "alpha": {"assistant": "mock"},
        "beta": {"assistant": "mock"},
        "gamma": {"assistant": "mock"},
    }
    (studio_root / "organizations" / "trio" / "model_mapping.json").write_text(
        __import__("json").dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    MockAssistant.reset()
    session = WebSession(root=studio_root)
    updates = list(
        handle_chat_submit(
            session,
            "テスト議題",
            org_id="trio",
            workflow_value="discussion",
            stream=False,
            temperature=0.7,
        )
    )
    assert updates
    messages = updates[-1][0]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1


def test_collect_events_via_engine_matches_renderer(studio_root: Path) -> None:
    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    events = collect_events(engine, "ping", stream=False)
    renderer = ChatEventRenderer()
    renderer.add_user("ping")
    for event in events:
        renderer.apply(event)
    assert any("ping" in m["content"] for m in renderer.messages if m["role"] == "user")


def test_resolve_user_input_files_only(studio_root: Path) -> None:
    sample = studio_root / "sample.txt"
    sample.write_text("hello attachment", encoding="utf-8")
    prompt, display, context, names = resolve_user_input_with_attachments(
        "",
        [str(sample)],
        {},
    )
    assert prompt == FILE_ONLY_DEFAULT
    assert FILE_ONLY_DEFAULT in display
    assert "sample.txt" in display
    assert "hello attachment" in context
    assert names == ["sample.txt"]


def test_resolve_user_input_rejects_missing_file(studio_root: Path) -> None:
    from studio.validation import StudioValidationError

    with pytest.raises(StudioValidationError):
        resolve_user_input_with_attachments(
            "hi",
            [str(studio_root / "missing.txt")],
            {},
        )


def test_web_session_file_only_submit_clears_upload(studio_root: Path) -> None:
    MockAssistant.reset()
    sample = studio_root / "note.md"
    sample.write_text("# Title\nbody", encoding="utf-8")
    session = WebSession(root=studio_root)
    updates = list(
        handle_chat_submit(
            session,
            "",
            org_id="solo",
            workflow_value="",
            stream=False,
            temperature=0.7,
            files=[str(sample)],
            upload_limits={},
        )
    )
    assert updates
    first = updates[0]
    assert first[4] is True
    messages = updates[-1][0]
    assert any(
        m["role"] == "user"
        and FILE_ONLY_DEFAULT in m["content"]
        and "note.md" in m["content"]
        for m in messages
    )
    assert any(m["role"] == "assistant" for m in messages)

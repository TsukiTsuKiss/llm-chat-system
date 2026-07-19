"""Phase 4a Web UI event rendering parity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.assistants import MockAssistant
from studio.engine import EngineEvent, SessionEngine, collect_events
from studio.loader import load_session_context
from studio.rag_ui import build_rag_ui_state
from studio.web_ui import (
    ChatEventRenderer,
    FILE_ONLY_DEFAULT,
    IDLE_STATUS,
    WebSession,
    handle_chat_submit,
    last_rag_injection_preview,
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
    config_path = studio_root / "organizations" / "nokuru" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.get("workflow_bindings", {}).pop("quiz", None)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

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


def test_workflow_dropdown_nokuru_quiz_available(studio_root: Path) -> None:
    _copy_nokuru_tree(studio_root)
    assert workflow_available_for_org(studio_root, "nokuru", "quiz") is True
    choices = workflow_dropdown_choices_for_org(studio_root, "nokuru")
    quiz_labels = [label for label, value in choices if value == "quiz"]
    assert quiz_labels == ["quiz"]


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


def test_build_rag_ui_state_reflects_config(studio_root: Path) -> None:
    import json

    studio_root.joinpath("studio_config.json").write_text(
        json.dumps({"user_context": {"rag": {"enabled": True}}}),
        encoding="utf-8",
    )
    state = build_rag_ui_state(studio_root)
    assert state.available
    assert state.default_rag is True
    assert "プレビュー" in state.corpus_preview or state.corpus_preview == ""

    studio_root.joinpath("studio_config.json").write_text(
        json.dumps({"user_context": {"rag": {"enabled": False}}}),
        encoding="utf-8",
    )
    state = build_rag_ui_state(studio_root)
    assert not state.available
    assert state.default_rag is False
    assert "enabled" in state.panel_md
    import json

    uc_dir = studio_root / "user_context"
    corpus = uc_dir / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ctx\n", encoding="utf-8")
    (corpus / "notes.md").write_text("## rag\n\nloader parity keyword\n", encoding="utf-8")
    studio_root.joinpath("studio_config.json").write_text(
        json.dumps(
            {
                "user_context": {
                    "enabled": True,
                    "rag": {"enabled": True, "top_k": 3},
                }
            }
        ),
        encoding="utf-8",
    )

    from studio.user_context_rag import reindex_corpus

    config = json.loads((studio_root / "studio_config.json").read_text(encoding="utf-8"))
    reindex_corpus(studio_root, config)

    MockAssistant.reset()
    session = WebSession(root=studio_root)
    list(
        handle_chat_submit(
            session,
            "loader parity",
            org_id="solo",
            workflow_value="",
            stream=False,
            temperature=0.7,
            user_context=True,
            user_context_rag=True,
        )
    )
    assert session.engine is not None
    assert session.engine.state is not None
    assert session.engine.state.user_context_rag_enabled
    assert session.engine.state.last_context_chunks
    preview = last_rag_injection_preview(session)
    assert "loader" in preview or "parity" in preview


def test_web_session_user_context_rag_off(studio_root: Path) -> None:
    import json

    uc_dir = studio_root / "user_context"
    corpus = uc_dir / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "notes.md").write_text("## rag\n\nkeyword\n", encoding="utf-8")
    studio_root.joinpath("studio_config.json").write_text(
        json.dumps({"user_context": {"enabled": True, "rag": {"enabled": True}}}),
        encoding="utf-8",
    )

    from studio.user_context_rag import reindex_corpus

    config = json.loads((studio_root / "studio_config.json").read_text(encoding="utf-8"))
    reindex_corpus(studio_root, config)

    MockAssistant.reset()
    session = WebSession(root=studio_root)
    list(
        handle_chat_submit(
            session,
            "keyword",
            org_id="solo",
            workflow_value="",
            stream=False,
            temperature=0.7,
            user_context=True,
            user_context_rag=False,
        )
    )
    assert session.engine is not None
    assert session.engine.state is not None
    assert not session.engine.state.last_context_chunks
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


def test_resume_branch_preserves_user_context_rag(studio_root: Path) -> None:
    import json

    studio_root.joinpath("studio_config.json").write_text(
        json.dumps({"user_context": {"enabled": True, "rag": {"enabled": True}}}),
        encoding="utf-8",
    )

    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "first turn", stream=False)
    parent_id = engine.state.logger.session_id

    from studio.session_resume import load_resumed_session

    resumed = load_resumed_session(studio_root, parent_id)

    session = WebSession(root=studio_root)
    session.resume_branch(
        resumed,
        ctx,
        stream=False,
        temperature=0.7,
        user_context=True,
        user_context_rag=True,
    )
    assert session.engine.state.user_context_rag_enabled is True

    collect_events(session.engine, "branch turn", stream=False)
    child_id = session.engine.state.logger.session_id
    child_meta = json.loads(
        (studio_root / "sessions" / f"{child_id}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert child_meta["generation"]["user_context_rag"] is True

    session2 = WebSession(root=studio_root)
    session2.resume_branch(
        resumed,
        ctx,
        stream=False,
        temperature=0.7,
        user_context=True,
        user_context_rag=False,
    )
    assert session2.engine.state.user_context_rag_enabled is False

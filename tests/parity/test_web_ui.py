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
    initial_workflow_for_org,
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
        "talents/yuki.json",
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
        "yuki": {"assistant": "mock"},
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


def test_initial_workflow_prefers_request_then_org_default(studio_root: Path) -> None:
    _copy_nokuru_tree(studio_root)
    assert initial_workflow_for_org(studio_root, "nokuru") == "meeting"
    assert initial_workflow_for_org(studio_root, "nokuru", "quiz") == "quiz"
    assert initial_workflow_for_org(studio_root, "nokuru", "no_such_workflow") == "meeting"
    assert initial_workflow_for_org(studio_root, "solo") == ""


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


def test_renderer_puts_notice_before_active_bubble() -> None:
    renderer = ChatEventRenderer()
    renderer.apply(
        EngineEvent("step_start", {"talent_id": "solo_bot", "display_name": "ソロBot"})
    )
    renderer.apply(EngineEvent("notice", {"text": "ウェブ検索はこのプロバイダのメニューにない"}))
    renderer.apply(
        EngineEvent(
            "step_done",
            {
                "talent_id": "solo_bot",
                "display_name": "ソロBot",
                "text": "本日のニュースは…",
                "elapsed": 0.0,
                "tokens": {"in": 0, "out": 0, "source": "none"},
                "cost": 0.0,
            },
        )
    )
    assert "メニューにない" in renderer.messages[0]["content"]
    assert "本日のニュース" in renderer.messages[1]["content"]


def test_process_events_throttles_chunk_updates(studio_root: Path) -> None:
    from studio.web_ui import process_events

    def events():
        yield EngineEvent("step_start", {"talent_id": "a", "display_name": "A"})
        for _ in range(300):
            yield EngineEvent("chunk", {"talent_id": "a", "text": "x"})
        yield EngineEvent("step_done", {"talent_id": "a", "display_name": "A", "text": "x" * 300})

    session = WebSession(root=studio_root)
    updates = list(process_events(session, events()))

    assert len(updates) < 20
    assert updates[-1][1] == IDLE_STATUS
    assert any("x" * 300 in m["content"] for m in updates[-1][0])


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


def test_ui_settings_are_recorded_and_restored(studio_root: Path, monkeypatch) -> None:
    from studio.session_resume import load_resumed_session
    from studio.web_ui import apply_session_resume

    settings = {
        "stream": False, "user_context": False, "user_context_rag": False,
        "web_search": False, "voice": False, "timing": True, "merge": False,
    }
    session = WebSession(root=studio_root, ui_settings=settings.copy())
    MockAssistant.reset()
    list(handle_chat_submit(
        session, "hello", org_id="solo", workflow_value="", stream=False, temperature=0.7,
        user_context=False, user_context_rag=False,
    ))
    logger = session.engine.state.logger
    session.ui_settings["web_search"] = True
    session.ui_settings["merge"] = True
    session.save_ui_settings()
    session.save_ui_settings()
    records = [json.loads(line) for line in logger.log_path.read_text(encoding="utf-8").splitlines()]
    saved = [record["settings"] for record in records if record["type"] == "ui_settings"]
    assert saved == [settings, session.ui_settings]
    assert load_resumed_session(studio_root, logger.session_id).ui_settings == session.ui_settings

    monkeypatch.setattr("studio.web_ui.missing_audio_files", lambda *_args: [])
    restored = WebSession(root=studio_root)
    result = apply_session_resume(
        restored, logger.session_id, stream=True, temperature=0.7,
        ui_settings={key: not value for key, value in session.ui_settings.items()},
    )
    assert restored.ui_settings == session.ui_settings
    assert restored.stream is False
    assert restored.user_context is False
    assert "保存されていない設定" not in result[2]


def test_settings_changed_at_session_start_are_recorded(studio_root: Path) -> None:
    settings = {"stream": False, "voice": False}
    session = WebSession(root=studio_root, ui_settings=settings.copy())
    MockAssistant.reset()
    updates = handle_chat_submit(
        session, "hello", org_id="solo", workflow_value="", stream=False, temperature=0.7,
    )
    next(updates)
    next(updates)
    assert session.engine is not None and session.engine.state is not None
    assert not session.engine.state.started
    session.ui_settings["voice"] = True
    list(updates)
    assert session.engine.state.logger is not None
    records = [
        json.loads(line)
        for line in session.engine.state.logger.log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["settings"] for record in records if record["type"] == "ui_settings"] == [
        settings, {"stream": False, "voice": True},
    ]


def test_resume_preserves_and_reports_unrecorded_settings(studio_root: Path, monkeypatch) -> None:
    from studio.web_ui import apply_session_resume

    MockAssistant.reset()
    engine = SessionEngine(load_session_context("solo", studio_root))
    collect_events(engine, "hello", stream=False)
    monkeypatch.setattr("studio.web_ui.missing_audio_files", lambda *_args: [])
    current = {
        "stream": True, "user_context": True, "user_context_rag": True,
        "web_search": True, "voice": True, "timing": False, "merge": True,
    }
    restored = WebSession(root=studio_root)
    result = apply_session_resume(
        restored, engine.state.logger.session_id, stream=True, temperature=0.7, ui_settings=current,
    )
    assert restored.ui_settings["stream"] is False
    assert restored.ui_settings["web_search"] is True
    assert restored.ui_settings["voice"] is True
    assert restored.ui_settings["timing"] is False
    assert "ウェブ検索" in result[2] and "読み上げ" in result[2]


def test_resume_infers_voice_only_when_not_saved(studio_root: Path, monkeypatch) -> None:
    from studio.web_ui import apply_session_resume

    MockAssistant.reset()
    engine = SessionEngine(load_session_context("solo", studio_root))
    collect_events(engine, "hello", stream=False)
    logger = engine.state.logger
    audio_dir = studio_root / "sessions" / "audio" / logger.session_id
    audio_dir.mkdir(parents=True)
    timeline = audio_dir / "timeline.jsonl"
    monkeypatch.setattr("studio.web_ui.missing_audio_files", lambda *_args: [])
    current = {
        "stream": True, "user_context": True, "user_context_rag": True,
        "web_search": False, "voice": False, "timing": True, "merge": False,
    }

    restored = WebSession(root=studio_root)
    timeline.write_text('{"kind":"utterance","file":"01.wav"}\n', encoding="utf-8")
    result = apply_session_resume(restored, logger.session_id, stream=True, temperature=0.7, ui_settings=current)
    assert restored.ui_settings["voice"] is False
    assert "音声記録から ON と推定" not in result[2]
    timeline.unlink()
    (audio_dir / "01.wav").write_bytes(b"audio")
    result = apply_session_resume(restored, logger.session_id, stream=True, temperature=0.7, ui_settings=current)
    assert restored.ui_settings["voice"] is False

    timeline.write_text('{"kind":"utterance","file":"01.wav"}\n', encoding="utf-8")
    result = apply_session_resume(restored, logger.session_id, stream=True, temperature=0.7, ui_settings=current)
    assert restored.ui_settings["voice"] is True
    assert "音声記録から ON と推定" in result[2]
    assert "最後の設定は不明" in result[2]
    assert "音声記録から ON と推定" in result[-1]

    logger.log_ui_settings({"voice": False})
    current["voice"] = True
    result = apply_session_resume(restored, logger.session_id, stream=True, temperature=0.7, ui_settings=current)
    assert restored.ui_settings["voice"] is False
    assert "音声記録から ON と推定" not in result[2]


def test_resume_restores_workflow_and_toggles_in_browser(studio_root: Path, monkeypatch) -> None:
    import socket
    import time

    from playwright.sync_api import sync_playwright
    import MultiRoleStudioWeb as web

    _copy_nokuru_tree(studio_root)
    (studio_root / "studio_config.json").write_text(
        json.dumps({"user_context": {"enabled": True, "rag": {"enabled": True}}}), encoding="utf-8"
    )
    saved = {
        "stream": False, "user_context": False, "user_context_rag": False,
        "web_search": True, "voice": True, "timing": False, "merge": True,
    }
    session_dir = studio_root / "sessions"
    session_dir.mkdir()
    session_id = "20261124_030249"
    records = [
        {"type": "session_meta", "organization": "nokuru", "workflow": "meeting", "talents": {},
         "generation": {"stream": True}},
        {"type": "ui_settings", "settings": {key: value for key, value in saved.items() if key != "voice"}},
        {"type": "user_input", "text": "first"},
    ]
    (session_dir / f"{session_id}.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    audio_dir = session_dir / "audio" / session_id
    audio_dir.mkdir(parents=True)
    (audio_dir / "timeline.jsonl").write_text('{"kind":"utterance","file":"01.wav"}\n', encoding="utf-8")
    (audio_dir / "01.wav").write_bytes(b"audio")

    class Monitor:
        def start(self):
            pass

        def states(self):
            return []

    monkeypatch.setattr(web, "engine_monitor", lambda _urls: Monitor())
    monkeypatch.setattr("studio.web_ui.missing_audio_files", lambda *_args: [])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    demo = web.build_ui(studio_root, cli_org="solo")
    try:
        demo.launch(server_name="127.0.0.1", server_port=port, prevent_thread_lock=True, quiet=True)
        with sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                pytest.skip("Playwright Chromium がインストールされていません")
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.get_by_role("tab", name="📄 セッション").click()
                page.get_by_role("button", name="再開", exact=True).click()
                page.get_by_label("ワークフロー", exact=True).wait_for(state="visible")
                page.wait_for_function(
                    "() => document.querySelectorAll('[role=tab]')[0].getAttribute('aria-selected') === 'true'"
                )
                page.wait_for_timeout(1200)
                assert page.get_by_label("組織", exact=True).input_value() == "nokuru"
                assert page.get_by_label("ワークフロー", exact=True).input_value() == "meeting"
                labels = {
                    "stream": "ストリーミング", "user_context": "ユーザーコンテキスト",
                    "user_context_rag": "コンテキスト RAG", "web_search": "ウェブ検索",
                    "voice": "読み上げ", "timing": "タイミング表示", "merge": "連続メッセージを1つにまとめる",
                }
                assert {key: page.get_by_label(label, exact=True).is_checked() for key, label in labels.items()} == saved
                assert "音声記録から ON と推定" in page.get_by_label("状態", exact=True).input_value()

                page.get_by_label("読み上げ", exact=True).uncheck()
                page.get_by_label("メッセージ", exact=True).fill("続き")
                page.get_by_role("button", name="送信", exact=True).click()
                deadline = time.monotonic() + 15
                branch_records = []
                branch_path = None
                while time.monotonic() < deadline:
                    for path in session_dir.glob("*.jsonl"):
                        if path.stem != session_id:
                            branch_path = path
                            branch_records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                    if any(record.get("type") == "ui_settings" for record in branch_records):
                        break
                    page.wait_for_timeout(100)
                branch_settings = next(record["settings"] for record in branch_records if record["type"] == "ui_settings")
                assert branch_records[0]["workflow"] == "meeting"
                assert branch_records[0]["parent_session_id"] == session_id
                assert branch_settings == {**saved, "voice": False}
                assert branch_path is not None
                from playwright.sync_api import expect

                expect(page.get_by_label("状態", exact=True)).to_have_value(IDLE_STATUS, timeout=15000)
                page.get_by_label("タイミング表示", exact=True).check()
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    branch_records = [json.loads(line) for line in branch_path.read_text(encoding="utf-8").splitlines()]
                    recorded = [record["settings"] for record in branch_records if record["type"] == "ui_settings"]
                    if recorded[-1]["timing"]:
                        break
                    page.wait_for_timeout(100)
                assert recorded[-1] == {**saved, "voice": False, "timing": True}

                page.get_by_role("tab", name="⚙️ 設定編集").click()
                page.get_by_role("tab", name="🏢 組織").click()
                page.get_by_label("組織 ID", exact=True).click()
                page.get_by_role("option", name="solo", exact=True).click()
                solo = json.loads((studio_root / "organizations" / "solo" / "config.json").read_text(encoding="utf-8"))
                expect(page.get_by_role("textbox", name="name", exact=True)).to_have_value(solo["name"], timeout=15000)
                page.get_by_role("button", name="組織 config を保存", exact=True).click()
                page.get_by_role("tab", name="💬 チャット").click()
                expect(page.get_by_label("組織", exact=True)).to_have_value("solo", timeout=15000)
                expected_workflow = resolve_workflow_value_for_org(studio_root, "solo", "meeting")
                expected_label = next(
                    label for label, value in workflow_dropdown_choices_for_org(studio_root, "solo")
                    if value == expected_workflow
                )
                expect(page.get_by_label("ワークフロー", exact=True)).to_have_value(expected_label)
                talent_id = solo["talent_ids"][0]
                talent_name = json.loads(
                    (studio_root / "talents" / f"{talent_id}.json").read_text(encoding="utf-8")
                )["name"]
                expect(page.get_by_text(talent_name, exact=False).first).to_be_visible(timeout=15000)
            finally:
                browser.close()
    finally:
        demo.close()


def test_workflow_availability_cache_follows_config_edits(studio_root: Path) -> None:
    _copy_nokuru_tree(studio_root)
    assert workflow_available_for_org(studio_root, "nokuru", "quiz") is True

    config_path = studio_root / "organizations" / "nokuru" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.get("workflow_bindings", {}).pop("quiz", None)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    assert workflow_available_for_org(studio_root, "nokuru", "quiz") is False

#!/usr/bin/env python3
"""MultiRoleStudio Web UI."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import gradio as gr

from studio.gradio_template import use_japanese_html_template
from studio.loader import load_studio_config
from studio.validation import StudioValidationError
from studio.settings_ui import SettingsHandles, build_settings_tab
from studio.sessions_ui import SessionsHandles, build_sessions_tab
from studio.rag_ui import (
    CORPUS_PREVIEW_PLACEHOLDER,
    RAG_DISABLED_HINT,
    build_rag_ui_state,
    corpus_panel_markdown,
    list_corpus_files,
    load_studio_config_for_ui,
    rag_available_in_config,
    read_corpus_file,
    run_reindex,
    search_preview_markdown,
)
from studio.web_ui import (
    WebSession,
    audio_finished_update,
    audio_started_update,
    engine_led_html,
    handle_chat_submit,
    handle_choice,
    initial_workflow_for_org,
    last_rag_injection_preview,
    list_organizations,
    live_timing_update,
    load_org_panel,
    next_audio_update,
    upload_limits_from_config,
    workflow_available_for_org,
    workflow_dropdown_for_org,
    workflow_unavailable_note,
)
from studio.voice import DEFAULT_BASE_URL, engine_monitor, parse_voicevox_urls
from web_input_utils import (
    stream_default_from_config,
    temperature_default_from_config,
    user_context_default_from_config,
)

VERSION = "0.8.1"

DEFAULT_ORG = os.getenv("MULTIROLESTUDIOWEB_ORG", "")
DEFAULT_PORT = int(os.getenv("MULTIROLESTUDIOWEB_PORT", "7862"))

STUDIO_WEB_CSS = """
.gradio-container footer { display: none !important; }
/* 全タブ共通: すべてのボタンを水色で統一（項目名の紫チップと区別） */
.gradio-container {
  --button-primary-background-fill: #38bdf8;
  --button-primary-background-fill-hover: #0ea5e9;
  --button-primary-border-color: #0ea5e9;
  --button-primary-border-color-hover: #0284c7;
  --button-primary-text-color: white;
  --button-secondary-background-fill: #38bdf8;
  --button-secondary-background-fill-hover: #0ea5e9;
  --button-secondary-border-color: #0ea5e9;
  --button-secondary-border-color-hover: #0284c7;
  --button-secondary-text-color: white;
  --button-secondary-text-color-hover: white;
  --button-cancel-background-fill: #38bdf8;
  --button-cancel-background-fill-hover: #0ea5e9;
  --button-cancel-border-color: #0ea5e9;
  --button-cancel-border-color-hover: #0284c7;
  --button-cancel-text-color: white;
}
.studio-id-row {
  align-items: flex-end !important;
  gap: 0.5rem !important;
}
.studio-action-btn {
  flex: 0 0 auto !important;
  align-self: flex-end !important;
}
.studio-action-btn button {
  min-height: 2.25rem !important;
  height: 2.25rem !important;
  white-space: nowrap;
}
.studio-chat-column {
  min-height: 0 !important;
}
#studio-chatbot {
  max-height: calc(100dvh - 20rem) !important;
}
/* 読み上げ中の発言（JS がクラスを付ける） */
#studio-chatbot .message-row.studio-playing {
  position: relative;
}
#studio-chatbot .message-row.studio-playing .message {
  background: rgba(56, 189, 248, 0.18) !important;
  border-color: #38bdf8 !important;
  box-shadow: 0 0 0 2px #38bdf8;
}
#studio-chatbot .message-row.studio-playing::before {
  content: "🔊";
  position: absolute;
  right: 12px;
  top: 6px;
  z-index: 1;
}
.studio-chat-footer {
  flex: 0 0 auto !important;
}
/* セッションタブ: レポート小窓は可変、操作ボタン行は常に viewport 内に残す */
#studio-session-panel {
  display: flex !important;
  flex-direction: column !important;
  box-sizing: border-box !important;
  /* タブ見出し・グローバルヘッダを除き、タブ内をほぼ全高で使う（下端 30px の余白） */
  min-height: calc(100dvh - 9rem - 30px) !important;
  height: calc(100dvh - 9rem - 30px) !important;
  max-height: calc(100dvh - 9rem - 30px) !important;
  overflow: hidden !important;
}
#studio-session-panel > *:not(.studio-session-report-wrap) {
  flex: 0 0 auto !important;
}
.studio-session-report-wrap {
  flex: 1 1 0 !important;
  min-height: 0 !important;
  max-height: none !important;
  overflow-y: auto !important;
  margin: 0.25rem 0 0.5rem;
}
#studio-session-actions,
#studio-session-context-actions {
  flex: 0 0 auto !important;
}
/* セッションレポート Mermaid: ノード内文字のコントラスト確保（Gradio ダーク UI 対策） */
.studio-session-report .mermaid foreignObject,
.studio-session-report .mermaid foreignObject div,
.studio-session-report .mermaid foreignObject p,
.studio-session-report .mermaid foreignObject span {
  color: #0f172a !important;
}
.studio-session-report .mermaid .nodeLabel,
.studio-session-report .mermaid .label {
  color: #0f172a !important;
}
.studio-session-report[data-flow-theme="dark"] .mermaid foreignObject,
.studio-session-report[data-flow-theme="dark"] .mermaid foreignObject div,
.studio-session-report[data-flow-theme="dark"] .mermaid foreignObject p,
.studio-session-report[data-flow-theme="dark"] .mermaid foreignObject span,
.studio-session-report[data-flow-theme="dark"] .mermaid .nodeLabel,
.studio-session-report[data-flow-theme="dark"] .mermaid .label {
  color: #f8fafc !important;
}
"""

CHATBOT_MIN_HEIGHT = 200
# 初回表示でメッセージ欄・送信ボタンが viewport 内に収まる高さ（リサイズ可）
CHATBOT_DEFAULT_HEIGHT = "clamp(200px, calc(100dvh - 22rem), 480px)"

DEFAULT_MSG_PLACEHOLDER = "メッセージを入力（Enter: 送信 / Shift+Enter: 改行）"

# Gradio の自動スクロールは使わず（autoscroll=False）、再生中の箱へのスクロールと末尾追従をここで行う。
# playing は「連番:発言番号」。利用者がホイール・タッチ・クリックしてから 8 秒は動かさない。
SCROLL_TO_PLAYING_JS = """
(playing) => {
  const w = window;
  w.__studioPlayingVal = playing;
  if (w.__studioRaf) return;
  w.__studioRaf = requestAnimationFrame(() => {
    w.__studioRaf = 0;
    const root = document.querySelector('#studio-chatbot');
    if (!root) return;
    const rows = [...root.querySelectorAll('.message-row')];
    const m = /^\\d+:(\\d*)$/.exec(w.__studioPlayingVal || '');
    const idx = m && m[1] !== '' ? Number(m[1]) : -1;
    rows.forEach((r, i) => r.classList.toggle('studio-playing', i === idx));
    if (!rows.length) { w.__studioPlayingIdx = -1; return; }
    let box = rows[0].parentElement;
    while (box && !(box.scrollHeight > box.clientHeight && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) {
      box = box.parentElement;
    }
    if (!box) return;
    if (!box.__studioBound) {
      box.__studioBound = true;
      box.__studioStick = true;
      box.__studioUserAt = 0;
      const touch = () => { box.__studioUserAt = Date.now(); };
      ['wheel', 'touchstart', 'pointerdown'].forEach(ev => box.addEventListener(ev, touch, { passive: true }));
      box.addEventListener('scroll', () => {
        box.__studioStick = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
      });
    }
    const quiet = Date.now() - box.__studioUserAt > 8000;
    const prev = w.__studioPlayingIdx;
    w.__studioPlayingIdx = idx;
    if (idx >= 0) {
      if (idx === prev || !quiet || !rows[idx]) return;
      const top = box.scrollTop + rows[idx].getBoundingClientRect().top - box.getBoundingClientRect().top - 40;
      box.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    } else if (quiet && box.__studioStick) {
      box.scrollTo({ top: box.scrollHeight });
    }
  });
}
"""

# 再生表示（iframe）から再生中の発言の冒頭が届いたら、同じ文面のチャットの箱を強調してスクロールする。
STUDIO_HEAD = (
    "<script>\n"
    f"window.__studioScrollToPlaying = {SCROLL_TO_PLAYING_JS};\n"
    """
window.__studioLastMatch = 0;
window.addEventListener('message', (e) => {
  if (e.origin !== window.location.origin || !e.data || e.data.type !== 'studio-playing') return;
  const rows = [...document.querySelectorAll('#studio-chatbot .message-row')];
  const norm = (s) => (s || '').replace(/\\s+/g, '');
  const snippet = norm(e.data.snippet);
  let idx = -1;
  if (snippet) {
    const hits = rows.map((r, i) => (norm(r.textContent).includes(snippet) ? i : -1)).filter((i) => i >= 0);
    idx = hits.find((i) => i >= window.__studioLastMatch) ?? (hits.length ? hits[0] : -1);
    if (idx >= 0) window.__studioLastMatch = idx;
  }
  window.__studioScrollToPlaying('0:' + (idx >= 0 ? idx : ''));
});
"""
    "</script>"
)


def _msg_input_update(placeholder: str = DEFAULT_MSG_PLACEHOLDER) -> dict:
    """Keep the textbox empty; only change the placeholder hint."""
    return gr.update(value="", placeholder=placeholder)


def _upload_input_update(clear: bool = False) -> dict:
    return gr.update(value=None) if clear else gr.update()


def _default_org(root: Path, cli_org: str | None = None) -> str:
    orgs = list_organizations(root)
    if not orgs:
        return ""
    try:
        config = load_studio_config(root)
    except StudioValidationError:
        config = {}
    preferred = (cli_org or "").strip() or config.get("default_org") or DEFAULT_ORG
    if preferred in orgs:
        return preferred
    if "solo" in orgs:
        return "solo"
    return orgs[0]


def build_ui(
    root: Path,
    *,
    cli_org: str | None = None,
    cli_workflow: str | None = None,
    voicevox_url: str = DEFAULT_BASE_URL,
) -> gr.Blocks:
    orgs = list_organizations(root)
    try:
        studio_config = load_studio_config(root)
    except StudioValidationError:
        studio_config = {}
    default_stream = stream_default_from_config(studio_config, default_value=True)
    default_temperature = temperature_default_from_config(studio_config, default_value=0.7)
    default_user_context = user_context_default_from_config(studio_config, default_value=True)
    rag_ui = build_rag_ui_state(root)
    default_user_context_rag = rag_ui.default_rag
    rag_config_available = rag_ui.available
    initial_corpus_files = rag_ui.corpus_files
    initial_corpus_file = rag_ui.corpus_file
    default_org = _default_org(root, cli_org)
    initial_wf = initial_workflow_for_org(root, default_org or "", cli_workflow)
    if cli_workflow and initial_wf != cli_workflow:
        print(f"[WARN] --workflow '{cli_workflow}' は組織 '{default_org}' で使えません。'{initial_wf or '直接送信'}' で起動します。")
    wf_choices, default_wf = workflow_dropdown_for_org(root, default_org or "", initial_wf)
    upload_limits = upload_limits_from_config(studio_config)
    led_monitor = engine_monitor(parse_voicevox_urls(voicevox_url))
    led_monitor.start()

    with gr.Blocks(title=f"MultiRoleStudio Web {VERSION}", fill_height=True) as demo:
        session_state = gr.State(WebSession(root=root, voicevox_url=voicevox_url))
        valid_wf_state = gr.State(default_wf)
        pending_wf_hint_state = gr.State("")

        gr.Markdown(f"# MultiRoleStudio Web `{VERSION}`")

        with gr.Tabs():
            with gr.Tab("💬 チャット"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=260):
                        org_dd = gr.Dropdown(
                            label="組織",
                            choices=orgs,
                            value=default_org if default_org in orgs else (orgs[0] if orgs else None),
                        )
                        wf_dd = gr.Dropdown(
                            label="ワークフロー",
                            choices=wf_choices,
                            value=default_wf,
                        )
                        wf_note_md = gr.Markdown("")
                        upload_files = gr.File(
                            label="ファイルを会話に取り込む（テキスト系）",
                            file_count="multiple",
                            type="filepath",
                        )
                        stream_cb = gr.Checkbox(label="ストリーミング", value=default_stream)
                        user_context_cb = gr.Checkbox(
                            label="ユーザーコンテキスト",
                            value=default_user_context,
                        )
                        user_context_rag_cb = gr.Checkbox(
                            label="コンテキスト RAG",
                            value=default_user_context_rag,
                            interactive=rag_config_available,
                        )
                        web_search_cb = gr.Checkbox(label="ウェブ検索", value=False)
                        voice_cb = gr.Checkbox(label="読み上げ（VOICEVOX）", value=False)
                        timing_cb = gr.Checkbox(label="タイミング表示", value=True)
                        engine_led = gr.HTML(engine_led_html(led_monitor.states()))
                        audio_player = gr.Audio(
                            label="読み上げ",
                            type="numpy",
                            autoplay=True,
                            interactive=False,
                        )
                        playing_box = gr.Textbox(visible="hidden", elem_id="studio-playing")
                        merge_cb = gr.Checkbox(
                            label="連続メッセージを1つにまとめる",
                            value=False,
                        )
                        with gr.Accordion("RAG ツール（corpus / index）", open=False):
                            rag_panel_md = gr.Markdown(rag_ui.panel_md)
                            refresh_rag_btn = gr.Button(
                                "設定を再読込",
                                variant="secondary",
                            )
                            reindex_btn = gr.Button(
                                "index 再構築",
                                variant="secondary",
                                interactive=rag_config_available,
                            )
                            rag_status_md = gr.Markdown(rag_ui.status_hint)
                            corpus_dd = gr.Dropdown(
                                label="corpus ファイル",
                                choices=initial_corpus_files,
                                value=initial_corpus_file,
                                interactive=rag_config_available,
                            )
                            corpus_tb = gr.Textbox(
                                label="corpus プレビュー",
                                value=rag_ui.corpus_preview or CORPUS_PREVIEW_PLACEHOLDER,
                                lines=6,
                                max_lines=12,
                                interactive=False,
                            )
                            rag_query_tb = gr.Textbox(
                                label="検索プレビュー（クエリ）",
                                placeholder="例: loader E204 parity",
                                lines=1,
                            )
                            rag_search_btn = gr.Button(
                                "検索プレビュー",
                                variant="secondary",
                                interactive=rag_config_available,
                            )
                            rag_search_md = gr.Markdown("_検索結果がここに表示されます_")
                            rag_inject_md = gr.Markdown("_送信後に注入 chunk が表示されます_")
                        temp_sl = gr.Slider(
                            label="Temperature",
                            minimum=0.0,
                            maximum=2.0,
                            step=0.1,
                            value=default_temperature,
                        )
                        new_chat_btn = gr.Button("新規チャット", variant="primary")
                        talents_md = gr.Markdown("**参加人材**")
                    with gr.Column(scale=3, elem_classes=["studio-chat-column"]):
                        chatbot = gr.Chatbot(
                            label="チャット",
                            elem_id="studio-chatbot",
                            height=CHATBOT_DEFAULT_HEIGHT,
                            min_height=CHATBOT_MIN_HEIGHT,
                            resizable=True,
                            group_consecutive_messages=False,
                            autoscroll=False,
                        )
                        with gr.Column(elem_classes=["studio-chat-footer"]):
                            status_tb = gr.Textbox(label="状態", lines=1, interactive=False)
                            with gr.Row(visible=False) as choice_row:
                                continue_btn = gr.Button("続行 (y)", variant="primary")
                                exit_btn = gr.Button("終了 (n)", variant="primary")
                            msg_tb = gr.Textbox(
                                label="メッセージ",
                                placeholder=DEFAULT_MSG_PLACEHOLDER,
                                lines=1,
                                max_lines=6,
                            )
                            send_btn = gr.Button("送信", variant="primary")
                            live_timing = gr.HTML("", visible=False, elem_id="studio-live-timing")

            build_settings_tab(
                root,
                SettingsHandles(org_dd=org_dd, wf_dd=wf_dd, talents_md=talents_md),
                demo,
                chat_org=default_org,
                chat_workflow=default_wf,
            )

            build_sessions_tab(
                root,
                SessionsHandles(
                    session_state=session_state,
                    org_dd=org_dd,
                    wf_dd=wf_dd,
                    wf_note_md=wf_note_md,
                    chatbot=chatbot,
                    status_tb=status_tb,
                    talents_md=talents_md,
                    choice_row=choice_row,
                    valid_wf_state=valid_wf_state,
                    pending_wf_hint_state=pending_wf_hint_state,
                    stream_cb=stream_cb,
                    user_context_cb=user_context_cb,
                    temp_sl=temp_sl,
                ),
                demo,
            )

        def on_org_change(org_id: str, workflow_value: str) -> tuple[dict, str, str, str, str]:
            choices, value = workflow_dropdown_for_org(root, org_id or "", workflow_value)
            talents = load_org_panel(root, org_id, value)[0]
            return gr.update(choices=choices, value=value), talents, value, "", ""

        def on_wf_change(
            org_id: str,
            workflow_value: str,
            last_valid_wf: str,
            pending_hint: str,
        ) -> tuple[dict, dict | str, str, str, str]:
            if workflow_value and not workflow_available_for_org(root, org_id or "", workflow_value):
                revert = last_valid_wf
                if not workflow_available_for_org(root, org_id or "", revert or None):
                    _, revert = workflow_dropdown_for_org(root, org_id or "", "")
                note = workflow_unavailable_note(root, org_id or "", workflow_value)
                return gr.update(value=revert), gr.update(), revert, note, note

            talents = load_org_panel(root, org_id, workflow_value)[0]
            return gr.update(), talents, workflow_value, "", ""

        def on_new_chat(session: WebSession):
            summary = session.reset_chat()
            status = "新規チャットを開始しました"
            if summary:
                status = f"{status}\n{summary}"
            return [], session, status, gr.update(visible=False), _msg_input_update(), _upload_input_update(True)

        def on_submit(
            session: WebSession,
            user_text: str,
            org_id: str,
            workflow_value: str,
            stream: bool,
            temperature: float,
            user_context: bool,
            user_context_rag: bool,
            files,
            web_search: bool,
            voice: bool,
        ):
            try:
                for messages, status, show_choice, placeholder, clear_upload in handle_chat_submit(
                    session,
                    user_text,
                    org_id=org_id,
                    workflow_value=workflow_value,
                    stream=stream,
                    temperature=temperature,
                    user_context=user_context,
                    user_context_rag=user_context_rag,
                    files=files,
                    upload_limits=upload_limits,
                    web_search=bool(web_search),
                    voice=bool(voice),
                ):
                    yield (
                        messages,
                        session,
                        status,
                        gr.update(visible=show_choice),
                        _msg_input_update(placeholder),
                        _upload_input_update(clear_upload),
                        last_rag_injection_preview(session),
                    )
            except StudioValidationError as exc:
                yield (
                    session.renderer.copy_messages(),
                    session,
                    exc.format_all(),
                    gr.update(visible=False),
                    _msg_input_update(),
                    _upload_input_update(),
                    gr.update(),
                )

        def on_choice(session: WebSession, choice: str):
            result = handle_choice(session, choice)
            if isinstance(result, tuple):
                messages, status, show_choice, placeholder, clear_upload = result
                yield (
                    messages,
                    session,
                    status,
                    gr.update(visible=show_choice),
                    _msg_input_update(placeholder),
                    _upload_input_update(clear_upload),
                    last_rag_injection_preview(session),
                )
                return
            for messages, status, show_choice, placeholder, clear_upload in result:
                yield (
                    messages,
                    session,
                    status,
                    gr.update(visible=show_choice),
                    _msg_input_update(placeholder),
                    _upload_input_update(clear_upload),
                    last_rag_injection_preview(session),
                )

        def sync_chat_prefs(
            session: WebSession,
            stream: bool,
            user_context: bool,
            user_context_rag: bool,
            temperature: float,
        ):
            session.stream = True if stream is None else stream
            session.user_context = True if user_context is None else user_context
            session.user_context_rag = True if user_context_rag is None else user_context_rag
            session.temperature = 0.7 if temperature is None else temperature
            return session

        def on_corpus_select(filename: str | None):
            config = load_studio_config_for_ui(root)
            return read_corpus_file(root, config, filename)

        def refresh_rag_ui(preserve_rag_checked: bool):
            state = build_rag_ui_state(root, load_corpus_preview=False)
            rag_update = (
                gr.update(value=preserve_rag_checked, interactive=state.available)
                if preserve_rag_checked is not None
                else gr.update(value=state.default_rag, interactive=state.available)
            )
            return (
                state.panel_md,
                rag_update,
                gr.update(interactive=state.available),
                gr.update(choices=state.corpus_files, value=state.corpus_file, interactive=state.available),
                gr.update(value=CORPUS_PREVIEW_PLACEHOLDER if state.corpus_files else ""),
                gr.update(interactive=state.available),
                state.status_hint,
            )

        def on_refresh_rag_clicked(current_rag: bool):
            return refresh_rag_ui(current_rag)

        def on_reindex(current_rag: bool):
            config = load_studio_config_for_ui(root)
            message = run_reindex(root, config)
            state = build_rag_ui_state(root, load_corpus_preview=False)
            return (
                message,
                state.panel_md,
                gr.update(choices=state.corpus_files, value=state.corpus_file, interactive=state.available),
                gr.update(value=CORPUS_PREVIEW_PLACEHOLDER if state.corpus_files else ""),
                gr.update(interactive=state.available),
            )

        def on_rag_search(
            query: str,
            user_context: bool,
            user_context_rag: bool,
        ):
            config = load_studio_config_for_ui(root)
            if not rag_available_in_config(config):
                return RAG_DISABLED_HINT
            return search_preview_markdown(
                root,
                config,
                query,
                user_context=user_context,
                user_context_rag=user_context_rag,
            )

        stream_cb.change(
            sync_chat_prefs,
            inputs=[session_state, stream_cb, user_context_cb, user_context_rag_cb, temp_sl],
            outputs=[session_state],
        )
        user_context_cb.change(
            sync_chat_prefs,
            inputs=[session_state, stream_cb, user_context_cb, user_context_rag_cb, temp_sl],
            outputs=[session_state],
        )
        user_context_rag_cb.change(
            sync_chat_prefs,
            inputs=[session_state, stream_cb, user_context_cb, user_context_rag_cb, temp_sl],
            outputs=[session_state],
        )
        temp_sl.change(
            sync_chat_prefs,
            inputs=[session_state, stream_cb, user_context_cb, user_context_rag_cb, temp_sl],
            outputs=[session_state],
        )
        corpus_dd.change(on_corpus_select, inputs=[corpus_dd], outputs=[corpus_tb], queue=False)
        refresh_rag_btn.click(
            on_refresh_rag_clicked,
            inputs=[user_context_rag_cb],
            outputs=[
                rag_panel_md,
                user_context_rag_cb,
                reindex_btn,
                corpus_dd,
                corpus_tb,
                rag_search_btn,
                rag_status_md,
            ],
            queue=False,
        )
        reindex_btn.click(
            on_reindex,
            inputs=[user_context_rag_cb],
            outputs=[rag_status_md, rag_panel_md, corpus_dd, corpus_tb, rag_search_btn],
            queue=False,
        )
        rag_search_btn.click(
            on_rag_search,
            inputs=[rag_query_tb, user_context_cb, user_context_rag_cb],
            outputs=[rag_search_md],
            queue=False,
        )
        rag_query_tb.submit(
            on_rag_search,
            inputs=[rag_query_tb, user_context_cb, user_context_rag_cb],
            outputs=[rag_search_md],
            queue=False,
        )

        org_dd.change(
            on_org_change,
            inputs=[org_dd, wf_dd],
            outputs=[wf_dd, talents_md, valid_wf_state, pending_wf_hint_state, wf_note_md],
        )
        wf_dd.change(
            on_wf_change,
            inputs=[org_dd, wf_dd, valid_wf_state, pending_wf_hint_state],
            outputs=[wf_dd, talents_md, valid_wf_state, pending_wf_hint_state, wf_note_md],
        )
        merge_cb.change(
            lambda merge: gr.update(group_consecutive_messages=merge),
            inputs=[merge_cb],
            outputs=[chatbot],
        )
        demo.load(
            on_org_change,
            inputs=[org_dd, wf_dd],
            outputs=[wf_dd, talents_md, valid_wf_state, pending_wf_hint_state, wf_note_md],
        )

        new_chat_btn.click(
            on_new_chat,
            inputs=[session_state],
            outputs=[chatbot, session_state, status_tb, choice_row, msg_tb, upload_files],
        )

        submit_inputs = [
            session_state,
            msg_tb,
            org_dd,
            wf_dd,
            stream_cb,
            temp_sl,
            user_context_cb,
            user_context_rag_cb,
            upload_files,
            web_search_cb,
            voice_cb,
        ]
        submit_outputs = [
            chatbot,
            session_state,
            status_tb,
            choice_row,
            msg_tb,
            upload_files,
            rag_inject_md,
        ]

        send_btn.click(on_submit, inputs=submit_inputs, outputs=submit_outputs)
        msg_tb.submit(on_submit, inputs=submit_inputs, outputs=submit_outputs)

        # 発言ごとの音声は再生開始（play）・再生完了（stop）・タイマーで順に渡す
        audio_player.play(
            audio_started_update,
            inputs=[session_state],
            outputs=[playing_box],
            queue=False,
            show_progress="hidden",
        )
        audio_player.stop(
            audio_finished_update,
            inputs=[session_state],
            outputs=[audio_player, playing_box],
            queue=False,
            show_progress="hidden",
        )
        audio_timer = gr.Timer(1.0)
        audio_timer.tick(
            next_audio_update,
            inputs=[session_state],
            outputs=[audio_player, playing_box],
            queue=False,
            show_progress="hidden",
        )
        led_timer = gr.Timer(0.5)
        led_timer.tick(
            # ライブのチャートが出ている間は、チャート側の ENGINE の灯と重なるので隠す
            lambda session: "" if session.live_chart_shown() else engine_led_html(led_monitor.states()),
            inputs=[session_state],
            outputs=[engine_led],
            queue=False,
            show_progress="hidden",
        )
        live_timer = gr.Timer(1.0)
        live_timer.tick(
            live_timing_update,
            inputs=[session_state, timing_cb],
            outputs=[live_timing],
            queue=False,
            show_progress="hidden",
        )
        chatbot.change(None, [playing_box], None, js=SCROLL_TO_PLAYING_JS, queue=False, show_progress="hidden")
        playing_box.change(None, [playing_box], None, js=SCROLL_TO_PLAYING_JS, queue=False, show_progress="hidden")

        continue_btn.click(
            on_choice,
            inputs=[session_state, gr.State("continue")],
            outputs=[chatbot, session_state, status_tb, choice_row, msg_tb, upload_files, rag_inject_md],
        )
        exit_btn.click(
            on_choice,
            inputs=[session_state, gr.State("exit")],
            outputs=[chatbot, session_state, status_tb, choice_row, msg_tb, upload_files, rag_inject_md],
        )

    return demo


def suppress_connection_reset_log() -> None:
    # Windows の Proactor が、ブラウザ側切断時に出す無害なログだけを落とす
    class _Filter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            exc = record.exc_info[1] if record.exc_info else None
            return not isinstance(exc, ConnectionResetError)

    logging.getLogger("asyncio").addFilter(_Filter())


def main() -> None:
    parser = argparse.ArgumentParser(description="MultiRoleStudio Web UI")
    parser.add_argument("--org", default=None, help="デフォルト組織 ID")
    parser.add_argument(
        "--workflow",
        default=None,
        help="起動時に選択するワークフロー ID（省略時は組織の default_workflow、なければ直接送信）",
    )
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="ポート番号")
    parser.add_argument("--share", action="store_true", help="Gradio 公開トンネルを有効化")
    parser.add_argument("--no-browser", action="store_true", help="起動時にブラウザを開かない")
    parser.add_argument(
        "--host",
        default=None,
        help="待ち受けアドレス（既定: この PC のみ。別 PC から開くなら 0.0.0.0）。認証はない",
    )
    parser.add_argument(
        "--voicevox-url",
        default=DEFAULT_BASE_URL,
        help="VOICEVOX の接続先（既定: 環境変数 VOICEVOX_URL または http://127.0.0.1:50021）。カンマ区切りで複数指定すると並列合成",
    )
    parser.add_argument("--version", action="version", version=f"MultiRoleStudioWeb {VERSION}")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    print(f"[INFO] MultiRoleStudioWeb v{VERSION} 起動中 (root={root})")
    use_japanese_html_template()
    suppress_connection_reset_log()
    demo = build_ui(
        root, cli_org=args.org, cli_workflow=args.workflow, voicevox_url=args.voicevox_url
    )
    if args.host and args.host not in {"127.0.0.1", "localhost"}:
        print("[WARN] --host で外部から接続できます。認証はありません。信頼できるネットワーク内でのみ使ってください。")
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        inbrowser=not args.no_browser,
        theme=gr.themes.Soft(),
        css=STUDIO_WEB_CSS,
        head=STUDIO_HEAD,
        prevent_thread_lock=True,
        allowed_paths=[str(root / "sessions" / "audio")],
    )
    print("[INFO] サーバー起動完了。終了するには q + Enter を押してください。")
    try:
        while True:
            if input().strip().lower() == "q":
                break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        demo.close()
        print("[INFO] サーバーを停止しました。")


if __name__ == "__main__":
    main()

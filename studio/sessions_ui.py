"""Gradio sessions tab (design.md §8.5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from studio.minutes import save_minutes_from_session
from studio.session_report import (
    FlowTheme,
    export_session_markdown,
    load_session_markdown,
    session_dropdown_choices,
)
from studio.validation import StudioValidationError
from studio.web_ui import apply_session_resume

_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"])
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])
_DEFAULT_FLOW_THEME = "ダーク"


@dataclass
class SessionsHandles:
    session_state: Any
    org_dd: gr.Dropdown
    wf_dd: gr.Dropdown
    wf_note_md: gr.Markdown
    chatbot: gr.Chatbot
    status_tb: gr.Textbox
    talents_md: gr.Markdown
    choice_row: gr.Row
    valid_wf_state: Any
    pending_wf_hint_state: Any
    stream_cb: gr.Checkbox
    temp_sl: gr.Slider


def _flow_theme_key(label: str) -> FlowTheme:
    return "dark" if label == "ダーク" else "light"


def build_sessions_tab(root: Path, handles: SessionsHandles, _demo: gr.Blocks) -> None:
    initial_choices = session_dropdown_choices(root)
    initial_session_id = initial_choices[0][1] if initial_choices else None
    initial_flow_theme = _flow_theme_key(_DEFAULT_FLOW_THEME)
    initial_report = (
        load_session_markdown(root, initial_session_id, flow_theme=initial_flow_theme)
        if initial_session_id
        else "_セッションがありません_"
    )

    with gr.Tab("📄 セッション"):
        with gr.Column(elem_classes=["studio-settings-panel"]):
            gr.Markdown(
                "`sessions/*.jsonl` の一覧表示、Markdown レポート閲覧、エクスポート（§8.5）。"
                " 下段は **JSONL から生成したレポート**（生ログではありません）。"
                " **再開** は分岐セッションとしてチャットタブへ読み込みます（§7.2）。"
                " 議事録・採用は Phase 5b/5c。"
            )
            with gr.Row():
                session_dd = gr.Dropdown(
                    label="セッション",
                    choices=initial_choices,
                    value=initial_session_id,
                    allow_custom_value=False,
                    scale=4,
                )
                flow_theme_radio = gr.Radio(
                    choices=["ライト", "ダーク"],
                    value=_DEFAULT_FLOW_THEME,
                    label="フロー図テーマ",
                    scale=1,
                )
                refresh_btn = gr.Button("一覧更新", **_ACTION_BTN)
            report_md = gr.Markdown(initial_report, elem_classes=["studio-session-report"])
            with gr.Row():
                resume_btn = gr.Button("再開", **_SAVE_BTN)
                minutes_btn = gr.Button("議事録 (.json + .md)", **_SAVE_BTN)
                export_btn = gr.Button("エクスポート (.md)", **_SAVE_BTN)
                adopt_btn = gr.Button("成果物採用", **_SAVE_BTN)
            session_msg = gr.Markdown("")
            export_file = gr.File(label="エクスポート結果", interactive=False, visible=False)

    def _hide_export() -> dict:
        return gr.update(value=None, visible=False)

    def _show_export(path: str) -> dict:
        return gr.update(value=path, visible=True)

    def refresh_session_list(current: str | None) -> tuple[list[tuple[str, str]], str | None]:
        choices = session_dropdown_choices(root)
        values = [session_id for _label, session_id in choices]
        value = current if current in values else (values[0] if values else None)
        return choices, value

    def on_session_select(session_id: str | None, theme_label: str):
        if not session_id:
            return "_セッションを選択してください_", _hide_export(), ""
        return (
            load_session_markdown(
                root,
                session_id,
                flow_theme=_flow_theme_key(theme_label),
            ),
            _hide_export(),
            "",
        )

    def on_refresh(current: str | None, theme_label: str):
        choices, session_id = refresh_session_list(current)
        report, file_upd, _msg = on_session_select(session_id, theme_label)
        return gr.update(choices=choices, value=session_id), report, file_upd, ""

    def on_export(session_id: str | None, theme_label: str):
        if not session_id:
            return _hide_export(), "セッションを選択してください"
        try:
            path = export_session_markdown(
                root,
                session_id,
                flow_theme=_flow_theme_key(theme_label),
            )
        except OSError as exc:
            return _hide_export(), f"エクスポート失敗: {exc}"
        return _show_export(str(path)), f"`{path.name}` を出力しました（`sessions/exports/`）"

    def on_resume(
        session_id: str | None,
        web_session,
        stream: bool,
        temperature: float,
    ):
        if not session_id:
            return (
                web_session,
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(visible=False),
                "セッションを選択してください",
            )
        try:
            (
                web_session,
                messages,
                status,
                _org,
                org_upd,
                wf_upd,
                talents,
                wf_value,
                _hint_clear,
                msg,
            ) = apply_session_resume(
                web_session,
                session_id,
                stream=stream,
                temperature=temperature,
            )
        except StudioValidationError as exc:
            return (
                web_session,
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(visible=False),
                exc.format_all(),
            )
        return (
            web_session,
            messages,
            status,
            org_upd,
            wf_upd,
            talents,
            wf_value,
            "",
            gr.update(value=""),
            gr.update(visible=False),
            msg,
        )

    def on_minutes(session_id: str | None):
        if not session_id:
            return "セッションを選択してください"
        result = save_minutes_from_session(
            root,
            session_id,
            topic=None,
            commit=True,
        )
        if not result.ok:
            return result.message
        return f"**議事録** — {result.message}"

    def phase5_notice(feature: str) -> str:
        return f"**{feature}** は Phase 5 で実装予定です（design.md §8.5 / 9.1）。"

    refresh_btn.click(
        on_refresh,
        inputs=[session_dd, flow_theme_radio],
        outputs=[session_dd, report_md, export_file, session_msg],
    )
    session_dd.change(
        on_session_select,
        inputs=[session_dd, flow_theme_radio],
        outputs=[report_md, export_file, session_msg],
    )
    flow_theme_radio.change(
        on_session_select,
        inputs=[session_dd, flow_theme_radio],
        outputs=[report_md, export_file, session_msg],
    )
    export_btn.click(
        on_export,
        inputs=[session_dd, flow_theme_radio],
        outputs=[export_file, session_msg],
    )
    resume_btn.click(
        on_resume,
        inputs=[
            session_dd,
            handles.session_state,
            handles.stream_cb,
            handles.temp_sl,
        ],
        outputs=[
            handles.session_state,
            handles.chatbot,
            handles.status_tb,
            handles.org_dd,
            handles.wf_dd,
            handles.talents_md,
            handles.valid_wf_state,
            handles.pending_wf_hint_state,
            handles.wf_note_md,
            handles.choice_row,
            session_msg,
        ],
    )
    minutes_btn.click(
        on_minutes,
        inputs=[session_dd],
        outputs=[session_msg],
    )
    adopt_btn.click(
        lambda: phase5_notice("成果物採用"),
        outputs=[session_msg],
    )

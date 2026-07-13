#!/usr/bin/env python3
"""MultiRoleStudio Web UI (Phase 4a: chat, Phase 4b: settings, Phase 4c: attachments)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import gradio as gr

from studio.gradio_template import use_japanese_html_template
from studio.loader import load_studio_config
from studio.validation import StudioValidationError
from studio.settings_ui import SettingsHandles, build_settings_tab
from studio.web_ui import (
    DIRECT_WORKFLOW_VALUE,
    WebSession,
    handle_chat_submit,
    handle_choice,
    list_organizations,
    load_org_panel,
    upload_limits_from_config,
    workflow_dropdown_choices,
)
from web_input_utils import stream_default_from_config, temperature_default_from_config

VERSION = "0.4.2"

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
.studio-chat-footer {
  flex: 0 0 auto !important;
}
"""

CHATBOT_MIN_HEIGHT = 200
# 初回表示でメッセージ欄・送信ボタンが viewport 内に収まる高さ（リサイズ可）
CHATBOT_DEFAULT_HEIGHT = "clamp(200px, calc(100dvh - 22rem), 480px)"

DEFAULT_MSG_PLACEHOLDER = "メッセージを入力…"


def _msg_input_update(placeholder: str = DEFAULT_MSG_PLACEHOLDER) -> dict:
    """Keep the textbox empty; only change the placeholder hint."""
    return gr.update(value="", placeholder=placeholder)


def _upload_input_update(clear: bool = False) -> dict:
    return gr.update(value=None) if clear else gr.update()


def _default_org(root: Path) -> str:
    orgs = list_organizations(root)
    if not orgs:
        return ""
    try:
        config = load_studio_config(root)
    except StudioValidationError:
        config = {}
    preferred = config.get("default_org") or DEFAULT_ORG
    if preferred in orgs:
        return preferred
    if "solo" in orgs:
        return "solo"
    return orgs[0]


def build_ui(root: Path) -> gr.Blocks:
    orgs = list_organizations(root)
    wf_choices = workflow_dropdown_choices(root)
    try:
        studio_config = load_studio_config(root)
    except StudioValidationError:
        studio_config = {}
    default_stream = stream_default_from_config(studio_config, default_value=True)
    default_temperature = temperature_default_from_config(studio_config, default_value=0.7)
    default_org = _default_org(root)
    upload_limits = upload_limits_from_config(studio_config)

    with gr.Blocks(title=f"MultiRoleStudio Web {VERSION}", fill_height=True) as demo:
        session_state = gr.State(WebSession(root=root))

        gr.Markdown(
            f"# MultiRoleStudio Web `{VERSION}`\n"
            "Phase 4a: チャット / Phase 4b: 設定編集 / Phase 4c: ファイル添付"
        )

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
                            value=DIRECT_WORKFLOW_VALUE,
                        )
                        upload_files = gr.File(
                            label="ファイルを会話に取り込む（テキスト系）",
                            file_count="multiple",
                            type="filepath",
                        )
                        stream_cb = gr.Checkbox(label="ストリーミング", value=default_stream)
                        merge_cb = gr.Checkbox(
                            label="連続メッセージを1つにまとめる",
                            value=False,
                        )
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
                        )
                        with gr.Column(elem_classes=["studio-chat-footer"]):
                            status_tb = gr.Textbox(label="状態", lines=1, interactive=False)
                            with gr.Row(visible=False) as choice_row:
                                continue_btn = gr.Button("続行 (y)", variant="primary")
                                exit_btn = gr.Button("終了 (n)", variant="primary")
                            msg_tb = gr.Textbox(
                                label="メッセージ",
                                placeholder=DEFAULT_MSG_PLACEHOLDER,
                                lines=2,
                            )
                            send_btn = gr.Button("送信", variant="primary")

            build_settings_tab(
                root,
                SettingsHandles(org_dd=org_dd, wf_dd=wf_dd, talents_md=talents_md),
                demo,
            )

            with gr.Tab("📄 セッション"):
                gr.Markdown("Phase 4e で実装予定（design.md §8.5）")

        def refresh_talents(org_id: str, workflow_value: str) -> str:
            return load_org_panel(root, org_id, workflow_value)[0]

        def on_org_change(org_id: str, workflow_value: str) -> str:
            return refresh_talents(org_id, workflow_value)

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
            files,
        ):
            try:
                for messages, status, show_choice, placeholder, clear_upload in handle_chat_submit(
                    session,
                    user_text,
                    org_id=org_id,
                    workflow_value=workflow_value,
                    stream=stream,
                    temperature=temperature,
                    files=files,
                    upload_limits=upload_limits,
                ):
                    yield (
                        messages,
                        session,
                        status,
                        gr.update(visible=show_choice),
                        _msg_input_update(placeholder),
                        _upload_input_update(clear_upload),
                    )
            except StudioValidationError as exc:
                yield (
                    session.renderer.copy_messages(),
                    session,
                    exc.format_all(),
                    gr.update(visible=False),
                    _msg_input_update(),
                    _upload_input_update(),
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
                )

        org_dd.change(on_org_change, inputs=[org_dd, wf_dd], outputs=[talents_md])
        wf_dd.change(on_org_change, inputs=[org_dd, wf_dd], outputs=[talents_md])
        merge_cb.change(
            lambda merge: gr.update(group_consecutive_messages=merge),
            inputs=[merge_cb],
            outputs=[chatbot],
        )
        demo.load(refresh_talents, inputs=[org_dd, wf_dd], outputs=[talents_md])

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
            upload_files,
        ]
        submit_outputs = [chatbot, session_state, status_tb, choice_row, msg_tb, upload_files]

        send_btn.click(on_submit, inputs=submit_inputs, outputs=submit_outputs)
        msg_tb.submit(on_submit, inputs=submit_inputs, outputs=submit_outputs)

        continue_btn.click(
            on_choice,
            inputs=[session_state, gr.State("continue")],
            outputs=[chatbot, session_state, status_tb, choice_row, msg_tb, upload_files],
        )
        exit_btn.click(
            on_choice,
            inputs=[session_state, gr.State("exit")],
            outputs=[chatbot, session_state, status_tb, choice_row, msg_tb, upload_files],
        )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="MultiRoleStudio Web UI")
    parser.add_argument("--org", default=None, help="デフォルト組織 ID")
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="ポート番号")
    parser.add_argument("--share", action="store_true", help="Gradio 公開トンネルを有効化")
    parser.add_argument("--version", action="version", version=f"MultiRoleStudioWeb {VERSION}")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.org:
        global DEFAULT_ORG
        DEFAULT_ORG = args.org

    print(f"[INFO] MultiRoleStudioWeb v{VERSION} 起動中 (root={root})")
    use_japanese_html_template()
    demo = build_ui(root)
    demo.launch(
        server_port=args.port,
        share=args.share,
        inbrowser=True,
        theme=gr.themes.Soft(),
        css=STUDIO_WEB_CSS,
        prevent_thread_lock=True,
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

"""ChatWeb.py - Chat.py の Gradio Web インターフェース ラッパー

Chat.py の LLM 接続ロジックをそのまま流用し、
ブラウザから操作できるチャット UI を提供する。

使い方:
    python ChatWeb.py
    python ChatWeb.py --assistant Claude --port 7861
    python ChatWeb.py --share   # 外部公開URL付き（一時的なトンネル）

環境変数:
    CHATWEB_ASSISTANT : デフォルトアシスタント名
    CHATWEB_PORT      : デフォルトポート番号
"""

from __future__ import annotations

import os
import argparse
from typing import Generator

import gradio as gr
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.messages import HumanMessage, AIMessage

# Chat.py から LLM 接続ロジックを流用（MyPedia.py と同じ方式）
from Chat import load_ai_assistants_config, load_assistant

VERSION = "1.1.0"
VERSION_DATE = "2026-06-24"

DEFAULT_ASSISTANT = os.getenv("CHATWEB_ASSISTANT", "OpenAI")
DEFAULT_PORT = int(os.getenv("CHATWEB_PORT", "7860"))
SYSTEM_MESSAGE_FILE = "system_message.txt"

# --- 初期化 ---
AI_ASSISTANTS: dict = {}
try:
    AI_ASSISTANTS = load_ai_assistants_config()
    print(f"[INFO] ChatWeb: {len(AI_ASSISTANTS)} アシスタントを読み込みました")
except Exception as e:
    print(f"[ERROR] アシスタント設定の読み込みに失敗: {e}")


def _load_system_message() -> str:
    try:
        with open(SYSTEM_MESSAGE_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _build_chain(assistant_name: str, system_message: str, model_name: str | None = None):
    """LangChain チェーンを組み立てる。"""
    cfg = AI_ASSISTANTS[assistant_name]
    model = model_name if model_name else cfg["model"]
    llm = load_assistant(AI_ASSISTANTS, assistant_name, model)

    prompt_messages = []
    if system_message.strip() and assistant_name not in ["Gemini"]:
        prompt_messages.append(
            SystemMessagePromptTemplate.from_template(system_message)
        )
    prompt_messages += [
        MessagesPlaceholder(variable_name="history"),
        HumanMessagePromptTemplate.from_template("{input}"),
    ]
    prompt = ChatPromptTemplate.from_messages(prompt_messages)
    return prompt | llm


# セッションごとの履歴を保持するストア（list[HumanMessage | AIMessage]）
_history_store: dict[str, list] = {}


def _get_history(session_id: str) -> list:
    if session_id not in _history_store:
        _history_store[session_id] = []
    return _history_store[session_id]


def chat_fn(
    message: str,
    history: list,
    assistant_name: str,
    model_name: str,
    system_message: str,
    session_id: str,
) -> Generator[str, None, None]:
    """ストリーミングで回答を返すジェネレータ。"""
    if not message.strip():
        yield ""
        return

    if assistant_name not in AI_ASSISTANTS:
        yield f"[ERROR] アシスタント '{assistant_name}' が見つかりません。"
        return

    try:
        chain = _build_chain(assistant_name, system_message, model_name)
        lc_history = _get_history(session_id)

        response_text = ""
        for chunk in chain.stream({"input": message, "history": lc_history}):
            content = getattr(chunk, "content", "") or ""
            if content:
                response_text += content
                yield response_text

        # 履歴に追加
        lc_history.append(HumanMessage(content=message))
        lc_history.append(AIMessage(content=response_text))

    except Exception as e:
        yield f"[ERROR] {e}"


def clear_history(session_id: str) -> tuple:
    """会話履歴をリセットする。"""
    if session_id in _history_store:
        del _history_store[session_id]
    return [], ""


def build_ui() -> gr.Blocks:
    assistant_names = list(AI_ASSISTANTS.keys()) if AI_ASSISTANTS else [DEFAULT_ASSISTANT]
    default_assistant = DEFAULT_ASSISTANT if DEFAULT_ASSISTANT in assistant_names else assistant_names[0]
    default_system = _load_system_message()

    def _get_models(assistant_name: str) -> list[str]:
        cfg = AI_ASSISTANTS.get(assistant_name, {})
        return cfg.get("models") or ([cfg["model"]] if cfg.get("model") else [])

    default_models = _get_models(default_assistant)

    css = """
    #main-chatbot {
        flex-grow: 1;
        min-height: 0;
        height: calc(100vh - 220px) !important;
        overflow-y: auto;
    }
    """
    with gr.Blocks(title="ChatWeb", fill_height=True, css=css) as demo:
        gr.Markdown("# 💬 ChatWeb")

        # セッションIDを状態として保持（タブごとに独立）
        session_id = gr.State(lambda: __import__("uuid").uuid4().hex)

        with gr.Row():
            with gr.Column(scale=1, min_width=220):
                gr.Markdown("### ⚙️ 設定")
                assistant_dd = gr.Dropdown(
                    choices=assistant_names,
                    value=default_assistant,
                    label="アシスタント",
                )
                model_dd = gr.Dropdown(
                    choices=default_models,
                    value=default_models[0] if default_models else None,
                    label="モデル",
                )
                system_box = gr.Textbox(
                    value=default_system,
                    label="システムメッセージ",
                    lines=6,
                    placeholder="AIへの役割・制約を記述...",
                )
                clear_btn = gr.Button("🗑️ 履歴をクリア", variant="secondary")

            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="会話",
                    elem_id="main-chatbot",
                )
                with gr.Row():
                    msg_box = gr.Textbox(
                        placeholder="メッセージを入力して Enter",
                        label="",
                        scale=9,
                        autofocus=True,
                    )
                    send_btn = gr.Button("送信", variant="primary", scale=1)

        # アシスタント切替時にモデル一覧を更新
        def _update_models(assistant_name: str):
            models = _get_models(assistant_name)
            return gr.Dropdown(choices=models, value=models[0] if models else None)

        assistant_dd.change(
            _update_models,
            inputs=[assistant_dd],
            outputs=[model_dd],
        )

        # 送信処理（Gradio 6.17 は messages 形式: dict のリスト）
        def _submit(message, history, assistant, model, system, sid):
            history = history or []
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": ""})
            for partial in chat_fn(message, history, assistant, model, system, sid):
                history[-1] = {"role": "assistant", "content": partial}
                yield "", history

        msg_box.submit(
            _submit,
            inputs=[msg_box, chatbot, assistant_dd, model_dd, system_box, session_id],
            outputs=[msg_box, chatbot],
        )
        send_btn.click(
            _submit,
            inputs=[msg_box, chatbot, assistant_dd, model_dd, system_box, session_id],
            outputs=[msg_box, chatbot],
        )

        # 履歴クリア
        clear_btn.click(
            lambda sid: ([], sid),
            inputs=[session_id],
            outputs=[chatbot, session_id],
        ).then(
            lambda sid: _history_store.pop(sid, None) or sid,
            inputs=[session_id],
            outputs=[session_id],
        )

    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatWeb - Chat.py の Gradio Web UI")
    parser.add_argument("--assistant", default=None, help="デフォルトアシスタント名")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="ポート番号（デフォルト: 7860）")
    parser.add_argument("--share", action="store_true", help="Gradio の外部公開トンネルを有効にする")
    args = parser.parse_args()

    global DEFAULT_ASSISTANT
    if args.assistant and args.assistant in AI_ASSISTANTS:
        DEFAULT_ASSISTANT = args.assistant

    print(f"[INFO] ChatWeb v{VERSION} 起動中...")
    demo = build_ui()
    demo.launch(
        server_port=args.port,
        share=args.share,
        inbrowser=True,
        theme=gr.themes.Soft(),
        prevent_thread_lock=True,
    )
    print("[INFO] サーバーが起動しました。終了するには q + Enter を押してください。")
    try:
        while True:
            line = input()
            if line.strip().lower() == "q":
                break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        demo.close()
        print("[INFO] サーバーを停止しました。")


if __name__ == "__main__":
    main()

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
import re
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
from Chat import (
    load_ai_assistants_config,
    load_assistant,
    load_history_from_csv,
    is_summary_request,
    is_zenn_summary_request,
    create_conversation_summary,
    save_summary_to_file,
    LOGS_DIR,
    SUMMARIES_DIR,
)

VERSION = "1.3.0"
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
    """ストリーミングで回答を返すジェネレータ。まとめ要求も処理する。"""
    if not message.strip():
        yield ""
        return

    if assistant_name not in AI_ASSISTANTS:
        yield f"[ERROR] アシスタント '{assistant_name}' が見つかりません。"
        return

    # ─── まとめ要求検知 ───────────────────────────────────────────
    zenn_mode = is_zenn_summary_request(message)
    if zenn_mode or is_summary_request(message):
        lc_history = _get_history(session_id)

        # 履歴が空の場合はスキップ
        if not lc_history:
            yield "ℹ️ 会話履歴がまだありません。先に会話を始めてください。"
            return

        class _FakeHistory:
            def get_messages(self):
                return lc_history

        history_text = create_conversation_summary(_FakeHistory())

        if zenn_mode:
            summary_prompt = (
                f"以下の会話履歴を、Zenn記事の草稿としてまとめてください。\n"
                f"読者はエンジニアを想定し、「です・ます」調で書いてください。\n"
                f"構成は「## 見出し」を使って読みやすく整理してください。\n\n"
                f"{history_text}\n\nZenn記事の草稿（タイトルは除く、本文のみ）を作成してください："
            )
        else:
            summary_prompt = (
                f"以下の会話履歴をまとめてください。\n\n{history_text}\n\n"
                f"まとめる際は以下の点を心がけてください：\n"
                f"- 重要なキーワードや概念は [[キーワード]] の形式で囲んでリンク化してください\n"
                f"- #タグ も適切に付与してください\n\n上記の会話を簡潔にまとめてください："
            )

        try:
            chain = _build_chain(assistant_name, system_message, model_name)
            label = (
                f"📰 Zenn草稿（{assistant_name}:{model_name}）:\n"
                if zenn_mode
                else f"📋 会話まとめ（{assistant_name}:{model_name}）:\n"
            )
            yield label
            response_text = label
            for chunk in chain.stream({"input": summary_prompt, "history": []}):
                content = getattr(chunk, "content", "") or ""
                if content:
                    response_text += content
                    yield response_text

            # ファイル保存
            summary_body = response_text[len(label):]
            saved = save_summary_to_file(summary_body, assistant_name, model_name, zenn_mode=zenn_mode)
            if saved:
                notice = f"\n\n💾 `{saved}` に保存しました。"
                response_text += notice
                yield response_text

            # まとめは履歴に含めない（トークン節約）
        except Exception as e:
            yield f"[ERROR] まとめ生成中にエラーが発生しました: {e}"
        return

    # ─── 通常の会話 ────────────────────────────────────────────
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


def _list_logs() -> list[str]:
    """logs/ フォルダの CSV ファイル一覧（新しい順）"""
    if not os.path.exists(LOGS_DIR):
        return []
    files = [f for f in os.listdir(LOGS_DIR) if f.endswith(".csv")]
    files.sort(reverse=True)
    return files


def _list_summaries() -> list[str]:
    """summaries/ フォルダの MD ファイル一覧（新しい順）"""
    if not os.path.exists(SUMMARIES_DIR):
        return []
    files = [f for f in os.listdir(SUMMARIES_DIR) if f.endswith(".md")]
    files.sort(reverse=True)
    return files


def _preview_log(filename: str) -> str:
    """ログファイルの直近10件をプレビューテキストに変換"""
    if not filename:
        return ""
    filepath = os.path.join(LOGS_DIR, filename)
    messages, _, last_assistant, last_model = load_history_from_csv(filepath)
    if not messages:
        return "（会話履歴が空です）"
    lines = [
        f"アシスタント: {last_assistant}  /  モデル: {last_model}",
        "─" * 40,
    ]
    for msg in messages[-10:]:
        text = msg.content[:150].replace("\n", " ")
        suffix = "..." if len(msg.content) > 150 else ""
        if isinstance(msg, HumanMessage):
            lines.append(f"👤 {text}{suffix}")
        else:
            lines.append(f"🤖 {text}{suffix}")
    return "\n".join(lines)


def _preview_summary(filename: str) -> str:
    """まとめファイルの先頭800文字をプレビュー"""
    if not filename:
        return ""
    filepath = os.path.join(SUMMARIES_DIR, filename)
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r'\[\[(.+?)\]\]', r'**\1**', content)
        return content[:800] + ("..." if len(content) > 800 else "")
    except Exception as e:
        return f"読み込みエラー: {e}"


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
                with gr.Row():
                    load_log_btn = gr.Button("📂 ログ再開", size="sm")
                    load_summary_btn = gr.Button("📋 まとめ読込", size="sm")

                # ─── ログ読み込みパネル ──────────────────────────────
                with gr.Group(visible=False) as log_panel:
                    gr.Markdown("#### 📂 ログから会話を再開")
                    log_file_dd = gr.Dropdown(
                        choices=[],
                        label="ログファイル（新しい順）",
                        interactive=True,
                    )
                    log_preview_box = gr.Textbox(
                        label="プレビュー（直近10件）",
                        lines=10,
                        interactive=False,
                    )
                    with gr.Row():
                        log_confirm_btn = gr.Button("この会話を再開", variant="primary", size="sm")
                        log_cancel_btn = gr.Button("閉じる", size="sm")

                # ─── まとめ読み込みパネル ────────────────────────────
                with gr.Group(visible=False) as summary_panel:
                    gr.Markdown("#### 📋 まとめを読み込む")
                    summary_file_dd = gr.Dropdown(
                        choices=[],
                        label="まとめファイル（新しい順）",
                        interactive=True,
                    )
                    summary_preview_box = gr.Textbox(
                        label="プレビュー",
                        lines=10,
                        interactive=False,
                    )
                    summary_mode_radio = gr.Radio(
                        choices=["システムメッセージに追記", "会話履歴として注入"],
                        value="システムメッセージに追記",
                        label="読み込み方式",
                    )
                    with gr.Row():
                        summary_confirm_btn = gr.Button("読み込む", variant="primary", size="sm")
                        summary_cancel_btn = gr.Button("閉じる", size="sm")

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

        # ─── ログパネル コールバック ─────────────────────────────────
        load_log_btn.click(
            lambda: (gr.update(visible=True), gr.update(visible=False),
                     gr.update(choices=_list_logs(), value=None), ""),
            outputs=[log_panel, summary_panel, log_file_dd, log_preview_box],
        )
        log_cancel_btn.click(
            lambda: gr.update(visible=False),
            outputs=[log_panel],
        )
        log_file_dd.change(
            _preview_log,
            inputs=[log_file_dd],
            outputs=[log_preview_box],
        )

        def _load_log_fn(filename: str, sid: str, current_assistant: str, current_model: str):
            if not filename:
                return gr.update(visible=False), [], current_assistant, gr.update()
            filepath = os.path.join(LOGS_DIR, filename)
            messages, _, last_assistant, last_model = load_history_from_csv(filepath)
            _history_store[sid] = list(messages)
            display = [
                {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
                for m in messages
            ]
            new_assistant = (
                last_assistant
                if last_assistant and last_assistant in AI_ASSISTANTS
                else current_assistant
            )
            new_models = _get_models(new_assistant)
            new_model = (
                last_model
                if last_model and last_model in new_models
                else (new_models[0] if new_models else current_model)
            )
            return (
                gr.update(visible=False),
                display,
                new_assistant,
                gr.update(choices=new_models, value=new_model),
            )

        log_confirm_btn.click(
            _load_log_fn,
            inputs=[log_file_dd, session_id, assistant_dd, model_dd],
            outputs=[log_panel, chatbot, assistant_dd, model_dd],
        )

        # ─── まとめパネル コールバック ───────────────────────────────
        load_summary_btn.click(
            lambda: (gr.update(visible=False), gr.update(visible=True),
                     gr.update(choices=_list_summaries(), value=None), ""),
            outputs=[log_panel, summary_panel, summary_file_dd, summary_preview_box],
        )
        summary_cancel_btn.click(
            lambda: gr.update(visible=False),
            outputs=[summary_panel],
        )
        summary_file_dd.change(
            _preview_summary,
            inputs=[summary_file_dd],
            outputs=[summary_preview_box],
        )

        def _load_summary_fn(filename: str, mode: str, system_msg: str, sid: str):
            if not filename:
                return gr.update(visible=False), system_msg, gr.update()
            filepath = os.path.join(SUMMARIES_DIR, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                content = re.sub(r'\[\[(.+?)\]\]', r'**\1**', content)
            except Exception:
                return gr.update(visible=False), system_msg, gr.update()
            if mode == "システムメッセージに追記":
                new_system = system_msg.rstrip() + f"\n\n---\n【過去の会話まとめ】\n{content}"
                return gr.update(visible=False), new_system, gr.update()
            else:  # 会話履歴として注入
                history = _get_history(sid)
                history.insert(0, AIMessage(content=f"【過去の会話まとめ】\n{content}"))
                display = [
                    {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
                    for m in history
                ]
                return gr.update(visible=False), system_msg, display

        summary_confirm_btn.click(
            _load_summary_fn,
            inputs=[summary_file_dd, summary_mode_radio, system_box, session_id],
            outputs=[summary_panel, system_box, chatbot],
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

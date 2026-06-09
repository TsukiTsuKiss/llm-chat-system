"""MultiRoleChatWeb.py - MultiRoleChat.py の Gradio Web インターフェース ラッパー

MultiRoleChat.py のロール管理・LLM接続ロジックをそのまま流用し、
ブラウザから複数ロールの応答を同時に確認できる UI を提供する。

使い方:
    python MultiRoleChatWeb.py
    python MultiRoleChatWeb.py --org tech_startup
    python MultiRoleChatWeb.py --org consulting_firm --port 7861
    python MultiRoleChatWeb.py --share   # 外部公開URL付き

環境変数:
    MULTIROLECHATWEB_ORG  : デフォルト組織名
    MULTIROLECHATWEB_PORT : デフォルトポート番号
"""

from __future__ import annotations

import os
import argparse
import threading
import time
from datetime import datetime

import gradio as gr
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    MessagesPlaceholder,
    HumanMessagePromptTemplate,
)
from langchain_core.messages import HumanMessage, AIMessage

from MultiRoleChat import (
    load_ai_assistants_config,
    MultiRoleManager,
    load_organization_config,
    setup_organization_from_config,
)

VERSION = "1.0.0"
VERSION_DATE = "2026-06-09"

DEFAULT_ORG = os.getenv("MULTIROLECHATWEB_ORG", "")
DEFAULT_PORT = int(os.getenv("MULTIROLECHATWEB_PORT", "7861"))

# 最大ロール数（Gradio はビルド時に Component 数を固定するため上限を設ける）
MAX_ROLES = 16

# ロール名に使う色絵文字（0〜15）
ROLE_EMOJIS = [
    "🔵", "🟠", "🟢", "🟣",
    "🔴", "🟡", "🟤", "⚫",
    "🔷", "🚨", "💠", "🟩",
    "🔶", "ℹ️",  "🧊", "⚪",
]

# --- グローバル AI アシスタント設定 ---
AI_ASSISTANTS: dict = {}
try:
    AI_ASSISTANTS = load_ai_assistants_config()
    print(f"[INFO] MultiRoleChatWeb: {len(AI_ASSISTANTS)} アシスタントを読み込みました")
except Exception as e:
    print(f"[ERROR] アシスタント設定の読み込みに失敗: {e}")


# --------------------------------------------------------------------------- #
#  Utilities
# --------------------------------------------------------------------------- #

def _list_organizations() -> list[str]:
    """organizations/ 配下の config.json を持つ組織名を列挙する。"""
    org_dir = "organizations"
    orgs = []
    if os.path.isdir(org_dir):
        for name in sorted(os.listdir(org_dir)):
            if os.path.isfile(os.path.join(org_dir, name, "config.json")):
                orgs.append(name)
    return orgs


def _list_role_sets(org_config: dict | None) -> list[str]:
    """組織設定から利用可能なロールセット名を返す。
    優先順: demo_roles > organization_roles > roles >各 scenario
    """
    if not org_config:
        return []
    sets = []
    for k in ("demo_roles", "organization_roles", "roles"):
        if k in org_config:
            sets.append(k)
    for key in org_config.get("scenarios", {}):
        sets.append(f"scenario:{key}")
    return sets


def _load_org(org_name: str, role_set: str = "") -> tuple[MultiRoleManager, list[str]]:
    """組織を読み込んで (manager, role_names) を返す。
    role_set が空の場合は先頭のセットを自動選択する。
    """
    org_config = load_organization_config(org_name)
    if org_config is None:
        raise RuntimeError(f"組織 '{org_name}' の設定を読み込めませんでした。")
    # role_set 未指定の場合は先頭セットを選択
    available = _list_role_sets(org_config)
    if not role_set or role_set not in available:
        role_set = available[0] if available else ""
    manager = MultiRoleManager(AI_ASSISTANTS)
    # ロールセットを限定して読み込む
    if role_set and role_set.startswith("scenario:"):
        # scenarios キー配下の名前付きロールセット
        sc_key = role_set[len("scenario:"):]
        sc_roles = org_config.get("scenarios", {}).get(sc_key, [])
        patched = {k: v for k, v in org_config.items()
                   if k not in ("roles", "demo_roles", "organization_roles")}
        patched["demo_roles"] = sc_roles  # demo_roles として注入
        setup_organization_from_config(manager, patched)
    elif role_set and role_set in org_config:
        # 全ロールキーを除去してから選択セットだけを追加する
        # (setup_organization_from_config は "roles" キーを優先するため
        #  不要なキーを残すと空リストがヒットしてしまう)
        patched = {k: v for k, v in org_config.items()
                   if k not in ("roles", "demo_roles", "organization_roles")}
        patched[role_set] = org_config[role_set]
        setup_organization_from_config(manager, patched)
    else:
        setup_organization_from_config(manager, org_config)
    role_names = list(manager.active_roles.keys())
    return manager, role_names


def _roleset_label(key: str) -> str:
    """ロールセットキーを表示名に変換する。"""
    if key == "demo_roles":
        return "デモロール (demo_roles)"
    if key == "organization_roles":
        return "組織ロール (organization_roles)"
    if key == "roles":
        return "ロール (roles)"
    if key.startswith("scenario:"):
        return f"[シナリオ] {key[len('scenario:'):]}"
    return key


def _roleset_choices(sets: list[str]) -> list[tuple[str, str]]:
    """(表示名, 値) タプルリストを返す。"""
    return [(_roleset_label(k), k) for k in sets]


def _build_role_chain(role_info: dict):
    """ロール情報から LangChain チェーンを構築する（履歴は呼び出し元で管理）。"""
    llm = role_info["instance"]
    system_prompt = role_info["system_prompt"]
    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(system_prompt),
        MessagesPlaceholder("history"),
        HumanMessagePromptTemplate.from_template("{input}"),
    ])
    return prompt | llm


def _list_log_files() -> list[str]:
    """multi_logs/ 配下の .md ファイルを新しい順に返す。"""
    log_dir = "multi_logs"
    if not os.path.isdir(log_dir):
        return []
    return sorted(
        [f for f in os.listdir(log_dir) if f.endswith(".md")],
        reverse=True,
    )


def _read_log(filename: str) -> str:
    """ログファイルの内容を返す。"""
    if not filename:
        return "_ログファイルを選択してください_"
    path = os.path.join("multi_logs", filename)
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # CRLF → LF 正規化
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # コードブロック外の単独改行を <br> に変換（Gradio Markdown は単独 \n を改行しない）
        import re
        parts = re.split(r"(```.*?```)", content, flags=re.DOTALL)
        content = "".join(
            p if p.startswith("```") else re.sub(r"(?<!\n)\n(?!\n)", "<br>\n", p)
            for p in parts
        )
        # 旧ログの4スペースインデント（コードブロック化）をリスト形式に変換
        content = re.sub(r"(<br>\n) {4}(\S)", r"\1- \2", content)
        # Mermaid ブロック内の \n（リテラル）を <br/> に変換し、改行を正しく表示
        def _fix_mermaid_block(m: re.Match) -> str:
            return m.group(0).replace("\\n", "<br/>")
        content = re.sub(r"```mermaid.*?```", _fix_mermaid_block, content, flags=re.DOTALL)
        # Mermaid フロー図の前に注記を挿入
        content = re.sub(
            r"(```mermaid\n)",
            "> ⚠️ フロー図はライトモードで表示してください（ダークモードでは文字が見えません）\n\n\\1",
            content,
        )
        return content
    except Exception as e:
        return f"❌ 読み込みエラー: {e}"


def _make_role_info_md(role_names: list[str], manager: MultiRoleManager) -> str:
    """サイドバー用ロール一覧 Markdown を生成する。"""
    if not role_names:
        return "_ロールなし_"
    lines = ["**ロール一覧**", ""]
    for i, name in enumerate(role_names):
        info = manager.active_roles[name]
        emoji = ROLE_EMOJIS[i % len(ROLE_EMOJIS)]
        lines.append(
            f'{emoji} **{name}**  \n'
            f'<span style="font-size:0.85em; color:#888;">{info["assistant"]} / {info["model"]}</span>'
        )
    return "\n\n".join(lines)


def _build_css() -> str:
    return "\n".join([
        "#thread-chatbot { height: calc(100vh - 240px) !important; overflow-y: auto; }",
        "#log-viewer { height: calc(100vh - 160px); overflow-y: auto; padding: 1em;"
        " background: #ffffff !important; color: #111111 !important; border-radius: 8px; }",
        "#log-viewer * { color: #111111 !important; }",
        "#log-viewer pre, #log-viewer code {"
        " background: #f5f5f5 !important; color: #111111 !important; border: 1px solid #ddd; }",
        "#log-viewer svg text { fill: #000000 !important; }",
    ])


def _role_label(role_name: str, role_index: int) -> str:
    """ロール名を絵文字付きのベールに変換する。"""
    emoji = ROLE_EMOJIS[role_index % len(ROLE_EMOJIS)]
    return f"{emoji} **{role_name}**"


def _workflow_choices(org_config: dict | None) -> list[str]:
    """組織設定からワークフロー選択肢を返す。"""
    choices = ["(直接送信：全ロール)"]  # 常に先頭
    if org_config:
        for key, wf in org_config.get("workflows", {}).items():
            name = wf.get("name", key) if isinstance(wf, dict) else key
            choices.append(f"{key}\u300f{name}")
    return choices


def _phases_for_choice(manager: MultiRoleManager, org_config: dict | None, choice: str) -> list[dict]:
    """ワークフロー選択から phases リストを返す。
    直接送信時は全ロールを serial 1フェーズにまとめる。
    """
    if not choice or choice.startswith("(直接送信"):
        roles = list(manager.active_roles.keys())[:MAX_ROLES]
        return [{"type": "serial", "steps": [{"role": r} for r in roles]}]

    wf_key = choice.split("\u300f")[0]
    workflows = (org_config or {}).get("workflows", {})
    wf = workflows.get(wf_key)
    if wf:
        return wf.get("phases", [])
    return [{"type": "serial", "steps": [{"role": r} for r in manager.active_roles.keys()]}]



_sessions: dict[str, dict] = {}
# {session_id: {"manager": ..., "role_names": [...], "histories": {role: []}, "org_name": str, "role_set": str}}


def _get_session(session_id: str, org_name: str, role_set: str = "(全ロール)") -> dict:
    """セッションを取得。組織またはロールセットが変わった場合は再初期化する。"""
    sess = _sessions.get(session_id)
    if sess is None or sess.get("org_name") != org_name or sess.get("role_set") != role_set:
        manager, role_names = _load_org(org_name, role_set)
        sess = {
            "manager": manager,
            "role_names": role_names,
            "histories": {r: [] for r in role_names},
            "org_name": org_name,
            "role_set": role_set,
        }
        _sessions[session_id] = sess
    return sess


# --------------------------------------------------------------------------- #
#  UI builder
# --------------------------------------------------------------------------- #

def build_ui(default_org: str = "") -> gr.Blocks:
    org_list = _list_organizations()
    if not org_list:
        raise RuntimeError("organizations/ ディレクトリに config.json が見つかりません。")

    initial_org = default_org if default_org in org_list else org_list[0]
    initial_manager, initial_role_names = _load_org(initial_org)
    initial_role_sets = _list_role_sets(initial_manager.organization_config)
    initial_role_set = initial_role_sets[0] if initial_role_sets else ""

    css = _build_css()

    with gr.Blocks(title="MultiRoleChatWeb", fill_height=True) as demo:
        gr.Markdown("# 🎭 MultiRoleChatWeb")

        session_id = gr.State(lambda: __import__("uuid").uuid4().hex)

        with gr.Tabs():
            with gr.TabItem("💬 チャット"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=220):
                        gr.Markdown("### ⚙️ 設定")
                        org_dd = gr.Dropdown(
                            choices=org_list,
                            value=initial_org,
                            label="組織",
                        )
                        roleset_dd = gr.Dropdown(
                            choices=_roleset_choices(initial_role_sets),
                            value=initial_role_set,
                            label="ロールセット",
                        )
                        initial_wf_choices = _workflow_choices(
                            initial_manager.organization_config
                        )
                        workflow_dd = gr.Dropdown(
                            choices=initial_wf_choices,
                            value=initial_wf_choices[0] if initial_wf_choices else "",
                            label="ワークフロー",
                        )
                        role_info_md = gr.Markdown(
                            _make_role_info_md(initial_role_names, initial_manager)
                        )
                        clear_btn = gr.Button("🗑️ 履歴をクリア", variant="secondary")

                    with gr.Column(scale=5):
                        chatbot = gr.Chatbot(
                            label="スレッド",
                            elem_id="thread-chatbot",
                        )
                        with gr.Row():
                            msg_box = gr.Textbox(
                                placeholder="全ロールへのメッセージを入力して Enter",
                                label="",
                                scale=9,
                                autofocus=True,
                            )
                            send_btn = gr.Button("送信", variant="primary", scale=1)

            with gr.TabItem("📄 ログ"):
                with gr.Row():
                    with gr.Column(scale=1, min_width=220):
                        log_refresh_btn = gr.Button("🔄 一覧更新", variant="secondary")
                        log_list = gr.Dropdown(
                            choices=_list_log_files(),
                            value=None,
                            label="ログファイル",
                            interactive=True,
                        )
                    with gr.Column(scale=5):
                        log_view = gr.Markdown(
                            value="_ログファイルを選択してください_",
                            elem_id="log-viewer",
                        )

        # ------------------------------------------------------------------ #
        #  Event handlers
        # ------------------------------------------------------------------ #

        def on_org_change(org_name: str, sid: str):
            """組織切替: ロールセット・ワークフロー候補をリセットする。"""
            try:
                # まず org の org_config だけ先読みしてセット一覧を作成
                from MultiRoleChat import load_organization_config as _loc
                org_config = _loc(org_name)
                rs_choices = _list_role_sets(org_config)
                rs_value = rs_choices[0] if rs_choices else ""
                sess = _get_session(sid, org_name, rs_value)
                role_names = sess["role_names"]
                manager = sess["manager"]
            except Exception as e:
                return f"❌ {e}", gr.update(), gr.update(), []
            info = _make_role_info_md(role_names, manager)
            wf_choices = _workflow_choices(manager.organization_config)
            return (
                info,
                gr.update(choices=_roleset_choices(rs_choices), value=rs_value),
                gr.update(choices=wf_choices, value=wf_choices[0] if wf_choices else ""),
                [],
            )

        def on_roleset_change(org_name: str, role_set: str, sid: str):
            """ロールセット切替: チャット履歴とワークフロー候補を更新する。"""
            try:
                sess = _get_session(sid, org_name, role_set)
                role_names = sess["role_names"]
                manager = sess["manager"]
            except Exception as e:
                return f"❌ {e}", gr.update(), []
            info = _make_role_info_md(role_names, manager)
            wf_choices = _workflow_choices(manager.organization_config)
            return info, gr.update(choices=wf_choices, value=wf_choices[0]), []

        org_dd.change(
            on_org_change,
            inputs=[org_dd, session_id],
            outputs=[role_info_md, roleset_dd, workflow_dd, chatbot],
        )
        roleset_dd.change(
            on_roleset_change,
            inputs=[org_dd, roleset_dd, session_id],
            outputs=[role_info_md, workflow_dd, chatbot],
        )

        def on_submit(message, chat_val, org_name, role_set, workflow_choice, session_id_val):
            """メッセージを送信し、ワークフローに従って各ロールの回答を単一スレッドに追加する。
            serial: 1件ずつストリーミング。
            parallel: 全ロールをスレッド並列実行、完了後に一括表示。
            """
            if not message.strip():
                yield "", chat_val
                return

            try:
                sess = _get_session(session_id_val, org_name, role_set)
            except Exception as e:
                yield f"❌ {e}", chat_val
                return

            manager = sess["manager"]
            histories = sess["histories"]
            all_role_keys = list(manager.active_roles.keys())
            org_config = manager.organization_config
            phases = _phases_for_choice(manager, org_config, workflow_choice)

            # --- ログ初期化 ---
            os.makedirs("multi_logs", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"multi_logs/{timestamp}_web.md"
            wf_key = workflow_choice.split("｝")[0] if "｝" not in workflow_choice else workflow_choice
            wf_key = workflow_choice.split("\u300f")[0] if "\u300f" in workflow_choice else "web"
            pseudo_workflow = {
                "name": workflow_choice if not workflow_choice.startswith("(") else "直接送信",
                "description": f"Web UI からの送信 ({role_set})",
                "phases": phases,
            }
            manager._initialize_workflow_log(log_filename, pseudo_workflow, message, wf_key)
            session_start = time.time()
            step_num = [1]  # mutable counter for nested functions

            chat_val = (chat_val or []) + [{"role": "user", "content": message}]
            yield "", chat_val

            for phase in phases:
                phase_type = phase.get("type", "serial")
                steps = [
                    s for s in phase.get("steps", [])
                    if s.get("role") in manager.active_roles
                ]

                if phase_type == "parallel" and len(steps) > 1:
                    # --- 並列実行 ---
                    results: dict[str, str] = {}
                    errors_par: dict[str, str] = {}
                    elapsed_map: dict[str, float] = {}

                    def _run(role_name: str, _build_chain=_build_role_chain) -> None:
                        t0 = time.time()
                        try:
                            ri = manager.active_roles[role_name]
                            chain = _build_chain(ri)
                            lc_hist = histories[role_name]
                            text = ""
                            for chunk in chain.stream({"input": message, "history": lc_hist}):
                                text += getattr(chunk, "content", "") or ""
                            results[role_name] = text
                            lc_hist.append(HumanMessage(content=message))
                            lc_hist.append(AIMessage(content=text))
                        except Exception as ex:
                            errors_par[role_name] = str(ex)
                        elapsed_map[role_name] = time.time() - t0

                    role_idx_map = {
                        s["role"]: all_role_keys.index(s["role"])
                        for s in steps if s["role"] in all_role_keys
                    }
                    for s in steps:
                        rn = s["role"]
                        lbl = _role_label(rn, role_idx_map.get(rn, 0))
                        chat_val = chat_val + [{"role": "assistant", "content": f"{lbl}\n\n⏳ 並列実行中..."}]
                    yield "", chat_val

                    threads = [threading.Thread(target=_run, args=(s["role"],)) for s in steps]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join()

                    offset = len(chat_val) - len(steps)
                    for j, s in enumerate(steps):
                        rn = s["role"]
                        lbl = _role_label(rn, role_idx_map.get(rn, 0))
                        action = s.get("action", "")
                        if rn in results:
                            chat_val[offset + j] = {"role": "assistant", "content": f"{lbl}\n\n{results[rn]}"}
                            manager._append_step_to_log(log_filename, step_num[0], rn, action, results[rn], elapsed=elapsed_map.get(rn))
                        else:
                            err_text = f"❌ {errors_par.get(rn, '不明なエラー')}"
                            chat_val[offset + j] = {"role": "assistant", "content": f"{lbl}\n\n{err_text}"}
                            manager._append_step_to_log(log_filename, step_num[0], rn, action, err_text, elapsed=elapsed_map.get(rn))
                        step_num[0] += 1
                    yield "", chat_val

                else:
                    # --- serial 実行 ---
                    for s in steps:
                        role_name = s["role"]
                        action = s.get("action", "")
                        role_idx = all_role_keys.index(role_name) if role_name in all_role_keys else 0
                        label = _role_label(role_name, role_idx)

                        chat_val = chat_val + [{"role": "assistant", "content": f"{label}\n\n⏳ 考え中..."}]
                        yield "", chat_val

                        response_text = ""
                        t0 = time.time()
                        try:
                            role_info = manager.active_roles[role_name]
                            chain = _build_role_chain(role_info)
                            lc_history = histories[role_name]

                            chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n"}
                            for chunk in chain.stream({"input": message, "history": lc_history}):
                                content = getattr(chunk, "content", "") or ""
                                if content:
                                    response_text += content
                                    chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n{response_text}"}
                                    yield "", chat_val

                            lc_history.append(HumanMessage(content=message))
                            lc_history.append(AIMessage(content=response_text))

                        except Exception as e:
                            response_text = f"❌ {e}"
                            chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n{response_text}"}
                            yield "", chat_val

                        elapsed = time.time() - t0
                        manager._append_step_to_log(log_filename, step_num[0], role_name, action, response_text, elapsed=elapsed)
                        step_num[0] += 1

            # --- ログ完了 ---
            total_elapsed = time.time() - session_start
            manager._finalize_workflow_log(
                log_filename,
                manager.token_tracker.get_session_summary(),
                total_elapsed=total_elapsed,
            )
            yield "", chat_val

        msg_box.submit(on_submit, inputs=[msg_box, chatbot, org_dd, roleset_dd, workflow_dd, session_id], outputs=[msg_box, chatbot])
        send_btn.click(on_submit, inputs=[msg_box, chatbot, org_dd, roleset_dd, workflow_dd, session_id], outputs=[msg_box, chatbot])

        def on_clear(org_name: str, role_set: str, sid: str):
            """履歴を全クリアする。"""
            sess = _sessions.get(sid)
            if sess:
                for role_name in sess["histories"]:
                    sess["histories"][role_name] = []
            return []

        clear_btn.click(
            on_clear,
            inputs=[org_dd, roleset_dd, session_id],
            outputs=[chatbot],
        )

        # ---- ログタブ イベント ----
        log_list.change(
            _read_log,
            inputs=[log_list],
            outputs=[log_view],
        )
        log_refresh_btn.click(
            lambda: gr.update(choices=_list_log_files()),
            inputs=[],
            outputs=[log_list],
        )

    return demo


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="MultiRoleChatWeb - MultiRoleChat の Gradio Web UI"
    )
    parser.add_argument("--org", default=DEFAULT_ORG, help="デフォルト組織名")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="ポート番号")
    parser.add_argument("--share", action="store_true", help="外部公開URL付きで起動")
    args = parser.parse_args()

    print(f"[INFO] MultiRoleChatWeb v{VERSION} 起動中...")
    demo = build_ui(default_org=args.org)
    demo.launch(server_port=args.port, share=args.share, css=_build_css())


if __name__ == "__main__":
    main()

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
from web_input_utils import (
    build_uploaded_context,
    stream_default_from_config,
    temperature_default_from_config,
)

VERSION = "1.3.0"
VERSION_DATE = "2026-07-05"

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


def _stream_default_from_org_config(org_config: dict | None) -> bool:
    """ストリーミング表示の初期値を組織設定から取得する。

    優先順:
    1) web.stream
    2) ui.stream
    3) stream
    未設定または不正値は True。
    """
    return stream_default_from_config(org_config, default_value=True)


def _temperature_default_from_org_config(org_config: dict | None) -> float:
    """temperature の初期値を組織設定から取得する。"""
    return temperature_default_from_config(org_config, default_value=0.7)


def _build_role_chain(role_info: dict, temperature: float | None = None):
    """ロール情報から LangChain チェーンを構築する（履歴は呼び出し元で管理）。"""
    llm = role_info["instance"]
    if temperature is not None:
        # 一時対応として全ロール共通温度を bind で適用する。
        try:
            llm = llm.bind(temperature=float(temperature))
        except Exception:
            pass
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


# --------------------------------------------------------------------------- #
#  設定編集ヘルパー
# --------------------------------------------------------------------------- #

def _org_dir(org_name: str) -> str:
    return os.path.join("organizations", org_name)


def _config_path(org_name: str) -> str:
    return os.path.join(_org_dir(org_name), "config.json")


def _load_config_raw(org_name: str) -> dict:
    """config.json を dict で返す。"""
    import json
    path = _config_path(org_name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_config_raw(org_name: str, data: dict) -> None:
    """dict を config.json に保存する。"""
    import json
    path = _config_path(org_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _list_role_set_keys(org_name: str) -> list[str]:
    """config.json に存在するロールセットキー一覧を返す。"""
    try:
        data = _load_config_raw(org_name)
    except Exception:
        return []
    return [k for k in ("demo_roles", "organization_roles", "roles") if k in data]


def _get_roles_in_set(org_name: str, role_set_key: str) -> list[dict]:
    """指定ロールセットのロールリストを返す。"""
    try:
        data = _load_config_raw(org_name)
        return data.get(role_set_key, [])
    except Exception:
        return []


def _read_system_prompt(org_name: str, prompt_file: str) -> str:
    """roles/*.txt の内容を返す。prompt_file は config.json の値そのまま。"""
    if not prompt_file:
        return ""
    path = os.path.join(_org_dir(org_name), prompt_file)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _save_system_prompt(org_name: str, prompt_file: str, content: str) -> str:
    """roles/*.txt に内容を保存する。ファイルが存在しない場合は作成する。"""
    if not prompt_file:
        return "❌ prompt_file が空です"
    path = os.path.join(_org_dir(org_name), prompt_file)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ 保存しました: {prompt_file}"


def _save_role(org_name: str, role_set_key: str, original_name: str,
               name: str, assistant: str, model: str,
               role_type: str, prompt_file: str, prompt_content: str) -> str:
    """ロールのメタ情報をconfig.jsonに、プロンプト本文をtxtに保存する。"""
    try:
        data = _load_config_raw(org_name)
    except Exception as e:
        return f"❌ config.json 読み込みエラー: {e}"
    roles = data.get(role_set_key, [])
    # 対象ロールを検索して更新
    found = False
    for r in roles:
        if r.get("name") == original_name:
            r["name"] = name.strip()
            r["assistant"] = assistant.strip()
            r["model"] = model.strip()
            if role_type.strip():
                r["role_type"] = role_type.strip()
            elif "role_type" in r:
                del r["role_type"]
            r["system_prompt_file"] = prompt_file.strip()
            found = True
            break
    if not found:
        # 新規ロール追加
        new_role: dict = {
            "name": name.strip(),
            "assistant": assistant.strip(),
            "model": model.strip(),
            "system_prompt_file": prompt_file.strip(),
        }
        if role_type.strip():
            new_role["role_type"] = role_type.strip()
        roles.append(new_role)
        data[role_set_key] = roles
    _save_config_raw(org_name, data)
    # プロンプト本文を保存
    msg = _save_system_prompt(org_name, prompt_file.strip(), prompt_content)
    return f"✅ ロール '{name}' を保存しました。{msg}"


def _delete_role(org_name: str, role_set_key: str, role_name: str) -> str:
    """指定ロールをconfig.jsonから削除する。"""
    try:
        data = _load_config_raw(org_name)
    except Exception as e:
        return f"❌ config.json 読み込みエラー: {e}"
    roles = data.get(role_set_key, [])
    before = len(roles)
    data[role_set_key] = [r for r in roles if r.get("name") != role_name]
    if len(data[role_set_key]) == before:
        return f"❌ ロール '{role_name}' が見つかりません"
    _save_config_raw(org_name, data)
    return f"✅ ロール '{role_name}' を削除しました"


def _list_workflow_keys(org_name: str) -> list[str]:
    """config.json の workflows キー一覧を返す。"""
    try:
        data = _load_config_raw(org_name)
        return list(data.get("workflows", {}).keys())
    except Exception:
        return []


def _get_workflow_json(org_name: str, wf_key: str) -> str:
    """指定ワークフローをJSON文字列で返す。"""
    import json
    try:
        data = _load_config_raw(org_name)
        wf = data.get("workflows", {}).get(wf_key, {})
        return json.dumps(wf, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"❌ {e}"


def _save_workflow(org_name: str, wf_key: str, wf_json: str) -> str:
    """JSONテキストをconfig.jsonのworkflowsに保存する。"""
    import json
    key = wf_key.strip()
    if not key:
        return "❌ ワークフローキーが空です"
    try:
        wf_data = json.loads(wf_json)
    except json.JSONDecodeError as e:
        return f"❌ JSON パースエラー: {e}"
    try:
        data = _load_config_raw(org_name)
    except Exception as e:
        return f"❌ config.json 読み込みエラー: {e}"
    if "workflows" not in data:
        data["workflows"] = {}
    data["workflows"][key] = wf_data
    _save_config_raw(org_name, data)
    return f"✅ ワークフロー '{key}' を保存しました"


def _delete_workflow(org_name: str, wf_key: str) -> str:
    """指定ワークフローをconfig.jsonから削除する。"""
    try:
        data = _load_config_raw(org_name)
    except Exception as e:
        return f"❌ config.json 読み込みエラー: {e}"
    if wf_key not in data.get("workflows", {}):
        return f"❌ ワークフロー '{wf_key}' が見つかりません"
    del data["workflows"][wf_key]
    _save_config_raw(org_name, data)
    return f"✅ ワークフロー '{wf_key}' を削除しました"


def _create_organization(new_org_name: str) -> str:
    """新規組織フォルダとconfig.jsonを作成する。"""
    import json
    name = new_org_name.strip()
    if not name:
        return "❌ 組織名が空です"
    path = os.path.join("organizations", name)
    if os.path.exists(path):
        return f"❌ 組織 '{name}' はすでに存在します"
    os.makedirs(os.path.join(path, "roles"), exist_ok=True)
    initial = {
        "organization": name,
        "demo_roles": [],
        "workflows": {},
    }
    with open(os.path.join(path, "config.json"), "w", encoding="utf-8") as f:
        json.dump(initial, f, ensure_ascii=False, indent=2)
    return f"✅ 組織 '{name}' を作成しました"


def _list_assistants() -> list[str]:
    """AI_ASSISTANTS のキー一覧を返す（モデル選択補助用）。"""
    return sorted(AI_ASSISTANTS.keys())


def _list_models_for_assistant(assistant_name: str) -> list[str]:
    """指定アシスタントのモデル一覧を返す。"""
    info = AI_ASSISTANTS.get(assistant_name, {})
    models = info.get("models", [])
    if isinstance(models, list):
        return models
    return []


def _build_css() -> str:
    return "\n".join([
        "#thread-chatbot { height: calc(100vh - 240px) !important; overflow-y: auto; }",
        "#log-viewer { height: calc(100vh - 160px); overflow-y: auto; padding: 1em;"
        " background: #ffffff !important; color: #111111 !important; border-radius: 8px; }",
        "#log-viewer * { color: #111111 !important; }",
        "#log-viewer pre, #log-viewer code {"
        " background: #f5f5f5 !important; color: #111111 !important; border: 1px solid #ddd; }",
        "#log-viewer svg text { fill: #000000 !important; }",
        # Gradio デフォルトフッター（API・Built with Gradio・設定）を非表示
        ".gradio-container footer { display: none !important; }",
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
    initial_stream = _stream_default_from_org_config(initial_manager.organization_config)
    initial_temperature = _temperature_default_from_org_config(initial_manager.organization_config)

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
                        upload_files = gr.File(
                            label="ファイルを会話に取り込む（テキスト系）",
                            file_count="multiple",
                            type="filepath",
                        )
                        stream_cb = gr.Checkbox(
                            label="ストリーミング表示",
                            value=initial_stream,
                            info="未設定時はON。organizations/*/config.json の stream 設定で初期値を上書きできます。",
                        )
                        temperature_slider = gr.Slider(
                            minimum=0.0,
                            maximum=2.0,
                            step=0.1,
                            value=initial_temperature,
                            label="Temperature（全体）",
                            info="一時対応: 全ロール共通の温度。将来的にロール個別設定へ拡張予定。",
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

            # ------------------------------------------------------------------ #
            #  設定編集タブ
            # ------------------------------------------------------------------ #
            with gr.TabItem("⚙️ 設定編集"):
                with gr.Row():
                    # --- 左ペイン: 組織選択 ---
                    with gr.Column(scale=1, min_width=220):
                        gr.Markdown("### 🏢 組織")
                        edit_org_dd = gr.Dropdown(
                            choices=org_list,
                            value=initial_org,
                            label="組織を選択",
                        )
                        new_org_name = gr.Textbox(label="新規組織名", placeholder="フォルダ名（英数字）")
                        create_org_btn = gr.Button("➕ 新規作成", variant="secondary")
                        org_action_msg = gr.Markdown("")

                    # --- 右ペイン: ロール編集 / ワークフロー編集 ---
                    with gr.Column(scale=5):
                        with gr.Tabs():
                            # ---- ロール編集サブタブ ----
                            with gr.TabItem("👤 ロール編集"):
                                with gr.Row():
                                    _initial_rs_keys = _list_role_set_keys(initial_org)
                                    _initial_rs_val = _initial_rs_keys[0] if _initial_rs_keys else None
                                    edit_roleset_dd = gr.Dropdown(
                                        choices=_initial_rs_keys,
                                        value=_initial_rs_val,
                                        label="ロールセット",
                                    )
                                _initial_role_choices = [
                                    r["name"] for r in _get_roles_in_set(initial_org, _initial_rs_val)
                                ] if _initial_rs_val else []
                                with gr.Row():
                                    edit_role_dd = gr.Dropdown(
                                        choices=_initial_role_choices,
                                        value=None,
                                        label="ロールを選択",
                                        scale=4,
                                    )
                                    refresh_roles_btn = gr.Button("🔄", scale=1, min_width=50)
                                    delete_role_btn = gr.Button("🗑️ 削除", variant="stop", scale=1)

                                gr.Markdown("---")
                                with gr.Row():
                                    role_name_tb = gr.Textbox(label="name", scale=2)
                                    role_assistant_dd = gr.Dropdown(
                                        choices=_list_assistants(),
                                        label="assistant",
                                        scale=2,
                                        allow_custom_value=True,
                                    )
                                with gr.Row():
                                    role_model_tb = gr.Textbox(label="model", scale=3)
                                    role_type_tb = gr.Textbox(label="role_type（任意）", scale=2)
                                role_prompt_file_tb = gr.Textbox(
                                    label="system_prompt_file（例: roles/hinata.txt）"
                                )
                                role_prompt_ta = gr.Textbox(
                                    label="システムプロンプト本文",
                                    lines=12,
                                    max_lines=30,
                                )
                                with gr.Row():
                                    save_role_btn = gr.Button("💾 保存", variant="primary")
                                    new_role_btn = gr.Button("➕ 新規ロール", variant="secondary")
                                role_save_msg = gr.Markdown("")

                            # ---- ワークフロー編集サブタブ ----
                            with gr.TabItem("🔄 ワークフロー編集"):
                                with gr.Row():
                                    edit_wf_dd = gr.Dropdown(
                                        choices=_list_workflow_keys(initial_org),
                                        value=None,
                                        label="ワークフローを選択",
                                        scale=4,
                                    )
                                    refresh_wf_btn = gr.Button("🔄", scale=1, min_width=50)
                                    delete_wf_btn = gr.Button("🗑️ 削除", variant="stop", scale=1)
                                with gr.Row():
                                    new_wf_key_tb = gr.Textbox(
                                        label="新規キー名（英数字）",
                                        placeholder="例: my_workflow",
                                        scale=3,
                                    )
                                    new_wf_btn = gr.Button("➕ 新規作成", variant="secondary", scale=1)
                                wf_key_display = gr.Textbox(
                                    label="編集中のキー",
                                    interactive=False,
                                )
                                wf_json_ta = gr.Textbox(
                                    label="ワークフロー JSON",
                                    lines=20,
                                    max_lines=40,
                                )
                                with gr.Row():
                                    save_wf_btn = gr.Button("💾 保存", variant="primary")
                                wf_save_msg = gr.Markdown("")

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
            stream_default = _stream_default_from_org_config(manager.organization_config)
            temperature_default = _temperature_default_from_org_config(manager.organization_config)
            return (
                info,
                gr.update(choices=_roleset_choices(rs_choices), value=rs_value),
                gr.update(choices=wf_choices, value=wf_choices[0] if wf_choices else ""),
                gr.update(value=stream_default),
                gr.update(value=temperature_default),
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
            outputs=[role_info_md, roleset_dd, workflow_dd, stream_cb, temperature_slider, chatbot],
        )
        roleset_dd.change(
            on_roleset_change,
            inputs=[org_dd, roleset_dd, session_id],
            outputs=[role_info_md, workflow_dd, chatbot],
        )

        def on_submit(message, chat_val, org_name, role_set, workflow_choice, files, use_stream, temperature, session_id_val):
            """メッセージを送信し、ワークフローに従って各ロールの回答を単一スレッドに追加する。
            serial: ストリーミングON時は逐次表示、OFF時は一括表示。
            parallel: 全ロールをスレッド並列実行、完了後に一括表示。
            """
            raw_message = (message or "").strip()
            file_context, file_notes, used_file_names = build_uploaded_context(files)
            if not raw_message and used_file_names:
                raw_message = "添付ファイルの内容を要約してください。"

            if not raw_message:
                yield "", chat_val
                return

            prompt_input = f"{raw_message}{file_context}" if file_context else raw_message
            user_display = raw_message
            if used_file_names:
                user_display += f"\n\n📎 添付: {', '.join(used_file_names)}"
            if file_notes:
                user_display += f"\n\n{file_notes}"

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
            manager._initialize_workflow_log(log_filename, pseudo_workflow, user_display, wf_key)
            session_start = time.time()
            step_num = [1]  # mutable counter for nested functions

            chat_val = (chat_val or []) + [{"role": "user", "content": user_display}]
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
                            chain = _build_chain(ri, temperature)
                            lc_hist = histories[role_name]
                            if use_stream:
                                text = ""
                                for chunk in chain.stream({"input": prompt_input, "history": lc_hist}):
                                    text += getattr(chunk, "content", "") or ""
                            else:
                                response = chain.invoke({"input": prompt_input, "history": lc_hist})
                                content = getattr(response, "content", "") or ""
                                if isinstance(content, list):
                                    content = " ".join(str(item) for item in content)
                                text = str(content)
                            results[role_name] = text
                            lc_hist.append(HumanMessage(content=raw_message))
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
                            chain = _build_role_chain(role_info, temperature)
                            lc_history = histories[role_name]

                            if use_stream:
                                chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n"}
                                for chunk in chain.stream({"input": prompt_input, "history": lc_history}):
                                    content = getattr(chunk, "content", "") or ""
                                    if content:
                                        response_text += content
                                        chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n{response_text}"}
                                        yield "", chat_val
                            else:
                                response = chain.invoke({"input": prompt_input, "history": lc_history})
                                content = getattr(response, "content", "") or ""
                                if isinstance(content, list):
                                    content = " ".join(str(item) for item in content)
                                response_text = str(content)
                                chat_val[-1] = {"role": "assistant", "content": f"{label}\n\n{response_text}"}
                                yield "", chat_val

                            lc_history.append(HumanMessage(content=raw_message))
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

        msg_box.submit(on_submit, inputs=[msg_box, chatbot, org_dd, roleset_dd, workflow_dd, upload_files, stream_cb, temperature_slider, session_id], outputs=[msg_box, chatbot])
        send_btn.click(on_submit, inputs=[msg_box, chatbot, org_dd, roleset_dd, workflow_dd, upload_files, stream_cb, temperature_slider, session_id], outputs=[msg_box, chatbot])

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

        # ------------------------------------------------------------------ #
        #  設定編集タブ イベントハンドラ
        # ------------------------------------------------------------------ #

        # --- 組織切替（編集タブ用） ---
        def on_edit_org_change(org_name: str):
            rs_keys = _list_role_set_keys(org_name)
            rs_val = rs_keys[0] if rs_keys else None
            role_choices = [r["name"] for r in _get_roles_in_set(org_name, rs_val)] if rs_val else []
            wf_keys = _list_workflow_keys(org_name)
            return (
                gr.update(choices=rs_keys, value=rs_val),
                gr.update(choices=role_choices, value=None),
                gr.update(choices=wf_keys, value=None),
                "", "", "", "", "", "", "",
            )

        edit_org_dd.change(
            on_edit_org_change,
            inputs=[edit_org_dd],
            outputs=[
                edit_roleset_dd, edit_role_dd, edit_wf_dd,
                role_name_tb, role_assistant_dd, role_model_tb,
                role_type_tb, role_prompt_file_tb, role_prompt_ta, role_save_msg,
            ],
        )

        # --- 組織新規作成 ---
        def on_create_org(new_name: str):
            msg = _create_organization(new_name)
            orgs = _list_organizations()
            return gr.update(choices=orgs), gr.update(choices=orgs), msg, ""

        create_org_btn.click(
            on_create_org,
            inputs=[new_org_name],
            outputs=[org_dd, edit_org_dd, org_action_msg, new_org_name],
        )

        # --- ロールセット切替 ---
        def on_edit_roleset_change(org_name: str, rs_key: str):
            roles = _get_roles_in_set(org_name, rs_key) if rs_key else []
            choices = [r["name"] for r in roles]
            return gr.update(choices=choices, value=None), "", "", "", "", "", ""

        edit_roleset_dd.change(
            on_edit_roleset_change,
            inputs=[edit_org_dd, edit_roleset_dd],
            outputs=[
                edit_role_dd,
                role_name_tb, role_assistant_dd, role_model_tb,
                role_type_tb, role_prompt_file_tb, role_prompt_ta,
            ],
        )

        # --- ロール選択 ---
        def on_edit_role_change(org_name: str, rs_key: str, role_name: str):
            if not role_name or not rs_key:
                return "", "", "", "", "", ""
            roles = _get_roles_in_set(org_name, rs_key)
            role = next((r for r in roles if r.get("name") == role_name), None)
            if not role:
                return role_name, "", "", "", "", ""
            prompt_file = role.get("system_prompt_file", "")
            prompt_content = _read_system_prompt(org_name, prompt_file)
            return (
                role.get("name", ""),
                role.get("assistant", ""),
                role.get("model", ""),
                role.get("role_type", ""),
                prompt_file,
                prompt_content,
            )

        edit_role_dd.change(
            on_edit_role_change,
            inputs=[edit_org_dd, edit_roleset_dd, edit_role_dd],
            outputs=[
                role_name_tb, role_assistant_dd, role_model_tb,
                role_type_tb, role_prompt_file_tb, role_prompt_ta,
            ],
        )

        # --- ロール一覧更新 ---
        def on_refresh_roles(org_name: str, rs_key: str):
            roles = _get_roles_in_set(org_name, rs_key) if rs_key else []
            return gr.update(choices=[r["name"] for r in roles], value=None)

        refresh_roles_btn.click(
            on_refresh_roles,
            inputs=[edit_org_dd, edit_roleset_dd],
            outputs=[edit_role_dd],
        )

        # --- ロール保存 ---
        def on_save_role(org_name, rs_key, original_name,
                         name, assistant, model, role_type,
                         prompt_file, prompt_content):
            if not rs_key:
                return "❌ ロールセットが未選択です", gr.update()
            msg = _save_role(
                org_name, rs_key, original_name,
                name, assistant, model, role_type, prompt_file, prompt_content,
            )
            roles = _get_roles_in_set(org_name, rs_key)
            return msg, gr.update(choices=[r["name"] for r in roles], value=name.strip())

        save_role_btn.click(
            on_save_role,
            inputs=[
                edit_org_dd, edit_roleset_dd, edit_role_dd,
                role_name_tb, role_assistant_dd, role_model_tb,
                role_type_tb, role_prompt_file_tb, role_prompt_ta,
            ],
            outputs=[role_save_msg, edit_role_dd],
        )

        # --- 新規ロール（フォームをクリア） ---
        def on_new_role(org_name: str, rs_key: str):
            # 新規作成用: prompt_file のデフォルトパスを自動提案
            return None, "", "", "", "", f"roles/new_role.txt", ""

        new_role_btn.click(
            on_new_role,
            inputs=[edit_org_dd, edit_roleset_dd],
            outputs=[
                edit_role_dd,
                role_name_tb, role_assistant_dd, role_model_tb,
                role_type_tb, role_prompt_file_tb, role_prompt_ta,
            ],
        )

        # --- ロール削除 ---
        def on_delete_role(org_name: str, rs_key: str, role_name: str):
            if not role_name:
                return "❌ ロールが未選択です", gr.update()
            msg = _delete_role(org_name, rs_key, role_name)
            roles = _get_roles_in_set(org_name, rs_key)
            return msg, gr.update(choices=[r["name"] for r in roles], value=None)

        delete_role_btn.click(
            on_delete_role,
            inputs=[edit_org_dd, edit_roleset_dd, edit_role_dd],
            outputs=[role_save_msg, edit_role_dd],
        )

        # --- ワークフロー選択 ---
        def on_edit_wf_change(org_name: str, wf_key: str):
            if not wf_key:
                return "", ""
            return wf_key, _get_workflow_json(org_name, wf_key)

        edit_wf_dd.change(
            on_edit_wf_change,
            inputs=[edit_org_dd, edit_wf_dd],
            outputs=[wf_key_display, wf_json_ta],
        )

        # --- ワークフロー一覧更新 ---
        def on_refresh_wf(org_name: str):
            return gr.update(choices=_list_workflow_keys(org_name), value=None)

        refresh_wf_btn.click(
            on_refresh_wf,
            inputs=[edit_org_dd],
            outputs=[edit_wf_dd],
        )

        # --- ワークフロー保存 ---
        def on_save_wf(org_name: str, wf_key: str, wf_json: str):
            if not wf_key:
                return "❌ ワークフローキーが未選択/未入力です", gr.update()
            msg = _save_workflow(org_name, wf_key, wf_json)
            return msg, gr.update(choices=_list_workflow_keys(org_name), value=wf_key)

        save_wf_btn.click(
            on_save_wf,
            inputs=[edit_org_dd, wf_key_display, wf_json_ta],
            outputs=[wf_save_msg, edit_wf_dd],
        )

        # --- 新規ワークフロー作成 ---
        def on_new_wf(org_name: str, new_key: str):
            import json
            key = new_key.strip()
            if not key:
                return "❌ キー名が空です", gr.update(), "", ""
            template = json.dumps({
                "name": key,
                "description": "",
                "phases": [
                    {
                        "type": "serial",
                        "steps": [{"role": "ロール名", "action": "アクション説明"}],
                    }
                ],
            }, ensure_ascii=False, indent=2)
            msg = _save_workflow(org_name, key, template)
            return msg, gr.update(choices=_list_workflow_keys(org_name), value=key), key, template

        new_wf_btn.click(
            on_new_wf,
            inputs=[edit_org_dd, new_wf_key_tb],
            outputs=[wf_save_msg, edit_wf_dd, wf_key_display, wf_json_ta],
        )

        # --- ワークフロー削除 ---
        def on_delete_wf(org_name: str, wf_key: str):
            if not wf_key:
                return "❌ ワークフローが未選択です", gr.update()
            msg = _delete_workflow(org_name, wf_key)
            return msg, gr.update(choices=_list_workflow_keys(org_name), value=None)

        delete_wf_btn.click(
            on_delete_wf,
            inputs=[edit_org_dd, edit_wf_dd],
            outputs=[wf_save_msg, edit_wf_dd],
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
    demo.launch(server_port=args.port, share=args.share, inbrowser=True, css=_build_css(), prevent_thread_lock=True)
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

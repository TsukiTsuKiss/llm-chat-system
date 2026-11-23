#!/usr/bin/env python3
"""
MultiRoleStudioWeb のデモ自動操作

デモ専用のプロジェクトルートを一時フォルダに作り、Web UI をそこで起動して、
Playwright で画面を操作する。画面下部のキャプションは、ページに重ねるだけでアプリ本体は変更しない。
録画は次の 2 通り。
  - OBS などで録る: ブラウザを開いて実行し、読み上げはアプリがブラウザで再生する音を録る（--wait を使う）。
  - --record フォルダ: 画面なしで実行し、画面は Playwright が録画、声は保存された wav と
    timeline.jsonl から組み立てて、ffmpeg で 1 本の mp4 にする（表示装置・リモート音声に依存しない）。

事前準備:
  python -m pip install -r requirements.txt && python -m playwright install chromium
  VOICEVOX を起動しておく（読み上げシーン用）。API キーは環境変数で渡す（通常の起動と同じ）。--record には ffmpeg も必要。

使い方:
  python demo/make_demo.py                          # 全シーン
  python demo/make_demo.py --scenes chat,session    # シーンを指定
  python demo/make_demo.py --speed 0.5              # 待ち時間を半分にする（動作確認用）
  python demo/make_demo.py --mock --no-voice        # LLM を mock に置き換え、読み上げなしで通し確認（費用ゼロ）
  python demo/make_demo.py --keep-root              # 終了後もデモ用ルートを残す
  python demo/make_demo.py --wait                   # ブラウザを開いて Enter を待つ（OBS を合わせてから開始）
  python demo/make_demo.py --record demo/out        # 画面なしで実行し、demo/out/demo_<日時>.mp4 を作る

実データ（sessions/ など）には触れない。デモ用ルートは、実リポジトリの外に作り、そこだけで git init する。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import expect

REPO = Path(__file__).resolve().parent.parent

BROADCAST_TALENTS = ["midori", "akari", "souta", "gou", "haruka", "kento", "yuuma"]
DEMO_ORG = "broadcast_studio"
DEMO_WORKFLOW = "broadcast_news_digest"
DEMO_TOPIC = "今日の主要ニュースを6件、日本時間の最新の報道から取り上げてください。"

DEMO_CONTEXT_MD = """# ユーザーコンテキスト（デモ用）

- 呼び名: ゆうさん
- 趣味: 天体写真。週末は郊外で星空を撮ることが多い
- 説明は結論から、短く
"""

# コンテキスト RAG の素材（見出しごとに分割される）
DEMO_CORPUS = {
    "observing_notes.md": """# 観測メモ

## 月が明るい夜の撮影方針
月が明るい夜は、淡い星雲の撮影を避ける。代わりに月面・惑星・明るい二重星を狙う。
どうしても星雲を撮るなら、ナローバンドフィルターを使い、露出は短くして枚数で稼ぐ。

## 白飛びを避けるコツ
ライブスタッキングで中心部が白飛びするときは、停止しきい値を下げる。ゲインも一段下げて、1 枚あたりの露出を短くする。
""",
    "equipment.md": """# 機材メモ

## 赤道儀の準備
赤道儀は撮影の 30 分前に電源を入れ、温度順応させる。極軸合わせは撮影のたびに確認する。

## 結露対策
明け方は気温が下がって結露しやすい。ヒーターをレンズに巡らせ、片づける前に温めて乾かす。
""",
}

DEMO_MEMO_TXT = """来週の撮影計画
- 候補日: 土曜の夜（新月に近い）
- 場所: 郊外の駐車場
- 持ち物: 赤道儀、予備バッテリー、防寒着
- 注意: 日没後は冷えるので、機材の結露対策をする
"""

DEMO_SOLO_ORG = "demo_solo"
DEMO_SOLO_TALENT = "demo_assistant"

DEMO_CONFIRM_WORKFLOW = {
    "name": "デモ: 確認と続行",
    "description": "ユーザーへの質問（割り込み）と、続行・終了の選択を見せる",
    "interrupt_on": "【ユーザー確認】",
    "slots": {"assistant": {"description": "案内役", "count": "1"}},
    "phases": [
        {
            "type": "serial",
            "steps": [
                {
                    "slot": "assistant",
                    "action": "週末の過ごし方を A 案・B 案の 2 つ、各 1 行で出す。最後に必ず『【ユーザー確認】A と B のどちらが好みですか？』と書いて終える",
                }
            ],
        },
        {
            "type": "loop",
            "max_iterations": 3,
            "exit": {"type": "user", "prompt": "もう 1 案考えますか？"},
            "phases": [
                {
                    "type": "serial",
                    "steps": [
                        {
                            "slot": "assistant",
                            "action": "選ばれた案を踏まえ、別の切り口の提案を 1 つだけ、1 文で足す",
                        }
                    ],
                }
            ],
        },
    ],
}

CAPTION_JS = """
(text) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483647;'
      + 'max-width:80vw;padding:10px 22px;border-radius:10px;background:rgba(0,0,0,.72);color:#fff;'
      + 'font:600 24px/1.4 "Meiryo","Yu Gothic UI",sans-serif;text-align:center;pointer-events:none;';
    document.body.appendChild(el);
  }
  el.textContent = text || '';
  el.style.display = text ? 'block' : 'none';
}
"""


class Demo:
    """ページ操作の共通部品。speed は待ち時間の倍率（実生成の待ちには効かない）。"""

    def __init__(self, page, speed: float):
        self.page = page
        self.speed = speed
        self.marks: dict[str, float] = {}

    def wait(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000 * self.speed))

    def caption(self, text: str, hold: float = 2.0) -> None:
        self.page.evaluate(CAPTION_JS, text)
        self.wait(hold)

    def type_text(self, locator, text: str, delay_ms: int = 60) -> None:
        locator.click()
        locator.press_sequentially(text, delay=int(delay_ms * self.speed))


def free_port(preferred: int) -> int:
    import socket

    for port in range(preferred, preferred + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("空きポートがありません")


def force_remove(func, path, _exc) -> None:
    # Windows では .git 配下が読み取り専用のため、属性を外して消し直す
    os.chmod(path, stat.S_IWRITE)
    func(path)


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))


def build_demo_root(org: str, workflow: str, mock: bool = False, voicevox_url: str | None = None) -> Path:
    """実データから必要分だけをコピーしたデモ用ルートを、リポジトリ外の一時フォルダに作る。"""
    org_src = REPO / "organizations" / org
    mapping_src = org_src / "model_mapping.json"
    if not mock and not mapping_src.is_file():
        raise FileNotFoundError(
            f"{mapping_src} がありません。model_mapping.example.json をコピーし、使用するモデルを設定してください。"
        )

    root = Path(tempfile.mkdtemp(prefix="studio_demo_"))
    if REPO in root.resolve().parents:
        raise RuntimeError(f"デモ用ルートがリポジトリ内です: {root}")

    for name in ("ai_assistants_config.json", "model_costs.csv"):
        shutil.copy2(REPO / name, root / name)
    copy_tree(REPO / "schemas", root / "schemas")

    (root / "talents").mkdir()
    for talent in BROADCAST_TALENTS:
        shutil.copy2(REPO / "talents" / f"{talent}.json", root / "talents" / f"{talent}.json")

    (root / "workflows").mkdir()
    for path in (REPO / "workflows").glob("broadcast_*.json"):
        shutil.copy2(path, root / "workflows" / path.name)

    # 個人用の問題ではなく、同梱の問題セットを使う
    (root / "benchmark_questions").mkdir()
    shutil.copy2(REPO / "samples" / "benchmark" / "questions.example.json", root / "benchmark_questions" / "questions.example.json")

    org_dst = root / "organizations" / org
    org_dst.mkdir(parents=True)
    for path in org_src.iterdir():
        # 未承認の辞書候補は実データなのでコピーしない
        if path.is_file() and ".pending" not in path.name:
            shutil.copy2(path, org_dst / path.name)

    import json

    if mock:
        mapping_path = org_dst / "model_mapping.json"
        source = mapping_path if mapping_path.exists() else org_dst / "model_mapping.example.json"
        mapping = json.loads(source.read_text(encoding="utf-8"))
        mock_mapping = {talent: {"assistant": "mock"} for talent in mapping}
        mapping_path.write_text(json.dumps(mock_mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    config_path = REPO / "studio_config.json"
    if not config_path.exists():
        config_path = REPO / "studio_config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["default_org"] = org
    user_context = config.setdefault("user_context", {})
    user_context.update(enabled=True, path="user_context/my_context.md")
    rag_config = user_context.setdefault("rag", {})
    rag_config.update(enabled=True, corpus_dir="user_context/corpus", index_dir="user_context/index")
    (root / "studio_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    context_dir = root / "user_context"
    (context_dir / "corpus").mkdir(parents=True)
    (context_dir / "my_context.md").write_text(DEMO_CONTEXT_MD, encoding="utf-8")
    for name, text in DEMO_CORPUS.items():
        (context_dir / "corpus" / name).write_text(text, encoding="utf-8")
    (root / "demo_memo.txt").write_text(DEMO_MEMO_TXT, encoding="utf-8")

    # 文脈・割り込み・ウェブ検索・添付のデモ用に、人材 1 人だけの組織を用意する
    (root / "talents" / f"{DEMO_SOLO_TALENT}.json").write_text(
        json.dumps(
            {
                "name": "アシスタント",
                "system_prompt": "あなたは親切なアシスタントです。日本語で簡潔に答えます。ユーザーコンテキストや参考資料があれば、それを踏まえて答えます。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    solo_dir = root / "organizations" / DEMO_SOLO_ORG
    solo_dir.mkdir()
    (solo_dir / "config.json").write_text(
        json.dumps({"name": "デモ（ひとり）", "talent_ids": [DEMO_SOLO_TALENT]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    solo_mapping = (
        {"assistant": "mock"}
        if mock
        else {"assistant": "Anthropic", "model": "claude-haiku-5-5", "web_search": True}
    )
    (solo_dir / "model_mapping.json").write_text(
        json.dumps({DEMO_SOLO_TALENT: solo_mapping}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "workflows" / "demo_confirm.json").write_text(
        json.dumps(DEMO_CONFIRM_WORKFLOW, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 実データの名前やメモ（機材の型番）を映さないよう、voicevox_engines.json は汎用名で作り直す
    urls = [url.strip().rstrip("/") for url in (voicevox_url or "").split(",") if url.strip()]
    if urls:
        engines = [{"name": f"engine-{i}", "url": url} for i, url in enumerate(urls, 1)]
        (root / "voicevox_engines.json").write_text(
            json.dumps({"engines": engines}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 議事録・成果物採用の Git コミットが、実リポジトリではなくデモ用ルートに向くようにする
    git = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True, text=True)
    git("init", "-q")
    git("config", "user.name", "demo")
    git("config", "user.email", "demo@example.invalid")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: デモ用ルートの初期状態")
    return root


def start_server(root: Path, org: str, workflow: str, port: int, voicevox_url: str | None):
    cmd = [
        sys.executable, str(REPO / "MultiRoleStudioWeb.py"),
        "--root", str(root), "--org", org, "--workflow", workflow,
        "--port", str(port), "--no-browser",
    ]
    if voicevox_url:
        cmd += ["--voicevox-url", voicevox_url]
    log = open(root / "server.log", "w", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(cmd, cwd=REPO, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, env=env)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(120):
        if proc.poll() is not None:
            raise RuntimeError(f"サーバーが終了しました。ログ: {root / 'server.log'}")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return proc, url
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("サーバーの起動がタイムアウトしました")


def stop_server(proc) -> None:
    try:
        proc.stdin.write("q\n")
        proc.stdin.flush()
        proc.wait(timeout=10)
    except Exception:
        proc.terminate()


# --- シーン -----------------------------------------------------------------

IDLE = re.compile("待機中")


def chat_message_count(d: Demo) -> int:
    return d.page.locator("#studio-chatbot .message-row").count()


def wait_chat_idle(d: Demo, sent_from: int, timeout_s: int = 1800) -> None:
    """送信した発言が画面に出てから、状態欄が待機中に戻るまで待つ（発言と「実行中」は同じ更新で届く）。"""
    d.page.wait_for_function(
        "(n) => document.querySelectorAll('#studio-chatbot .message-row').length > n",
        arg=sent_from,
        timeout=30_000,
    )
    expect(d.page.get_by_label("状態", exact=True)).to_have_value(IDLE, timeout=timeout_s * 1000)


def wait_reading_done(d: Demo, quiet_s: float = 8.0, timeout_s: int = 900) -> None:
    """再生中の発言の枠（.studio-playing）が、発言の間の空きより長く出なくなるまで待つ。"""
    deadline = time.time() + timeout_s
    quiet_since = time.time()
    while time.time() < deadline:
        if d.page.locator("#studio-chatbot .studio-playing").count() > 0:
            quiet_since = time.time()
        elif time.time() - quiet_since >= quiet_s:
            return
        d.page.wait_for_timeout(500)


def scene_chat(d: Demo, args) -> None:
    page = d.page
    d.caption("MultiRoleStudio: 複数の AI 人材が役割分担して対話・番組・議論を進めます", 3.5)
    d.caption(f"組織「{args.org}」とワークフロー「{args.workflow}」が選ばれています", 3.0)

    if not args.no_voice:
        d.caption("「読み上げ」をオンにすると、各人材が自分の声で話します（声のない人材は読み上げません）", 2.5)
        page.get_by_label("読み上げ", exact=True).check()
        d.wait(1.0)

    d.caption("ウェブ検索をオンにすると、ニュースを最新の報道から調べて取り上げます", 2.5)
    page.get_by_label("ウェブ検索").check()
    d.wait(1.0)

    d.caption("メッセージを入力して送信します", 1.5)
    box = page.get_by_label("メッセージ", exact=True)
    d.type_text(box, args.topic)
    d.wait(0.8)
    sent_from = chat_message_count(d)
    d.marks["voice_start"] = time.time()  # 読み上げセッションの開始時刻（--record の声の位置合わせ）
    page.get_by_role("button", name="送信", exact=True).click()

    d.caption("各人材が順番に回答します（ストリーミング表示・所要時間・トークン・コスト付き）", 4.0)
    wait_chat_idle(d, sent_from)
    if not args.no_voice:
        d.caption("生成が完了しました。読み上げは再生中です", 1.5)
        wait_reading_done(d)
    # 以降のシーンで不要な検索が走らないように戻す
    page.get_by_label("ウェブ検索").uncheck()
    d.caption("", 0.1)


def open_timing_replay(d: Demo, timeout_s: int = 180) -> None:
    """「タイミング再生」を押し、再生ページが出るまで待つ。

    音声の再生成が短時間で終わると、結果の表示が直後の更新で消えることがあるため、
    再生成中でもないのに出ていなければ押し直す（2 回目は再生成が要らず、1 回の更新で出る）。
    """
    page = d.page
    iframe = page.locator("#studio-session-timing iframe")
    button = page.get_by_role("button", name="タイミング再生")
    panel = page.locator("#studio-session-panel")
    deadline = time.time() + timeout_s
    clicked_at = 0.0
    while time.time() < deadline:
        if iframe.count() and iframe.first.is_visible():
            return
        if time.time() - clicked_at > 8 and "作り直しています" not in panel.inner_text():
            button.click()
            clicked_at = time.time()
        page.wait_for_timeout(500)
    shot = Path(tempfile.gettempdir()) / "demo_timing_timeout.png"
    page.screenshot(path=str(shot))
    raise TimeoutError(f"タイミング再生が表示されませんでした（画面: {shot}）")


def show_flow(d: Demo, caption: str, hold: float = 3.0, max_steps: int = 6) -> None:
    """レポートのフロー図（Mermaid）を小窓の先頭に出し、図の高さに合わせて上から順に送って見せる。"""
    page = d.page
    page.locator(".studio-session-report .mermaid svg").first.wait_for(state="visible", timeout=30_000)
    # スクロールするのは外側の wrap ではなく、レポート自身
    scroller = ".studio-session-report-wrap > .studio-session-report"
    steps = page.evaluate(
        """(sel) => {
          const box = document.querySelector(sel);
          const diagram = box && box.querySelector('.mermaid');
          if (!box || !diagram) return 0;
          box.scrollBy({top: diagram.getBoundingClientRect().top - box.getBoundingClientRect().top - 8, behavior: 'smooth'});
          return Math.ceil(diagram.getBoundingClientRect().height / (box.clientHeight * 0.7));
        }""",
        scroller,
    )
    d.caption(caption, hold)
    for _ in range(min(max(int(steps) - 1, 0), max_steps)):
        page.evaluate(
            "(sel) => { const b = document.querySelector(sel); if (b) b.scrollBy({top: b.clientHeight * 0.7, behavior: 'smooth'}); }",
            scroller,
        )
        d.wait(2.0)


def scene_session(d: Demo, args) -> None:
    page = d.page
    d.caption("セッションタブ: 実行した対話は sessions/*.jsonl に記録され、あとから見返せます", 3.0)
    page.get_by_role("tab", name="📄 セッション").click()
    d.wait(1.0)
    page.get_by_role("button", name="一覧更新").first.click()
    d.wait(1.5)

    d.caption("レポートには、参加人材・使ったモデル・音声・費用がまとまります", 3.0)
    d.wait(2.0)
    show_flow(d, "フロー図（Mermaid）: 誰がどの順で話したかが図になり、並列の発言は枝分かれで表されます")

    page.get_by_label("ライト", exact=True).check()
    d.wait(1.5)
    show_flow(d, "フロー図のテーマは、ダークとライトを切り替えられます", hold=3.0, max_steps=2)

    message = page.locator("#studio-session-panel")
    d.caption("エクスポート: レポートを Markdown ファイルとして書き出します", 2.0)
    page.get_by_role("button", name="エクスポート (.md)").click()
    d.wait(3.0)

    d.caption("議事録: JSON を正本に、Markdown も生成して Git に記録します", 2.0)
    page.get_by_role("button", name="議事録 (.json + .md)").click()
    d.wait(3.5)

    d.caption("sandbox に保存: 成果物を作業場所に退避します", 2.0)
    page.get_by_role("button", name="sandbox に保存").click()
    d.wait(3.0)

    if not args.no_voice:
        d.caption("タイミング再生: 回答・音声合成・再生の時刻を、あとから見直せます", 2.5)
        open_timing_replay(d)
        d.wait(5.0)
        message.scroll_into_view_if_needed()
    d.caption("", 0.1)


def vis(locator):
    """同じラベルが複数タブにあるので、表示中のものだけに絞る。"""
    return locator.locator("visible=true")


def wait_for_benchmark_completion(page, timeout: int = 600_000) -> None:
    vis(page.get_by_text("✅ 完了しました")).first.wait_for(timeout=timeout)


def pick_option(d: Demo, dropdown, text: str) -> None:
    dropdown.click()
    d.wait(0.6)
    d.page.locator('[role="option"]').filter(has_text=text).first.click()


def scene_settings(d: Demo, args) -> None:
    page = d.page

    def button(name: str):
        return vis(page.get_by_role("button", name=name, exact=True))

    def field(label: str):
        return vis(page.get_by_label(label, exact=True))

    def message_after(hold: float = 2.5) -> None:
        # Gradio の読み込み表示（status-tracker）が消えるまで待ってから、見せる間を取る
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"status-tracker\"]:not(.hide)')",
            timeout=60_000,
        )
        d.wait(hold)

    d.caption("設定編集タブ: 人材・組織・ワークフローを、画面から作ってすぐ使えます", 3.0)
    page.get_by_role("tab", name="⚙️ 設定編集").click()
    d.wait(1.0)

    # --- 人材 ---
    page.get_by_role("tab", name="👤 人材").click()
    d.caption("人材: 名前・性格・system_prompt を編集して保存します（保存前にバリデーション）", 3.0)
    pick_option(d, field("人材 ID"), "akari")
    d.wait(1.5)
    d.type_text(field("personality"), " 聞き手に安心感を与える落ち着いた語り口。")
    button("保存").click()
    message_after()

    d.caption("新規作成: ID を入れて「新規作成」。ひな形が入るので、中身を書き換えます", 2.5)
    d.type_text(field("新規 ID"), "demo_guide")
    button("新規作成").click()
    message_after()
    d.type_text(field("name"), "デモガイド")
    d.type_text(field("system_prompt"), "あなたはデモ用の案内役です。質問に短く、やさしく答えます。")
    button("保存").click()
    message_after()

    # --- 組織 ---
    page.get_by_role("tab", name="🏢 組織").click()
    d.caption("組織: 人材を束ね、モデル割当（どの AI が話すか）を決めます", 3.0)
    d.type_text(field("新規組織 ID"), "demo_org")
    pick_option(d, field("初期人材（必須）"), "akari")
    button("新規作成").click()
    message_after(3.0)
    d.type_text(field("mission"), "デモ用の小さな組織")
    if not args.mock:
        d.caption("model_mapping: 人材ごとに、プロバイダーとモデルを選びます", 2.5)
        pick_option(d, field("assistant"), "Groq")
        d.wait(1.0)
        pick_option(d, field("model"), "openai/gpt-oss-120b")
        d.wait(1.0)
    button("model_mapping を保存").click()
    message_after()
    button("組織 config を保存").click()
    message_after()

    # --- ワークフロー ---
    page.get_by_role("tab", name="🔄 ワークフロー").click()
    d.caption("ワークフロー: スロットとフェーズを JSON で定義します（ここではひな形を作るだけ）", 3.0)
    d.type_text(field("新規 ID"), "demo_flow")
    button("新規作成").click()
    message_after(3.5)

    # --- できた組織で会話 ---
    # 直前のシーンで選んだワークフローが引き継がれるので、直接送信を明示する
    open_chat_tab(d, org="demo_org", workflow="直接送信")
    d.caption("作った組織は、チャットタブの「組織」にすぐ現れます", 3.0)
    send_chat(d, "自己紹介をしてください。")
    d.wait(3.0)

    # --- 後片付け ---
    d.caption("不要になった設定は、「削除」で消せます（使用中の人材は削除できません）", 3.0)
    page.get_by_role("tab", name="⚙️ 設定編集").click()
    page.get_by_role("tab", name="🏢 組織").click()
    pick_option(d, field("組織 ID"), "demo_org")
    d.wait(1.0)
    button("削除").click()
    message_after()
    page.get_by_role("tab", name="🔄 ワークフロー").click()
    pick_option(d, field("ワークフロー ID"), "demo_flow")
    d.wait(1.0)
    button("削除").click()
    message_after()
    page.get_by_role("tab", name="👤 人材").click()
    pick_option(d, field("人材 ID"), "demo_guide")
    d.wait(1.0)
    button("削除").click()
    message_after()
    d.caption("", 0.1)


def scene_benchmark(d: Demo, args) -> None:
    page = d.page
    d.caption("LLMベンチマーク: 同じ問題を、組織の各モデルに同じ条件で流して比べます", 3.0)
    page.get_by_role("tab", name="🎯 LLMベンチマーク").click()
    d.wait(1.5)

    d.caption("問題セット（JSON / JSONL）を選びます", 2.0)
    pick_option(d, vis(page.get_by_label(re.compile("から選ぶ"))), "questions.example.json")
    d.wait(1.5)

    d.caption("対象モデルを絞り込みます（プロバイダーごとに 1 つずつ）。呼び出し回数の見積も表示されます", 3.0)
    for talent in ("haruka", "yuuma", "kento", "gou"):
        vis(page.get_by_label(re.compile(rf"\({talent}\)"))).uncheck()
        d.wait(0.5)
    d.wait(2.0)

    d.caption("実行すると、進捗がリアルタイムに出ます（料金がかかるので、実行前に見積もりを確認）", 3.0)
    vis(page.get_by_role("button", name="実行", exact=True)).click()
    wait_for_benchmark_completion(page)
    d.caption("正解率・速度・コストがモデルごとに集計され、CSV と Markdown で保存されます", 3.0)
    page.get_by_role("heading", name="結果", exact=True).scroll_into_view_if_needed()
    d.wait(5.0)

    d.caption("過去の結果は、あとから開いて見返せます", 2.5)
    page.get_by_role("button", name="過去の結果").click()
    d.wait(1.0)
    vis(page.get_by_role("button", name="一覧更新", exact=True)).last.click()
    d.wait(1.0)
    pick_option(d, vis(page.get_by_label("結果", exact=True)), "20")
    d.wait(4.0)
    d.caption("", 0.1)


def label_field(page, label: str):
    return vis(page.get_by_label(label, exact=True))


def open_chat_tab(d: Demo, org: str | None = None, workflow: str | None = None, new_chat: bool = True) -> None:
    """チャットタブを開き、組織・ワークフローを選んで新規チャットにする。読み上げは切る。"""
    page = d.page
    page.get_by_role("tab", name="💬 チャット").click()
    d.wait(1.0)
    if org:
        pick_option(d, label_field(page, "組織"), org)
        d.wait(1.0)
    if workflow:
        pick_option(d, label_field(page, "ワークフロー"), workflow)
        d.wait(1.0)
    voice = page.get_by_label("読み上げ", exact=True)
    if voice.is_checked():
        voice.uncheck()
    if new_chat:
        page.get_by_role("button", name="新規チャット").click()
        d.wait(1.5)


def send_chat(d: Demo, text: str, wait: bool = True) -> None:
    """メッセージを打ち込んで送信し、（wait のとき）待機中に戻るまで待つ。"""
    page = d.page
    d.type_text(page.get_by_label("メッセージ", exact=True), text)
    sent_from = chat_message_count(d)
    page.get_by_role("button", name="送信", exact=True).click()
    if wait:
        wait_chat_idle(d, sent_from)


def wait_status(d: Demo, pattern: str, timeout_s: int = 300) -> None:
    expect(d.page.get_by_label("状態", exact=True)).to_have_value(re.compile(pattern), timeout=timeout_s * 1000)


def scene_context(d: Demo, args) -> None:
    page = d.page
    open_chat_tab(d, org=DEMO_SOLO_ORG, workflow="直接送信")
    d.caption("文脈の使い方: ユーザーコンテキスト・RAG・ウェブ検索・ファイル添付で、AI に情報を渡します", 3.5)

    rag = page.get_by_label("コンテキスト RAG")
    rag.uncheck()
    page.get_by_label("ユーザーコンテキスト", exact=True).check()
    d.caption("ユーザーコンテキスト: 趣味や呼び名を事前に登録しておくと、毎回説明しなくても踏まえてくれます", 3.5)
    send_chat(d, "私の趣味に合う週末の過ごし方を、一つ提案してください。")
    d.wait(4.0)

    d.caption("コンテキスト RAG: 手元のメモ（corpus）から、質問に関係する部分だけを探して渡します", 3.5)
    page.get_by_text("RAG ツール（corpus / index）").click()
    d.wait(1.0)
    vis(page.get_by_role("button", name="index 再構築", exact=True)).click()
    d.wait(3.0)
    d.type_text(label_field(page, "検索プレビュー（クエリ）"), "月が明るい夜")
    vis(page.get_by_role("button", name="検索プレビュー", exact=True)).click()
    d.wait(4.0)
    rag.check()
    send_chat(d, "観測メモにある、月が明るい夜の撮影方針を教えてください。")
    d.caption("回答の後、左のパネルに「今回渡した断片（chunk）」が出ます", 4.0)
    page.get_by_text("RAG ツール（corpus / index）").click()
    d.wait(1.0)

    d.caption("ウェブ検索: オンにすると、最新の情報を調べて答えます（対応したモデルのみ）", 3.5)
    page.get_by_label("ウェブ検索").check()
    send_chat(d, "今日の日本の主要ニュースを一つ、報道機関名と日付つきで教えてください。")
    page.get_by_label("ウェブ検索").uncheck()
    d.wait(4.0)

    d.caption("ファイル添付: テキスト系のファイルを会話に取り込めます", 3.0)
    page.locator("input[type='file']").first.set_input_files(str(args.root / "demo_memo.txt"))
    d.wait(2.5)
    send_chat(d, "添付したメモの要点を、一行で教えてください。")
    d.wait(4.0)
    d.caption("", 0.1)


def wait_choice_buttons(d: Demo) -> None:
    """続行/終了ボタンが出るまで待つ。

    出力が極端に速い（mock）と、ボタンを出す更新が前の更新で上書きされることがある。
    その場合は、選択待ちの間に文字を送ると、アプリが「ボタンを使ってください」とボタンを出し直す。
    """
    button = d.page.get_by_role("button", name="続行 (y)")
    try:
        button.wait_for(state="visible", timeout=5000)
    except Exception:
        send_chat(d, "続行", wait=False)
        button.wait_for(state="visible", timeout=10_000)


def answer_until_choice(d: Demo, caption: str | None = None) -> None:
    """質問（【ユーザー確認】）が出たら答え、続行/終了の選択が出るまで進める。"""
    page = d.page
    status = page.get_by_label("状態", exact=True)
    for answer in ("A にします。", "それでお願いします。", "はい、お願いします。", "そのままで構いません。"):
        wait_status(d, "質問に答えてください|続行または終了")
        if "続行または終了" in status.input_value():
            wait_choice_buttons(d)
            return
        if caption:
            d.caption(caption, 3.0)
            caption = None
        before = chat_message_count(d)
        send_chat(d, answer, wait=False)
        page.wait_for_function(
            "(n) => document.querySelectorAll('#studio-chatbot .message-row').length > n", arg=before, timeout=60_000
        )
    wait_status(d, "続行または終了")
    wait_choice_buttons(d)


def scene_interrupt(d: Demo, args) -> None:
    page = d.page
    open_chat_tab(d, org=DEMO_SOLO_ORG, workflow="demo_confirm")
    d.caption("割り込み: AI が確認したいとき、【ユーザー確認】で止まって質問します", 3.5)
    send_chat(d, "週末の予定を決めたい。", wait=False)
    answer_until_choice(d, "質問に答えると、その続きから実行が再開します")

    d.caption("続行 / 終了: ループの区切りで、続けるかをユーザーが決めます", 3.5)
    before = chat_message_count(d)
    page.get_by_role("button", name="続行 (y)").click()
    # 古い「続行または終了」のままを拾わないよう、新しい発言が出てから状態を見る
    page.wait_for_function(
        "(n) => document.querySelectorAll('#studio-chatbot .message-row').length > n", arg=before, timeout=60_000
    )
    answer_until_choice(d)
    d.caption("「終了」を選ぶと、ここで完了します", 2.5)
    page.get_by_role("button", name="終了 (n)").click()
    wait_status(d, "待機中")
    d.wait(3.0)
    d.caption("", 0.1)


def scene_voice(d: Demo, args) -> None:
    """セッションタブの「読みを点検」。チャットシーンで読み上げたセッションがあること。"""
    page = d.page
    if args.no_voice:
        print("[demo] voice: --no-voice のためスキップ")
        return
    d.caption("読みの点検: 誤読されそうな語を AI が探し、辞書に登録すると次から正しく読みます", 3.5)
    page.get_by_role("tab", name="📄 セッション").click()
    d.wait(1.0)
    page.get_by_role("button", name="一覧更新").first.click()
    d.wait(1.5)
    page.get_by_role("button", name="読みを点検（誤読候補）").click()
    page.get_by_text(re.compile("読み点検 — |読みの点検に失敗")).first.wait_for(timeout=300_000)
    d.wait(3.0)
    candidates = vis(page.locator("label:has(input[type='checkbox'])", has_text="→"))
    if candidates.count() == 0:
        d.caption("今回は新しい誤読候補がありませんでした", 3.0)
    else:
        d.caption("候補は未承認の辞書に入ります。選んで「本登録」すると、組織の辞書に反映されます", 3.5)
        candidates.first.check()
        d.wait(1.5)
        page.get_by_role("button", name="選択を辞書へ本登録").click()
        d.wait(3.5)
    d.caption("", 0.1)


def scene_voicevox(d: Demo, args) -> None:
    """VOICEVOX タブ。--voicevox-url の ENGINE が、デモ用ルートの voicevox_engines.json に入っている。"""
    page = d.page
    if args.no_voice or not args.voicevox_url:
        print("[demo] voicevox: --no-voice か --voicevox-url なしのためスキップ")
        return
    d.caption("VOICEVOX タブ: 読み上げに使う ENGINE を管理し、速さを測ります", 3.0)
    page.get_by_role("tab", name="🔊 VOICEVOX").click()
    page.get_by_text(re.compile("待機|未検出")).first.wait_for(timeout=60_000)
    d.caption("ENGINE の一覧です。状態・version・デバイスを表示し、有効/無効を切り替えられます", 3.5)
    d.wait(2.0)

    d.caption("ベンチマーク: 短・中・長の文を各 ENGINE に合成させ、速さを測ります。進捗はタイムラインに出ます", 3.5)
    page.get_by_role("heading", name=re.compile("ベンチマーク（ENGINE")).scroll_into_view_if_needed()
    vis(page.get_by_label("各文を何回ずつ流すか")).fill("1")
    vis(page.get_by_label("同時実行数（カンマ区切り）")).fill("1,2")
    d.wait(1.0)
    vis(page.get_by_role("button", name="実行", exact=True)).click()
    wait_for_benchmark_completion(page)
    d.caption("ENGINE ごとの速さが表になります。PC によって数倍違うので、将来の割り振りの最適化に使います", 4.0)
    page.get_by_text("速さ（2 回目以降の中央値）").first.scroll_into_view_if_needed()
    d.wait(5.0)

    d.caption("過去に読み上げたセッションの記録からも、ENGINE ごとの速さを集計できます", 3.5)
    page.get_by_role("heading", name="過去セッションの速さ").scroll_into_view_if_needed()
    vis(page.get_by_role("button", name="集計を更新", exact=True)).click()
    d.wait(4.0)
    d.caption("", 0.1)


def scene_voicemap(d: Demo, args) -> None:
    """設定編集の「🔊 声」サブタブ。声の一覧を ENGINE から取るので --voicevox-url が必要。保存はしない。"""
    page = d.page
    if args.no_voice or not args.voicevox_url:
        print("[demo] voicemap: --no-voice か --voicevox-url なしのためスキップ")
        return
    d.caption("声の設定: 人材の声（全組織共通）に、組織ごとの設定と、役割の話し方を重ねます", 3.5)
    page.get_by_role("tab", name="⚙️ 設定編集").click()
    d.wait(1.0)
    page.get_by_role("tab", name="🔊 声").click()
    page.get_by_text(re.compile("読み上げない|speaker")).first.wait_for(timeout=60_000)
    d.caption("人材ごとの、実際に使う声の一覧です。同じ声の人材がいると、警告が出ます", 3.5)
    d.wait(2.5)

    d.caption("人材を選んで、ENGINE から取った声（キャラ / スタイル）を選び直せます", 3.0)
    vis(page.get_by_label("声（キャラ / スタイル）")).scroll_into_view_if_needed()
    d.wait(2.0)

    d.caption("「特定の発言」を使うと、action に特定の文字を含むところだけ、速さや声を変えられます", 3.5)
    page.get_by_text("特定の発言（action）で声を切り替える").click()
    d.type_text(vis(page.get_by_label("発言1: action に含む文字列")), "放送後")
    d.type_text(vis(page.get_by_label("発言1: 速さ")), "1.3")
    d.wait(1.0)

    d.caption("保存する前に、試聴できます", 3.0)
    page.get_by_role("radio", name="特定の発言1").check()
    vis(page.get_by_role("button", name="▶ この組織の声を試聴")).click()
    page.locator("audio").first.wait_for(state="attached", timeout=60_000)
    d.wait(4.0)
    d.caption("", 0.1)


SCENES: dict[str, Callable[[Demo, argparse.Namespace], None]] = {
    "chat": scene_chat,
    "session": scene_session,
    "voice": scene_voice,
    "context": scene_context,
    "interrupt": scene_interrupt,
    "settings": scene_settings,
    "benchmark": scene_benchmark,
    "voicevox": scene_voicevox,
    "voicemap": scene_voicemap,
}


def build_voice_track(root: Path, offset: float, out_wav: Path) -> bool:
    """timeline.jsonl の再生開始時刻に発言の wav を並べて、動画と同じ時間軸の 1 本の音声にする。

    offset は「動画の開始から読み上げセッションの開始まで」の秒数。読み上げが無ければ False。
    """
    import json
    import wave

    import numpy as np

    audio_dirs = sorted(p for p in (root / "sessions" / "audio").glob("*") if (p / "timeline.jsonl").is_file())
    if not audio_dirs:
        return False
    if len(audio_dirs) > 1:
        print(f"[demo] 読み上げのセッションが複数あります。最初のものだけを使います: {audio_dirs[0].name}")
    audio_dir = audio_dirs[0]

    clips: list[tuple[float, Path]] = []
    for line in (audio_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("kind") == "play_start" and event.get("file"):
            path = audio_dir / event["file"]
            if path.is_file():
                clips.append((offset + float(event["t"]), path))
    if not clips:
        return False

    def load(path: Path):
        with wave.open(str(path)) as reader:
            data = np.frombuffer(reader.readframes(reader.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            if reader.getnchannels() > 1:
                data = data.reshape(-1, reader.getnchannels()).mean(axis=1)
            return reader.getframerate(), data

    rate = load(clips[0][1])[0]
    loaded: list[tuple[float, Any]] = []
    for start, path in clips:
        clip_rate, data = load(path)
        if clip_rate != rate:
            positions = np.linspace(0, len(data) - 1, int(len(data) * rate / clip_rate))
            data = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
        loaded.append((max(0.0, start), data))

    total = int(max(start * rate + len(data) for start, data in loaded)) + rate
    mix = np.zeros(total, dtype=np.float32)
    for start, data in loaded:
        begin = int(start * rate)
        mix[begin : begin + len(data)] += data
    pcm = (np.clip(mix, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(out_wav), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return True


def compose_mp4(video: Path, voice: Path | None, out: Path, loudness: float = 0.0) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg が見つかりません（PATH に通してください）")
    cmd = [ffmpeg, "-y", "-i", str(video)]
    if voice:
        cmd += ["-i", str(voice)]
    cmd += ["-c:v", "libx264", "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if voice:
        if loudness:
            # VOICEVOX の原音は小さいので、目標ラウドネス（LUFS）に合わせて上げる
            cmd += ["-af", f"loudnorm=I={loudness}:TP=-1.5:LRA=11"]
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd.append(str(out))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg が失敗しました:\n{result.stderr[-800:]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MultiRoleStudioWeb デモ自動操作")
    parser.add_argument("--scenes", default=",".join(SCENES), help=f"カンマ区切り（{', '.join(SCENES)}）")
    parser.add_argument("--org", default=DEMO_ORG)
    parser.add_argument("--workflow", default=DEMO_WORKFLOW)
    parser.add_argument("--topic", default=DEMO_TOPIC)
    parser.add_argument("--port", type=int, default=7870)
    parser.add_argument("--voicevox-url", default=None)
    parser.add_argument("--speed", type=float, default=1.0, help="待ち時間の倍率（0.5 で半分）")
    parser.add_argument("--size", default="1920x1300", help="ページの表示領域（幅x高さ）。画面に収まる大きさにする。ライブのタイムライン（高さ400px）をスクロールなしで見せるには縦 1250 以上")
    parser.add_argument("--keep-root", action="store_true", help="デモ用ルートを削除しない")
    parser.add_argument("--mock", action="store_true", help="LLM を mock に置き換える（費用ゼロ。読み上げを使うなら --no-voice を付けない）")
    parser.add_argument("--no-voice", action="store_true", help="読み上げと、それに依存する操作を省く")
    parser.add_argument("--headless", action="store_true", help="ブラウザを表示しない（開発時の確認用）")
    parser.add_argument("--wait", action="store_true", help="ブラウザを開いたあと Enter を押すまで待つ（OBS のウィンドウ選択・録画開始用）")
    parser.add_argument("--record", metavar="DIR", help="画面なしで実行し、画面と声を 1 本の mp4 にして DIR に出す（ffmpeg が必要）")
    parser.add_argument("--loudness", type=float, default=-16.0, help="--record の声の目標ラウドネス（LUFS。既定 -16。0 なら調整しない）")
    args = parser.parse_args()

    names = [s.strip() for s in args.scenes.split(",") if s.strip()]
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        parser.error(f"不明なシーン: {', '.join(unknown)}")
    width, height = (int(v) for v in args.size.lower().split("x"))
    record_dir = Path(args.record).resolve() if args.record else None
    if record_dir and not shutil.which("ffmpeg"):
        parser.error("--record には ffmpeg が必要です（PATH に通してください）")

    from playwright.sync_api import sync_playwright

    root = build_demo_root(args.org, args.workflow, mock=args.mock, voicevox_url=args.voicevox_url)
    print(f"[demo] デモ用ルート: {root}")
    proc = None
    failure: Exception | None = None
    video_tmp = Path(tempfile.mkdtemp(prefix="demo_video_")) if record_dir else None
    try:
        proc, url = start_server(root, args.org, args.workflow, free_port(args.port), args.voicevox_url)
        print(f"[demo] サーバー起動: {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=args.headless or record_dir is not None,
                args=["--autoplay-policy=no-user-gesture-required", f"--window-size={width},{height + 90}"],
            )
            context_options: dict[str, Any] = {"viewport": {"width": width, "height": height}}
            if video_tmp:
                # 既定では 800x800 に縮められるので、ページと同じサイズを指定する
                context_options.update(record_video_dir=str(video_tmp), record_video_size={"width": width, "height": height})
            context = browser.new_context(**context_options)
            page = context.new_page()
            video_start = time.time()
            page.goto(url)
            page.wait_for_selector("#studio-chatbot")
            d = Demo(page, args.speed)
            args.root = root
            if args.wait and not record_dir:
                input("[demo] ブラウザを開きました。OBS を設定して録画を始めたら、Enter でデモを始めます: ")
            current = ""
            try:
                for current in names:
                    print(f"[demo] シーン: {current}")
                    SCENES[current](d, args)
                d.caption("", 0.1)
            except Exception as exc:  # 途中で失敗しても、ここまでの録画は残す
                if not record_dir:
                    raise
                failure = exc
                print(f"[demo] シーン {current} で失敗しました: {exc!r:.300}")
            context.close()  # 動画ファイルはここで確定する
            video_path = Path(page.video.path()) if video_tmp else None
            browser.close()
        if record_dir and video_path:
            record_dir.mkdir(parents=True, exist_ok=True)
            voice_wav = video_tmp / "voice.wav"
            voice = None
            if "voice_start" in d.marks and build_voice_track(root, d.marks["voice_start"] - video_start, voice_wav):
                voice = voice_wav
            out_path = record_dir / f"demo_{time.strftime('%Y%m%d_%H%M%S')}{'_partial' if failure else ''}.mp4"
            try:
                compose_mp4(video_path, voice, out_path, args.loudness)
            except RuntimeError:
                kept = shutil.copy2(video_path, record_dir / video_path.name)
                print(f"[demo] mp4 への変換に失敗。録画は {kept} に残しました")
                raise
            print(f"[demo] 録画を保存しました: {out_path}{'' if voice else '（声なし）'}")
        if failure:
            raise failure
    finally:
        if proc is not None:
            stop_server(proc)
        if video_tmp:
            shutil.rmtree(video_tmp, ignore_errors=True)
        if args.keep_root:
            print(f"[demo] デモ用ルートを残しました: {root}")
        else:
            shutil.rmtree(root, onexc=force_remove)


if __name__ == "__main__":
    main()

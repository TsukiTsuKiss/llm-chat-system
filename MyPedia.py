from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi import HTTPException
from pydantic import BaseModel
from langchain_core.messages import AIMessage

import argparse
import os
import re
import time
import uvicorn

# Chat.py の LLM 接続ロジックをそのまま流用
from Chat import load_ai_assistants_config, load_assistant

app = FastAPI()

DEFAULT_ASSISTANT = "Groq"

INIT_ERROR = None
AI_ASSISTANTS = {}
AI_ASSISTANT = None
MODEL = None
llm = None

try:
    AI_ASSISTANTS = load_ai_assistants_config()
    AI_ASSISTANT = os.getenv("MYPEDIA_ASSISTANT", DEFAULT_ASSISTANT)
    if AI_ASSISTANT not in AI_ASSISTANTS:
        raise ValueError(f"無効なMYPEDIA_ASSISTANT: {AI_ASSISTANT}. 利用可能: {', '.join(AI_ASSISTANTS.keys())}")
    fast_mode = os.getenv("MYPEDIA_FAST", "false").lower() in {"1", "true", "yes", "on"}
    default_model = AI_ASSISTANTS[AI_ASSISTANT]["model"]
    if fast_mode and AI_ASSISTANTS[AI_ASSISTANT].get("fast_model"):
        default_model = AI_ASSISTANTS[AI_ASSISTANT]["fast_model"]
    MODEL = os.getenv("MYPEDIA_MODEL", default_model)
    llm = load_assistant(AI_ASSISTANTS, AI_ASSISTANT, MODEL)
    print(f"[INFO] MyPedia LLM: assistant={AI_ASSISTANT}, model={MODEL}")
except Exception as e:
    INIT_ERROR = str(e)
    print(f"[ERROR] MyPedia 初期化に失敗: {INIT_ERROR}")

HTML = """
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MyPedia Q&A</title>
<style>
	body{font-family:system-ui,sans-serif;max-width:900px;margin:24px;}
	textarea{width:100%;height:90px;}
	button{padding:10px 14px;margin-top:8px;}
	pre{white-space:pre-wrap;background:#f6f6f6;padding:12px;border-radius:8px;}
	.term{color:blue;cursor:pointer;text-decoration:underline;background:#eef4ff;border-radius:3px;padding:0 2px;margin:0 1px;}
</style>
</head>
<body>
<h2>MyPedia - Q&A</h2>
<textarea id="q" placeholder="例：ラズパイとは何ですか？"></textarea><br>
<button onclick="ask()">Ask</button>
<button id="backBtn" onclick="goBack()" disabled>戻る</button>
<button id="forwardBtn" onclick="goForward()" disabled>進む</button>
<div id="timing" style="margin-top:8px; font-size:14px;"></div>
<pre id="a"></pre>

<script>
const historyStack = [];
const forwardStack = [];
let currentState = null;

// term クリックを拾う（HTMLにonclickを埋めないので壊れにくい）
document.addEventListener("click", (e) => {
	const el = e.target.closest(".term");   // ← ここがポイント
	if (!el) return;
	drill(el.dataset.term);
});

function updateNavButtons(){
    document.getElementById("backBtn").disabled = historyStack.length === 0;
    document.getElementById("forwardBtn").disabled = forwardStack.length === 0;
}

function snapshotState(){
    return {
        query: document.getElementById("q").value,
        answerHtml: document.getElementById("a").innerHTML,
        timingText: document.getElementById("timing").textContent,
    };
}

function restoreState(state){
    document.getElementById("q").value = state.query ?? "";
    document.getElementById("a").innerHTML = state.answerHtml ?? "";
    document.getElementById("timing").textContent = state.timingText ?? "";
    currentState = { ...state };
    updateNavButtons();
}

function goBack(){
    if (!historyStack.length || !currentState) return;
    forwardStack.push({ ...currentState });
    const prev = historyStack.pop();
    restoreState(prev);
}

function goForward(){
    if (!forwardStack.length || !currentState) return;
    historyStack.push({ ...currentState });
    const next = forwardStack.pop();
    restoreState(next);
}

function drill(term){
	const timingEl = document.getElementById("timing");
	timingEl.textContent = "クリック検出: " + term;   // ← デバッグ表示

    // 短すぎる語は次検索に渡さない（汎用語ヒットを減らす）
    if (!term || term.length < 4 || term.length > 80) return;

	const q = `「${term}」とは何ですか？`;
	if (currentState && currentState.query === q) return;
	document.getElementById("q").value = q;
	ask();
}

function escapeHtml(s){
	return s.replace(/[&<>"']/g, c => ({
		"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
	}[c]));
}

function shouldLinkTerm(term){
    const t = term.trim().replace(/\\s+/g, " ");
    if (!t || /^[0-9]+$/.test(t)) return false;
    if (/^(?:参考になる)?検索語句[:：]?$/.test(t)) return false;
    if (/^参考語句[:：]?$/.test(t)) return false;
    if (/^関連検索語句[:：]?$/.test(t)) return false;
    if (/検索語句/.test(t)) return false;
    return t.length >= 4;
}

function escapeRegExp(s){
    return s.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\$&");
}

function buildHintPattern(term){
    return term
        .trim()
        .split(/\\s+/)
        .filter(Boolean)
        .map((part) => escapeRegExp(part))
        .join("\\\\s+");
}

// [[語句]] ヒントを最優先リンク化し、残る本文単語もリンク化する
function linkify(escaped){
    const hints = new Set();
    const placeholders = [];

    // 0) **太字** マーカーを除去してテキストとして残す（行全体は消さない）
    let text = escaped.replace(/[*][*]([^\\n*]+)[*][*]/g, '$1');

    // 1) [[語句]] のブラケットを除去しヒント語句を収集
    text = text.replace(/\\[\\[([^\\[\\]]{1,80})\\]\\]/g, (_, rawTerm) => {
        const t = rawTerm.trim();
        if (t && shouldLinkTerm(t)) hints.add(t);
        return t;
    });

    // 2) ヒント語句をリンク化してプレースホルダーに退避（長い順で優先マッチ）
    if (hints.size > 0) {
        const hintParts = [...hints]
            .sort((a, b) => b.length - a.length)
            .map((h) => buildHintPattern(h));
        const reHint = new RegExp(`(${hintParts.join("|")})`, "gu");
        text = text.replace(reHint, (m) => {
            const term = m.replace(/\\s+/g, " ").replace(/"/g, '&quot;');
            const html = `<span class="term" data-term="${term}" title="${term}を検索">${m}</span>`;
            const token = `\ue000${placeholders.length}\ue001`;
            placeholders.push(html);
            return token;
        });
    }

    // 3) フォールバック: 長い英単語 / カタカナ語 / 漢字語句をリンク化
    //    プレースホルダー（\uE000N\uE001）は正規表現に一致しないので安全
    const reFallback = /([A-Za-z][A-Za-z0-9._-]{3,}|[ァ-ヴー]{4,}|[一-龥々]{3,}(?:の[一-龥々]{2,}){0,2})/gu;
    text = text.replace(reFallback, (m) => {
        if (!shouldLinkTerm(m)) return m;
        const term = m.replace(/"/g, '&quot;');
        return `<span class="term" data-term="${term}" title="${term}を検索">${m}</span>`;
    });

    // 4) プレースホルダーを復元
    for (let i = 0; i < placeholders.length; i++) {
        text = text.replace(`\ue000${i}\ue001`, placeholders[i]);
    }

    return text;
}

async function ask(){
	const q = document.getElementById("q").value.trim();
	const pre = document.getElementById("a");
	const timingEl = document.getElementById("timing");
	if(!q) return;
    if (currentState && currentState.query === q) return;

    const prevState = snapshotState();
    forwardStack.length = 0;

	pre.textContent = "生成中...";
	const t0 = performance.now();
	timingEl.textContent = "送信中...";

	try{
		const res = await fetch("/ask", {
			method:"POST",
			headers: {"Content-Type":"application/json"},
			body: JSON.stringify({question:q})
		});

		// 失敗時の表示を分かりやすく
		if (!res.ok) {
			const text = await res.text();
			pre.textContent = text;
			timingEl.textContent = `HTTP ${res.status}`;
			return;
		}

		const data = await res.json();
		const answer = data.answer ?? "(no answer)";

		// 回答をリンク化して表示（日本語でも文章まるごとになりにくい）
		pre.innerHTML = linkify(escapeHtml(answer));

		const t1 = performance.now();
		if (data.server_ms != null) {
			timingEl.textContent = `表示まで: ${(t1-t0).toFixed(0)} ms / サーバ処理: ${data.server_ms.toFixed(0)} ms`;
		} else {
			timingEl.textContent = `表示まで: ${(t1-t0).toFixed(0)} ms`;
		}

        if (prevState.query || prevState.answerHtml || prevState.timingText) {
            historyStack.push(prevState);
        }
        currentState = snapshotState();
        updateNavButtons();
	} catch(e){
		pre.textContent = "エラー";
		timingEl.textContent = "通信エラー: " + e;
		updateNavButtons();
	}
}
</script>
</body>
</html>
"""


class AskReq(BaseModel):
    question: str


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.post("/ping")
async def ping():
    return {"ok": True}


@app.post("/ask")
async def ask(req: AskReq):
    if INIT_ERROR:
        raise HTTPException(status_code=500, detail=f"LLM初期化エラー: {INIT_ERROR}")

    prompt = f"""あなたは事実に基づいて回答するアシスタントです。
不明な場合は推測せず「分かりません」と言ってください。

出力形式を必ず守ってください。
1. まず質問への回答本文を書く。
2. その後、空行を1行入れてから、必ず次の見出しを1行だけ出す。
参考になる検索語句:
3. 見出しの直後に、[[語句]] を1行に1個ずつ 2〜5 行出す。

厳守ルール:
- 見出しは必ず「参考になる検索語句:」の完全一致にする
- 見出しを太字にしない（** を使わない）
- 見出し名を変更しない（例: 関連語句, 次に調べる語句 などは禁止）
- 箇条書き記号（-, *, ・, 1.）は使わない
- 語句は必ず [[...]] 形式にする
- なるべく具体的な語句（固有名詞・複合語）にする
- 短すぎる一般語（例: CPU, メモリ, 設定, 方法）は避ける
- 連続する概念は分割せず 1 つの語句にまとめる（例: [[Raspberry Pi 財団]]）
- 1語あたり 4〜30 文字程度

質問: {req.question}

日本語で簡潔に答えてください。"""

    t0 = time.perf_counter()
    response = await llm.ainvoke(prompt)
    t1 = time.perf_counter()

    if isinstance(response, AIMessage):
        answer_text = str(response.content).strip()
    else:
        answer_text = str(response).strip()

    # LLM出力の見出しゆらぎを吸収して表示を安定化
    answer_text = re.sub(
        r"(?m)^\s*\*{0,2}\s*(?:参考になる)?(?:関連)?検索語句\s*[:：]?\s*\*{0,2}\s*$",
        "参考になる検索語句:",
        answer_text,
    )
    answer_text = re.sub(r"(?m)^\s*[-*・]\s*(\[\[[^\]\n]{1,80}\]\])\s*$", r"\1", answer_text)
    answer_text = re.sub(r"(?m)^\s*\d+[.)]\s*(\[\[[^\]\n]{1,80}\]\])\s*$", r"\1", answer_text)
    answer_text = re.sub(r"(?m)([^\n])\n(参考になる検索語句:\s*$)", r"\1\n\n\2", answer_text)

    return {
        "answer": answer_text,
        "server_ms": (t1 - t0) * 1000.0,
        "assistant": AI_ASSISTANT,
        "model": MODEL,
    }


if __name__ == "__main__":
    _assistants = load_ai_assistants_config()
    _choices = list(_assistants.keys())

    parser = argparse.ArgumentParser(
        prog="MyPedia.py",
        description="MyPedia Q&A サーバー（外部LLM接続）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
使用例:
  python3 MyPedia.py                          # デフォルト設定（Groq）で起動
  python3 MyPedia.py -a ChatGPT               # ChatGPT で起動
  python3 MyPedia.py -a Gemini -m gemini-3-flash-preview
  python3 MyPedia.py --fast                   # fast_model に切り替えて起動
  python3 MyPedia.py --port 8080              # ポート指定

環境変数でも同様に切り替え可能:
  MYPEDIA_ASSISTANT=ChatGPT python3 MyPedia.py
  MYPEDIA_MODEL=gpt-5.4      python3 MyPedia.py
  MYPEDIA_FAST=true          python3 MyPedia.py

利用可能なアシスタント: {_choices}
        """,
    )
    parser.add_argument(
        "-a", "--assistant",
        default=None,
        choices=_choices,
        help=f"使用するアシスタントを指定（デフォルト: {DEFAULT_ASSISTANT}）",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="モデル名を直接指定（省略時はアシスタントのデフォルトモデルを使用）",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="fast_model に切り替えて起動",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="ホスト（デフォルト: 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="ポート番号（デフォルト: 8765）",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="ファイル変更時に自動リロード（開発用）",
    )

    args = parser.parse_args()

    # CLI 引数を環境変数に反映（モジュールレベルの初期化より後なので再初期化）
    if args.assistant:
        os.environ["MYPEDIA_ASSISTANT"] = args.assistant
    if args.fast:
        os.environ["MYPEDIA_FAST"] = "true"
    if args.model:
        os.environ["MYPEDIA_MODEL"] = args.model

    # 引数で上書きした場合は再初期化して表示
    if args.assistant or args.model or args.fast:
        import importlib, sys
        import MyPedia as _self
        _self.AI_ASSISTANTS = load_ai_assistants_config()
        _self.AI_ASSISTANT = os.environ.get("MYPEDIA_ASSISTANT", DEFAULT_ASSISTANT)
        fast_mode = os.environ.get("MYPEDIA_FAST", "false").lower() in {"1", "true", "yes", "on"}
        default_model = _self.AI_ASSISTANTS[_self.AI_ASSISTANT]["model"]
        if fast_mode and _self.AI_ASSISTANTS[_self.AI_ASSISTANT].get("fast_model"):
            default_model = _self.AI_ASSISTANTS[_self.AI_ASSISTANT]["fast_model"]
        _self.MODEL = os.environ.get("MYPEDIA_MODEL", default_model)
        _self.llm = load_assistant(_self.AI_ASSISTANTS, _self.AI_ASSISTANT, _self.MODEL)
        print(f"[INFO] MyPedia LLM 再設定: assistant={_self.AI_ASSISTANT}, model={_self.MODEL}")

    print(f"[INFO] MyPedia サーバー起動: http://{args.host}:{args.port}")
    uvicorn.run("MyPedia:app", host=args.host, port=args.port, reload=args.reload)

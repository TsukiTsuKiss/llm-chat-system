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
FAST_MODE = False
llm = None


def _resolve_model(assistant_name: str, fast_mode: bool) -> str:
    default_model = AI_ASSISTANTS[assistant_name]["model"]
    if fast_mode and AI_ASSISTANTS[assistant_name].get("fast_model"):
        default_model = AI_ASSISTANTS[assistant_name]["fast_model"]
    return default_model


def _reload_llm(assistant_name: str, fast_mode: bool, model_override: str | None = None) -> None:
    global AI_ASSISTANT, MODEL, FAST_MODE, llm
    if assistant_name not in AI_ASSISTANTS:
        raise ValueError(f"無効なassistant: {assistant_name}")
    default_model = _resolve_model(assistant_name, fast_mode)
    MODEL = model_override or default_model
    llm = load_assistant(AI_ASSISTANTS, assistant_name, MODEL)
    AI_ASSISTANT = assistant_name
    FAST_MODE = fast_mode


def _build_assistant_options() -> list[dict[str, str]]:
    options = []
    for name, conf in AI_ASSISTANTS.items():
        options.append(
            {
                "assistant": name,
                "model": conf.get("model", ""),
                "fast_model": conf.get("fast_model", ""),
            }
        )
    return options

try:
    AI_ASSISTANTS = load_ai_assistants_config()
    AI_ASSISTANT = os.getenv("MYPEDIA_ASSISTANT", DEFAULT_ASSISTANT)
    if AI_ASSISTANT not in AI_ASSISTANTS:
        raise ValueError(f"無効なMYPEDIA_ASSISTANT: {AI_ASSISTANT}. 利用可能: {', '.join(AI_ASSISTANTS.keys())}")
    FAST_MODE = os.getenv("MYPEDIA_FAST", "false").lower() in {"1", "true", "yes", "on"}
    MODEL = os.getenv("MYPEDIA_MODEL", _resolve_model(AI_ASSISTANT, FAST_MODE))
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
	.help-link{float:right;font-size:13px;color:#555;text-decoration:none;margin-top:6px;}
	.help-link:hover{color:#000;}
	details{margin-top:32px;border:1px solid #ddd;border-radius:8px;padding:12px 16px;background:#fafafa;}
	summary{cursor:pointer;font-weight:bold;font-size:15px;}
	.help-body{margin-top:12px;font-size:14px;line-height:1.7;}
	.help-body code{background:#eee;padding:1px 5px;border-radius:3px;font-size:13px;}
	.help-body table{border-collapse:collapse;width:100%;}
	.help-body th,.help-body td{border:1px solid #ccc;padding:5px 10px;text-align:left;font-size:13px;}
	.help-body th{background:#f0f0f0;}
    .settings-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0;}
    .settings-row label{font-size:13px;}
    .settings-row select{padding:4px 6px;}
    .settings-row button{margin-top:0;padding:6px 10px;}
    #llmStatus{font-size:12px;color:#444;}
    #tempStatus{font-size:12px;color:#666;margin-left:6px;}
</style>
</head>
<body>
<h2>MyPedia - Q&A <a class="help-link" href="/help" target="_blank">📖 ヘルプ（別タブ）</a></h2>
<div class="settings-row">
<label>プロバイダ:
<select id="assistantSel"></select>
</label>
<label>モード:
<select id="modeSel">
<option value="detail">詳細</option>
<option value="fast">高速</option>
</select>
</label>
<span id="llmStatus"></span>
</div>
<textarea id="q" placeholder="例：ラズパイとは何ですか？">かぐや姫の出した難題とは何だい？</textarea><br>
<button onclick="ask()">Ask</button>
<button id="backBtn" onclick="goBack()" disabled>戻る</button>
<button id="forwardBtn" onclick="goForward()" disabled>進む</button>
<label style="margin-left:16px;font-size:13px;">Temperature: <input type="range" id="temp" min="0" max="2" step="0.1" value="0" oninput="document.getElementById('tempVal').textContent=this.value" style="vertical-align:middle;"> <span id="tempVal">0</span></label><span id="tempStatus"></span>
<div id="timing" style="margin-top:8px; font-size:14px;"></div>
<pre id="a"></pre>

<details>
<summary>📖 ヘルプ</summary>
<div class="help-body">
<p>入力欄に質問を入れて <strong>Ask</strong> を押すと、LLM が回答します。</p>
<h3>基本操作</h3>
<table>
<tr><th>操作</th><th>説明</th></tr>
<tr><td>Ask</td><td>質問を送信して回答を表示</td></tr>
<tr><td>プロバイダ / モード</td><td>選択を変更すると LLM 設定が切り替わります（検索実行は Ask のみ）。</td></tr>
<tr><td>青いリンク語句をクリック</td><td>その語句で自動再検索（ドリルダウン）</td></tr>
<tr><td>戻る / 進む</td><td>閲覧履歴を前後に移動</td></tr>
<tr><td>Temperature スライダー</td><td>LLM の出力のランダム性を調整（0=確定的・事実寄り、1〜2=創造的・多様）。既定値は 0。</td></tr>
</table>
<h3>リンク語句について</h3>
<p>回答中に <code>[[語句]]</code> 形式で含まれた語句、および英単語・カタカナ語・漢字語句が自動でリンク化されます。クリックすると <code>「語句」とは何ですか？</code> を自動送信します。</p>
<h3>起動コマンド例</h3>
<table>
<tr><th>コマンド</th><th>説明</th></tr>
<tr><td><code>python3 MyPedia.py</code></td><td>Groq（既定）で起動</td></tr>
<tr><td><code>python3 MyPedia.py -a Grok</code></td><td>Grok で起動</td></tr>
<tr><td><code>python3 MyPedia.py -a Grok --model grok-3</code></td><td>モデル直接指定</td></tr>
<tr><td><code>python3 MyPedia.py --port 8080</code></td><td>ポート変更</td></tr>
</table>
<p style="margin-top:10px"><a href="/help" target="_blank">詳細ドキュメントを別タブで開く →</a></p>
</div>
</details>

<script>
const historyStack = [];
const forwardStack = [];
let currentState = null;
let assistantOptions = [];

function modeLabel(mode){
    return mode === "fast" ? "高速" : "詳細";
}

function findAssistantConfig(name){
    return assistantOptions.find((x) => x.assistant === name);
}

function renderLlmStatus(assistant, mode){
    const info = findAssistantConfig(assistant);
    if (!info) return;
    const model = mode === "fast" ? (info.fast_model || info.model) : info.model;
    document.getElementById("llmStatus").textContent = `現在: ${assistant} / ${modeLabel(mode)} / ${model}`;
}

async function loadLlmSettings(){
    try {
        const res = await fetch("/settings");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        assistantOptions = data.options || [];

        const sel = document.getElementById("assistantSel");
        sel.innerHTML = "";
        for (const opt of assistantOptions) {
            const o = document.createElement("option");
            o.value = opt.assistant;
            o.textContent = opt.assistant;
            sel.appendChild(o);
        }
        sel.value = data.current.assistant;

        const modeSel = document.getElementById("modeSel");
        modeSel.value = data.current.fast_mode ? "fast" : "detail";
        renderLlmStatus(sel.value, modeSel.value);
        sel.addEventListener("change", applyLlmSettings);
        modeSel.addEventListener("change", applyLlmSettings);
    } catch (e) {
        document.getElementById("llmStatus").textContent = "LLM設定の読み込みに失敗";
    }
}

async function applyLlmSettings(){
    const assistant = document.getElementById("assistantSel").value;
    const mode = document.getElementById("modeSel").value;
    const status = document.getElementById("llmStatus");
    status.textContent = "LLM設定を適用中...";
    try {
        const res = await fetch("/settings", {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({assistant, mode})
        });
        if (!res.ok) {
            const txt = await res.text();
            throw new Error(txt || `HTTP ${res.status}`);
        }
        const data = await res.json();
        renderLlmStatus(data.assistant, data.fast_mode ? "fast" : "detail");
        // 設定変更後は同一クエリでも Ask できるよう、重複ガード状態をクリア
        currentState = null;
        status.textContent += " / 次の Ask から反映";
    } catch (e) {
        status.textContent = "LLM設定の適用に失敗";
    }
}

document.addEventListener("DOMContentLoaded", loadLlmSettings);
document.addEventListener("DOMContentLoaded", () => {
    const temp = document.getElementById("temp");
    if (!temp) return;
    const tempStatus = document.getElementById("tempStatus");
    // Temperature を変えたら同一クエリでも Ask できるようにする
    temp.addEventListener("input", () => {
        currentState = null;
        if (tempStatus) tempStatus.textContent = "次のAskで反映";
    });
});

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
    const tempEl = document.getElementById("temp");
    const assistantEl = document.getElementById("assistantSel");
    const modeEl = document.getElementById("modeSel");
    return {
        query: document.getElementById("q").value,
        temperature: tempEl ? tempEl.value : "0",
        assistant: assistantEl ? assistantEl.value : "",
        mode: modeEl ? modeEl.value : "detail",
        answerHtml: document.getElementById("a").innerHTML,
        timingText: document.getElementById("timing").textContent,
    };
}

function restoreState(state){
    document.getElementById("q").value = state.query ?? "";
    const tempEl = document.getElementById("temp");
    if (tempEl && state.temperature != null) {
        tempEl.value = state.temperature;
        const tempVal = document.getElementById("tempVal");
        if (tempVal) tempVal.textContent = state.temperature;
    }
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

async function ask(force=false){
	const q = document.getElementById("q").value.trim();
	const temp = document.getElementById("temp")?.value ?? "0";
	const assistant = document.getElementById("assistantSel")?.value ?? "";
	const mode = document.getElementById("modeSel")?.value ?? "detail";
    const tempStatus = document.getElementById("tempStatus");
	const pre = document.getElementById("a");
	const timingEl = document.getElementById("timing");
	if(!q) return;
    if (
        !force &&
        currentState &&
        currentState.query === q &&
        currentState.temperature === temp &&
        currentState.assistant === assistant &&
        currentState.mode === mode
    ) return;

    const prevState = snapshotState();
    forwardStack.length = 0;

	pre.textContent = "生成中...";
	const t0 = performance.now();
	timingEl.textContent = "送信中...";

	try{
        if (tempStatus) tempStatus.textContent = "";
		const res = await fetch("/ask", {
			method:"POST",
			headers: {"Content-Type":"application/json"},
			body: JSON.stringify({question:q, temperature:parseFloat(document.getElementById("temp").value)})
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
    temperature: float = 0.0


class SettingsReq(BaseModel):
    assistant: str
    mode: str = "detail"
    model: str | None = None


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/help", response_class=HTMLResponse)
def help_page():
    doc_path = os.path.join(os.path.dirname(__file__), "docs", "mypedia", "README.md")
    try:
        md = open(doc_path, encoding="utf-8").read()
    except FileNotFoundError:
        md = "ドキュメントが見つかりません。"

    # Markdown を簡易 HTML 変換
    import html as _html
    lines = md.split("\n")
    body_lines = []
    in_code = False
    in_ul = False
    for line in lines:
        esc = _html.escape(line)
        if esc.startswith("```"):
            if in_ul:
                body_lines.append("</ul>"); in_ul = False
            if in_code:
                body_lines.append("</code></pre>"); in_code = False
            else:
                body_lines.append("<pre><code>"); in_code = True
        elif in_code:
            body_lines.append(esc)
        elif esc.startswith("### "):
            if in_ul: body_lines.append("</ul>"); in_ul = False
            body_lines.append(f"<h3>{esc[4:]}</h3>")
        elif esc.startswith("## "):
            if in_ul: body_lines.append("</ul>"); in_ul = False
            body_lines.append(f"<h2>{esc[3:]}</h2>")
        elif esc.startswith("# "):
            if in_ul: body_lines.append("</ul>"); in_ul = False
            body_lines.append(f"<h1>{esc[2:]}</h1>")
        elif esc.startswith("- "):
            if not in_ul: body_lines.append("<ul>"); in_ul = True
            body_lines.append(f"<li>{esc[2:]}</li>")
        elif esc == "":
            if in_ul: body_lines.append("</ul>"); in_ul = False
        else:
            if in_ul: body_lines.append("</ul>"); in_ul = False
            body_lines.append(f"<p>{esc}</p>")
    if in_ul: body_lines.append("</ul>")
    if in_code: body_lines.append("</code></pre>")

    body = "\n".join(body_lines)
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MyPedia ヘルプ</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:24px;line-height:1.6;}}
h1{{margin:16px 0 8px;}}
h2{{margin:14px 0 6px;}}
h3{{margin:10px 0 4px;}}
p{{margin:4px 0;}}
ul{{margin:4px 0 4px 24px;padding:0;}}
li{{margin:2px 0;}}
pre{{background:#f4f4f4;padding:10px 12px;border-radius:6px;overflow-x:auto;white-space:pre-wrap;margin:6px 0;}}
code{{background:#eee;padding:1px 5px;border-radius:3px;font-size:0.9em;}}
</style></head><body>
{body}
<p style="margin-top:24px"><a href="/">&larr; MyPedia に戻る</a></p>
</body></html>"""


@app.post("/ping")
async def ping():
    return {"ok": True}


@app.get("/settings")
def get_settings():
    if INIT_ERROR:
        raise HTTPException(status_code=500, detail=f"LLM初期化エラー: {INIT_ERROR}")
    return {
        "current": {
            "assistant": AI_ASSISTANT,
            "model": MODEL,
            "fast_mode": FAST_MODE,
        },
        "options": _build_assistant_options(),
    }


@app.post("/settings")
def update_settings(req: SettingsReq):
    global INIT_ERROR
    try:
        fast_mode = req.mode == "fast"
        _reload_llm(req.assistant, fast_mode, req.model)
        INIT_ERROR = None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LLM再設定エラー: {e}")
    return {
        "ok": True,
        "assistant": AI_ASSISTANT,
        "model": MODEL,
        "fast_mode": FAST_MODE,
    }


@app.post("/ask")
async def ask(req: AskReq):
    if INIT_ERROR:
        raise HTTPException(status_code=500, detail=f"LLM初期化エラー: {INIT_ERROR}")

    prompt = f"""あなたは知識豊富なアシスタントです。質問に対して分かりやすく答えてください。
- 質問の内容を勝手に読み替えたり、関係ない話題にしないでください。
- 確信がない情報には「〜と言われています」「〜の可能性があります」など留保を付けてください。

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
    try:
        response = await llm.bind(temperature=req.temperature).ainvoke(prompt)
    except Exception:
        # temperature 非対応モデルはそのまま呼ぶ
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
        _self.FAST_MODE = os.environ.get("MYPEDIA_FAST", "false").lower() in {"1", "true", "yes", "on"}
        default_model = _self._resolve_model(_self.AI_ASSISTANT, _self.FAST_MODE)
        _self.MODEL = os.environ.get("MYPEDIA_MODEL", default_model)
        _self.llm = load_assistant(_self.AI_ASSISTANTS, _self.AI_ASSISTANT, _self.MODEL)
        print(f"[INFO] MyPedia LLM 再設定: assistant={_self.AI_ASSISTANT}, model={_self.MODEL}")

    print(f"[INFO] MyPedia サーバー起動: http://{args.host}:{args.port}")
    uvicorn.run("MyPedia:app", host=args.host, port=args.port, reload=args.reload)

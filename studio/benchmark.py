"""クイズ形式のベンチマーク（問題セットの読み込み・並列実行・自動採点・集計）。

人材ごとの assistant / model（model_mapping.json）を使い、人格を付けない共通の指示で、同じ問題を同じ条件で投げる。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from studio.assistants import InvokeResult, invoke_llm_step, invoke_mock_step
from studio.errors import detect_api_error
from studio.history import ConversationHistory
from studio.loader import SessionContext
from studio.logging import load_model_costs

SYSTEM_PROMPTS = {
    "answer": (
        "あなたは問題に答える解答者です。最終行を『答え: ○』の形式だけで出力してください"
        "（選択肢がある問題では ○ は選択肢の記号）。理由や前置きは書かないでください。"
    ),
    "reason": (
        "あなたは問題に答える解答者です。簡潔な理由（100文字以内）を述べたうえで、最終行を『答え: ○』の形式にしてください"
        "（選択肢がある問題では ○ は選択肢の記号）。"
    ),
}

RESULT_COLUMNS = [
    "question_id", "trial", "talent_id", "name", "assistant", "model", "temperature", "status", "answer", "expected",
    "correct", "elapsed", "wall", "tokens_in", "tokens_out", "tokens_source", "cost", "attempts", "rate_limited", "error",
]
SUMMARY_COLUMNS = [
    "rank", "talent_id", "name", "provider", "model", "trials_ok", "errors", "scored", "correct", "accuracy",
    "median_sec", "p95_sec", "mean_sec", "mean_out_tokens", "total_cost", "cost_per_correct", "rate_limited",
    "price_known",
]

# 429 で待つときの設定（サーバーが示した待ち時間に足す余裕・示されないときの既定値・上限・1 回答あたりの待ち回数）
RATE_WAIT_MARGIN = 1.0
DEFAULT_RATE_WAIT = 30.0
MAX_RATE_WAIT = 120.0
MAX_RATE_WAITS = 5


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    choices: dict[str, str] = field(default_factory=dict)
    answer: str | None = None
    source: str = ""


@dataclass(frozen=True)
class Target:
    talent_id: str
    name: str
    assistant: str
    model: str
    assistant_cfg: dict[str, Any]


Invoker = Callable[[Target, str, str], InvokeResult]


@dataclass
class BenchmarkReport:
    out_dir: Path
    rows: list[dict[str, Any]]
    summary: list[dict[str, Any]]
    cancelled: bool = False


class BenchmarkCancelled(Exception):
    """中断要求を受けて試行をやめた。"""


def _label(value: str) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().upper()


def model_label(provider: str, model: str) -> str:
    """表示用の「プロバイダー (モデル)」。"""
    return f"{provider} ({model})" if model else provider


def unpriced_targets(costs: dict[str, dict[str, float]], targets: list[Target]) -> list[Target]:
    """単価表（model_costs.csv）に載っていないモデル。計算は既定単価になる。"""
    return [t for t in targets if t.assistant != "mock" and t.model not in costs]


def default_price_text(costs: dict[str, dict[str, float]]) -> str:
    default = costs["default"]
    return f"入力 ${default['input'] * 1e6:g} / 出力 ${default['output'] * 1e6:g}（100 万トークンあたり）"


class _RateLimiter:
    """モデルごとの呼び出し間隔（rpm）と、2 回目以降に待つ 429 後の休止を、同じモデルを使う全スレッドで共有する。"""

    def __init__(self, rpm: float | None) -> None:
        self._interval = 60.0 / rpm if rpm else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self, cancel: threading.Event | None = None) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self._interval
        if start > now:
            if cancel is None:
                time.sleep(start - now)
            else:
                cancel.wait(start - now)
        if cancel is not None and cancel.is_set():
            raise BenchmarkCancelled

    def defer(self, seconds: float) -> None:
        with self._lock:
            self._next = max(self._next, time.monotonic() + seconds)


def _retry_after(message: str) -> float | None:
    """エラー文が示す「この秒数後に再試行」を秒で返す。無ければ None。"""
    match = re.search(r"(?:retry|try again) in ([0-9.]+)\s*(ms|s)\b", message, re.IGNORECASE)
    if match:
        value = float(match.group(1).rstrip("."))
        return value / 1000 if match.group(2).lower() == "ms" else value
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", message)
    return float(match.group(1)) if match else None


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).lower()


def load_questions(path: Path) -> list[Question]:
    """問題セット（JSON: 配列または {"questions": [...]}、JSONL: 1 行 1 問）を読む。"""
    raw = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() == ".jsonl":
        items: Any = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        data = json.loads(raw)
        items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("問題が 1 件もありません")

    questions: list[Question] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not str(item.get("question") or "").strip():
            raise ValueError(f"{index} 件目: question がありません")
        question_id = str(item.get("id", index))
        if question_id in seen:
            raise ValueError(f"id が重複しています: {question_id}")
        seen.add(question_id)
        raw_choices = item.get("choices") or {}
        if not isinstance(raw_choices, dict):
            raise ValueError(f"{question_id}: choices は {{記号: 本文}} の形で書いてください")
        choices = {_label(key): str(value) for key, value in raw_choices.items()}
        answer = item.get("answer")
        expected = None if answer in (None, "") else (_label(answer) if choices else str(answer))
        if choices and expected is not None and expected not in choices:
            raise ValueError(f"{question_id}: answer '{answer}' が choices にありません")
        questions.append(
            Question(question_id, str(item["question"]).strip(), choices, expected, str(item.get("source") or ""))
        )
    return questions


def build_user_message(question: Question) -> str:
    lines = [question.text]
    lines.extend(f"{label}) {text}" for label, text in question.choices.items())
    return "\n".join(lines)


_ANSWER_LINE = re.compile(r"答え\s*[:：]\s*([^\n]+)")
_LEADING_LABEL = re.compile(r"[\s*「『(（\[]*([A-Za-z])(?![A-Za-z0-9])")


def extract_answer(text: str, choices: dict[str, str]) -> str:
    """回答本文から答えを取り出す。最終行の『答え: ○』を優先し、取れなければ空文字。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    found = _ANSWER_LINE.findall(normalized)
    if found:
        value = found[-1].strip()
    elif choices and len(normalized.strip()) == 1:
        value = normalized.strip()
    else:
        return ""
    if choices:
        match = _LEADING_LABEL.match(value)
        label = match.group(1).upper() if match else ""
        return label if label in choices else ""
    return value.strip(" 。.*「」『』")


def is_correct(answer: str, expected: str | None) -> int | str:
    if expected is None:
        return ""
    return int(bool(answer) and _norm_text(answer) == _norm_text(expected))


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def select_targets(ctx: SessionContext, talent_ids: list[str] | None = None) -> list[Target]:
    available = [tid for tid in ctx.org.get("talent_ids") or [] if ctx.model_mapping.get(tid, {}).get("assistant") != "human"]
    if talent_ids:
        unknown = [tid for tid in talent_ids if tid not in available]
        if unknown:
            raise ValueError(f"組織 '{ctx.org_id}' の対象外の人材です: {', '.join(unknown)}")
        available = list(talent_ids)
    if not available:
        raise ValueError("ベンチマークの対象になる人材がありません")
    targets = []
    for tid in available:
        mapping = ctx.model_mapping.get(tid, {})
        assistant = mapping.get("assistant", "")
        targets.append(
            Target(
                talent_id=tid,
                name=ctx.talents.get(tid, {}).get("name", tid),
                assistant=assistant,
                model=mapping.get("model", ""),
                assistant_cfg=ctx.assistants.get(assistant, {}),
            )
        )
    return targets


def make_invoker(root: Path, temperature: float | None) -> Invoker:
    costs = load_model_costs(root)

    def invoke(target: Target, system_prompt: str, user_message: str) -> InvokeResult:
        history = ConversationHistory()
        if target.assistant == "mock":
            return invoke_mock_step(target.talent_id, 1, stream=False, history=history, user_message=user_message)
        # 再試行は _run_trial 側で行い、待ち時間を応答時間に含めない（ライブラリ内部の再試行を無効化）
        return invoke_llm_step(
            assistant_name=target.assistant,
            assistant_cfg=target.assistant_cfg,
            model=target.model,
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
            temperature=temperature,
            stream=False,
            costs=costs,
            max_retries=1,
            client_kwargs={"max_retries": 0},
        )

    return invoke


def _run_trial(
    invoker: Invoker,
    target: Target,
    question: Question,
    trial: int,
    system_prompt: str,
    retries: int,
    retry_delay: float,
    gate: threading.Semaphore,
    limiter: _RateLimiter,
    cancel: threading.Event | None = None,
) -> tuple[dict[str, Any], str]:
    user_message = build_user_message(question)
    row: dict[str, Any] = {
        "question_id": question.id, "trial": trial, "talent_id": target.talent_id, "name": target.name,
        "assistant": target.assistant, "model": target.model, "temperature": "", "expected": question.answer or "",
        "status": "error", "answer": "", "correct": "", "elapsed": "", "wall": "", "tokens_in": "",
        "tokens_out": "", "tokens_source": "", "cost": "", "attempts": 0, "rate_limited": 0, "error": "",
    }
    text = ""
    attempt = 0
    with gate:
        while True:
            row["attempts"] = attempt + 1
            limiter.wait(cancel)
            began = time.perf_counter()
            try:
                result = invoker(target, system_prompt, user_message)
            except Exception as exc:
                message = str(exc)
                row["error"] = f"{type(exc).__name__}: {message}"
                if detect_api_error(message) == "429" and row["rate_limited"] < MAX_RATE_WAITS:
                    # 制限に当たったときは、サーバーが示した秒数だけ同じモデルの呼び出しを止めてから再試行する
                    row["rate_limited"] += 1
                    wait = (_retry_after(message) or DEFAULT_RATE_WAIT) + RATE_WAIT_MARGIN
                    limiter.defer(min(wait, MAX_RATE_WAIT))
                    continue
                if attempt < retries:
                    time.sleep(retry_delay * (attempt + 1))
                    attempt += 1
                    continue
                break
            text = result.text
            answer = extract_answer(text, question.choices)
            row.update(
                status="ok", error="", answer=answer, correct=is_correct(answer, question.answer),
                temperature="" if result.temperature is None else result.temperature,
                elapsed=round(result.elapsed, 3), wall=round(time.perf_counter() - began, 3),
                tokens_in=result.tokens_in, tokens_out=result.tokens_out, tokens_source=result.tokens_source,
                cost=round(result.cost, 6),
            )
            break
    return row, text


def summarize(
    rows: list[dict[str, Any]], targets: list[Target], unpriced: set[str] | None = None
) -> list[dict[str, Any]]:
    summary = []
    for target in targets:
        mine = [r for r in rows if r["talent_id"] == target.talent_id]
        ok = [r for r in mine if r["status"] == "ok"]
        scored = [r for r in ok if r["correct"] != ""]
        correct = sum(int(r["correct"]) for r in scored)
        times = [float(r["elapsed"]) for r in ok]
        cost = sum(float(r["cost"]) for r in ok)
        summary.append(
            {
                "talent_id": target.talent_id, "name": target.name, "provider": target.assistant,
                "model": target.model,
                "trials_ok": len(ok), "errors": len(mine) - len(ok), "scored": len(scored), "correct": correct,
                "accuracy": round(correct / len(scored), 4) if scored else "",
                "median_sec": round(percentile(times, 50), 3) if times else "",
                "p95_sec": round(percentile(times, 95), 3) if times else "",
                "mean_sec": round(sum(times) / len(times), 3) if times else "",
                "mean_out_tokens": round(sum(int(r["tokens_out"]) for r in ok) / len(ok), 1) if ok else "",
                "total_cost": round(cost, 6),
                "cost_per_correct": round(cost / correct, 6) if correct else "",
                "rate_limited": sum(int(r["rate_limited"]) for r in mine),
                "price_known": target.talent_id not in (unpriced or set()),
            }
        )

    def sort_key(entry: dict[str, Any]) -> tuple[float, float]:
        accuracy = entry["accuracy"] if entry["accuracy"] != "" else -1.0
        median = entry["median_sec"] if entry["median_sec"] != "" else float("inf")
        return (-accuracy, median)

    summary.sort(key=sort_key)
    for rank, entry in enumerate(summary, start=1):
        entry["rank"] = rank
    return summary


def format_summary_table(summary: list[dict[str, Any]]) -> str:
    """記事に貼れる Markdown の表。正解率優先、同率は中央値の短い順。"""
    def pct(value: Any) -> str:
        return f"{value * 100:.1f}%" if value != "" else "-"

    def sec(value: Any) -> str:
        return f"{value:.2f}秒" if value != "" else "-"

    lines = [
        "| 順位 | モデル | 正解率 | 正解/採点 | 中央値 | p95 | 平均出力トークン | コスト | エラー |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for entry in summary:
        tokens = f"{entry['mean_out_tokens']:.0f}" if entry["mean_out_tokens"] != "" else "-"
        cost = f"${entry['total_cost']:.4f}" + ("" if entry.get("price_known", True) else "*")
        lines.append(
            f"| {entry['rank']} | {model_label(entry['provider'], entry['model'])} | {pct(entry['accuracy'])} "
            f"| {entry['correct']}/{entry['scored']} | {sec(entry['median_sec'])} | {sec(entry['p95_sec'])} "
            f"| {tokens} | {cost} | {entry['errors']} |"
        )
    if any(not entry.get("price_known", True) for entry in summary):
        lines.extend(["", "\\* 単価が未登録のため、既定単価で概算した値です（`model_costs.csv` に追加してください）"])
    return "\n".join(lines)


def miss_lines(rows: list[dict[str, Any]]) -> list[str]:
    """誤答のあった問題ごとに、誤答したモデルと回数を出す。"""
    misses: dict[str, dict[str, int]] = {}
    for row in rows:
        if row["status"] == "ok" and row["correct"] == 0:
            label = model_label(row["assistant"], row["model"])
            by_name = misses.setdefault(row["question_id"], {})
            by_name[label] = by_name.get(label, 0) + 1
    return [f"Q{qid}: " + ", ".join(f"{name}×{count}" for name, count in names.items()) for qid, names in misses.items()]


def format_report_markdown(
    title: str,
    conditions: str,
    summary: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    questions: list[Question],
    targets: list[Target],
) -> str:
    """結果フォルダに置く summary.md（条件・順位表・問題別の正答数・誤答した問題）。"""
    scored_ids = {q.id for q in questions if q.answer is not None}
    header = ["問題", *(model_label(t.assistant, t.model) for t in targets)]
    matrix = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for question in questions:
        if question.id not in scored_ids:
            continue
        cells = []
        for target in targets:
            mine = [r for r in rows if r["question_id"] == question.id and r["talent_id"] == target.talent_id]
            ok = [r for r in mine if r["status"] == "ok"]
            cell = f"{sum(int(r['correct']) for r in ok)}/{len(ok)}" if ok else "-"
            cells.append(cell + (f" (エラー{len(mine) - len(ok)})" if len(mine) > len(ok) else ""))
        matrix.append(f"| Q{question.id} | " + " | ".join(cells) + " |")

    misses = miss_lines(rows)
    used = ["| ID | 出典 | 問題文（先頭） | 正解 |", "|---|---|---|---|"]
    for question in questions:
        head = question.text.splitlines()[0][:40].replace("|", "｜")
        used.append(f"| Q{question.id} | {question.source or '-'} | {head} | {question.answer or '-'} |")
    mapping = ["| タレント | プロバイダー | モデル |", "|---|---|---|"]
    mapping.extend(f"| {t.name} ({t.talent_id}) | {t.assistant} | {t.model or '-'} |" for t in targets)
    parts = [
        f"# {title}",
        "",
        "## 条件",
        "",
        conditions,
        "",
        "## 対象（タレントとプロバイダー・モデルの対応）",
        "",
        *mapping,
        "",
        "## 順位",
        "",
        format_summary_table(summary),
        "",
        "## 問題別の正解数（正解/回答できた回数）",
        "",
        *matrix,
        "",
        "## 誤答のあった問題",
        "",
        *([f"- {line}" for line in misses] or ["- なし"]),
        "",
        "## 使用した問題",
        "",
        *used,
        "",
    ]
    return "\n".join(parts)


def _conditions_lines(
    ctx: SessionContext,
    questions: list[Question],
    targets: list[Target],
    rows: list[dict[str, Any]],
    *,
    trials: int,
    style: str,
    temperature: float | None,
    max_parallel: int,
    per_provider: int,
    retries: int,
    rpm: float | None,
    questions_path: Path | None,
    questions_label: str | None,
    command: str,
    costs: dict[str, dict[str, float]],
) -> str:
    """結果に影響する実行条件（問題セット・試行・temperature など）を箇条書きにする。"""
    if questions_path is not None and Path(questions_path).is_file():
        digest = hashlib.sha256(Path(questions_path).read_bytes()).hexdigest()[:8]
        shown = questions_label or Path(questions_path).as_posix()
        source = f"`{shown}`（{len(questions)} 問、sha256 先頭 {digest}）"
    else:
        source = f"{len(questions)} 問"
    temperature_text = "プロバイダー既定" if temperature is None else str(temperature)
    fell_back = [
        model_label(t.assistant, t.model)
        for t in targets
        if temperature is not None
        and t.assistant != "mock"
        and any(r["talent_id"] == t.talent_id and r["status"] == "ok" and r["temperature"] == "" for r in rows)
    ]
    if fell_back:
        temperature_text += f"（指定値を受け付けず既定値で実行: {', '.join(fell_back)}）"
    lines = [
        f"- 問題セット: {source}",
        f"- 組織: {ctx.org_id} / 対象: {len(targets)} モデル（下の対応表）",
        f"- 試行: {trials} 回 / 指示: {style} / temperature: {temperature_text}",
        f"- 同時実行: 全体 {max_parallel} / プロバイダーごと {per_provider} / 再試行: {retries} 回",
        "- 応答時間: ライブラリ内部の再試行を無効化（対応するクライアントのみ）し、429 の待ち時間は含めない",
    ]
    if rpm:
        lines.append(f"- 呼び出し頻度の上限: モデルごとに 1 分あたり {rpm:g} 回")
    limited: dict[str, int] = {}
    for r in rows:
        if r["rate_limited"]:
            label = model_label(r["assistant"], r["model"])
            limited[label] = limited.get(label, 0) + int(r["rate_limited"])
    if limited:
        lines.append("- レート制限（429）で待った回数: " + ", ".join(f"{k} {v} 回" for k, v in limited.items()))
    unpriced = unpriced_targets(costs, targets)
    if unpriced:
        names = ", ".join(model_label(t.assistant, t.model) for t in unpriced)
        lines.append(
            f"- 単価: {names} は `model_costs.csv` に未登録のため、既定単価（{default_price_text(costs)}）で概算"
        )
    if command:
        lines.append(f"- 実行コマンド: `{command}`")
    return "\n".join(lines)


def run_benchmark(
    ctx: SessionContext,
    questions: list[Question],
    *,
    out_root: Path,
    trials: int = 1,
    style: str = "reason",
    talent_ids: list[str] | None = None,
    max_parallel: int = 8,
    per_provider: int = 4,
    retries: int = 2,
    retry_delay: float = 1.0,
    temperature: float | None = 0.0,
    invoker: Invoker | None = None,
    progress: Callable[[str], None] | None = None,
    questions_path: Path | None = None,
    command: str = "",
    rpm: float | None = None,
    cancel: threading.Event | None = None,
    questions_label: str | None = None,
) -> BenchmarkReport:
    if style not in SYSTEM_PROMPTS:
        raise ValueError(f"style は {', '.join(SYSTEM_PROMPTS)} のどちらかです")
    if trials < 1:
        raise ValueError("trials は 1 以上にしてください")
    targets = select_targets(ctx, talent_ids)
    costs = load_model_costs(ctx.root)
    unpriced = {t.talent_id for t in unpriced_targets(costs, targets)}
    if progress and unpriced:
        names = ", ".join(model_label(t.assistant, t.model) for t in targets if t.talent_id in unpriced)
        progress(f"⚠ 単価未登録（既定単価 {default_price_text(costs)} で概算）: {names}")
    invoker = invoker or make_invoker(ctx.root, temperature)
    system_prompt = SYSTEM_PROMPTS[style]

    out_dir = Path(out_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    gates = {name: threading.Semaphore(max(1, per_provider)) for name in {t.assistant for t in targets}}
    limiters = {(t.assistant, t.model): _RateLimiter(rpm) for t in targets}
    lock = threading.Lock()
    rows: list[dict[str, Any]] = []
    total = trials * len(questions) * len(targets)

    # 同じ問題の各モデルを隣り合わせに並べ、プロバイダーごとの同時数制限で待たされにくくする
    jobs = [(target, question, trial) for trial in range(1, trials + 1) for question in questions for target in targets]

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8-sig") as csv_file, (
        out_dir / "raw.jsonl"
    ).open("w", encoding="utf-8") as raw_file:
        writer = csv.DictWriter(csv_file, fieldnames=RESULT_COLUMNS)
        writer.writeheader()

        def work(job: tuple[Target, Question, int]) -> None:
            target, question, trial = job
            if cancel is not None and cancel.is_set():
                return
            try:
                row, text = _run_trial(
                    invoker, target, question, trial, system_prompt, retries, retry_delay, gates[target.assistant],
                    limiters[(target.assistant, target.model)], cancel,
                )
            except BenchmarkCancelled:
                return
            with lock:
                rows.append(row)
                writer.writerow(row)
                csv_file.flush()
                raw_file.write(json.dumps({**row, "text": text}, ensure_ascii=False) + "\n")
                raw_file.flush()
                if progress:
                    mark = row["correct"] if row["status"] == "ok" else "ERR"
                    progress(
                        f"[{len(rows)}/{total}] Q{question.id} #{trial} {model_label(target.assistant, target.model)}: "
                        f"{row['answer'] or '-'} ({mark})"
                    )

        with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as pool:
            for future in [pool.submit(work, job) for job in jobs]:
                future.result()

    cancelled = bool(cancel is not None and cancel.is_set() and len(rows) < total)
    summary = summarize(rows, targets, unpriced)
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(summary)
    conditions = _conditions_lines(
        ctx, questions, targets, rows, trials=trials, style=style, temperature=temperature,
        max_parallel=max_parallel, per_provider=per_provider, retries=retries, rpm=rpm,
        questions_path=questions_path, questions_label=questions_label, command=command, costs=costs,
    )
    title = f"ベンチマーク結果 {out_dir.name}"
    if cancelled:
        title += f"（中断: {len(rows)}/{total} 回で停止）"
    (out_dir / "summary.md").write_text(
        format_report_markdown(title, conditions, summary, rows, questions, targets), encoding="utf-8"
    )
    return BenchmarkReport(out_dir=out_dir, rows=rows, summary=summary, cancelled=cancelled)

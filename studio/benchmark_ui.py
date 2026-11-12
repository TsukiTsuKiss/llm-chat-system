"""Gradio ベンチマークタブ（問題セットの選択・実行・結果表示）。実行本体は studio/benchmark.py。"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from studio.benchmark import (
    default_price_text,
    load_questions,
    model_label,
    run_benchmark,
    select_targets,
    unpriced_targets,
)
from studio.loader import load_session_context
from studio.logging import load_model_costs
from studio.validation import StudioValidationError
from studio.web_ui import list_organizations

QUESTIONS_DIR = "benchmark_questions"
RESULTS_DIR = "benchmark_results"
DEFAULT_ORG = "quiz_evaluation"
MAX_LOG_LINES = 300
RESULT_FILES = ("summary.md", "results.csv", "summary.csv", "raw.jsonl")

_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"])
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])


@dataclass
class BenchmarkJob:
    running: bool = False
    cancel: threading.Event | None = None


def list_question_files(root: Path) -> list[str]:
    folder = root / QUESTIONS_DIR
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".json", ".jsonl"))


def list_result_dirs(root: Path) -> list[str]:
    folder = root / RESULTS_DIR
    if not folder.is_dir():
        return []
    return sorted((p.name for p in folder.iterdir() if (p / "summary.md").is_file()), reverse=True)


def target_choices(root: Path, org_id: str | None) -> tuple[list[tuple[str, str]], str]:
    """組織の対象モデル（人間以外のタレント）。読めないときは、空の選択肢とその理由を返す。"""
    if not org_id:
        return [], "組織を選んでください"
    try:
        targets = select_targets(load_session_context(org_id, root))
    except StudioValidationError as exc:
        return [], exc.format_all()
    except ValueError as exc:
        return [], str(exc)
    return [(f"{model_label(t.assistant, t.model)}  ←  {t.name} ({t.talent_id})", t.talent_id) for t in targets], ""


def resolve_questions(root: Path, upload: Any, selected: str | None) -> tuple[Path | None, str]:
    """アップロードを優先し、なければ benchmark_questions/ の選択を使う。戻り値は (パス, 表示名)。"""
    if upload:
        path = Path(getattr(upload, "name", upload))
        return path, path.name
    if selected and Path(selected).name == selected:
        path = root / QUESTIONS_DIR / selected
        if path.is_file():
            return path, f"{QUESTIONS_DIR}/{selected}"
    return None, ""


def price_warning(root: Path, org_id: str | None, talent_ids: list[str] | None) -> str:
    """単価表にないモデルを選んでいるときの警告（コストは既定単価での概算になる）。"""
    if not org_id or not talent_ids:
        return ""
    try:
        targets = select_targets(load_session_context(org_id, root), list(talent_ids))
    except (StudioValidationError, ValueError):
        return ""
    costs = load_model_costs(root)
    missing = unpriced_targets(costs, targets)
    if not missing:
        return ""
    names = ", ".join(model_label(t.assistant, t.model) for t in missing)
    return f"⚠️ 単価未登録（`model_costs.csv` に追加してください。コストは既定単価 {default_price_text(costs)} で概算）: {names}"


def estimate_text(
    root: Path, org_id: str | None, upload: Any, selected: str | None, talent_ids: list[str] | None, trials: Any
) -> str:
    path, label = resolve_questions(root, upload, selected)
    if path is None:
        return "問題セットを選んでください。"
    try:
        questions = load_questions(path)
    except (OSError, ValueError) as exc:
        return f"⚠️ 問題セットを読めません: {exc}"
    models = len(talent_ids or [])
    count = max(1, int(trials or 1))
    scored = sum(q.answer is not None for q in questions)
    text = (
        f"`{label}`: **{len(questions)} 問**（採点あり {scored} 問） × **{models} モデル** × **{count} 回** "
        f"= **{len(questions) * models * count} 回の API 呼び出し**（料金がかかります）"
    )
    warning = price_warning(root, org_id, talent_ids)
    return f"{text}\n\n{warning}" if warning else text


def result_files(out_dir: Path) -> list[str]:
    return [str(out_dir / name) for name in RESULT_FILES if (out_dir / name).is_file()]


def read_result(root: Path, name: str | None) -> tuple[str, list[str]]:
    if not name or Path(name).name != name:
        return "_結果を選んでください_", []
    out_dir = root / RESULTS_DIR / name
    summary = out_dir / "summary.md"
    if not summary.is_file():
        return "_summary.md がありません_", []
    return summary.read_text(encoding="utf-8"), result_files(out_dir)


def _out(*, log: str | None = None, status: str | None = None, summary: str | None = None, files: Any = None, running: bool = False):
    """(進捗, 状態, 結果表, 結果ファイル, 実行ボタン, 中断ボタン) の更新。None は変更なし。"""
    keep = gr.update()
    return (
        keep if log is None else log,
        keep if status is None else status,
        keep if summary is None else summary,
        keep if files is None else files,
        gr.update(interactive=not running),
        gr.update(interactive=running),
    )


def run_job(
    root: Path,
    job: BenchmarkJob,
    org_id: str | None,
    talent_ids: list[str] | None,
    upload: Any,
    selected: str | None,
    trials: Any,
    style: str,
    use_default_temperature: bool,
    temperature: Any,
    rpm: Any,
    per_provider: Any,
    retries: Any,
):
    if job.running:
        yield _out(status="⚠️ すでに実行中です", running=True)
        return
    path, label = resolve_questions(root, upload, selected)
    if not org_id or not talent_ids or path is None:
        yield _out(status="⚠️ 組織・対象モデル・問題セットを選んでください")
        return
    try:
        ctx = load_session_context(org_id, root)
        questions = load_questions(path)
    except StudioValidationError as exc:
        yield _out(status=f"❌ {exc.format_all()}")
        return
    except (OSError, ValueError) as exc:
        yield _out(status=f"❌ {exc}")
        return

    job.running = True
    cancel = job.cancel = threading.Event()
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            report = run_benchmark(
                ctx,
                questions,
                out_root=root / RESULTS_DIR,
                trials=max(1, int(trials or 1)),
                style=style,
                talent_ids=list(talent_ids),
                max_parallel=int(ctx.studio_config.get("max_parallel_calls", 8)),
                per_provider=max(1, int(per_provider or 1)),
                retries=max(0, int(retries or 0)),
                temperature=None if use_default_temperature else float(temperature or 0.0),
                rpm=float(rpm) if rpm else None,
                progress=lambda message: events.put(("log", message)),
                cancel=cancel,
                questions_path=path,
                questions_label=label,
            )
            events.put(("done", report))
        except Exception as exc:  # 画面に理由を出して終わる
            events.put(("error", exc))

    threading.Thread(target=worker, daemon=True).start()
    lines: list[str] = []
    try:
        yield _out(log="", status="🏃 実行を開始しました…", running=True)
        finished: tuple[str, Any] | None = None
        while finished is None:
            try:
                batch = [events.get(timeout=1.0)]
            except queue.Empty:
                continue
            while True:
                try:
                    batch.append(events.get_nowait())
                except queue.Empty:
                    break
            for kind, payload in batch:
                if kind == "log":
                    lines.append(payload)
                else:
                    finished = (kind, payload)
            lines = lines[-MAX_LOG_LINES:]
            if finished is None:
                yield _out(log="\n".join(lines), status=lines[-1], running=True)
        kind, payload = finished
        if kind == "error":
            yield _out(log="\n".join(lines), status=f"❌ {type(payload).__name__}: {payload}")
            return
        summary_text, files = read_result(root, payload.out_dir.name)
        state = "⏹ 中断しました（ここまでの結果を保存）" if payload.cancelled else "✅ 完了しました"
        yield _out(log="\n".join(lines), status=f"{state}: `{RESULTS_DIR}/{payload.out_dir.name}`", summary=summary_text, files=files)
    finally:
        # 画面が閉じられて生成器が止められたときも、実行中の呼び出しを止める
        cancel.set()
        job.running = False
        job.cancel = None


def cancel_job(job: BenchmarkJob) -> str:
    if job.running and job.cancel is not None:
        job.cancel.set()
        return "⏹ 中断しています…（実行中の呼び出しが終わるまで待ちます）"
    return "実行中ではありません"


def build_benchmark_tab(root: Path, _demo: gr.Blocks) -> None:
    orgs = list_organizations(root)
    org0 = DEFAULT_ORG if DEFAULT_ORG in orgs else (orgs[0] if orgs else None)
    choices0, error0 = target_choices(root, org0)

    with gr.Tab("🎯 ベンチマーク") as benchmark_tab:
        job_state = gr.State(BenchmarkJob())
        gr.Markdown(
            "問題セット（JSON / JSONL）を、組織の各モデルに同じ条件で流し、正解率・速度・コストを自動で集計します。"
            " 実行には **API 料金がかかります**。結果は `benchmark_results/` に保存されます。"
        )
        with gr.Row():
            with gr.Column(scale=1):
                org_dd = gr.Dropdown(label="組織", choices=orgs, value=org0)
                talents_cb = gr.CheckboxGroup(
                    label="対象モデル（プロバイダー (モデル) ← タレント）",
                    choices=choices0,
                    value=[value for _, value in choices0],
                )
                target_note = gr.Markdown(error0)
                upload = gr.File(label="問題セット（JSON / JSONL）", file_types=[".json", ".jsonl"], type="filepath")
                with gr.Row():
                    question_dd = gr.Dropdown(
                        label=f"または {QUESTIONS_DIR}/ から選ぶ（アップロードが優先）",
                        choices=list_question_files(root),
                        value=None,
                        scale=4,
                    )
                    refresh_questions_btn = gr.Button("一覧更新", **_ACTION_BTN)
                estimate_md = gr.Markdown("問題セットを選んでください。")
            with gr.Column(scale=1):
                trials = gr.Number(label="試行回数（同じ問題を何回ずつ流すか）", value=1, minimum=1, precision=0)
                style = gr.Radio(
                    label="指示", choices=[("簡潔な理由つき", "reason"), ("答えだけ", "answer")], value="reason"
                )
                with gr.Row():
                    temperature = gr.Number(label="temperature", value=0.0, minimum=0.0, scale=1)
                    use_default_temperature = gr.Checkbox(label="プロバイダー既定を使う", value=False, scale=1)
                rpm = gr.Number(label="1 分あたりの呼び出し上限（モデルごと。0 で制限なし）", value=0, minimum=0)
                per_provider = gr.Number(label="プロバイダーごとの同時実行数", value=4, minimum=1, precision=0)
                retries = gr.Number(label="失敗時の再試行回数", value=2, minimum=0, precision=0)
                with gr.Row():
                    run_btn = gr.Button("実行", **_SAVE_BTN)
                    cancel_btn = gr.Button("中断", interactive=False, **_SAVE_BTN)

        status_md = gr.Markdown("")
        log_tb = gr.Textbox(label="進捗", lines=8, max_lines=12, interactive=False)
        gr.Markdown("### 結果")
        summary_md = gr.Markdown("_まだ実行していません_")
        files_out = gr.File(label="結果ファイル", file_count="multiple", interactive=False)
        with gr.Accordion("過去の結果", open=False):
            with gr.Row():
                result_dd = gr.Dropdown(label="結果", choices=list_result_dirs(root), value=None, scale=4)
                refresh_results_btn = gr.Button("一覧更新", **_ACTION_BTN)

        def on_org_change(org_id: str | None, upload_value: Any, selected: str | None, trials_value: Any):
            choices, error = target_choices(root, org_id)
            ids = [value for _, value in choices]
            return (
                gr.update(choices=choices, value=ids),
                error,
                estimate_text(root, org_id, upload_value, selected, ids, trials_value),
            )

        def on_estimate(
            org_id: str | None, upload_value: Any, selected: str | None, ids: list[str] | None, trials_value: Any
        ) -> str:
            return estimate_text(root, org_id, upload_value, selected, ids, trials_value)

        def on_refresh_questions():
            return gr.update(choices=list_question_files(root))

        def on_refresh_results():
            return gr.update(choices=list_result_dirs(root))

        def on_show_result(name: str | None):
            summary_text, files = read_result(root, name)
            return summary_text, files

        def on_run(job: BenchmarkJob, *values: Any):
            yield from run_job(root, job, *values)

        estimate_inputs = [org_dd, upload, question_dd, talents_cb, trials]
        org_dd.change(
            on_org_change,
            inputs=[org_dd, upload, question_dd, trials],
            outputs=[talents_cb, target_note, estimate_md],
            queue=False,
        )
        for component in (upload, question_dd, talents_cb, trials):
            component.change(on_estimate, inputs=estimate_inputs, outputs=[estimate_md], queue=False)
        refresh_questions_btn.click(on_refresh_questions, outputs=[question_dd], queue=False)
        refresh_results_btn.click(on_refresh_results, outputs=[result_dd], queue=False)
        benchmark_tab.select(
            lambda: (gr.update(choices=list_question_files(root)), gr.update(choices=list_result_dirs(root))),
            outputs=[question_dd, result_dd],
            queue=False,
        )
        result_dd.change(on_show_result, inputs=[result_dd], outputs=[summary_md, files_out], queue=False)

        run_btn.click(
            on_run,
            inputs=[
                job_state, org_dd, talents_cb, upload, question_dd, trials, style,
                use_default_temperature, temperature, rpm, per_provider, retries,
            ],
            outputs=[log_tb, status_md, summary_md, files_out, run_btn, cancel_btn],
        )
        cancel_btn.click(cancel_job, inputs=[job_state], outputs=[status_md], queue=False)

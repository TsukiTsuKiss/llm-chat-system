"""Gradio VOICEVOX タブ（ENGINE の一覧・有効/無効・ベンチマーク・過去セッションの速さ集計）。"""

from __future__ import annotations

import html
import queue
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import gradio as gr

from studio.benchmark_ui import BenchmarkJob
from studio.voice import engine_available
from studio.voice_bench import Sample, fetch_info, make_meta, run_benchmark, write_results
from studio.voice_engines import EngineConfigError, engine_names_by_url, load_engines, set_enabled
from studio.voice_stats import EngineStat, collect_synth_stats

RESULTS_DIR = "benchmark_results"
RESULT_FILES = ("report.md", "samples.csv")
MAX_LOG_LINES = 300
NO_FILE_TEXT = "`voicevox_engines.json` がありません。`voicevox_engines.example.json` を参考に、プロジェクトのルートに作ってください。"

_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"])
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])

StatesGetter = Callable[[], list[tuple[str, str]]]


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def engine_choices(root: Path) -> tuple[list[str], list[str], str]:
    """(全 ENGINE 名, 有効な ENGINE 名, 読めないときの理由)。通信はしない。"""
    try:
        engines = load_engines(root)
    except EngineConfigError as exc:
        return [], [], f"❌ {exc}"
    if not engines:
        return [], [], NO_FILE_TEXT
    return [e.name for e in engines], [e.name for e in engines if e.enabled], ""


def engine_overview(root: Path, states: StatesGetter) -> str:
    """ENGINE の一覧表（有効/無効・デバイス・version・いまの状態）。各 ENGINE へ問い合わせる。"""
    try:
        engines = load_engines(root)
    except EngineConfigError as exc:
        return f"❌ {exc}"
    if not engines:
        return NO_FILE_TEXT

    busy_urls = {url.rstrip("/") for url, state in states() if state == "busy"}

    def probe(engine) -> tuple[bool, str, str]:
        if not engine_available(engine.url):
            return False, "?", "?"
        version, devices = fetch_info(engine.url)
        return True, version, devices

    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        probed = list(pool.map(probe, engines))

    lines = [
        "| 有効 | ENGINE | URL | デバイス（設定 / 実測） | version | 状態 | メモ |",
        "|---|---|---|---|---|---|---|",
    ]
    for engine, (alive, version, devices) in zip(engines, probed):
        state = "🟡 合成中" if engine.url in busy_urls else "🟢 待機" if alive else "⚪ 未検出"
        cells = [
            "✅" if engine.enabled else "—",
            engine.name,
            engine.url,
            f"{engine.device} / {devices}",
            version,
            state,
            engine.note,
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(lines)


def save_enabled(root: Path, selected: list[str] | None) -> str:
    try:
        set_enabled(root, selected or [])
    except (EngineConfigError, OSError) as exc:
        return f"❌ 保存できません: {exc}"
    return "✅ 保存しました。**次回の Studio 起動から**反映されます（起動中の読み上げには影響しません）。"


def stats_markdown(stats: list[EngineStat], read_sessions: int) -> str:
    if not stats:
        return "_合成の記録がありません（読み上げたセッションがまだありません）_"
    lines = [
        f"新しい順に {read_sessions} セッションを集計（失敗した合成は中央値に含めません）。",
        "",
        "| ENGINE | 合成数 | 失敗 | セッション数 | 中央値(秒) | 1文字(ms) |",
        "|---|---|---|---|---|---|",
    ]
    for stat in stats:
        median = "-" if stat.median_sec is None else f"{stat.median_sec:.2f}"
        per_char = "-" if stat.median_ms_per_char is None else f"{stat.median_ms_per_char:.1f}"
        lines.append(f"| {_cell(stat.name)} | {stat.calls} | {stat.failed} | {stat.sessions} | {median} | {per_char} |")
    if any(s.with_chars < s.calls for s in stats):
        lines += ["", "1 文字あたりは、文字数を記録したセッション以降のみ。古い記録は含みません。"]
    return "\n".join(lines)


def stats_text(root: Path, recent: Any) -> str:
    stats, read_sessions = collect_synth_stats(root, engine_names_by_url(root), recent_sessions=int(recent or 30))
    return stats_markdown(stats, read_sessions)


def list_voice_result_dirs(root: Path) -> list[str]:
    folder = root / RESULTS_DIR
    if not folder.is_dir():
        return []
    return sorted(
        (p.name for p in folder.iterdir() if p.name.startswith("voice_") and (p / "report.md").is_file()),
        reverse=True,
    )


def read_voice_result(root: Path, name: str | None) -> tuple[str, list[str]]:
    if not name or Path(name).name != name:
        return "_結果を選んでください_", []
    out_dir = root / RESULTS_DIR / name
    report = out_dir / "report.md"
    if not report.is_file():
        return "_report.md がありません_", []
    return report.read_text(encoding="utf-8"), [str(out_dir / f) for f in RESULT_FILES if (out_dir / f).is_file()]


def parse_levels(text: str) -> list[int]:
    levels = [int(item) for item in text.replace("、", ",").split(",") if item.strip()]
    if not levels or min(levels) < 1:
        raise ValueError("同時実行数は 1 以上の整数をカンマ区切りで指定してください")
    return levels


def _out(
    *,
    log: str | None = None,
    status: str | None = None,
    timeline: str | None = None,
    report: str | None = None,
    files: Any = None,
    running: bool = False,
):
    """(進捗, 状態, タイムライン, 結果表, 結果ファイル, 実行ボタン, 中断ボタン) の更新。None は変更なし。"""
    keep = gr.update()
    return (
        keep if log is None else log,
        keep if status is None else status,
        keep if timeline is None else timeline,
        keep if report is None else report,
        keep if files is None else files,
        gr.update(interactive=not running),
        gr.update(interactive=running),
    )


_BAR_COLORS = {"short": "#9ecae1", "medium": "#4292c6", "long": "#08519c"}
_LANE_PX = 16


def _bar_color(sample: Sample) -> str:
    if not sample.ok:
        return "#d9534f"
    if sample.phase == "first":
        return "#f0ad4e"
    if sample.mode.startswith("concurrent"):
        return "#5cb85c"
    return _BAR_COLORS.get(sample.size, "#4292c6")


def timeline_html(samples: Sequence[Sample], names: Sequence[str]) -> str:
    """ENGINE ごとの行に、合成 1 回を棒で並べる（同時実行は段を分ける）。横軸は開始からの秒。"""
    if not samples:
        return ""
    total = max(max(s.start + s.seconds for s in samples), 1.0)
    rows: list[str] = []
    for name in names:
        mine = sorted((s for s in samples if s.engine == name), key=lambda s: s.start)
        lane_ends: list[float] = []
        bars: list[str] = []
        for sample in mine:
            lane = next((i for i, end in enumerate(lane_ends) if end <= sample.start + 0.05), len(lane_ends))  # ms 丸めの誤差を許す
            if lane == len(lane_ends):
                lane_ends.append(0.0)
            lane_ends[lane] = sample.start + sample.seconds
            tip = html.escape(f"{sample.size} {sample.chars}文字 / {sample.seconds:.2f}秒 / {sample.mode}" + (f" / {sample.error}" if sample.error else ""))
            bars.append(
                f'<div title="{tip}" style="position:absolute;left:{sample.start / total * 100:.2f}%;'
                f"width:{max(sample.seconds / total * 100, 0.3):.2f}%;top:{lane * _LANE_PX}px;height:{_LANE_PX - 3}px;"
                f'background:{_bar_color(sample)};border-radius:2px"></div>'
            )
        height = max(len(lane_ends), 1) * _LANE_PX + 2
        rows.append(
            f'<div style="display:flex;align-items:flex-start;margin:3px 0">'
            f'<div style="width:130px;flex:none;font-size:12px;padding-right:8px;text-align:right">{html.escape(name)}</div>'
            f'<div style="position:relative;flex:1;height:{height}px;border-left:1px solid #8886;'
            f'border-bottom:1px solid #8883">{"".join(bars)}</div></div>'
        )
    legend = " ".join(
        f'<span style="display:inline-block;width:10px;height:10px;background:{color};border-radius:2px"></span> {label}'
        for color, label in (
            ("#f0ad4e", "初回"),
            ("#9ecae1", "短"),
            ("#4292c6", "中"),
            ("#08519c", "長"),
            ("#5cb85c", "同時実行"),
            ("#d9534f", "失敗"),
        )
    )
    axis = f'<div style="margin-left:130px;font-size:11px;display:flex;justify-content:space-between"><span>0 秒</span><span>{total / 2:.0f} 秒</span><span>{total:.0f} 秒</span></div>'
    return f'<div style="font-size:12px;margin:4px 0">{legend}</div>{"".join(rows)}{axis}'


def run_voice_bench(
    root: Path,
    job: BenchmarkJob,
    states: StatesGetter,
    selected: list[str] | None,
    trials: Any,
    levels_text: str,
    speaker: Any,
):
    if job.running:
        yield _out(status="⚠️ すでに実行中です", running=True)
        return
    if any(state == "busy" for _, state in states()):
        yield _out(status="⚠️ 読み上げ中は実行できません（ENGINE を奪い合うため、本番の速さが落ちます）。読み上げが終わってからにしてください")
        return
    try:
        engines = [e for e in load_engines(root) if e.name in (selected or [])]
        levels = parse_levels(levels_text or "")
    except (EngineConfigError, ValueError) as exc:
        yield _out(status=f"❌ {exc}")
        return
    if not engines:
        yield _out(status="⚠️ 対象の ENGINE を選んでください")
        return
    targets = [(e.name, e.url) for e in engines]
    names = [name for name, _ in targets]
    count = max(1, int(trials or 1))
    speaker_id = int(speaker if speaker is not None else 1)

    job.running = True
    cancel = job.cancel = threading.Event()
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            meta = make_meta(speaker_id, count, levels)
            results = run_benchmark(
                targets,
                speaker=speaker_id,
                trials=count,
                levels=levels,
                progress=lambda message: events.put(("log", message)),
                cancel=cancel,
                on_sample=lambda sample: events.put(("sample", sample)),
            )
            events.put(("done", write_results(root / RESULTS_DIR, results, meta)))
        except Exception as exc:  # 画面に理由を出して終わる
            events.put(("error", exc))

    threading.Thread(target=worker, daemon=True).start()
    lines: list[str] = []
    samples: list[Sample] = []
    try:
        yield _out(log="", status="🏃 実行を開始しました…", timeline="", running=True)
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
                elif kind == "sample":
                    samples.append(payload)
                else:
                    finished = (kind, payload)
            lines = lines[-MAX_LOG_LINES:]
            if finished is None:
                yield _out(
                    log="\n".join(lines),
                    status=lines[-1] if lines else None,
                    timeline=timeline_html(samples, names),
                    running=True,
                )
        kind, payload = finished
        if kind == "error":
            yield _out(log="\n".join(lines), status=f"❌ {type(payload).__name__}: {payload}")
            return
        report, files = read_voice_result(root, payload.name)
        state = "⏹ 中断しました（ここまでの結果を保存）" if cancel.is_set() else "✅ 完了しました"
        yield _out(
            log="\n".join(lines),
            status=f"{state}: `{RESULTS_DIR}/{payload.name}`",
            timeline=timeline_html(samples, names),
            report=report,
            files=files,
        )
    finally:
        # 画面が閉じられて生成器が止められたときも、実行中の呼び出しを止める
        cancel.set()
        job.running = False
        job.cancel = None


def cancel_voice_bench(job: BenchmarkJob) -> str:
    if job.running and job.cancel is not None:
        job.cancel.set()
        return "⏹ 中断しています…（実行中の合成が終わるまで待ちます）"
    return "実行中ではありません"


def build_voice_tab(root: Path, states: StatesGetter, _demo: gr.Blocks) -> None:
    names0, enabled0, note0 = engine_choices(root)

    with gr.Tab("🔊 VOICEVOX") as voice_tab:
        job_state = gr.State(BenchmarkJob())

        gr.Markdown(
            "VOICEVOX の ENGINE（音声を作るサーバー）を管理し、速さを測るタブです。"
            " ENGINE は、PC によって合成の速さが数倍違います。いまは空いた ENGINE に文を順に渡していますが、"
            "将来は、ENGINE ごとの速さ（固定の遅れと 1 文字あたりの時間）をもとに、長い文を速い ENGINE へ割り振る最適化をしたいと考えています。"
            " そのための測定データを、ここで集めます。"
        )

        gr.Markdown("### ENGINE")
        gr.Markdown(
            "`voicevox_engines.json` の ENGINE の一覧です。このタブを開くたびに、各 ENGINE へ問い合わせて状態を更新します。"
        )
        overview_md = gr.Markdown(note0 or "_このタブを開くと表示します_")
        enabled_cb = gr.CheckboxGroup(
            label="有効にする ENGINE（保存すると `voicevox_engines.json` を書き換えます）", choices=names0, value=enabled0
        )
        with gr.Row():
            save_btn = gr.Button("有効/無効を保存", **_SAVE_BTN)
            refresh_btn = gr.Button("状態を更新", **_ACTION_BTN)
        save_md = gr.Markdown("")

        gr.Markdown("### ベンチマーク（ENGINE の速さの測定）")
        gr.Markdown(
            "短・中・長の文を各 ENGINE に合成させて、速さを測ります（初回と 2 回目以降・同時実行を含む）。"
            " 読み上げ中は実行できません。結果は `benchmark_results/voice_<日時>/` に保存されます。"
        )
        targets_cb = gr.CheckboxGroup(label="対象 ENGINE", choices=names0, value=enabled0)
        with gr.Row():
            trials = gr.Number(label="各文を何回ずつ流すか", value=3, minimum=1, precision=0)
            levels = gr.Textbox(label="同時実行数（カンマ区切り）", value="1,2,3")
            speaker = gr.Number(label="話者（スタイル）ID", value=1, minimum=0, precision=0)
        with gr.Row():
            run_btn = gr.Button("実行", **_SAVE_BTN)
            cancel_btn = gr.Button("中断", interactive=False, **_SAVE_BTN)
        status_md = gr.Markdown("")
        timeline_out = gr.HTML("")
        log_tb = gr.Textbox(label="進捗", lines=6, max_lines=12, interactive=False)
        report_md = gr.Markdown("_まだ実行していません_")
        files_out = gr.File(label="結果ファイル", file_count="multiple", interactive=False)
        with gr.Accordion("過去の結果", open=False):
            with gr.Row():
                result_dd = gr.Dropdown(label="結果", choices=list_voice_result_dirs(root), value=None, scale=4)
                refresh_results_btn = gr.Button("一覧更新", **_ACTION_BTN)

        gr.Markdown("### 過去セッションの速さ")
        gr.Markdown("読み上げたセッションの記録（`sessions/audio/*/timeline.jsonl`）から、ENGINE ごとの合成の速さを集計します。")
        with gr.Row():
            recent = gr.Number(label="集計するセッション数（新しい順）", value=30, minimum=1, precision=0, scale=3)
            refresh_stats_btn = gr.Button("集計を更新", **_ACTION_BTN)
        stats_md = gr.Markdown("_このタブを開くと表示します_")

        def on_refresh():
            names, enabled, note = engine_choices(root)
            return (
                note or engine_overview(root, states),
                gr.update(choices=names, value=enabled),
                gr.update(choices=names, value=enabled),
            )

        def on_save(selected: list[str] | None):
            message = save_enabled(root, selected)
            return message, on_refresh()[0]

        def on_open(recent_value: Any):
            overview, enabled_update, targets_update = on_refresh()
            return (
                overview,
                enabled_update,
                targets_update,
                gr.update(choices=list_voice_result_dirs(root)),
                stats_text(root, recent_value),
            )

        def on_run(job: BenchmarkJob, *values: Any):
            yield from run_voice_bench(root, job, states, *values)

        voice_tab.select(
            on_open,
            inputs=[recent],
            outputs=[overview_md, enabled_cb, targets_cb, result_dd, stats_md],
        )
        refresh_btn.click(on_refresh, outputs=[overview_md, enabled_cb, targets_cb])
        save_btn.click(on_save, inputs=[enabled_cb], outputs=[save_md, overview_md])
        refresh_stats_btn.click(lambda value: stats_text(root, value), inputs=[recent], outputs=[stats_md])
        refresh_results_btn.click(
            lambda: gr.update(choices=list_voice_result_dirs(root)), outputs=[result_dd], queue=False
        )
        result_dd.change(
            lambda name: read_voice_result(root, name), inputs=[result_dd], outputs=[report_md, files_out], queue=False
        )
        run_btn.click(
            on_run,
            inputs=[job_state, targets_cb, trials, levels, speaker],
            outputs=[log_tb, status_md, timeline_out, report_md, files_out, run_btn, cancel_btn],
        )
        cancel_btn.click(cancel_voice_bench, inputs=[job_state], outputs=[status_md], queue=False)

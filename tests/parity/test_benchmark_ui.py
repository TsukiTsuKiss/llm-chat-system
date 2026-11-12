"""ベンチマークタブ（studio/benchmark_ui.py）のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import gradio as gr

from studio import benchmark_ui


def _write_questions(root: Path, name: str = "q.json") -> Path:
    folder = root / benchmark_ui.QUESTIONS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(
        json.dumps([
            {"question": "Q1", "choices": {"A": "a", "B": "b"}, "answer": "A"},
            {"question": "Q2", "choices": {"A": "a", "B": "b"}, "answer": "B"},
        ]),
        encoding="utf-8",
    )
    return path


def test_target_choices_lists_non_human_talents(studio_root: Path):
    choices, error = benchmark_ui.target_choices(studio_root, "solo")
    assert error == "" and [value for _, value in choices] == ["solo_bot"]
    assert "←" in choices[0][0]

    assert benchmark_ui.target_choices(studio_root, None)[0] == []
    assert benchmark_ui.target_choices(studio_root, "nothing")[1] != ""


def test_question_and_result_listing_and_resolution(studio_root: Path):
    assert benchmark_ui.list_question_files(studio_root) == []
    _write_questions(studio_root, "b.json")
    _write_questions(studio_root, "a.jsonl")
    (studio_root / benchmark_ui.QUESTIONS_DIR / "note.txt").write_text("x", encoding="utf-8")
    assert benchmark_ui.list_question_files(studio_root) == ["a.jsonl", "b.json"]

    path, label = benchmark_ui.resolve_questions(studio_root, None, "b.json")
    assert path is not None and path.is_file() and label == "benchmark_questions/b.json"
    assert benchmark_ui.resolve_questions(studio_root, None, "../evil.json") == (None, "")
    uploaded = studio_root / "up.json"
    uploaded.write_text("[]", encoding="utf-8")
    assert benchmark_ui.resolve_questions(studio_root, str(uploaded), "b.json") == (uploaded, "up.json")

    assert benchmark_ui.list_result_dirs(studio_root) == []
    assert benchmark_ui.read_result(studio_root, "../x")[1] == []


def test_estimate_text_counts_calls(studio_root: Path):
    _write_questions(studio_root)
    text = benchmark_ui.estimate_text(studio_root, "solo", None, "q.json", ["a", "b", "c"], 2)
    assert "2 問" in text and "3 モデル" in text and "12 回の API 呼び出し" in text
    assert "選んでください" in benchmark_ui.estimate_text(studio_root, "solo", None, None, ["a"], 1)

    bad = studio_root / benchmark_ui.QUESTIONS_DIR / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert "読めません" in benchmark_ui.estimate_text(studio_root, "solo", None, "bad.json", ["a"], 1)


def test_price_warning_lists_models_missing_from_cost_table(studio_root: Path):
    mapping = studio_root / "organizations" / "solo" / "model_mapping.json"
    mapping.write_text(json.dumps({"solo_bot": {"assistant": "ChatGPT", "model": "no-such-model"}}), encoding="utf-8")
    warning = benchmark_ui.price_warning(studio_root, "solo", ["solo_bot"])
    assert "単価未登録" in warning and "ChatGPT (no-such-model)" in warning

    (studio_root / "model_costs.csv").write_text(
        "date_updated,provider,model,input_cost_per_1k_tokens,output_cost_per_1k_tokens,currency,notes\n"
        "2026-01-01,OpenAI,no-such-model,0.001,0.002,USD,\n",
        encoding="utf-8",
    )
    assert benchmark_ui.price_warning(studio_root, "solo", ["solo_bot"]) == ""
    assert benchmark_ui.price_warning(studio_root, None, ["solo_bot"]) == ""


def test_run_job_streams_progress_and_returns_result_files(studio_root: Path):
    _write_questions(studio_root)
    job = benchmark_ui.BenchmarkJob()
    outputs = list(
        benchmark_ui.run_job(
            studio_root, job, "solo", ["solo_bot"], None, "q.json", 2, "reason", False, 0.0, 0, 1, 0
        )
    )
    log, status, summary, files, run_update, cancel_update = outputs[-1]
    assert "完了" in status and "ベンチマーク結果" in summary
    assert [Path(f).name for f in files] == list(benchmark_ui.RESULT_FILES)
    assert "[4/4]" in log
    assert run_update["interactive"] is True and cancel_update["interactive"] is False
    assert outputs[0][4]["interactive"] is False  # 実行中は実行ボタンを止める
    assert job.running is False and job.cancel is None

    (name,) = benchmark_ui.list_result_dirs(studio_root)
    shown, shown_files = benchmark_ui.read_result(studio_root, name)
    assert "ベンチマーク結果" in shown and len(shown_files) == 4


def test_run_job_rejects_missing_inputs_and_double_start(studio_root: Path):
    job = benchmark_ui.BenchmarkJob()
    (only,) = list(benchmark_ui.run_job(studio_root, job, "solo", [], None, None, 1, "reason", False, 0.0, 0, 1, 0))
    assert "選んでください" in only[1]

    job.running = True
    (only,) = list(
        benchmark_ui.run_job(studio_root, job, "solo", ["solo_bot"], None, "q.json", 1, "reason", False, 0.0, 0, 1, 0)
    )
    assert "すでに実行中" in only[1]


def test_cancel_job_sets_event_only_while_running():
    import threading

    job = benchmark_ui.BenchmarkJob()
    assert "実行中ではありません" in benchmark_ui.cancel_job(job)
    job.running, job.cancel = True, threading.Event()
    assert "中断しています" in benchmark_ui.cancel_job(job) and job.cancel.is_set()


def test_build_benchmark_tab_wires_into_blocks(studio_root: Path):
    with gr.Blocks() as demo:
        with gr.Tabs():
            benchmark_ui.build_benchmark_tab(studio_root, demo)

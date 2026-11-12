"""ベンチマーク（studio/benchmark.py）のテスト。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from studio import benchmark
from studio.assistants import InvokeResult
from studio.loader import SessionContext

REPO_ROOT = Path(__file__).resolve().parents[2]


def _ctx(tmp_path: Path, mapping: dict | None = None) -> SessionContext:
    ids = ["fast", "slow", "human"]
    return SessionContext(
        root=tmp_path,
        org_id="demo",
        org={"talent_ids": ids},
        talents={"fast": {"name": "ファスト"}, "slow": {"name": "スロー"}, "human": {"name": "人"}},
        model_mapping=mapping
        or {"fast": {"assistant": "mock", "model": "m1"}, "slow": {"assistant": "mock", "model": "m2"}, "human": {"assistant": "human"}},
        assistants={},
        studio_config={},
    )


def _result(text: str, elapsed: float, cost: float = 0.001) -> InvokeResult:
    return InvokeResult(text=text, elapsed=elapsed, tokens_in=10, tokens_out=5, tokens_source="estimate", cost=cost, stream=False)


def test_load_questions_validates_and_normalizes(tmp_path: Path):
    path = tmp_path / "q.json"
    path.write_text(
        json.dumps({"questions": [{"question": "Q", "choices": {"ａ": "x", "b": "y"}, "answer": "B"}]}), encoding="utf-8"
    )
    (question,) = benchmark.load_questions(path)
    assert question.id == "1" and list(question.choices) == ["A", "B"] and question.answer == "B"

    path.write_text(json.dumps([{"question": "Q", "choices": {"A": "x"}, "answer": "Z"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="choices にありません"):
        benchmark.load_questions(path)

    path.write_text(json.dumps([{"question": "Q", "id": "1"}, {"question": "R", "id": "1"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="重複"):
        benchmark.load_questions(path)


def test_load_questions_reads_jsonl_and_sample(tmp_path: Path):
    path = tmp_path / "q.jsonl"
    path.write_text('{"question": "A?", "answer": "x"}\n\n{"question": "B?"}\n', encoding="utf-8")
    assert [(q.id, q.answer) for q in benchmark.load_questions(path)] == [("1", "x"), ("2", None)]

    questions = benchmark.load_questions(REPO_ROOT / "samples" / "benchmark" / "questions.example.json")
    assert [q.id for q in questions] == ["1", "2", "3"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("理由です。\n答え: B", "B"),
        ("答え：ｂ）東京", "B"),
        ("答え: **C**", "C"),
        ("答え: A\n（補足）\n答え: D", "D"),
        ("B", "B"),
        ("答え: Z", ""),
        ("よく分かりません", ""),
    ],
)
def test_extract_answer_with_choices(text: str, expected: str):
    assert benchmark.extract_answer(text, {"A": "", "B": "", "C": "", "D": ""}) == expected


def test_extract_answer_free_form_and_scoring():
    assert benchmark.extract_answer("答え: H２O。", {}) == "H2O"
    assert benchmark.is_correct("H2O", "h2o") == 1
    assert benchmark.is_correct("", "A") == 0
    assert benchmark.is_correct("A", None) == ""


def test_percentile_interpolates():
    assert benchmark.percentile([1.0], 95) == 1.0
    assert benchmark.percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0
    assert benchmark.percentile([1.0, 3.0], 95) == pytest.approx(2.9)


def test_run_benchmark_scores_retries_and_ranks(tmp_path: Path):
    questions = [
        benchmark.Question("1", "Q1", {"A": "a", "B": "b"}, "A"),
        benchmark.Question("2", "Q2", {"A": "a", "B": "b"}, "B"),
    ]
    flaky = {"count": 0}

    def invoker(target, system_prompt, user_message):
        assert "答え: ○" in system_prompt and user_message.startswith("Q")
        if target.talent_id == "fast":
            # 1 問目は 1 回失敗してから成功し、2 問目は誤答する
            if user_message.startswith("Q1"):
                flaky["count"] += 1
                if flaky["count"] == 1:
                    raise ConnectionError("boom")
                return _result("答え: A", 0.5)
            return _result("答え: A", 0.5)
        return _result("答え: A" if user_message.startswith("Q1") else "答え: B", 2.0)

    messages: list[str] = []
    report = benchmark.run_benchmark(
        _ctx(tmp_path), questions, out_root=tmp_path / "out", trials=2, retry_delay=0, invoker=invoker, progress=messages.append
    )

    assert len(report.rows) == 2 * 2 * 2 and len(messages) == 8
    assert [e["talent_id"] for e in report.summary] == ["slow", "fast"]  # human は対象外、正解率優先
    slow, fast = report.summary
    assert slow["accuracy"] == 1.0 and slow["median_sec"] == 2.0 and slow["rank"] == 1
    assert fast["correct"] == 2 and fast["scored"] == 4 and fast["errors"] == 0
    assert any(r["attempts"] == 2 for r in report.rows)
    assert benchmark.miss_lines(report.rows) == ["Q2: mock (m1)×2"]

    with (report.out_dir / "results.csv").open(encoding="utf-8-sig", newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 8
    raw = [json.loads(line) for line in (report.out_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("text" in r for r in raw)
    assert (report.out_dir / "summary.csv").is_file()
    markdown = (report.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "- 問題セット: 2 問" in markdown and "- 組織: demo / 対象: 2 モデル（下の対応表）" in markdown
    assert "| ファスト (fast) | mock | m1 |" in markdown and "| スロー (slow) | mock | m2 |" in markdown
    assert "- 試行: 2 回 / 指示: reason / temperature: 0.0" in markdown
    assert "| Q1 | 2/2 | 2/2 |" in markdown and "| Q2 | 0/2 | 2/2 |" in markdown
    assert "- Q2: mock (m1)×2" in markdown
    assert "| 1 | mock (m2) | 100.0% |" in benchmark.format_summary_table(report.summary)


def test_report_lists_questions_and_conditions_and_temperature_fallback(tmp_path: Path):
    questions_file = tmp_path / "q.json"
    questions_file.write_text(
        json.dumps([{"id": "7", "question": "水の化学式は|どれ", "choices": {"A": "H2O"}, "answer": "A", "source": "例題"}]),
        encoding="utf-8",
    )
    ctx = _ctx(tmp_path, {
        "fast": {"assistant": "A", "model": "m1"}, "slow": {"assistant": "B", "model": "m2"}, "human": {"assistant": "human"},
    })

    def invoker(target, system_prompt, user_message):
        result = _result("答え: A", 1.0)
        result.temperature = 0.3 if target.talent_id == "fast" else None
        return result

    report = benchmark.run_benchmark(
        ctx, benchmark.load_questions(questions_file), out_root=tmp_path / "out", temperature=0.3, invoker=invoker,
        questions_path=questions_file, command="python MultiRoleStudio.py --benchmark q.json",
    )
    markdown = (report.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "`" + questions_file.as_posix() + "`（1 問、sha256 先頭" in markdown
    assert "temperature: 0.3（指定値を受け付けず既定値で実行: B (m2)）" in markdown
    assert "- 実行コマンド: `python MultiRoleStudio.py --benchmark q.json`" in markdown
    assert "| Q7 | 例題 | 水の化学式は｜どれ | A |" in markdown
    assert {r["talent_id"]: r["temperature"] for r in report.rows} == {"fast": 0.3, "slow": ""}


def test_retry_after_parses_server_hints():
    assert benchmark._retry_after("429 ... Please retry in 49.871200504s. [links") == pytest.approx(49.87, abs=0.01)
    assert benchmark._retry_after("retry_delay {\n  seconds: 35\n}") == 35
    assert benchmark._retry_after("Please try again in 20ms.") == pytest.approx(0.02)
    assert benchmark._retry_after("boom") is None


def test_rate_limited_calls_wait_for_server_hint_and_are_reported(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(benchmark, "RATE_WAIT_MARGIN", 0.0)
    calls = {"n": 0}

    def invoker(target, system_prompt, user_message):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 You exceeded your current quota. Please retry in 0.01s.")
        return _result("答え: A", 1.0)

    report = benchmark.run_benchmark(
        _ctx(tmp_path), [benchmark.Question("1", "Q", {"A": "a"}, "A")], out_root=tmp_path / "out",
        talent_ids=["fast"], invoker=invoker, rpm=600,
    )
    (row,) = report.rows
    assert row["status"] == "ok" and row["rate_limited"] == 1 and row["attempts"] == 1 and row["elapsed"] == 1.0
    markdown = (report.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "レート制限（429）で待った回数: mock (m1) 1 回" in markdown
    assert "呼び出し頻度の上限: モデルごとに 1 分あたり 600 回" in markdown
    assert report.summary[0]["rate_limited"] == 1


def test_rate_limiter_spaces_calls_per_model():
    import time

    limiter = benchmark._RateLimiter(600)  # 0.1 秒間隔
    began = time.monotonic()
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - began >= 0.18


def test_run_benchmark_cancel_stops_remaining_trials(tmp_path: Path):
    import threading

    cancel = threading.Event()
    questions = [benchmark.Question(str(i), f"Q{i}", {"A": "a"}, "A") for i in range(1, 6)]

    def invoker(target, system_prompt, user_message):
        cancel.set()  # 最初の呼び出しの直後に中断を要求する
        return _result("答え: A", 0.1)

    report = benchmark.run_benchmark(
        _ctx(tmp_path), questions, out_root=tmp_path / "out", talent_ids=["fast"], max_parallel=1,
        invoker=invoker, cancel=cancel,
    )
    assert report.cancelled is True and 1 <= len(report.rows) < 5
    markdown = (report.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "中断:" in markdown.splitlines()[0]


def test_unpriced_models_are_flagged_in_report_and_progress(tmp_path: Path):
    ctx = _ctx(tmp_path, {
        "fast": {"assistant": "A", "model": "known"}, "slow": {"assistant": "B", "model": "unknown"},
        "human": {"assistant": "human"},
    })
    (tmp_path / "model_costs.csv").write_text(
        "date_updated,provider,model,input_cost_per_1k_tokens,output_cost_per_1k_tokens,currency,notes\n"
        "2026-01-01,A,known,0.001,0.002,USD,\n",
        encoding="utf-8",
    )
    messages: list[str] = []
    report = benchmark.run_benchmark(
        ctx, [benchmark.Question("1", "Q", {"A": "a"}, "A")], out_root=tmp_path / "out",
        invoker=lambda target, system, user: _result("答え: A", 1.0), progress=messages.append,
    )
    assert messages[0].startswith("⚠ 単価未登録") and "B (unknown)" in messages[0] and "A (known)" not in messages[0]
    assert {e["talent_id"]: e["price_known"] for e in report.summary} == {"fast": True, "slow": False}
    markdown = (report.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "| $0.0010 |" in markdown and "| $0.0010* |" in markdown
    assert "\\* 単価が未登録" in markdown
    assert "- 単価: B (unknown) は `model_costs.csv` に未登録" in markdown and "入力 $1 / 出力 $3" in markdown


def test_run_benchmark_records_errors_without_failing(tmp_path: Path):
    def invoker(target, system_prompt, user_message):
        raise TimeoutError("slow")

    report = benchmark.run_benchmark(
        _ctx(tmp_path), [benchmark.Question("1", "Q", {"A": "a"}, "A")], out_root=tmp_path / "out", retries=1,
        retry_delay=0, invoker=invoker,
    )
    assert all(r["status"] == "error" and r["attempts"] == 2 and "TimeoutError" in r["error"] for r in report.rows)
    assert all(e["errors"] == 1 and e["accuracy"] == "" for e in report.summary)


def test_select_targets_filters_and_rejects_unknown(tmp_path: Path):
    ctx = _ctx(tmp_path)
    assert [t.talent_id for t in benchmark.select_targets(ctx, ["slow"])] == ["slow"]
    with pytest.raises(ValueError, match="対象外"):
        benchmark.select_targets(ctx, ["human"])

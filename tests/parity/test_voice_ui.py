"""VOICEVOX タブの部品（ENGINE 一覧・有効/無効の保存・過去セッションの集計・ベンチマーク実行）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio import voice_bench, voice_ui
from studio.benchmark_ui import BenchmarkJob
from studio.voice_engines import ENGINES_FILE, EngineConfigError, load_engines, set_enabled
from studio.voice_stats import collect_synth_stats
from tests.parity.test_voice_bench import make_wav


def write_engines(root: Path, engines: list[dict]) -> None:
    (root / ENGINES_FILE).write_text(json.dumps({"engines": engines}, ensure_ascii=False), encoding="utf-8")


def write_timeline(root: Path, session: str, records: list[dict]) -> None:
    folder = root / "sessions" / "audio" / session
    folder.mkdir(parents=True)
    (folder / "timeline.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def synth(engine: str, t: float, end: float, **extra) -> dict:
    return {"kind": "synth", "engine": engine, "t": t, "end": end, "file": "01_a.wav", **extra}


def test_set_enabled_rewrites_only_enabled_flags(tmp_path):
    write_engines(
        tmp_path,
        [
            {"name": "a", "url": "http://a:1", "note": "メモ", "parallel": 2},
            {"name": "b", "url": "http://b:1", "enabled": False},
        ],
    )
    set_enabled(tmp_path, ["B"])
    a, b = load_engines(tmp_path)
    assert (a.enabled, b.enabled) == (False, True)
    assert (a.note, a.parallel) == ("メモ", 2)
    assert "メモ" in (tmp_path / ENGINES_FILE).read_text(encoding="utf-8")
    assert not (tmp_path / (ENGINES_FILE + ".tmp")).exists()


def test_set_enabled_requires_existing_file(tmp_path):
    with pytest.raises(EngineConfigError):
        set_enabled(tmp_path, [])


def test_engine_choices(tmp_path):
    assert voice_ui.engine_choices(tmp_path)[2] == voice_ui.NO_FILE_TEXT
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}, {"name": "b", "url": "http://b:1", "enabled": False}])
    assert voice_ui.engine_choices(tmp_path) == (["a", "b"], ["a"], "")
    (tmp_path / ENGINES_FILE).write_text("{", encoding="utf-8")
    assert voice_ui.engine_choices(tmp_path)[2].startswith("❌")


def test_engine_overview_shows_state_device_and_escapes_pipes(tmp_path, monkeypatch):
    write_engines(
        tmp_path,
        [
            {"name": "a", "url": "http://a:1", "device": "gpu", "note": "x|y"},
            {"name": "b", "url": "http://b:1", "enabled": False},
            {"name": "c", "url": "http://c:1"},
        ],
    )
    monkeypatch.setattr(voice_ui, "engine_available", lambda url: url != "http://c:1")
    monkeypatch.setattr(voice_ui, "fetch_info", lambda url: ("0.26.0", "cpu"))
    text = voice_ui.engine_overview(tmp_path, lambda: [("http://a:1", "busy"), ("http://b:1", "idle")])
    rows = {line.split("|")[2].strip(): line for line in text.splitlines()[2:]}
    assert "合成中" in rows["a"] and "gpu / cpu" in rows["a"] and "x\\|y" in rows["a"]
    assert "待機" in rows["b"] and "—" in rows["b"]
    assert "未検出" in rows["c"] and "cpu / ?" in rows["c"]


def test_save_enabled_messages(tmp_path):
    assert voice_ui.save_enabled(tmp_path, ["a"]).startswith("❌")
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}])
    assert voice_ui.save_enabled(tmp_path, []).startswith("✅")
    assert load_engines(tmp_path)[0].enabled is False


def test_collect_synth_stats_groups_by_name_and_url(tmp_path):
    names = {"http://old:1": "old-pc"}
    write_timeline(
        tmp_path,
        "20261101_000000",
        [synth("http://old:1", 0, 2.0), synth("http://x:1", 0, 1.0, chars=10, engine_name="new-pc")],
    )
    write_timeline(
        tmp_path,
        "20261102_000000",
        [
            synth("http://x:1", 0, 3.0, chars=10, engine_name="new-pc"),
            synth("http://x:1", 0, 9.0, chars=10, engine_name="new-pc", failed=True),
            synth("http://other:1", 0, 5.0),
            {"kind": "play_start", "t": 1},
        ],
    )
    stats, read = collect_synth_stats(tmp_path, names)
    by_name = {s.name: s for s in stats}
    assert read == 2
    assert by_name["new-pc"].calls == 2 and by_name["new-pc"].failed == 1 and by_name["new-pc"].sessions == 2
    assert by_name["new-pc"].median_sec == pytest.approx(2.0)
    assert by_name["new-pc"].median_ms_per_char == pytest.approx(200.0)
    assert by_name["old-pc"].median_ms_per_char is None and by_name["old-pc"].with_chars == 0
    assert "http://other:1" in by_name
    assert stats[0].name == "new-pc"  # 1 文字あたりが分かるものが先


def test_collect_synth_stats_limits_to_recent_sessions(tmp_path):
    write_timeline(tmp_path, "20261101_000000", [synth("http://old:1", 0, 1.0)])
    write_timeline(tmp_path, "20261102_000000", [synth("http://new:1", 0, 1.0)])
    stats, read = collect_synth_stats(tmp_path, recent_sessions=1)
    assert read == 1 and [s.name for s in stats] == ["http://new:1"]


def test_collect_synth_stats_without_sessions(tmp_path):
    assert collect_synth_stats(tmp_path) == ([], 0)
    assert "記録がありません" in voice_ui.stats_markdown([], 0)


def test_parse_levels():
    assert voice_ui.parse_levels("1, 2、3") == [1, 2, 3]
    for bad in ("", "0", "a"):
        with pytest.raises(ValueError):
            voice_ui.parse_levels(bad)


def _statuses(outputs) -> list[str]:
    return [o[1] for o in outputs if isinstance(o[1], str)]


def test_run_voice_bench_refuses_while_reading(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}])
    job = BenchmarkJob()
    outputs = list(voice_ui.run_voice_bench(tmp_path, job, lambda: [("http://a:1", "busy")], ["a"], 1, "1", 1))
    assert "読み上げ中" in _statuses(outputs)[0] and not job.running


def test_run_voice_bench_runs_and_saves(tmp_path, monkeypatch):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}, {"name": "b", "url": "http://b:1"}])
    monkeypatch.setattr(voice_bench, "fetch_info", lambda url: ("0.26.0", "cpu"))
    monkeypatch.setattr(voice_bench, "synthesize", lambda text, entry, url: make_wav())
    job = BenchmarkJob()
    outputs = list(voice_ui.run_voice_bench(tmp_path, job, lambda: [("http://a:1", "idle")], ["a"], 1, "1,2", 1))

    assert "完了しました" in _statuses(outputs)[-1] and not job.running
    (result_dir,) = [p for p in (tmp_path / "benchmark_results").iterdir() if p.name.startswith("voice_")]
    report = (result_dir / "report.md").read_text(encoding="utf-8")
    assert "| a |" in report and "| b |" not in report
    assert voice_ui.list_voice_result_dirs(tmp_path) == [result_dir.name]
    text, files = voice_ui.read_voice_result(tmp_path, result_dir.name)
    assert text == report and len(files) == 2
    assert voice_ui.read_voice_result(tmp_path, "../x")[0].startswith("_結果を選んで")


def test_run_voice_bench_validates_input(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}])
    idle = lambda: []
    assert "選んでください" in _statuses(list(voice_ui.run_voice_bench(tmp_path, BenchmarkJob(), idle, [], 1, "1", 1)))[0]
    assert "1 以上" in _statuses(list(voice_ui.run_voice_bench(tmp_path, BenchmarkJob(), idle, ["a"], 1, "0", 1)))[0]


def test_measure_engine_stops_when_cancelled(monkeypatch):
    import threading

    monkeypatch.setattr(voice_bench, "fetch_info", lambda url: ("v", "cpu"))
    cancel = threading.Event()

    def fake_synth(text, entry, url):
        cancel.set()  # 初回の合成が終わった時点で中断する
        return make_wav()

    monkeypatch.setattr(voice_bench, "synthesize", fake_synth)
    result = voice_bench.measure_engine("pc", "http://pc", {"speaker": 1}, trials=3, levels=[1, 2], cancel=cancel)
    assert len(result.samples) == 1


def test_stats_merge_former_url_into_current_name(tmp_path):
    write_engines(tmp_path, [{"name": "nuc", "url": "http://10.0.0.2:1", "former_urls": ["http://10.0.0.1:1"]}])
    write_timeline(tmp_path, "20261101_000000", [synth("http://10.0.0.1:1", 0, 2.0)])
    write_timeline(tmp_path, "20261102_000000", [synth("http://10.0.0.2:1", 0, 4.0, chars=10, engine_name="nuc")])
    text = voice_ui.stats_text(tmp_path, 30)
    assert "| nuc | 2 |" in text and "10.0.0.1" not in text


def test_measure_engine_records_start_offsets_and_notifies(monkeypatch):
    monkeypatch.setattr(voice_bench, "fetch_info", lambda url: ("v", "cpu"))
    monkeypatch.setattr(voice_bench, "synthesize", lambda text, entry, url: make_wav())
    seen: list = []
    result = voice_bench.measure_engine(
        "pc", "http://pc", {"speaker": 1}, trials=1, levels=[1, 2], on_sample=seen.append
    )
    assert seen == result.samples
    starts = [s.start for s in result.samples if s.mode == "sequential"]
    assert starts == sorted(starts) and all(s >= 0 for s in starts)


def test_timeline_html_places_bars_by_engine_and_splits_lanes():
    def sample(engine, start, seconds, **kw):
        base = dict(mode="sequential", phase="warm", size="medium", chars=49, trial=1, audio_sec=1.0, ok=True)
        return voice_bench.Sample(engine=engine, url="u", seconds=seconds, start=start, **{**base, **kw})

    assert voice_ui.timeline_html([], ["a"]) == ""
    samples = [
        sample("a", 0.0, 2.0, phase="first"),
        sample("a", 2.0, 2.0),
        sample("a", 4.0, 1.0, mode="concurrent-2"),
        sample("a", 4.5, 1.0, mode="concurrent-2"),
        sample("<b>", 0.0, 5.0, ok=False),
    ]
    page = voice_ui.timeline_html(samples, ["a", "<b>"])
    assert page.count("<div title=") == 5
    assert "&lt;b&gt;" in page and "<b>" not in page.replace("&lt;b&gt;", "")
    assert "#f0ad4e" in page and "#5cb85c" in page and "#d9534f" in page
    assert "top:16px" in page  # 重なる同時実行は 2 段目
    assert "left:72.73%" in page  # 4.0 秒 / 全体 5.5 秒

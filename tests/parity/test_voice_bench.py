"""VOICEVOX ENGINE ベンチマーク（合成と通信はモックで置き換える）。"""

from __future__ import annotations

import csv
import io
import json
import wave
from pathlib import Path

import pytest

from studio import voice_bench
from studio.voice_bench import (
    SENTENCES,
    build_markdown,
    fit_line,
    make_meta,
    measure_engine,
    resolve_targets,
    run_benchmark,
    write_results,
)
from studio.voice_engines import ENGINES_FILE


def make_wav(frames: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fake_info(monkeypatch):
    monkeypatch.setattr(voice_bench, "fetch_info", lambda url: ("0.26.0", "cpu"))


def test_resolve_targets_defaults_to_enabled_engines_with_names(tmp_path):
    (tmp_path / ENGINES_FILE).write_text(
        json.dumps(
            {
                "engines": [
                    {"name": "a", "url": "http://127.0.0.1:1"},
                    {"name": "b", "url": "http://127.0.0.1:2", "enabled": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert resolve_targets(None, tmp_path) == [("a", "http://127.0.0.1:1")]
    assert resolve_targets("b, http://127.0.0.1:9", tmp_path) == [
        ("b", "http://127.0.0.1:2"),
        ("http://127.0.0.1:9", "http://127.0.0.1:9"),
    ]


def test_resolve_targets_without_file_uses_default_url(tmp_path):
    assert resolve_targets(None, tmp_path) == [(voice_bench.DEFAULT_BASE_URL, voice_bench.DEFAULT_BASE_URL)]


def test_fit_line_recovers_fixed_delay_and_slope():
    fit = fit_line([(10, 0.5), (50, 1.3), (110, 2.5)])
    assert fit is not None
    delay, slope = fit
    assert delay == pytest.approx(0.3)
    assert slope == pytest.approx(0.02)
    assert fit_line([(10, 1.0)]) is None
    assert fit_line([(10, 1.0), (10, 2.0)]) is None


def test_measure_engine_records_first_warm_and_concurrency(monkeypatch):
    calls: list[str] = []

    def fake_synth(text, entry, url):
        calls.append(text)
        assert entry == {"speaker": 3}
        return make_wav()

    monkeypatch.setattr(voice_bench, "synthesize", fake_synth)
    result = measure_engine("pc", "http://pc", {"speaker": 3}, trials=2, levels=[1, 2])

    assert (result.version, result.devices) == ("0.26.0", "cpu")
    first = [s for s in result.samples if s.phase == "first"]
    assert len(first) == 1 and first[0].size == "medium"
    sequential = [s for s in result.samples if s.mode == "sequential" and s.phase == "warm"]
    assert sorted({s.size for s in sequential}) == ["long", "medium", "short"]
    assert len(sequential) == 3 * 2
    concurrent = [s for s in result.samples if s.mode == "concurrent-2"]
    assert len(concurrent) == 2 * 2
    assert all(s.ok and s.audio_sec == 1.0 and s.chars == len(SENTENCES[s.size]) for s in result.samples)
    assert [c.concurrency for c in result.concurrency] == [1, 2]
    assert len(calls) == 1 + 6 + 4


def test_measure_engine_stops_when_first_call_fails(monkeypatch):
    def fail(text, entry, url):
        raise OSError("refused")

    monkeypatch.setattr(voice_bench, "synthesize", fail)
    result = measure_engine("pc", "http://pc", {"speaker": 1}, trials=3, levels=[1, 2])

    assert len(result.samples) == 1
    assert not result.samples[0].ok and "refused" in result.samples[0].error
    assert result.concurrency == []


def test_run_benchmark_and_outputs(tmp_path: Path, monkeypatch):
    def fake_synth(text, entry, url):
        if url == "http://bad":
            raise OSError("down")
        return make_wav()

    monkeypatch.setattr(voice_bench, "synthesize", fake_synth)
    messages: list[str] = []
    results = run_benchmark(
        [("good", "http://good"), ("bad", "http://bad")],
        speaker=1,
        trials=1,
        levels=[1, 2],
        progress=messages.append,
    )
    assert [r.name for r in results] == ["good", "bad"]
    assert messages

    meta = make_meta(1, 1, [1, 2])
    out_dir = write_results(tmp_path, results, meta)
    assert out_dir.name == f"voice_{meta['stamp']}"

    with (out_dir / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert {r["engine"] for r in rows} == {"good", "bad"}
    assert any(r["ok"] == "False" and r["error"] == "down" for r in rows)

    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "| good | 0.26.0 | cpu |" in report
    assert "| bad |" in report and "失敗" in report
    assert report == build_markdown(results, meta)

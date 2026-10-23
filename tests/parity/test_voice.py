"""VOICEVOX 読み上げ（studio/voice.py）のテスト。"""

from __future__ import annotations

import io
import json
import urllib.error
import wave
from pathlib import Path

from studio import voice
from studio.engine import EngineEvent
from studio.voice import VoiceReader, clean_for_speech, join_wavs, load_voice_mapping, split_for_speech


def test_clean_for_speech_strips_markdown():
    text = "**今日の日付**\n- [記事](https://example.com/a) です。https://example.com/b\n1. 次の項目"
    assert clean_for_speech(text) == "今日の日付\n記事 です。\n次の項目"


def test_load_voice_mapping_falls_back_to_example(tmp_path: Path):
    org = tmp_path / "organizations" / "demo"
    org.mkdir(parents=True)
    (org / "voice_mapping.example.json").write_text(
        json.dumps({"a": {"speaker": 3}, "b": {"speaker": "x"}, "c": "bad"}), encoding="utf-8"
    )
    assert load_voice_mapping(tmp_path, "demo") == {"a": {"speaker": 3}}
    assert load_voice_mapping(tmp_path, "missing") == {}


def test_voice_reader_saves_mapped_talents_only(tmp_path: Path, monkeypatch):
    calls: list[tuple[str, int]] = []

    def fake_synthesize(text, entry, base_url=voice.DEFAULT_BASE_URL):
        calls.append((text, entry["speaker"]))
        return b"RIFF"

    monkeypatch.setattr(voice, "synthesize", fake_synthesize)
    reader = VoiceReader(tmp_path, {"news_main": {"speaker": 14}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "s1"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "news_director", "text": "進行表"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "news_main", "text": "**おはようございます**"}))
    reader.close()

    assert calls == [("おはようございます", 14)]
    assert (tmp_path / "sessions" / "audio" / "s1" / "01_news_main.wav").read_bytes() == b"RIFF"


def test_split_for_speech_groups_sentences_by_limit():
    text = "あああ。いいい。ううう。\nえええ"
    assert split_for_speech(text, limit=7) == ["あああ。いいい。", "ううう。", "えええ"]


def _wav(frames: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(frames)
    return buf.getvalue()


def test_join_wavs_concatenates_frames():
    joined = join_wavs([_wav(b"\x01\x00"), _wav(b"\x02\x00\x03\x00")])
    with wave.open(io.BytesIO(joined)) as r:
        assert r.readframes(r.getnframes()) == b"\x01\x00\x02\x00\x03\x00"


def test_voice_reader_skips_chunk_on_http_error(tmp_path: Path, monkeypatch, capsys):
    def flaky(text, entry, base_url=voice.DEFAULT_BASE_URL):
        if text == "bad。":
            raise urllib.error.HTTPError("u", 500, "Internal Server Error", {}, None)  # type: ignore[arg-type]
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", flaky)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: ["ok。", "bad。", "ok2。"])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "s3"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close()

    assert "一部を飛ばします" in capsys.readouterr().err
    with wave.open(str(tmp_path / "sessions" / "audio" / "s3" / "01_a.wav")) as r:
        assert r.getnframes() == 2


def test_voice_reader_stops_after_connection_failure(tmp_path: Path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(voice, "synthesize", fail)
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "s2"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "one"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "two"}))
    reader.close()

    assert capsys.readouterr().err.count("VOICEVOX に接続できない") == 1
    assert not (tmp_path / "sessions" / "audio").exists()

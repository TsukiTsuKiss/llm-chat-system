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
    assert split_for_speech(text, limit=8) == ["あああ。いいい。", "ううう。", "えええ"]


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


def test_parse_voicevox_urls_splits_and_trims():
    assert voice.parse_voicevox_urls(" http://a:50021/ , http://b:50021,, ") == ["http://a:50021", "http://b:50021"]


def test_voice_reader_spreads_chunks_over_engines_in_order(tmp_path: Path, monkeypatch):
    import time

    used: set[str] = set()
    index = {"a。": 1, "b。": 2, "c。": 3, "d。": 4}

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        used.add(base_url)
        if text == "a。":
            time.sleep(0.2)
        return _wav(bytes([index[text], 0]))

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: ["a。", "b。", "c。", "d。"])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1", "http://e2"])
    reader.handle(EngineEvent("session_start", {"session_id": "m1"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close()

    assert used == {"http://e1", "http://e2"}
    with wave.open(str(tmp_path / "sessions" / "audio" / "m1" / "01_a.wav")) as r:
        assert r.readframes(r.getnframes()) == b"\x01\x00\x02\x00\x03\x00\x04\x00"


def test_voice_reader_drops_unreachable_engine_and_continues(tmp_path: Path, monkeypatch, capsys):
    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        if base_url == "http://bad":
            raise OSError("refused")
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: ["a。", "b。", "c。"])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://bad", "http://good"])
    reader.handle(EngineEvent("session_start", {"session_id": "m2"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close()

    err = capsys.readouterr().err
    assert "http://bad に接続できない" in err
    assert "読み上げを中止" not in err
    with wave.open(str(tmp_path / "sessions" / "audio" / "m2" / "01_a.wav")) as r:
        assert r.getnframes() == 3


def test_apply_dictionary_prefers_longer_surface():
    assert voice.apply_dictionary("株探と株探の記事", {"株探": "カブタン", "株": "カブ"}) == "カブタンとカブタンの記事"


def test_voice_reader_applies_dictionary(tmp_path: Path, monkeypatch):
    spoken: list[str] = []
    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: spoken.append(text) or b"RIFF")
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, dictionary={"株探": "カブタン"})
    reader.handle(EngineEvent("session_start", {"session_id": "s3"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "（株探、10月23日）"}))
    reader.close()
    assert spoken == ["（カブタン、10月23日）"]


def test_audio_relay_hands_out_one_at_a_time(tmp_path: Path):
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    first.write_bytes(_wav(b"\x01\x00" * 10))
    second.write_bytes(_wav(b"\x02\x00" * 10))
    relay = voice.AudioRelay()
    assert relay.next_if_idle() is None
    relay.push(first)
    relay.push(second)
    assert relay.next_if_idle() == first
    assert relay.next_if_idle() is None
    relay.finished()
    assert relay.next_if_idle() == second


def test_load_wav_array_returns_rate_and_samples(tmp_path: Path):
    path = tmp_path / "a.wav"
    path.write_bytes(_wav(b"\x01\x00\x02\x00"))
    rate, data = voice.load_wav_array(path)
    assert rate == 24000
    assert data.tolist() == [1, 2]


def test_voice_reader_calls_on_utterance_with_saved_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: _wav(b"\x01\x00"))
    seen: list[Path] = []
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, on_utterance=seen.append)
    reader.begin_session("s9")
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "こんにちは"}))
    reader.close()
    assert seen == [tmp_path / "sessions" / "audio" / "s9" / "01_a.wav"]


def test_web_session_voice_pushes_utterance_to_relay(studio_root: Path, monkeypatch):
    import time

    from studio import web_ui
    from studio.loader import load_session_context
    from studio.web_ui import WebSession, handle_chat_submit

    talent_id = load_session_context("solo", studio_root).org["talent_ids"][0]
    (studio_root / "organizations" / "solo" / "voice_mapping.json").write_text(
        json.dumps({talent_id: {"speaker": 1}}), encoding="utf-8"
    )
    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: _wav(b"\x01\x00"))
    monkeypatch.setattr(web_ui, "engine_available", lambda url=None: True)

    session = WebSession(root=studio_root)
    list(
        handle_chat_submit(
            session, "こんにちは", org_id="solo", workflow_value="", stream=False, temperature=0.7, voice=True
        )
    )
    path = None
    for _ in range(100):
        path = session.relay.next_if_idle()
        if path:
            break
        time.sleep(0.05)
    session.close_voice()

    assert path is not None
    assert path.parent.name == session.engine.state.logger.session_id


def test_web_session_voice_without_mapping_adds_note(studio_root: Path):
    from studio.web_ui import WebSession, handle_chat_submit

    session = WebSession(root=studio_root)
    updates = list(
        handle_chat_submit(
            session, "こんにちは", org_id="solo", workflow_value="", stream=False, temperature=0.7, voice=True
        )
    )
    assert any("voice_mapping.json" in m["content"] for m in updates[-1][0])
    assert session.voice is None


def test_clean_for_speech_drops_backstage_notes():
    assert clean_for_speech("本文です。\n\n（進行メモ）前の発言で日曜日とありました。\n続き") == "本文です。"
    assert clean_for_speech("本文です。\n\n**ディレクター点検**\n- 未確認です") == "本文です。"
    assert clean_for_speech("進行メモという言葉を含む本文です。") == "進行メモという言葉を含む本文です。"

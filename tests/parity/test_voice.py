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
    reader = VoiceReader(tmp_path, {"akari": {"speaker": 14}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "s1"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "midori", "text": "進行表"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "akari", "text": "**おはようございます**"}))
    reader.close()

    assert calls == [("おはようございます", 14)]
    assert (tmp_path / "sessions" / "audio" / "s1" / "01_akari.wav").read_bytes() == b"RIFF"


def test_voice_reader_when_action_reads_only_matching_step(tmp_path: Path, monkeypatch):
    calls: list[str] = []

    def fake_synthesize(text, entry, base_url=voice.DEFAULT_BASE_URL):
        calls.append(text)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake_synthesize)
    mapping = {"midori": {"speaker": 2, "when_action": "放送後"}}
    reader = VoiceReader(tmp_path, mapping, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "s4"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "midori", "action": "放送前。進行表を作る"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "midori", "text": "進行表"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "midori", "action": "放送後の点検"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "midori", "text": "**ディレクター点検**\n- 数字が未確認です。"}))
    reader.close()

    assert calls == ["ディレクター点検", "数字が未確認です。"]
    assert (tmp_path / "sessions" / "audio" / "s4" / "01_midori.wav").exists()


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
    assert not list((tmp_path / "sessions" / "audio").rglob("*.wav"))


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
    relay.started()
    relay.finished()
    assert relay.next_if_idle() == second


def test_audio_relay_ignores_stop_before_playback_starts(tmp_path: Path):
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    first.write_bytes(_wav(b"\x01\x00" * 10))
    second.write_bytes(_wav(b"\x02\x00" * 10))
    relay = voice.AudioRelay()
    relay.push(first)
    relay.push(second)
    assert relay.next_if_idle() == first
    relay.finished()
    assert relay.next_if_idle() is None


def test_audio_relay_exposes_tag_of_playing_audio(tmp_path: Path):
    path = tmp_path / "a.wav"
    path.write_bytes(_wav(b"\x01\x00" * 10))
    relay = voice.AudioRelay()
    relay.push(path, 3)
    assert relay.playing_tag is None
    assert relay.next_if_idle() == path
    assert relay.playing_tag == 3
    relay.started()
    assert relay.playing_tag == 3
    relay.finished()
    assert relay.playing_tag is None


def test_next_audio_update_publishes_playing_index(tmp_path: Path):
    from studio.web_ui import WebSession, audio_finished_update, audio_started_update, next_audio_update

    path = tmp_path / "a.wav"
    path.write_bytes(_wav(b"\x01\x00" * 10))
    session = WebSession(root=tmp_path, relay=voice.AudioRelay())
    session.renderer.messages = [{"role": "assistant", "content": "A"}, {"role": "assistant", "content": "B"}]
    session.relay.push(path, 1)

    _, playing = next_audio_update(session)
    assert playing == "1:1"

    assert not isinstance(audio_started_update(session), str)
    assert session.renderer.messages[1]["content"] == "B"

    _, playing = audio_finished_update(session)
    assert playing == "2:"


def test_audio_relay_reports_stop_arriving_before_audio_ends(tmp_path: Path, capsys):
    path = tmp_path / "a.wav"
    path.write_bytes(_wav(b"\x01\x00" * 24000 * 10))
    relay = voice.AudioRelay()
    relay.push(path)
    assert relay.next_if_idle() == path
    relay.started()
    relay.finished()
    assert "stop 通知が音声の長さより早く届きました" in capsys.readouterr().err


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


def test_engine_monitor_reports_off_idle_busy():
    monitor = voice.EngineMonitor(["http://a", "http://b"], probe=lambda url: url == "http://a")
    assert monitor.states() == [("http://a", "off"), ("http://b", "off")]

    monitor.probe_once()
    assert monitor.states() == [("http://a", "idle"), ("http://b", "off")]

    monitor.set_busy("http://a", True)
    assert monitor.states()[0] == ("http://a", "busy")
    monitor.set_busy("http://a", False)
    assert monitor.states()[0] == ("http://a", "idle")


def test_engine_monitor_skips_probe_while_busy():
    monitor = voice.EngineMonitor(["http://a"], probe=lambda url: False)
    monitor.set_busy("http://a", True)
    monitor.probe_once()
    assert monitor.states() == [("http://a", "busy")]


def test_voice_reader_marks_engine_busy_while_synthesizing(tmp_path: Path, monkeypatch):
    monitor = voice.EngineMonitor(["http://e1"], probe=lambda url: True)
    seen: list[str] = []

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        seen.append(monitor.states()[0][1])
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1"], monitor=monitor)
    reader.handle(EngineEvent("session_start", {"session_id": "led"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close()

    assert seen == ["busy"]
    assert monitor.states() == [("http://e1", "idle")]


def test_voice_reader_uses_standby_engine_once_it_responds(tmp_path: Path, monkeypatch):
    import time

    monitor = voice.EngineMonitor(["http://e1", "http://e2"], probe=lambda url: True)
    monitor.probe_once()
    used: set[str] = set()

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        used.add(base_url)
        time.sleep(0.2)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: ["a。", "b。", "c。", "d。"])
    reader = VoiceReader(
        tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1"], monitor=monitor, standby=["http://e2"]
    )
    reader.handle(EngineEvent("session_start", {"session_id": "revive"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close()

    assert used == {"http://e1", "http://e2"}


def test_voice_reader_starts_next_utterance_while_previous_is_synthesizing(tmp_path: Path, monkeypatch):
    import time

    started: dict[str, float] = {}
    finished: dict[str, float] = {}

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        started[text] = time.monotonic()
        if text == "first":
            time.sleep(0.4)
        finished[text] = time.monotonic()
        return _wav(b"\x01\x00" if text == "first" else b"\x02\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: [text])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1", "http://e2"])
    reader.handle(EngineEvent("session_start", {"session_id": "pipe"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "first"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "second"}))
    reader.close()

    assert started["second"] < finished["first"]
    audio = tmp_path / "sessions" / "audio" / "pipe"
    with wave.open(str(audio / "01_a.wav")) as r:
        assert r.readframes(r.getnframes()) == b"\x01\x00"
    with wave.open(str(audio / "02_a.wav")) as r:
        assert r.readframes(r.getnframes()) == b"\x02\x00"


def test_voice_reader_records_timeline_and_builds_replay(tmp_path: Path, monkeypatch):
    from studio.voice_timeline import build_replay
    from studio.session_report import read_jsonl

    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: _wav(b"\x01\x00"))
    monkeypatch.setattr(voice, "split_for_speech", lambda text: [text])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1"])
    reader.handle(EngineEvent("session_start", {"session_id": "tl"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "a"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "hello", "elapsed": 1.5}))
    reader.close()

    audio_dir = tmp_path / "sessions" / "audio" / "tl"
    kinds = [r["kind"] for r in read_jsonl(audio_dir / "timeline.jsonl")]
    assert kinds == ["step_start", "step_done", "utterance_text", "synth_start", "synth", "utterance", "end"]
    synth_record = next(r for r in read_jsonl(audio_dir / "timeline.jsonl") if r["kind"] == "synth")
    assert synth_record["engine"] == "http://e1" and synth_record["end"] >= synth_record["t"]

    out = build_replay(tmp_path, "tl")
    assert out == audio_dir / "replay.html"
    html = out.read_text(encoding="utf-8")
    assert '"session_id": "tl"' in html and "__DATA__" not in html


def test_timeline_is_not_written_before_first_synthesis(tmp_path: Path):
    from studio.voice_timeline import TimelineRecorder

    recorder = TimelineRecorder()
    recorder.begin(tmp_path / "sessions" / "audio" / "none", "none")
    recorder.add("step_done", talent_id="a")
    assert not (tmp_path / "sessions").exists()


def test_audio_relay_records_play_events(tmp_path: Path):
    from studio.voice_timeline import TimelineRecorder

    recorder = TimelineRecorder()
    recorder.begin(tmp_path, "relay")
    recorder.add("utterance", file="x.wav", duration=1.0)
    relay = voice.AudioRelay()
    relay.timeline = recorder
    path = tmp_path / "x.wav"
    path.write_bytes(_wav(b"\x01\x00" * 100))
    relay.push(path)
    assert relay.next_if_idle() == path
    relay.started()
    relay.finished()

    from studio.session_report import read_jsonl

    kinds = [r["kind"] for r in read_jsonl(tmp_path / "timeline.jsonl")]
    assert kinds == ["utterance", "play_start", "play_stop"]


def test_voice_reader_closes_failed_synthesis_in_timeline(tmp_path: Path, monkeypatch):
    from studio.session_report import read_jsonl

    def fail(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(voice, "synthesize", fail)
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "fail"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "one"}))
    reader.close()

    records = read_jsonl(tmp_path / "sessions" / "audio" / "fail" / "timeline.jsonl")
    assert [r["kind"] for r in records] == ["step_done", "utterance_text", "synth_start", "synth", "end"]
    assert records[3]["failed"] is True


def test_live_iframe_points_page_at_gradio_file_route(tmp_path: Path):
    from studio.voice_timeline import live_iframe_html

    html = live_iframe_html("live1", tmp_path / "sessions" / "audio" / "live1")
    assert html.startswith("<iframe srcdoc=")
    assert "/gradio_api/file=" in html and "live1/" in html
    assert "&quot;live&quot;: true" in html


def test_live_timing_update_publishes_once_per_session(tmp_path: Path, monkeypatch):
    from studio.web_ui import WebSession, live_timing_update

    session = WebSession(root=tmp_path)
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    reader.begin_session("t1")
    session.voice = reader
    session.voice_enabled = True

    first = live_timing_update(session)
    assert first["visible"] is True and "srcdoc" in first["value"]
    assert session.published_timing == "t1"
    assert "visible" not in live_timing_update(session)

    session.voice_enabled = False
    assert live_timing_update(session)["visible"] is False
    reader.close()


def test_mark_turn_end_records_turn_end(tmp_path: Path, monkeypatch):
    from studio.session_report import read_jsonl
    from studio.web_ui import WebSession

    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: _wav(b"\x01\x00"))
    session = WebSession(root=tmp_path)
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    session.voice = reader
    session.voice_enabled = True
    reader.handle(EngineEvent("session_start", {"session_id": "turn"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "x"}))
    reader.close(wait=True)
    session.mark_turn_end()

    kinds = [r["kind"] for r in read_jsonl(tmp_path / "sessions" / "audio" / "turn" / "timeline.jsonl")]
    assert kinds[-2:] == ["end", "turn_end"]


def test_replay_iframe_reads_timeline_and_points_audio_at_gradio(tmp_path: Path):
    import pytest

    from studio.voice_timeline import replay_iframe_html

    with pytest.raises(FileNotFoundError):
        replay_iframe_html(tmp_path, "nothing")

    audio_dir = tmp_path / "sessions" / "audio" / "saved"
    audio_dir.mkdir(parents=True)
    (audio_dir / "timeline.jsonl").write_text(
        json.dumps({"kind": "utterance", "t": 1.0, "file": "01_a.wav", "duration": 2.0}) + "\n", encoding="utf-8"
    )
    html = replay_iframe_html(tmp_path, "saved")
    assert "/gradio_api/file=" in html and "saved/" in html
    assert "&quot;events&quot;" in html and "01_a.wav" in html


def test_live_timing_update_shows_replay_of_resumed_session(tmp_path: Path):
    from studio.web_ui import WebSession, live_timing_update

    audio_dir = tmp_path / "sessions" / "audio" / "old"
    audio_dir.mkdir(parents=True)
    (audio_dir / "timeline.jsonl").write_text(
        json.dumps({"kind": "utterance", "t": 1.0, "file": "01_a.wav", "duration": 2.0}) + "\n", encoding="utf-8"
    )
    session = WebSession(root=tmp_path)
    assert "visible" not in live_timing_update(session)

    session.replay_session_id = "old"
    shown = live_timing_update(session)
    assert shown["visible"] is True and "old/" in shown["value"]
    assert session.published_timing == "replay:old"
    assert not session.live_chart_shown()

    session.reset_chat()
    assert live_timing_update(session)["visible"] is False


def test_live_timing_update_hides_chart_when_toggled_off(tmp_path: Path):
    from studio.web_ui import WebSession, live_timing_update

    reader = VoiceReader(tmp_path, {"a": {"speaker": 1}}, play=False)
    reader.begin_session("t2")
    session = WebSession(root=tmp_path)
    session.voice = reader
    session.voice_enabled = True

    assert live_timing_update(session)["visible"] is True
    assert session.live_chart_shown()
    assert live_timing_update(session, False)["visible"] is False
    assert not session.live_chart_shown()
    assert live_timing_update(session, True)["visible"] is True
    reader.close()


def test_studio_head_listens_for_playing_message_from_replay():
    import MultiRoleStudioWeb as web

    assert "studio-playing" in web.STUDIO_HEAD
    assert "__studioScrollToPlaying" in web.STUDIO_HEAD
    assert web.STUDIO_HEAD.startswith("<script>") and web.STUDIO_HEAD.endswith("</script>")


def test_replay_backfills_utterance_text_from_session_log(tmp_path: Path):
    from studio.voice_timeline import replay_data

    org_dir = tmp_path / "organizations" / "org"
    org_dir.mkdir(parents=True)
    (org_dir / "voice_mapping.json").write_text(json.dumps({"a": {"speaker": 1}, "b": {"speaker": 2}}), encoding="utf-8")
    log = [
        {"type": "session_meta", "organization": "org", "workflow": "wf", "talents": {"a": "A", "b": "B", "c": "C"}},
        {"type": "step", "talent_id": "a", "action": "x", "text": "**one** first"},
        {"type": "step", "talent_id": "c", "action": "x", "text": "silent"},
        {"type": "step", "talent_id": "b", "action": "x", "text": "second"},
        {"type": "step", "talent_id": "a", "action": "x", "text": "third"},
    ]
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in log), encoding="utf-8")
    audio_dir = tmp_path / "sessions" / "audio" / "s1"
    audio_dir.mkdir(parents=True)
    timeline = [
        {"kind": "step_done", "t": 4.0, "talent_id": "a"},
        {"kind": "step_done", "t": 6.0, "talent_id": "c"},
        {"kind": "step_done", "t": 9.0, "talent_id": "b"},
        {"kind": "step_done", "t": 12.0, "talent_id": "a"},
        {"kind": "utterance", "t": 5.0, "file": "01_a.wav", "duration": 1.0},
        {"kind": "utterance", "t": 10.0, "file": "02_b.wav", "duration": 1.0},
        {"kind": "utterance", "t": 13.0, "file": "03_a.wav", "duration": 1.0},
    ]
    (audio_dir / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in timeline), encoding="utf-8")

    texts = [e for e in replay_data(tmp_path, "s1")["events"] if e["kind"] == "utterance_text"]
    assert [(e["file"], e["t"], e["text"]) for e in texts] == [
        ("01_a.wav", 4.0, "one first"),
        ("02_b.wav", 9.0, "second"),
        ("03_a.wav", 12.0, "third"),
    ]

    # 件数や話者が合わないときは、誤った本文を付けない
    (tmp_path / "sessions" / "s1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in log[:-1]), encoding="utf-8"
    )
    assert not [e for e in replay_data(tmp_path, "s1")["events"] if e["kind"] == "utterance_text"]


def _regen_session(tmp_path: Path) -> Path:
    org_dir = tmp_path / "organizations" / "org"
    org_dir.mkdir(parents=True)
    (org_dir / "voice_mapping.json").write_text(json.dumps({"a": {"speaker": 1}}), encoding="utf-8")
    (tmp_path / "voice_dictionary.json").write_text(json.dumps({"株探": "カブタン"}), encoding="utf-8")
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "r1.jsonl").write_text(
        json.dumps({"type": "session_meta", "organization": "org", "workflow": "wf", "talents": {"a": "A"}}),
        encoding="utf-8",
    )
    audio_dir = tmp_path / "sessions" / "audio" / "r1"
    audio_dir.mkdir(parents=True)
    events = [
        {"kind": "utterance_text", "t": 1.0, "file": "01_a.wav", "talent_id": "a", "text": "株探です。二文目。"},
        {"kind": "utterance_text", "t": 5.0, "file": "02_a.wav", "talent_id": "a", "text": "続きです。"},
        {"kind": "utterance", "t": 2.0, "file": "01_a.wav", "duration": 1.0},
        {"kind": "utterance", "t": 6.0, "file": "02_a.wav", "duration": 1.0},
    ]
    (audio_dir / "timeline.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    return audio_dir


def test_regenerate_audio_creates_only_missing_files(tmp_path: Path, monkeypatch):
    from studio.voice_regen import missing_audio_files, regenerate_audio

    audio_dir = _regen_session(tmp_path)
    (audio_dir / "01_a.wav").write_bytes(_wav(b"\x09\x00"))
    spoken: list[str] = []

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        spoken.append(text)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "engine_available", lambda url=None: True)
    assert missing_audio_files(tmp_path, "r1") == ["02_a.wav"]

    result = regenerate_audio(tmp_path, "r1", urls=["http://e1"])
    assert result.created == ["02_a.wav"] and not result.failed
    assert spoken == ["続きです。"]
    assert (audio_dir / "02_a.wav").is_file()
    assert audio_dir.joinpath("01_a.wav").read_bytes() == _wav(b"\x09\x00")
    assert missing_audio_files(tmp_path, "r1") == []
    assert regenerate_audio(tmp_path, "r1", urls=["http://e1"]).message == "再生成が必要な音声はありません"


def test_regenerate_audio_force_applies_dictionary_and_overwrites(tmp_path: Path, monkeypatch):
    from studio.voice_regen import regenerate_audio

    audio_dir = _regen_session(tmp_path)
    (audio_dir / "01_a.wav").write_bytes(_wav(b"\x09\x00"))
    (audio_dir / "02_a.wav").write_bytes(_wav(b"\x09\x00"))
    spoken: list[str] = []

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        spoken.append(text)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "engine_available", lambda url=None: True)
    result = regenerate_audio(tmp_path, "r1", urls=["http://e1", "http://e2"], force=True)

    assert sorted(result.created) == ["01_a.wav", "02_a.wav"]
    assert "カブタンです。二文目。" in spoken
    assert audio_dir.joinpath("01_a.wav").read_bytes() == _wav(b"\x01\x00")


def test_regenerate_audio_reports_when_engine_unreachable(tmp_path: Path, monkeypatch):
    from studio.voice_regen import regenerate_audio

    _regen_session(tmp_path)
    monkeypatch.setattr(voice, "engine_available", lambda url=None: False)
    result = regenerate_audio(tmp_path, "r1", urls=["http://e1"])
    assert result.failed == ["01_a.wav", "02_a.wav"] and "接続できない" in result.message


def test_voice_cleanup_deletes_only_regenerable_old_wavs(tmp_path: Path):
    import os
    import time
    from datetime import datetime

    from studio import voice_cleanup

    org_dir = tmp_path / "organizations" / "org"
    org_dir.mkdir(parents=True)
    (tmp_path / "sessions").mkdir()

    def make(session_id: str, *, texts: bool, timeline: bool = True) -> Path:
        audio = tmp_path / "sessions" / "audio" / session_id
        audio.mkdir(parents=True)
        (audio / "01_a.wav").write_bytes(b"x" * 100)
        if timeline:
            events = [{"kind": "utterance", "t": 1.0, "file": "01_a.wav", "duration": 1.0}]
            if texts:
                events.append({"kind": "utterance_text", "t": 1.0, "file": "01_a.wav", "talent_id": "a", "text": "t"})
            (audio / "timeline.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        old = time.time() - 86400 * 30
        for path in audio.iterdir():
            os.utime(path, (old, old))
        return audio

    make("20261001_100000", texts=True)
    make("20261002_100000", texts=False)
    make("20261003_100000", texts=True, timeline=False)
    make("20261026_100000", texts=True)

    items = {i.session_id: i for i in voice_cleanup.plan(tmp_path, older_than_days=3, now=datetime(2026, 10, 27))}
    assert items["20261001_100000"].action == "delete"
    assert items["20261002_100000"].action == "skip" and "本文" in items["20261002_100000"].reason
    assert items["20261003_100000"].action == "skip" and "記録がない" in items["20261003_100000"].reason
    assert items["20261026_100000"].action == "keep"

    kept = {i.session_id: i.action for i in voice_cleanup.plan(tmp_path, keep_latest=1, now=datetime(2026, 10, 27))}
    assert kept["20261026_100000"] == "keep" and kept["20261001_100000"] == "delete"

    forced = voice_cleanup.plan(
        tmp_path, older_than_days=3, include_unregenerable=True, now=datetime(2026, 10, 27)
    )
    assert {i.session_id: i.action for i in forced}["20261003_100000"] == "delete"

    assert voice_cleanup.apply(list(items.values())) == 100
    base = tmp_path / "sessions" / "audio"
    assert not (base / "20261001_100000" / "01_a.wav").exists()
    assert (base / "20261001_100000" / "timeline.jsonl").exists()
    assert (base / "20261002_100000" / "01_a.wav").exists()


def test_engine_led_html_shows_state_per_engine():
    from studio.web_ui import engine_led_html

    html = engine_led_html([("http://a:50021", "off"), ("http://b:50021", "idle"), ("http://c:50021", "busy")])
    assert html.count("border-radius:50%") == 3
    assert "http://b:50021: 待機" in html
    assert "#ff4136" in html
    assert engine_led_html([]) == ""


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


def test_clean_for_speech_keeps_underscores_inside_words():
    assert clean_for_speech("raw_live_stack.py と _強調_ と __init__") == "raw_live_stack.py と 強調 と init"


def test_clean_for_speech_normalizes_odd_spaces_and_hyphens():
    assert clean_for_speech("Raspberry\u202fPi\u00a0Zero\u20092W と Wi\u2011Fi") == "Raspberry Pi Zero 2W と Wi-Fi"


def test_clean_for_speech_drops_backstage_notes():
    assert clean_for_speech("本文です。\n\n（進行メモ）前の発言で日曜日とありました。\n続き") == "本文です。"
    assert clean_for_speech("本文です。\n\n**ディレクター点検**\n- 未確認です") == "本文です。"
    assert clean_for_speech("進行メモという言葉を含む本文です。") == "進行メモという言葉を含む本文です。"


def test_clean_for_speech_drops_operation_and_research_memos():
    note = "本文です。\n\n（番組運用メモ・読み上げ対象外）前の発言の確認状況：未確認です。"
    assert clean_for_speech(note) == "本文です。"
    memo = "本文です。\n\n**ディレクター・リサーチメモ（放送用ではありません）**\n- 未確認"
    assert clean_for_speech(memo) == "本文です。"
    assert clean_for_speech("運用メモの見直しを話します。") == "運用メモの見直しを話します。"

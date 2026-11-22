"""声の variants（step の action に合う文字列で、声・速さなどを切り替える）。"""

from __future__ import annotations

import json
from pathlib import Path

from studio import voice
from studio.engine import EngineEvent
from studio.session_report import read_jsonl
from studio.voice import (
    VoiceReader,
    entry_labels,
    resolve_voice_entry,
    variant_voice_entry,
)
from tests.parity.test_voice import _regen_session, _wav

ENTRY = {
    "label": "四国めたん",
    "speaker": 2,
    "speed": 1.0,
    "variants": [
        {"when_action": "放送後", "speaker": 5, "speed": 1.2, "label": "ずんだもん", "ignored": 1},
        {"when_action": "放送", "pitch": 0.1},
    ],
}


def test_resolve_voice_entry_first_match_wins_and_overlays_only_voice_keys():
    entry, variant = resolve_voice_entry(ENTRY, "放送後の点検")
    assert variant == "放送後"
    assert entry == {"label": "ずんだもん", "speaker": 5, "speed": 1.2}
    entry, variant = resolve_voice_entry(ENTRY, "放送前の準備")
    assert variant == "放送" and entry["speaker"] == 2 and entry["pitch"] == 0.1


def test_resolve_voice_entry_without_match_returns_base_without_variants():
    entry, variant = resolve_voice_entry(ENTRY, "進行")
    assert variant is None
    assert entry == {"label": "四国めたん", "speaker": 2, "speed": 1.0}
    assert resolve_voice_entry({"speaker": 1}, "x") == ({"speaker": 1}, None)


def test_variant_voice_entry_matches_recorded_when_action_exactly():
    assert variant_voice_entry(ENTRY, "放送後")["speaker"] == 5
    assert variant_voice_entry(ENTRY, "放送後の点検")["speaker"] == 2
    assert variant_voice_entry(ENTRY, None)["speaker"] == 2


def test_entry_labels_lists_unique_labels_in_order():
    assert entry_labels(ENTRY) == ["四国めたん", "ずんだもん"]
    assert entry_labels({"speaker": 1}) == []
    assert entry_labels({"label": "A", "variants": [{"when_action": "x", "label": "A"}]}) == ["A"]


def test_voice_reader_applies_variant_and_records_it(tmp_path: Path, monkeypatch):
    used: list[dict] = []

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        used.append(entry)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: [text])
    reader = VoiceReader(tmp_path, {"a": {"speaker": 1, "variants": [{"when_action": "判定", "speaker": 9, "speed": 1.3}]}}, play=False)
    reader.handle(EngineEvent("session_start", {"session_id": "v1"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "a", "action": "通常の発言"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "ひとつめ"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "a", "action": "【判定】を出す"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "ふたつめ"}))
    reader.close()

    assert [(e["speaker"], e.get("speed")) for e in used] == [(1, None), (9, 1.3)]
    texts = [r for r in read_jsonl(tmp_path / "sessions" / "audio" / "v1" / "timeline.jsonl") if r["kind"] == "utterance_text"]
    assert "variant" not in texts[0] and texts[1]["variant"] == "判定"


def test_regenerate_audio_uses_recorded_variant(tmp_path: Path, monkeypatch):
    from studio.voice_regen import regenerate_audio

    audio_dir = _regen_session(tmp_path)
    org_dir = tmp_path / "organizations" / "org"
    (org_dir / "voice_mapping.json").write_text(
        json.dumps({"a": {"speaker": 1, "variants": [{"when_action": "判定", "speaker": 9}]}}), encoding="utf-8"
    )
    events = [json.loads(line) for line in (audio_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
    for event in events:
        if event.get("file") == "02_a.wav" and event["kind"] == "utterance_text":
            event["variant"] = "判定"
    (audio_dir / "timeline.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    speakers: dict[str, int] = {}

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        speakers[text] = entry["speaker"]
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "engine_available", lambda url=None: True)
    regenerate_audio(tmp_path, "r1", urls=["http://e1"], force=True)

    assert speakers["続きです。"] == 9
    assert speakers["カブタンです。二文目。"] == 1

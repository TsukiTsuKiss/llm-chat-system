"""声の層（人材の既定の声・組織の上書き・read:false・役割の話し方）と、step_start の役割名（slot）。"""

from __future__ import annotations

import json
from pathlib import Path

from studio import voice
from studio.assistants import MockAssistant
from studio.engine import EngineEvent, SessionEngine, collect_events
from studio.loader import load_session_context
from studio.session_report import read_jsonl
from studio.voice import (
    VoiceReader,
    load_voice_mapping,
    load_voice_roles,
    resolve_voice_entry,
    talent_voice,
    variant_voice_entry,
)
from tests.parity.test_phase2_workflow import trio_root  # noqa: F401  (fixture)
from tests.parity.test_voice import _regen_session, _wav


def make_root(root: Path, org_talents: list[str], talent_voices: dict[str, object], mapping: dict | None = None) -> None:
    org = root / "organizations" / "org"
    org.mkdir(parents=True)
    (org / "config.json").write_text(json.dumps({"name": "組織", "talent_ids": org_talents}), encoding="utf-8")
    (root / "talents").mkdir()
    for tid in org_talents:
        data: dict = {"name": tid, "system_prompt": "x"}
        if tid in talent_voices:
            data["voice"] = talent_voices[tid]
        (root / "talents" / f"{tid}.json").write_text(json.dumps(data), encoding="utf-8")
    if mapping is not None:
        (org / "voice_mapping.json").write_text(json.dumps(mapping), encoding="utf-8")


def test_talent_voice_accepts_only_voicevox_with_integer_speaker(tmp_path):
    make_root(
        tmp_path,
        ["a", "b", "c", "d"],
        {
            "a": {"engine": "voicevox", "speaker": 2, "label": "四国めたん"},
            "b": {"engine": "other", "speaker": 2},
            "c": {"engine": "voicevox", "speaker": "2"},
        },
    )
    assert talent_voice(tmp_path, "a") == {"speaker": 2, "label": "四国めたん"}
    assert talent_voice(tmp_path, "b") is None and talent_voice(tmp_path, "c") is None
    assert talent_voice(tmp_path, "d") is None and talent_voice(tmp_path, "missing") is None


def test_load_voice_mapping_uses_talent_voice_without_org_file(tmp_path):
    make_root(tmp_path, ["a", "b"], {"a": {"engine": "voicevox", "speaker": 2, "label": "四国めたん", "speed": 1.1}})
    assert load_voice_mapping(tmp_path, "org") == {"a": {"speaker": 2, "label": "四国めたん", "speed": 1.1}}


def test_org_mapping_overrides_talent_voice_and_adds_org_only_keys(tmp_path):
    make_root(
        tmp_path,
        ["a", "b"],
        {"a": {"engine": "voicevox", "speaker": 2, "label": "四国めたん", "speed": 1.1}},
        {
            "a": {"speed": 1.3, "when_action": "放送後"},
            "b": {"speaker": 3, "label": "ずんだもん"},
            "user": {"speaker": 8},
        },
    )
    mapping = load_voice_mapping(tmp_path, "org")
    assert mapping["a"] == {"speaker": 2, "label": "四国めたん", "speed": 1.3, "when_action": "放送後"}
    assert mapping["b"] == {"speaker": 3, "label": "ずんだもん"}
    assert mapping["user"] == {"speaker": 8}


def test_org_speaker_override_drops_stale_talent_label(tmp_path):
    make_root(tmp_path, ["a", "b"], {"a": {"engine": "voicevox", "speaker": 2, "label": "四国めたん"}}, {"a": {"speaker": 3}})
    assert load_voice_mapping(tmp_path, "org")["a"] == {"speaker": 3}
    make_root_b = {"a": {"speaker": 2}}
    (tmp_path / "organizations" / "org" / "voice_mapping.json").write_text(json.dumps(make_root_b), encoding="utf-8")
    assert load_voice_mapping(tmp_path, "org")["a"]["label"] == "四国めたん"


def test_read_false_excludes_a_talent_that_has_a_default_voice(tmp_path):
    make_root(
        tmp_path,
        ["a", "b"],
        {"a": {"engine": "voicevox", "speaker": 2}, "b": {"engine": "voicevox", "speaker": 3}},
        {"b": {"read": False}, "_roles": {"x": {"speed": 1.1}}},
    )
    assert list(load_voice_mapping(tmp_path, "org")) == ["a"]


def test_load_voice_roles_keeps_only_numeric_style_keys(tmp_path):
    make_root(
        tmp_path,
        ["a"],
        {},
        {"_roles": {"moderator": {"speed": 0.95, "pitch": -0.02, "speaker": 9, "intonation": "x"}, "bad": 1}},
    )
    assert load_voice_roles(tmp_path, "org") == {"moderator": {"speed": 0.95, "pitch": -0.02}}
    assert load_voice_roles(tmp_path, "missing") == {}


def test_resolution_order_is_base_then_role_then_variant():
    entry = {"speaker": 2, "speed": 1.0, "variants": [{"when_action": "判定", "speed": 1.5, "speaker": 5}]}
    roles = {"moderator": {"speed": 0.9, "pitch": 0.05, "speaker": 99}}
    assert resolve_voice_entry(entry, "通常", "moderator", roles) == ({"speaker": 2, "speed": 0.9, "pitch": 0.05}, None)
    assert resolve_voice_entry(entry, "【判定】", "moderator", roles) == (
        {"speaker": 5, "speed": 1.5, "pitch": 0.05},
        "判定",
    )
    assert resolve_voice_entry(entry, "通常", "member", roles)[0] == {"speaker": 2, "speed": 1.0}
    assert variant_voice_entry(entry, "判定", "moderator", roles)["speed"] == 1.5
    assert variant_voice_entry(entry, None, "moderator", roles)["speed"] == 0.9


def test_voice_reader_applies_role_style_and_records_slot(tmp_path, monkeypatch):
    used: list[dict] = []

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        used.append(entry)
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "split_for_speech", lambda text: [text])
    reader = VoiceReader(
        tmp_path, {"a": {"speaker": 1, "speed": 1.0}}, play=False, roles={"moderator": {"speed": 0.9}}
    )
    reader.handle(EngineEvent("session_start", {"session_id": "r1"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "a", "action": "進行", "slot": "moderator"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "ひとつめ"}))
    reader.handle(EngineEvent("step_start", {"talent_id": "a", "action": "発言", "slot": "member"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "ふたつめ"}))
    reader.close()

    assert [e["speed"] for e in used] == [0.9, 1.0]
    texts = [r for r in read_jsonl(tmp_path / "sessions" / "audio" / "r1" / "timeline.jsonl") if r["kind"] == "utterance_text"]
    assert texts[0]["slot"] == "moderator" and "slot" not in texts[1]


def test_regenerate_audio_reproduces_role_style(tmp_path, monkeypatch):
    from studio.voice_regen import regenerate_audio

    audio_dir = _regen_session(tmp_path)
    (tmp_path / "organizations" / "org" / "voice_mapping.json").write_text(
        json.dumps({"a": {"speaker": 1, "speed": 1.0}, "_roles": {"moderator": {"speed": 0.8}}}), encoding="utf-8"
    )
    events = [json.loads(line) for line in (audio_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
    for event in events:
        if event["kind"] == "utterance_text" and event["file"] == "02_a.wav":
            event["slot"] = "moderator"
    (audio_dir / "timeline.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    speeds: dict[str, float] = {}

    def fake(text, entry, base_url=voice.DEFAULT_BASE_URL):
        speeds[text] = entry["speed"]
        return _wav(b"\x01\x00")

    monkeypatch.setattr(voice, "synthesize", fake)
    monkeypatch.setattr(voice, "engine_available", lambda url=None: True)
    regenerate_audio(tmp_path, "r1", urls=["http://e1"], force=True)
    assert speeds["続きです。"] == 0.8 and speeds["カブタンです。二文目。"] == 1.0


def test_step_start_carries_slot_in_serial_and_parallel_phases(trio_root: Path) -> None:  # noqa: F811
    MockAssistant.reset()
    ctx = load_session_context("trio", trio_root, workflow_id="discussion")
    starts = [e for e in collect_events(SessionEngine(ctx), "議題", stream=False) if e.type == "step_start"]
    assert starts and all(e.payload["talent_id"] in ctx.slot_bindings[e.payload["slot"]] for e in starts)

    MockAssistant.reset()
    ctx = load_session_context("trio", trio_root, workflow_id="quiz")
    starts = [e for e in collect_events(SessionEngine(ctx), "問題", stream=False) if e.type == "step_start"]
    assert starts and all(e.payload["talent_id"] in ctx.slot_bindings[e.payload["slot"]] for e in starts)

    MockAssistant.reset()
    direct = collect_events(SessionEngine(load_session_context("trio", trio_root)), "直接", stream=False)
    assert all("slot" not in e.payload for e in direct if e.type == "step_start")


def test_credit_text_uses_engine_display_name_and_falls_back_to_id():
    assert voice.credit_text(None, "四国めたん") == "VOICEVOX: 四国めたん"
    assert voice.credit_text("voicevox", "") == "VOICEVOX"
    assert voice.credit_text("future_tts", "Aさん") == "future_tts: Aさん"


def test_voice_statuses_distinguish_voice_silent_stopped_and_unset(tmp_path):
    make_root(
        tmp_path,
        ["a", "b", "c", "d", "e"],
        {
            "a": {"engine": "voicevox", "speaker": 2, "label": "四国めたん"},
            "b": {"engine": "none"},
            "c": {"engine": "voicevox", "speaker": 3, "label": "ずんだもん"},
            "e": {"engine": "none"},
        },
        {"c": {"read": False}, "e": {"speaker": 8, "label": "春日部つむぎ"}},
    )
    statuses = voice.voice_statuses(tmp_path, "org")
    assert {tid: s.kind for tid, s in statuses.items()} == {"a": "voice", "b": "none", "c": "stopped", "d": "unset", "e": "voice"}
    assert statuses["a"].text == "VOICEVOX: 四国めたん" and statuses["e"].text == "VOICEVOX: 春日部つむぎ"
    assert statuses["b"].text == "音なし" and statuses["c"].text == "音なし（この組織で停止）"
    assert statuses["d"].text == "声なし（読み上げません）"
    assert list(load_voice_mapping(tmp_path, "org")) == ["a", "e"]


def test_silent_talents_note_lists_only_unset_talents(tmp_path):
    make_root(tmp_path, ["a", "b", "c"], {"a": {"engine": "voicevox", "speaker": 2}, "b": {"engine": "none"}})
    assert voice.silent_talents_note(tmp_path, "org") == "声のない人材（読み上げません）: c"
    make_root_all = {"c": {"engine": "voicevox", "speaker": 3}}
    set_path = tmp_path / "talents" / "c.json"
    data = json.loads(set_path.read_text(encoding="utf-8"))
    data["voice"] = make_root_all["c"]
    set_path.write_text(json.dumps(data), encoding="utf-8")
    assert voice.silent_talents_note(tmp_path, "org") == ""


def test_talent_schema_accepts_silent_voice_and_rejects_extra_fields():
    from studio.schema_validate import validate_schema_document

    def errors(voice_value):
        return validate_schema_document({"name": "x", "system_prompt": "y", "voice": voice_value}, "talent", "t").errors

    assert not errors({"engine": "none"})
    assert not errors({"engine": "voicevox", "speaker": 2})
    assert errors({"engine": "voicevox"})  # speaker が必要
    assert errors({"engine": "none", "speaker": 2})  # 音なしに声は付けない
    assert errors({"engine": "other", "speaker": 2})


def test_session_report_shows_engine_name_from_voice_engines():
    from studio.session_report import generate_session_markdown

    records = [
        {
            "type": "session_meta",
            "organization": "demo",
            "workflow": "wf",
            "talents": {"a": "あ", "b": "い"},
            "models": {},
            "voices": {"a": "四国めたん", "b": "Aさん"},
            "voice_engines": {"b": "future_tts"},
            "generation": {},
        }
    ]
    markdown = generate_session_markdown(records, session_id="20261123_000000")
    assert "VOICEVOX: 四国めたん" in markdown and "future_tts: Aさん" in markdown

"""声のマッピングの編集（読み書き・検証・試聴・画面の部品）。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from studio import voice_mapping, voice_mapping_ui
from studio.voice_mapping import (
    SpeakerStyle,
    build_entry,
    build_roles,
    build_talent_voice,
    build_variant,
    fetch_speakers,
    preview_wav,
    read_talent_voice,
    read_voice_mapping_raw,
    save_talent_voice,
    save_voice_mapping,
    shared_speakers,
    validate_entry,
)
from studio.voice_mapping_ui import (
    INHERIT,
    NO_VOICE_NOTE,
    base_updates,
    org_updates,
    overview_markdown,
    override_from_fields,
    preview_entry,
    role_updates,
    save_override,
    save_roles,
    talent_voice_from_fields,
)

SPEAKERS = [SpeakerStyle("四国めたん", "ノーマル", 2), SpeakerStyle("ずんだもん", "ノーマル", 3)]


def make_org(root: Path, talent_ids: list[str], mapping: dict | None = None, *, example: bool = False) -> Path:
    org = root / "organizations" / "org"
    org.mkdir(parents=True)
    (org / "config.json").write_text(json.dumps({"name": "組織", "talent_ids": talent_ids}, ensure_ascii=False), encoding="utf-8")
    (root / "talents").mkdir(exist_ok=True)
    for tid in talent_ids:
        (root / "talents" / f"{tid}.json").write_text(json.dumps({"name": f"名前{tid}", "system_prompt": "x"}), encoding="utf-8")
    if mapping is not None:
        name = "voice_mapping.example.json" if example else "voice_mapping.json"
        (org / name).write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return org


def test_read_voice_mapping_raw_prefers_real_file_and_falls_back_to_example(tmp_path):
    org = make_org(tmp_path, ["a"], {"a": {"speaker": 1}, "user": {"speaker": 8}, "bad": 5}, example=True)
    assert read_voice_mapping_raw(tmp_path, "org") == {"a": {"speaker": 1}, "user": {"speaker": 8}}
    (org / "voice_mapping.json").write_text(json.dumps({"a": {"speaker": 2}}), encoding="utf-8")
    assert read_voice_mapping_raw(tmp_path, "org") == {"a": {"speaker": 2}}
    assert read_voice_mapping_raw(tmp_path, "none") == {}


@pytest.mark.parametrize(
    "entry",
    [
        {"speaker": 1, "read": "no"},
        {"speaker": -1},
        {"speaker": 1, "speed": 3.0},
        {"speaker": 1, "pitch": 0.5},
        {"speaker": 1, "intonation": -1},
        {"speaker": 1, "unknown": 1},
        {"speaker": 1, "variants": [{"speaker": 2}]},
        {"speaker": 1, "variants": [{"when_action": "x", "speed": 9}]},
        {"speaker": 1, "variants": ["x"]},
    ],
)
def test_validate_entry_rejects_bad_values(entry):
    assert validate_entry("a", entry)


def test_validate_entry_accepts_full_entry():
    entry = {
        "label": "四国めたん",
        "speaker": 2,
        "speed": 1.2,
        "pitch": -0.1,
        "intonation": 1.5,
        "when_action": "放送後",
        "variants": [{"when_action": "判定", "speaker": 3, "speed": 1.0, "label": "ずんだもん"}],
    }
    assert validate_entry("a", entry) == []


def test_save_voice_mapping_writes_real_file_only_and_validates(tmp_path):
    org = make_org(tmp_path, ["a"], {"a": {"speaker": 1}}, example=True)
    path = save_voice_mapping(tmp_path, "org", {"a": {"speaker": 2, "label": "四国めたん"}})
    assert path == org / "voice_mapping.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": {"speaker": 2, "label": "四国めたん"}}
    assert json.loads((org / "voice_mapping.example.json").read_text(encoding="utf-8")) == {"a": {"speaker": 1}}
    assert "四国めたん" in path.read_text(encoding="utf-8")
    assert not (org / "voice_mapping.json.tmp").exists()
    with pytest.raises(ValueError, match="speed"):
        save_voice_mapping(tmp_path, "org", {"a": {"speaker": 1, "speed": 5}})
    assert json.loads(path.read_text(encoding="utf-8"))["a"]["speaker"] == 2


def test_build_entry_and_variant_omit_empty_values():
    assert build_entry(speaker="3", label="", speed=None, pitch="", intonation=None, when_action=" ", variants=[]) == {"speaker": 3}
    entry = build_entry(
        speaker=2, label="L", speed=1.2, pitch=0, intonation=None, when_action="放送後", variants=[{"when_action": "x"}]
    )
    assert entry == {"label": "L", "speaker": 2, "speed": 1.2, "pitch": 0.0, "when_action": "放送後", "variants": [{"when_action": "x"}]}
    assert build_variant(when_action=" ", label="", speaker=None, speed=None, pitch=None, intonation=None) is None
    assert build_variant(when_action="判定", label="", speaker=None, speed=1.1, pitch=None, intonation=None) == {
        "when_action": "判定",
        "speed": 1.1,
    }


def test_shared_speakers_reports_only_duplicates_and_ignores_user():
    mapping = {"a": {"speaker": 2}, "b": {"speaker": 2}, "c": {"speaker": 3}, "user": {"speaker": 2}}
    assert shared_speakers(mapping) == {2: ["a", "b"]}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_speakers_uses_first_responding_engine_and_caches(monkeypatch):
    monkeypatch.setattr(voice_mapping, "_speakers_cache", None)
    monkeypatch.setattr(voice_mapping, "prefer_ipv4", lambda url: url)
    calls: list[str] = []
    payload = [{"name": "四国めたん", "styles": [{"name": "ノーマル", "id": 2}, {"name": "あまあま", "id": 0}]}]

    def fake_urlopen(url, timeout):
        calls.append(url)
        if "bad" in url:
            raise OSError("down")
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr(voice_mapping.urllib.request, "urlopen", fake_urlopen)
    speakers = fetch_speakers(["http://bad", "http://good"])
    assert [(s.character, s.style, s.speaker_id) for s in speakers] == [("四国めたん", "ノーマル", 2), ("四国めたん", "あまあま", 0)]
    assert speakers[0].display == "四国めたん（ノーマル） #2"
    assert fetch_speakers(["http://bad"]) == speakers and calls == ["http://bad/speakers", "http://good/speakers"]


def test_fetch_speakers_returns_empty_when_no_engine(monkeypatch):
    monkeypatch.setattr(voice_mapping, "_speakers_cache", None)
    monkeypatch.setattr(voice_mapping, "prefer_ipv4", lambda url: url)

    def fail(url, timeout):
        raise OSError("down")

    monkeypatch.setattr(voice_mapping.urllib.request, "urlopen", fail)
    assert fetch_speakers(["http://x"]) == []


def test_preview_wav_falls_back_to_next_engine_then_raises(monkeypatch):
    def fake(text, entry, url):
        if url == "http://bad":
            raise OSError("down")
        return b"wav:" + url.encode()

    monkeypatch.setattr(voice_mapping, "synthesize", fake)
    assert preview_wav({"speaker": 1}, "", ["http://bad", "http://ok"]) == b"wav:http://ok"
    with pytest.raises(OSError):
        preview_wav({"speaker": 1}, "x", ["http://bad"])


def set_talent_voice(root: Path, talent_id: str, voice: dict) -> None:
    path = root / "talents" / f"{talent_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["voice"] = voice
    path.write_text(json.dumps(data), encoding="utf-8")


def test_build_entry_read_false_and_optional_speaker():
    assert build_entry(speaker=None, label="", speed=1.1, pitch=None, intonation=None, when_action="", variants=[], read=False) == {
        "read": False,
        "speed": 1.1,
    }


def test_build_talent_voice_and_roles():
    assert build_talent_voice(speaker="2", label="四国めたん", speed=None, pitch=0.1, intonation="") == {
        "engine": "voicevox",
        "speaker": 2,
        "label": "四国めたん",
        "pitch": 0.1,
    }
    assert build_roles([("moderator", 0.9, None, None), ("", 1.0, None, None), ("member", None, None, None)]) == {
        "moderator": {"speed": 0.9}
    }


def test_validate_roles_rejects_voice_keys_and_out_of_range(tmp_path):
    make_org(tmp_path, ["a"])
    with pytest.raises(ValueError, match="speaker"):
        save_voice_mapping(tmp_path, "org", {"_roles": {"moderator": {"speaker": 3}}})
    with pytest.raises(ValueError, match="speed"):
        save_voice_mapping(tmp_path, "org", {"_roles": {"moderator": {"speed": 9}}})
    save_voice_mapping(tmp_path, "org", {"a": {"speed": 1.1}, "_roles": {"moderator": {"speed": 0.9}}})


def test_save_and_read_talent_voice_keeps_other_fields(tmp_path):
    make_org(tmp_path, ["a"])
    save_talent_voice(tmp_path, "a", {"engine": "voicevox", "speaker": 2, "label": "四国めたん"})
    data = json.loads((tmp_path / "talents" / "a.json").read_text(encoding="utf-8"))
    assert data["name"] == "名前a" and data["voice"]["speaker"] == 2
    assert read_talent_voice(tmp_path, "a") == data["voice"]
    with pytest.raises(ValueError):
        save_talent_voice(tmp_path, "a", {"engine": "voicevox", "speaker": 2, "speed": 9})
    save_talent_voice(tmp_path, "a", None)
    assert read_talent_voice(tmp_path, "a") is None
    with pytest.raises(ValueError, match="見つかりません"):
        save_talent_voice(tmp_path, "zzz", None)


def test_overview_shows_effective_voice_source_state_and_warnings(tmp_path):
    make_org(
        tmp_path,
        ["a", "b", "c", "d"],
        {"b": {"speaker": 2, "label": "四国めたん"}, "c": {"read": False}, "_roles": {"moderator": {"speed": 0.9}}},
    )
    set_talent_voice(tmp_path, "a", {"engine": "voicevox", "speaker": 2, "label": "四国めたん", "speed": 1.2})
    set_talent_voice(tmp_path, "c", {"engine": "voicevox", "speaker": 3, "label": "ずんだもん"})
    text = " ".join(overview_markdown(tmp_path, "org").split())
    assert "名前a (`a`) | 四国めたん | 2 | 1.2 | | | 人材の既定 | 読む" in text
    assert "名前b (`b`) | 四国めたん | 2 | | | | 組織の上書き | 読む" in text
    assert "名前c (`c`) | | | | | | | 音なし（この組織で停止）" in text
    assert "名前d (`d`) | | | | | | | 声なし（読み上げません）" in text
    assert "moderator（speed 0.9）" in text
    assert "speaker 2 が重なっています: a, b" in text
    assert overview_markdown(tmp_path, None) == "組織を選んでください。"


def test_field_updates_fill_base_org_and_role_rows():
    assert len(base_updates({"speaker": 2, "speed": 1.2}, SPEAKERS)) == 4
    assert base_updates(None, SPEAKERS)[1:] == [None, None, None]
    updates = org_updates(
        {"read": False, "speaker": 3, "when_action": "放送後", "variants": [{"when_action": "判定", "speaker": 2, "pitch": 0.1}]},
        SPEAKERS,
    )
    assert len(updates) == 6 + 3 * 5
    assert updates[0] is False and updates[5] == "放送後" and updates[6] == "判定" and updates[9] == 0.1
    assert org_updates(None, SPEAKERS)[0] is True
    roles = role_updates({"moderator": {"speed": 0.9}}, ["moderator", "member"])
    assert len(roles) == 4 * 4 and roles[1] == 0.9 and roles[5] is None


def _org_values(speaker=INHERIT, speed=None, pitch=None, intonation=None, when="", rows=None):
    rows = rows or []
    flat: list = []
    for index in range(3):
        flat += list(rows[index]) if index < len(rows) else ["", INHERIT, None, None, None]
    return (speaker, speed, pitch, intonation, when, *flat)


def test_talent_voice_from_fields_uses_character_name_and_keeps_previous_label():
    assert talent_voice_from_fields((2, 1.1, None, None), SPEAKERS, None) == {
        "engine": "voicevox",
        "speaker": 2,
        "label": "四国めたん",
        "speed": 1.1,
    }
    assert talent_voice_from_fields((None, None, None, None), SPEAKERS, None) is None
    kept = talent_voice_from_fields((99, None, None, None), SPEAKERS, {"speaker": 99, "label": "旧キャラ"})
    assert kept["label"] == "旧キャラ"


def test_override_from_fields_omits_inherited_values_and_builds_variants():
    assert override_from_fields(True, _org_values(), SPEAKERS, None) == {}
    values = _org_values(3, 1.1, rows=[("判定", 2, 1.3, None, None), ("", INHERIT, None, None, None), ("速報", INHERIT, 1.5, None, None)])
    assert override_from_fields(True, values, SPEAKERS, None) == {
        "label": "ずんだもん",
        "speaker": 3,
        "speed": 1.1,
        "variants": [
            {"when_action": "判定", "label": "四国めたん", "speaker": 2, "speed": 1.3},
            {"when_action": "速報", "speed": 1.5},
        ],
    }
    assert override_from_fields(False, _org_values(), SPEAKERS, None) == {"read": False}


def test_override_from_fields_keeps_extra_variants_beyond_the_screen_rows():
    previous = {"variants": [{"when_action": "a"}, {"when_action": "b"}, {"when_action": "c"}, {"when_action": "d", "speed": 1.1}]}
    assert override_from_fields(True, _org_values(), SPEAKERS, previous)["variants"] == [{"when_action": "d", "speed": 1.1}]


def test_save_override_requires_a_voice_somewhere_and_removes_empty_override(tmp_path):
    make_org(tmp_path, ["a", "b"], {"user": {"speaker": 8}, "b": {"speed": 1.2}})
    mapping = read_voice_mapping_raw(tmp_path, "org")
    with pytest.raises(ValueError, match=NO_VOICE_NOTE[:6]):
        save_override(tmp_path, "org", "a", mapping, True, _org_values(), SPEAKERS)
    set_talent_voice(tmp_path, "a", {"engine": "voicevox", "speaker": 2, "label": "四国めたん"})
    updated = save_override(tmp_path, "org", "a", mapping, True, _org_values(None, 1.2), SPEAKERS)
    assert updated["a"] == {"speed": 1.2} and list(updated) == ["a", "b", "user"]
    cleared = save_override(tmp_path, "org", "a", updated, True, _org_values(), SPEAKERS)
    assert "a" not in cleared
    stopped = save_override(tmp_path, "org", "a", cleared, False, _org_values(), SPEAKERS)
    assert stopped["a"] == {"read": False}


def test_save_roles_writes_underscore_roles_and_removes_when_empty(tmp_path):
    make_org(tmp_path, ["a"], {"a": {"speaker": 2}})
    mapping = read_voice_mapping_raw(tmp_path, "org")
    rows = ("moderator", 0.9, None, 0.5, None, None, None, None, None, None, None, None, None, None, None, None)
    updated = save_roles(tmp_path, "org", mapping, rows)
    assert updated["_roles"] == {"moderator": {"speed": 0.9, "intonation": 0.5}} and list(updated) == ["a", "_roles"]
    saved = json.loads((tmp_path / "organizations" / "org" / "voice_mapping.json").read_text(encoding="utf-8"))
    assert saved["_roles"]["moderator"]["speed"] == 0.9
    assert "_roles" not in save_roles(tmp_path, "org", updated, (None,) * 16)
    with pytest.raises(ValueError, match="speed"):
        save_roles(tmp_path, "org", updated, ("moderator", 9, None, None, *[None] * 12))


def test_preview_entry_layers_base_org_and_variant():
    base = (2, 1.0, None, None)
    org = _org_values(None, 1.2, when="", rows=[("判定", 3, 1.5, None, None)])
    assert preview_entry(base, True, org, SPEAKERS, "人材の既定", None, None) == {"speaker": 2, "label": "四国めたん", "speed": 1.0}
    assert preview_entry(base, True, org, SPEAKERS, "この組織", None, None)["speed"] == 1.2
    variant = preview_entry(base, True, org, SPEAKERS, "特定の発言1", None, None)
    assert variant["speaker"] == 3 and variant["speed"] == 1.5
    with pytest.raises(ValueError, match="action"):
        preview_entry(base, True, org, SPEAKERS, "特定の発言2", None, None)
    with pytest.raises(ValueError):
        preview_entry((None, None, None, None), True, _org_values(), SPEAKERS, "この組織", None, None)


def test_silent_choice_saves_engine_none_and_is_not_previewable():
    assert talent_voice_from_fields((voice_mapping_ui.SILENT_CHOICE, 1.1, None, None), SPEAKERS, None) == {"engine": "none"}
    updates = base_updates({"engine": "none"}, SPEAKERS)
    assert updates[0]["value"] == voice_mapping_ui.SILENT_CHOICE and updates[0]["choices"][0] == ("（音なし）", "none")
    with pytest.raises(ValueError, match=NO_VOICE_NOTE[:6]):
        preview_entry((voice_mapping_ui.SILENT_CHOICE, None, None, None), True, _org_values(), SPEAKERS, "人材の既定", None, None)


def test_save_talent_voice_accepts_silent_engine(tmp_path):
    make_org(tmp_path, ["a"])
    save_talent_voice(tmp_path, "a", {"engine": "none"})
    assert read_talent_voice(tmp_path, "a") == {"engine": "none"}


def test_scale_fields_step_within_the_valid_range():
    for key, step in (("speed", 0.05), ("pitch", 0.01), ("intonation", 0.05)):
        field = voice_mapping_ui._scale_field(key, key)
        low, high = voice_mapping.SCALE_RANGES[key]
        assert (field.minimum, field.maximum, field.step) == (low, high, step)
        assert 0 < step <= (high - low) / 10  # 既定の 1 だと、高さは 1 回で範囲外になっていた


def test_describe_voice_shows_character_and_settings():
    assert voice_mapping_ui.describe_voice({"speaker": 2, "label": "四国めたん", "speed": 1.1, "pitch": 0}) == "四国めたん（speaker 2、速さ 1.1、高さ 0）"
    assert voice_mapping_ui.describe_voice({"speaker": 99}) == "speaker 99"

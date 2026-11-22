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
    build_variant,
    fetch_speakers,
    preview_wav,
    read_voice_mapping_raw,
    save_voice_mapping,
    shared_speakers,
    validate_entry,
)
from studio.voice_mapping_ui import (
    INHERIT,
    entry_from_fields,
    field_updates,
    overview_markdown,
    save_entry,
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
        {"label": "x"},
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


def test_overview_markdown_lists_talents_and_warns_about_shared_speakers(tmp_path):
    make_org(tmp_path, ["a", "b", "c"], {"a": {"label": "四国めたん", "speaker": 2, "speed": 1.2}, "b": {"speaker": 2, "variants": [{"when_action": "x"}]}})
    text = overview_markdown(tmp_path, "org", voice_mapping_ui.read_voice_mapping_raw(tmp_path, "org"))
    assert "名前a (`a`) | 四国めたん | 2 | 1.2" in text
    assert "名前c (`c`) | —（読み上げない）" in text
    assert "speaker 2 が重なっています: a, b" in text
    assert overview_markdown(tmp_path, None, {}) == "組織を選んでください。"


def test_field_updates_fills_base_and_variant_rows():
    entry = {"speaker": 2, "speed": 1.2, "when_action": "放送後", "variants": [{"when_action": "判定", "speaker": 3, "pitch": 0.1}]}
    updates = field_updates(entry, SPEAKERS)
    assert len(updates) == 6 + 3 * 5
    assert updates[0] is True and updates[2] == 1.2 and updates[5] == "放送後"
    assert updates[6] == "判定" and updates[8] is None and updates[9] == 0.1
    assert updates[11] == "" and field_updates(None, SPEAKERS)[0] is False


def _values(speaker=2, speed=None, pitch=None, intonation=None, when="", rows=None):
    rows = rows or []
    flat: list = []
    for index in range(3):
        flat += list(rows[index]) if index < len(rows) else ["", INHERIT, None, None, None]
    return (speaker, speed, pitch, intonation, when, *flat)


def test_entry_from_fields_takes_character_name_and_variant_overrides():
    values = _values(2, 1.1, when="", rows=[("判定", 3, 1.3, None, None), ("", INHERIT, None, None, None), ("速報", INHERIT, 1.5, None, None)])
    entry = entry_from_fields(values, SPEAKERS, None)
    assert entry == {
        "label": "四国めたん",
        "speaker": 2,
        "speed": 1.1,
        "variants": [
            {"when_action": "判定", "label": "ずんだもん", "speaker": 3, "speed": 1.3},
            {"when_action": "速報", "speed": 1.5},
        ],
    }
    with pytest.raises(ValueError):
        entry_from_fields(_values(None), SPEAKERS, None)


def test_entry_from_fields_keeps_previous_label_for_unknown_speaker_and_extra_variants():
    previous = {"label": "旧キャラ", "speaker": 99, "variants": [{"when_action": "a"}, {"when_action": "b"}, {"when_action": "c"}, {"when_action": "d", "speed": 1.1}]}
    entry = entry_from_fields(_values(99), SPEAKERS, previous)
    assert entry["label"] == "旧キャラ"
    assert entry["variants"] == [{"when_action": "d", "speed": 1.1}]  # 画面の 3 行は空に消され、4 件目以降だけ残る


def test_save_entry_updates_one_talent_keeps_order_and_user(tmp_path):
    make_org(tmp_path, ["a", "b"], {"user": {"speaker": 8}, "b": {"speaker": 3}})
    mapping = read_voice_mapping_raw(tmp_path, "org")
    updated = save_entry(tmp_path, "org", "a", mapping, True, _values(2, 1.2), SPEAKERS)
    assert list(updated) == ["a", "b", "user"]
    saved = json.loads((tmp_path / "organizations" / "org" / "voice_mapping.json").read_text(encoding="utf-8"))
    assert saved["a"] == {"label": "四国めたん", "speaker": 2, "speed": 1.2} and saved["user"] == {"speaker": 8}
    removed = save_entry(tmp_path, "org", "b", updated, False, _values(3), SPEAKERS)
    assert "b" not in removed and "b" not in json.loads((tmp_path / "organizations" / "org" / "voice_mapping.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        save_entry(tmp_path, "org", "a", removed, True, _values(2, 9.9), SPEAKERS)

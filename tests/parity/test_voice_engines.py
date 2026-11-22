"""VOICEVOX ENGINE の登録名・IPv4 優先の解決。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio import voice_engines
from studio.voice_engines import (
    ENGINES_FILE,
    EngineConfigError,
    engine_names_by_url,
    expand_engine_spec,
    load_engines,
    prefer_ipv4,
)

FALLBACK = "http://127.0.0.1:50021"


def write_engines(root: Path, engines: list[dict]) -> None:
    (root / ENGINES_FILE).write_text(json.dumps({"engines": engines}), encoding="utf-8")


@pytest.fixture(autouse=True)
def clear_resolve_cache():
    voice_engines._resolved.clear()
    yield
    voice_engines._resolved.clear()


def test_load_engines_missing_file_is_empty(tmp_path):
    assert load_engines(tmp_path) == []


def test_load_engines_applies_defaults_and_strips_slash(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:50021/"}])
    (engine,) = load_engines(tmp_path)
    assert (engine.name, engine.url, engine.device, engine.parallel, engine.enabled) == (
        "a",
        "http://a:50021",
        "cpu",
        1,
        True,
    )


@pytest.mark.parametrize(
    "engine",
    [
        {"name": "a,b", "url": "http://a:50021"},
        {"name": "a b", "url": "http://a:50021"},
        {"name": "a", "url": "a:50021"},
        {"name": "a", "url": "http://a:50021", "device": "tpu"},
        {"name": "a", "url": "http://a:50021", "parallel": 0},
        {"name": "a", "url": "http://a:50021", "unknown": 1},
    ],
)
def test_load_engines_rejects_invalid_entry(tmp_path, engine):
    write_engines(tmp_path, [engine])
    with pytest.raises(EngineConfigError):
        load_engines(tmp_path)


def test_load_engines_rejects_duplicate_names_ignoring_case(tmp_path):
    write_engines(tmp_path, [{"name": "A", "url": "http://a:1"}, {"name": "a", "url": "http://b:1"}])
    with pytest.raises(EngineConfigError, match="重複"):
        load_engines(tmp_path)


def test_load_engines_rejects_broken_json(tmp_path):
    (tmp_path / ENGINES_FILE).write_text("{", encoding="utf-8")
    with pytest.raises(EngineConfigError):
        load_engines(tmp_path)


def test_expand_unspecified_uses_enabled_engines_only(tmp_path):
    write_engines(
        tmp_path,
        [
            {"name": "a", "url": "http://a:1"},
            {"name": "b", "url": "http://b:1", "enabled": False},
            {"name": "c", "url": "http://c:1"},
        ],
    )
    assert expand_engine_spec(None, tmp_path, FALLBACK) == "http://a:1,http://c:1"


def test_expand_unspecified_without_file_uses_fallback(tmp_path):
    assert expand_engine_spec(None, tmp_path, FALLBACK) == FALLBACK
    assert expand_engine_spec("  ", tmp_path, FALLBACK) == FALLBACK


def test_expand_all_disabled_uses_fallback(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1", "enabled": False}])
    assert expand_engine_spec(None, tmp_path, FALLBACK) == FALLBACK


def test_expand_names_and_urls_mixed_even_when_disabled(tmp_path):
    write_engines(tmp_path, [{"name": "Off", "url": "http://off:1", "enabled": False}])
    assert expand_engine_spec("off, http://x:2 ,", tmp_path, FALLBACK) == "http://off:1,http://x:2"


def test_expand_unknown_name_is_error(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1"}])
    with pytest.raises(EngineConfigError, match="見つかりません"):
        expand_engine_spec("zzz", tmp_path, FALLBACK)


def test_engine_names_by_url_includes_ipv4_form(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_engines, "_resolve_ipv4", lambda host: "10.0.0.5")
    write_engines(tmp_path, [{"name": "pc", "url": "http://pc.local:50021"}])
    names = engine_names_by_url(tmp_path)
    assert names["http://pc.local:50021"] == "pc"
    assert names["http://10.0.0.5:50021"] == "pc"


def test_engine_names_by_url_tolerates_bad_file(tmp_path):
    (tmp_path / ENGINES_FILE).write_text("{", encoding="utf-8")
    assert engine_names_by_url(tmp_path) == {}
    assert engine_names_by_url(None) == {}


def test_timeline_records_engine_name(tmp_path, monkeypatch):
    from studio import voice
    from studio.engine import EngineEvent
    from studio.session_report import read_jsonl
    from studio.voice import VoiceReader

    monkeypatch.setattr(voice_engines, "_resolve_ipv4", lambda host: None)
    write_engines(tmp_path, [{"name": "pc-a", "url": "http://e1:50021"}])
    wav = voice.io.BytesIO()
    with voice.wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x01\x00")
    monkeypatch.setattr(voice, "synthesize", lambda text, entry, base_url=voice.DEFAULT_BASE_URL: wav.getvalue())
    monkeypatch.setattr(voice, "split_for_speech", lambda text: [text])
    reader = VoiceReader(
        tmp_path, {"a": {"speaker": 1}}, play=False, base_url=["http://e1:50021", "http://other:50021"]
    )
    reader.handle(EngineEvent("session_start", {"session_id": "nm"}))
    reader.handle(EngineEvent("step_done", {"talent_id": "a", "text": "hello"}))
    reader.close()

    records = read_jsonl(tmp_path / "sessions" / "audio" / "nm" / "timeline.jsonl")
    for kind in ("synth_start", "synth"):
        record = next(r for r in records if r["kind"] == kind)
        if record["engine"] == "http://e1:50021":
            assert record["engine_name"] == "pc-a"
        else:
            assert "engine_name" not in record


def test_prefer_ipv4_replaces_host_and_keeps_path(monkeypatch):
    monkeypatch.setattr(voice_engines, "_resolve_ipv4", lambda host: "192.168.1.5")
    assert prefer_ipv4("http://pc.local:50021/audio_query?text=a") == "http://192.168.1.5:50021/audio_query?text=a"
    assert prefer_ipv4("http://pc.local") == "http://192.168.1.5"


def test_prefer_ipv4_leaves_ip_literals_and_unresolved_hosts(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(voice_engines, "_resolve_ipv4", lambda host: calls.append(host) or None)
    assert prefer_ipv4("http://127.0.0.1:50021") == "http://127.0.0.1:50021"
    assert prefer_ipv4("http://[::1]:50021") == "http://[::1]:50021"
    assert calls == []
    assert prefer_ipv4("http://nohost:50021") == "http://nohost:50021"
    assert calls == ["nohost"]


def test_resolve_ipv4_caches_within_ttl(monkeypatch):
    calls: list[str] = []

    def fake_getaddrinfo(host, port, family, type_):
        calls.append(host)
        return [(family, type_, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(voice_engines.socket, "getaddrinfo", fake_getaddrinfo)
    assert voice_engines._resolve_ipv4("pc.local") == "10.1.2.3"
    assert voice_engines._resolve_ipv4("pc.local") == "10.1.2.3"
    assert calls == ["pc.local"]


def test_resolve_ipv4_failure_returns_none(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("no such host")

    monkeypatch.setattr(voice_engines.socket, "getaddrinfo", fail)
    assert voice_engines._resolve_ipv4("nohost") is None


def test_former_urls_map_to_current_name_and_current_url_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_engines, "_resolve_ipv4", lambda host: None)
    write_engines(
        tmp_path,
        [
            {"name": "new", "url": "http://10.0.0.2:1", "former_urls": ["http://10.0.0.1:1/", "http://10.0.0.9:1"]},
            {"name": "other", "url": "http://10.0.0.9:1"},
        ],
    )
    assert load_engines(tmp_path)[0].former_urls == ("http://10.0.0.1:1", "http://10.0.0.9:1")
    names = engine_names_by_url(tmp_path)
    assert names["http://10.0.0.1:1"] == "new"
    assert names["http://10.0.0.9:1"] == "other"


def test_load_engines_rejects_bad_former_url(tmp_path):
    write_engines(tmp_path, [{"name": "a", "url": "http://a:1", "former_urls": ["a:1"]}])
    with pytest.raises(EngineConfigError):
        load_engines(tmp_path)

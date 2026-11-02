"""読みチェック（studio/voice_check.py）のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from studio import voice, voice_check


def _setup(tmp_path: Path) -> None:
    org = tmp_path / "organizations" / "demo"
    org.mkdir(parents=True)
    (org / "voice_mapping.json").write_text(
        json.dumps({"akari": {"speaker": 14}, "midori": {"speaker": 2, "when_action": "放送後"}}), encoding="utf-8"
    )
    (tmp_path / "voice_dictionary.json").write_text(json.dumps({"Pi": "パイ"}), encoding="utf-8")
    (org / "voice_dictionary.json").write_text(json.dumps({"Pi": "ピー"}), encoding="utf-8")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    rows = [
        {"type": "session_meta", "organization": "demo"},
        {"type": "step", "talent_id": "midori", "action": "放送前", "text": "リサーチメモ"},
        {"type": "step", "talent_id": "midori", "action": "放送後。点検", "text": "点検です。"},
        {"type": "step", "talent_id": "akari", "action": "司会", "text": "**Pi** です。次です。"},
        {"type": "step", "talent_id": "unknown", "action": "x", "text": "読まない"},
    ]
    (sessions / "s1.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_spoken_chunks_follow_voice_reader_rules(tmp_path: Path):
    _setup(tmp_path)
    chunks, org = voice_check.spoken_chunks(tmp_path, "s1")
    assert org == "demo"
    # 放送前の midori・マッピング外の人材は読まず、組織辞書が共通辞書に優先する
    assert chunks == [("midori", 2, "点検です。"), ("akari", 14, "ピー です。次です。")]


def test_reading_of_joins_moras(monkeypatch):
    query = {"accent_phrases": [{"moras": [{"text": "コ"}, {"text": "ン"}]}, {"moras": [{"text": "ニ"}]}]}
    monkeypatch.setattr(voice_check, "_post", lambda url, data=None, *, timeout: json.dumps(query).encode())
    assert voice_check.reading_of("こんに", 2) == "コンニ"


def test_pending_dictionary_has_lowest_priority(tmp_path: Path):
    _setup(tmp_path)
    pending = {"pending": {"Pi": {"reading": "ペー"}, "Nvidia": {"reading": "エヌビディア"}}, "rejected": ["x"]}
    (tmp_path / "organizations" / "demo" / "voice_dictionary.pending.json").write_text(
        json.dumps(pending), encoding="utf-8"
    )
    assert voice.load_voice_dictionary(tmp_path, "demo") == {"Pi": "ピー", "Nvidia": "エヌビディア"}


def test_parse_suggestions_tolerates_fences_and_garbage():
    text = '```json\n{"suggestions": [{"surface": "Nvidia", "reading": "エヌビディア"}, {"surface": 1}]}\n```'
    assert voice_check.parse_suggestions(text) == [("Nvidia", "エヌビディア")]
    assert voice_check.parse_suggestions("なし") == []


def test_filter_suggestions_guards_dictionary():
    texts = ["Nvidia のGPUです。", "Pi は Pizza と違う。Pizza は食べ物。", "ab は短い。", "WebGL と WebGLX。"]
    found = [
        ("Nvidia", "エヌビディア"),
        ("Nvidia", "ニビディア"),  # 重複
        ("Pizza", "ピザ"),
        ("Pi", "パイ"),  # 短すぎ
        ("Web", "ウェブ"),  # 他の語の一部
        ("WebGL", "ウェブジーエル"),  # WebGLX の一部にもなる
        ("GPU", "ジーピーユー"),
        ("Known", "ノウン"),
        ("Ghost", "ゴースト"),  # 文に無い
        ("Bad", "bad"),  # カナでない
    ]
    kept = voice_check.filter_suggestions(found, texts, known={"GPU"})
    assert kept == [("Nvidia", "エヌビディア"), ("Pizza", "ピザ")]


def test_save_pending_keeps_rejected(tmp_path: Path):
    _setup(tmp_path)
    path = tmp_path / "organizations" / "demo" / "voice_dictionary.pending.json"
    path.write_text(json.dumps({"pending": {}, "rejected": ["Foo"]}), encoding="utf-8")
    voice_check.save_pending(tmp_path, "demo", [("Nvidia", "エヌビディア")], "s1")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rejected"] == ["Foo"]
    assert data["pending"]["Nvidia"]["reading"] == "エヌビディア"
    assert data["pending"]["Nvidia"]["session"] == "s1"


def test_adopt_and_reject_pending(tmp_path: Path):
    _setup(tmp_path)
    voice_check.save_pending(tmp_path, "demo", [("Nvidia", "エヌビディア"), ("Foo", "フー"), ("Bar", "バー")], "s1")
    assert voice_check.session_org(tmp_path, "s1") == "demo"
    assert voice_check.adopt_pending(tmp_path, "demo", ["Nvidia", "Missing"]) == ["Nvidia"]
    assert voice_check.reject_pending(tmp_path, "demo", ["Foo"]) == ["Foo"]

    org_dict = json.loads((tmp_path / "organizations" / "demo" / "voice_dictionary.json").read_text(encoding="utf-8"))
    assert org_dict == {"Pi": "ピー", "Nvidia": "エヌビディア"}
    assert voice_check.list_pending(tmp_path, "demo") == [("Bar", "バー", False)]
    pending = json.loads((tmp_path / "organizations" / "demo" / "voice_dictionary.pending.json").read_text(encoding="utf-8"))
    assert pending["rejected"] == ["Foo"]


def test_suggest_for_session_saves_filtered_entries(tmp_path: Path, monkeypatch):
    _setup(tmp_path)
    rows = [
        {"type": "session_meta", "organization": "demo"},
        {"type": "step", "talent_id": "akari", "action": "司会", "text": "Nvidia の話です。"},
    ]
    (tmp_path / "sessions" / "s2.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    monkeypatch.setattr(voice_check, "engine_available", lambda url: True)
    monkeypatch.setattr(voice_check, "reading_of", lambda text, speaker, base_url: "ヌビディア")
    monkeypatch.setattr(
        voice_check, "ask_llm", lambda root, assistant, model, items: [("Nvidia", "エヌビディア"), ("Ghost", "ゴースト")]
    )
    org, label, entries = voice_check.suggest_for_session(tmp_path, "s2", urls=["http://x"], model_override="A/m")
    assert (org, label, entries) == ("demo", "A/m", [("Nvidia", "エヌビディア")])
    assert voice_check.list_pending(tmp_path, "demo") == [("Nvidia", "エヌビディア", False)]


def test_filter_suggestions_accepts_kanji_and_symbols_but_not_noise():
    texts = ["過半数未達が続き、A+B を足す。"]
    found = [
        ("未達", "ミタツ"),
        ("+", "プラス"),
        ("ラズベリーパイ", "ラズベリーパイ"),  # カナだけ・読みが同じ
        ("過半数", "カハンスウ"),  # 誤読ではない候補でも、表記が文中に在れば残る（人が承認で弾く）
    ]
    kept = voice_check.filter_suggestions(found, texts, known=set())
    assert ("未達", "ミタツ") in kept and ("+", "プラス") in kept
    assert all(surface != "ラズベリーパイ" for surface, _ in kept)


def test_needs_review_entries_are_not_applied_until_adopted(tmp_path: Path):
    _setup(tmp_path)
    voice_check.save_pending(tmp_path, "demo", [("未達", "ミタツ"), ("Nvidia", "エヌビディア")], "s1")
    assert voice_check.list_pending(tmp_path, "demo") == [("未達", "ミタツ", True), ("Nvidia", "エヌビディア", False)]
    applied = voice.load_voice_dictionary(tmp_path, "demo")
    assert "未達" not in applied and applied["Nvidia"] == "エヌビディア"

    voice_check.adopt_pending(tmp_path, "demo", ["未達"])
    assert voice.load_voice_dictionary(tmp_path, "demo")["未達"] == "ミタツ"


def test_normalize_reading_aligns_long_vowels():
    assert voice_check.normalize_reading("セイフケイセイ") == voice_check.normalize_reading("セエフケエセエ")
    assert voice_check.normalize_reading("ラズベリーパイ") == "ラズベリイパイ"
    assert voice_check.normalize_reading("ミタ ツ") == "ミタツ"


def test_filter_drops_candidates_already_read_correctly():
    texts = ["政府形成で未達です。"]
    found = [("政府形成", "セイフケイセイ"), ("未達", "ミタツ")]
    engine = ["セエフケエセエデヒツジタチデス"]
    assert voice_check.filter_suggestions(found, texts, set(), engine) == [("未達", "ミタツ")]

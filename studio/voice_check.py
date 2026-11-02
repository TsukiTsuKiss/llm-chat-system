"""保存済みセッションの読み上げ文を VOICEVOX の /audio_query に通し、読み（カナ）を一覧する（design.md §7.9.2）。

--suggest は、LLM が誤読の候補を未承認辞書（voice_dictionary.pending.json）へ追記する。本登録は人が行う。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from studio.voice import (
    DEFAULT_BASE_URL,
    PENDING_DICTIONARY_FILE,
    VOICE_DICTIONARY_FILE,
    _post,
    apply_dictionary,
    clean_for_speech,
    engine_available,
    load_voice_dictionary,
    load_voice_mapping,
    parse_voicevox_urls,
    read_pending_dictionary,
    split_for_speech,
)

_LATIN = re.compile(r"[A-Za-z]")
_KATAKANA = re.compile(r"^[ァ-ヶー・ ]+$")
_KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヶー・ ]+$")
_SUGGESTION_PAIR = re.compile(r'"surface"\s*:\s*"([^"]+)"\s*,\s*"reading"\s*:\s*"([^"]+)"')
# studio_config に voice_suggest が無いときの候補生成モデル（速さ重視）
DEFAULT_SUGGEST = {"assistant": "Groq", "model": "openai/gpt-oss-120b"}
MIN_SURFACE_LENGTH = 3
SUGGEST_BATCH = 2


def reading_of(text: str, speaker: int, base_url: str = DEFAULT_BASE_URL) -> str:
    """ENGINE が出す読み（カナ）。合成はしない。"""
    query = json.loads(
        _post(f"{base_url}/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": speaker}), timeout=30)
    )
    return "".join(m["text"] for phrase in query["accent_phrases"] for m in phrase["moras"])


def spoken_chunks(
    root: Path, session_id: str, org_id: str | None = None
) -> tuple[list[tuple[str, int, str]], str]:
    """実際に読み上げる文を (talent_id, speaker, 文) で返す。読み上げ対象・辞書は VoiceReader と同じ規則。"""
    path = root / "sessions" / f"{session_id}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"セッションがありません: {path}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    org = org_id or next((r.get("organization") for r in records if r.get("type") == "session_meta"), None)
    if not org:
        raise ValueError("組織 ID を特定できません（--org で指定してください）")
    mapping = load_voice_mapping(root, org)
    dictionary = load_voice_dictionary(root, org)
    chunks: list[tuple[str, int, str]] = []
    for record in records:
        if record.get("type") != "step":
            continue
        entry: dict[str, Any] | None = mapping.get(record.get("talent_id", ""))
        if entry is None:
            continue
        when_action = entry.get("when_action")
        if when_action and when_action not in (record.get("action") or ""):
            continue
        text = apply_dictionary(clean_for_speech(record.get("text", ""), strip_backstage=not when_action), dictionary)
        chunks.extend((record["talent_id"], entry["speaker"], c) for c in split_for_speech(text))
    return chunks, org


def parse_suggestions(text: str) -> list[tuple[str, str]]:
    """LLM の出力から (表記, 読み) を取り出す。長い応答が途中で切れて JSON として壊れていても、対の形を拾う。"""
    return [
        (surface.strip(), re.sub(r"\s+", "", reading))
        for surface, reading in _SUGGESTION_PAIR.findall(text or "")
    ]


_VOWELS = {
    "ア": "アカガサザタダナハバパマヤラワァャヮ",
    "イ": "イキギシジチヂニヒビピミリィ",
    "ウ": "ウクグスズツヅヌフブプムユルゥュヴ",
    "エ": "エケゲセゼテデネヘベペメレェ",
    "オ": "オコゴソゾトドノホボポモヨロヲォョ",
}
_VOWEL_OF = {ch: vowel for vowel, chars in _VOWELS.items() for ch in chars}
_E_LONG = re.compile("([" + _VOWELS["エ"] + "])イ")
_O_LONG = re.compile("([" + _VOWELS["オ"] + "])ウ")


def normalize_reading(kana: str) -> str:
    """長音の書き方（ー / ウ / オオ、イ / エエ）を ENGINE の表記（母音の重ね）に揃える。"""
    out: list[str] = []
    for ch in re.sub(r"[ 　・]", "", kana):
        out.append(_VOWEL_OF.get(out[-1], "ー") if ch == "ー" and out else ch)
    return _O_LONG.sub(r"\1オ", _E_LONG.sub(r"\1エ", "".join(out)))


def needs_review(surface: str) -> bool:
    """英字を含まない表記（漢字・記号）は境界を判定できず他の語を壊しうるので、承認するまで読み上げに適用しない。"""
    return not _LATIN.search(surface)


def filter_suggestions(
    suggestions: list[tuple[str, str]],
    texts: list[str],
    known: set[str],
    engine_readings: list[str] | None = None,
) -> list[tuple[str, str]]:
    """読み上げ文に実在し、既知・却下済みでなく、誤読でも他の語を壊すものでもないものだけ残す。"""
    body = "\n".join(texts)
    engine = "\n".join(normalize_reading(r) for r in engine_readings or [])
    kept: dict[str, str] = {}
    for surface, reading in suggestions:
        if not surface or surface in known or surface in kept or surface == reading:
            continue
        # カナだけの表記は、辞書適用後の文字列や助詞を壊すので出さない
        if _KANA_ONLY.match(surface) or not _KATAKANA.match(reading):
            continue
        # ENGINE の読みにすでに含まれる（長音の書き方の違いだけの）候補は誤読ではない
        if engine and normalize_reading(reading) in engine:
            continue
        if surface not in body:
            continue
        if not needs_review(surface):
            if len(surface) < MIN_SURFACE_LENGTH:
                continue
            whole = re.findall(rf"(?<![A-Za-z0-9]){re.escape(surface)}(?![A-Za-z0-9])", body)
            # 他の語の一部としても出る表記は、部分一致で壊すので出さない
            if len(whole) != body.count(surface):
                continue
        kept[surface] = reading
    return list(kept.items())


_SYSTEM_PROMPT = (
    "あなたは日本語の読み上げ音声（VOICEVOX）の誤読を点検する校正者です。"
    "各項目は「文」（読み上げ文）と、音声合成エンジンが出した「読み」（カナ）です。"
    "文中の語句や記号のうち、読みが自然な日本語の読み方と明らかに違うものだけを選びます。"
    "例: 「未達」が「ヒツジタチ」、「+」が「タス」、「一眼」が「イチメ」、「Nvidia」が「ヌビディア」"
    "（正しくは「ミタツ」「プラス」「イチガン」「エヌビディア」）。"
    "表記は誤読している語そのものだけにし、助詞・活用語尾・前後の語を含めないでください（「一眼でも」ではなく「一眼」）。"
    "表記は文中にあるとおり（綴り・漢字・記号をそのまま）、読みは正しいカタカナで返してください。"
    "カナだけで書かれた語を表記にしないでください。読みが妥当なもの・自信がないものは含めず、誤読がなければ空にしてください。"
    "「読み」は長音を「オオ」「ウウ」のように母音の重ねで表すので、長音の表記の違いは誤りとみなさず、音そのものが違う場合だけ選びます。"
    "「日本」の「ニッポン」と「ニホン」のようにどちらも通用する読みや、アクセントの違いは選ばないでください。"
    '出力は JSON のみ: {"suggestions": [{"surface": "表記", "reading": "カタカナ"}]}。なければ {"suggestions": []}。'
)


def suggest_model(root: Path, override: str | None) -> tuple[str, str]:
    if override:
        assistant, _, model = override.partition("/")
        if not assistant or not model:
            raise ValueError("--suggest-model は Assistant/モデル名 の形式で指定してください")
        return assistant, model
    from studio.loader import load_studio_config

    cfg = load_studio_config(root).get("voice_suggest") or {}
    return cfg.get("assistant", DEFAULT_SUGGEST["assistant"]), cfg.get("model", DEFAULT_SUGGEST["model"])


def ask_llm(root: Path, assistant: str, model: str, items: list[str]) -> list[tuple[str, str]]:
    from studio.assistants import invoke_llm_step
    from studio.history import ConversationHistory
    from studio.loader import load_ai_assistants
    from studio.logging import load_model_costs
    from studio.validation import ValidationReport

    assistants = load_ai_assistants(root, ValidationReport())
    if assistant not in assistants:
        raise ValueError(f"'{assistant}' は ai_assistants_config.json にありません")
    costs = load_model_costs(root)

    def ask(batch: list[str]) -> list[tuple[str, str]]:
        result = invoke_llm_step(
            assistant_name=assistant,
            assistant_cfg=assistants[assistant],
            model=model,
            system_prompt=_SYSTEM_PROMPT,
            user_message="\n\n".join(batch),
            history=ConversationHistory(),
            temperature=0.0,
            stream=False,
            costs=costs,
        )
        # 空応答は「候補なし」と区別できないので、分割して再試行し、1件でも駄目なら失敗にする
        if '"suggestions"' in (result.text or ""):
            return parse_suggestions(result.text)
        if len(batch) == 1:
            raise ValueError(f"{assistant}/{model} が有効な応答を返しませんでした")
        mid = len(batch) // 2
        return ask(batch[:mid]) + ask(batch[mid:])

    found: list[tuple[str, str]] = []
    for start in range(0, len(items), SUGGEST_BATCH):
        found.extend(ask(items[start : start + SUGGEST_BATCH]))
    return found


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pending_path(root: Path, org: str) -> Path:
    return root / "organizations" / org / PENDING_DICTIONARY_FILE


def save_pending(root: Path, org: str, entries: list[tuple[str, str]], session_id: str) -> Path:
    path = pending_path(root, org)
    data = read_pending_dictionary(path)
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for surface, reading in entries:
        record: dict[str, Any] = {"reading": reading, "session": session_id, "added": stamp}
        if needs_review(surface):
            record["needs_review"] = True
        data["pending"][surface] = record
    _write_json(path, data)
    return path


def list_pending(root: Path, org: str) -> list[tuple[str, str, bool]]:
    """未承認辞書の (表記, 読み, 要確認)。要確認は承認するまで読み上げに適用されない。"""
    items = []
    for surface, entry in read_pending_dictionary(pending_path(root, org))["pending"].items():
        reading = entry.get("reading") if isinstance(entry, dict) else entry
        if isinstance(reading, str) and reading:
            items.append((surface, reading, isinstance(entry, dict) and bool(entry.get("needs_review"))))
    return items


def adopt_pending(root: Path, org: str, surfaces: list[str]) -> list[str]:
    """選んだ候補を組織辞書へ本登録し、未承認辞書から外す。本登録した表記を返す。"""
    readings = {surface: reading for surface, reading, _ in list_pending(root, org)}
    chosen = [s for s in surfaces if s in readings]
    if not chosen:
        return []
    dict_path = root / "organizations" / org / VOICE_DICTIONARY_FILE
    registered: dict[str, Any] = json.loads(dict_path.read_text(encoding="utf-8")) if dict_path.is_file() else {}
    for surface in chosen:
        registered[surface] = readings[surface]
    _write_json(dict_path, registered)
    path = pending_path(root, org)
    data = read_pending_dictionary(path)
    for surface in chosen:
        data["pending"].pop(surface, None)
    _write_json(path, data)
    return chosen


def reject_pending(root: Path, org: str, surfaces: list[str]) -> list[str]:
    """選んだ候補を未承認辞書から外し、再提案されないよう rejected に記録する。"""
    path = pending_path(root, org)
    data = read_pending_dictionary(path)
    chosen = [s for s in surfaces if s in data["pending"]]
    for surface in chosen:
        data["pending"].pop(surface)
        if surface not in data["rejected"]:
            data["rejected"].append(surface)
    if chosen:
        _write_json(path, data)
    return chosen


def session_org(root: Path, session_id: str) -> str | None:
    path = root / "sessions" / f"{session_id}.jsonl"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and (record := json.loads(line)).get("type") == "session_meta":
            return record.get("organization") or None
    return None


def suggest_for_session(
    root: Path,
    session_id: str,
    *,
    urls: list[str],
    org_id: str | None = None,
    model_override: str | None = None,
) -> tuple[str, str, list[tuple[str, str]]]:
    """誤読候補を作って未承認辞書へ追記する。(組織 ID, モデル表示, 追記した候補)。

    セッション無し・設定不備は FileNotFoundError / ValueError、ENGINE に繋がらないときは ConnectionError。
    """
    chunks, org = spoken_chunks(root, session_id, org_id)
    base_url = next((u for u in urls if engine_available(u)), None)
    if base_url is None:
        raise ConnectionError(f"VOICEVOX ({', '.join(urls)}) に接続できません")
    readings = [reading_of(chunk, speaker, base_url) for _talent, speaker, chunk in chunks]
    items = [f"文: {chunk}\n読み: {kana}" for (_t, _s, chunk), kana in zip(chunks, readings)]
    assistant, model = suggest_model(root, model_override)
    found = ask_llm(root, assistant, model, items) if items else []
    known = set(load_voice_dictionary(root, org)) | set(read_pending_dictionary(pending_path(root, org))["rejected"])
    entries = filter_suggestions(found, [c for _, _, c in chunks], known, readings)
    if entries:
        save_pending(root, org, entries, session_id)
    return org, f"{assistant}/{model}", entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="読み上げ文の読み（カナ）を VOICEVOX で点検する")
    parser.add_argument("session_id", help="セッション ID")
    parser.add_argument("--org", default=None, help="組織 ID（省略時はセッションの記録から）")
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    parser.add_argument("--voicevox-url", default=DEFAULT_BASE_URL, help="VOICEVOX ENGINE の URL（カンマ区切りなら先頭）")
    parser.add_argument("--ascii-only", action="store_true", help="英字を含む文だけを出す（誤読しやすい）")
    parser.add_argument("--suggest", action="store_true", help="LLM が誤読候補を未承認辞書へ追記する")
    parser.add_argument(
        "--suggest-model", default=None, help="候補生成のモデル（Assistant/モデル名。既定は studio_config の voice_suggest）"
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        chunks, org = spoken_chunks(root, args.session_id, args.org)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    urls = parse_voicevox_urls(args.voicevox_url)
    base_url = next((u for u in urls if engine_available(u)), None)
    if base_url is None:
        print(f"VOICEVOX ({args.voicevox_url}) に接続できません", file=sys.stderr)
        return 1
    if args.suggest:
        try:
            _, model_label, entries = suggest_for_session(
                root, args.session_id, urls=urls, org_id=org, model_override=args.suggest_model
            )
        except (ValueError, ConnectionError) as exc:
            print(exc, file=sys.stderr)
            return 1
        if not entries:
            print(f"候補はありません（{model_label}）")
            return 0
        path = pending_path(root, org)
        print(f"{path.relative_to(root).as_posix()} に {len(entries)} 件追記しました（{model_label}）")
        for surface, reading in entries:
            print(f"  {surface} → {reading}")
        return 0

    for talent_id, speaker, chunk in chunks:
        if args.ascii_only and not _LATIN.search(chunk):
            continue
        try:
            kana = reading_of(chunk, speaker, base_url)
        except (urllib.error.URLError, OSError) as exc:
            print(f"[{talent_id}] 読みを取得できません: {exc}", file=sys.stderr)
            return 1
        print(f"[{talent_id}] {chunk}\n    → {kana}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

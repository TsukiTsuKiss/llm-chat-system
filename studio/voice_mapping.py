"""声のマッピング（organizations/<組織>/voice_mapping.json）の読み書き・検証・試聴。UI は voice_mapping_ui.py。"""

from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio.bindings_form import load_binding_slot_specs
from studio.config_store import load_config, save_config
from studio.voice import USER_VOICE_ID, VOICE_MAPPING_FILES, VOICE_ROLES_KEY, synthesize
from studio.voice_engines import prefer_ipv4

VOICE_MAPPING_FILE = VOICE_MAPPING_FILES[0]
PREVIEW_TEXT = "こんにちは。これは声の試聴です。速さや高さを変えると、聞こえ方が変わります。"
# VOICEVOX が受け付ける範囲
SCALE_RANGES = {"speed": (0.5, 2.0), "pitch": (-0.15, 0.15), "intonation": (0.0, 2.0)}
_ENTRY_KEYS = {"label", "speaker", "when_action", "variants", "read", *SCALE_RANGES}
_VARIANT_KEYS = {"when_action", "label", "speaker", *SCALE_RANGES}
_SPEAKERS_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class SpeakerStyle:
    character: str
    style: str
    speaker_id: int

    @property
    def display(self) -> str:
        return f"{self.character}（{self.style}） #{self.speaker_id}"


_speakers_cache: tuple[float, list[SpeakerStyle]] | None = None


def fetch_speakers(urls: Sequence[str]) -> list[SpeakerStyle]:
    """最初に応答した ENGINE の /speakers から、キャラ・スタイルの一覧を作る。取れなければ空。"""
    global _speakers_cache
    now = time.monotonic()
    if _speakers_cache is not None and _speakers_cache[0] > now:
        return _speakers_cache[1]
    for url in urls:
        try:
            with urllib.request.urlopen(f"{prefer_ipv4(url)}/speakers", timeout=5) as response:
                data = json.loads(response.read())
        except (OSError, ValueError):
            continue
        styles = [
            SpeakerStyle(str(item.get("name", "")), str(style.get("name", "")), int(style["id"]))
            for item in data
            for style in item.get("styles", [])
            if isinstance(style.get("id"), int)
        ]
        if styles:
            _speakers_cache = (now + _SPEAKERS_TTL_SECONDS, styles)
            return styles
    return []


def preview_wav(entry: dict[str, Any], text: str, urls: Sequence[str]) -> bytes:
    """最初に応答した ENGINE で合成する。どれにも接続できなければ OSError。"""
    last: OSError | None = None
    for url in urls:
        try:
            return synthesize(text or PREVIEW_TEXT, entry, url)
        except OSError as exc:
            last = exc
    raise OSError("VOICEVOX に接続できません") from last


def read_voice_mapping_raw(root: Path, org_id: str) -> dict[str, dict[str, Any]]:
    """編集用に、voice_mapping.json（なければ .example）の中身をそのまま返す。無ければ空。"""
    org_dir = Path(root) / "organizations" / org_id
    for name in VOICE_MAPPING_FILES:
        path = org_dir / name
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {key: value for key, value in data.items() if isinstance(value, dict)}
    return {}


def _check_scales(item: dict[str, Any], where: str, errors: list[str]) -> None:
    if "speaker" in item and (not isinstance(item["speaker"], int) or isinstance(item["speaker"], bool) or item["speaker"] < 0):
        errors.append(f"{where}: speaker は 0 以上の整数にしてください")
    for key, (low, high) in SCALE_RANGES.items():
        if key in item:
            value = item[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                errors.append(f"{where}: {key} は {low} 〜 {high} の数にしてください")


def validate_entry(talent_id: str, entry: dict[str, Any]) -> list[str]:
    """組織の上書き 1 件の検証。speaker は省ける（人材の既定の声を使う）。"""
    errors: list[str] = []
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        errors.append(f"{talent_id}: 未知の項目 {', '.join(sorted(unknown))}")
    if "read" in entry and not isinstance(entry["read"], bool):
        errors.append(f"{talent_id}: read は true / false にしてください")
    _check_scales(entry, talent_id, errors)
    for index, variant in enumerate(entry.get("variants") or [], 1):
        where = f"{talent_id} の variants[{index}]"
        if not isinstance(variant, dict):
            errors.append(f"{where}: オブジェクトにしてください")
            continue
        if not isinstance(variant.get("when_action"), str) or not variant["when_action"]:
            errors.append(f"{where}: when_action（action に含まれる文字列）が必要です")
        unknown = set(variant) - _VARIANT_KEYS
        if unknown:
            errors.append(f"{where}: 未知の項目 {', '.join(sorted(unknown))}")
        _check_scales(variant, where, errors)
    return errors


def validate_roles(roles: Any) -> list[str]:
    """`_roles`（役割名 → speed / pitch / intonation）の検証。"""
    if not isinstance(roles, dict):
        return [f"{VOICE_ROLES_KEY}: オブジェクトにしてください"]
    errors: list[str] = []
    for slot, style in roles.items():
        where = f"{VOICE_ROLES_KEY}[{slot}]"
        if not isinstance(style, dict):
            errors.append(f"{where}: オブジェクトにしてください")
            continue
        unknown = set(style) - set(SCALE_RANGES)
        if unknown:
            errors.append(f"{where}: 未知の項目 {', '.join(sorted(unknown))}（役割で変えられるのは速さ・高さ・抝揚だけ）")
        _check_scales(style, where, errors)
    return errors


def save_voice_mapping(root: Path, org_id: str, mapping: dict[str, Any]) -> Path:
    """検証して voice_mapping.json に書く（.example には書かない）。誤りがあれば ValueError。"""
    errors = [
        error
        for talent_id, entry in mapping.items()
        if talent_id not in (USER_VOICE_ID, VOICE_ROLES_KEY)
        for error in validate_entry(talent_id, entry)
    ]
    if VOICE_ROLES_KEY in mapping:
        errors += validate_roles(mapping[VOICE_ROLES_KEY])
    if errors:
        raise ValueError("\n".join(errors))
    path = Path(root) / "organizations" / org_id / VOICE_MAPPING_FILE
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def build_variant(
    *, when_action: str, label: str, speaker: Any, speed: Any, pitch: Any, intonation: Any
) -> dict[str, Any] | None:
    """画面の 1 行から variant を作る。when_action が空なら None（行を使わない）。"""
    when = (when_action or "").strip()
    if not when:
        return None
    variant: dict[str, Any] = {"when_action": when}
    if label:
        variant["label"] = label
    if speaker not in (None, ""):
        variant["speaker"] = int(speaker)
    for key, value in (("speed", speed), ("pitch", pitch), ("intonation", intonation)):
        if _number(value) is not None:
            variant[key] = _number(value)
    return variant


def build_entry(
    *,
    speaker: Any,
    label: str,
    speed: Any,
    pitch: Any,
    intonation: Any,
    when_action: str,
    variants: Sequence[dict[str, Any]],
    read: bool = True,
) -> dict[str, Any]:
    """組織の上書き 1 件。空欄の項目は書かない（speaker を省くと、人材の既定の声）。"""
    entry: dict[str, Any] = {}
    if not read:
        entry["read"] = False
    if label:
        entry["label"] = label
    if speaker not in (None, ""):
        entry["speaker"] = int(speaker)
    for key, value in (("speed", speed), ("pitch", pitch), ("intonation", intonation)):
        if _number(value) is not None:
            entry[key] = _number(value)
    if (when_action or "").strip():
        entry["when_action"] = when_action.strip()
    if variants:
        entry["variants"] = list(variants)
    return entry


def build_talent_voice(*, speaker: Any, label: str, speed: Any, pitch: Any, intonation: Any) -> dict[str, Any]:
    """人材の既定の声（talents/<id>.json の voice）。"""
    voice: dict[str, Any] = {"engine": "voicevox", "speaker": int(speaker)}
    if label:
        voice["label"] = label
    for key, value in (("speed", speed), ("pitch", pitch), ("intonation", intonation)):
        if _number(value) is not None:
            voice[key] = _number(value)
    return voice


def read_talent_voice(root: Path, talent_id: str) -> dict[str, Any] | None:
    voice = load_config("talent", talent_id, root).get("voice") if talent_id else None
    return voice if isinstance(voice, dict) else None


def save_talent_voice(root: Path, talent_id: str, voice: dict[str, Any] | None) -> None:
    """人材の既定の声を talents/<id>.json に書く（None で削除）。他の項目はそのまま。誤りは ValueError。"""
    data = load_config("talent", talent_id, root)
    if not data:
        raise ValueError(f"人材 {talent_id} が見つかりません")
    if voice is None:
        data.pop("voice", None)
    else:
        data["voice"] = voice
    result = save_config("talent", talent_id, data, root)
    if not result.ok:
        raise ValueError(result.message)


def build_roles(rows: Sequence[tuple[Any, Any, Any, Any]]) -> dict[str, dict[str, float]]:
    """画面の行（役割名, 速さ, 高さ, 抝揚）から `_roles` を作る。役割名が空・値がすべて空の行は使わない。"""
    roles: dict[str, dict[str, float]] = {}
    for name, speed, pitch, intonation in rows:
        slot = (name or "").strip()
        style = {
            key: number
            for key, value in (("speed", speed), ("pitch", pitch), ("intonation", intonation))
            if (number := _number(value)) is not None
        }
        if slot and style:
            roles[slot] = style
    return roles


def slot_choices(root: Path) -> list[str]:
    """ワークフローに出てくる役割（スロット）名の候補。"""
    try:
        return sorted({spec.slot_name for spec in load_binding_slot_specs(Path(root))})
    except (OSError, ValueError):
        return []


def shared_speakers(mapping: dict[str, dict[str, Any]]) -> dict[int, list[str]]:
    """基本の声が同じ人材の組（2 人以上のものだけ）。聞き分けにくくなるので、警告に使う。"""
    groups: dict[int, list[str]] = defaultdict(list)
    for talent_id, entry in mapping.items():
        if talent_id != USER_VOICE_ID and isinstance(entry.get("speaker"), int):
            groups[entry["speaker"]].append(talent_id)
    return {speaker: ids for speaker, ids in groups.items() if len(ids) > 1}

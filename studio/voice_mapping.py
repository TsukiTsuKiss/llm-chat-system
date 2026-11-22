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

from studio.voice import USER_VOICE_ID, VOICE_MAPPING_FILES, synthesize
from studio.voice_engines import prefer_ipv4

VOICE_MAPPING_FILE = VOICE_MAPPING_FILES[0]
PREVIEW_TEXT = "こんにちは。これは声の試聴です。速さや高さを変えると、聞こえ方が変わります。"
# VOICEVOX が受け付ける範囲
SCALE_RANGES = {"speed": (0.5, 2.0), "pitch": (-0.15, 0.15), "intonation": (0.0, 2.0)}
_ENTRY_KEYS = {"label", "speaker", "when_action", "variants", *SCALE_RANGES}
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
    errors: list[str] = []
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        errors.append(f"{talent_id}: 未知の項目 {', '.join(sorted(unknown))}")
    if "speaker" not in entry:
        errors.append(f"{talent_id}: speaker が必要です")
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


def save_voice_mapping(root: Path, org_id: str, mapping: dict[str, dict[str, Any]]) -> Path:
    """検証して voice_mapping.json に書く（.example には書かない）。誤りがあれば ValueError。"""
    errors = [
        error
        for talent_id, entry in mapping.items()
        if talent_id != USER_VOICE_ID
        for error in validate_entry(talent_id, entry)
    ]
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
) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    if label:
        entry["label"] = label
    entry["speaker"] = int(speaker)
    for key, value in (("speed", speed), ("pitch", pitch), ("intonation", intonation)):
        if _number(value) is not None:
            entry[key] = _number(value)
    if (when_action or "").strip():
        entry["when_action"] = when_action.strip()
    if variants:
        entry["variants"] = list(variants)
    return entry


def shared_speakers(mapping: dict[str, dict[str, Any]]) -> dict[int, list[str]]:
    """基本の声が同じ人材の組（2 人以上のものだけ）。聞き分けにくくなるので、警告に使う。"""
    groups: dict[int, list[str]] = defaultdict(list)
    for talent_id, entry in mapping.items():
        if talent_id != USER_VOICE_ID and isinstance(entry.get("speaker"), int):
            groups[entry["speaker"]].append(talent_id)
    return {speaker: ids for speaker, ids in groups.items() if len(ids) > 1}

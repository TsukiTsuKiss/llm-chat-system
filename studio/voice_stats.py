"""過去セッションの合成記録（sessions/audio/*/timeline.jsonl の synth）から、ENGINE ごとの速さを集計する。"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EngineStat:
    name: str
    calls: int
    failed: int
    sessions: int
    median_sec: float | None
    median_ms_per_char: float | None
    with_chars: int  # chars の記録がある合成の数（1 文字あたりの母数）


def _read_synth_records(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("kind") == "synth":
            records.append(record)
    return records


def collect_synth_stats(
    root: Path, names_by_url: Mapping[str, str] | None = None, *, recent_sessions: int = 30
) -> tuple[list[EngineStat], int]:
    """(ENGINE ごとの集計, 読んだセッション数)。名前は engine_name、なければ URL から引く。速い順。"""
    names = names_by_url or {}
    audio_root = root / "sessions" / "audio"
    if not audio_root.is_dir():
        return [], 0
    folders = sorted(
        (p for p in audio_root.iterdir() if (p / "timeline.jsonl").is_file()), key=lambda p: p.name, reverse=True
    )[: max(1, recent_sessions)]

    seconds: dict[str, list[float]] = {}
    per_char: dict[str, list[float]] = {}
    failed: dict[str, int] = {}
    sessions: dict[str, set[str]] = {}
    for folder in folders:
        for record in _read_synth_records(folder / "timeline.jsonl"):
            url = str(record.get("engine") or "")
            key = record.get("engine_name") or names.get(url.rstrip("/")) or url or "?"
            sessions.setdefault(key, set()).add(folder.name)
            if record.get("failed"):
                failed[key] = failed.get(key, 0) + 1
                continue
            try:
                duration = float(record["end"]) - float(record["t"])
            except (KeyError, TypeError, ValueError):
                continue
            seconds.setdefault(key, []).append(duration)
            chars = record.get("chars")
            if isinstance(chars, int) and chars > 0:
                per_char.setdefault(key, []).append(duration / chars * 1000)

    stats = [
        EngineStat(
            name=key,
            calls=len(seconds.get(key, [])),
            failed=failed.get(key, 0),
            sessions=len(sessions[key]),
            median_sec=statistics.median(seconds[key]) if key in seconds else None,
            median_ms_per_char=statistics.median(per_char[key]) if key in per_char else None,
            with_chars=len(per_char.get(key, [])),
        )
        for key in sessions
    ]
    stats.sort(key=lambda s: (s.median_ms_per_char is None, s.median_ms_per_char or 0.0, s.name))
    return stats, len(folders)

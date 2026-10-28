"""読み上げの実時間ログ（timeline.jsonl）と、そこから作る再生用 HTML（design.md §7.9.1）。

使い方: python -m studio.voice_timeline [セッション ID]（省略時は最新）→ sessions/audio/<id>/replay.html
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from html import escape
from pathlib import Path
from typing import Any

TIMELINE_FILE = "timeline.jsonl"
REPLAY_FILE = "replay.html"
_TEMPLATE = Path(__file__).with_name("voice_replay.html")


class TimelineRecorder:
    """回答・合成・再生の時刻を session 開始からの秒数で記録する。最初の合成を始めるまでは書き出さない。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._out_dir: Path | None = None
        self._session_id: str | None = None
        self._t0 = 0.0
        self._buffer: list[str] = []
        self._active = False
        self._first_write = True

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def out_dir(self) -> Path | None:
        return self._out_dir

    def begin(self, out_dir: Path, session_id: str) -> None:
        with self._lock:
            if session_id == self._session_id:
                return
            self._session_id = session_id
            self._out_dir = out_dir
            self._t0 = time.monotonic()
            self._buffer.clear()
            self._active = False
            self._first_write = True

    def now(self) -> float:
        return time.monotonic() - self._t0

    def add(self, kind: str, *, t: float | None = None, **fields: Any) -> None:
        with self._lock:
            if self._out_dir is None:
                return
            stamp = time.monotonic() - self._t0 if t is None else t
            self._buffer.append(json.dumps({"kind": kind, "t": round(stamp, 3), **fields}, ensure_ascii=False))
            if kind in ("synth_start", "utterance"):
                self._active = True
            if self._active:
                self._flush_locked()

    def _flush_locked(self) -> None:
        assert self._out_dir is not None
        self._out_dir.mkdir(parents=True, exist_ok=True)
        mode = "w" if self._first_write else "a"
        with (self._out_dir / TIMELINE_FILE).open(mode, encoding="utf-8") as handle:
            handle.write("\n".join(self._buffer) + "\n")
        self._first_write = False
        self._buffer.clear()


def _render_page(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)


def _backfill_utterance_text(root: Path, session_id: str, events: list[dict[str, Any]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    """発言本文を記録する前の timeline.jsonl に、セッションログから本文を補う（読み上げ対象の発言と wav を順に対応づける）。"""
    from collections import Counter, defaultdict

    from studio.session_report import read_jsonl, session_log_path
    from studio.voice import clean_for_speech, load_voice_mapping

    if any(e.get("kind") == "utterance_text" for e in events) or not meta.get("organization"):
        return events
    mapping = load_voice_mapping(Path(root), meta["organization"])
    done_times: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e.get("kind") == "step_done":
            done_times[e["talent_id"]].append(e["t"])

    seen: Counter[str] = Counter()
    voiced: list[tuple[str, float, str]] = []
    for record in read_jsonl(session_log_path(root, session_id)):
        if record.get("type") != "step":
            continue
        talent_id = record["talent_id"]
        nth = seen[talent_id]
        seen[talent_id] += 1
        entry = mapping.get(talent_id)
        if entry is None:
            continue
        when_action = entry.get("when_action")
        if when_action and when_action not in (record.get("action") or ""):
            continue
        shown = clean_for_speech(record.get("text") or "", strip_backstage=not when_action)
        if shown:
            times = done_times[talent_id]
            voiced.append((talent_id, times[nth] if nth < len(times) else 0.0, shown))

    files = sorted(e["file"] for e in events if e.get("kind") == "utterance")
    if len(files) != len(voiced) or any(f.split("_", 1)[1][:-4] != v[0] for f, v in zip(files, voiced)):
        return events
    extra = [
        {"kind": "utterance_text", "t": t, "file": f, "talent_id": talent_id, "text": text}
        for f, (talent_id, t, text) in zip(files, voiced)
    ]
    return [*events, *extra]


def replay_data(root: Path, session_id: str, *, base: str = "") -> dict[str, Any]:
    from studio.session_report import read_jsonl, read_session_meta, session_log_path

    audio_dir = Path(root) / "sessions" / "audio" / session_id
    events = read_jsonl(audio_dir / TIMELINE_FILE)
    if not events:
        raise FileNotFoundError(f"{audio_dir / TIMELINE_FILE} がありません（読み上げを有効にしたセッションのみ記録されます）")
    meta = read_session_meta(session_log_path(root, session_id)) or {}
    title = " / ".join(part for part in (meta.get("organization"), meta.get("workflow")) if part)
    return {
        "session_id": session_id,
        "title": title,
        "organization": meta.get("organization"),
        "names": meta.get("talents") or {},
        "events": _backfill_utterance_text(root, session_id, events, meta),
        "base": base,
    }


def build_replay(root: Path, session_id: str) -> Path:
    """sessions/audio/<id>/timeline.jsonl から、同じフォルダに単体の replay.html を作る。"""
    out = Path(root) / "sessions" / "audio" / session_id / REPLAY_FILE
    data = replay_data(root, session_id)
    out.write_text(_render_page(data), encoding="utf-8")
    return out


def _iframe(page: str, height: int) -> str:
    return (
        f'<iframe srcdoc="{escape(page, quote=True)}" '
        f'style="width:100%;height:{height}px;border:0;border-radius:6px"></iframe>'
    )


def replay_iframe_html(root: Path, session_id: str, *, compact: bool = False) -> str:
    """保存済みセッションの再生ページを、Gradio のファイル配信で wav を読む iframe（srcdoc）にする。"""
    audio_dir = Path(root) / "sessions" / "audio" / session_id
    data = replay_data(root, session_id, base=gradio_file_base(audio_dir))
    data["embedded"] = compact
    return _iframe(_render_page(data), 340 if compact else 640)


def gradio_file_base(audio_dir: Path) -> str:
    """Gradio のファイル配信（launch の allowed_paths）で、フォルダ内のファイルを指す URL の接頭辞。"""
    return f"/gradio_api/file={Path(audio_dir).resolve().as_posix()}/"


def live_iframe_html(session_id: str, audio_dir: Path, *, height: int = 340) -> str:
    """進行中のセッションを timeline.jsonl の更新に合わせて表示する iframe（srcdoc）。"""
    page = _render_page({"live": True, "session_id": session_id, "base": gradio_file_base(audio_dir)})
    return _iframe(page, height)


def latest_session_id(root: Path) -> str | None:
    audio_root = Path(root) / "sessions" / "audio"
    if not audio_root.is_dir():
        return None
    ids = sorted((p.name for p in audio_root.iterdir() if (p / TIMELINE_FILE).is_file()), reverse=True)
    return ids[0] if ids else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="読み上げのタイミング再生用 HTML を作る")
    parser.add_argument("session_id", nargs="?", help="セッション ID（省略時は timeline.jsonl のある最新）")
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    session_id = args.session_id or latest_session_id(root)
    if not session_id:
        print("timeline.jsonl のあるセッションがありません", file=sys.stderr)
        return 1
    try:
        out = build_replay(root, session_id)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"作成しました: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

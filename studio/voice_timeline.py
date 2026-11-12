"""読み上げの実時間ログ（timeline.jsonl）と、そこから作る再生用 HTML（design.md §7.9.1）。

使い方: python -m studio.voice_timeline [セッション ID]（省略時は最新）→ sessions/audio/<id>/replay.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from html import escape
from pathlib import Path
from typing import Any

TIMELINE_FILE = "timeline.jsonl"
REPLAY_FILE = "replay.html"
_TEMPLATE = Path(__file__).with_name("voice_replay.html")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class TimelineRecorder:
    """回答・合成・再生の時刻を session 開始からの秒数で記録する。最初の回答開始までは書き出さない。"""

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
            if kind in ("step_start", "step_done", "synth_start", "utterance", "play_start"):
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


_USER_PLAY_GAP = 0.3


def _shift_event_times(events: list[dict[str, Any]], start_t: float, delta: float) -> None:
    if delta <= 1e-9:
        return
    for event in events:
        stamp = event.get("t")
        if isinstance(stamp, (int, float)) and stamp + 1e-9 >= start_t:
            event["t"] = round(float(stamp) + delta, 3)
            end = event.get("end")
            if isinstance(end, (int, float)):
                event["end"] = round(float(end) + delta, 3)


def _activity_times(events: list[dict[str, Any]], *, after: float | None = None) -> list[float]:
    from studio.voice import USER_VOICE_ID

    times: list[float] = []
    for event in events:
        if event.get("kind") not in ("step_start", "play_start", "utterance", "synth_start"):
            continue
        if event.get("talent_id") == USER_VOICE_ID:
            continue
        if str(event.get("file") or "").endswith(f"_{USER_VOICE_ID}.wav"):
            continue
        stamp = event.get("t")
        if not isinstance(stamp, (int, float)):
            continue
        if after is not None and stamp <= after + 1e-9:
            continue
        times.append(float(stamp))
    return times


def _user_input_texts(root: Path, session_id: str) -> list[str]:
    from studio.session_report import read_jsonl, session_log_path
    from studio.voice import clean_for_speech

    path = session_log_path(root, session_id)
    if not path.is_file():
        return []
    texts: list[str] = []
    for record in read_jsonl(path):
        if record.get("type") != "user_input":
            continue
        shown = clean_for_speech(str(record.get("text") or ""), strip_backstage=False)
        if shown:
            texts.append(shown)
    return texts


def _inject_user_replay(
    root: Path, session_id: str, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """セッションログの user_input を、再生用の発言として timeline に差し込む（ライブの記録は変えない）。"""
    from studio.voice import USER_VOICE_ID, _safe_duration

    if any(e.get("kind") == "utterance_text" and e.get("talent_id") == USER_VOICE_ID for e in events):
        return events
    texts = _user_input_texts(root, session_id)
    if not texts:
        return events

    events = [dict(event) for event in events]
    audio_dir = Path(root) / "sessions" / "audio" / session_id
    turn_ends = [
        float(e["t"])
        for e in events
        if e.get("kind") == "turn_end" and isinstance(e.get("t"), (int, float))
    ]
    extra: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        filename = f"u{index + 1:02d}_{USER_VOICE_ID}.wav"
        wav_path = audio_dir / filename
        duration = _safe_duration(wav_path) if wav_path.is_file() else 0.0
        if index == 0:
            insert_t = 0.0
            next_t = min(_activity_times(events), default=None)
            if duration > 0 and next_t is not None:
                needed = duration + _USER_PLAY_GAP
                if next_t < needed:
                    _shift_event_times(events, next_t, needed - next_t)
                    turn_ends = [t + (needed - next_t) if t >= next_t else t for t in turn_ends]
        else:
            turn_t = turn_ends[index - 1] if index - 1 < len(turn_ends) else max(
                (float(e["t"]) for e in events if isinstance(e.get("t"), (int, float))),
                default=0.0,
            )
            next_t = min(_activity_times(events, after=turn_t), default=None)
            if next_t is None:
                insert_t = turn_t
            elif duration > 0:
                gap = duration + _USER_PLAY_GAP
                if next_t - turn_t < gap:
                    _shift_event_times(events, next_t, gap - (next_t - turn_t))
                    shifted = gap - (next_t - turn_t)
                    turn_ends = [t + shifted if t >= next_t else t for t in turn_ends]
                    next_t = turn_t + gap
                insert_t = next_t - gap
            else:
                insert_t = next_t
        insert_t = round(max(0.0, insert_t), 3)
        extra.append(
            {
                "kind": "utterance_text",
                "t": insert_t,
                "file": filename,
                "talent_id": USER_VOICE_ID,
                "text": text,
            }
        )
        if duration > 0:
            extra.append({"kind": "utterance", "t": insert_t, "file": filename, "duration": duration})
            extra.append({"kind": "play_start", "t": insert_t, "file": filename})
            extra.append({"kind": "play_stop", "t": round(insert_t + duration, 3), "file": filename})
    return [*events, *extra]


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
    from studio.voice import USER_VOICE_ID, USER_VOICE_LABEL

    names = dict(meta.get("talents") or {})
    names.setdefault(USER_VOICE_ID, USER_VOICE_LABEL)
    filled = _backfill_utterance_text(root, session_id, events, meta)
    return {
        "session_id": session_id,
        "title": title,
        "organization": meta.get("organization"),
        "names": names,
        "events": _inject_user_replay(root, session_id, filled),
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
        f'style="width:100%;height:{height}px;border:0;border-radius:6px;overflow:hidden"></iframe>'
    )


def replay_iframe_html(root: Path, session_id: str, *, compact: bool = False) -> str:
    """保存済みセッションの再生ページを、Gradio のファイル配信で wav を読む iframe（srcdoc）にする。"""
    audio_dir = Path(root) / "sessions" / "audio" / session_id
    data = replay_data(root, session_id, base=gradio_file_base(audio_dir))
    data["embedded"] = compact
    return _iframe(_render_page(data), 400 if compact else 640)


def gradio_file_base(audio_dir: Path) -> str:
    """Gradio のファイル配信（launch の allowed_paths）で、フォルダ内の wav を指す URL の接頭辞。"""
    return f"/gradio_api/file={Path(audio_dir).resolve().as_posix()}/"


def timeline_poll_url(session_id: str) -> str:
    """書き込み中の timeline.jsonl をスナップショットで返す Studio 側の URL。"""
    return f"/studio/audio/{session_id}/timeline.jsonl"


def timeline_snapshot_bytes(root: Path, session_id: str) -> bytes | None:
    """配信時点のファイル内容を一括で読む。追記中の Content-Length 不一致を避ける。"""
    if not _SESSION_ID_RE.fullmatch(session_id):
        return None
    audio_root = (Path(root) / "sessions" / "audio").resolve()
    path = audio_root / session_id / TIMELINE_FILE
    try:
        resolved = path.resolve()
        if (
            resolved.name != TIMELINE_FILE
            or resolved.parent.name != session_id
            or not resolved.is_relative_to(audio_root)
        ):
            return None
        return resolved.read_bytes()
    except OSError:
        return None


def mount_timeline_route(app: Any, root: Path) -> None:
    """ライブ表示が timeline.jsonl を 1 秒ごとに取る経路。Gradio のファイル配信は使わない。"""
    from starlette.responses import Response

    path = "/studio/audio/{session_id}/timeline.jsonl"
    routes = getattr(app, "routes", None) or getattr(getattr(app, "router", None), "routes", [])
    if any(getattr(route, "path", None) == path for route in routes):
        return

    async def timeline(session_id: str) -> Response:
        data = timeline_snapshot_bytes(root, session_id)
        if data is None:
            return Response(status_code=404)
        return Response(
            content=data,
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store"},
        )

    app.add_api_route(path, timeline, methods=["GET"], include_in_schema=False)


def live_iframe_html(
    session_id: str,
    audio_dir: Path,
    *,
    height: int = 400,
    engines: list[str] | None = None,
    names: dict[str, str] | None = None,
) -> str:
    """進行中のセッションを timeline.jsonl の更新に合わせて表示する iframe（srcdoc）。"""
    page = _render_page(
        {
            "live": True,
            "session_id": session_id,
            "base": gradio_file_base(audio_dir),
            "timeline_url": timeline_poll_url(session_id),
            "engines": list(engines or []),
            "play_lane": True,
            "names": dict(names or {}),
        }
    )
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

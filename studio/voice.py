"""VOICEVOX による発言の読み上げ（CLI 用）。"""

from __future__ import annotations

import io
import json
import queue
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any

try:
    import winsound
except ImportError:  # Windows 以外は保存のみ
    winsound = None  # type: ignore[assignment]

DEFAULT_BASE_URL = "http://127.0.0.1:50021"
VOICE_MAPPING_FILES = ("voice_mapping.json", "voice_mapping.example.json")

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MD_MARKS = re.compile(r"[*#`_>]+|^\s*[-・]\s+|^\s*\d+\.\s+", re.MULTILINE)
_BLANKS = re.compile(r"\n{2,}")


def clean_for_speech(text: str) -> str:
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _MD_MARKS.sub("", text)
    return _BLANKS.sub("\n", text).strip()


def split_for_speech(text: str, limit: int = 60) -> list[str]:
    # 先頭の音を早く出すため、文単位で limit 文字程度にまとめて合成する
    chunks: list[str] = []
    for line in text.split("\n"):
        current = ""
        for sentence in re.split(r"(?<=[。！？])", line):
            sentence = sentence.strip()
            if not sentence:
                continue
            if current and len(current) + len(sentence) > limit:
                chunks.append(current)
                current = ""
            current += sentence
        if current:
            chunks.append(current)
    return chunks


def join_wavs(wavs: list[bytes]) -> bytes:
    if len(wavs) == 1:
        return wavs[0]
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        for index, data in enumerate(wavs):
            with wave.open(io.BytesIO(data)) as reader:
                if index == 0:
                    writer.setparams(reader.getparams())
                writer.writeframes(reader.readframes(reader.getnframes()))
    return out.getvalue()


def load_voice_mapping(root: Path, org_id: str) -> dict[str, dict[str, Any]]:
    org_dir = root / "organizations" / org_id
    for name in VOICE_MAPPING_FILES:
        path = org_dir / name
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            talent_id: entry
            for talent_id, entry in data.items()
            if isinstance(entry, dict) and isinstance(entry.get("speaker"), int)
        }
    return {}


def _post(url: str, data: bytes | None = None, *, timeout: float) -> bytes:
    headers = {"Content-Type": "application/json"} if data else {}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def synthesize(text: str, entry: dict[str, Any], base_url: str = DEFAULT_BASE_URL) -> bytes:
    speaker = entry["speaker"]
    query = json.loads(
        _post(
            f"{base_url}/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": speaker}),
            timeout=30,
        )
    )
    for key, field in (("speed", "speedScale"), ("pitch", "pitchScale"), ("intonation", "intonationScale")):
        if key in entry:
            query[field] = entry[key]
    return _post(
        f"{base_url}/synthesis?speaker={speaker}",
        json.dumps(query).encode("utf-8"),
        timeout=120,
    )


def engine_available(base_url: str = DEFAULT_BASE_URL) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/version", timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


class VoiceReader:
    """step_done イベントを順に音声化し、wav を保存して再生する。"""

    def __init__(
        self,
        root: Path,
        mapping: dict[str, dict[str, Any]],
        *,
        base_url: str = DEFAULT_BASE_URL,
        play: bool = True,
    ) -> None:
        self._root = root
        self._mapping = mapping
        self._base_url = base_url
        self._play = play and winsound is not None
        self._out_dir: Path | None = None
        self._count = 0
        self._failed = False
        self._queue: queue.Queue[tuple[Path, str, dict[str, Any]] | None] = queue.Queue()
        self._playback: queue.Queue[bytes | None] = queue.Queue()
        self._workers = [
            threading.Thread(target=self._synthesize_loop, daemon=True),
            threading.Thread(target=self._playback_loop, daemon=True),
        ]
        for worker in self._workers:
            worker.start()

    def handle(self, event: Any) -> None:
        if event.type == "session_start":
            self._out_dir = self._root / "sessions" / "audio" / event.payload["session_id"]
            return
        if event.type != "step_done" or self._out_dir is None:
            return
        entry = self._mapping.get(event.payload["talent_id"])
        text = clean_for_speech(event.payload["text"])
        if entry is None or not text:
            return
        self._count += 1
        path = self._out_dir / f"{self._count:02d}_{event.payload['talent_id']}.wav"
        self._queue.put((path, text, entry))

    def close(self) -> None:
        self._queue.put(None)
        for worker in self._workers:
            worker.join()

    def _synthesize_loop(self) -> None:
        while (job := self._queue.get()) is not None:
            if self._failed:
                continue
            path, text, entry = job
            wavs: list[bytes] = []
            for chunk in split_for_speech(text):
                try:
                    wav = synthesize(chunk, entry, self._base_url)
                except urllib.error.HTTPError as exc:
                    print(f"[voice] 合成に失敗したため一部を飛ばします: {exc}", file=sys.stderr)
                    continue
                except OSError as exc:
                    self._failed = True
                    print(f"[voice] VOICEVOX に接続できないため読み上げを中止します: {exc}", file=sys.stderr)
                    break
                wavs.append(wav)
                self._playback.put(wav)
            if wavs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(join_wavs(wavs))
        self._playback.put(None)

    def _playback_loop(self) -> None:
        while (wav := self._playback.get()) is not None:
            if self._play:
                winsound.PlaySound(wav, winsound.SND_MEMORY)

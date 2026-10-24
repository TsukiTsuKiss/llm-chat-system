"""VOICEVOX による発言の読み上げ（CLI のスピーカー再生 / Web UI のブラウザ再生）。"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from collections import deque
from collections.abc import Sequence
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

try:
    import winsound
except ImportError:  # Windows 以外は保存のみ
    winsound = None  # type: ignore[assignment]

DEFAULT_BASE_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021").rstrip("/")
VOICE_MAPPING_FILES = ("voice_mapping.json", "voice_mapping.example.json")
VOICE_DICTIONARY_FILE = "voice_dictionary.json"

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_MD_MARKS = re.compile(r"[*#`_>]+|^\s*[-・]\s+|^\s*\d+\.\s+", re.MULTILINE)
_BLANKS = re.compile(r"\n{2,}")
# 発言末尾に混ざる裏方メモ（この行以降を読み上げない）
_BACKSTAGE = re.compile(
    r"^[ \t]*(?:[（(【\[][ \t]*進行メモ[）)】\]]|[（(【\[]?[ \t]*ディレクター点検[）)】\]]?).*\Z",
    re.MULTILINE | re.DOTALL,
)


def clean_for_speech(text: str) -> str:
    text = _BACKSTAGE.sub("", _MD_MARKS.sub("", text))
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
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


def _read_dictionary(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and k}


def load_voice_dictionary(root: Path, org_id: str) -> dict[str, str]:
    # 共通辞書（ルート直下）に組織辞書を重ね、同じ表記は組織側を優先する
    return {
        **_read_dictionary(root / VOICE_DICTIONARY_FILE),
        **_read_dictionary(root / "organizations" / org_id / VOICE_DICTIONARY_FILE),
    }


def apply_dictionary(text: str, dictionary: dict[str, str]) -> str:
    # 長い表記を先に置換し、短い表記が一部を壊さないようにする
    for surface in sorted(dictionary, key=len, reverse=True):
        text = text.replace(surface, dictionary[surface])
    return text


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


def parse_voicevox_urls(value: str) -> list[str]:
    urls = [item.strip().rstrip("/") for item in value.split(",")]
    return [url for url in urls if url]


def engine_available(base_url: str = DEFAULT_BASE_URL) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/version", timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


class AudioRelay:
    """ブラウザ再生用の順番待ち。再生中は次の音声を渡さない。"""

    # end イベントが届かない場合に備え、長さに加える猛予
    GRACE_SECONDS = 5.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: deque[Path] = deque()
        self._playing_until: float | None = None

    def push(self, path: Path) -> None:
        with self._lock:
            self._items.append(path)

    def finished(self) -> None:
        with self._lock:
            self._playing_until = None

    def next_if_idle(self) -> Path | None:
        with self._lock:
            now = time.monotonic()
            if self._playing_until is not None and now < self._playing_until:
                return None
            if not self._items:
                return None
            path = self._items.popleft()
            self._playing_until = now + wav_duration(path) + self.GRACE_SECONDS
            return path

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._playing_until = None


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as reader:
        return reader.getnframes() / reader.getframerate()


def load_wav_array(path: Path):
    """gr.Audio(type="numpy") へ渡す (sample_rate, ndarray)。ファイル配信の許可パスを避ける。"""
    import numpy as np

    with wave.open(str(path)) as reader:
        frames = reader.readframes(reader.getnframes())
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[reader.getsampwidth()]
        data = np.frombuffer(frames, dtype=dtype)
        if reader.getnchannels() > 1:
            data = data.reshape(-1, reader.getnchannels())
        return reader.getframerate(), data


class VoiceReader:
    """step_done イベントを順に音声化し、wav を保存する。play=True でサーバー側スピーカーも鳴らす。

    base_url に複数の ENGINE を渡すと、発言内の文を空いている ENGINE に振り分けて並列に合成する。
    """

    def __init__(
        self,
        root: Path,
        mapping: dict[str, dict[str, Any]],
        *,
        base_url: str | Sequence[str] = DEFAULT_BASE_URL,
        play: bool = True,
        dictionary: dict[str, str] | None = None,
        on_utterance: Callable[[Path], None] | None = None,
    ) -> None:
        self._root = root
        self._mapping = mapping
        self._dictionary = dictionary or {}
        urls = [base_url] if isinstance(base_url, str) else list(base_url)
        self._idle_engines: queue.Queue[str] = queue.Queue()
        for url in urls:
            self._idle_engines.put(url)
        self._alive_engines = len(urls)
        self._engine_lock = threading.Lock()
        self._play = play and winsound is not None
        self._on_utterance = on_utterance
        self._out_dir: Path | None = None
        self._count = 0
        self._failed = False
        self._queue: queue.Queue[tuple[Path, str, dict[str, Any]] | None] = queue.Queue()
        self._tasks: queue.Queue[tuple[str, dict[str, Any], Future[bytes | None]] | None] = queue.Queue()
        self._playback: queue.Queue[bytes | None] = queue.Queue()
        self._engine_workers = [threading.Thread(target=self._engine_loop, daemon=True) for _ in urls]
        self._workers = [
            threading.Thread(target=self._synthesize_loop, daemon=True),
            threading.Thread(target=self._playback_loop, daemon=True),
            *self._engine_workers,
        ]
        for worker in self._workers:
            worker.start()

    def begin_session(self, session_id: str) -> None:
        self._out_dir = self._root / "sessions" / "audio" / session_id
        self._count = 0

    def handle(self, event: Any) -> None:
        if event.type == "session_start":
            self.begin_session(event.payload["session_id"])
            return
        if event.type != "step_done" or self._out_dir is None:
            return
        entry = self._mapping.get(event.payload["talent_id"])
        text = apply_dictionary(clean_for_speech(event.payload["text"]), self._dictionary)
        if entry is None or not text:
            return
        self._count += 1
        path = self._out_dir / f"{self._count:02d}_{event.payload['talent_id']}.wav"
        self._queue.put((path, text, entry))

    def close(self, *, wait: bool = True) -> None:
        if not wait:
            self._failed = True
        self._queue.put(None)
        if wait:
            for worker in self._workers:
                worker.join()

    def _synthesize_loop(self) -> None:
        while (job := self._queue.get()) is not None:
            if self._failed:
                continue
            path, text, entry = job
            futures: list[Future[bytes | None]] = []
            for chunk in split_for_speech(text):
                future: Future[bytes | None] = Future()
                self._tasks.put((chunk, entry, future))
                futures.append(future)
            wavs: list[bytes] = []
            for future in futures:
                wav = future.result()
                if self._failed:
                    break
                if wav is None:
                    continue
                wavs.append(wav)
                if self._play:
                    self._playback.put(wav)
            if wavs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(join_wavs(wavs))
                if self._on_utterance:
                    self._on_utterance(path)
        for _ in self._engine_workers:
            self._tasks.put(None)
        self._playback.put(None)

    def _engine_loop(self) -> None:
        while (task := self._tasks.get()) is not None:
            chunk, entry, future = task
            try:
                future.set_result(self._synthesize_chunk(chunk, entry))
            except Exception as exc:
                future.set_exception(exc)

    def _synthesize_chunk(self, chunk: str, entry: dict[str, Any]) -> bytes | None:
        """空いている ENGINE で合成する。None は飛ばした文、または全 ENGINE 停止（_failed）。"""
        while not self._failed:
            try:
                url = self._idle_engines.get(timeout=1)
            except queue.Empty:
                continue
            try:
                wav = synthesize(chunk, entry, url)
            except urllib.error.HTTPError as exc:
                self._idle_engines.put(url)
                print(f"[voice] 合成に失敗したため一部を飛ばします: {exc}", file=sys.stderr)
                return None
            except OSError as exc:
                with self._engine_lock:
                    self._alive_engines -= 1
                    remaining = self._alive_engines
                if remaining == 0:
                    self._failed = True
                    print(f"[voice] VOICEVOX に接続できないため読み上げを中止します: {exc}", file=sys.stderr)
                    return None
                print(f"[voice] {url} に接続できないため、この ENGINE を外して続けます: {exc}", file=sys.stderr)
                continue
            self._idle_engines.put(url)
            return wav
        return None

    def _playback_loop(self) -> None:
        while (wav := self._playback.get()) is not None:
            if self._play:
                winsound.PlaySound(wav, winsound.SND_MEMORY)

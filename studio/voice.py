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
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

try:
    import winsound
except ImportError:  # Windows 以外は保存のみ
    winsound = None  # type: ignore[assignment]

from studio.voice_timeline import TimelineRecorder

DEFAULT_BASE_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021").rstrip("/")
VOICE_MAPPING_FILES = ("voice_mapping.json", "voice_mapping.example.json")
VOICE_DICTIONARY_FILE = "voice_dictionary.json"

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
# 単語中の _（live_stack など）は辞書の照合に必要なので残し、強調用の _ だけ除く
_MD_MARKS = re.compile(
    r"[*#`>]+|(?<![0-9A-Za-z])_+|_+(?![0-9A-Za-z])|^\s*[-・]\s+|^\s*\d+\.\s+", re.MULTILINE
)
_BLANKS = re.compile(r"\n{2,}")
# LLM が混ぜる特殊な空白・ハイフンを通常のものに揃え、辞書の照合を外さないようにする
_ODD_SPACES = re.compile(r"[\u00a0\u2007\u2009\u202f]")
_ODD_HYPHENS = re.compile(r"[\u2010\u2011\u2012]")
# 発言末尾に混ざる裏方メモ（この行以降を読み上げない）
_BACKSTAGE = re.compile(
    r"^[ \t]*(?:"
    r"[（(【\[][^）)】\]\n]*(?:進行メモ|運用メモ|リサーチメモ|読み上げ対象外|放送用ではありません)"
    r"|[（(【\[]?[ \t]*ディレクター[・･]?(?:点検|リサーチメモ)"
    r").*\Z",
    re.MULTILINE | re.DOTALL,
)


def clean_for_speech(text: str, *, strip_backstage: bool = True) -> str:
    text = _ODD_HYPHENS.sub("-", _ODD_SPACES.sub(" ", text))
    text = _MD_MARKS.sub("", text)
    if strip_backstage:
        text = _BACKSTAGE.sub("", text)
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


class EngineMonitor:
    """ENGINE ごとの状態（off=未検出 / idle=待機 / busy=合成中）。定期的に /version で死活を確認する。"""

    PROBE_INTERVAL_SECONDS = 5.0

    def __init__(self, urls: Sequence[str], probe: Callable[[str], bool] | None = None) -> None:
        self.urls = list(urls)
        self._probe = probe
        self._lock = threading.Lock()
        self._alive = {url: False for url in self.urls}
        self._busy = {url: 0 for url in self.urls}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or not self.urls:
                return
            self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            self.probe_once()
            time.sleep(self.PROBE_INTERVAL_SECONDS)

    def probe_once(self) -> None:
        with self._lock:
            targets = [url for url in self.urls if not self._busy[url]]
        if not targets:
            return
        probe = self._probe or engine_available
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            results = list(pool.map(probe, targets))
        with self._lock:
            for url, alive in zip(targets, results):
                if not self._busy[url]:
                    self._alive[url] = alive

    def set_busy(self, url: str, busy: bool) -> None:
        with self._lock:
            if url not in self._busy:
                return
            if busy:
                self._busy[url] += 1
                self._alive[url] = True
            else:
                self._busy[url] = max(0, self._busy[url] - 1)

    def mark_off(self, url: str) -> None:
        with self._lock:
            if url in self._alive:
                self._alive[url] = False

    def is_alive(self, url: str) -> bool:
        with self._lock:
            return self._alive.get(url, False)

    def states(self) -> list[tuple[str, str]]:
        with self._lock:
            return [
                (url, "busy" if self._busy[url] else "idle" if self._alive[url] else "off")
                for url in self.urls
            ]


_monitors: dict[tuple[str, ...], EngineMonitor] = {}
_monitors_lock = threading.Lock()


def engine_monitor(urls: Sequence[str]) -> EngineMonitor:
    """同じ URL 構成なら全セッションで共有する（gr.State の deepcopy を通さない）。"""
    key = tuple(urls)
    with _monitors_lock:
        if key not in _monitors:
            _monitors[key] = EngineMonitor(key)
        return _monitors[key]


class AudioRelay:
    """ブラウザ再生用の順番待ち。再生中は次の音声を渡さない。

    渡した音声の読み込みが遅れても途中で次へ進まないよう、待ち時間は再生開始（play 通知）から数える。
    """

    # 渡してから再生開始（play 通知）までに許す時間
    LOAD_GRACE_SECONDS = 30.0
    # 再生開始後、stop が届かない場合に備えて長さに加える猶予
    GRACE_SECONDS = 5.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: deque[tuple[Path, Any]] = deque()
        self._deadline: float | None = None
        self._handed_tag: Any = None
        self._started = False
        self._started_at = 0.0
        self._duration = 0.0
        self._handed_file = ""
        # 設定すると、受け渡し・再生開始・再生終了の時刻を記録する
        self.timeline: TimelineRecorder | None = None

    def push(self, path: Path, tag: Any = None) -> None:
        with self._lock:
            self._items.append((path, tag))

    def started(self) -> None:
        """渡した音声の再生が始まった（ブラウザの play 通知）。"""
        with self._lock:
            if self._deadline is None or self._started:
                return
            now = time.monotonic()
            self._started = True
            self._started_at = now
            self._deadline = now + self._duration + self.GRACE_SECONDS
            if self.timeline is not None:
                self.timeline.add("play_start", file=self._handed_file)

    def finished(self) -> None:
        with self._lock:
            # 再生開始前に届いた stop は前の音声のものなので無視する
            if self._deadline is None or not self._started:
                return
            elapsed = time.monotonic() - self._started_at
            if elapsed < self._duration - 0.5:
                print(
                    f"[voice] stop 通知が音声の長さより早く届きました: 再生開始から {elapsed:.1f}秒 / 長さ {self._duration:.1f}秒",
                    file=sys.stderr,
                )
            if self.timeline is not None:
                self.timeline.add("play_stop", file=self._handed_file)
            self._reset_current()

    def _reset_current(self) -> None:
        self._deadline = None
        self._handed_tag = None
        self._started = False

    @property
    def playing_tag(self) -> Any:
        """渡した音声に付いたタグ（再生開始前を含む）。終わったときは None。"""
        with self._lock:
            if self._deadline is not None and time.monotonic() < self._deadline:
                return self._handed_tag
            return None

    def next_if_idle(self) -> Path | None:
        with self._lock:
            now = time.monotonic()
            if self._deadline is not None and now < self._deadline:
                return None
            if not self._items:
                return None
            path, self._handed_tag = self._items.popleft()
            self._handed_file = path.name
            self._duration = wav_duration(path)
            self._started = False
            self._deadline = now + self._duration + self.LOAD_GRACE_SECONDS
            return path

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._reset_current()


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as reader:
        return reader.getnframes() / reader.getframerate()


def _safe_duration(path: Path) -> float:
    try:
        return round(wav_duration(path), 3)
    except (wave.Error, EOFError):
        return 0.0


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

    base_url に複数の ENGINE を渡すと、文を空いている ENGINE に振り分けて並列に合成する。
    次の発言の文は、前の発言の合成完了を待たずに空いた ENGINE へ投入する（結果は発言・文の順に回収）。
    standby は開始時に接続できなかった ENGINE。monitor が応答を検出したら合成に加わる。
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
        monitor: EngineMonitor | None = None,
        standby: Sequence[str] = (),
    ) -> None:
        self._root = root
        self._mapping = mapping
        self._dictionary = dictionary or {}
        urls = [base_url] if isinstance(base_url, str) else list(base_url)
        self._idle_engines: queue.Queue[str] = queue.Queue()
        for url in urls:
            self._idle_engines.put(url)
        self._alive_engines = len(urls)
        self._monitor = monitor
        self._removed: set[str] = set(standby)
        self._engine_lock = threading.Lock()
        self._play = play and winsound is not None
        self._on_utterance = on_utterance
        self._out_dir: Path | None = None
        self._count = 0
        self._failed = False
        # 回答・合成・再生の時刻の記録（replay.html の元データ）
        self.timeline = TimelineRecorder()
        # on_utterance へ渡す前に呼び出し側が取り出す、保存先 wav ごとのタグ
        self.tags: dict[Path, Any] = {}
        self._actions: dict[str, str] = {}
        self._queue: queue.Queue[tuple[Path, str, dict[str, Any]] | None] = queue.Queue()
        self._pending: queue.Queue[tuple[Path, list[Future[bytes | None]]] | None] = queue.Queue()
        self._tasks: queue.Queue[tuple[str, dict[str, Any], Future[bytes | None], str] | None] = queue.Queue()
        self._playback: queue.Queue[bytes | None] = queue.Queue()
        self._engine_workers = [
            threading.Thread(target=self._engine_loop, daemon=True) for _ in range(len(urls) + len(self._removed))
        ]
        self._workers = [
            threading.Thread(target=self._dispatch_loop, daemon=True),
            threading.Thread(target=self._collect_loop, daemon=True),
            threading.Thread(target=self._playback_loop, daemon=True),
            *self._engine_workers,
        ]
        for worker in self._workers:
            worker.start()

    def begin_session(self, session_id: str) -> None:
        self._out_dir = self._root / "sessions" / "audio" / session_id
        self._count = 0
        self.timeline.begin(self._out_dir, session_id)

    def handle(self, event: Any, tag: Any = None) -> None:
        if event.type == "session_start":
            self.begin_session(event.payload["session_id"])
            return
        if event.type == "step_start":
            self._actions[event.payload["talent_id"]] = event.payload.get("action") or ""
            self.timeline.add(
                "step_start", talent_id=event.payload["talent_id"], name=event.payload.get("display_name")
            )
            return
        if event.type != "step_done" or self._out_dir is None:
            return
        talent_id = event.payload["talent_id"]
        self.timeline.add(
            "step_done", talent_id=talent_id, name=event.payload.get("display_name"), elapsed=event.payload.get("elapsed")
        )
        entry = self._mapping.get(talent_id)
        if entry is None:
            return
        # when_action 指定時は、その文字列を含む step だけを本文全体で読む（同じ人材の別 step は読まない）
        when_action = entry.get("when_action")
        if when_action and when_action not in self._actions.get(talent_id, ""):
            return
        shown = clean_for_speech(event.payload["text"], strip_backstage=not when_action)
        text = apply_dictionary(shown, self._dictionary)
        if not text:
            return
        self._count += 1
        path = self._out_dir / f"{self._count:02d}_{talent_id}.wav"
        self.timeline.add("utterance_text", file=path.name, talent_id=talent_id, text=shown)
        if tag is not None:
            self.tags[path] = tag
        self._queue.put((path, text, entry))

    def close(self, *, wait: bool = True) -> None:
        if not wait:
            self._failed = True
        self._queue.put(None)
        if wait:
            for worker in self._workers:
                worker.join()
        self.timeline.add("end")

    def _dispatch_loop(self) -> None:
        while (job := self._queue.get()) is not None:
            if self._failed:
                continue
            path, text, entry = job
            futures: list[Future[bytes | None]] = []
            for chunk in split_for_speech(text):
                future: Future[bytes | None] = Future()
                self._tasks.put((chunk, entry, future, path.name))
                futures.append(future)
            self._pending.put((path, futures))
        self._pending.put(None)

    def _collect_loop(self) -> None:
        while (job := self._pending.get()) is not None:
            path, futures = job
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
                self.timeline.add("utterance", file=path.name, duration=_safe_duration(path))
                if self._on_utterance:
                    self._on_utterance(path)
        for _ in self._engine_workers:
            self._tasks.put(None)
        self._playback.put(None)

    def _engine_loop(self) -> None:
        while (task := self._tasks.get()) is not None:
            chunk, entry, future, file = task
            try:
                future.set_result(self._synthesize_chunk(chunk, entry, file))
            except Exception as exc:
                future.set_exception(exc)

    def _synthesize_chunk(self, chunk: str, entry: dict[str, Any], file: str = "") -> bytes | None:
        """空いている ENGINE で合成する。None は飛ばした文、または全 ENGINE 停止（_failed）。"""
        while not self._failed:
            self._revive_engines()
            try:
                url = self._idle_engines.get(timeout=1)
            except queue.Empty:
                continue
            self._set_busy(url, True)
            began = self.timeline.now()
            self.timeline.add("synth_start", t=began, engine=url, file=file)
            try:
                wav = synthesize(chunk, entry, url)
            except urllib.error.HTTPError as exc:
                self._log_synth(began, url, file, failed=True)
                self._set_busy(url, False)
                self._idle_engines.put(url)
                print(f"[voice] 合成に失敗したため一部を飛ばします: {exc}", file=sys.stderr)
                return None
            except OSError as exc:
                self._log_synth(began, url, file, failed=True)
                self._set_busy(url, False)
                if self._monitor is not None:
                    self._monitor.mark_off(url)
                with self._engine_lock:
                    self._alive_engines -= 1
                    self._removed.add(url)
                    remaining = self._alive_engines
                if remaining == 0:
                    self._failed = True
                    print(f"[voice] VOICEVOX に接続できないため読み上げを中止します: {exc}", file=sys.stderr)
                    return None
                print(f"[voice] {url} に接続できないため、この ENGINE を外して続けます: {exc}", file=sys.stderr)
                continue
            self._log_synth(began, url, file)
            self._set_busy(url, False)
            self._idle_engines.put(url)
            return wav
        return None

    def _log_synth(self, began: float, url: str, file: str, *, failed: bool = False) -> None:
        extra = {"failed": True} if failed else {}
        self.timeline.add("synth", t=began, end=round(self.timeline.now(), 3), engine=url, file=file, **extra)

    def _set_busy(self, url: str, busy: bool) -> None:
        if self._monitor is not None:
            self._monitor.set_busy(url, busy)

    def _revive_engines(self) -> None:
        """外していた ENGINE が monitor で応答していれば、合成に戻す。"""
        if self._monitor is None or not self._removed:
            return
        with self._engine_lock:
            for url in [u for u in self._removed if self._monitor.is_alive(u)]:
                self._removed.discard(url)
                self._alive_engines += 1
                self._idle_engines.put(url)

    def _playback_loop(self) -> None:
        while (wav := self._playback.get()) is not None:
            if self._play:
                winsound.PlaySound(wav, winsound.SND_MEMORY)

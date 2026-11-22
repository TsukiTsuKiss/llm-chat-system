"""VOICEVOX ENGINE の速さを測る（短・中・長の文、初回と 2 回目以降、同時実行）。"""

from __future__ import annotations

import csv
import io
import json
import statistics
import threading
import time
import urllib.request
import wave
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from studio.voice import DEFAULT_BASE_URL, parse_voicevox_urls, synthesize
from studio.voice_engines import engine_names_by_url, expand_engine_spec, prefer_ipv4

SENTENCES = {
    "short": "こんにちは、今日もよろしくお願いします。",
    "medium": "今日のニュースをお伝えします。国内では、各地で朝から強い雨が降り、交通機関に一部乱れが出ています。",
    "long": (
        "続いて、経済のニュースです。今月の国内の消費者物価は、前の年の同じ月と比べて上昇が続いており、"
        "食料品やエネルギーの値上がりが家計を圧迫しています。専門家は、賃金の伸びが物価に追いつくかどうかが、"
        "今後の景気を左右すると指摘しています。"
    ),
}
SIZES = tuple(SENTENCES)
FIRST_SIZE = "medium"


@dataclass
class Sample:
    engine: str
    url: str
    mode: str  # sequential / concurrent-N
    phase: str  # first / warm
    size: str
    chars: int
    trial: int
    seconds: float
    audio_sec: float | None
    ok: bool
    error: str = ""
    start: float = 0.0  # ベンチマーク開始からの秒（タイムライン表示用）


@dataclass
class ConcurrencyResult:
    concurrency: int
    calls: int
    wall_sec: float
    chars_per_sec: float


@dataclass
class EngineResult:
    name: str
    url: str
    version: str = "?"
    devices: str = "?"
    samples: list[Sample] = field(default_factory=list)
    concurrency: list[ConcurrencyResult] = field(default_factory=list)


def resolve_targets(value: str | None, root: Path) -> list[tuple[str, str]]:
    """測定対象を (名前, URL) にする。未指定は voicevox_engines.json の有効な ENGINE 全部。"""
    urls = parse_voicevox_urls(expand_engine_spec(value, root, DEFAULT_BASE_URL))
    names = engine_names_by_url(root)
    return [(names.get(url) or names.get(prefer_ipv4(url)) or url, url) for url in urls]


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(prefer_ipv4(url), timeout=5) as response:
        return json.loads(response.read())


def fetch_info(url: str) -> tuple[str, str]:
    """(バージョン, 使えるデバイス)。取れなければ "?"。"""
    try:
        version = str(_get_json(f"{url}/version"))
    except (OSError, ValueError):
        version = "?"
    try:
        devices = _get_json(f"{url}/supported_devices")
        names = [key for key, usable in devices.items() if usable]
        device_text = "+".join(names) if names else "?"
    except (OSError, ValueError, AttributeError):
        device_text = "?"
    return version, device_text


def _wav_seconds(wav: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(wav)) as reader:
            return round(reader.getnframes() / reader.getframerate(), 3)
    except (wave.Error, EOFError, ZeroDivisionError):
        return None


def _timed(
    name: str, url: str, entry: dict[str, Any], *, mode: str, phase: str, size: str, trial: int, t0: float
) -> Sample:
    text = SENTENCES[size]
    began = time.perf_counter()
    start = round(began - t0, 3)
    try:
        wav = synthesize(text, entry, url)
    except (OSError, ValueError) as exc:
        seconds = round(time.perf_counter() - began, 3)
        return Sample(name, url, mode, phase, size, len(text), trial, seconds, None, False, str(exc), start)
    seconds = round(time.perf_counter() - began, 3)
    return Sample(name, url, mode, phase, size, len(text), trial, seconds, _wav_seconds(wav), True, "", start)


def measure_engine(
    name: str,
    url: str,
    entry: dict[str, Any],
    *,
    trials: int,
    levels: Sequence[int],
    progress: Callable[[str], None] = lambda message: None,
    cancel: threading.Event | None = None,
    on_sample: Callable[[Sample], None] = lambda sample: None,
    t0: float | None = None,
) -> EngineResult:
    def cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    started = time.perf_counter() if t0 is None else t0
    result = EngineResult(name, url)

    def record(*samples: Sample) -> None:
        result.samples.extend(samples)
        for sample in samples:
            on_sample(sample)

    result.version, result.devices = fetch_info(url)
    progress(f"{name}: 初回の合成")
    first = _timed(name, url, entry, mode="sequential", phase="first", size=FIRST_SIZE, trial=0, t0=started)
    record(first)
    if not first.ok:
        progress(f"{name}: 失敗したため測定を中止: {first.error}")
        return result

    progress(f"{name}: 逐次（短・中・長 各 {trials} 回）")
    for size in SIZES:
        for trial in range(1, trials + 1):
            if cancelled():
                return result
            record(_timed(name, url, entry, mode="sequential", phase="warm", size=size, trial=trial, t0=started))

    warm_medium = [s for s in result.samples if s.phase == "warm" and s.size == FIRST_SIZE and s.ok]
    if warm_medium:
        total = max(sum(s.seconds for s in warm_medium), 0.001)  # 秒は ms に丸めるので 0 になりうる
        result.concurrency.append(
            ConcurrencyResult(1, len(warm_medium), round(total, 3), round(sum(s.chars for s in warm_medium) / total, 2))
        )

    for level in sorted({n for n in levels if n > 1}):
        progress(f"{name}: 同時 {level}（中の文を {level} 本ずつ {trials} 回）")
        wall = 0.0
        ok_chars = 0
        calls = 0
        for trial in range(1, trials + 1):
            if cancelled():
                return result
            began = time.perf_counter()
            with ThreadPoolExecutor(max_workers=level) as pool:
                futures = [
                    pool.submit(
                        _timed,
                        name,
                        url,
                        entry,
                        mode=f"concurrent-{level}",
                        phase="warm",
                        size=FIRST_SIZE,
                        trial=trial,
                        t0=started,
                    )
                    for _ in range(level)
                ]
                samples = [future.result() for future in futures]
            wall += time.perf_counter() - began
            record(*samples)
            ok_samples = [s for s in samples if s.ok]
            calls += len(ok_samples)
            ok_chars += sum(s.chars for s in ok_samples)
        if wall > 0 and calls:
            result.concurrency.append(ConcurrencyResult(level, calls, round(wall, 3), round(ok_chars / wall, 2)))
    return result


def run_benchmark(
    targets: Sequence[tuple[str, str]],
    *,
    speaker: int,
    trials: int,
    levels: Sequence[int],
    progress: Callable[[str], None] = lambda message: None,
    cancel: threading.Event | None = None,
    on_sample: Callable[[Sample], None] = lambda sample: None,
) -> list[EngineResult]:
    """ENGINE は別の PC なので、ENGINE どうしは並行して測り、ENGINE 内は順に測る。"""
    entry = {"speaker": speaker}
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, len(targets))) as pool:
        futures = [
            pool.submit(
                measure_engine,
                name,
                url,
                entry,
                trials=trials,
                levels=levels,
                progress=progress,
                cancel=cancel,
                on_sample=on_sample,
                t0=t0,
            )
            for name, url in targets
        ]
        return [future.result() for future in futures]


def fit_line(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """seconds = 固定の遅れ + 1 文字あたり × 文字数 の最小二乗。(固定の遅れ, 1 文字あたり秒)。"""
    if len(points) < 2:
        return None
    mean_x = statistics.fmean(x for x, _ in points)
    mean_y = statistics.fmean(y for _, y in points)
    variance = sum((x - mean_x) ** 2 for x, _ in points)
    if variance == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / variance
    return mean_y - slope * mean_x, slope


def _warm_sequential(result: EngineResult, size: str | None = None) -> list[Sample]:
    return [
        s
        for s in result.samples
        if s.ok and s.mode == "sequential" and s.phase == "warm" and (size is None or s.size == size)
    ]


def _median_seconds(samples: Sequence[Sample]) -> float | None:
    return statistics.median(s.seconds for s in samples) if samples else None


def _fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def build_markdown(results: Sequence[EngineResult], meta: dict[str, Any]) -> str:
    levels = sorted({c.concurrency for r in results for c in r.concurrency})
    lines = [
        "# VOICEVOX ENGINE ベンチマーク",
        "",
        f"- 日時: {meta['started']}",
        f"- 話者 ID: {meta['speaker']} / 各 {meta['trials']} 回 / 同時実行: {', '.join(str(n) for n in meta['levels'])}",
        "- 文の長さ: "
        + " / ".join(f"{size} {len(text)} 文字" for size, text in SENTENCES.items())
        + "。時間は audio_query と synthesis を合わせた秒（実際の読み上げと同じ）",
        "",
        "## 速さ（2 回目以降の中央値）",
        "",
        "| ENGINE | version | デバイス | 初回(秒) | 短(秒) | 中(秒) | 長(秒) | 固定の遅れ(秒) | 1文字(ms) |"
        + "".join(f" 同時{n}(文字/秒) |" for n in levels),
        "|---|---|---|---|---|---|---|---|---|" + "---|" * len(levels),
    ]
    for result in results:
        first = next((s for s in result.samples if s.phase == "first"), None)
        medians = [_median_seconds(_warm_sequential(result, size)) for size in SIZES]
        fit = fit_line([(s.chars, s.seconds) for s in _warm_sequential(result)])
        by_level = {c.concurrency: c.chars_per_sec for c in result.concurrency}
        first_text = "失敗" if first is not None and not first.ok else _fmt(first.seconds if first else None)
        lines.append(
            f"| {result.name} | {result.version} | {result.devices} | {first_text} | "
            + " | ".join(_fmt(m) for m in medians)
            + f" | {_fmt(fit[0] if fit else None)} | {_fmt(fit[1] * 1000 if fit else None, 1)} |"
            + "".join(f" {_fmt(by_level.get(n), 1)} |" for n in levels)
        )
    failures = [s for r in results for s in r.samples if not s.ok]
    if failures:
        lines += ["", "## 失敗", ""]
        for s in failures[:20]:
            lines.append(f"- {s.engine} / {s.mode} / {s.size}: {s.error}")
        if len(failures) > 20:
            lines.append(f"- ほか {len(failures) - 20} 件")
    lines += [
        "",
        "見方: 初回はモデル読み込みを含む。固定の遅れと 1 文字あたりは、逐次の全サンプルを直線で近似した値。",
        "同時 N の文字/秒は、中の文を N 本同時に投げたときの合計の処理速度（1 は逐次）。大きいほど並列が効いている。",
        "",
    ]
    return "\n".join(lines)


def write_results(out_root: Path, results: Sequence[EngineResult], meta: dict[str, Any]) -> Path:
    out_dir = out_root / f"voice_{meta['stamp']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = [f.name for f in fields(Sample)]
    with (out_dir / "samples.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for result in results:
            for sample in result.samples:
                writer.writerow(asdict(sample))
    (out_dir / "report.md").write_text(build_markdown(results, meta), encoding="utf-8")
    return out_dir


def make_meta(speaker: int, trials: int, levels: Sequence[int]) -> dict[str, Any]:
    now = datetime.now()
    return {
        "started": now.strftime("%Y-%m-%d %H:%M:%S"),
        "stamp": now.strftime("%Y%m%d_%H%M%S"),
        "speaker": speaker,
        "trials": trials,
        "levels": list(levels),
    }

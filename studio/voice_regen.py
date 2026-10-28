"""保存済みセッションの音声（wav）を、記録した発言本文から作り直す（design.md §7.9.1）。

声は今の voice_mapping.json と読み辞書で合成するため、記録時と変わりうる。force=True で既存の wav も作り直す。
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from studio import voice
from studio.voice_timeline import replay_data


@dataclass
class RegenResult:
    created: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    message: str = ""


def missing_audio_files(root: Path, session_id: str) -> list[str]:
    """記録に本文があり、wav が無い発言のファイル名。記録がなければ空。"""
    try:
        data = replay_data(root, session_id)
    except FileNotFoundError:
        return []
    audio_dir = Path(root) / "sessions" / "audio" / session_id
    return [
        e["file"] for e in data["events"] if e.get("kind") == "utterance_text" and not (audio_dir / e["file"]).is_file()
    ]


def regenerate_audio(root: Path, session_id: str, *, urls: list[str], force: bool = False) -> RegenResult:
    """wav が無い発言（force なら全発言）を、接続できる ENGINE に分けて合成し直す。"""
    data = replay_data(root, session_id)
    audio_dir = Path(root) / "sessions" / "audio" / session_id
    targets = [
        e
        for e in data["events"]
        if e.get("kind") == "utterance_text" and (force or not (audio_dir / e["file"]).is_file())
    ]
    result = RegenResult()
    if not targets:
        result.message = "再生成が必要な音声はありません"
        return result

    engines = [url for url in urls if voice.engine_available(url)]
    if not engines:
        result.failed = [e["file"] for e in targets]
        result.message = "VOICEVOX に接続できないため、音声を作り直せません"
        return result

    organization = data.get("organization") or ""
    mapping = voice.load_voice_mapping(root, organization) if organization else {}
    dictionary = voice.load_voice_dictionary(root, organization)

    jobs: list[tuple[str, list[Future[bytes]]]] = []
    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        count = 0
        for event in targets:
            entry = mapping.get(event["talent_id"])
            if entry is None:
                result.failed.append(event["file"])
                continue
            chunks = voice.split_for_speech(voice.apply_dictionary(event["text"], dictionary))
            futures: list[Future[bytes]] = []
            for chunk in chunks:
                futures.append(pool.submit(voice.synthesize, chunk, entry, engines[count % len(engines)]))
                count += 1
            jobs.append((event["file"], futures))

        for file, futures in jobs:
            wavs: list[bytes] = []
            for future in futures:
                try:
                    wavs.append(future.result())
                except OSError:
                    continue
            if not wavs:
                result.failed.append(file)
                continue
            path = audio_dir / file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(voice.join_wavs(wavs))
            result.created.append(file)

    result.message = f"音声を {len(result.created)} 件作り直しました"
    if result.failed:
        result.message += f"（{len(result.failed)} 件は作れませんでした）"
    return result

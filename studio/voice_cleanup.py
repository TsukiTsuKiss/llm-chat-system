"""古い読み上げ音声（wav）を整理する（design.md §7.9.1）。

timeline.jsonl とセッションログは残し、発言本文から作り直せるセッションの wav だけを対象にする。
既定は一覧のみ。--apply を付けたときだけ削除する。

    python -m studio.voice_cleanup --older-than-days 3
    python -m studio.voice_cleanup --keep-latest 10 --apply
    python -m studio.voice_cleanup --older-than-days 3 --include-unregenerable
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from studio.voice_timeline import replay_data

# 書き込み中のセッションを消さないための猶予
ACTIVE_SECONDS = 600


@dataclass
class Candidate:
    session_id: str
    files: list[Path] = field(default_factory=list)
    size: int = 0
    action: str = "keep"  # delete / keep / skip
    reason: str = ""


def _regenerable(root: Path, session_id: str) -> str:
    """作り直せなければ理由を返す。作り直せるなら空文字。"""
    try:
        events = replay_data(root, session_id)["events"]
    except FileNotFoundError:
        return "タイミングの記録がない"
    texts = {e["file"] for e in events if e.get("kind") == "utterance_text"}
    missing = [e["file"] for e in events if e.get("kind") == "utterance" and e["file"] not in texts]
    return "発言本文が揃わない" if missing or not texts else ""


def plan(
    root: Path,
    *,
    older_than_days: int | None = None,
    keep_latest: int | None = None,
    include_unregenerable: bool = False,
    now: datetime | None = None,
) -> list[Candidate]:
    audio_root = Path(root) / "sessions" / "audio"
    now = now or datetime.now()
    items: list[Candidate] = []
    for directory in sorted((p for p in audio_root.iterdir() if p.is_dir()), reverse=True) if audio_root.is_dir() else []:
        wavs = sorted(directory.glob("*.wav"))
        if wavs:
            items.append(Candidate(directory.name, wavs, sum(f.stat().st_size for f in wavs)))

    for index, item in enumerate(items):
        if keep_latest is not None and index < keep_latest:
            item.reason = "最新"
            continue
        if older_than_days is not None:
            try:
                started = datetime.strptime(item.session_id, "%Y%m%d_%H%M%S")
            except ValueError:
                item.action, item.reason = "skip", "日時が読み取れない"
                continue
            if started > now - timedelta(days=older_than_days):
                item.reason = "新しい"
                continue
        if time.time() - max(f.stat().st_mtime for f in item.files) < ACTIVE_SECONDS:
            item.action, item.reason = "skip", "更新から 10 分以内"
            continue
        reason = _regenerable(Path(root), item.session_id)
        if reason and include_unregenerable:
            item.action, item.reason = "delete", f"削除対象（作り直せない: {reason}）"
        elif reason:
            item.action, item.reason = "skip", f"作り直せない（{reason}）"
        else:
            item.action, item.reason = "delete", "削除対象"
    return items


def apply(items: list[Candidate]) -> int:
    """対象の wav を削除し、解放したバイト数を返す。"""
    freed = 0
    for item in items:
        if item.action != "delete":
            continue
        for path in item.files:
            freed += path.stat().st_size
            path.unlink()
    return freed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="古い読み上げ音声（wav）を整理する（既定は一覧のみ）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--older-than-days", type=int, help="この日数より古いセッションの wav を対象にする")
    group.add_argument("--keep-latest", type=int, help="新しい N セッション以外の wav を対象にする")
    parser.add_argument("--apply", action="store_true", help="実際に削除する")
    parser.add_argument(
        "--include-unregenerable",
        action="store_true",
        help="タイミングの記録や発言本文がなく、作り直せないセッションの wav も対象にする（消すと元に戻せない）",
    )
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    items = plan(
        root,
        older_than_days=args.older_than_days,
        keep_latest=args.keep_latest,
        include_unregenerable=args.include_unregenerable,
    )
    for item in items:
        print(f"{item.action:6} {item.size / 1_048_576:7.1f} MB  {len(item.files):3d} 本  {item.session_id}  {item.reason}")
    target = sum(i.size for i in items if i.action == "delete")
    print(f"削除対象: {sum(1 for i in items if i.action == 'delete')} セッション / {target / 1_048_576:.1f} MB")
    if not args.apply:
        print("（一覧のみ。削除するには --apply を付けてください）")
        return 0
    print(f"削除しました: {apply(items) / 1_048_576:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

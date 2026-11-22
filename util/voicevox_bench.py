"""VOICEVOX ENGINE の速さを測る。

例: python util/voicevox_bench.py                       # voicevox_engines.json の有効な ENGINE 全部
    python util/voicevox_bench.py --engine nuc7i7dnhe,kuroodoshi --trials 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio.voice_bench import make_meta, resolve_targets, run_benchmark, write_results  # noqa: E402
from studio.voice_engines import EngineConfigError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="VOICEVOX ENGINE の速さを測る（結果は CSV と Markdown に出力）")
    parser.add_argument("--root", default=".", help="プロジェクトルート（voicevox_engines.json のある場所）")
    parser.add_argument(
        "--engine",
        default=None,
        help="対象の ENGINE（登録名か URL。カンマ区切り。既定: voicevox_engines.json の有効な ENGINE 全部）",
    )
    parser.add_argument("--speaker", type=int, default=1, help="話者（スタイル）ID（既定: 1）")
    parser.add_argument("--trials", type=int, default=3, help="短・中・長を各何回ずつ測るか（既定: 3）")
    parser.add_argument("--concurrency", default="1,2,3", help="同時実行数（カンマ区切り。既定: 1,2,3）")
    parser.add_argument("--out", default="benchmark_results", help="結果の出力先（既定: benchmark_results）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    try:
        levels = [int(item) for item in args.concurrency.split(",") if item.strip()]
        targets = resolve_targets(args.engine, root)
    except (ValueError, EngineConfigError) as exc:
        parser.error(str(exc))
    if args.trials < 1 or not levels or min(levels) < 1:
        parser.error("--trials と --concurrency は 1 以上にしてください")

    print(f"[bench] 対象: {', '.join(f'{name}={url}' for name, url in targets)}")
    meta = make_meta(args.speaker, args.trials, levels)
    results = run_benchmark(
        targets,
        speaker=args.speaker,
        trials=args.trials,
        levels=levels,
        progress=lambda message: print(f"[bench] {message}", flush=True),
    )
    out_dir = write_results(root / args.out, results, meta)
    print((out_dir / "report.md").read_text(encoding="utf-8"))
    print(f"[bench] 出力: {out_dir}")
    return 0 if any(r.samples and r.samples[0].ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

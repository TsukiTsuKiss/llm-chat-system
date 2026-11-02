"""ai_assistants_config.json の各モデルを1回ずつ呼び、実際に使えるかを確認する。

使い方: python check_ai_models.py [--provider Together ...] [--model 部分一致] [--workers 4]
極小のプロンプトを送るので課金は少額だが、API キーのあるプロバイダーでは全モデルに1回ずつ課金される。
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ai_model_sync import probe
from studio.loader import load_ai_assistants
from studio.logging import load_model_costs
from studio.validation import ValidationReport


def main() -> int:
    parser = argparse.ArgumentParser(description="登録モデルの疎通確認")
    parser.add_argument("--provider", nargs="*", help="対象プロバイダー（省略時は全て）")
    parser.add_argument("--model", default=None, help="モデル名の部分一致")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    assistants = load_ai_assistants(root, ValidationReport())
    costs = load_model_costs(root)
    targets = [
        (provider, model)
        for provider, cfg in assistants.items()
        if not args.provider or provider in args.provider
        for model in cfg.get("models", [])
        if not args.model or args.model in model
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda t: (*t, *probe(assistants, costs, *t)), targets))
    for provider, model, ok, detail in results:
        print(f"{'OK' if ok else 'NG'}  {provider}/{model}  {detail}")
    failed = [r for r in results if not r[2]]
    print(f"\n{len(results) - len(failed)}/{len(results)} 件が利用可能")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

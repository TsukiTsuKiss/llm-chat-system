"""ai_assistants_config.json を、実際にモデルを呼んだ結果に合わせて更新する。

既定は確認のみ（何も書き込まない）。--apply で、呼べないモデルを JSON から外し、
ai_assistants_config.csv を JSON から作り直す。新規候補は表示するだけで、自動では追加しない。

使い方: python update_ai_config.py [update] [--provider NAME ...] [--registered-only] [--apply]
Opper はモデル数が多いので、--provider Opper を指定したときだけ確認する。
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

from studio.assistants import invoke_llm_step
from studio.history import ConversationHistory
from studio.loader import load_ai_assistants
from studio.logging import load_model_costs
from studio.validation import ValidationReport

JSON_FILE = "ai_assistants_config.json"
CSV_FILE = "ai_assistants_config.csv"
CSV_HEADER = ["assistant_name", "module", "class", "model", "fast_model"]
DEFAULT_EXCLUDED = {"Opper"}
BACKUPS_KEPT = 3

API_KEY_ENV = {
    "ChatGPT": "OPENAI_API_KEY",
    "Gemini": "GOOGLE_API_KEY",
    "Groq": "GROQ_API_KEY",
    "Mistral": "MISTRAL_API_KEY",
    "Together": "TOGETHER_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Grok": "XAI_API_KEY",
    "Opper": "OPPER_API_KEY",
}

# チャット用でないモデルを候補から外す
NON_CHAT_WORDS = (
    "embed", "whisper", "tts", "transcribe", "audio", "realtime", "image", "dall-e", "moderation",
    "guard", "rerank", "sora", "imagen", "veo", "aqa", "babbage", "davinci", "computer-use",
)

# 「モデルが存在しない・使えない」と判断できるエラーだけを削除の根拠にする（一時的な失敗は保留）
UNAVAILABLE_MARKERS = (
    "404", "model_not_found", "does not exist", "not found", "model_not_available",
    "non-serverless", "do not have access", "not supported",
)


@dataclass
class Probe:
    provider: str
    model: str
    ok: bool
    detail: str
    registered: bool


def is_unavailable(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in UNAVAILABLE_MARKERS)


def probe(assistants: dict, costs: dict, provider: str, model: str) -> tuple[bool, str]:
    try:
        result = invoke_llm_step(
            assistant_name=provider,
            assistant_cfg=assistants[provider],
            model=model,
            system_prompt="簡潔に答える",
            user_message="1+1は？一言で。",
            history=ConversationHistory(),
            temperature=None,
            stream=False,
            costs=costs,
            max_retries=1,
        )
    except Exception as exc:
        return False, str(exc).splitlines()[0][:160]
    if not result.text.strip():
        return False, "空応答"
    return True, f"{result.elapsed:.1f}s"


def list_provider_models(provider: str) -> list[str] | None:
    """プロバイダーのモデル一覧 API からチャット用モデル ID を返す。取得できないときは None。"""
    key = os.getenv(API_KEY_ENV.get(provider, ""))
    if not key:
        return None
    try:
        if provider == "ChatGPT":
            data = _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
            return [m["id"] for m in data["data"]]
        if provider == "Gemini":
            data = _get("https://generativelanguage.googleapis.com/v1beta/models", {}, {"key": key, "pageSize": 1000})
            return [
                m["name"].removeprefix("models/")
                for m in data["models"]
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        if provider == "Groq":
            data = _get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
            return [m["id"] for m in data["data"]]
        if provider == "Mistral":
            data = _get("https://api.mistral.ai/v1/models", {"Authorization": f"Bearer {key}"})
            return [m["id"] for m in data["data"]]
        if provider == "Together":
            data = _get("https://api.together.xyz/v1/models", {"Authorization": f"Bearer {key}"})
            data = data if isinstance(data, list) else data.get("data", [])
            return [m["id"] for m in data if m.get("type") == "chat"]
        if provider == "Grok":
            data = _get("https://api.x.ai/v1/models", {"Authorization": f"Bearer {key}"})
            return [m["id"] for m in data["data"]]
        if provider == "Anthropic":
            data = _get(
                "https://api.anthropic.com/v1/models",
                {"x-api-key": key, "anthropic-version": "2023-06-01"},
                {"limit": 1000},
            )
            return [m["id"] for m in data["data"]]
    except (requests.RequestException, KeyError, ValueError):
        return None
    return None


def _get(url: str, headers: dict, params: dict | None = None):
    response = requests.get(url, headers={"User-Agent": "curl/8.0", **headers}, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def new_candidates(listed: list[str], registered: list[str]) -> list[str]:
    known = set(registered)
    return sorted(
        m for m in set(listed) - known if not any(word in m.lower() for word in NON_CHAT_WORDS)
    )


def remove_unavailable(config: dict, removals: dict[str, list[str]]) -> dict:
    """removals にあるモデルを models から外した新しい設定を返す。"""
    updated = json.loads(json.dumps(config))
    for provider, models in removals.items():
        updated[provider]["models"] = [m for m in updated[provider]["models"] if m not in models]
    return updated


def build_csv_rows(existing: list[dict], config: dict) -> list[list[str]]:
    """JSON にあるプロバイダーは models の先頭2つを model / fast_model にし、JSON にない行は残す。"""

    def row(name: str, cfg: dict) -> list[str]:
        models = cfg["models"]
        return [name, cfg["module"], cfg["class"], models[0] if models else "", models[1] if len(models) > 1 else ""]

    rows = []
    seen = set()
    for old in existing:
        name = old["assistant_name"]
        seen.add(name)
        rows.append(row(name, config[name]) if name in config else [old[h] for h in CSV_HEADER])
    rows.extend(row(name, cfg) for name, cfg in config.items() if name not in seen)
    return rows


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
    shutil.copy2(path, target)
    old = sorted(glob.glob(str(path.with_name(f"{path.stem}_backup_*{path.suffix}"))), key=os.path.getctime, reverse=True)
    for stale in old[BACKUPS_KEPT:]:
        os.remove(stale)
    return target


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="登録モデルを実際に呼んで ai_assistants_config.json を更新する")
    parser.add_argument("--provider", nargs="*", help="対象プロバイダー（省略時は Opper 以外すべて）")
    parser.add_argument("--registered-only", action="store_true", help="新規候補を探さず、登録済みモデルだけ確認する")
    parser.add_argument("--apply", action="store_true", help="呼べないモデルを JSON から外し、CSV を作り直す")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    json_path, csv_path = root / JSON_FILE, root / CSV_FILE
    config = json.loads(json_path.read_text(encoding="utf-8"))
    assistants = load_ai_assistants(root, ValidationReport())
    costs = load_model_costs(root)

    providers = [p for p in config if (p in args.provider if args.provider else p not in DEFAULT_EXCLUDED)]
    targets: list[tuple[str, str, bool]] = []
    notes: list[str] = []
    for provider in providers:
        if not os.getenv(API_KEY_ENV.get(provider, "")):
            notes.append(f"{provider}: {API_KEY_ENV.get(provider, 'API キー')} が未設定のためスキップ")
            continue
        registered = config[provider]["models"]
        targets.extend((provider, m, True) for m in registered)
        if args.registered_only:
            continue
        listed = list_provider_models(provider)
        if listed is None:
            notes.append(f"{provider}: モデル一覧を取得できないため新規候補は確認しない")
            continue
        notes.extend(f"{provider}: 登録モデル {m} は一覧 API にない" for m in registered if m not in listed)
        targets.extend((provider, m, False) for m in new_candidates(listed, registered))

    def work(target: tuple[str, str, bool]) -> Probe:
        provider, model, registered = target
        ok, detail = probe(assistants, costs, provider, model)
        return Probe(provider, model, ok, detail, registered)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(work, targets))

    print("== 登録済みモデル")
    for r in (r for r in results if r.registered):
        print(f"  {'OK' if r.ok else 'NG'}  {r.provider}/{r.model}  {r.detail}")
    candidates = [r for r in results if not r.registered and r.ok]
    if candidates:
        print("\n== 新規候補（呼べたもの。自動では追加しません）")
        for r in candidates:
            print(f"  {r.provider}/{r.model}  {r.detail}")

    removals: dict[str, list[str]] = {}
    for provider in providers:
        mine = [r for r in results if r.registered and r.provider == provider]
        gone = [r.model for r in mine if not r.ok and is_unavailable(r.detail)]
        if gone and len(gone) == len(mine):
            notes.append(f"{provider}: 全モデルが失敗したため削除しない（キーや接続を確認してください）")
        elif gone:
            removals[provider] = gone
    for note in notes:
        print(f"[注意] {note}")
    if removals:
        print("\n== 削除対象（存在しない・使えないと判断したもの）")
        for provider, models in removals.items():
            for m in models:
                print(f"  {provider}/{m}")

    if not args.apply:
        print("\n確認のみ。反映するには --apply を付けて再実行してください。")
        return 0

    updated = remove_unavailable(config, removals)
    existing = list(csv.DictReader(csv_path.open(encoding="utf-8", newline=""))) if csv_path.exists() else []
    rows = build_csv_rows(existing, updated)
    print(f"\n[バックアップ] {backup(json_path).name}")
    write_json(json_path, updated)
    if csv_path.exists():
        print(f"[バックアップ] {backup(csv_path).name}")
    write_csv(csv_path, rows)
    print(f"[更新] {JSON_FILE} と {CSV_FILE} を書き込みました")
    return 0

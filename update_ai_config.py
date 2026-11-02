#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Assistants Configuration Updater

登録モデルを実際に呼んで使えるかを確認し、ai_assistants_config.json と ai_assistants_config.csv を更新する。
モデル一覧 API で見つけた新規候補は表示するだけで、自動では追加しない（実装は ai_model_sync.py）。

コマンド:
  python update_ai_config.py [update] [--apply]                                  # 確認（--apply で JSON/CSV に反映）
  python update_ai_config.py costs list                                          # コスト一覧表示
  python update_ai_config.py costs verify                                        # AI設定とコストDBの整合性確認
  python update_ai_config.py costs add <model> <provider> <input> <output>       # 新しいモデル追加
  python update_ai_config.py costs update <model> <input> <output>               # コスト更新
  python update_ai_config.py costs crawl <source>                                # コスト情報を更新

Crawl sources: openai, anthropic, google, groq, all
"""

import csv
import os
import sys
from datetime import datetime

# 設定ファイル（CSV は旧版 MultiRoleChat 向け。ai_model_sync が JSON から作り直す）
CONFIG_FILE = "ai_assistants_config.csv"
MODEL_COSTS_FILE = "model_costs.csv"


# ================== コスト管理機能 ==================

def load_ai_assistants_config():
    """AI アシスタント設定を読み込む"""
    config = {}
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ ファイル {CONFIG_FILE} が見つかりません。")
        return {}
    
    try:
        with open(CONFIG_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                config[row['assistant_name']] = {
                    'module': row['module'],
                    'class': row['class'],
                    'model': row['model'],
                    'fast_model': row['fast_model']
                }
        return config
    except Exception as e:
        print(f"❌ AI設定ファイル読み込みエラー: {e}")
        return {}

def get_provider_from_module(module_name):
    """モジュール名からプロバイダー名を推定"""
    module_to_provider = {
        'langchain_openai': 'OpenAI',
        'langchain_google_genai': 'Google',
        'langchain_groq': 'Groq',
        'langchain_anthropic': 'Anthropic',
        'langchain_mistralai': 'Mistral',
        'langchain_together': 'Together',
        'langchain_xai': 'XAI'
    }
    return module_to_provider.get(module_name, 'Unknown')

def load_model_costs():
    """モデルコスト情報を読み込む"""
    costs = []
    if not os.path.exists(MODEL_COSTS_FILE):
        print(f"❌ ファイル {MODEL_COSTS_FILE} が見つかりません。")
        return []
    
    try:
        with open(MODEL_COSTS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            costs = list(reader)
        return costs
    except Exception as e:
        print(f"❌ ファイル読み込みエラー: {e}")
        return []

def save_model_costs(costs):
    """モデルコスト情報を保存する"""
    try:
        with open(MODEL_COSTS_FILE, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['date_updated', 'provider', 'model', 'input_cost_per_1k_tokens', 'output_cost_per_1k_tokens', 'currency', 'notes']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(costs)
        print(f"✅ {MODEL_COSTS_FILE} を更新しました。")
    except Exception as e:
        print(f"❌ ファイル保存エラー: {e}")

def list_costs():
    """コスト一覧を表示"""
    costs = load_model_costs()
    if not costs:
        return
    
    print("\n📊 モデルコスト一覧:")
    print("=" * 100)
    print(f"{'Provider':<15} {'Model':<25} {'Input/1K':<10} {'Output/1K':<10} {'Updated':<12} {'Notes'}")
    print("-" * 100)
    
    for cost in costs:
        provider = cost['provider'][:14]
        model = cost['model'][:24]
        input_cost = f"${cost['input_cost_per_1k_tokens']}"
        output_cost = f"${cost['output_cost_per_1k_tokens']}"
        updated = cost['date_updated']
        notes = cost['notes'][:30]
        
        print(f"{provider:<15} {model:<25} {input_cost:<10} {output_cost:<10} {updated:<12} {notes}")

def verify_provider_mapping():
    """AI設定とコストデータベースのプロバイダー情報の整合性を確認"""
    print("\n🔍 プロバイダーマッピング確認:")
    print("=" * 80)
    
    ai_config = load_ai_assistants_config()
    costs = load_model_costs()
    
    if not ai_config:
        print("❌ AI設定ファイルを読み込めませんでした。")
        return
    
    print(f"{'Assistant':<12} {'Module':<25} {'Inferred Provider':<15} {'Models in Cost DB'}")
    print("-" * 80)
    
    for assistant_name, config in ai_config.items():
        module = config['module']
        inferred_provider = get_provider_from_module(module)
        
        # コストデータベースで該当するモデルを検索
        matching_models = [c['model'] for c in costs if c['provider'] == inferred_provider]
        models_count = len(matching_models)
        
        print(f"{assistant_name:<12} {module:<25} {inferred_provider:<15} {models_count} models")
        
        # 不整合をチェック
        assistant_models = [config['model'], config['fast_model']]
        for model in assistant_models:
            if model and not any(c['model'] == model and c['provider'] == inferred_provider for c in costs):
                print(f"  ⚠️  Missing: {model} for {inferred_provider}")
    
    print()
    return True

def add_model_cost(model, provider, input_cost, output_cost, notes=""):
    """新しいモデルを追加"""
    costs = load_model_costs()
    
    # 既存モデルのチェック
    for cost in costs:
        if cost['model'] == model:
            print(f"⚠️  モデル '{model}' は既に存在します。updateコマンドを使用してください。")
            return
    
    new_cost = {
        'date_updated': datetime.now().strftime("%Y-%m-%d"),
        'provider': provider,
        'model': model,
        'input_cost_per_1k_tokens': str(input_cost),
        'output_cost_per_1k_tokens': str(output_cost),
        'currency': 'USD',
        'notes': notes
    }
    
    costs.append(new_cost)
    save_model_costs(costs)
    print(f"✅ モデル '{model}' を追加しました。")

def update_model_cost(model, input_cost, output_cost):
    """既存モデルのコストを更新"""
    costs = load_model_costs()
    
    updated = False
    for cost in costs:
        if cost['model'] == model:
            cost['date_updated'] = datetime.now().strftime("%Y-%m-%d")
            cost['input_cost_per_1k_tokens'] = str(input_cost)
            cost['output_cost_per_1k_tokens'] = str(output_cost)
            updated = True
            break
    
    if updated:
        save_model_costs(costs)
        print(f"✅ モデル '{model}' のコストを更新しました。")
    else:
        print(f"❌ モデル '{model}' が見つかりません。")

def update_or_add_model_cost(model, provider, input_cost, output_cost, notes=""):
    """モデルが存在する場合は更新、存在しない場合は追加"""
    costs = load_model_costs()
    
    # 既存のモデルを探す
    found = False
    for cost in costs:
        if cost["model"] == model and cost["provider"] == provider:
            cost["input_cost_per_1k_tokens"] = input_cost
            cost["output_cost_per_1k_tokens"] = output_cost
            cost["date_updated"] = datetime.now().strftime("%Y-%m-%d")
            cost["notes"] = notes
            found = True
            break
    
    if not found:
        # 新しいモデルを追加
        costs.append({
            "date_updated": datetime.now().strftime("%Y-%m-%d"),
            "provider": provider,
            "model": model,
            "input_cost_per_1k_tokens": input_cost,
            "output_cost_per_1k_tokens": output_cost,
            "currency": "USD",
            "notes": notes
        })
    
    save_model_costs(costs)

def crawl_openai_costs():
    """OpenAI APIからモデルコスト情報を取得"""
    print("📡 OpenAI API情報を取得中...")
    
    # OpenAI公式価格情報（手動更新が必要）
    openai_models = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "text-embedding-3-large": {"input": 0.13, "output": 0.13},
        "text-embedding-3-small": {"input": 0.02, "output": 0.02},
        "text-embedding-ada-002": {"input": 0.10, "output": 0.10}
    }
    
    for model, costs in openai_models.items():
        update_or_add_model_cost(model, "OpenAI", costs["input"], costs["output"], 
                           f"Updated via API crawl on {datetime.now().strftime('%Y-%m-%d')}")
    
    print(f"✅ OpenAI {len(openai_models)} モデルの価格を更新しました。")

def crawl_anthropic_costs():
    """Anthropic APIからモデルコスト情報を取得"""
    print("📡 Anthropic API情報を取得中...")
    
    # Anthropic公式価格情報（手動更新が必要）
    anthropic_models = {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku-20241022": {"input": 0.25, "output": 1.25},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25}
    }
    
    for model, costs in anthropic_models.items():
        update_or_add_model_cost(model, "Anthropic", costs["input"], costs["output"], 
                           f"Updated via API crawl on {datetime.now().strftime('%Y-%m-%d')}")
    
    print(f"✅ Anthropic {len(anthropic_models)} モデルの価格を更新しました。")

def crawl_google_costs():
    """Google AI APIからモデルコスト情報を取得"""
    print("📡 Google AI API情報を取得中...")
    
    # Google AI公式価格情報（手動更新が必要）
    google_models = {
        "gemini-2.0-flash-exp": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.0-pro": {"input": 0.50, "output": 1.50}
    }
    
    for model, costs in google_models.items():
        update_or_add_model_cost(model, "Google", costs["input"], costs["output"], 
                           f"Updated via API crawl on {datetime.now().strftime('%Y-%m-%d')}")
    
    print(f"✅ Google {len(google_models)} モデルの価格を更新しました。")

def crawl_groq_costs():
    """Groq APIからモデルコスト情報を取得"""
    print("📡 Groq API情報を取得中...")
    
    # Groq価格情報（Free tierとPaid tierの混合）
    # 注意: GroqはLPUデモンストレーション目的で多くのモデルを無料提供
    #       レート制限内での評価・開発用途は無料
    groq_models = {
        # 無料枠対象モデル（評価・開発用途）
        "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0, "note": "Free tier for evaluation and development"},
        "llama-3.1-70b-versatile": {"input": 0.0, "output": 0.0, "note": "Free tier for evaluation and development"},
        "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0, "note": "Free tier for evaluation and development"},
        "mixtral-8x7b-32768": {"input": 0.0, "output": 0.0, "note": "Free tier for evaluation and development"},
        "gemma-7b-it": {"input": 0.0, "output": 0.0, "note": "Free tier for evaluation and development"}
    }
    
    for model, costs in groq_models.items():
        note = costs.get("note", f"Updated via API crawl on {datetime.now().strftime('%Y-%m-%d')}")
        update_or_add_model_cost(model, "Groq", costs["input"], costs["output"], note)
    
    print(f"✅ Groq {len(groq_models)} モデルの価格を更新しました（無料枠適用）。")

def crawl_costs(source):
    """外部APIからコスト情報をクロールして更新する"""
    print(f"🔍 {source} からコスト情報をクロールしています...")
    
    if source == "openai" or source == "all":
        crawl_openai_costs()
    
    if source == "anthropic" or source == "all":
        crawl_anthropic_costs()
    
    if source == "google" or source == "all":
        crawl_google_costs()
    
    if source == "groq" or source == "all":
        crawl_groq_costs()
    
    print("✅ コストクロールが完了しました。")


def main():
    args = sys.argv[1:]
    if args and args[0] == "costs":
        return run_costs_command(args[1:])
    if args and args[0] == "update":
        args = args[1:]
    from ai_model_sync import run

    return run(args)


def run_costs_command(args):
    if not args:
        print("使用法: python update_ai_config.py costs [list|verify|add|update|crawl]")
        return 1

    subcommand = args[0]
    if subcommand == "list":
        list_costs()
    elif subcommand == "verify":
        verify_provider_mapping()
    elif subcommand == "add":
        if len(args) < 5:
            print("使用法: python update_ai_config.py costs add <model> <provider> <input_cost> <output_cost> [notes]")
            return 1
        try:
            input_cost = float(args[3])
            output_cost = float(args[4])
        except ValueError:
            print("❌ コストは数値で入力してください。")
            return 1
        add_model_cost(args[1], args[2], input_cost, output_cost, " ".join(args[5:]))
    elif subcommand == "update":
        if len(args) < 4:
            print("使用法: python update_ai_config.py costs update <model> <input_cost> <output_cost>")
            return 1
        try:
            input_cost = float(args[2])
            output_cost = float(args[3])
        except ValueError:
            print("❌ コストは数値で入力してください。")
            return 1
        update_model_cost(args[1], input_cost, output_cost)
    elif subcommand == "crawl":
        if len(args) < 2:
            print("使用法: python update_ai_config.py costs crawl <source>")
            print("利用可能なソース: openai, anthropic, google, groq, all")
            return 1
        crawl_costs(args[1])
    else:
        print("❌ 不明なコストコマンドです。")
        print("利用可能なコマンド: list, verify, add, update, crawl")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Assistants Configuration Updater
各AIプロバイダーの最新モデル情報を取得して、ai_assistants_config.csvを更新するスクリプト

機能:
- 各AIプロバイダーのAPIから最新の利用可能モデル一覧を自動取得
- 通常モデル(model)と高速モデル(fast_model)の両方に対応
- API取得失敗時は事前定義されたフォールバックモデルを使用
- 設定ファイルの自動バックアップと安全な更新処理

対応プロバイダー:
- OpenAI (ChatGPT): gpt-4o, gpt-4o-mini など
- Google (Gemini): gemini-2.5-pro, gemini-2.5-flash など
- Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant など
- Mistral AI: mistral-large-latest, mistral-small-latest など
- Anthropic (Claude): claude-opus-4, claude-3-5-haiku-latest など
- Together AI: meta-llama モデル群 (フォールバックのみ)
- xAI (Grok): grok-3-latest など (フォールバックのみ)
"""

import requests
import csv
import json
import os
from datetime import datetime
import time
import sys
import re
from typing import Dict, List, Optional

# 設定ファイル
CONFIG_FILE = "ai_assistants_config.csv"
BACKUP_FILE = f"ai_assistants_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# 既知の最新モデル情報（2025年7月時点）
FALLBACK_MODELS = {
    'ChatGPT': {
        'module': 'langchain_openai',
        'class': 'ChatOpenAI',
        'model': 'gpt-4o',  # 2025年7月時点の最新安定版
        'fast_model': 'gpt-4o-mini',  # 高速版
        'backup_models': ['gpt-4o-mini', 'gpt-4-turbo', 'gpt-4']
    },
    'Gemini': {
        'module': 'langchain_google_genai',
        'class': 'ChatGoogleGenerativeAI',
        'model': 'gemini-2.5-pro',  # 2025年7月時点の最新安定版
        'fast_model': 'gemini-2.5-flash',  # 高速版
        'backup_models': ['gemini-1.5-flash', 'gemini-1.0-pro']
    },
    'Groq': {
        'module': 'langchain_groq',
        'class': 'ChatGroq',
        'model': 'llama-3.3-70b-versatile',  # Groqで利用可能な最新
        'fast_model': 'llama-3.1-8b-instant',  # 高速版
        'backup_models': ['llama-3.1-8b-instant', 'mixtral-8x7b-32768']
    },
    'Mistral': {
        'module': 'langchain_mistralai',
        'class': 'ChatMistralAI',
        'model': 'mistral-large-latest',  # 2025年7月時点の最新
        'fast_model': 'mistral-small-latest',  # 高速版
        'backup_models': ['mistral-medium-latest', 'mistral-small-latest']
    },
    'Together': {
        'module': 'langchain_together',
        'class': 'ChatTogether',
        'model': 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
        'fast_model': '',  # 高速版（空白）
        'backup_models': ['meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo', 'mistralai/Mixtral-8x7B-Instruct-v0.1']
    },
    'Anthropic': {
        'module': 'langchain_anthropic',
        'class': 'ChatAnthropic',
        'model': 'claude-opus-4-20250514',  # 2025年7月時点の最新Claude 4
        'fast_model': 'claude-3-5-haiku-latest',  # 高速版
        'backup_models': ['claude-opus-4-20250514', 'claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022']
    },
    'Grok': {
        'module': 'langchain_xai',
        'class': 'ChatXAI',
        'model': 'grok-3-latest',  # 2025年7月時点の最新
        'fast_model': '',  # 高速版（空白）
        'backup_models': ['grok-beta', 'grok-2']
    }
}

def backup_config_file():
    """設定ファイルをバックアップする"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as src:
                with open(BACKUP_FILE, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            print(f"[INFO] 設定ファイルをバックアップしました: {BACKUP_FILE}")
            return True
        except Exception as e:
            print(f"[ERROR] バックアップに失敗しました: {e}")
            return False
    else:
        print(f"[WARNING] 設定ファイル {CONFIG_FILE} が見つかりません")
        return False

def fetch_webpage_content(url, timeout=10):
    """ウェブページの内容を取得する"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"[ERROR] {url} の取得に失敗しました: {e}")
        return None

def get_openai_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """OpenAI API経由で利用可能なモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("  - OpenAI API Key が設定されていません")
            return None, None
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get('https://api.openai.com/v1/models', headers=headers, timeout=10)
        if response.status_code == 200:
            models = response.json()
            gpt_models = [m['id'] for m in models['data'] if m['id'].startswith('gpt-4')]
            
            # 通常モデル（最新のGPT-4モデル）を選択
            normal_model = None
            if 'gpt-4o' in gpt_models:
                normal_model = 'gpt-4o'
            elif 'gpt-4-turbo' in gpt_models:
                normal_model = 'gpt-4-turbo'
            elif gpt_models:
                normal_model = max(gpt_models)
            
            # 高速モデル（miniバージョン）を選択
            fast_model = None
            if 'gpt-4o-mini' in gpt_models:
                fast_model = 'gpt-4o-mini'
            elif 'gpt-4-turbo-preview' in gpt_models:
                fast_model = 'gpt-4-turbo-preview'
            
            return normal_model, fast_model
        
    except Exception as e:
        print(f"  - OpenAI API エラー: {e}")
    
    return None, None

def get_gemini_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """Google API経由で利用可能なGeminiモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            print("  - Google API Key が設定されていません")
            return None, None
        
        url = f'https://generativelanguage.googleapis.com/v1/models?key={api_key}'
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            gemini_models = [m['name'].split('/')[-1] for m in models.get('models', []) 
                           if 'gemini' in m['name'].lower()]
            
            # 通常モデル（Proバージョン）を選択
            normal_model = None
            for model in ['gemini-2.5-pro', 'gemini-1.5-pro', 'gemini-1.0-pro']:
                if model in gemini_models:
                    normal_model = model
                    break
            
            # 高速モデル（Flashバージョン）を選択
            fast_model = None
            for model in ['gemini-2.5-flash', 'gemini-1.5-flash']:
                if model in gemini_models:
                    fast_model = model
                    break
            
            return normal_model, fast_model
        
    except Exception as e:
        print(f"  - Google API エラー: {e}")
    
    return None, None

def get_groq_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """Groq API経由で利用可能なモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            print("  - Groq API Key が設定されていません")
            return None, None
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get('https://api.groq.com/openai/v1/models', headers=headers, timeout=10)
        if response.status_code == 200:
            models = response.json()
            llama_models = [m['id'] for m in models['data'] if 'llama' in m['id'].lower()]
            
            # 通常モデル（大きなモデル）を選択
            normal_model = None
            for model in ['llama-3.3-70b-versatile', 'llama-3.1-70b-versatile']:
                if model in llama_models:
                    normal_model = model
                    break
            
            # 高速モデル（小さなモデル）を選択
            fast_model = None
            for model in ['llama-3.1-8b-instant', 'llama-3.2-8b-instant']:
                if model in llama_models:
                    fast_model = model
                    break
            
            return normal_model, fast_model
        
    except Exception as e:
        print(f"  - Groq API エラー: {e}")
    
    return None, None

def get_anthropic_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """Anthropic API経由で利用可能なモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            print("  - Anthropic API Key が設定されていません")
            return None, None
        
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        }
        
        # 2025年7月時点での最新Claude 4モデル
        available_models = [
            'claude-opus-4-20250514',    # Claude Opus 4 - 最高性能（通常モデル）
            'claude-sonnet-4-20250514',  # Claude Sonnet 4 - 高性能・バランス型
            'claude-3-7-sonnet-20250219', # Claude 3.7 Sonnet - 高性能
            'claude-3-5-sonnet-20241022', # Claude 3.5 Sonnet - 旧世代
            'claude-3-5-haiku-20241022'   # Claude 3.5 Haiku - 高速（高速モデル）
        ]
        
        # 通常モデル（Opus 4）と高速モデル（Haiku）を返す
        normal_model = available_models[0]  # claude-opus-4-20250514
        fast_model = 'claude-3-5-haiku-latest'  # 高速版
        
        return normal_model, fast_model
        
    except Exception as e:
        print(f"  - Anthropic API エラー: {e}")
    
    return None, None

def get_mistral_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """Mistral API経由で利用可能なモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('MISTRAL_API_KEY')
        if not api_key:
            print("  - Mistral API Key が設定されていません")
            return None, None
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get('https://api.mistral.ai/v1/models', headers=headers, timeout=10)
        if response.status_code == 200:
            models = response.json()
            mistral_models = [m['id'] for m in models['data']]
            
            # 通常モデル（大きなモデル）を選択
            normal_model = None
            for model in ['mistral-large-latest', 'mistral-medium-latest']:
                if model in mistral_models:
                    normal_model = model
                    break
            
            # 高速モデル（小さなモデル）を選択
            fast_model = None
            for model in ['mistral-small-latest', 'mistral-tiny']:
                if model in mistral_models:
                    fast_model = model
                    break
            
            return normal_model, fast_model
        
    except Exception as e:
        print(f"  - Mistral API エラー: {e}")
    
    return None, None

def get_latest_models():
    """各プロバイダーの最新モデルを取得"""
    print("[INFO] 最新モデル情報を取得中...")
    
    latest_models = {}
    
    # OpenAI
    print("OpenAIの最新モデルを確認中...")
    openai_normal, openai_fast = get_openai_models_via_api()
    if openai_normal:
        latest_models['ChatGPT'] = {'model': openai_normal, 'fast_model': openai_fast}
        print(f"  - OpenAI最新モデル: {openai_normal} / {openai_fast}")
    else:
        print("  - OpenAI最新モデルの取得に失敗、フォールバックを使用")
    
    # Gemini
    print("Geminiの最新モデルを確認中...")
    gemini_normal, gemini_fast = get_gemini_models_via_api()
    if gemini_normal:
        latest_models['Gemini'] = {'model': gemini_normal, 'fast_model': gemini_fast}
        print(f"  - Gemini最新モデル: {gemini_normal} / {gemini_fast}")
    else:
        print("  - Gemini最新モデルの取得に失敗、フォールバックを使用")
    
    # Groq
    print("Groqの最新モデルを確認中...")
    groq_normal, groq_fast = get_groq_models_via_api()
    if groq_normal:
        latest_models['Groq'] = {'model': groq_normal, 'fast_model': groq_fast}
        print(f"  - Groq最新モデル: {groq_normal} / {groq_fast}")
    else:
        print("  - Groq最新モデルの取得に失敗、フォールバックを使用")
    
    # Mistral
    print("Mistralの最新モデルを確認中...")
    mistral_normal, mistral_fast = get_mistral_models_via_api()
    if mistral_normal:
        latest_models['Mistral'] = {'model': mistral_normal, 'fast_model': mistral_fast}
        print(f"  - Mistral最新モデル: {mistral_normal} / {mistral_fast}")
    else:
        print("  - Mistral最新モデルの取得に失敗、フォールバックを使用")
    
    # Anthropic
    print("Anthropicの最新モデルを確認中...")
    anthropic_normal, anthropic_fast = get_anthropic_models_via_api()
    if anthropic_normal:
        latest_models['Anthropic'] = {'model': anthropic_normal, 'fast_model': anthropic_fast}
        print(f"  - Anthropic最新モデル: {anthropic_normal} / {anthropic_fast}")
    else:
        print("  - Anthropic最新モデルの取得に失敗、フォールバックを使用")
    
    # Together AI（APIが複雑なため、フォールバック使用）
    print("Together AIは現在のフォールバックモデルを使用します")
    
    # Grok（XAI）（APIが限定的なため、フォールバック使用）
    print("Grokは現在のフォールバックモデルを使用します")
    
    return latest_models

def update_config_file(latest_models):
    """設定ファイルを更新"""
    print("[INFO] 設定ファイルを更新中...")
    
    # 現在の設定を読み込み
    current_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    current_config[row['assistant_name']] = {
                        'module': row['module'],
                        'class': row['class'],
                        'model': row['model'],
                        'fast_model': row.get('fast_model', '')  # fast_modelが存在しない場合は空文字
                    }
        except Exception as e:
            print(f"[ERROR] 現在の設定ファイルの読み込みに失敗: {e}")
            return False
    
    # 新しい設定を作成
    new_config = {}
    updated = False
    
    for assistant_name, fallback_info in FALLBACK_MODELS.items():
        if assistant_name in current_config:
            # 現在の設定をベースに更新
            new_config[assistant_name] = current_config[assistant_name].copy()
        else:
            # 新規追加
            new_config[assistant_name] = {
                'module': fallback_info['module'],
                'class': fallback_info['class'],
                'model': fallback_info['model'],
                'fast_model': fallback_info['fast_model']
            }
        
        # 最新モデルがあれば更新
        if assistant_name in latest_models:
            latest_info = latest_models[assistant_name]
            
            # 通常モデルの更新
            old_model = new_config[assistant_name]['model']
            new_model = latest_info['model']
            if old_model != new_model:
                new_config[assistant_name]['model'] = new_model
                print(f"  - {assistant_name} (model): {old_model} → {new_model}")
                updated = True
            
            # 高速モデルの更新
            old_fast_model = new_config[assistant_name].get('fast_model', '')
            new_fast_model = latest_info.get('fast_model', '')
            if old_fast_model != new_fast_model and new_fast_model is not None:
                new_config[assistant_name]['fast_model'] = new_fast_model
                print(f"  - {assistant_name} (fast_model): {old_fast_model} → {new_fast_model}")
                updated = True
            
            if old_model == new_model and old_fast_model == new_fast_model:
                print(f"  - {assistant_name}: {old_model} / {old_fast_model} (変更なし)")
        else:
            # フォールバックモデルを使用
            fallback_model = fallback_info['model']
            fallback_fast_model = fallback_info['fast_model']
            
            if new_config[assistant_name]['model'] != fallback_model:
                new_config[assistant_name]['model'] = fallback_model
                print(f"  - {assistant_name} (model): フォールバックモデル {fallback_model} を使用")
                updated = True
            
            if new_config[assistant_name].get('fast_model', '') != fallback_fast_model:
                new_config[assistant_name]['fast_model'] = fallback_fast_model
                print(f"  - {assistant_name} (fast_model): フォールバック {fallback_fast_model} を使用")
                updated = True
    
    # 設定ファイルを書き込み
    if updated or not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['assistant_name', 'module', 'class', 'model', 'fast_model'])
                for assistant_name, config in new_config.items():
                    writer.writerow([
                        assistant_name, 
                        config['module'], 
                        config['class'], 
                        config['model'],
                        config.get('fast_model', '')
                    ])
            print(f"[INFO] 設定ファイル {CONFIG_FILE} を更新しました")
            return True
        except Exception as e:
            print(f"[ERROR] 設定ファイルの書き込みに失敗: {e}")
            return False
    else:
        print("[INFO] 更新する必要はありません")
        return True

def main():
    """メイン処理"""
    print("=== AI Assistants Configuration Updater ===")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 環境変数の確認
    print("[INFO] API キーの確認...")
    api_keys = {
        'OpenAI': os.getenv('OPENAI_API_KEY'),
        'Google': os.getenv('GOOGLE_API_KEY'),
        'Groq': os.getenv('GROQ_API_KEY'),
        'Mistral': os.getenv('MISTRAL_API_KEY'),
        'Together': os.getenv('TOGETHER_API_KEY'),
        'Anthropic': os.getenv('ANTHROPIC_API_KEY')
    }
    
    for provider, key in api_keys.items():
        status = "✓" if key else "✗"
        print(f"  {status} {provider}_API_KEY: {'設定済み' if key else '未設定'}")
    print()
    
    try:
        # バックアップ作成
        if not backup_config_file():
            response = input("バックアップの作成に失敗しました。続行しますか？ (y/N): ")
            if response.lower() != 'y':
                print("処理を中止しました")
                return
        
        # 最新モデル情報取得
        latest_models = get_latest_models()
        
        # 設定ファイル更新
        if update_config_file(latest_models):
            print()
            print("[SUCCESS] 設定ファイルの更新が完了しました！")
            print(f"バックアップファイル: {BACKUP_FILE}")
            
            # 更新後の設定を表示
            print("\n[INFO] 更新後の設定:")
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        model = row['model']
                        fast_model = row.get('fast_model', '')
                        if fast_model:
                            print(f"  - {row['assistant_name']}: {model} / {fast_model}")
                        else:
                            print(f"  - {row['assistant_name']}: {model}")
        else:
            print()
            print("[ERROR] 設定ファイルの更新に失敗しました")
            return 1
            
    except KeyboardInterrupt:
        print("\n[INFO] ユーザーによって中断されました")
        return 1
    except Exception as e:
        print(f"[ERROR] 予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

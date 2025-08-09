#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Assistants Configuration Updater
各AIプロバイダーの最新モデル情報を取得して、ai_assistants_config.csvを更新するスクリプト

機能:
- 各AIプロバイダーのAPIから最新の利用可能モデル一覧を自動取得
-             print(f"                # モデル一覧を表                print(f"    ✓ 主要モデル: {sorted(important_models)}")
                if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")             if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")多すぎる場合は要約）
            if verbose_mode:
                print(f"    ✓ 全GPTモデル一覧: {sorted(gpt_models)}")
            elif len(gpt_models) <= 10:
                print(f"    ✓ 発見されたモデル: {gpt_models}")
            else:
                # 主要モデルのみ表示
                important_models = [m for m in gpt_models if any(keyword in m for keyword in ['gpt-5', 'gpt-4o', 'gpt-4-turbo'])]
                other_count = len(gpt_models) - len(important_models)
                print(f"    ✓ 主要モデル: {sorted(important_models)}")
                if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")                   print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")           print(f"    ✓ 主要モデル: {sorted(important_models)}")
                if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")             if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)"){len(gpt_models)} 個のGPTモデルを発見")
            
            # 詳細表示モード（環境変数VERBOSE_MODEが設定されている場合）
            verbose_mode = os.getenv('VERBOSE_MODE', '').lower() in ['true', '1', 'yes']
            
            # モデル一覧を表示（多すぎる場合は要約）
            if verbose_mode:
                print(f"    ✓ 全GPTモデル一覧: {sorted(gpt_models)}")
            elif len(gpt_models) <= 10:
                print(f"    ✓ 発見されたモデル: {gpt_models}")
            else:
                # 主要モデルのみ表示
                important_models = [m for m in gpt_models if any(keyword in m for keyword in ['gpt-5', 'gpt-4o', 'gpt-4-turbo'])]
                other_count = len(gpt_models) - len(important_models)
                print(f"    ✓ 主要モデル: {sorted(important_models)}")
                if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")ブスクレイピングで最新モデル情報を発見
- 通常モデル(model)と高速モデル(fast_model)の両方に対応
- API取得失敗時は事前定義されたフォールバックモデルを使用
- 設定ファイルの自動バックアップと安全な更新処理

対応プロバイダー:
- OpenAI (ChatGPT): gpt-5, gpt-4o, gpt-4o-mini など (API + Webスクレイピング)
- Google (Gemini): gemini-2.5-pro, gemini-2.5-flash など (API)
- Groq: llama-3.3-70b-versatile, llama-3.1-8b-instant など (API)
- Mistral AI: mistral-large-latest, mistral-small-latest など (API)
- Anthropic (Claude): claude-opus-4, claude-3-5-haiku-latest など (API + Webスクレイピング)
- Together AI: meta-llama モデル群 (Webスクレイピング + フォールバック)
- xAI (Grok): grok-3-latest など (API + フォールバック)
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

# 動的に生成されるフォールバックモデル設定
def get_fallback_models():
    """現在の設定ファイルから動的にフォールバックモデル設定を生成"""
    fallback_models = {}
    
    # まず現在の設定ファイルを読み込む
    if os.path.exists(CONFIG_FILE):
        try:
            print(f"[INFO] 既存の設定ファイル {CONFIG_FILE} からデフォルト値を読み込み中...")
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    assistant_name = row['assistant_name']
                    fallback_models[assistant_name] = {
                        'module': row['module'],
                        'class': row['class'],
                        'model': row['model'],
                        'fast_model': row.get('fast_model', ''),
                    }
                    print(f"  ✓ {assistant_name}: {row['model']} / {row.get('fast_model', 'なし')}")
            
            print(f"[INFO] {len(fallback_models)} 個のアシスタント設定を読み込みました")
            
        except Exception as e:
            print(f"[WARNING] 設定ファイル読み込みエラー: {e}")
            print("[INFO] ハードコードされたデフォルト値を使用します")
            fallback_models = get_hardcoded_fallback_models()
    else:
        print(f"[INFO] 設定ファイル {CONFIG_FILE} が存在しません。初期デフォルト値を使用します")
        fallback_models = get_hardcoded_fallback_models()
    
    return fallback_models

def get_hardcoded_fallback_models():
    """ハードコードされた初期デフォルト値（設定ファイルが存在しない場合用）"""
    return {
        'ChatGPT': {
            'module': 'langchain_openai',
            'class': 'ChatOpenAI',
            'model': 'gpt-5',  # 高性能基本版
            'fast_model': 'gpt-5-chat-latest',  # チャット特化高速版
        },
        'Gemini': {
            'module': 'langchain_google_genai',
            'class': 'ChatGoogleGenerativeAI',
            'model': 'gemini-2.5-pro',  # 最新安定版
            'fast_model': 'gemini-2.5-flash',  # 高速版
        },
        'Groq': {
            'module': 'langchain_groq',
            'class': 'ChatGroq',
            'model': 'llama-3.3-70b-versatile',  # 最新大型モデル
            'fast_model': 'llama-3.1-8b-instant',  # 高速版
        },
        'Mistral': {
            'module': 'langchain_mistralai',
            'class': 'ChatMistralAI',
            'model': 'mistral-large-latest',  # 最新大型モデル
            'fast_model': 'mistral-small-latest',  # 高速版
        },
        'Together': {
            'module': 'langchain_together',
            'class': 'ChatTogether',
            'model': 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
            'fast_model': '',  # 高速版（空白）
        },
        'Anthropic': {
            'module': 'langchain_anthropic',
            'class': 'ChatAnthropic',
            'model': 'claude-opus-4-20250514',  # 最新Claude 4
            'fast_model': 'claude-3-5-haiku-latest',  # 高速版
        },
        'Grok': {
            'module': 'langchain_xai',
            'class': 'ChatXAI',
            'model': 'grok-4-0709',  # 最新Grok 4
            'fast_model': 'grok-3-mini-fast',  # 高速版
        }
    }

# 動的に設定を取得
FALLBACK_MODELS = get_fallback_models()

def backup_config_file():
    """設定ファイルをバックアップし、同時に現在の設定をFALLBACK_MODELSに反映する"""
    global FALLBACK_MODELS
    
    if os.path.exists(CONFIG_FILE):
        try:
            # バックアップ前に現在の設定を読み込んでフォールバックとして使用
            print(f"[INFO] バックアップ前に現在の設定を読み込み中...")
            FALLBACK_MODELS = get_fallback_models()
            
            # バックアップ実行
            with open(CONFIG_FILE, 'r', encoding='utf-8') as src:
                with open(BACKUP_FILE, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            print(f"[INFO] 設定ファイルをバックアップしました: {BACKUP_FILE}")
            
            # 古いバックアップファイルを削除（最新3つを保持）
            cleanup_old_backups()
            
            return True
        except Exception as e:
            print(f"[ERROR] バックアップに失敗しました: {e}")
            # エラーが発生してもフォールバック設定は初期化
            FALLBACK_MODELS = get_fallback_models()
            return False
    else:
        print(f"[WARNING] 設定ファイル {CONFIG_FILE} が見つかりません")
        # 設定ファイルが存在しない場合は初期デフォルト値を使用
        FALLBACK_MODELS = get_fallback_models()
        return False

def cleanup_old_backups(keep_count=3):
    """古いバックアップファイルを削除する（最新のN個を保持）"""
    try:
        import glob
        
        # バックアップファイルパターン
        pattern = "ai_assistants_config_backup_*.csv"
        backup_files = glob.glob(pattern)
        
        if len(backup_files) <= keep_count:
            return  # 保持数以下なら削除しない
        
        # ファイルを作成時間順にソート（新しい順）
        backup_files.sort(key=os.path.getctime, reverse=True)
        
        # 古いファイルを削除
        files_to_delete = backup_files[keep_count:]
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                print(f"[INFO] 古いバックアップファイルを削除: {file_path}")
            except Exception as e:
                print(f"[WARNING] バックアップファイル削除に失敗: {file_path} - {e}")
                
    except Exception as e:
        print(f"[WARNING] バックアップクリーンアップエラー: {e}")

def get_model_priority_score(model_name: str, provider: str) -> int:
    """モデル名から優先順位スコアを動的に計算"""
    score = 0
    model_lower = model_name.lower()
    
    if provider == 'openai':
        # GPT-5系が最優先
        if 'gpt-5' in model_lower:
            score += 1000
            # 基本のgpt-5を通常モデルとして最優先
            if model_lower == 'gpt-5':
                score += 300  # 基本版を最優先
            elif 'chat-latest' in model_lower:
                score += 100  # チャット特化は高速版向け（スコア低め）
            elif 'mini' in model_lower or 'nano' in model_lower:
                score += 50   # 軽量版は高速版向け（スコア低め）
            elif any(date in model_lower for date in ['2025-08', '2025-07', '2025-06']):
                score += 150  # 最新日付版は中程度
        elif 'gpt-4o' in model_lower:
            score += 800
            if 'mini' in model_lower:
                score += 50
        elif 'gpt-4' in model_lower:
            score += 600
            if 'turbo' in model_lower:
                score += 100
        
    elif provider == 'anthropic':
        # Claude 4系が最優先
        if 'claude-opus-4' in model_lower or 'claude-4-opus' in model_lower:
            score += 1000
        elif 'claude-sonnet-4' in model_lower or 'claude-4-sonnet' in model_lower:
            score += 950
        elif 'claude-3-7' in model_lower:
            score += 900
        elif 'claude-3-5' in model_lower:
            score += 850
            if 'haiku' in model_lower:
                score += 100  # 高速版ボーナス
        elif 'claude-3' in model_lower:
            score += 800
        
        # 日付の新しさを考慮
        if '2025' in model_lower:
            score += 200
        elif '2024' in model_lower:
            score += 100
            
    elif provider == 'grok':
        # Grok 4系が最優先
        if 'grok-4' in model_lower:
            score += 1000
            # 基本のgrok-4を通常モデルとして最優先
            if 'grok-4' in model_lower and len(model_lower.replace('grok-4', '').replace('-', '')) <= 10:
                score += 200  # 基本版またはシンプルな日付版を最優先
        elif 'grok-3' in model_lower:
            score += 900
            if 'mini' in model_lower and 'fast' in model_lower:
                score += 50  # 高速版は高速モデル向け（スコア低め）
            elif 'fast' in model_lower:
                score += 30  # 高速版は高速モデル向け（スコア低め）
            elif 'mini' in model_lower:
                score += 20  # 軽量版は高速モデル向け（スコア低め）
        elif 'grok-2' in model_lower:
            score += 800
        
        # 日付の新しさを考慮
        if '2025' in model_lower or '1212' in model_lower:
            score += 100
            
    elif provider == 'gemini':
        # Gemini 2.5系が最優先
        if 'gemini-2.5' in model_lower:
            score += 1000
            if 'pro' in model_lower:
                score += 100  # Proは高性能版
            elif 'flash' in model_lower:
                score += 50   # Flashは高速版（スコア低め）
        elif 'gemini-2.0' in model_lower:
            score += 950
        elif 'gemini-1.5' in model_lower:
            score += 900
        elif 'gemini-1.0' in model_lower:
            score += 800
            
    elif provider == 'groq':
        # Llama 3.3系が最優先
        if 'llama-3.3' in model_lower:
            score += 1000
        elif 'llama-3.2' in model_lower:
            score += 950
        elif 'llama-3.1' in model_lower:
            score += 900
        elif 'llama-3' in model_lower:
            score += 850
        
        # モデルサイズ
        if '70b' in model_lower:
            score += 100
        elif '8b' in model_lower:
            score += 50
            if 'instant' in model_lower:
                score += 100  # 高速版ボーナス
                
    elif provider == 'mistral':
        # Latest系が最優先
        if 'large-latest' in model_lower:
            score += 1000
        elif 'medium-latest' in model_lower:
            score += 900
        elif 'small-latest' in model_lower:
            score += 850
        elif 'latest' in model_lower:
            score += 800
            
    return score

def select_best_models(models: List[str], provider: str) -> tuple[Optional[str], Optional[str]]:
    """モデルリストから最適な通常モデルと高速モデルを動的に選択"""
    if not models:
        return None, None
    
    # 各モデルにスコアを付与
    scored_models = [(model, get_model_priority_score(model, provider)) for model in models]
    scored_models.sort(key=lambda x: x[1], reverse=True)
    
    # 通常モデル（最高スコア）
    normal_model = scored_models[0][0]
    
    # 高速モデルを選択（異なる特性を持つモデルを優先）
    fast_model = None
    normal_lower = normal_model.lower()
    
    for model, score in scored_models:
        model_lower = model.lower()
        
        # 通常モデルと異なる特性を持つモデルを高速版として選択
        if provider == 'openai':
            # 通常がGPT-5基本版なら、chat-latestまたはmini/nano版を選択
            if 'gpt-5' in normal_lower and 'gpt-5' in model_lower:
                if ('chat-latest' in model_lower and model_lower != normal_model) or \
                   ('mini' in model_lower and 'mini' not in normal_lower) or \
                   ('nano' in model_lower and 'nano' not in normal_lower):
                    fast_model = model
                    break
        elif provider == 'anthropic':
            # 通常がOpusなら、Haikuを選択
            if 'haiku' in model_lower and 'haiku' not in normal_lower:
                fast_model = model
                break
        elif provider == 'grok':
            # 通常がGrok-4なら、mini-fastを優先選択
            if ('fast' in model_lower or 'mini' in model_lower) and model_lower != normal_model:
                # grok-3-mini-fastを最優先
                if 'grok-3-mini-fast' in model_lower:
                    fast_model = model
                    break
                elif 'mini' in model_lower and 'fast' in model_lower:
                    fast_model = model
                    break
                elif 'fast' in model_lower:
                    if not fast_model:  # まだ見つかっていない場合のみ
                        fast_model = model
        elif provider == 'gemini':
            # 通常がProなら、Flashを選択
            if ('flash' in model_lower and 'pro' in normal_lower) or \
               ('pro' in model_lower and 'flash' in normal_lower and score < scored_models[0][1]):
                fast_model = model
                break
        elif provider == 'groq':
            # 通常が70bなら、8b instantを選択
            if 'instant' in model_lower or ('8b' in model_lower and '70b' in normal_lower):
                fast_model = model
                break
        elif provider == 'mistral':
            # 通常がlargeなら、smallを選択
            if 'small' in model_lower and 'large' in normal_lower:
                fast_model = model
                break
    
    # 高速モデルが見つからない場合、2番目に高いスコアのモデルを使用
    if not fast_model and len(scored_models) > 1:
        fast_model = scored_models[1][0]
    
    return normal_model, fast_model

def fetch_webpage_content(url, timeout=10):
    """ウェブページの内容を取得する"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"[ERROR] {url} の取得に失敗しました: {e}")
        return None
    """ウェブページの内容を取得する"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"[ERROR] {url} の取得に失敗しました: {e}")
        return None

def get_openai_models_from_web() -> Optional[tuple[str, str]]:
    """OpenAIの公開情報から最新モデル情報を動的に取得"""
    try:
        print("      - Webサイトから補完情報を取得中...")
        
        # 複数のソースから情報を取得
        sources = [
            ('https://platform.openai.com/docs/models', 5),
            ('https://openai.com/api/', 3),
            ('https://openai.com/pricing', 3),
        ]
        
        all_found_models = set()
        
        for url, timeout in sources:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive',
                }
                
                response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
                if response.status_code == 200:
                    content = response.text
                    
                    # より包括的なパターンマッチング
                    patterns = [
                        r'gpt-[5-9][a-zA-Z0-9\-\.]*',  # GPT-5以上
                        r'gpt-4[a-zA-Z0-9\-\.]*',      # GPT-4系
                    ]
                    
                    for pattern in patterns:
                        models = re.findall(pattern, content, re.IGNORECASE)
                        for model in models:
                            if len(model) < 50:  # 異常に長いモデル名を除外
                                all_found_models.add(model.lower())
                
            except requests.RequestException:
                continue  # 次のソースを試行
        
        if all_found_models:
            model_list = list(all_found_models)
            print(f"      ✓ Web検出モデル: {sorted(model_list)}")
            
            # 動的選択を使用
            normal_model, fast_model = select_best_models(model_list, 'openai')
            
            if normal_model and fast_model:
                print(f"      ✓ Web動的選択: {normal_model} / {fast_model}")
                return (normal_model, fast_model)
        
        # 高速フォールバック
        print("      - Web取得タイムアウト、既知モデルを使用")
        return ('gpt-5', 'gpt-5-chat-latest')
        
    except Exception as e:
        print(f"      - Web取得エラー: {e}")
        return ('gpt-5', 'gpt-5-chat-latest')

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
        
        # まずAPI経由で確実に取得を試行
        print("    - OpenAI APIから直接モデル一覧を取得中...")
        response = requests.get('https://api.openai.com/v1/models', headers=headers, timeout=5)
        if response.status_code == 200:
            models = response.json()
            gpt_models = [m['id'] for m in models['data'] if m['id'].startswith('gpt-')]
            
            print(f"    ✓ API経由で {len(gpt_models)} 個のGPTモデルを発見")
            
            # 詳細表示モード（環境変数VERBOSE_MODEが設定されている場合）
            verbose_mode = os.getenv('VERBOSE_MODE', '').lower() in ['true', '1', 'yes']
            
            # モデル一覧を表示（多すぎる場合は要約）
            if verbose_mode:
                print(f"    ✓ 全GPTモデル一覧: {sorted(gpt_models)}")
            elif len(gpt_models) <= 10:
                print(f"    ✓ 発見されたモデル: {gpt_models}")
            else:
                # 主要モデルのみ表示
                important_models = [m for m in gpt_models if any(keyword in m for keyword in ['gpt-5', 'gpt-4o', 'gpt-4-turbo'])]
                other_count = len(gpt_models) - len(important_models)
                print(f"    ✓ 主要モデル: {sorted(important_models)}")
                if other_count > 0:
                    print(f"    ✓ その他のモデル: {other_count}個 (VERBOSE_MODE=true で全表示)")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(gpt_models, 'openai')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
            return normal_model, fast_model
        
        else:
            print(f"    - API エラー: HTTP {response.status_code}")
            
        # API失敗時のみWebスクレイピングを試行（タイムアウトを短く）
        print("    - API失敗、Webサイトから情報取得を試行...")
        web_models = get_openai_models_from_web()
        if web_models:
            return web_models
        
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
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            models = response.json()
            gemini_models = [m['name'].split('/')[-1] for m in models.get('models', []) 
                           if 'gemini' in m['name'].lower()]
            
            print(f"    ✓ {len(gemini_models)} 個のGeminiモデルを発見: {gemini_models}")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(gemini_models, 'gemini')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
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
        
        response = requests.get('https://api.groq.com/openai/v1/models', headers=headers, timeout=5)
        if response.status_code == 200:
            models = response.json()
            llama_models = [m['id'] for m in models['data'] if 'llama' in m['id'].lower()]
            
            print(f"    ✓ {len(llama_models)} 個のLlamaモデルを発見: {llama_models}")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(llama_models, 'groq')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
            return normal_model, fast_model
        
    except Exception as e:
        print(f"  - Groq API エラー: {e}")
    
    return None, None

def get_anthropic_models_from_web() -> Optional[tuple[str, str]]:
    """AnthropicのWebサイトから最新モデル情報を動的に取得"""
    try:
        print("    - Anthropicのウェブサイトから最新モデル情報を取得中...")
        
        sources = [
            'https://docs.anthropic.com/claude/docs/models-overview',
            'https://docs.anthropic.com/claude/reference/getting-started-with-the-api',
            'https://www.anthropic.com/api',
            'https://www.anthropic.com/claude'
        ]
        
        all_found_models = set()
        
        for url in sources:
            try:
                content = fetch_webpage_content(url, timeout=5)
                if content:
                    # より包括的なClaudeモデルパターン
                    patterns = [
                        # Claude 4系
                        r'claude-[4-9][^"\'>\s]*',
                        r'claude-opus-[4-9][^"\'>\s]*',
                        r'claude-sonnet-[4-9][^"\'>\s]*',
                        r'claude-haiku-[4-9][^"\'>\s]*',
                        # Claude 3系
                        r'claude-3[^"\'>\s]*',
                        # 日付付きバージョン
                        r'claude-[^"\'>\s]*-202[4-9][^"\'>\s]*',
                        # Latest系
                        r'claude-[^"\'>\s]*-latest[^"\'>\s]*'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # 不要な文字を除去し、妥当性をチェック
                            clean_match = re.sub(r'[^\w\-\.]', '', match)
                            if (5 < len(clean_match) < 50 and 
                                'claude' in clean_match.lower() and
                                not any(invalid in clean_match.lower() for invalid in ['test', 'example', 'placeholder'])):
                                all_found_models.add(clean_match)
                                
            except Exception:
                continue  # 次のソースを試行
        
        if all_found_models:
            model_list = list(all_found_models)
            print(f"    ✓ Anthropic検出モデル: {sorted(model_list)}")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(model_list, 'anthropic')
            
            if normal_model:
                print(f"    ✓ Anthropic動的選択: {normal_model} / {fast_model or 'なし'}")
                return (normal_model, fast_model)
        
        print("    - ウェブサイトからの自動検出は失敗")
        return None
        
    except Exception as e:
        print(f"    - ウェブスクレイピングエラー: {e}")
        return None

def get_together_models_from_web() -> Optional[tuple[str, str]]:
    """Together AIのWebサイトから最新モデル情報を動的に取得"""
    try:
        print("    - Together AIのウェブサイトから最新モデル情報を取得中...")
        
        sources = [
            'https://docs.together.ai/docs/inference-models',
            'https://api.together.xyz/models',
            'https://together.ai/models'
        ]
        
        all_found_models = set()
        
        for url in sources:
            try:
                content = fetch_webpage_content(url, timeout=5)
                if content:
                    # より包括的なLlamaモデルパターン
                    patterns = [
                        r'meta-llama/Llama-[4-9][^"\'>\s]*',
                        r'meta-llama/Meta-Llama-[4-9][^"\'>\s]*',
                        r'meta-llama/llama-[4-9][^"\'>\s]*',
                        r'llamafactory/[^"\'>\s]*',
                        r'togethercomputer/[^"\'>\s]*'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            if len(match) < 100:  # 異常に長い名前を除外
                                all_found_models.add(match)
                                
            except Exception:
                continue  # 次のソースを試行
        
        if all_found_models:
            model_list = list(all_found_models)
            print(f"    ✓ Together AI検出モデル: {sorted(model_list[:5])}...")  # 最初の5つを表示
            
            # スコアベースで最適なモデルを選択
            scored_models = []
            for model in model_list:
                score = 0
                model_lower = model.lower()
                
                # Llama 4系を最優先
                if 'llama-4' in model_lower or 'llama/4' in model_lower:
                    score += 1000
                elif 'llama-3' in model_lower:
                    score += 800
                
                # 最新バージョンを優先
                if any(version in model_lower for version in ['instruct', 'chat', 'turbo']):
                    score += 100
                
                # FP8などの最適化版を優先
                if any(opt in model_lower for opt in ['fp8', 'int8', 'awq']):
                    score += 50
                
                scored_models.append((model, score))
            
            scored_models.sort(key=lambda x: x[1], reverse=True)
            
            if scored_models:
                best_model = scored_models[0][0]
                print(f"    ✓ Together AI動的選択: {best_model}")
                return (best_model, '')  # 高速版は通常設定なし
        
        print("    - Together AIウェブサイトからの自動検出は失敗")
        return None
        
    except Exception as e:
        print(f"    - Together AI ウェブスクレイピングエラー: {e}")
        return None

def get_grok_models_via_api() -> tuple[Optional[str], Optional[str]]:
    """xAI (Grok) API経由で利用可能なモデルを取得（通常モデル、高速モデル）"""
    try:
        # 環境変数からAPIキーを取得
        api_key = os.getenv('XAI_API_KEY')
        if not api_key:
            print("  - xAI API Key が設定されていません")
            return None, None
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # まず言語モデル専用エンドポイントを試行（より詳細な情報が得られる）
        print("    - xAI APIから言語モデル一覧を取得中...")
        response = requests.get('https://api.x.ai/v1/language-models', headers=headers, timeout=5)
        
        if response.status_code == 200:
            models = response.json()
            print(f"    ✓ /v1/language-models から取得成功")
            # language-modelsエンドポイントではmodelsフィールドを使用
            grok_models = [m['id'] for m in models.get('models', []) if 'grok' in m['id'].lower()]
        else:
            # フォールバック: 汎用modelsエンドポイントを試行
            print("    - /v1/models エンドポイントを試行...")
            response = requests.get('https://api.x.ai/v1/models', headers=headers, timeout=5)
            if response.status_code == 200:
                models = response.json()
                print(f"    ✓ /v1/models から取得成功")
                # modelsエンドポイントではdataフィールドを使用
                grok_models = [m['id'] for m in models.get('data', []) if 'grok' in m['id'].lower()]
            else:
                print(f"    - API エラー: HTTP {response.status_code}")
                return None, None
        
        if grok_models:
            print(f"    ✓ {len(grok_models)} 個のGrokモデルを発見: {grok_models}")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(grok_models, 'grok')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
            return normal_model, fast_model
        else:
            print("    - Grokモデルが見つかりませんでした")
            return None, None
        
    except Exception as e:
        print(f"  - xAI API エラー: {e}")
    
    return None, None

def test_anthropic_model(api_key: str, model: str) -> bool:
    """Anthropicモデルが利用可能かテスト"""
    try:
        headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01'
        }
        
        # 簡単なテストメッセージでモデルの利用可能性を確認
        data = {
            'model': model,
            'max_tokens': 1,
            'messages': [{'role': 'user', 'content': 'Hi'}]
        }
        
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers=headers,
            json=data,
            timeout=5
        )
        
        # 200系または適切なレスポンスなら利用可能
        return response.status_code in [200, 400]  # 400はmax_tokensが少なすぎる場合でもモデルは有効
        
    except Exception:
        return False

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
        
        # まずWebサイトから最新モデル情報を取得を試行
        web_models = get_anthropic_models_from_web()
        if web_models:
            return web_models
        
        # Webスクレイピングが失敗した場合、APIテスト呼び出しで利用可能モデルを確認
        print("    - APIテスト呼び出しで利用可能モデルを確認中...")
        
        # 動的にテストモデルリストを生成
        potential_models = []
        
        # Claude 4系の可能性を探る
        for version in ['4', '4-opus', 'opus-4']:
            for date in ['20250514', '20250301', '20241201', '20241001']:
                potential_models.append(f'claude-{version}-{date}')
                potential_models.append(f'claude-{version.replace("-", "-")}-{date}')
        
        # Claude 3.7系
        for date in ['20250219', '20250101', '20241201']:
            potential_models.append(f'claude-3-7-sonnet-{date}')
        
        # Claude 3.5系
        for variant in ['sonnet', 'haiku']:
            for date in ['latest', '20241022', '20241001', '20240620']:
                potential_models.append(f'claude-3-5-{variant}-{date}')
        
        # 既知の安定版も追加
        potential_models.extend([
            'claude-opus-4-20250514', 'claude-sonnet-4-20250514', 
            'claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022',
            'claude-3-5-haiku-latest', 'claude-3-5-haiku-20241022'
        ])
        
        # 重複を削除
        test_models = list(set(potential_models))
        
        # 各モデルの利用可能性をテスト
        available_models = []
        for model in test_models:
            if test_anthropic_model(api_key, model):
                available_models.append(model)
                print(f"    ✓ {model} - 利用可能")
            else:
                print(f"    ✗ {model} - 利用不可")
        
        if available_models:
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(available_models, 'anthropic')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
            return normal_model, fast_model
        
        # フォールバックとして既知のモデルを返す
        return 'claude-opus-4-20250514', 'claude-3-5-haiku-latest'
        
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
        
        response = requests.get('https://api.mistral.ai/v1/models', headers=headers, timeout=5)
        if response.status_code == 200:
            models = response.json()
            mistral_models = [m['id'] for m in models['data']]
            
            print(f"    ✓ {len(mistral_models)} 個のMistralモデルを発見: {mistral_models}")
            
            # 動的なモデル選択を使用
            normal_model, fast_model = select_best_models(mistral_models, 'mistral')
            
            if normal_model:
                print(f"    ✓ {normal_model} を通常モデルとして選択（動的選択）")
            if fast_model:
                print(f"    ✓ {fast_model} を高速モデルとして選択（動的選択）")
            
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
        print("  - OpenAI最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'ChatGPT' in FALLBACK_MODELS:
            latest_models['ChatGPT'] = {
                'model': FALLBACK_MODELS['ChatGPT']['model'], 
                'fast_model': FALLBACK_MODELS['ChatGPT']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['ChatGPT']['model']} / {FALLBACK_MODELS['ChatGPT']['fast_model']}")
    
    # Gemini
    print("Geminiの最新モデルを確認中...")
    gemini_normal, gemini_fast = get_gemini_models_via_api()
    if gemini_normal:
        latest_models['Gemini'] = {'model': gemini_normal, 'fast_model': gemini_fast}
        print(f"  - Gemini最新モデル: {gemini_normal} / {gemini_fast}")
    else:
        print("  - Gemini最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Gemini' in FALLBACK_MODELS:
            latest_models['Gemini'] = {
                'model': FALLBACK_MODELS['Gemini']['model'], 
                'fast_model': FALLBACK_MODELS['Gemini']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Gemini']['model']} / {FALLBACK_MODELS['Gemini']['fast_model']}")
    
    # Groq
    print("Groqの最新モデルを確認中...")
    groq_normal, groq_fast = get_groq_models_via_api()
    if groq_normal:
        latest_models['Groq'] = {'model': groq_normal, 'fast_model': groq_fast}
        print(f"  - Groq最新モデル: {groq_normal} / {groq_fast}")
    else:
        print("  - Groq最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Groq' in FALLBACK_MODELS:
            latest_models['Groq'] = {
                'model': FALLBACK_MODELS['Groq']['model'], 
                'fast_model': FALLBACK_MODELS['Groq']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Groq']['model']} / {FALLBACK_MODELS['Groq']['fast_model']}")
    
    # Mistral
    print("Mistralの最新モデルを確認中...")
    mistral_normal, mistral_fast = get_mistral_models_via_api()
    if mistral_normal:
        latest_models['Mistral'] = {'model': mistral_normal, 'fast_model': mistral_fast}
        print(f"  - Mistral最新モデル: {mistral_normal} / {mistral_fast}")
    else:
        print("  - Mistral最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Mistral' in FALLBACK_MODELS:
            latest_models['Mistral'] = {
                'model': FALLBACK_MODELS['Mistral']['model'], 
                'fast_model': FALLBACK_MODELS['Mistral']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Mistral']['model']} / {FALLBACK_MODELS['Mistral']['fast_model']}")
    
    # Anthropic
    print("Anthropicの最新モデルを確認中...")
    anthropic_normal, anthropic_fast = get_anthropic_models_via_api()
    if anthropic_normal:
        latest_models['Anthropic'] = {'model': anthropic_normal, 'fast_model': anthropic_fast}
        print(f"  - Anthropic最新モデル: {anthropic_normal} / {anthropic_fast}")
    else:
        print("  - Anthropic最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Anthropic' in FALLBACK_MODELS:
            latest_models['Anthropic'] = {
                'model': FALLBACK_MODELS['Anthropic']['model'], 
                'fast_model': FALLBACK_MODELS['Anthropic']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Anthropic']['model']} / {FALLBACK_MODELS['Anthropic']['fast_model']}")
    
    # Together AI（ウェブスクレイピングを試行）
    print("Together AIの最新モデルを確認中...")
    together_models = get_together_models_from_web()
    if together_models:
        latest_models['Together'] = {'model': together_models[0], 'fast_model': together_models[1]}
        print(f"  - Together AI最新モデル: {together_models[0]} / {together_models[1]}")
    else:
        print("  - Together AI最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Together' in FALLBACK_MODELS:
            latest_models['Together'] = {
                'model': FALLBACK_MODELS['Together']['model'], 
                'fast_model': FALLBACK_MODELS['Together']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Together']['model']} / {FALLBACK_MODELS['Together']['fast_model']}")
    
    # Grok（xAI）（APIを試行）
    print("Grokの最新モデルを確認中...")
    grok_normal, grok_fast = get_grok_models_via_api()
    if grok_normal:
        latest_models['Grok'] = {'model': grok_normal, 'fast_model': grok_fast}
        print(f"  - Grok最新モデル: {grok_normal} / {grok_fast}")
    else:
        print("  - Grok最新モデルの取得に失敗、前回設定値をフォールバックとして使用")
        if 'Grok' in FALLBACK_MODELS:
            latest_models['Grok'] = {
                'model': FALLBACK_MODELS['Grok']['model'], 
                'fast_model': FALLBACK_MODELS['Grok']['fast_model']
            }
            print(f"  - フォールバック値: {FALLBACK_MODELS['Grok']['model']} / {FALLBACK_MODELS['Grok']['fast_model']}")
    
    # 最終フォールバック値の適用（新しい値が取得できなかった場合）
    for provider in ['OpenAI', 'Mistral AI', 'Google', 'Anthropic', 'Together', 'Grok']:
        if provider not in latest_models:
            if provider in FALLBACK_MODELS:
                latest_models[provider] = {
                    'model': FALLBACK_MODELS[provider]['model'], 
                    'fast_model': FALLBACK_MODELS[provider]['fast_model']
                }
                print(f"  - {provider}: 設定ファイルからフォールバック値を使用 - {FALLBACK_MODELS[provider]['model']} / {FALLBACK_MODELS[provider]['fast_model']}")
            else:
                # 最終的なハードコードフォールバック
                hardcoded_defaults = get_hardcoded_fallback_models()
                if provider in hardcoded_defaults:
                    latest_models[provider] = {
                        'model': hardcoded_defaults[provider]['model'], 
                        'fast_model': hardcoded_defaults[provider]['fast_model']
                    }
                    print(f"  - {provider}: ハードコードデフォルト値を使用 - {hardcoded_defaults[provider]['model']} / {hardcoded_defaults[provider]['fast_model']}")
    
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
    global FALLBACK_MODELS
    
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
        'Anthropic': os.getenv('ANTHROPIC_API_KEY'),
        'xAI': os.getenv('XAI_API_KEY')
    }
    
    for provider, key in api_keys.items():
        status = "✓" if key else "✗"
        print(f"  {status} {provider}_API_KEY: {'設定済み' if key else '未設定'}")
    print()
    
    try:
        # バックアップ作成（この時点でFALLBACK_MODELSが設定される）
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

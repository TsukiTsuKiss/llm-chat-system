#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定ファイルの診断とテストツール
"""

import sys
import os
import json
import csv

def load_ai_assistants_config():
    """AI Assistants設定を読み込み"""
    ai_assistants = {}
    
    if not os.path.exists("ai_assistants_config.csv"):
        print("[ERROR] ai_assistants_config.csv が見つかりません。")
        return ai_assistants
    
    try:
        with open("ai_assistants_config.csv", 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                assistant_name = row['assistant_name']
                ai_assistants[assistant_name] = {
                    'module': row['module'],
                    'class': row['class'],
                    'model': row['model'],
                    'fast_model': row.get('fast_model', '').strip()
                }
    except Exception as e:
        print(f"[ERROR] AI Assistants設定ファイルの読み込みに失敗: {e}")
        return {}
    
    return ai_assistants

def load_multi_role_config(config_file):
    """マルチロール設定を読み込み"""
    if not os.path.exists(config_file):
        print(f"[ERROR] 設定ファイル '{config_file}' が見つかりません。")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"[ERROR] 設定ファイルの読み込みに失敗: {e}")
        return None

def diagnose_config(config_file):
    """設定の診断を実行"""
    print(f"🔍 設定診断: {config_file}")
    print("=" * 60)
    
    # AI Assistants設定を読み込み
    ai_assistants = load_ai_assistants_config()
    if not ai_assistants:
        print("❌ AI Assistants設定の読み込みに失敗しました。")
        return
    
    print("✅ AI Assistants設定:")
    for name, config in ai_assistants.items():
        print(f"  🤖 {name}: {config['module']}.{config['class']} ({config['model']})")
        if config.get('fast_model'):
            print(f"      Fast: {config['fast_model']}")
    
    # マルチロール設定を読み込み
    multi_config = load_multi_role_config(config_file)
    if not multi_config:
        print("❌ マルチロール設定の読み込みに失敗しました。")
        return
    
    print(f"\n✅ マルチロール設定 ({config_file}):")
    print(f"  組織: {multi_config.get('organization', 'Unknown')}")
    
    # 組織ロールの診断
    if 'organization_roles' in multi_config:
        print(f"\n📋 組織ロール ({len(multi_config['organization_roles'])}個):")
        for role in multi_config['organization_roles']:
            role_name = role['name']
            assistant = role['assistant']
            model = role['model']
            
            # Assistant設定の確認
            if assistant not in ai_assistants:
                print(f"  ❌ {role_name}: Assistant '{assistant}' が見つかりません")
            else:
                ai_config = ai_assistants[assistant]
                provider = f"{ai_config['module']}.{ai_config['class']}"
                print(f"  ✅ {role_name}: {provider} ({model})")
                
                # モデル名の検証
                default_model = ai_config['model']
                fast_model = ai_config.get('fast_model', '')
                if model != default_model and model != fast_model:
                    print(f"      ⚠️ モデル '{model}' はデフォルト設定にありません")
                    print(f"      ℹ️ 利用可能: {default_model}, {fast_model}")
    
    # ワークフローの診断
    if 'workflows' in multi_config:
        print(f"\n🔄 ワークフロー ({len(multi_config['workflows'])}個):")
        for wf_name, workflow in multi_config['workflows'].items():
            print(f"  📋 {wf_name}: {workflow['name']}")
            
            # ステップ内のロール参照をチェック
            defined_roles = set()
            if 'organization_roles' in multi_config:
                defined_roles = {role['name'] for role in multi_config['organization_roles']}
            
            for i, step in enumerate(workflow['steps'], 1):
                role_name = step['role']
                if role_name in defined_roles:
                    print(f"      ✅ Step {i}: {role_name}")
                else:
                    print(f"      ❌ Step {i}: {role_name} (ロールが定義されていません)")
    
    print("\n" + "=" * 60)
    print("🎯 診断完了")

def main():
    if len(sys.argv) < 2:
        print("使用法: python test_config.py <config_file>")
        print("例: python test_config.py multi_role_config_tech_startup.json")
        return
    
    config_file = sys.argv[1]
    diagnose_config(config_file)

if __name__ == "__main__":
    main()

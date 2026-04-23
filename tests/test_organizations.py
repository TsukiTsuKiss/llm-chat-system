#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiRoleChat 組織別設定テストスクリプト
複数組織の設定ファイルと構造を検証します。
"""

import os
import json
import sys
from pathlib import Path

# Windows cp932 環境での絵文字出力対策
if sys.stdout.encoding and sys.stdout.encoding.lower() in ('cp932', 'shift_jis', 'mbcs'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def print_header(title):
    """テストセクションのヘッダーを表示"""
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def print_test(test_name):
    """個別テストのヘッダーを表示"""
    print(f"\n[テスト] {test_name}")
    print("-" * 40)

def test_organization_structure():
    """組織フォルダ構造をテスト"""
    print_test("組織フォルダ構造の確認")
    
    organizations_dir = Path("organizations")
    if not organizations_dir.exists():
        print("❌ organizationsフォルダが存在しません")
        return False
    
    print("✅ organizationsフォルダが存在します")
    
    # 組織フォルダ一覧
    org_dirs = [d for d in organizations_dir.iterdir() if d.is_dir()]
    if not org_dirs:
        print("❌ 組織フォルダが見つかりません")
        return False
    
    print(f"📁 発見された組織: {len(org_dirs)}個")
    for org_dir in org_dirs:
        print(f"   - {org_dir.name}")
    
    return True

def test_config_files():
    """設定ファイルをテスト"""
    print_test("設定ファイルの存在と構文確認")
    
    organizations_dir = Path("organizations")
    all_valid = True
    
    for org_dir in organizations_dir.iterdir():
        if not org_dir.is_dir():
            continue
            
        config_file = org_dir / "config.json"
        print(f"\n🏢 {org_dir.name}:")
        
        # ファイル存在確認
        if not config_file.exists():
            print("   ❌ config.json が存在しません")
            all_valid = False
            continue
        
        print("   ✅ config.json が存在します")
        
        # ファイルサイズチェック
        file_size = config_file.stat().st_size
        if file_size == 0:
            print("   ❌ config.json が空ファイルです")
            all_valid = False
            continue
        
        print(f"   📏 ファイルサイズ: {file_size} bytes")
        
        # JSON構文チェック
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print("   ✅ JSON構文が正常です")
            
            # 必須フィールドチェック（新旧両形式に対応）
            # 新形式チェック
            if 'roles' in config:
                print("   ✅ roles フィールドが存在します（新形式）")
                role_count = len(config.get('roles', []))
                print(f"   📊 ロール: {role_count}個")
                
                # ワークフローの存在確認
                if 'workflows' in config:
                    workflow_count = len(config.get('workflows', {}))
                    print(f"   ✅ workflows フィールドが存在します（{workflow_count}個）")
                else:
                    print("   ⚠️  workflows フィールドがありません")
            else:
                # 旧形式チェック
                required_fields = ['organization', 'demo_roles', 'organization_roles']
                for field in required_fields:
                    if field in config:
                        print(f"   ✅ {field} フィールドが存在します（旧形式）")
                    else:
                        print(f"   ❌ {field} フィールドが不足しています")
                        all_valid = False
                
                # ロール数確認
                demo_count = len(config.get('demo_roles', []))
                org_count = len(config.get('organization_roles', []))
                print(f"   📊 デモロール: {demo_count}個, 組織ロール: {org_count}個")
            
        except json.JSONDecodeError as e:
            print(f"   ❌ JSON構文エラー: {e}")
            print(f"   🔍 エラー位置: 行{e.lineno}, 列{e.colno}")
            all_valid = False
        except UnicodeDecodeError as e:
            print(f"   ❌ 文字エンコーディングエラー: {e}")
            print("   💡 ファイルがUTF-8でエンコードされていない可能性があります")
            all_valid = False
        except Exception as e:
            print(f"   ❌ 読み込みエラー: {e}")
            all_valid = False
    
    return all_valid

def test_role_files():
    """ロールファイルをテスト"""
    print_test("ロールファイルの存在確認")
    
    organizations_dir = Path("organizations")
    # 基本的なロールファイル（旧形式用）
    basic_roles = ['secretary.txt', 'planner.txt', 'programmer.txt', 'analyst.txt']
    # creative_org専用ロールファイル
    creative_roles = ['wild_innovator.txt', 'devil_advocate.txt', 'visionary.txt', 'creative.txt', 'moderator.txt']
    
    all_valid = True
    
    for org_dir in organizations_dir.iterdir():
        if not org_dir.is_dir():
            continue
            
        roles_dir = org_dir / "roles"
        print(f"\n🏢 {org_dir.name}:")
        
        if not roles_dir.exists():
            print("   ❌ rolesフォルダが存在しません")
            all_valid = False
            continue
        
        print("   ✅ rolesフォルダが存在します")
        
        # 組織に応じた必須ロールファイルを選択
        if org_dir.name == 'creative_org':
            required_roles = creative_roles
            print("   📝 創造性特化組織のロールファイルをチェック")
        else:
            required_roles = basic_roles
            print("   📝 標準組織のロールファイルをチェック")
        
        # 必須ロールファイルチェック
        missing_count = 0
        for role_file in required_roles:
            role_path = roles_dir / role_file
            if role_path.exists():
                print(f"   ✅ {role_file}")
            else:
                print(f"   ❌ {role_file}")
                missing_count += 1
        
        # creative_orgでは部分的な存在でもOKとする
        if org_dir.name == 'creative_org' and missing_count < len(required_roles):
            print(f"   📝 創造性組織: {len(required_roles) - missing_count}/{len(required_roles)} ファイルが存在")
        elif missing_count > 0:
            all_valid = False
        
        # ロールファイル総数
        role_files = list(roles_dir.glob("*.txt"))
        print(f"   📊 総ロールファイル数: {len(role_files)}個")
    
    return all_valid

def test_workflow_files():
    """ワークフロー設定を検証する"""
    print("\n=== ワークフロー検証 ===")
    
    organizations_dir = Path("organizations")
    
    for org_dir in organizations_dir.iterdir():
        if not org_dir.is_dir():
            continue
            
        print(f"\n📁 {org_dir.name}")
        config_path = org_dir / 'config.json'
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            workflows = config.get('workflows', {})
            if not workflows:
                print("   ℹ️  ワークフローなし")
                continue
                
            for workflow_name, workflow_config in workflows.items():
                print(f"   🔄 ワークフロー: {workflow_name}")
                
                # 必須フィールドチェック（descriptionかnameのどちらか）
                has_description = 'description' in workflow_config
                has_name = 'name' in workflow_config
                has_steps = 'steps' in workflow_config
                has_phases = 'phases' in workflow_config
                
                if has_description or has_name:
                    desc_field = 'description' if has_description else 'name'
                    print(f"      ✅ {desc_field} フィールドあり")
                else:
                    print(f"      ❌ description または name フィールドなし")
                    return False
                
                if has_phases:
                    print(f"      ✅ phases フィールドあり")
                    # ネストを含む全ステップ数をカウント
                    def count_steps(phases_list):
                        total = 0
                        for p in phases_list:
                            total += len(p.get('steps', []))
                            if 'phases' in p:  # loop 内ネスト
                                total += count_steps(p['phases'])
                        return total
                    total_steps = count_steps(workflow_config['phases'])
                    if total_steps > 0:
                        print(f"      📊 総ステップ数: {total_steps}")
                    else:
                        print("      ❌ ステップが空")
                        return False
                elif has_steps:
                    print(f"      ✅ steps フィールドあり（旧形式）")
                    steps = workflow_config.get('steps', [])
                    if steps:
                        print(f"      📊 ステップ数: {len(steps)}")
                    else:
                        print("      ❌ ステップが空")
                        return False
                else:
                    print(f"      ❌ phases または steps フィールドなし")
                    return False
                    
        except Exception as e:
            print(f"   ❌ ワークフロー検証エラー: {e}")
            return False
            
    print("\n✅ ワークフロー検証完了")
    return True

def test_config_consistency():
    """設定ファイルとロールファイルの整合性をテスト"""
    print_test("設定ファイルとロールファイルの整合性確認")
    
    organizations_dir = Path("organizations")
    all_valid = True
    
    for org_dir in organizations_dir.iterdir():
        if not org_dir.is_dir():
            continue
            
        config_file = org_dir / "config.json"
        roles_dir = org_dir / "roles"
        
        print(f"\n🏢 {org_dir.name}:")
        
        if not config_file.exists() or not roles_dir.exists():
            print("   ⏭️ スキップ（必要ファイルが不足）")
            continue
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 参照されているロールファイルの存在確認
            referenced_files = set()
            missing_files = set()
            
            # 新形式（creative_org等）の処理
            if 'roles' in config:
                for role in config['roles']:
                    if 'system_prompt_file' in role:
                        file_path = Path(role['system_prompt_file'])
                        referenced_files.add(file_path.name)
                        
                        # 相対パスを組織フォルダ基準で解決
                        if not file_path.is_absolute():
                            full_path = org_dir / file_path
                        else:
                            full_path = file_path
                        
                        if full_path.exists():
                            print(f"   ✅ {file_path.name} (新形式ロール)")
                        else:
                            print(f"   ❌ {file_path.name} (新形式ロール, ファイル不存在)")
                            missing_files.add(str(file_path))
                            all_valid = False
            
            # 旧形式の処理
            for role_group in ['demo_roles', 'organization_roles', 'scenarios']:
                if role_group in config:
                    items = config[role_group]
                    
                    # scenariosは辞書形式なので特別処理
                    if role_group == 'scenarios':
                        for scenario_name, scenario_roles in items.items():
                            for role in scenario_roles:
                                if 'system_prompt_file' in role:
                                    file_path = Path(role['system_prompt_file'])
                                    referenced_files.add(file_path.name)
                                    
                                    if file_path.exists():
                                        print(f"   ✅ {file_path.name} (シナリオ: {scenario_name})")
                                    else:
                                        print(f"   ❌ {file_path.name} (シナリオ: {scenario_name}, ファイル不存在)")
                                        missing_files.add(str(file_path))
                                        all_valid = False
                    else:
                        for role in items:
                            if 'system_prompt_file' in role:
                                file_path = Path(role['system_prompt_file'])
                                referenced_files.add(file_path.name)
                                
                                # ファイル存在確認
                                if file_path.exists():
                                    print(f"   ✅ {file_path.name} ({role_group})")
                                else:
                                    print(f"   ❌ {file_path.name} ({role_group}, ファイル不存在)")
                                    missing_files.add(str(file_path))
                                    all_valid = False
            
            print(f"   📊 参照されているロールファイル: {len(referenced_files)}個")
            if missing_files:
                print(f"   ⚠️  不足ファイル: {len(missing_files)}個")
                for missing in sorted(missing_files):
                    print(f"      - {missing}")
            
        except Exception as e:
            print(f"   ❌ 整合性チェックエラー: {e}")
            all_valid = False
    
    return all_valid

def test_sample_execution():
    """サンプル実行テスト"""
    print_test("MultiRoleChat.py サンプル実行テスト")
    
    # MultiRoleChat.pyの存在確認
    if not Path("MultiRoleChat.py").exists():
        print("❌ MultiRoleChat.py が見つかりません")
        return False
    
    print("✅ MultiRoleChat.py が存在します")
    
    # 依存関係の確認
    print("\n📋 必要な依存関係の確認:")
    dependencies = ["langchain", "langchain_openai", "langchain_anthropic", "langchain_google_genai", "langchain_groq"]
    missing_deps = []
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"   ✅ {dep}")
        except ImportError:
            print(f"   ❌ {dep} (未インストール)")
            missing_deps.append(dep)
    
    if missing_deps:
        print(f"\n❌ 不足している依存関係: {', '.join(missing_deps)}")
        print("   これらのライブラリをインストールしてからテストを再実行してください")
        return False
    
    # Pythonインポートテスト
    print("\n📋 Pythonインポートテスト:")
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-c", 
            "import sys; sys.path.append('.'); "
            "from MultiRoleChat import parse_arguments, VERSION; "
            "print(f'MultiRoleChat v{VERSION} インポート成功')"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("   ✅ MultiRoleChat.py のインポートが成功しました")
            print(f"   📝 {result.stdout.strip()}")
        else:
            print("   ❌ MultiRoleChat.py のインポートに失敗しました")
            if result.stderr:
                print(f"   🔍 エラー: {result.stderr[:200]}...")
            return False
    except Exception as e:
        print(f"   ❌ インポートテスト失敗: {e}")
        return False
    
    # 簡易構文チェック
    print("\n📋 簡易構文チェック:")
    try:
        result = subprocess.run([
            sys.executable, "-m", "py_compile", "MultiRoleChat.py"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("   ✅ Python構文チェックが成功しました")
        else:
            print("   ❌ Python構文エラーが発見されました")
            if result.stderr:
                print(f"   🔍 エラー: {result.stderr[:200]}...")
            return False
    except Exception as e:
        print(f"   ❌ 構文チェック失敗: {e}")
        return False
    
    return True

def main():
    """メインテスト実行"""
    print_header("MultiRoleChat 組織別設定テスト")
    print("組織別フォルダ構造の検証を開始します...")
    
    tests = [
        ("組織フォルダ構造", test_organization_structure),
        ("設定ファイル", test_config_files),
        ("ロールファイル", test_role_files),
        ("ワークフロー", test_workflow_files),
        ("整合性", test_config_consistency),
        ("サンプル実行", test_sample_execution),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ {test_name}テストでエラー: {e}")
            results[test_name] = False
    
    # 結果サマリー
    print_header("テスト結果サマリー")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n📊 テスト結果: {passed}/{total} 通過")
    
    if passed == total:
        print("🎉 全てのテストが通過しました！")
        return 0
    else:
        print("⚠️  一部のテストが失敗しました。上記の詳細を確認してください。")
        return 1

if __name__ == "__main__":
    sys.exit(main())

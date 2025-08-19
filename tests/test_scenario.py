#!/usr/bin/env python3
import json
import os

def test_tech_startup_scenarios():
    """tech_startupのシナリオ設定をテスト"""
    config_path = "organizations/tech_startup/config.json"
    
    if not os.path.exists(config_path):
        print(f"❌ 設定ファイルが見つかりません: {config_path}")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print(f"✅ 設定ファイル読み込み成功: {config_path}")
        print(f"📋 組織名: {config.get('organization', 'unknown')}")
        
        if 'scenarios' in config:
            scenarios = config['scenarios']
            print(f"🎭 利用可能なシナリオ数: {len(scenarios)}")
            
            for scenario_name, roles in scenarios.items():
                print(f"\n📍 シナリオ: {scenario_name}")
                for role in roles:
                    role_file = role.get('system_prompt_file', 'unknown')
                    full_path = f"organizations/tech_startup/{role_file}"
                    exists = "✅" if os.path.exists(full_path) else "❌"
                    print(f"  {exists} {role.get('name', 'unknown')} -> {role_file}")
        else:
            print("❌ シナリオ設定がありません")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False

if __name__ == "__main__":
    test_tech_startup_scenarios()

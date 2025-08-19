#!/usr/bin/env python3
"""
MultiRoleChatのauto_programmingシナリオの直接テスト
"""
import sys
import os
sys.path.append('.')

from MultiRoleChat import load_organization_config, setup_scenario_roles_from_org, MultiRoleManager

def test_auto_programming():
    """auto_programmingシナリオの動作テスト"""
    try:
        # 組織設定を読み込み
        org_config = load_organization_config('tech_startup')
        print(f"✅ 組織設定読み込み成功: {org_config.get('organization', 'unknown')}")
        
        # ロール管理システム初期化
        role_manager = MultiRoleManager({}, use_fast=True)
        print("✅ ロール管理システム初期化成功")
        
        # シナリオロール設定
        result = setup_scenario_roles_from_org(role_manager, org_config, 'auto_programming')
        
        if result:
            print("✅ シナリオ設定成功")
            print(f"📋 設定されたロール数: {len(role_manager.roles)}")
            
            for role_name in role_manager.roles:
                print(f"  🎭 {role_name}")
                
            return True
        else:
            print("❌ シナリオ設定失敗")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_auto_programming()

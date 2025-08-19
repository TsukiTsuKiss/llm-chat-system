import os
from MultiRoleChat import MultiRoleManager, load_ai_assistants_config, load_organization_config

def test_workflow_logging():
    """ワークフローのログ機能をテスト"""
    # AI設定を読み込み
    ai_assistants = load_ai_assistants_config()
    
    # MultiRoleManagerを初期化
    role_manager = MultiRoleManager(
        ai_assistants=ai_assistants,
        use_fast=True,
        organization_name="tech_startup"
    )
    
    # 組織設定を読み込み
    org_config = load_organization_config("tech_startup")
    role_manager.organization_config = org_config
    
    print(f"✅ 組織設定読み込み成功: {role_manager.organization_name}")
    
    # 利用可能なワークフローを確認
    if hasattr(role_manager, 'organization_config') and role_manager.organization_config:
        workflows = role_manager.organization_config.get('workflows', {})
        print(f"📋 利用可能なワークフロー: {list(workflows.keys())}")
        
        # 反復実行ワークフローをテスト  
        if 'code_and_run_iterative' in workflows:
            print("\n🔄 code_and_run_iterative ワークフローをテスト実行...")
            try:
                role_manager.execute_iterative_workflow('code_and_run_iterative', '計算機プログラムを作成してテストしてください', max_iterations=2)
                print("✅ 反復ワークフロー実行完了")
            except Exception as e:
                print(f"❌ 反復ワークフロー実行エラー: {e}")

if __name__ == "__main__":
    test_workflow_logging()

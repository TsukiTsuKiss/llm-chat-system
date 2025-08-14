# 設定ファイル管理ガイド

このガイドでは、MultiRoleChatの設定ファイルを効率的に管理し、組織やプロジェクトに応じて適切な設定を適用する方法について説明します。

## 設定ファイルの階層構造

```
llm-chat-system/
├── ai_assistants_config.csv          # AIプロバイダー定義（共通）
├── multi_role_config.json            # デフォルト設定
├── multi_role_config_tech_startup.json  # テックスタートアップ用
├── multi_role_config_consulting.json    # コンサルティング用
└── organizations/                     # 組織別詳細設定
    ├── default_company/
    │   ├── config.json               # 組織設定
    │   └── roles/                    # ロール別プロンプト
    │       ├── secretary.txt
    │       ├── planner.txt
    │       └── ...
    ├── tech_startup/
    │   ├── config.json
    │   └── roles/
    └── consulting_firm/
        ├── config.json
        └── roles/
```

## 設定ファイルの種類と用途

### 1. AI Assistants設定 (`ai_assistants_config.csv`)

**用途**: 利用可能なAIプロバイダーとモデルの定義
**管理方法**: 全組織で共通使用

```csv
assistant_name,module,class,model,fast_model
ChatGPT,langchain_openai,ChatOpenAI,gpt-5,gpt-5-chat-latest
Gemini,langchain_google_genai,ChatGoogleGenerativeAI,gemini-2.5-pro,gemini-2.5-flash
```

### 2. メイン設定ファイル (`multi_role_config_*.json`)

**用途**: プロジェクトや組織の全体設定
**管理方法**: プロジェクト別、組織別に作成

### 3. 組織設定ファイル (`organizations/*/config.json`)

**用途**: 詳細な組織固有設定
**管理方法**: 組織ごとに独立管理

## 設定ファイルの選択ルール

### 起動時の設定ファイル指定

```bash
# デフォルト設定で起動
python MultiRoleChat.py

# 特定の設定ファイルを指定
python MultiRoleChat.py --config multi_role_config_tech_startup.json

# 組織モードで起動
python MultiRoleChat.py --organization
```

### 設定ファイルの優先順位

1. **コマンドライン指定** (`--config`)
2. **デフォルト設定** (`multi_role_config.json`)
3. **組織設定** (`organizations/*/config.json`)

## 新しい組織設定の作成手順

### 1. 基本設定の準備

```bash
# 組織フォルダを作成
mkdir organizations/my_company
mkdir organizations/my_company/roles

# 既存設定をコピー
cp organizations/default_company/config.json organizations/my_company/config.json
cp -r organizations/default_company/roles/* organizations/my_company/roles/
```

### 2. 設定ファイルの編集

```json
{
  "organization": "my_company",  // 組織名を変更
  "organization_roles": [
    {
      "name": "CEO",
      "assistant": "ChatGPT",
      "model": "gpt-5",
      "system_prompt_file": "organizations/my_company/roles/ceo.txt"
    }
  ]
}
```

### 3. メイン設定ファイルの作成

```bash
# 新しいメイン設定ファイルを作成
cp multi_role_config_tech_startup.json multi_role_config_my_company.json

# 設定を編集
vim multi_role_config_my_company.json
```

### 4. 動作確認

```bash
# 設定の検証
python test_config.py multi_role_config_my_company.json

# 実際の起動テスト
python MultiRoleChat.py --config multi_role_config_my_company.json
```

## プロバイダー分散戦略

### 基本原則

1. **API制限の分散**: 同一プロバイダーへの集中を避ける
2. **コスト最適化**: Fast Modelの積極活用
3. **品質保証**: 重要なロールには高品質モデル
4. **障害対応**: 複数プロバイダーでの冗長性

### 推奨分散パターン

#### 小規模チーム（3-4ロール）
```json
{
  "organization_roles": [
    {"name": "リーダー", "assistant": "ChatGPT", "model": "gpt-5-chat-latest"},
    {"name": "エンジニア", "assistant": "Groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"name": "デザイナー", "assistant": "Gemini", "model": "gemini-2.5-flash"},
    {"name": "秘書", "assistant": "Anthropic", "model": "claude-3-5-haiku-20241022"}
  ]
}
```

#### 中規模チーム（5-8ロール）
```json
{
  "organization_roles": [
    {"name": "CEO", "assistant": "ChatGPT", "model": "gpt-5"},
    {"name": "CTO", "assistant": "Groq", "model": "meta-llama/llama-4-maverick-17b-128e-instruct"},
    {"name": "デザイナー", "assistant": "Gemini", "model": "gemini-2.5-flash"},
    {"name": "マーケター", "assistant": "Mistral", "model": "devstral-small-latest"},
    {"name": "アナリスト", "assistant": "Anthropic", "model": "claude-3-5-haiku-20241022"},
    {"name": "PM", "assistant": "Grok", "model": "grok-3-mini-fast"}
  ]
}
```

## 設定のバージョン管理

### Git管理の推奨方法

```bash
# 設定ファイルをGit管理に追加
git add ai_assistants_config.csv
git add multi_role_config*.json
git add organizations/*/config.json

# プロンプトファイルも管理
git add organizations/*/roles/*.txt

# 実行ログは除外
echo "multi_logs/" >> .gitignore
echo "logs/" >> .gitignore
```

### ブランチ戦略

```bash
# 本番用設定
git checkout main

# 実験用設定
git checkout -b experimental-config
# 設定変更
git commit -m "新しいプロバイダー分散設定をテスト"

# 設定が安定したら本番に反映
git checkout main
git merge experimental-config
```

## 設定の検証とテスト

### 1. 設定診断ツールの活用

```bash
# 基本診断
python test_config.py multi_role_config_my_company.json

# 詳細診断（全設定ファイル）
for config in multi_role_config*.json; do
  echo "=== $config ==="
  python test_config.py "$config"
done
```

### 2. 段階的テスト

```bash
# 1. 設定読み込みテスト
python MultiRoleChat.py --config multi_role_config_my_company.json
# コマンド: config

# 2. 個別ロールテスト
# コマンド: talk <ロール名> テストメッセージ

# 3. ワークフローテスト
# コマンド: workflow <ワークフロー名> テストトピック
```

### 3. 性能テスト

```python
# パフォーマンス測定スクリプト例
import time
import subprocess

def test_workflow_performance(config_file, workflow_name):
    start_time = time.time()
    
    cmd = [
        "python", "MultiRoleChat.py", 
        "--config", config_file,
        "--workflow", workflow_name,
        "パフォーマンステスト"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    end_time = time.time()
    
    return {
        "duration": end_time - start_time,
        "success": result.returncode == 0,
        "output": result.stdout
    }
```

## 設定の移行とアップグレード

### 既存設定のアップグレード

```bash
# バックアップ作成
cp multi_role_config.json multi_role_config.json.backup.$(date +%Y%m%d)

# 新しい設定形式への移行
python upgrade_config.py multi_role_config.json
```

### 設定の互換性確認

```python
# 設定互換性チェック例
def check_config_compatibility(config_file):
    required_fields = [
        "organization", 
        "organization_roles", 
        "workflows"
    ]
    
    with open(config_file) as f:
        config = json.load(f)
    
    for field in required_fields:
        if field not in config:
            print(f"❌ 必須フィールド '{field}' が見つかりません")
            return False
    
    print("✅ 設定ファイルは互換性があります")
    return True
```

## 設定の共有とドキュメント化

### 設定ドキュメントの作成

```markdown
# プロジェクト設定ドキュメント

## 設定ファイル: multi_role_config_my_project.json

### 組織構成
- **プロジェクト名**: My Project
- **チームサイズ**: 6名
- **主要ワークフロー**: project_planning, product_development

### ロール構成
| ロール | プロバイダー | モデル | 用途 |
|--------|-------------|--------|------|
| PM | ChatGPT | gpt-5-chat-latest | 全体統括 |
| エンジニア | Groq | llama-4-scout | 技術実装 |

### 注意事項
- API制限対策として、ChatGPTは1日100リクエストまで
- 重要な会議ではClaude Opusを使用
```

### チーム向け設定ガイド

```bash
# チーム用セットアップスクリプト
#!/bin/bash

echo "プロジェクト設定のセットアップを開始します..."

# 設定ファイルをダウンロード
curl -O https://internal-repo/configs/multi_role_config_my_project.json

# 診断実行
python test_config.py multi_role_config_my_project.json

# 起動テスト
python MultiRoleChat.py --config multi_role_config_my_project.json --demo

echo "セットアップ完了！"
```

## 設定のモニタリングと最適化

### 使用状況の監視

```python
# 設定使用状況のログ分析
def analyze_config_usage(log_dir):
    # ワークフローログを解析
    # プロバイダー別エラー率を計算
    # レスポンス時間を測定
    pass
```

### 自動最適化

```python
# エラー率に基づく自動設定調整
def auto_optimize_config(config_file, error_threshold=0.1):
    # エラー率が高いロールのプロバイダーを変更
    # Fast Modelへの自動切り替え
    # 負荷分散の調整
    pass
```

---

このガイドに従って設定ファイルを管理することで、安定したMultiRoleChatの運用が可能になります。

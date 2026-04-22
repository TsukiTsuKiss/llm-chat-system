# MultiRoleChat 設定ガイド

## 📋 目次
1. [組織設定の概要](#組織設定の概要)
2. [設定ファイルの構造](#設定ファイルの構造)
3. [ロール名の統一](#ロール名の統一)
4. [プロバイダー分散戦略](#プロバイダー分散戦略)
5. [エラー診断](#エラー診断)
6. [設定ファイルの作成](#設定ファイルの作成)
7. [トラブルシューティング](#トラブルシューティング)

## 組織設定の概要

MultiRoleChatでは、異なる組織やプロジェクト向けに独立した設定を管理できます。

### 設定ファイルの種類

#### 1. メイン設定ファイル
- `multi_role_config.json` - デフォルト設定
- `multi_role_config_tech_startup.json` - テックスタートアップ向け
- `multi_role_config_consulting.json` - コンサルティング向け

#### 2. 組織別設定ファイル
```
organizations/
├── default_company/
│   └── config.json
├── tech_startup/
│   └── config.json
└── consulting_firm/
    └── config.json
```

#### 3. AI Assistants設定
- `ai_assistants_config.csv` - 利用可能なAIプロバイダーとモデル定義

## 設定ファイルの構造

### AI Assistants設定 (ai_assistants_config.csv)

```csv
assistant_name,module,class,model,fast_model
ChatGPT,langchain_openai,ChatOpenAI,gpt-5.4,gpt-5.3-chat-latest
Gemini,langchain_google_genai,ChatGoogleGenerativeAI,gemini-3.1-pro-preview,gemini-3-flash-preview
Groq,langchain_groq,ChatGroq,openai/gpt-oss-120b,openai/gpt-oss-20b
Anthropic,langchain_anthropic,ChatAnthropic,claude-opus-4-6,claude-sonnet-4-5
Mistral,langchain_mistralai,ChatMistralAI,mistral-large-2512,ministral-14b-2512
Together,langchain_together,ChatTogether,meta-llama/Llama-3.3-70B-Instruct-Turbo,meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo
Grok,langchain_xai,ChatXAI,grok-4-1-fast,grok-4-1-fast-non-reasoning
```

### マルチロール設定ファイル構造

```json
{
  "organization": "組織名",
  "organization_roles": [
    {
      "name": "ロール名",
      "assistant": "プロバイダー名",
      "model": "モデル名",
      "system_prompt_file": "プロンプトファイルパス"
    }
  ],
  "workflows": {
    "ワークフロー名": {
      "name": "表示名",
      "steps": [
        {"role": "ロール名", "action": "実行内容"}
      ]
    },
    "並列ワークフロー名": {
      "name": "表示名（並列）",
      "parallel_steps": [
        {"role": "ロール名1", "action": "実行内容"},
        {"role": "ロール名2", "action": "実行内容"}
      ]
    }
  }
}
```

> **`steps` vs `parallel_steps`**
> - `steps`: 前のロールの回答を次のロールに引き継ぐ逐次実行。対話形式の議論に最適。
> - `parallel_steps`: 全ロールに同じ入力を同時投げる並列実行。最遅モデルの時間で全吧1回分完了（鱼次比最大4倍速）。

## ロール名の統一

### 重要な原則
**ワークフロー定義のロール名と organization_roles のロール名は必ず一致させる**

### よくある問題と解決策

#### ❌ 問題のある設定
```json
// organization_roles
{"name": "分析官", ...}

// workflows
{"role": "分析専門", ...}  // 名前が一致しない
```

#### ✅ 正しい設定
```json
// organization_roles
{"name": "分析専門", ...}

// workflows  
{"role": "分析専門", ...}  // 名前が一致
```

### 標準ロール名

| ロール名 | 用途 | 推奨プロバイダー |
|----------|------|------------------|
| 秘書 | 会議管理・まとめ | Anthropic (軽量モデル) |
| 企画 | アイデア創出・企画 | Gemini (創造性) |
| 分析専門 | データ分析・評価 | ChatGPT (論理思考) |
| 実装専門 | 技術実装・開発 | Groq (高速処理) |
| マーケター | 市場分析・戦略 | Mistral (効率的) |
| デザイナー | UI/UX・デザイン | Grok (創造的) |

## プロバイダー分散戦略

### API制限を避けるための分散配置

#### 基本方針
1. **同一プロバイダーの過度な集中を避ける**
2. **各ロールの特性に適したプロバイダーを選択**
3. **Fast Modelを積極的に活用**

#### 推奨分散パターン

```json
{
  "organization_roles": [
    {"name": "秘書", "assistant": "Anthropic", "model": "claude-sonnet-4-5"},
    {"name": "企画", "assistant": "Gemini", "model": "gemini-3-flash-preview"},
    {"name": "分析専門", "assistant": "ChatGPT", "model": "gpt-5.3-chat-latest"},
    {"name": "実装専門", "assistant": "Groq", "model": "openai/gpt-oss-20b"},
    {"name": "マーケター", "assistant": "Mistral", "model": "ministral-14b-2512"},
    {"name": "デザイナー", "assistant": "Grok", "model": "grok-4-1-fast-non-reasoning"}
  ]
}
```

#### プロバイダー別特徴

| プロバイダー | 特徴 | 適用ロール | 注意点 |
|-------------|------|------------|--------|
| **OpenAI (ChatGPT)** | 高品質・論理的 | 分析専門、企画 | レート制限あり |
| **Anthropic (Claude)** | 安全・丁寧 | 秘書、マーケター | クレジット制限 |
| **Google (Gemini)** | 創造的・多言語 | 企画、デザイナー | 応答が空になることあり |
| **Groq** | 高速処理 | 実装専門 | API制限あり |
| **Mistral** | 効率的・軽量 | マーケター | 応答品質にばらつき |
| **Grok** | 創造的・ユニーク | デザイナー | 新しいプロバイダー |

## エラー診断

### 強化された診断機能

エラー発生時に以下の詳細情報が表示されます：

```
🚨 詳細診断情報:
[ロール名] 🚨 エラー詳細
  Organization: tech_startup
  Config: multi_role_config_tech_startup.json
  Source: role/default_org/planner.txt
  Provider: langchain_openai.ChatOpenAI
  Assistant: ChatGPT
  Model: gpt-5
  Error: ⚠️ API制限に達しました。しばらく待ってから再試行してください。
```

### 診断コマンド

#### 1. リアルタイム診断（MultiRoleChat内）
```
🎭 MultiRoleChat> config    # 現在の設定状況を表示
🎭 MultiRoleChat> list      # ロール一覧と詳細設定
🎭 MultiRoleChat> debug <ロール名>  # 特定ロールの詳細診断
```

#### 2. 事前診断ツール
```bash
python test_config.py multi_role_config_tech_startup.json
```

### よくあるエラーパターン

#### 1. **API制限エラー**
```
⚠️ API制限に達しました。しばらく待ってから再試行してください。
```
**原因**: 同一プロバイダーの過度な使用
**解決策**: プロバイダー分散、Fast Model使用

#### 2. **クレジット不足**
```
⚠️ APIクレジットが不足しています。
```
**原因**: Anthropic APIのクレジット残高不足
**解決策**: クレジット補充、他プロバイダーへの変更

#### 3. **応答が空**
```
応答が空でした
```
**原因**: Google Gemini APIの一時的な問題、不正なプロンプト
**解決策**: プロンプト見直し、他プロバイダーへの変更

#### 4. **ロールが見つからない**
```
⚠️ ロール 'XXX' が見つかりません。スキップします。
```
**原因**: ワークフローとロール定義の名前不一致
**解決策**: ロール名の統一

## 設定ファイルの作成

### 1. 新しい組織設定の作成

```bash
# 1. 組織フォルダを作成
mkdir organizations/my_company

# 2. 設定ファイルをコピー
cp organizations/default_company/config.json organizations/my_company/config.json

# 3. 設定ファイルを編集
# - organization名を変更
# - ロール設定をカスタマイズ
# - プロバイダーを分散配置
```

### 2. メイン設定ファイルの作成

```bash
# 既存設定をベースに作成
cp multi_role_config_tech_startup.json multi_role_config_my_company.json

# 設定内容をカスタマイズ
```

### 3. ロールファイルの準備

```bash
# ロールファイルフォルダを作成
mkdir organizations/my_company/roles

# システムプロンプトファイルを作成
echo "あなたは..." > organizations/my_company/roles/secretary.txt
```

## トラブルシューティング

### 設定診断チェックリスト

#### ✅ 基本チェック
- [ ] `ai_assistants_config.csv` が存在し、正しく読み込めるか
- [ ] 設定ファイルのJSON構文が正しいか
- [ ] organization_roles が定義されているか

#### ✅ ロール設定チェック
- [ ] ワークフローのロール名とorganization_rolesのロール名が一致するか
- [ ] 指定されたassistantがai_assistants_config.csvに存在するか
- [ ] システムプロンプトファイルが存在するか

#### ✅ プロバイダー分散チェック
- [ ] 同一プロバイダーに過度に集中していないか
- [ ] Fast Modelを適切に使用しているか
- [ ] 各プロバイダーのAPI制限を考慮しているか

### 設定ファイル検証

```bash
# 設定診断ツールの実行
python test_config.py <設定ファイル名>

# 結果例:
# ✅ すべて正常
# ❌ 問題発見 → 詳細な原因と解決策を表示
```

### 段階的デバッグ

1. **設定診断ツールの実行**
2. **個別ロールのテスト**
3. **ワークフローの段階実行**
4. **プロバイダー別の動作確認**

---

## 📝 設定例

### テックスタートアップ向け設定

```json
{
  "organization": "tech_startup",
  "organization_roles": [
    {"name": "CTO", "assistant": "ChatGPT", "model": "gpt-5-chat-latest"},
    {"name": "PM", "assistant": "Gemini", "model": "gemini-2.5-flash"},
    {"name": "エンジニア", "assistant": "Groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"name": "デザイナー", "assistant": "Grok", "model": "grok-3-mini-fast"}
  ]
}
```

### コンサルティング向け設定

```json
{
  "organization": "consulting_firm", 
  "organization_roles": [
    {"name": "パートナー", "assistant": "Anthropic", "model": "claude-opus-4-20250514"},
    {"name": "シニアコンサルタント", "assistant": "ChatGPT", "model": "gpt-5"},
    {"name": "アナリスト", "assistant": "Gemini", "model": "gemini-2.5-pro"},
    {"name": "プロジェクトマネージャー", "assistant": "Mistral", "model": "mistral-large-latest"}
  ]
}
```

---

*このガイドは MultiRoleChat v1.0.0 に基づいています*

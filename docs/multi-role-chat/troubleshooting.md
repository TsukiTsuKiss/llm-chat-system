# MultiRoleChat トラブルシューティングガイド

## 🚨 緊急時の診断手順

### 1. 即座に問題を特定する方法

#### エラーが発生したら
1. **エラーログを確認** - どのロールでエラーが発生したかを特定
2. **診断コマンドを実行** - `debug <ロール名>` で詳細情報を取得
3. **設定を検証** - `config` コマンドで全体設定を確認

#### エラーログの読み方

```
🚨 詳細診断情報:
[企画] 🚨 エラー詳細
  Organization: tech_startup              ← 組織名
  Config: multi_role_config_tech_startup.json  ← 設定ファイル
  Source: role/default_org/planner.txt    ← プロンプトファイル
  Provider: langchain_openai.ChatOpenAI   ← プロバイダー情報
  Assistant: ChatGPT                      ← AIアシスタント
  Model: gpt-5                           ← 使用モデル
  Error: ⚠️ API制限に達しました           ← 実際のエラー
```

## 🔧 よくある問題と解決策

### API制限・レート制限エラー

#### 症状
```
⚠️ API制限に達しました。しばらく待ってから再試行してください。
⚠️ レート制限エラー: トークン数を削減する必要があります。
429 Too Many Requests
```

#### 原因
- 同一プロバイダーへの短時間での大量リクエスト
- 1つのAPIキーでの過度な使用

#### 解決策

**即座の対応:**
1. **他のプロバイダーに切り替え**
   ```json
   // 企画ロールをChatGPTからGeminiに変更
   {"name": "企画", "assistant": "Gemini", "model": "gemini-2.5-flash"}
   ```

2. **Fast Modelを使用**
   ```json
   // 重いモデルから軽量モデルに変更
   {"name": "企画", "assistant": "ChatGPT", "model": "gpt-5-chat-latest"}
   ```

**根本的解決:**
- プロバイダー分散設定の実装
- 設定ファイルの見直し

### クレジット不足エラー

#### 症状
```
⚠️ APIクレジットが不足しています。
credit balance is too low
```

#### 原因
- Anthropic Claude APIのクレジット残高不足

#### 解決策

**即座の対応:**
1. **他のプロバイダーに変更**
   ```json
   // AnthropicからChatGPTに変更
   {"name": "秘書", "assistant": "ChatGPT", "model": "gpt-5-chat-latest"}
   ```

**根本的解決:**
- APIクレジットの補充
- 複数プロバイダーでの負荷分散

### 応答が空のエラー

#### 症状
```
応答が空でした
応答の取得に失敗しました
```

#### 原因
- Google Gemini APIの一時的な問題
- 不適切なシステムプロンプト
- モデルの過負荷

#### 解決策

**即座の対応:**
1. **プロバイダー変更**
   ```json
   // GeminiからChatGPTに変更
   {"name": "分析専門", "assistant": "ChatGPT", "model": "gpt-5"}
   ```

2. **システムプロンプトの確認**
   - プロンプトファイルが存在するか
   - プロンプト内容が適切か

### ロールが見つからないエラー

#### 症状
```
⚠️ ロール 'XXX' が見つかりません。スキップします。
```

#### 原因
- ワークフローとロール定義の名前不一致

#### 解決策

**名前の統一:**
```json
// ワークフロー定義
{"role": "分析専門", "action": "データ分析"}

// ロール定義（名前を一致させる）
{"name": "分析専門", "assistant": "ChatGPT", "model": "gpt-5"}
```

## 🔍 診断ツールの使い方

### 1. 設定診断ツール

```bash
python test_config.py multi_role_config_tech_startup.json
```

#### 出力例（正常）
```
✅ マルチロール設定 (multi_role_config_tech_startup.json):
  組織: tech_startup
📋 組織ロール (6個):
  ✅ 秘書: langchain_anthropic.ChatAnthropic (claude-3-5-haiku-20241022)
  ✅ 企画: langchain_google_genai.ChatGoogleGenerativeAI (gemini-2.5-flash)
```

#### 出力例（問題あり）
```
❌ 企画: Assistant 'UnknownAI' が見つかりません
⚠️ モデル 'invalid-model' はデフォルト設定にありません
❌ Step 1: 分析官 (ロールが定義されていません)
```

### 2. リアルタイム診断（MultiRoleChat内）

#### 設定確認
```
🎭 MultiRoleChat> config
📋 現在の設定情報:
  設定ファイル: multi_role_config_tech_startup.json
  検出された組織: tech_startup
  Fast Mode: 無効
  アクティブロール数: 6
```

#### ロール詳細確認
```
🎭 MultiRoleChat> debug 企画
🔍 ロール '企画' の詳細設定:
  Assistant: Gemini
  Model: gemini-2.5-flash
  Organization: tech_startup
  Config Path: /path/to/multi_role_config_tech_startup.json
  Source File: role/default_org/planner.txt
```

## 🛠️ 設定修正の手順

### 1. プロバイダー分散の実装

#### 現在の問題を特定
```bash
python test_config.py multi_role_config_tech_startup.json
```

#### 分散パターンの適用
```json
{
  "organization_roles": [
    {"name": "秘書", "assistant": "Anthropic", "model": "claude-3-5-haiku-20241022"},
    {"name": "企画", "assistant": "Gemini", "model": "gemini-2.5-flash"},
    {"name": "分析専門", "assistant": "ChatGPT", "model": "gpt-5-chat-latest"},
    {"name": "実装専門", "assistant": "Groq", "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    {"name": "マーケター", "assistant": "Mistral", "model": "devstral-small-latest"},
    {"name": "デザイナー", "assistant": "Grok", "model": "grok-3-mini-fast"}
  ]
}
```

### 2. ロール名の統一

#### 不一致を特定
```bash
grep -n "role.*:" multi_role_config_tech_startup.json | grep -v "organization_roles"
```

#### 統一作業
1. ワークフロー内のロール名をリストアップ
2. organization_rolesのロール名と照合
3. 不一致箇所を修正

### 3. システムプロンプトファイルの確認

#### ファイル存在確認
```bash
# プロンプトファイルの存在確認
find . -name "*.txt" -path "*/role/*" -type f
```

#### ファイル内容確認
```bash
# 内容が空でないかチェック
find . -name "*.txt" -path "*/role/*" -empty
```

## 📊 パフォーマンス最適化

### プロバイダー別レスポンス速度

| プロバイダー | 平均レスポンス時間 | 推奨用途 |
|-------------|------------------|----------|
| **Groq** | ~1-2秒 | 高速処理が必要なロール |
| **Gemini Flash** | ~2-3秒 | バランス型 |
| **ChatGPT Latest** | ~3-5秒 | 高品質が必要なロール |
| **Claude Haiku** | ~2-4秒 | 安全性重視 |
| **Mistral Small** | ~1-3秒 | 軽量処理 |
| **Grok Mini** | ~2-4秒 | 創造的タスク |

### 最適化のガイドライン

1. **高頻度ロール**: 高速プロバイダー（Groq、Gemini Flash）
2. **重要ロール**: 高品質プロバイダー（ChatGPT、Claude）
3. **支援ロール**: 軽量プロバイダー（Mistral、Grok Mini）

## 🚨 緊急時の回避策

### 全プロバイダー制限時の対応

#### 1. Fast Modelへの一括切り替え
```json
// すべてのロールをFast Modelに変更
{"assistant": "ChatGPT", "model": "gpt-5-chat-latest"}
{"assistant": "Gemini", "model": "gemini-2.5-flash"}
{"assistant": "Anthropic", "model": "claude-3-5-haiku-20241022"}
```

#### 2. ロール数の削減
```json
// 最小限のロールのみでワークフロー実行
"steps": [
  {"role": "企画", "action": "要件定義から実装まで一括対応"},
  {"role": "秘書", "action": "結果まとめ"}
]
```

#### 3. マニュアル実行
```
🎭 MultiRoleChat> talk 企画 LLM仮想会社会議チャットボットの要件を整理してください
```

## 📝 設定ファイルバックアップ

### 推奨バックアップ手順

#### 1. 設定変更前のバックアップ
```bash
# 現在の設定をバックアップ
cp multi_role_config_tech_startup.json multi_role_config_tech_startup.json.backup.$(date +%Y%m%d_%H%M%S)
```

#### 2. 動作確認
```bash
# 変更後の動作確認
python test_config.py multi_role_config_tech_startup.json
```

#### 3. ロールバック（必要時）
```bash
# 問題がある場合は元に戻す
cp multi_role_config_tech_startup.json.backup.20250813_232000 multi_role_config_tech_startup.json
```

---

## 📞 サポート情報

### 問題報告時に含めるべき情報

1. **エラーメッセージ** - 完全なエラーログ
2. **設定ファイル** - 使用中の設定ファイル名
3. **実行コマンド** - 実行したワークフローやコマンド
4. **環境情報** - Python版、OS、インストールパッケージ

### ログファイルの場所

- **ワークフローログ**: `multi_logs/workflow_*.md`
- **会議ログ**: `multi_logs/meeting_*.md`
- **クイズログ**: `multi_logs/quiz_*.md`

---

*このガイドは MultiRoleChat v1.0.0 に基づいています*

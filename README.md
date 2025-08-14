# LLM Chat System - 高度なAI協働システム

このシステムは、複数のAIが協力して問題解決を行う革新的なチャットシステムです。

## 🎯 主要コンポーネント

### 1. MultiRoleChat - マルチロールAI協働システム

複数のAIアシスタントが異なる専門役割を担当し、チームとして協働するシステム

**主要機能:**
- 🎭 **複数ロール管理** - 企画、分析、実装、デザインなど専門ロール
- 🔄 **ワークフロー自動化** - 定義済みプロセスの自動実行
- 🏢 **組織シミュレーション** - 企業やチームの会議・議論をシミュレート
- ⚡ **プロバイダー分散** - API制限回避とパフォーマンス最適化
- 🔍 **強化診断機能** - エラー発生時の詳細分析とトラブルシューティング
- 💰 **統合コスト管理システム** - リアルタイムコスト追跡と価格管理
- 💾 **自動コード保存機能** - AIが生成したコードを`sandbox/`に自動保存

**新機能 (v1.3.0):**
- 💾 **自動コード保存システム** - AI生成コードの`sandbox/`自動保存機能
- 🔧 **コード保存管理** - セッション別ファイル管理と実行スクリプト生成
- 📁 **分離実行環境** - 生成と実行の完全分離による安全性確保

**新機能 (v1.2.0):**
- 🔧 **統合管理ユーティリティ** - AI設定とコスト管理の一元化 (`update_ai_config.py`)
- 🔍 **プロバイダーマッピング** - AI設定からコスト情報への自動マッピング
- ⚖️ **整合性チェック機能** - AI設定とコスト情報の不整合を自動検出

**機能改良 (v1.1.0):**
- 🏢 **組織別設定システム** - 独立した組織とワークフローの管理
- ⚡ **ワークフロー直接実行** - コマンドラインから直接ワークフロー起動
- 🎨 **創造性特化組織** - ブレインストーミングと革新的思考に特化
- 🤖 **スタンドアロンモード** - 組織設定からの単独実行機能

**機能改良 (v1.0.0):**
- 📊 組織情報とプロバイダー情報を含む詳細エラー診断
- 🛠️ 設定ファイル検証ツール (`test_config.py`)
- 📋 リアルタイム設定確認コマンド (`config`, `debug`)
- 🔧 ロール名統一とプロバイダー分散による安定性向上

### 2. Single Chat - シンプルAIチャット

基本的な1対1のAIチャット機能

## 📚 ドキュメント

### MultiRoleChat
- 📖 **[メインガイド](docs/multi-role-chat/README.md)** - 基本機能と使用方法
- ⚙️ **[設定ガイド](docs/multi-role-chat/configuration-guide.md)** - 組織設定・プロバイダー分散・エラー診断
- 🔧 **[設定管理ガイド](docs/multi-role-chat/configuration-management.md)** - 設定ファイル管理・バージョン管理  
- 🚨 **[トラブルシューティング](docs/multi-role-chat/troubleshooting.md)** - エラー解決・診断ツール
- 🚀 **[クイックスタート](docs/multi-role-chat/quickstart.md)** - 迅速な導入手順
- 💡 **[実例集](docs/multi-role-chat/examples.md)** - 実際の使用例とベストプラクティス
- 💰 **[コスト管理](docs/cost-management.md)** - 統合コスト管理とプロバイダーマッピング
- 💾 **[コード保存機能](docs/code-saving-feature.md)** - AI生成コードの自動保存と安全実行

### Single Chat
- 🚀 **[クイックスタート](docs/single-chat/quickstart.md)** - シンプルチャットの使用方法
- 📖 **[メインガイド](docs/single-chat/README.md)** - 基本機能と設定

## 🔧 統合管理ユーティリティ

### AI設定とコスト管理

`update_ai_config.py`はAI設定とコスト管理を一元的に行うツールです：

```bash
# AI設定の更新（最新モデル情報を取得）
python update_ai_config.py

# コスト一覧の表示
python update_ai_config.py costs list

# AI設定とコスト情報の整合性確認
python update_ai_config.py costs verify

# モデルコスト情報の追加
python update_ai_config.py costs add gpt-5 OpenAI 0.005 0.015 "Latest GPT-5 pricing"

# 最新価格情報の自動取得
python update_ai_config.py costs crawl all
```

詳細は [コスト管理ドキュメント](docs/cost-management.md) を参照してください。

## 🚀 クイックスタート

### MultiRoleChat

```bash
# 1. 組織指定とワークフロー直接実行（推奨）
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"

# 2. 利用可能な組織とワークフローの確認
python MultiRoleChat.py --org creative_org

# 3. 組織を指定して対話モードで起動
python MultiRoleChat.py --org tech_startup

# 4. デモモードでの起動
python MultiRoleChat.py --demo

# 5. ワークフロー実行（対話モード内）
🎭 MultiRoleChat> workflow product_development "LLM仮想会社会議チャットボット"
```

### Single Chat

```bash
python Chat.py
```

## 🔧 設定ファイル構造

```
llm-chat-system/
├── ai_assistants_config.csv          # AIプロバイダー定義（共通）
├── model_costs.csv                    # モデルコスト情報データベース
├── update_ai_config.py               # 統合管理ユーティリティ（AI設定+コスト管理）
├── organizations/                     # 組織別詳細設定
│   ├── creative_org/                  # 創造性特化組織
│   │   ├── config.json               # 組織設定とワークフロー
│   │   └── roles/                    # 組織専用ロール
│   │       ├── wild_innovator.txt    # ワイルドアイデア・ジェネレーター
│   │       ├── devil_advocate.txt    # 悪魔の代弁者
│   │       ├── visionary.txt         # ビジョナリー
│   │       ├── creative.txt          # 創造性重視
│   │       └── moderator.txt         # モデレーター
│   ├── tech_startup/config.json      # テックスタートアップ組織
│   ├── consulting_firm/config.json   # コンサルティング組織
│   └── default_company/config.json   # デフォルト組織
└── docs/                             # ドキュメント
    ├── multi-role-chat/              # MultiRoleChatドキュメント
    ├── single-chat/                  # SingleChatドキュメント
    └── cost-management.md            # コスト管理システムガイド
```

## 🎭 MultiRoleChat の特徴

### 組織とロールの管理

**テックスタートアップ組織例:**
- 📋 **企画** - 戦略立案とアイデア創出
- 🔬 **分析専門** - データ分析と市場調査  
- 💻 **実装専門** - 技術実装と開発
- 🎨 **デザイナー** - UI/UXデザイン
- 📢 **マーケター** - 市場戦略と販促
- 📝 **秘書** - 会議管理と総括

### プロバイダー分散戦略

API制限を回避し、安定した運用を実現するため、各ロールを異なるAIプロバイダーに分散配置：

| ロール | プロバイダー | モデル | 特徴 |
|--------|-------------|--------|------|
| 企画 | Gemini | gemini-2.5-flash | 創造性・高速 |
| 分析専門 | ChatGPT | gpt-5-chat-latest | 論理思考・高品質 |
| 実装専門 | Groq | llama-4-scout | 高速処理 |
| デザイナー | Grok | grok-3-mini-fast | 創造性・独自性 |
| マーケター | Mistral | devstral-small | 効率性・軽量 |
| 秘書 | Anthropic | claude-3-5-haiku | 安全性・丁寧 |

### 強化された診断機能

エラー発生時に詳細な診断情報を提供：

```
🚨 詳細診断情報:
[企画] 🚨 エラー詳細
  Organization: tech_startup
  Config: multi_role_config_tech_startup.json
  Source: role/default_org/planner.txt
  Provider: langchain_google_genai.ChatGoogleGenerativeAI
  Assistant: Gemini
  Model: gemini-2.5-flash
  Error: ⚠️ API制限に達しました
```

## 🔍 診断とトラブルシューティング

### 設定診断ツール

```bash
# 組織設定の事前検証
python test_organizations.py

# 特定組織の詳細確認
python MultiRoleChat.py --org creative_org

# 出力例
✨ 組織: creative_org (創造性特化組織)
� 説明: 制約のない発想と革新的思考に特化した創造的組織

🎭 利用可能なロール (5個):
  ✅ ワイルドアイデア: 常識を破る革新的発想を生み出す
  ✅ ビジョナリー: 未来志向の戦略的視点を提供

🔄 利用可能なワークフロー (4個):
  ✅ creative_brainstorm: 制約のない自由な発想から革新的なアイデアを生み出す
```

### リアルタイム診断

```bash
🎭 MultiRoleChat> config      # 全体設定状況
🎭 MultiRoleChat> list        # ロール一覧と詳細
🎭 MultiRoleChat> debug ワイルドアイデア  # 特定ロールの詳細診断
```

## 📊 ワークフローの例

### 製品開発ワークフロー

```bash
workflow product_development "LLM仮想会社会議チャットボット"
```

**実行ステップ:**
1. **企画** - 要求仕様の整理と優先順位付け
2. **実装専門** - 技術アーキテクチャと実装計画
3. **企画** - ユーザーインターフェース設計
4. **分析専門** - 品質評価とリスク分析
5. **秘書** - 開発スケジュールと成果物整理

### コード生成と自動保存

```bash
# AIがコードを生成してsandboxに自動保存
python MultiRoleChat.py -o tech_startup -w simple_coding -t "フィボナッチ関数の実装"

💾 2 ファイル保存: sandbox/session_20250814_141337/
📁 実行可能ファイル: 2 ファイル保存済み (sandbox/session_20250814_141337/)

# 保存されたファイル構造
sandbox/session_20250814_141337/
├── code_000.py          # Python実装
├── code_001.js          # JavaScript実装
├── run_all.sh           # 実行スクリプト
└── session_info.json    # セッション情報
```

## 🚨 よくある問題と解決策

### API制限エラー
**症状:** `⚠️ API制限に達しました`
**解決策:** プロバイダー分散設定の適用、Fast Modelの使用

### ロール名不一致
**症状:** `⚠️ ロール 'XXX' が見つかりません`
**解決策:** 設定診断ツールでワークフローとロール定義の名前統一

### クレジット不足
**症状:** `⚠️ APIクレジットが不足しています`
**解決策:** 他のプロバイダーへの切り替え、軽量モデルの使用

## 🔄 更新履歴

## 📈 バージョン履歴

### v1.3.0 (2025-08-14)
- 💾 **自動コード保存システム** - AI生成コードの`sandbox/`自動保存機能
- 🔧 **コード保存管理** - セッション別ファイル管理と実行スクリプト生成  
- 📁 **分離実行環境** - 生成と実行の完全分離による安全性確保
- 🐳 **Docker統合準備** - コード実行環境のコンテナ化サポート

### v1.2.0 (2025-08-14)
- 🔧 **統合管理ユーティリティ** - AI設定とコスト管理の一元化 (`update_ai_config.py`)
- 🔍 **プロバイダーマッピング** - AI設定からコスト情報への自動マッピング
- ⚖️ **整合性チェック機能** - AI設定とコスト情報の不整合を自動検出
- 📊 **強化ログヘッダー** - 組織名とロール詳細情報を含む包括的なログ
- 💰 **CSV基盤コスト管理** - ハードコードから動的データベースへの移行
- 🗑️ **重複ツール削除** - `manage_model_costs.py`を統合により廃止

### v1.1.0 (2025-08-14)
- 🆕 **組織別設定システム** - 独立した組織とワークフローの管理
- 🆕 **ワークフロー直接実行** - コマンドラインから直接ワークフロー起動
- 🆕 **創造性特化組織（creative_org）** - ブレインストーミングと革新的思考に特化
- 🆕 **スタンドアロンモード** - 組織設定からの単独実行機能
- 🗑️ **Legacy削除** - 古い設定システムを完全に削除、新システムに一本化
- 🆕 **包括的ドキュメント拡充** - 組織別設定ガイドの追加

### v1.0.0 (2025-08-13)
- 🆕 強化された診断機能とエラー報告
- 🆕 組織情報とプロバイダー情報を含む詳細ログ
- 🆕 設定診断ツール (`test_config.py`)
- 🆕 プロバイダー分散戦略による安定性向上
- 🆕 ロール名統一とワークフロー最適化
- 🆕 包括的なドキュメント整備

## 🤝 コントリビューション

プロジェクトへの貢献を歓迎します：

1. **問題報告** - エラーログと設定情報を含めて報告
2. **機能提案** - 新しいロールやワークフローのアイデア
3. **設定共有** - 業界特化の設定ファイル例
4. **ドキュメント改善** - 使いやすさの向上

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルを参照してください。

---

**LLM Chat System v1.0.0** - AI協働の新しい可能性を探求

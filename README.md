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

**新機能 (v1.6.0):**
- 🔀 **phases スキーマ** - serial / parallel / loop / call によるネストワークフロー
- 📞 **サブルーチン呼び出し** - `type: "call"` で汎用ワークフローを再利用可能
- 📊 **Mermaid subgraph 展開** - call 先の中身をログのフロー図に可視化

**新機能 (v1.5.0):**
- 🏕️ **新規組織追加** - `groq_fast_discussion`（高速議論・ディベート）、`nokuru`（キャラクター会話シミュレーションの実験的サンプル）
- 💡 **使い方ガイド拡充** - 仮想会社会議・ディベート・フィクションへの応用例をREADMEに追加

**新機能 (v1.4.0):**
- 🎯 **クイズ評価システム** - 複数AIプロバイダーの性能比較・ベンチマーク機能
- ⚡ **応答時間測定** - クイズモードでの詳細パフォーマンス分析
- 📊 **性能統計レポート** - 正解率・応答速度・早押しクイズ分析
- 🏆 **8プロバイダー対応** - OpenAI/Google/Anthropic/Groq/Mistral/Together/Grok参加制限解除

**新機能 (v1.3.0):**
- 💾 **自動コード保存システム** - AI生成コードの`sandbox/`自動保存機能
- 🔧 **コード保存管理** - セッション別ファイル管理と実行スクリプト生成
- 📁 **分離実行環境** - 生成と実行の完全分離による安全性確保

**新機能 (v1.2.0):**
- 🔧 **統合管理ユーティリティ** - AI設定とコスト管理の一元化 (`update_ai_config.py`)
- 🔍 **プロバイダーマッピング** - AI設定からコスト情報への自動マッピング
- ⚖️ **整合性チェック機能** - AI設定とコスト情報の不整合を自動検出

**新機能 (v1.1.0):**
- 🏢 **組織別設定システム** - 独立した組織とワークフローの管理
- ⚡ **ワークフロー直接実行** - コマンドラインから直接ワークフロー起動
- 🎨 **創造性特化組織** - ブレインストーミングと革新的思考に特化
- 🤖 **スタンドアロンモード** - 組織設定からの単独実行機能
- 💬 **インタラクティブ会議** - `-i`オプションで人間も会議に参加可能
- 👨‍💼 **モデレーター機能** - `role_type: "moderator"`で会議の自動まとめ
- ⚡ **並列処理対応** - quiz/meetingコマンドの高速化
- 🛡️ **レート制限対策** - APIリクエストを0.3秒ずつずらして送信
- 🔢 **ラウンド数指定** - `-r`オプションで会議のラウンド数をカスタマイズ

**新機能 (v1.0.0):**
- 📊 組織情報とプロバイダー情報を含む詳細エラー診断
- 🛠️ 設定ファイル検証ツール (`test_config.py`)
- 📋 リアルタイム設定確認コマンド (`config`, `debug`)
- 🔧 ロール名統一とプロバイダー分散による安定性向上

### 2. Single Chat - 高度なAIチャットシステム

複数プロバイダー対応の洗練されたチャット機能

**主要機能:**
- 🎯 **複数プロバイダー対応** - OpenAI/Anthropic/Google/Groq/Mistral/Together対応
- 📋 **まとめ機能** - AI による会話履歴の自動要約とファイル保存
- 🔄 **高度なエラーハンドリング** - API制限エラーの自動対応とリトライ機能
- 💾 **会話履歴管理** - CSVログとセッション復元機能
- ⚡ **トークン節約機能** - まとめエントリの履歴除外によるトークン消費削減
- 🔧 **複数行編集** - 高度な行編集機能（もとい/ちゃいちゃい）

**新機能 (v8.0.0):**
- 🚨 **包括的API制限エラー対応** - 413/429/503/504エラーの自動検出・対応
- 📏 **自動履歴削減** - 413エラー時の会話履歴自動削減とリトライ
- 💡 **トークン節約機能** - まとめを会話履歴から除外してトークン消費削減
- 🎯 **エラー種別判定** - エラーコードとキーワードベースの正確な判定
- ⏰ **スマートリトライ** - エラー種別に応じた最適化された再試行戦略

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
- 🚀 **[クイックスタート](docs/single-chat/quickstart.md)** - 高度なチャット機能の使用方法
- 📖 **[メインガイド](docs/single-chat/README.md)** - 基本機能と設定
- 🚨 **[エラーハンドリング](docs/single-chat/error-handling.md)** - API制限エラー対応機能

## 🔧 統合管理ユーティリティ

### 1. モデルコスト管理（SQLite） - `model_costs_db.py`

**NEW!** `model_costs.csv`をSQLiteデータベースとして管理し、高度な分析が可能：

```bash
# データベースにロード
python model_costs_db.py load

# 最安値モデルを検索
python model_costs_db.py cheapest --limit 5

# プロバイダー別比較
python model_costs_db.py provider OpenAI

# 2つのCSVファイルを比較
python model_costs_db.py compare-files model_costs.csv model_costs_backup.csv

# 価格変動を分析
python model_costs_db.py price-changes

# SQLクエリを実行
python model_costs_db.py sql "SELECT * FROM model_costs WHERE provider='OpenAI'"

# インタラクティブSQLモード
python model_costs_db.py sql-interactive

# グラフ生成（matplotlibが必要）
python model_costs_db.py price-changes --graph
```

**SQLクエリ集（`sql/`フォルダ）:**
- `01_check_dates.sql` - 日付確認
- `02_cheapest_models.sql` - 最安値モデル
- `03_provider_comparison.sql` - プロバイダー比較
- `04_price_changes.sql` - 価格変動分析
- `05_groq_models.sql` - Groqモデル一覧
- `06_new_models.sql` - 新規追加モデル
- 他多数...

### 2. 組織設定バリデーション - `validate_org_configs.py`

組織設定ファイルのモデル名を`model_costs.csv`と照合し、自動修正：

```bash
# 全組織の設定を検証
python validate_org_configs.py validate

# 自動修正（同じタイプのモデルに置換）
python validate_org_configs.py fix

# 即座に修正を適用
python validate_org_configs.py fix-force
```

**機能:**
- ✅ モデル名の存在確認
- ✅ 同じタイプのモデルへの自動置換（Opus→Opus、70B→70B）
- ✅ バックアップ自動作成
- ✅ 詳細レポート出力

### 3. AI設定とコスト管理 - `update_ai_config.py`

AI設定とコスト管理を一元的に行うツール：

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
# 1. インタラクティブ会議（NEW v1.1.0）- あなたも参加！
python MultiRoleChat.py --org creative_org --demo
🎭 MultiRoleChat> meeting -i "革新的なAIサービスアイデア"

# 2. 組織指定とワークフロー直接実行（推奨）
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"

# 3. クイズ評価システム（並列処理対応）- AIモデル性能比較
python MultiRoleChat.py --org quiz_evaluation --demo
🎭 MultiRoleChat> quiz multiline continuous

# 4. 利用可能な組織とワークフローの確認
python MultiRoleChat.py --org creative_org

# 5. 組織を指定して対話モードで起動
python MultiRoleChat.py --org tech_startup

# 6. デモモードでの起動
python MultiRoleChat.py --demo

# 7. ワークフロー実行（対話モード内）
🎭 MultiRoleChat> workflow product_development "LLM仮想会社会議チャットボット"

# 8. 高速並列クイズ（対話モード内）
🎭 MultiRoleChat> quiz "日本で2番目に面積の大きい都道府県は？"
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
│   ├── quiz_evaluation/              # クイズ評価組織（NEW）
│   │   ├── config.json               # 8つのAIプロバイダー設定
│   │   ├── README.md                 # 性能評価結果・使用方法
│   │   └── roles/
│   │       └── quiz_king.txt         # 自称クイズ王キャラクター
│   ├── groq_fast_discussion/          # Groq専用高速議論・ディベート組織
│   │   ├── config.json               # 3ワークフロー: quick_discussion/debate/issue_discussion
│   │   └── roles/                    # リーダー・アナリスト・リスク評価・ファシリテーター
│   ├── nokuru/                        # キャラクター会話シミュレーションの実験的サンプル
│   │   ├── config.json               # 3ワークフロー: camp_planning/camp_discussion/solo_vs_group
│   │   └── roles/                    # ひなた・さつき・ゆき（ゲスト）・かえで
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

### 💡 こんな使い方もできます

MultiRoleChatの本質は **「役割を持ったエージェントに初期条件を与えて自律展開させる」** シミュレーターです。  
`roles/*.txt`（専門性・性格の定義）と `config.json`（場面・フロー構成）の組み合わせで、以下のような幅広い用途に対応できます。

| 要素 | 仮想会社として | ディベートとして | フィクションとして |
|------|--------------|----------------|------------------|
| `roles/*.txt` | 社員の専門性・職責 | 論者の立場・論拠スタイル | キャラクターの性格・裏設定 |
| `config.json workflows` | 会議の進行手順 | 賛否往復のラウンド構成 | 幕・章・シーンの構成 |
| `initial_message` | 議題 | 論題 | 物語の発端・状況設定 |
| `moderator` ロール | 司会・議事録 | 審判・論点整理 | ナレーター・舞台監督 |
| `max_rounds` | 議論の持ち時間 | ラウンド数 | シーンの尺 |

**例: 仮想会社会議**
```bash
python MultiRoleChat.py --org tech_startup --workflow product_development --topic "次世代AIアシスタントのMVP設計"
```

**例: 高速ディベート**
```bash
python MultiRoleChat.py --org groq_fast_discussion --workflow debate --topic "AIによる意思決定は人間の判断より信頼できるか"
```

**例: キャラクター会話シミュレーション（実験的サンプル）**
```bash
python MultiRoleChat.py --org nokuru --workflow camp_planning --topic "春休みのキャンプ計画"
```

> 💡 **裏設定の重要性**  
> 表に出さない動機・コンプレックス・人間関係の歴史をロール設定に含めると、  
> キャラクターの発言が表面的な役割を超えた深みを持ちます。  
> これは小説家が語る「キャラが勝手に動く」感覚に近い現象です。

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

### v1.6.0 (2026-04-23)
- 🔀 **phases スキーマ** - serial / parallel / loop / call の4タイプによるネストワークフロー
- 📞 **サブルーチン呼び出し** - `type: "call"` で汎用ワークフローを複数箇所から再利用
- 🔒 **循環呼び出し検出** - frozenset による call_stack 管理で無限ループを防止
- 📊 **Mermaid subgraph 展開** - call 先の中身をログのフロー図に自動展開・可視化

### v1.5.0 (2026-03-15)
- 🏕️ **新規組織追加** - `groq_fast_discussion`（高速議論・ディベート）、`nokuru`（キャラクター会話シミュレーションの実験的サンプル）
- 💡 **使い方ガイド拡充** - 仮想会社・ディベート・フィクションへの応用例をREADMEに追記
- 🔖 **モデル更新** - 各組織の使用モデルを最新版に更新

### v1.4.0 (2025-08-16)
- 🎯 **クイズ評価システム** - quiz_evaluation組織による複数AIプロバイダー性能比較機能
- ⚡ **応答時間測定** - クイズモードでの詳細パフォーマンス分析と統計
- 📊 **性能統計レポート** - 正解率・応答速度・早押しクイズ王決定戦分析
- 🏆 **8プロバイダー対応** - OpenAI/Google/Anthropic/Groq/Mistral/Together/Grok参加制限解除
- 🔧 **API問題解決** - Together APIのモデル変更とG検定ベース評価システム確立

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

## 🧪 テスト

`tests/`ディレクトリには各機能の検証スクリプトが含まれています：

```bash
# 設定ファイルの検証
python tests/test_config.py

# 組織設定の整合性チェック
python tests/test_organizations.py

# ワークフロー機能のテスト
python tests/test_workflow_logging.py
```

詳細は [`tests/README.md`](tests/README.md) を参照してください。

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルを参照してください。

---

**LLM Chat System v1.6.0** - AI協働の新しい可能性を探求

# LLM チャットシステム 🤖

複数のLLMを活用した包括的なAI対話システム集です。

## 💡 プロジェクト概要

このプロジェクトは、**対話を通じて思考を整理し、知識として構造化する**ことを目的とした、2つの専門的なチャットシステムを提供します。

### なぜ作ったのか

- 複数のLLMモデルを気軽に試し比べたい
- 会話の中から重要なアイデアや知見を効率的に抽出したい  
- マークダウン形式でナレッジベースを構築したい
- 各モデルの特性や癖を実際の使用を通じて理解したい

### なぜCLIなのか

- **μConsoleでの通勤中利用**: 移動時間を思考整理時間に変換
- **軽量性**: 場所を選ばず、どこでもAI協働環境を実現
- **継続性**: ブラウザやアプリに依存しない安定した対話環境
- **効率性**: キーボード主体の高速操作

## 🎯 システム構成

### 1. Chat.py - シングルチャットシステム

1対1の高度なAI会話システム

- **用途**: 個人的な思考整理、アイデア出し、学習支援
- **特徴**: まとめ機能、複数行編集、履歴管理
- **対象**: 日常的なAI対話を効率化したいユーザー

📖 **詳細**: [docs/single-chat/README.md](docs/single-chat/README.md)

### 2. MultiRoleChat.py - マルチロールチャットシステム

複数AIロール間での協調的会話システム（v1.0.0 with Fast Model Support）

- **用途**: チーム会議、ブレインストーミング、専門家会議、ワークフロー実行
- **特徴**: 
  - 仮想AI組織による専門ロール分担（最大20ロール）
  - ワークフロー自動化、ロール管理、AI進行役
  - **Fast Modelモード**（約2-3倍高速応答）
  - **自動ログ保存**（会話、会議、ワークフローのMarkdown形式記録）
  - **堅牢なエラーハンドリング**（APIレート制限、クレジット不足対応）
- **対象**: 複数の視点から問題を検討したいユーザー

📖 **詳細**: [docs/multi-role-chat/README.md](docs/multi-role-chat/README.md)

## 🔧 共通基盤

### サポートAIモデル

**標準モデル**: ChatGPT, Claude, Gemini, Groq, Together AI, Mistral, Grok
**Fast Modelサポート**: 高速応答用軽量モデル自動切替（約2-3倍高速）

### 主な機能

- **動的AI設定管理**: CSVベースの統一設定システム
- **カスタムシステムメッセージ**: 専用ファイルによる動作制御
- **自動要約機能**: 会話内容の構造化まとめ
- **Foam/Obsidian連携**: Markdownベースのナレッジ構築
- **Fast Model自動切替**: `--fast`オプションで高速応答モード

📖 **詳細**: [設定ガイド](docs/shared/configuration.md)

## 🚀 クイックスタート

```bash
# 1. ライブラリインストール
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq

# 2. APIキー設定（最低1つ）
export GROQ_API_KEY="your-api-key"      # Linux/Mac
$env:GROQ_API_KEY="your-api-key"        # Windows PowerShell

# 3. システム選択
python Chat.py                          # シングルチャット（個人向け）
python Chat.py --fast                   # 高速モード
python MultiRoleChat.py --demo          # マルチロールチャット（チーム向け）
python MultiRoleChat.py --fast          # マルチロール高速モード
```

📖 **詳細な手順**: [セットアップガイド](docs/shared/setup.md)

## 📁 プロジェクト構成

```text
llm-chat-system/
├── Chat.py                      # シングルチャットシステム
├── MultiRoleChat.py             # マルチロールチャットシステム
├── ai_assistants_config.csv     # AI設定（共通）
├── system_message.txt           # デフォルトシステムメッセージ
├── multi_role_config.json       # マルチロール設定
├── update_ai_config.py          # AI設定更新スクリプト
├── update_ai_models.bat         # AI設定更新バッチファイル
├── role/                        # ロール定義ファイル群（12種類）
├── logs/                        # Chat.py ログ
├── summaries/                   # 自動要約ファイル
├── docs/                        # 体系化されたドキュメント
│   ├── single-chat/             # Chat.py 専用ドキュメント
│   ├── multi-role-chat/         # MultiRoleChat.py 専用ドキュメント
│   └── shared/                  # 共通ドキュメント
└── README.md                    # このファイル
```

## 📖 ドキュメント

### 🚀 はじめる

- **[セットアップガイド](docs/shared/setup.md)** - 環境構築の詳細手順
- **[設定ガイド](docs/shared/configuration.md)** - AI設定のカスタマイズ
- **[トラブルシューティング](docs/shared/troubleshooting.md)** - よくある問題の解決

### 📘 システム別ガイド

- **[Chat.py 完全ガイド](docs/single-chat/README.md)** - シングルチャットの詳細
- **[Chat.py クイックスタート](docs/single-chat/quickstart.md)** - すぐに始める
- **[MultiRoleChat.py 完全ガイド](docs/multi-role-chat/README.md)** - マルチロールの詳細  
- **[MultiRoleChat.py クイックスタート](docs/multi-role-chat/quickstart.md)** - すぐに始める
- **[実践チュートリアル](docs/multi-role-chat/examples.md)** - 活用事例とコツ

## 🔧 技術仕様

**開発環境**: Python 3.8+, LangChain  
**設定管理**: CSV, JSON  
**ファイル管理**: 分離型（デフォルト）/ 統合型（オプション）

📖 **詳細**: 各システムのREADMEを参照

## 🤝 開発履歴

このプロジェクトは反復的なLLM開発の集大成です：

**Phase 1**: Chat.py - 基本的な1対1会話システム（18回の反復開発）  
**Phase 2**: MultiRoleChat.py - 複数ロール協調システム  
**Phase 3**: 統合プラットフォーム - 両システムの統合運用

## 🎯 使い分けガイド

| 用途 | おすすめシステム | 理由 |
|------|------------------|------|
| 日常的な質問・相談 | Chat.py | シンプルで高速 |
| 学習・調査 | Chat.py | まとめ機能が有効 |
| アイデア発想 | MultiRoleChat.py | 多角的視点 |
| プロジェクト企画 | MultiRoleChat.py | ワークフロー活用 |
| 技術検討 | MultiRoleChat.py | 専門家ロール活用 |

## 📄 ライセンス

MIT License

---

**開発期間**: 2024-2025年  
**最新版**: Chat.py v7.0.0, MultiRoleChat.py v1.0.0  
**ステータス**: 本番環境対応済み

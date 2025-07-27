# LLM チャットシステム 🤖

複数モデル対応と高度な機能を備えた洗練されたAI会話システムです。

## 💡 開発動機

このシステムは、**対話を通じて思考を整理し、知識として構造化する**という課題を解決するために開発されました。

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

### 既存ツールとの違い
- **複数モデル対応**: 1つのインターフェースで様々なLLMを切り替え
- **自動要約機能**: 会話から重要な部分を自動抽出
- **構造化出力**: Foamなどのナレッジ管理ツール連携を想定
- **継続的改善**: 使用ログから各モデルの特性分析が可能

単なるチャットツールではなく、**思考整理とナレッジ管理の統合プラットフォーム**を目指しています。

## 🌟 機能

### 🔧 主要コンポーネント
- **Chat.py**: 複数モデル対応の高度なAI会話システム
- **ai_assistants_config.csv**: AIモデル設定ファイル
- **update_ai_config.py**: AI設定更新用Pythonスクリプト
- **update_ai_models.bat**: AI設定更新用バッチファイル（Windows）

### 🛠️ 主な機能
- 複数プロバイダーのAIモデル対応（ChatGPT、Claude、Gemini、Groqなど）
- 自動要約機能付き会話履歴管理
- 会話保存のためのファイル出力機能
- 動的モデル切り替え
- パフォーマンス監視とログ記録

## 🚀 クイックスタート

### 必要な準備
```bash
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq langchain-together langchain-mistralai
```

### 環境設定

**⚠️ 重要: APIキーの設定**

環境変数としてAPIキーを設定してください：
```bash
set OPENAI_API_KEY=your_openai_key
set ANTHROPIC_API_KEY=your_anthropic_key  
set GOOGLE_API_KEY=your_google_key
set GROQ_API_KEY=your_groq_key
set TOGETHER_API_KEY=your_together_key
set MISTRAL_API_KEY=your_mistral_key
```

**📝 注意事項:**
- 使用するAIモデルに対応するAPIキーの設定が必要です
- APIキーが設定されていない場合、認証エラーが発生します
- 少なくとも1つのAPIキー（推奨：GROQ_API_KEY）を設定してください

## ⚠️ トラブルシューティング

### よくあるエラー

**1. APIキー未設定エラー**
```
Error: API key not found
```
→ 対応するAPIキーを環境変数に設定してください

**2. 認証エラー**
```
AuthenticationError: Invalid API key
```
→ APIキーが正しく設定されているか確認してください

**3. モデル未対応エラー**
```
Model not supported
```
→ ai_assistants_config.csv で対応モデルを確認してください

### 基本的な使用方法
```bash
# ヘルプ表示
python Chat.py --help

# デフォルトモデル（Groq）でのインタラクティブチャット
python Chat.py

# 特定のAIアシスタントとのチャット
python Chat.py -a ChatGPT

# 特定のモデルとのチャット
python Chat.py -a Claude -m claude-3-haiku-20240307

# 高速モードで実行
python Chat.py -a ChatGPT --fast

# 最新の会話ログを読み込んで継続
python Chat.py --latest
```

**📖 詳細なオプション:**
- `--help`: 使用方法とオプションの詳細表示
- `-a, --assistant`: 使用するAIアシスタント名
- `-m, --model`: 使用するモデル名
- `--fast`: 高速モード（簡易設定）
- `--latest`: 最新の会話ログを自動読み込み
- `-l, --load`: 指定した会話ログファイルを読み込み

### AI設定の更新

**AI設定ファイル（ai_assistants_config.csv）の更新:**

```bash
# Pythonスクリプトで設定を更新
python update_ai_config.py

# Windowsバッチファイルで設定を更新（GitHubから最新版を取得）
update_ai_models.bat
```

**📝 設定更新の詳細:**
- `update_ai_config.py`: 対話式でAI設定を追加・編集・削除
- `update_ai_models.bat`: GitHubリポジトリから最新のAI設定を自動取得
- 設定更新後は新しいモデルが即座に利用可能

## 📁 プロジェクト構成

```
├── Chat.py                 # メイン会話システム
├── ai_assistants_config.csv # AIモデル設定
├── system_message.txt      # システムメッセージ設定
├── update_ai_config.py     # AI設定更新スクリプト
├── update_ai_models.bat    # AI設定更新バッチファイル
└── README.md              # このドキュメント
```

## 🔧 技術的特徴

### 対応AIモデル

- ChatGPT (OpenAI)
- Claude (Anthropic)
- Gemini (Google)
- Groq
- Together AI
- Mistral
- Grok (xAI)

### 高度な機能

- **会話履歴管理**: 自動要約機能付きカスタム実装
- **ファイル出力**: 整理された形式で会話を保存
- **パフォーマンス監視**: 実行時間追跡
- **動的設定**: CSV ベースのモデル設定
- **複数行入力**: 複雑なプロンプトに対応

## 🤝 開発履歴

このプロジェクトは反復的なLLM開発の集大成を表しています：

- **Chat.py**: すべての高度な機能を組み込んだ最新版（Chat7.pyから進化）
- **段階的進化**: 基本的なQ&Aから洗練された会話管理へ
- **18回の開発反復**: Chat1.pyからChat7.pyまでの完全な進化

## 📄 ライセンス

MIT License

---

**開発期間**: 2024-2025年  
**最新版**: Chat.py（Chat7.pyから進化）  
**ステータス**: 本番環境対応済み

# LLM チャットシステム 🤖

複数モデル対応と高度な機能を備えた洗練されたAI会話システムです。

## 🌟 機能

### 🔧 主要コンポーネント
- **Chat.py**: 複数モデル対応の高度なAI会話システム
- **ai_assistants_config.csv**: AIモデル設定ファイル

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

## 📁 プロジェクト構成

```
├── Chat.py                 # メイン会話システム
├── ai_assistants_config.csv # AIモデル設定
├── system_message.txt      # システムメッセージ設定
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

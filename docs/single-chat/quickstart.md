# Chat.py クイックスタートガイド

## 🚀 はじめに

Chat.pyは1対1のAI会話に特化した高機能チャットシステムです。最新のFast Modelサポートにより、通常の高品質な応答と高速な応答を使い分けることができます。

## 📦 基本的な起動

```bash
# デフォルト設定（Groq）で起動
python Chat.py

# 特定のAIアシスタントを選択
python Chat.py -a ChatGPT
python Chat.py -a Claude
python Chat.py -a Gemini
```

## ⚡ 高速モードの利用

高速モードでは軽量モデルに自動切り替えされ、約2-3倍高速な応答が得られます：

```bash
# 高速版モデルに自動切り替え
python Chat.py -a ChatGPT --fast
python Chat.py -a Claude --fast
python Chat.py -a Groq --fast
```

### 高速モード対応モデル
- **ChatGPT**: gpt-4o → gpt-4o-mini
- **Claude**: claude-3-5-sonnet → claude-3-5-haiku
- **Groq**: llama-3.1-70b-versatile → llama-3.1-8b-instant

## 💬 基本的な使い方

### 1. 普通の会話
```
あなた: こんにちは！Pythonについて教えてください
```

### 2. 複数行入力モード
```
あなた: multi
=== Chat 複数行入力モード ===
複数行でメッセージを入力してください。
終了するには Ctrl+Z を押してください。

以下のプログラムにバグがあります：
def calculate(x, y):
    result = x + y
    return result

修正方法を教えてください。
[Ctrl+Z]
```

### 3. 会話のまとめ機能
```
あなた: まとめてください
📋 まとめ要求を検出しました。会話履歴をまとめています...
```

## 📁 ファイル管理

### ログの継続
```bash
# 最新の会話ログを自動読み込み
python Chat.py --latest

# 特定のログファイルを指定
python Chat.py -l 20250809_143000
python Chat.py -l logs/conversation.csv
```

### カスタムシステムメッセージ
```bash
# カスタムシステムメッセージファイルを指定
python Chat.py -s teacher_mode.txt
python Chat.py -s expert_consultant.txt
```

## 🎯 実用例

### 学習・研究用途
```bash
# 専門的な質問に最適なモデルを選択
python Chat.py -a Claude -s academic_system.txt
```

### プログラミング支援
```bash
# コード解析に強いモデルを使用
python Chat.py -a ChatGPT --fast
```

### アイデア整理
```bash
# 創造性の高いモデルで発想支援
python Chat.py -a Gemini
```

### 文書作成支援
```bash
# 文章作成に特化したシステムメッセージで起動
python Chat.py -s writing_assistant.txt -a Claude
```

## 📝 会話の効率化

### 複数行編集コマンド
- `show` - 現在の入力内容を表示
- `clear` - 入力内容をクリア
- `もとい` / `ちゃいちゃい` - 直前の行を削除
- `single` - 1行入力モードに戻る

### 特別なコマンド
- `まとめてください` - 会話履歴をAIがまとめてファイル保存
- `さようなら` / `bye` / `exit` - チャット終了

## 🔧 詳細オプション

### モデル継続設定
```bash
# ログ読み込み時にモデル選択を確認
python Chat.py --latest --confirm-model

# ログのモデル設定を無視して指定モデルを強制使用
python Chat.py -l conversation.csv -a Groq --ignore-log-model
```

### デバッグ・情報確認
```bash
# ヘルプ表示
python Chat.py --help

# バージョン情報
python Chat.py --version
```

## 📊 ファイル出力

### 自動保存される内容
- **ログファイル**: `logs/YYYYMMDD_HHMMSS.csv` - 全会話履歴
- **まとめファイル**: `summaries/YYYYMMDD_HHMMSS.md` - AI生成の要約

### ファイル形式
- **ログ**: CSV形式（Excel等で開けます）
- **まとめ**: Markdown形式（Foam/Obsidian連携対応）

## ❓ トラブル解決

### よくある問題

#### APIキーエラー
```bash
# 環境変数の設定確認
echo $GROQ_API_KEY      # Linux/Mac
echo $env:GROQ_API_KEY  # Windows PowerShell
```

#### モジュールエラー
```bash
# 必要なライブラリの再インストール
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq
```

#### ログファイルが見つからない
```bash
# logsフォルダの内容確認
dir logs\               # Windows
ls logs/                # Linux/Mac
```

### 緊急時の対処
```bash
# 最小構成で起動テスト
python Chat.py --version

# 設定ファイルの確認
type ai_assistants_config.csv   # Windows
cat ai_assistants_config.csv    # Linux/Mac
```

## 🎨 カスタマイズ例

### カスタムシステムメッセージファイル

**teacher_mode.txt**:
```
あなたは優秀な教師です。複雑な概念を分かりやすく説明し、学習者の理解を促進してください。
```

**code_reviewer.txt**:
```
あなたは経験豊富なシニアエンジニアです。コードレビューを行い、改善点を具体的に指摘してください。
```

**writing_assistant.txt**:
```
あなたは優秀な編集者です。文章の構成、論理性、読みやすさを向上させるアドバイスを提供してください。
```

## 📚 次のステップ

- **詳細マニュアル**: [Chat.py README](README.md) で全機能を確認
- **共通設定**: [設定ガイド](../shared/configuration.md) でAI設定をカスタマイズ
- **トラブル解決**: [トラブルシューティング](../shared/troubleshooting.md) で問題を解決

---

**これで効率的なAI対話環境の完成です！** 🤖✨

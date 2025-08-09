# セットアップガイド

## 必要な環境

- Python 3.8以上
- pip パッケージマネージャー

## 詳細なインストール手順

### 1. Python環境の確認

```bash
python --version
# または
python3 --version
```

### 2. 必要なライブラリのインストール

```bash
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq langchain-together langchain-mistralai
```

### 3. APIキーの設定

#### Windows (PowerShell)

```powershell
# 永続的な設定
[Environment]::SetEnvironmentVariable("GROQ_API_KEY", "your-api-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-api-key", "User")

# 一時的な設定（セッション内のみ）
$env:GROQ_API_KEY="your-api-key"
$env:OPENAI_API_KEY="your-api-key"
```

#### Windows (コマンドプロンプト)

```cmd
# 永続的な設定
setx GROQ_API_KEY "your-api-key"
setx OPENAI_API_KEY "your-api-key"

# 一時的な設定
set GROQ_API_KEY=your-api-key
set OPENAI_API_KEY=your-api-key
```

#### Linux/Mac

```bash
# ~/.bashrc または ~/.zshrc に追加
echo 'export GROQ_API_KEY="your-api-key"' >> ~/.bashrc
echo 'export OPENAI_API_KEY="your-api-key"' >> ~/.bashrc
source ~/.bashrc

# 一時的な設定
export GROQ_API_KEY="your-api-key"
export OPENAI_API_KEY="your-api-key"
```

### 4. 設定ファイルの確認

#### ai_assistants_config.csv

システムで利用可能なAIアシスタントの設定を確認：

```bash
# ファイルの存在確認
ls ai_assistants_config.csv

# 内容確認
type ai_assistants_config.csv   # Windows
cat ai_assistants_config.csv    # Linux/Mac
```

### 5. 動作確認

#### Chat.py のテスト

```bash
python Chat.py --help
python Chat.py --version
```

#### MultiRoleChat.py のテスト

```bash
python MultiRoleChat.py --help
python MultiRoleChat.py --version
```

## APIキー取得方法

### Groq（推奨・無料）

1. [Groq Console](https://console.groq.com/) にアクセス
2. アカウント作成・ログイン
3. API Keys セクションでキーを生成
4. 高速で無料枠が充実

### OpenAI

1. [OpenAI Platform](https://platform.openai.com/) にアクセス
2. アカウント作成・ログイン
3. API keys セクションでキーを生成
4. 課金が必要だが高品質

### Anthropic (Claude)

1. [Anthropic Console](https://console.anthropic.com/) にアクセス
2. アカウント作成・ログイン
3. API Keys セクションでキーを生成

### Google (Gemini)

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. Google アカウントでログイン
3. API key を生成

## トラブルシューティング

### よくある問題

#### ModuleNotFoundError

```bash
# 不足しているモジュールをインストール
pip install [モジュール名]
```

#### APIキーエラー

- 環境変数が正しく設定されているか確認
- APIキーが有効で、クレジット残高があるか確認
- キーに不要なスペースや改行が含まれていないか確認

#### ファイル権限エラー

```bash
# Windowsの場合
# 管理者権限でコマンドプロンプトを実行

# Linux/Macの場合
chmod +x Chat.py
chmod +x MultiRoleChat.py
```

## 高度な設定

### 仮想環境の使用

```bash
# 仮想環境作成
python -m venv llm-chat-env

# 仮想環境アクティベート
# Windows
llm-chat-env\Scripts\activate
# Linux/Mac
source llm-chat-env/bin/activate

# ライブラリインストール
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq langchain-together langchain-mistralai
```

### システムメッセージのカスタマイズ

```bash
# カスタムシステムメッセージファイルを作成
cp system_message.txt my_custom_system.txt
# ファイルを編集

# 使用時に指定
python Chat.py -s my_custom_system.txt
```

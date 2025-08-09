# AI設定ガイド

## ai_assistants_config.csv の構造

このファイルは、システムで利用可能な全AIアシスタントの設定を管理します。

### フォーマット

```csv
assistant_name,module,class,model,fast_model
ChatGPT,langchain_openai,ChatOpenAI,gpt-4o,gpt-4o-mini
Groq,langchain_groq,ChatGroq,llama-3.1-70b-versatile,llama-3.1-8b-instant
Claude,langchain_anthropic,ChatAnthropic,claude-3-5-sonnet-20241022,claude-3-haiku-20240307
Gemini,langchain_google_genai,ChatGoogleGenerativeAI,gemini-2.5-flash,gemini-1.5-flash
```

### 列の説明

| 列名 | 説明 | 例 |
|------|------|-----|
| `assistant_name` | システム内での識別名 | `ChatGPT`, `Groq` |
| `module` | LangChainモジュール名 | `langchain_openai` |
| `class` | 利用するクラス名 | `ChatOpenAI` |
| `model` | デフォルトモデル名 | `gpt-4o` |
| `fast_model` | 高速版モデル名（オプション） | `gpt-4o-mini` |

## 新しいAIプロバイダーの追加

### 1. 必要なライブラリのインストール

```bash
# 例：新しいプロバイダーのライブラリをインストール
pip install langchain-newprovider
```

### 2. CSVファイルへの追加

```csv
NewProvider,langchain_newprovider,ChatNewProvider,default-model,fast-model
```

### 3. 環境変数の設定

```bash
export NEWPROVIDER_API_KEY="your-api-key"
```

### 4. 設定の更新

```bash
# 設定更新スクリプトを実行
python update_ai_config.py

# またはバッチファイル（Windows）
update_ai_models.bat
```

## モデル設定の詳細

### OpenAI (ChatGPT)

```csv
ChatGPT,langchain_openai,ChatOpenAI,gpt-4o,gpt-4o-mini
```

**利用可能モデル**:
- `gpt-4o` - 最新の高性能モデル
- `gpt-4o-mini` - コスト効率の良いモデル
- `gpt-4-turbo` - 高性能ターボモデル
- `gpt-3.5-turbo` - 従来の高速モデル

### Anthropic (Claude)

```csv
Claude,langchain_anthropic,ChatAnthropic,claude-3-5-sonnet-20241022,claude-3-haiku-20240307
```

**利用可能モデル**:
- `claude-3-5-sonnet-20241022` - 最新の高性能モデル
- `claude-3-opus-20240229` - 最高性能モデル
- `claude-3-haiku-20240307` - 高速モデル

### Google (Gemini)

```csv
Gemini,langchain_google_genai,ChatGoogleGenerativeAI,gemini-2.5-flash,gemini-1.5-flash
```

**利用可能モデル**:
- `gemini-2.5-flash` - 最新の高速モデル
- `gemini-1.5-pro` - 高性能モデル
- `gemini-1.5-flash` - バランス型モデル

### Groq

```csv
Groq,langchain_groq,ChatGroq,llama-3.1-70b-versatile,llama-3.1-8b-instant
```

**利用可能モデル**:
- `llama-3.1-70b-versatile` - 高性能モデル
- `llama-3.1-8b-instant` - 超高速モデル
- `mixtral-8x7b-32768` - Mixtralモデル

## 高速モデルの活用

### --fast スイッチの使用

```bash
# 通常モデル
python Chat.py -a ChatGPT

# 高速モデル（自動切り替え）
python Chat.py -a ChatGPT --fast
```

### 高速モデルの設定

高速モデルが設定されている場合、`--fast` スイッチで自動的に切り替わります：

```csv
assistant_name,module,class,model,fast_model
ChatGPT,langchain_openai,ChatOpenAI,gpt-4o,gpt-4o-mini
```

上記設定で `--fast` を使用すると、自動的に `gpt-4o-mini` に切り替わります。

## 設定の検証

### 設定ファイルの構文チェック

```python
# Python での検証
import csv

with open('ai_assistants_config.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(f"Assistant: {row['assistant_name']}, Model: {row['model']}")
```

### 接続テスト

```bash
# 特定のアシスタントでテスト
python Chat.py -a ChatGPT --version
python MultiRoleChat.py --demo --help
```

## トラブルシューティング

### よくある設定エラー

#### CSVフォーマットエラー

- カンマの数が合わない
- 引用符の対応が正しくない
- エンコーディングの問題（UTF-8で保存）

#### モデル名エラー

- 提供されていないモデル名を指定
- タイポやスペースの誤り
- 大文字小文字の間違い

#### APIキー関連

- 環境変数名と設定ファイルの対応確認
- APIキーの有効性確認
- クレジット残高の確認

### デバッグ方法

```bash
# 詳細なエラー出力で実行
python Chat.py -a ChatGPT --version

# 設定ファイルの内容確認
type ai_assistants_config.csv   # Windows
cat ai_assistants_config.csv    # Linux/Mac
```

## バックアップと復元

### 設定のバックアップ

```bash
# 日付付きバックアップ作成
copy ai_assistants_config.csv ai_assistants_config_backup_$(Get-Date -Format "yyyyMMdd_HHmmss").csv
```

### 設定の復元

```bash
# バックアップから復元
copy ai_assistants_config_backup_20250809_123456.csv ai_assistants_config.csv
```

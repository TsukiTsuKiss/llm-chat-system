# トラブルシューティング

## よくある問題と解決策

### インストール関連

#### ModuleNotFoundError

**症状**: `ModuleNotFoundError: No module named 'langchain_openai'`

**解決策**:

```bash
# 必要なモジュールをインストール
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq langchain-together langchain-mistralai

# 仮想環境を使用している場合
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install [必要なモジュール]
```

#### Python バージョンエラー

**症状**: `SyntaxError` や互換性エラー

**解決策**:

```bash
# Pythonバージョン確認
python --version

# Python 3.8以上が必要
# アップデートまたは適切なバージョンをインストール
```

### APIキー関連

#### 認証エラー

**症状**: `Authentication failed` や `Invalid API key`

**解決策**:

1. **APIキーの確認**:

```bash
# 環境変数の確認
echo $GROQ_API_KEY      # Linux/Mac
echo $env:GROQ_API_KEY  # Windows PowerShell
```

2. **APIキーの再設定**:

```bash
# Windows PowerShell
$env:GROQ_API_KEY="your-correct-api-key"

# Linux/Mac
export GROQ_API_KEY="your-correct-api-key"
```

3. **APIキーの有効性確認**:
   - 各プロバイダーのコンソールでキーが有効か確認
   - クレジット残高があるか確認
   - キーの権限設定を確認

#### レート制限エラー

**症状**: `Rate limit exceeded` や `429 Too Many Requests`

**解決策**:

- システムには自動リトライ機能が内蔵されています
- しばらく待ってから再実行
- 別のAPIプロバイダーに切り替え

```bash
# 別のプロバイダーに切り替え
python Chat.py -a Groq  # GroqからChatGPTに変更
python Chat.py -a ChatGPT
```

### ファイル関連

#### ログファイルエラー

**症状**: `Permission denied` でログファイルに書き込めない

**解決策**:

1. **権限の確認**:

```bash
# Windows - 管理者権限でコマンドプロンプトを実行
# Linux/Mac
chmod 755 logs/
chmod 644 logs/*
```

2. **ディスク容量の確認**:

```bash
# ディスク容量確認
dir           # Windows
df -h         # Linux/Mac
```

#### 設定ファイルエラー

**症状**: `CSV parsing error` や設定ファイルの読み込みエラー

**解決策**:

1. **ファイルフォーマットの確認**:

```bash
# ファイルの存在確認
ls ai_assistants_config.csv

# ファイル内容の確認
type ai_assistants_config.csv   # Windows
cat ai_assistants_config.csv    # Linux/Mac
```

2. **CSVフォーマットの修正**:
   - カンマの数を確認
   - 引用符の対応を確認
   - UTF-8エンコーディングで保存

### 実行時エラー

#### システムメッセージファイルエラー

**症状**: `System message file not found`

**解決策**:

```bash
# デフォルトファイルの確認
ls system_message.txt

# カスタムファイルを指定する場合
python Chat.py -s custom_system.txt

# ファイルが存在しない場合は作成
echo "You are a helpful assistant." > system_message.txt
```

#### メモリ不足エラー

**症状**: `MemoryError` や極端に遅い動作

**解決策**:

1. **履歴の制限**:
   - デフォルトで履歴は制限されていますが、さらに短縮可能
   - `MAX_HISTORY_LENGTH` の値を小さくする

2. **高速モデルの使用**:

```bash
python Chat.py --fast
python MultiRoleChat.py --demo --fast
```

### ネットワーク関連

#### 接続エラー

**症状**: `Connection error` や `Network timeout`

**解決策**:

1. **インターネット接続の確認**:

```bash
# 基本的な接続テスト
ping google.com
```

2. **プロキシ設定**:

```bash
# プロキシ環境の場合
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
```

3. **ファイアウォール設定**:
   - 企業ネットワークでブロックされている場合がある
   - IT部門に相談

### MultiRoleChat 固有の問題

#### ロール設定エラー

**症状**: `Role not found` や設定ファイルの読み込みエラー

**解決策**:

1. **設定ファイルの確認**:

```bash
# 設定ファイルの存在確認
ls multi_role_config.json
ls role/

# JSON フォーマットの確認
python -m json.tool multi_role_config.json
```

2. **ロールファイルの確認**:

```bash
# role/ ディレクトリの内容確認
ls role/
```

#### メモリ使用量の問題

**症状**: 複数ロールでの会話時にメモリ使用量が増大

**解決策**:

1. **参加ロール数の制限**:
   - 同時に活動するロール数を減らす
   - 必要に応じてロールの入れ替えを行う

2. **会話履歴の管理**:
   - 定期的に履歴をクリア
   - まとめ機能を活用して履歴を整理

### デバッグ方法

#### 詳細ログの有効化

```bash
# 詳細な実行情報を確認
python Chat.py --help
python MultiRoleChat.py --help

# バージョン情報の確認
python Chat.py --version
python MultiRoleChat.py --version
```

#### ステップバイステップ実行

```bash
# 最小構成でテスト
python Chat.py --latest
python MultiRoleChat.py --demo
```

### 環境別の注意点

#### Windows

- PowerShell と コマンドプロンプトで環境変数設定が異なる
- パスの区切り文字（\\）に注意
- 文字エンコーディング（UTF-8）の設定

#### Linux/Mac

- パーミッション設定に注意
- 仮想環境の活用を推奨
- パッケージマネージャーとの競合に注意

#### 企業環境

- プロキシ設定が必要な場合が多い
- セキュリティソフトによるブロック
- IT ポリシーによる制限

## ヘルプとサポート

### 公式ドキュメント

- [システム別ドキュメント](../README.md)
- [セットアップガイド](setup.md)
- [設定ガイド](configuration.md)

### 問題報告

問題が解決しない場合は、以下の情報を含めて報告してください：

1. **環境情報**:
   - OS（Windows/Linux/Mac）
   - Pythonバージョン
   - インストール済みパッケージ

2. **エラー情報**:
   - 完全なエラーメッセージ
   - 実行したコマンド
   - 期待した動作

3. **設定情報**:
   - 使用中のAPIプロバイダー
   - 設定ファイルの内容（APIキーは除く）

### トラブルシューティングチェックリスト

- [ ] Python 3.8以上がインストールされている
- [ ] 必要なライブラリがインストールされている
- [ ] APIキーが正しく設定されている
- [ ] インターネット接続が正常である
- [ ] 設定ファイルが正しいフォーマットである
- [ ] ファイルとディレクトリの権限が適切である
- [ ] 十分なディスク容量がある

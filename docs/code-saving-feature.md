# コード保存機能について

## 概要
MultiRoleChat.pyは、AIが生成したコードを自動的に`sandbox/`フォルダに保存する軽量機能を提供します。

## 特徴

### ✨ **軽量統合**
- **オプショナル**: `code_saver.py`が存在する場合のみ有効
- **非侵入的**: メインフローに影響なし
- **エラー耐性**: 保存エラーがあってもチャット継続

### 🔄 **自動分離アーキテクチャ**
```
MultiRoleChat.py (AIの仕事)
  ↓ コード生成
  ↓ ファイル保存
sandbox/ (あなたの管理)
  ↓ 独立実行
Docker Sandbox (セキュア実行)
```

### 📁 **保存構造**
```
sandbox/
├── session_20250814_123456/     # セッション別フォルダ
│   ├── code_001.py             # Python コード
│   ├── code_002.js             # JavaScript コード
│   ├── run_all.sh              # 実行スクリプト
│   ├── session_info.json       # セッション情報
│   └── *.meta.json             # ファイルメタデータ
└── results/                     # 実行結果（将来用）
```

## 使用例

### 通常のMultiRoleChat使用
```bash
python MultiRoleChat.py -o tech_startup -w simple_coding -t "フィボナッチ関数"
```

### 出力例
```
💾 2 ファイル保存: sandbox/session_20250814_123456/
- code_001.py (Python)
- code_002.js (JavaScript)

🎉 ワークフロー 'シンプルコーディング' が完了しました！
📁 実行可能ファイル: 2 ファイル保存済み (sandbox/session_20250814_123456/)
```

## Docker実行（完全分離）

```bash
# 生成されたファイルをDocker実行
cd sandbox/session_20250814_123456/
docker run --rm -v $(pwd):/app python:3.11-slim python /app/code_001.py
docker run --rm -v $(pwd):/app node:18-slim node /app/code_002.js

# または一括実行スクリプト
bash run_all.sh
```

## 設定

### 有効化
`code_saver.py`をワークスペースに配置するだけで自動有効化

### 無効化
`code_saver.py`を削除または名前変更で自動無効化

### カスタムフォルダ
```python
# code_saver.py で変更可能
code_saver = CodeSaver(sandbox_dir="custom_folder")
```

## メリット

### 🤖 **AI側 (MultiRoleChat)**
- コード生成に専念
- ファイル保存は自動
- 実行環境は関知不要

### 👤 **ユーザー側**
- 完全な実行制御
- セキュリティ管理
- カスタム実行環境
- バックアップ・共有自由

### 🔒 **セキュリティ**
- AIはファイル保存のみ
- 実行は完全分離
- Docker活用で安全性確保

## 互換性
- **既存コード**: 完全に互換性維持
- **オプショナル**: 機能なしでも正常動作
- **軽量**: パフォーマンス影響なし

---

*この機能により、MultiRoleChat.pyはコード生成に集中し、実行環境は完全にユーザー管理となります。*

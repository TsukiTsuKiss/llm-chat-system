# CodeCraft Collective

## 概要
高速MVP生成に特化した最小限のAI開発組織

## 組織コンセプト
要求から即座に動作するアプリケーションを自動生成する組織。
議論を最小限に抑え、実際に動くプロダクトの迅速な提供を重視。

## メンバー（2名）

### 🔧 全能 統 - フルスタック開発者
- **AI**: ChatGPT (gpt-4o-mini)
- **役割**: 全技術スタック対応、MVP設計と実装
- **専門**: フルスタック開発、プロトタイピング、統合開発

### 🧪 検証 確 - 検証エンジニア
- **AI**: Together (Meta-Llama-3.1-70B-Instruct-Turbo)
- **役割**: 動作確認、品質検証、改善提案
- **専門**: 動作テスト、品質評価、ユーザビリティ

## ワークフロー

### instant_build（即席開発）
**1ステップ**: 全能統が要求から完全なアプリを即座に生成

### rapid_mvp（MVP高速生成）
**2ステップ**: 
1. 全能統 - MVP設計と実装
2. 検証確 - 動作確認と改善提案

## 特徴
- ✅ 議論時間の最小化
- ✅ 実際に動作するアプリの自動生成
- ✅ Webアプリケーション対応
- ✅ 自動実行スクリプト生成
- ✅ ファイル構成の自動最適化
## 使用方法

```bash
# 組織起動（対話モード）
python MultiRoleChat.py --org codecraft_collective

# 対話モードでワークフロー実行
workflow instant_build "シンプルな電卓"
workflow rapid_mvp "じゃんけんゲーム"
```

## 📱 Webアプリの確認方法

ワークフロー実行後、生成されたアプリは以下の方法で確認できます：

### 1. 自動実行スクリプトを使用
```bash
# sandboxフォルダで自動実行
cd sandbox/session_YYYYMMDD_HHMMSS/
bash run_all.sh
```

### 2. ブラウザで直接確認
```bash
# Webサーバーを起動
cd sandbox/session_YYYYMMDD_HHMMSS/
python3 -m http.server 8080

# ブラウザで以下にアクセス
# http://localhost:8080
```

生成されるファイル構成：
- `index.html` - メインのHTMLファイル
- `styles.css` - スタイルシート
- `script.js` - JavaScript機能
- `package.json` - プロジェクト設定
- `run_all.sh` - 自動実行スクリプト

実際に動作するWebアプリケーションが自動生成され、即座に実行・確認可能です。

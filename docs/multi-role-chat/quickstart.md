# MultiRoleChat クイックスタートガイド

## 🚀 はじめに

MultiRoleChatは複数のAIが異なる役割で協働するシステムです。

## 📦 起動方法

```bash
# 技術開発向け（プログラマー、デザイナー、マーケター）
python MultiRoleChat.py --demo

# 企業経営向け（秘書、企画、分析官、実行担当、マーケター、デザイナー）
python MultiRoleChat.py --organization

# 討論・面接などの特定シナリオ
python MultiRoleChat.py --scenario debate
```

## 💬 基本的な使い方

### 1. ロール確認
```bash
list
```

### 2. 個別相談
```bash
chat 企画 "新規事業のアイデアを教えて"
chat 分析官 "市場分析をお願いします"
```

### 3. チーム会議
```bash
# 複数人で議論
meeting 企画 分析官 マーケター "新商品企画について"
```

### 4. ワークフロー実行
```bash
# 体系的な検討プロセス
workflow startup_launch "AI企業の設立"
workflow project_planning "モバイルアプリ開発"
```

## 🎯 実用例

### スタートアップ設立相談
```bash
python MultiRoleChat.py --organization
workflow startup_launch "テクノロジー企業の設立"
```

### 製品開発会議
```bash
python MultiRoleChat.py --demo
meeting プログラマー デザイナー マーケター "新機能の検討"
```

### 市場分析
```bash
python MultiRoleChat.py --organization
workflow market_research "競合他社分析"
```

## 🔧 利用可能なワークフロー

- `startup_launch` - スタートアップ立ち上げ
- `project_planning` - プロジェクト企画
- `product_development` - 製品開発  
- `market_research` - 市場調査
- `new_product_meeting` - 新商品開発会議

## ❓ トラブル解決

### ロールが見つからない場合
```bash
# 現在のロールを確認
list

# 必要に応じて適切なモードで再起動
python MultiRoleChat.py --organization
```

### 終了方法
```bash
exit
```

## 📚 詳細情報

詳しい機能や設定については `MultiRoleChat_Manual.md` を参照してください。

---

**これであなたもAI組織の経営者です！** 🎭

# MultiRoleChat マニュアル

## 概要

MultiRoleChatは、複数のAIアシスタントが異なる役割（ロール）を担当して協働する高度なチャットボットシステムです。企業組織のような構造化された議論、ワークフロー実行、チーム会議を通じて、多角的で包括的な検討を行うことができます。

## ⭐ 主要機能

- **仮想AI組織**: 複数の専門ロールによる協調的問題解決
- **組織別設定システム (NEW)**: 独立した組織とワークフローの管理
- **ワークフロー直接実行 (NEW)**: コマンドラインから直接ワークフロー起動
- **ワークフロー自動化**: 定義済みプロセスの自動実行
- **Fast Modelモード**: 高速応答優先の軽量モード
- **クイズモード**: 複数AIによる一斉質問・回答比較
- **自動ログ保存**: 全会話をMarkdown形式で保存

---

## 📋 目次

1. [システム要件](#システム要件)
2. [基本的な使い方](#基本的な使い方)
3. [設定ガイド](configuration-guide.md) - **組織設定・プロバイダー分散・エラー診断**
4. [設定管理ガイド](configuration-management.md) - **設定ファイル管理・バージョン管理**
5. [トラブルシューティング](troubleshooting.md) - **エラー解決・診断ツール**
6. [モード別詳細](#モード別詳細)
4. [Fast Modelモード](#fast-modelモード)
5. [クイズモード](#クイズモード)
6. [ワークフロー機能](#ワークフロー機能)
7. [チーム会議機能](#チーム会議機能)
8. [ログ保存機能](#ログ保存機能)
9. [コマンド一覧](#コマンド一覧)
10. [設定ファイル詳細](#設定ファイル詳細)
11. [トラブルシューティング](#トラブルシューティング)

---

## システム要件

### 必要ファイル
- `MultiRoleChat.py` - メインプログラム
- `ai_assistants_config.csv` - AI助手設定
- `multi_role_config.json` - ロール・ワークフロー設定
- `role/` フォルダ - 各ロールのシステムプロンプト

### 依存関係
- Python 3.8以上
- langchain
- 各AIサービスのAPIキー設定

---

## 基本的な使い方

### 起動方法

```bash
# 基本起動（空の状態）
python MultiRoleChat.py

# デモモード（技術開発向けロール）
python MultiRoleChat.py --demo

# 組織モード（企業経営向けロール）
python MultiRoleChat.py --organization

# 組織指定とワークフロー直接実行（新機能）
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"

# 利用可能な組織とワークフロー一覧の確認（新機能）
python MultiRoleChat.py --org creative_org

# Fast Modelモード（高速応答）
python MultiRoleChat.py --organization --fast

# シナリオモード（特定用途）
python MultiRoleChat.py --scenario debate
python MultiRoleChat.py --scenario brainstorm
python MultiRoleChat.py --scenario interview
```

### 基本コマンド

```bash
# 利用可能なロールを確認
list

# 特定のロールと対話
chat ロール名 "メッセージ"

# ヘルプ表示
help

# 終了
exit
```

---

## モード別詳細

### 🎭 デモモード（--demo）

**技術開発に特化したロール構成**

| ロール名 | AI | 専門分野 |
|----------|-------|----------|
| プログラマー | ChatGPT | ソフトウェア開発、アーキテクチャ |
| デザイナー | Gemini | UI/UX、ビジュアルデザイン |
| マーケター | Groq | 市場分析、ビジネス戦略 |

**適用場面：**
- アプリケーション開発
- プロダクト企画
- 技術検討

### 🏢 組織モード（--organization）

**企業経営に特化したロール構成**

| ロール名 | AI | 専門分野 |
|----------|-------|----------|
| 秘書 | Anthropic | スケジュール管理、文書作成 |
| 企画 | ChatGPT | 戦略企画、事業計画 |
| 分析官 | Gemini | データ分析、市場調査 |
| 実行担当 | Groq | 技術実装、プロジェクト実行 |
| マーケター | Anthropic | 販売戦略、ブランディング |
| デザイナー | ChatGPT | 製品デザイン、ユーザー体験 |

**適用場面：**
- 事業計画策定
- 組織運営
- 戦略会議

### 🎯 シナリオモード

**特定用途に特化したロール構成**

#### debate（討論）
- 賛成派 vs 反対派による論理的討論

#### brainstorm（ブレインストーミング）
- 創造性重視 vs 実現性重視による発想検討

#### interview（面接）

- 面接官 vs 候補者による面接シミュレーション

### 組織別設定システム（新機能）

`--org` オプションを使用することで、独立した組織設定を利用できます。

#### 利用可能な組織

**creative_org（創造性特化組織）**
- 5つの専門ロール：ワイルドアイデア、ビジョナリー、悪魔の代弁者、創造性重視、モデレーター
- 4つのワークフロー：creative_brainstorm、idea_refinement、innovation_session、vision_planning

```bash
# 組織のワークフロー一覧を確認
python MultiRoleChat.py --org creative_org

# 特定ワークフローの直接実行
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"
```

#### ワークフロー例

**creative_brainstorm**: 制約のない自由な発想から革新的なアイデアを生み出すワークフロー
1. ワイルドアイデア：制約のない自由な発想でアイデアを大量生成
2. ビジョナリー：未来志向で革新的な視点からアイデアを拡張
3. 悪魔の代弁者：批判的思考でアイデアの問題点や落とし穴を指摘
4. 創造性重視：実現可能性を考慮しながら創造的解決策を提案
5. ワイルドアイデア：批判を踏まえてアイデアをより良く改良
6. モデレーター：議論を整理し、最も有望なアイデアを特定

---

## Fast Modelモード

### 概要

`--fast` オプションを使用することで、より高速な応答を重視した軽量モデルを使用できます。

### 使用方法

```bash
# 組織モード + Fast Model
python MultiRoleChat.py --organization --fast

# デモモード + Fast Model  
python MultiRoleChat.py --demo --fast
```

### Fast Model対応

| プロバイダー | 標準モデル | Fast Model | 応答速度 |
|------------|-----------|------------|---------|
| ChatGPT | gpt-5 | gpt-5-chat-latest | ⚡⚡⚡ |
| Gemini | gemini-2.5-pro | gemini-2.5-flash | ⚡⚡⚡ |
| Anthropic | claude-4-opus-20250301 | claude-3-5-haiku-20241022 | ⚡⚡⚡ |
| Groq | llama-3.3-70b-versatile | llama-3.1-8b-instant | ⚡⚡⚡⚡ |

### 特徴

- **応答速度**: 1-5秒（標準: 5-15秒）
- **応答品質**: 簡潔・実用的（標準: 詳細・高品質）
- **コスト**: 低め（標準: 高め）

---

## クイズモード

### 概要

クイズモードは、複数のAIアシスタントに同じ質問を投げて、それぞれの回答を比較検討できる機能です。AIモデル間の性能比較、ベンチマーク、多角的な視点での検討に最適です。

### 基本的な使い方

```bash
# シンプルなクイズモード
quiz "質問内容"

# 複数行の質問（Ctrl+Z/Ctrl+Dで終了）
quiz multiline

# 連続クイズモード（複数の質問を順次実行）
quiz continuous

# 複数行 + 連続モード（デフォルト複数行入力）
quiz multiline continuous
```

### 入力方法の詳細

#### 1. 単一行入力
```bash
quiz "プログラミング言語の選択について教えて"
```

#### 2. 複数行入力
```bash
quiz multiline
# 複数行の質問を入力
# 終了時はCtrl+Z（Windows）またはCtrl+D（Unix系）
```

#### 3. 連続クイズモード
```bash
quiz continuous
# 質問1を入力してEnter → 各AIが回答
# 質問2を入力してEnter → 各AIが回答
# "quit"で終了
```

#### 4. 複数行連続モード
```bash
quiz multiline continuous
# デフォルトで複数行入力モード
# 各質問をCtrl+Z/Ctrl+Dで区切り
# "quit"で終了
```

### クイズ結果の保存

```bash
# ログファイル自動保存
quiz_session_YYYYMMDD_HHMMSS.md
```

### ログファイル形式

```markdown
# Quiz Session - 2024/12/29 10:30:00

## Question 1: プログラミング言語について

### 👨‍💼 CTO (ChatGPT)
プログラミング言語の選択は...

### 🧪 研究者 (Gemini)  
技術的な観点から...

### 🔧 エンジニア (Groq)
実装面を考慮すると...

---
```

### 活用例

#### ベンチマーク比較
```bash
quiz "次のコードの最適化方法を提案してください"
```

#### 多角的検討
```bash
quiz multiline
新規事業の立ち上げについて、
以下の観点から検討してください：
- 市場性
- 技術的実現性  
- 収益性
^Z
```

#### 継続的評価
```bash
quiz continuous
# 複数のシナリオを連続して評価
```

---

## ワークフロー機能

### 概要
事前に定義されたステップに従って、複数のロールが順次作業を行う機能です。

### 利用可能なワークフロー

#### 1. project_planning（プロジェクト企画）
```bash
workflow project_planning "AIチャットボットの開発"
```

**実行ステップ：**
1. 企画：アイデア創出と企画立案
2. 分析官：実現可能性と技術的検討
3. デザイナー：UI/UX設計とユーザー体験検討
4. マーケター：市場性とビジネスモデル評価
5. 秘書：全体のまとめと次のアクションプラン作成

#### 2. startup_launch（スタートアップ立ち上げ）
```bash
workflow startup_launch "テクノロジー企業の設立"
```

**実行ステップ：**
1. 企画：事業コンセプトとビジョンの明確化
2. 分析官：市場調査と競合分析、リスク評価
3. 秘書：法人設立手続きと必要書類の整理
4. 実行担当：技術基盤とシステム要件の検討
5. 企画：資金調達計画と事業計画書作成
6. 秘書：設立スケジュールと次ステップのまとめ

#### 3. product_development（製品開発）
```bash
workflow product_development "スマートフォンアプリの開発"
```

#### 4. market_research（市場調査）
```bash
workflow market_research "競合他社の価格戦略分析"
```

#### 5. new_product_meeting（新商品開発会議）
```bash
workflow new_product_meeting "IoTデバイスの企画"
```

### ワークフローの特徴
- **順次実行**：各ステップが前のステップの結果を踏まえて実行
- **専門性活用**：各ロールの専門知識を活用
- **一貫性**：同じトピックについて体系的に検討
- **記録保持**：全ステップの結果を保存

---

## チーム会議機能

### 概要
複数のロールが参加する構造化された議論を行う機能です。

### 使用方法
```bash
meeting 参加者1 参加者2 参加者3 "議題"

# 例：新商品について6名で会議
meeting マーケター デザイナー 実行担当 分析官 企画 秘書 "新商品のブレインストーミング"
```

### 会議の流れ
1. **ラウンド制**：最大3ラウンドの議論
2. **順次発言**：各参加者が順番に意見を述べる
3. **継続性**：前のラウンドの議論を踏まえて深化
4. **総括**：秘書がいる場合は最終的な総括を実施

### 特徴
- **多角的議論**：異なる専門性からの視点
- **構造化**：organized形式での進行
- **記録**：全発言の記録と要約
- **柔軟性**：参加者数やロールを自由に設定

---

## ログ保存機能

### 概要

すべての会話は自動的にMarkdown形式で保存され、後から確認できます。

### 保存される会話タイプ

| 会話タイプ | ファイル名例 | 保存タイミング |
|-----------|-------------|---------------|
| **Talk** | `talk_20250809_143025.md` | 500文字以上で任意保存 |
| **Conversation** | `conversation_20250809_143025.md` | 自動保存 |
| **Meeting** | `meeting_20250809_143025.md` | 自動保存 |
| **Workflow** | `workflow_20250809_143025.md` | 自動保存 |

### 保存場所

```
multi_logs/
├── meeting_20250809_143025.md
├── workflow_20250809_144120.md
├── conversation_20250809_145030.md
└── talk_20250809_150000.md
```

### ログファイル構造

```markdown
# 会議ログ - 通勤時間活用アプリ開発

**開催日時**: 2025年8月9日 14:30:25
**参加者**: 企画, 分析官, デザイナー

---

## 📋 議事録

### 1. 企画
[企画の発言内容]

### 2. 分析官  
[分析官の発言内容]

## 📝 会議総括
[秘書による総括（会議の場合）]
```

### 特徴

- **構造化**: 発言者別に整理された読みやすい形式
- **検索可能**: Markdown形式でテキスト検索が容易
- **日時管理**: ファイル名に日時が含まれ、時系列管理が可能
- **総括機能**: 会議では秘書ロールによる自動総括

---

## コマンド一覧

### 基本コマンド

| コマンド | 説明 | 例 |
|----------|------|-----|
| `list` | 現在のロール一覧表示 | `list` |
| `talk <ロール> <メッセージ>` | 個別対話 | `talk 企画 "新規事業について"` |
| `help` | ヘルプ表示 | `help` |
| `exit` | 終了 | `exit` |

### ロール管理
| コマンド | 説明 | 例 |
|----------|------|-----|
| `add <ロール> <AI> <モデル> <プロンプト>` | ロール追加 | `add CEO ChatGPT gpt-5 "あなたはCEOです"` |
| `remove <ロール>` | ロール削除 | `remove CEO` |

### 高度な機能
| コマンド | 説明 | 例 |
|----------|------|-----|
| `workflow <ワークフロー名> <トピック>` | ワークフロー実行 | `workflow startup_launch "AI企業設立"` |
| `meeting <参加者...> <議題>` | チーム会議開催 | `meeting 企画 分析官 "戦略検討"` |
| `conversation <ロール1> <ロール2> <メッセージ>` | ロール間対話 | `conversation 企画 分析官 "市場分析"` |

### クイズモード
| コマンド | 説明 | 例 |
|----------|------|-----|
| `quiz "<質問>"` | 全ロールに一斉質問 | `quiz "最適なアーキテクチャは？"` |
| `quiz multiline` | 複数行質問モード | `quiz multiline` |
| `quiz continuous` | 連続クイズモード | `quiz continuous` |
| `quiz multiline continuous` | 複数行連続モード | `quiz multiline continuous` |

---

## 設定ファイル詳細

### multi_role_config.json 構造

```json
{
  "demo_roles": [
    {
      "name": "ロール名",
      "assistant": "AI名",
      "model": "モデル名",
      "system_prompt_file": "role/プロンプトファイル.txt"
    }
  ],
  "organization_roles": [ /* 同様の構造 */ ],
  "workflows": {
    "ワークフロー名": {
      "name": "表示名",
      "steps": [
        {"role": "ロール名", "action": "実行内容"}
      ]
    }
  },
  "scenarios": { /* シナリオ定義 */ }
}
```

### ロール追加方法

1. **プロンプトファイル作成**
```bash
# role/新ロール.txt を作成
echo "あなたは[専門分野]の専門家です。" > role/新ロール.txt
```

2. **設定ファイル更新**
```json
{
  "name": "新ロール",
  "assistant": "ChatGPT",
  "model": "gpt-5",
  "system_prompt_file": "role/新ロール.txt"
}
```

### ワークフロー追加方法

```json
"新ワークフロー": {
  "name": "ワークフロー表示名",
  "steps": [
    {"role": "ロール1", "action": "実行内容1"},
    {"role": "ロール2", "action": "実行内容2"}
  ]
}
```

---

## トラブルシューティング

### よくある問題

#### 1. ロールが見つからない
```
見つからないロール: マーケター, デザイナー
```

**原因：** 指定したロール名が現在のモードに存在しない
**解決策：**
- `list` でロール一覧を確認
- 適切なモードで起動（--demo, --organization）
- または `add` コマンドでロールを追加

#### 2. 設定ファイルが読み込めない
```
[WARNING] マルチロール設定ファイル 'multi_role_config.json' が見つかりません
```

**原因：** 設定ファイルが存在しないか、パスが間違っている
**解決策：**
- ファイルが同じディレクトリにあることを確認
- JSON形式が正しいことを確認

#### 3. プロンプトファイルが読み込めない
```
[WARNING] システムプロンプトファイル 'role/xxx.txt' が見つかりません
```

**原因：** プロンプトファイルが存在しない
**解決策：**
- `role/` フォルダとファイルの存在を確認
- パスが正しいことを確認

#### 4. AI APIエラー
**原因：** APIキーの設定問題、クレジット不足、レート制限
**解決策：**
- APIキーの設定確認
- ai_assistants_config.csv の設定確認
- 別のAIアシスタントに変更

### デバッグ方法

1. **ロール確認**
```bash
list
```

2. **設定確認**
```bash
# 設定ファイルの構文チェック
python -m json.tool multi_role_config.json
```

3. **ファイル存在確認**
```bash
dir role\*.txt  # Windows
ls role/*.txt   # Linux/Mac
```

---

## 応用例

### 1. スタートアップ企業シミュレーション
```bash
python MultiRoleChat.py --organization
workflow startup_launch "AIサービス企業の設立"
meeting 企画 分析官 マーケター "資金調達戦略"
```

### 2. 製品開発プロジェクト
```bash
python MultiRoleChat.py --demo
workflow project_planning "モバイルアプリ開発"
conversation プログラマー デザイナー "技術仕様の検討"
```

### 3. 市場分析会議
```bash
python MultiRoleChat.py --organization
workflow market_research "競合分析"
meeting マーケター 分析官 企画 "市場参入戦略"
```

---

## 更新履歴

- **v1.0.0** - 初回リリース
  - 基本的なマルチロール機能
  - ワークフロー実行
  - チーム会議機能
  - 外部設定ファイル対応

---

## サポート

問題が発生した場合は、以下を確認してください：

1. 全ての必要ファイルが存在する
2. API設定が正しい
3. JSON設定ファイルの構文が正しい
4. ロール名の一致

## ライセンス

このソフトウェアはMITライセンスの下で提供されています。

---

**MultiRoleChat v1.0.0** - 高度なAI協働システム

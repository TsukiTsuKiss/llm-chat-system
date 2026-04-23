# 組織別設定システム ガイド

## 概要

MultiRoleChatの組織別設定システムは、独立したロール構成とワークフローを管理するための新機能です。従来の単一設定ファイルではなく、目的別に特化した組織設定を利用できます。

## 利用可能な組織

### nokuru（野外活動サークル）

**目的**: キャンプ・アウトドア活動の企画・意思決定

**専門ロール**:
- 🌸 **かえで** - サークル部長・進行役（fast model）
- 🌞 **ひなた** - 元気いっぱいのアイデアマン
- 🍀 **さつき** - のんびり関西弁のムードメーカー
- ❄️ **ゆき（ゲスト）** - ソロキャンプ達人・実用重視

**利用可能ワークフロー**:

1. **camp_planning** - キャンプ企画（直列）
   - 全員が順番に意見を出して部長が取りまとめる

2. **camp_idea_parallel** - キャンプアイデア出し（並列）
   - 3人が同時にアイデアを出し、部長がまとめる

3. **camp_planning_vote** - キャンプ企画＋投票（parallel→loop）
   - 並列アイデア出し後、投票ループで1つに絞り込む

4. **camp_with_vote** - キャンプ議題→投票（`call` デモ）
   - 並列議論の後、汎用投票サブルーチン `vote_base` を `call` で呼び出す
   - `type: "call"` の実装例として最もわかりやすい構成

5. **vote_base** - 投票（共通サブルーチン）
   - `camp_with_vote` など他のワークフローから `call` で呼ばれる
   - ループ MAX3回 / 終了条件「全員賛成」

```bash
# キャンプアイデアを並列で出して投票で決める
python MultiRoleChat.py --org nokuru --workflow camp_with_vote --topic "夏の締めくくりキャンプ"

# フロー図だけ確認（subgraph で vote_base の中身も展開）
python MultiRoleChat.py --org nokuru --workflow camp_with_vote --mermaid
```

---

### creative_org（創造性特化組織）

**目的**: 制約のない発想と革新的アイデアの生成

**専門ロール**:
- 🔥 **ワイルドアイデア・ジェネレーター** - 常識を破る革新的発想
- 🔮 **ビジョナリー** - 未来志向の戦略的視点
- 😈 **悪魔の代弁者** - 批判的思考と問題点の指摘
- 🎨 **創造性重視** - 実現可能な創造的解決策
- 🎯 **モデレーター** - 議論の整理と方向性の管理

**利用可能ワークフロー**:

1. **creative_brainstorm** - 創造的ブレインストーミング
   - 制約のない自由な発想から革新的なアイデアを生み出す
   - 6段階のプロセスでアイデアを洗練

2. **idea_refinement** - アイデアの詳細化
   - 生成されたアイデアの実現可能性を検討
   - 具体的な実装計画の策定

3. **innovation_session** - 革新セッション
   - 新技術や新市場への挑戦的なアプローチ
   - 破壊的イノベーションの探求

4. **vision_planning** - ビジョン策定
   - 長期的ビジョンと戦略的方向性の策定
   - 組織の未来像の描画

## 使用方法

### 1. 組織情報の確認

```bash
# 利用可能な組織とワークフローを確認
python MultiRoleChat.py --org creative_org
```

出力例:
```
✨ 組織: creative_org (創造性特化組織)
📝 説明: 制約のない発想と革新的思考に特化した創造的組織

🎭 利用可能なロール (5個):
  ✅ ワイルドアイデア: 常識を破る革新的発想を生み出す
  ✅ ビジョナリー: 未来志向の戦略的視点を提供
  ✅ 悪魔の代弁者: 批判的思考で問題点を指摘
  ✅ 創造性重視: 実現可能な創造的解決策を提案
  ✅ モデレーター: 議論を整理し方向性を管理

🔄 利用可能なワークフロー (4個):
  ✅ creative_brainstorm: 制約のない自由な発想から革新的なアイデアを生み出す
  ✅ idea_refinement: アイデアの詳細化と実現可能性の検討
  ✅ innovation_session: 新技術や新市場への挑戦的なアプローチ
  ✅ vision_planning: 長期的ビジョンと戦略的方向性の策定
```

### 2. ワークフローの直接実行

```bash
# 創造的ブレインストーミングの実行
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIペットサービス"
```

### 3. 組織モードでの対話実行

```bash
# 組織を指定して対話モードで起動
python MultiRoleChat.py --org creative_org

# ワークフロー実行
🎭 creative_org> workflow creative_brainstorm "次世代教育プラットフォーム"

# 個別ロールとの対話
🎭 creative_org> chat ワイルドアイデア "宇宙時代のビジネスモデルを考えて"
```

## 創造的ブレインストーミング ワークフロー例

### 実行コマンド
```bash
python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIペットサービス"
```

### プロセス詳細

**段階1: ワイルドアイデア** - 制約のない発想
```
テレポーテーションAIペット、変身可能AIペット、
心を読むAIペット、宇宙探検AIペット、
過去タイムトラベル機能など、10個の革新的アイデアを生成
```

**段階2: ビジョナリー** - 未来志向の拡張
```
2035年の世界を見据えた、生命と技術の調和による新しい共生関係、
バイオテクノロジーとの融合、社会インフラとの連携、
次世代インタラクションなどの視点でアイデアを発展
```

**段階3: 悪魔の代弁者** - 批判的検証
```
ペットオーナーは本当にAIを求めているか？
プライバシーの問題、技術的課題、実現可能性、
競争優位性などの課題を厳しく指摘
```

**段階4: 創造性重視** - 現実的解決策
```
批判を踏まえて、個性化、感情認識、社会的交流促進、
教育的コンテンツ、セキュリティ確保などの
実現可能な機能を体系的に提案
```

**段階5: ワイルドアイデア** - 改良版アイデア
```
批判を受けて、セキュリティ強化、環境適応、
感情学習、共同変身システムなど、
より洗練された革新的アイデアを再提案
```

**段階6: モデレーター** - 最終整理
```
AIペットヘルスケア、エモーションアナライザー、
エコシステムを最も有望なアイデアとして特定し、
次のステップを明確化
```

### 出力結果

実行結果は `multi_logs/creative_brainstorm_YYYYMMDD_HHMMSS.md` に保存され、各段階での詳細な議論と最終的な推奨案が含まれます。

## 組織設定ファイルの構造

```
organizations/creative_org/
├── config.json          # 組織設定とワークフロー定義
└── roles/               # 組織専用ロールプロンプト
    ├── wild_innovator.txt    # ワイルドアイデア・ジェネレーター
    ├── devil_advocate.txt    # 悪魔の代弁者
    ├── visionary.txt         # ビジョナリー
    ├── creative.txt          # 創造性重視
    └── moderator.txt         # モデレーター
```

### config.json 例

```json
{
  "name": "creative_org",
  "display_name": "創造性特化組織",
  "description": "制約のない発想と革新的思考に特化した創造的組織",
  "roles": {
    "ワイルドアイデア": {
      "file": "wild_innovator.txt",
      "description": "常識を破る革新的発想を生み出す",
      "provider": "gemini",
      "model": "gemini-2.5-flash"
    }
  },
  "workflows": {
    "creative_brainstorm": {
      "name": "創造的ブレインストーミング",
      "description": "制約のない自由な発想から革新的なアイデアを生み出す",
      "steps": [
        {
          "role": "ワイルドアイデア",
          "action": "制約のない自由な発想でアイデアを大量生成"
        }
      ]
    }
  }
}
```

## 利用可能な組織（一覧）

| 組織名 | 用途 | ワークフロー数 |
|---|---|---|
| `creative_org` | 創造的ブレインストーミング | 4 |
| `quiz_evaluation` | AIモデルのクイズ性能比較 | 3 |
| `tech_startup` | スタートアップ開発・議論 | 複数 |
| `consulting_firm` | コンサルティング・分析 | 複数 |
| `default_company` | 汎用企業シミュレーション | 複数 |
| `groq_fast_discussion` | Groq 高速討論 | 複数 |
| `codecraft_collective` | コード生成・レビュー | 複数 |
| `nokuru` | キャラクター会話 | 複数 |

---

### quiz_evaluation（AIクイズ比較組織）

**目的**: 複数 AI プロバイダーにクイズを投げてモデル性能を比較評価

**参加ロール** (8ロール):
| ロール名 | プロバイダー | モデル |
|---|---|---|
| OpenAI自称クイズ王 | ChatGPT | gpt-5.4 |
| Google自称クイズ王 | Gemini | gemini-3.1-pro-preview |
| Anthropic自称クイズ王 | Anthropic | claude-opus-4-6 |
| Groq自称クイズ王 | Groq | openai/gpt-oss-120b |
| Groq軽量自称クイズ王 | Groq | openai/gpt-oss-20b |
| Mistral自称クイズ王 | Mistral | mistral-large-2512 |
| Together自称クイズ王 | Together | Llama-3.3-70B-Instruct-Turbo |
| Grok自称クイズ王 | Grok | grok-4-1-fast |

**利用可能なワークフロー**:

| ワークフロー名 | 実行方式 | 説明 |
|---|---|---|
| `quiz_battle` | 逐次 (`steps`) | 前の回答を見てマウント合戦しながら回答 |
| `model_comparison` | 並列 (`parallel_steps`) | 各モデルが独立して同時に回答 |
| `quiz_battle_parallel` | 並列 (`parallel_steps`) | 全プロバイダー同時実行（最速） |

**実行例**:
```bash
# 並列クイズバトル（推奨）
python MultiRoleChat.py --org quiz_evaluation
workflow quiz_battle_parallel 日本の首都はどこですか

# 逐次バトル（他モデルの回答を見て反応し合う）
workflow quiz_battle 量子コンピュータの原理を説明してください
```

**パフォーマンス比較** (実測):
| モード | 実時間 | トークン | コスト |
|---|---|---|---|
| `quiz_battle`（逐次） | 約45秒 | 〜3,800 | $0.01 |
| `quiz_battle_parallel`（並列） | 約11秒 | 〜700 | $0.005 |

---

## 新しい組織の作成

1. `organizations/` ディレクトリに新しい組織フォルダを作成
2. `config.json` で組織情報、ロール、ワークフローを定義
3. `roles/` フォルダにロール別プロンプトファイルを配置
4. `--org` オプションで指定して使用

## トラブルシューティング

### 組織が見つからない場合
```bash
# 利用可能な組織を確認
ls organizations/

# 組織設定の検証
python MultiRoleChat.py --org your_org_name
```

### ワークフローが実行されない場合
- config.json の workflow 定義を確認
- ロールファイルの存在を確認
- プロバイダー設定を確認

## 今後の拡張予定

- **tech_startup_org**: 技術スタートアップ特化組織
- **consulting_org**: コンサルティング特化組織  
- **research_org**: 研究開発特化組織
- **marketing_org**: マーケティング特化組織

各組織は独自のロール構成とワークフローを持ち、特定の業界や用途に最適化されます。

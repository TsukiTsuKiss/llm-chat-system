# 総合企業（default_company）

一般的な企業の企画・分析・デザイン・実装・マーケティングを、役割分担して進める汎用の組織です。

**理念**: お客様第一主義で革新的なソリューションを提供し、持続可能な社会の実現に貢献する

**行動指針**: 誠実性 / 革新性 / 協働性 / 品質重視 / 継続学習

## メンバーと役割

| 人材 | 役割（スロット） |
|---|---|
| かずま（`kazuma`） | 企画（`planner`） |
| みずき（`mizuki`） | 分析官（`analyst`） |
| あおい（`aoi`） | デザイナー（`designer`） |
| しょう（`shou`） | マーケター（`marketer`） |
| りょうた（`ryota`） | プログラマー（`programmer`） |
| しゅん（`shun`） | 実行担当（`executor`） |
| かんな（`kanna`） | 秘書（`secretary`。会議の総括役） |

この組織では、発言を口頭で読める長さにするため、1 ターン 500 文字以内、秘書の要約は 800 文字以内にする指示を入れています（`common_directives` と `role_directives`）。

## ワークフロー

| ワークフロー | 内容 |
|---|---|
| `company_project_planning`（既定） | アイデア創出から、実現可能性・UX・市場性の評価、アクションプランまでをまとめる |
| `company_startup_launch` | 事業計画から市場分析、技術的実現性、資金計画、初期開発着手までを順に進める |
| `company_product_development` | コンセプトと要求仕様から、デザイン、実装、販売戦略、市場反応の分析までを順に進める |
| `company_market_research` | データ収集と競合分析から、事業機会の評価、調査結果の検証、報告書作成までを進める |
| `company_new_product_meeting` | 新商品のアイデアから、市場分析、デザイン、技術評価、価格・販売戦略までを検討し、開発計画にまとめる |
| `company_brainstorm_parallel` | 初手で複数の役割から同時にアイデアを出し、視点を広げる |

## 使い方

```bash
# 対話で使う
python MultiRoleStudio.py --org default_company

# 新商品開発会議
python MultiRoleStudio.py --org default_company --workflow company_new_product_meeting \
  --topic "スマートウォッチの新機能について検討したい。健康管理とフィットネス分野で差別化を図りたい。"

# プロジェクト企画
python MultiRoleStudio.py --org default_company --workflow company_project_planning \
  --topic "AIを活用したカスタマーサポートシステムを企画したい。既存システムとの統合も考慮したい。"

# 市場調査
python MultiRoleStudio.py --org default_company --workflow company_market_research \
  --topic "リモートワーク支援ツール市場の動向と競合分析を行いたい。"
```

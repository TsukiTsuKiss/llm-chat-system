# 戦略コンサルティング・ファーム（consulting_firm）

クライアントの課題解決と戦略策定を担う、コンサルティング業務向けの専門チームです。

**理念**: お客様第一主義で革新的なソリューションを提供し、持続可能な社会の実現に貢献する

**行動指針**: 誠実性 / 革新性 / 協働性 / 品質重視 / 継続学習

## メンバー

| 人材 | `consulting_client_analysis` | `consulting_strategy_development` |
|---|---|---|
| かずま（`kazuma`） | 戦略企画（`strategic_planner`） | 戦略企画（`strategic_planner`） |
| しょう（`shou`） | 業界専門家（`industry_expert`） | — |
| かんな（`kanna`） | プロジェクトマネージャー（`project_manager`） | プロジェクトマネージャー（`project_manager`） |
| たいが（`taiga`） | — | 戦略コンサルタント（`strategy_consultant`） |
| みずき（`mizuki`） | リサーチャー（`researcher`） | データアナリスト（`data_analyst`） |

同じ人でも、ワークフローによって役割が変わります。役割の指示は `config.json` の `role_directives` に、スロット名ごとに書かれています。

## ワークフロー

| ワークフロー | 内容 |
|---|---|
| `consulting_client_analysis`（既定） | 業界分析と競合調査から、課題特定、専門知識に基づく提案、提案書と次ステップの整理までをまとめる |
| `consulting_strategy_development` | フレームワーク構築、データ検証、実行可能な戦略の策定と、実行計画の作成 |

## 使い方

```bash
python MultiRoleStudio.py --org consulting_firm --workflow consulting_client_analysis --topic "製造業DX戦略"
python MultiRoleStudio.py --org consulting_firm --workflow consulting_strategy_development --topic "新規事業参入計画"
```

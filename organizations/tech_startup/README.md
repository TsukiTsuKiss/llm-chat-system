# テックスタートアップ（tech_startup）

スピード重視で MVP を作り、技術的な判断を素早く下す、スタートアップ向けの組織です。

**理念**: 技術革新で世界を変え、ユーザーの生活をより豊かで便利にする

**行動指針**: スピード重視 / 技術革新 / ユーザー中心 / データドリブン / グローバル思考

## ワークフローと担当

| ワークフロー | 担当（スロット） | 内容 |
|---|---|---|
| `tech_mvp_development`（既定） | かずま（`product_owner`）、あおい（`designer`）、りょうた（`fullstack`）、たくみ（`cto`） | 最小機能要件の定義から、プロトタイプ、実装、技術判断までを順に進める |
| `tech_rapid_iteration` | りょうた（`fullstack`）、かずま（`product_owner`）、あおい（`designer`）、しゅん（`lead_engineer`） | 実装、優先度決定、デザイン調整、品質チェックを短いサイクルで回す |
| `tech_sprint` | たくみ（`cto`）、しゅん（`lead_engineer`）、りょうた（`fullstack`）、かんな（`product_manager`） | 技術課題の特定から、実装計画、集中実装、進捗管理とリリース計画までを順に進める |
| `tech_ai_auto_programming` | なおき（`ai_architect`）、すばる（`ai_implementer`） | アーキテクトの設計と、AI 実装エンジニアの実装を交互に進める |
| `tech_simple_coding` | ちひろ（`planner`）、すばる（`implementer`）、みさき（`reviewer`） | 軽量で単純なプログラムを、計画・実装・レビューの 3 ステップで作る |
| `tech_code_and_run` | すばる（`implementer`）、検証 確（`tester`） | 実装とテスターの検証を、合格が出るまで繰り返す（最大 5 回） |

## 選び方

| やりたいこと | ワークフロー |
|---|---|
| コードを作ってすぐ検証する（最短） | `tech_code_and_run` |
| Hello World など単純なプログラム | `tech_simple_coding` |
| 製品の最小構成を作る | `tech_mvp_development` |
| 短いサイクルで改善を回す | `tech_rapid_iteration` |
| 技術課題を解決する | `tech_sprint` |
| 複雑な AI システムを設計・実装する | `tech_ai_auto_programming` |

## 使い方

```bash
python MultiRoleStudio.py --org tech_startup --workflow tech_code_and_run --topic "フィボナッチ関数"
python MultiRoleStudio.py --org tech_startup --workflow tech_simple_coding --topic "Hello Worldプログラム"
python MultiRoleStudio.py --org tech_startup --workflow tech_mvp_development --topic "新しいSNSアプリ"
python MultiRoleStudio.py --org tech_startup --workflow tech_rapid_iteration --topic "機能改善"
python MultiRoleStudio.py --org tech_startup --workflow tech_sprint --topic "パフォーマンス改善"
```

コードを生成するワークフローは、終了時に `sandbox/session_<session_id>/` へ保存します（[sandbox 保存](../../docs/sandbox-saving.md)）。

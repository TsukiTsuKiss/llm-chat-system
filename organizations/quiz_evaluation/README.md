# AI性能評価センター（quiz_evaluation）

複数の AI プロバイダーのモデルを、同じ問題・同じ条件で比べるための組織です。各モデルが「自称クイズ王」として自信満々に答えますが、回答は選択肢の記号と簡潔な理由にそろえます。

## メンバー

| 人材 | 人材 | 人材 | 人材 |
|---|---|---|---|
| はじめ（`hajime`） | げん（`gen`） | いつき（`itsuki`） | じん（`jin`） |
| りつ（`ritsu`） | まい（`mai`） | とら（`tora`） | かい（`kai`） |

8 人は、それぞれ別のプロバイダー（またはモデル）を割り当てて比べる前提の、個性の異なる回答者です。割り当ては `model_mapping.json` で決めます。共通のスロットは `answerer` です。

## ワークフロー

| ワークフロー | 内容 |
|---|---|
| `quiz_battle` | 出された技術クイズに、8 人が順番に回答する |
| `quiz_battle_parallel`（既定） | 全員に同時に質問を投げて、回答と応答時間を比べる |

## 使い方

```bash
# 1 問ずつ試す（出題は入力欄・--topic で渡す）
python MultiRoleStudio.py --org quiz_evaluation --workflow quiz_battle_parallel --topic "日本で2番目に面積の大きい都道府県は？"

# 問題セットを全員に流して、自動採点・集計する
python MultiRoleStudio.py --org quiz_evaluation --benchmark samples/benchmark/questions.example.json
```

ベンチマークの詳細（問題セットの形式、採点、結果の出力先 `benchmark_results/`）は、[README のクイズ・ベンチマーク](../../README.md) の節を参照してください。

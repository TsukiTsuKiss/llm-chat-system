# 組織（organizations）

組織は、**人材（`talents/`）をどう編成し、どのワークフローで動かすか**を決める座組です。人材とワークフローは共有のため、同じ人材・同じワークフローを、組織を変えて使い回せます（例: 同じ「会議」の型でも、組織が違えば営業会議にも企画会議にもなります）。

仕様の正本は [設計書](../docs/MultiRoleStudio/design.md)（§3.3 組織）と [schemas/organization.schema.json](../schemas/organization.schema.json) です。

## 組織フォルダの構成

```text
organizations/<org_id>/
├── config.json                  # 組織の定義（Git 管理）
├── model_mapping.example.json   # 人材ごとの assistant + model の雛形（mock）
├── model_mapping.json           # 実行時に読む正本（.gitignore）
├── voice_mapping.example.json   # 読み上げの声の雛形（任意）
├── voice_mapping.json           # 読み上げの声（任意、.gitignore）
└── README.md                    # 組織の説明（任意）
```

`model_mapping.json` は、初回に `.example` をコピーして編集します。

### config.json の主な項目

| キー | 内容 |
|---|---|
| `name` / `mission` / `culture` | 組織名・目的・社風。人材のプロンプトに組織の文脈として加わる |
| `talent_ids` | この組織に所属する人材の ID（`talents/<id>.json`） |
| `default_workflow` | 起動時に使うワークフロー |
| `workflow_bindings` | ワークフローごとに、スロット（役割枠）へ人材を割り当てる |
| `common_directives` | 全員に共通の指示 |
| `role_directives` | スロット名ごとの役割の指示 |

人材 ID は人物名で、役割名・組織名を含めません。役割は `workflow_bindings` と `role_directives` で与えます。

## 組織一覧

| 組織 ID | 名前 | メンバー | 既定のワークフロー |
|---|---|---|---|
| `broadcast_studio` | 放送・配信スタジオ | みどり、あかり、そうた、ごう、はるか、けんと、ゆうま | `broadcast_news_show` |
| `codecraft_collective` | コードクラフト・コレクティブ | 全能 統、検証 確 | `rapid_mvp` |
| `consulting_firm` | 戦略コンサルティング・ファーム | かずま、しょう、かんな、たいが、みずき | `consulting_client_analysis` |
| `creative_org` | クリエイティブ・イノベーション・ラボ | るい、そら、くろ、ななみ、みお | `creative_brainstorm` |
| `decision_balance_org` | 意思決定バランス | ひかり、しずく、ともえ | `balanced_decision_support` |
| `default_company` | 総合企業 | かずま、みずき、あおい、しょう、りょうた、しゅん、かんな | `company_project_planning` |
| `groq_fast_discussion` | Groq高速意思決定チーム | ともえ、みずき、しずく、だいち | `groq_quick_discussion` |
| `nokuru` | のくる | ひなた、さつき、かえで、ゆき | `meeting` |
| `quiz_evaluation` | AI性能評価センター | はじめ、げん、いつき、じん、りつ、まい、とら、かい | `quiz_battle_parallel` |
| `solo` | ソロ | ソロBot | （直接送信） |
| `studio_dev` | Studio 開発チーム | アーキテクト、インプリメンター、レビュアー | `dev` |
| `tech_editorial` | Tech編集部 | ふみ、しおり、ことは、くろ、そうた、みさき、だいち | `tech_article_edit` |
| `tech_startup` | テックスタートアップ | かずま、あおい、りょうた、しゅん、たくみ、かんな、なおき、すばる、みさき、ちひろ、検証 確 | `tech_mvp_development` |
| `trio` | トリオ | Alpha、Beta、Gamma | `discussion` |

各組織で使えるワークフローは、`config.json` の `workflow_bindings` のキーです。

組織ごとの説明は、README のある組織（`codecraft_collective` / `consulting_firm` / `creative_org` / `default_company` / `quiz_evaluation` / `tech_startup`）のフォルダを参照してください。

## 使い方

```bash
# 組織を指定して、対話で使う
python MultiRoleStudio.py --org creative_org

# ワークフローとお題を指定して、1 回で完走する
python MultiRoleStudio.py --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"
python MultiRoleStudio.py --org consulting_firm --workflow consulting_client_analysis --topic "製造業DX戦略"
python MultiRoleStudio.py --org tech_startup --workflow tech_simple_coding --topic "フィボナッチ関数"

# Web UI
python MultiRoleStudioWeb.py --org tech_startup
```

オプションの一覧は [README](../README.md) の MultiRoleStudio の節を参照してください。クイズ・ベンチマークは `--benchmark` で、`quiz_evaluation` の人材全員に同じ問題を流します。

## 組織を追加する

1. `organizations/<org_id>/config.json` を作り、`talent_ids` に既存の人材 ID を入れる。
2. `workflow_bindings` で、使うワークフローのスロットに人材を割り当てる。
3. `role_directives` に、スロット名ごとの役割の指示を書く。
4. `model_mapping.example.json` を作り、`model_mapping.json` にコピーして assistant と model を指定する。

**新しい人材は、既存の人材で役割を賄えないときだけ追加します。** 組織側の `role_directives` で役割を切り替えれば、同じ人材を別の組織・別の役割で使い回せます。

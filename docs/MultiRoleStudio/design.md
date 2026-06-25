# MultiRoleStudio 設計メモ

作成日: 2026-06-25

---

## 開発の発端

### MultiRoleChat / MultiRoleChatWeb の課題

`MultiRoleChat.py` と `MultiRoleChatWeb.py` は「複数AIが会話する」ことを起点に作られており、
設定（組織・ロール・ワークフロー）はすべて `organizations/<名前>/config.json` に直書きする構造になっている。

使い込むにつれて以下の問題が見えてきた：

- **編集がファイル直接操作**：config.json や roles/*.txt をエディタで開いて手書きする必要がある
- **再利用性がない**：同じキャラクター（人材）を別の組織に使い回すとき、定義をコピペする
- **「Chat」という名前が狭い**：クイズ、会議、ブレインストーミング、投票など、会話以外の用途にも使われている

### 汎用化のアイデア

「会話する」ではなく「役割を持つエージェントを編成して何かをやらせる」という視点で再設計する。

演劇のアナロジーが構造にそのまま対応する：

| 演劇 | システム |
|---|---|
| 配役（キャスト） | 人材（AI エージェントの定義） |
| 舞台・座組（カンパニー） | 組織（人材の選択とモデルのマッピング） |
| ストーリー・演出 | ワークフロー（会話・進行のやり方） |
| 脚本（シナリオ） | シナリオ（全要素を即値で直書きした使い捨て定義） |

このアナロジーに合わせてファイル名を `MultiRoleStudio` とした。

---

## 現在のデータ構造（MultiRoleChat 時点）

```
organizations/
  <org_name>/
    config.json        ← 人材定義 + モデル割り当て + ワークフロー が混在
    roles/
      hinata.txt       ← システムプロンプト本文
      satsuki.txt
      ...
```

`config.json` の構造：

```json
{
  "organization": "nokuru",
  "demo_roles": [         ← ロールセット（メンバ選択 + モデル割り当て）
    {
      "name": "ひなた",
      "assistant": "Groq",
      "model": "openai/gpt-oss-120b",
      "system_prompt_file": "roles/hinata.txt"
    }
  ],
  "organization_roles": [ ← 別のロールセット（同上）
    ...
  ],
  "workflows": {          ← ワークフロー（role 名を参照するだけ。定義は含まない）
    "vote_base": {
      "phases": [...]
    }
  }
}
```

**ポイント**：ワークフローの `steps` はロール名の参照のみで、モデルやプロンプトを持たない。
人材定義とワークフローはすでに論理的に分離されている。

---

## 将来のデータ構造（MultiRoleStudio 目標）

```
talents/                ← 人材プール（組織横断で再利用）
  hinata.json           ← name, personality, system_prompt_file
  satsuki.json

workflows/              ← ワークフローテンプレート（組織横断で再利用）
  discussion.json       ← 自由討議
  quiz.json             ← クイズ大会
  brainstorm.json       ← ブレインストーミング
  meeting.json          ← 会議（モデレーター付き）

organizations/
  nokuru/
    config.json         ← 人材選択 + モデルマッピング + 使うワークフローの指定
    roles/              ← システムプロンプト本文（組織ごとにオーバーライド可）

scenarios/              ← 使い捨て全部入り定義（人材・モデル・ワークフローを直書き）
  camp_planning.json
```

### シナリオの位置づけ

| | 人材 | モデル | ワークフロー |
|---|---|---|---|
| 組織 | 参照（talents/ から） | マッピング定義 | 参照（workflows/ から） |
| シナリオ | 直書き（即値） | 直書き（即値） | 直書き（即値） |

シナリオは「永続管理が不要な使い捨て」。組織は「継続的に育てる資産」。

---

## MultiRoleStudio の追加機能（UI）

### 現在の MultiRoleChatWeb

- タブ：💬 チャット / 📄 ログ
- 設定変更はファイル直接編集

### MultiRoleStudio の UI 設計（案 B）

```
[💬 チャット] [⚙️ 設定編集] [📄 ログ]
```

設定編集タブの構造：

```
左ペイン: 組織一覧 + 新規作成/削除
右ペイン:
  [👤 ロール編集]         ← demo_roles / organization_roles の行 + roles/*.txt 本文
  [🔄 ワークフロー編集]   ← workflows の JSON（テキストエリア）
```

ロール編集画面：

```
ロール一覧（追加/削除ボタン付き）
└── 選択中ロールの詳細
     ├── name / assistant / model / role_type（フォーム）
     └── システムプロンプト本文（テキストエリア）
```

保存関数は `save_config(org, key, data)` の形に抽象化しておき、
将来の分離構造変更時に UI を触らずに済むようにする。

---

## 移行方針

- `MultiRoleChat.py` / `MultiRoleChatWeb.py` は **現行維持**（破壊しない）
- `MultiRoleStudio.py` は新ファイルとして作成（ロジックは MultiRoleChat を流用）
- データ構造は現在の `organizations/` をそのまま使い、将来分離に備えて保存層だけ抽象化

---

## 未決事項

- シナリオを `workflows/` に `scenario` タイプとして内包するか、`scenarios/` として独立させるか
- `talents/` の人材と `organizations/` のロール定義の重複をどう管理するか
- Web UI のワークフロー編集はテキストエリア（JSON直書き）で十分か、フォーム化するか

### モデルマッピングの分離（Git との相性問題）

現在の `config.json` にはキャラクター定義（name / system_prompt_file）と
インフラ設定（assistant / model）が混在しており、
ユーザーごとに契約プロバイダーが異なる場合に diff が汚れる。

`.env` / `.env.example` パターンと同じ構造の問題：

| ファイル | 性質 | Git 管理 |
|---|---|---|
| `roles/hinata.txt` | キャラクター定義（共有可） | ✅ commit |
| `config.json` の name / prompt_file | 構造定義（共有可） | ✅ commit |
| `config.json` の assistant / model | 環境依存（個人差あり） | ⚠️ .gitignore 候補 |

**分離案**：

```
organizations/nokuru/
  config.json                   ← キャラ構造のみ（Git 管理）
  model_mapping.json            ← assistant/model のみ（.gitignore）
  model_mapping.example.json    ← テンプレ（Git 管理）
```

`model_mapping.example.json` の例：

```json
{
  "ひなた": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "さつき": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "かえで": { "assistant": "Groq", "model": "openai/gpt-oss-20b" }
}
```

ユーザーは `.example` をコピーして自分の環境に合わせて書き換える。

**保留理由**：個人利用・クローズド運用では分離のコストが見合わない場合もある。
将来 talents/ への人材プール分離を進めるタイミングで合わせて判断する。

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

### 初期（制約強め・実装最小）
```
talents/                ← 人材プール（組織横断で再利用）
  hinata.json           ← name, personality, system_prompt
  satsuki.json

workflows/              ← ワークフローテンプレート（組織横断で再利用）
  discussion.json       ← 自由討議
  quiz.json             ← クイズ大会
  brainstorm.json       ← ブレインストーミング
  meeting.json          ← 会議（モデレーター付き）

organizations/
  nokuru/
    config.json         ← 人材選択 + モデルマッピング + 組織内役割指示 + ワークフロー指定

scenarios/              ← 使い捨て全部入り定義（人材・モデル・ワークフローを直書き）
  camp_planning.json
```

### 拡張（互換対応・任意機能を追加）
```
talents/                ← 人材プール（組織横断で再利用）
  hinata.json           ← name, personality, system_prompt or system_prompt_file
  satsuki.json

roles/                  ← 共通システムプロンプト（互換モード・任意）
  hinata.txt
  satsuki.txt

workflows/              ← ワークフローテンプレート（組織横断で再利用）
  discussion.json       ← 自由討議
  quiz.json             ← クイズ大会
  brainstorm.json       ← ブレインストーミング
  meeting.json          ← 会議（モデレーター付き）

organizations/
  nokuru/
    config.json         ← 人材選択 + モデルマッピング + 組織内役割指示 + ワークフロー指定
    roles/              ← 旧互換/拡張用（通常は不要）

scenarios/              ← 使い捨て全部入り定義（人材・モデル・ワークフローを直書き）
  camp_planning.json
```

`talents/hinata.json` のサンプル（推奨: 直書き方式）：

```json
{
  "id": "hinata",
  "name": "ひなた",
  "personality": "明るく前向き。対立をやわらげ、会話の流れを整える。",
  "system_prompt": "あなたは『ひなた』。議論を前に進め、発言者ごとの主張を取りこぼさない。回答は『要点』『未確定事項』『次アクション』の3見出しで出し、根拠が弱い点は仮説と明記し、1ターン300文字以内で簡潔にまとめる。",
  "tags": ["facilitator", "warm", "summary"]
}
```

`talents/hinata.json` のサンプル（互換: ファイル参照方式）：

```json
{
  "id": "hinata",
  "name": "ひなた",
  "personality": "明るく前向き。対立をやわらげ、会話の流れを整える。",
  "system_prompt_file": "roles/hinata.txt",
  "tags": ["facilitator", "warm", "summary"]
}
```

注: ファイル参照は既存資産との互換用。新規設計では `system_prompt` 直書きを第一選択とする。

`roles/hinata.txt` のサンプル（共通ベース）：

```txt
あなたは「ひなた」。

目的:
- 議論を前に進めること
- 発言者ごとの主張を取りこぼさないこと

出力ルール:
- 回答は「要点」「未確定事項」「次アクション」の3見出しで出す
- 断定しすぎず、根拠が弱い点は「仮説」と明記する
- 1ターンあたり最大300文字を目安に簡潔にまとめる
```

`organizations/nokuru/roles/hinata.txt` のサンプル（組織差分）：

```txt
【nokuru 追加指示】
- あなたは司会進行を優先する
- 毎ターンの冒頭で「今回のゴール」を1文で確認する
- 発言が偏ったら、未発言メンバーに1つ質問を振る
```

`personality` と `system_prompt` の役割分担：

1. `personality`: キャラクターの性格・口調・対人スタンス（短く安定）
2. `system_prompt`: タスク手順・出力形式・禁止事項（実行ルール）
3. 同じ内容になるなら片方でよい。最小構成は `system_prompt` のみでも運用可能
4. 運用で分けたい場合は「人格は personality、挙動仕様は system_prompt」に固定する

運用ルール案：

1. 標準は `system_prompt`（直書き）
2. `system_prompt_file` は互換目的でのみ使用（既存 `roles/*.txt` を流用したい場合）
3. `system_prompt_file` と `system_prompt` は同時指定不可（正本は常に1つ）

プロンプト解決ルール案（組織ごとの差分運用・拡張機能）：

1. 既定は `inherit`（共通 `roles/*.txt` をそのまま使う）
2. `append` を指定すると共通プロンプト末尾に組織差分を追記する
3. `override` を指定すると `organizations/<org>/roles/*.txt` に完全差し替えする

`append` の用途例：

- ベース人格は共通のまま、`nokuru` だけ「司会進行を優先する」指示を1〜2段落追加する

実装簡略化のための推奨段階導入：

1. Phase 1 (MVP): `system_prompt` のみサポート（`roles/` 解決ロジックなし）
2. Phase 2 (互換): `system_prompt_file` 読み込みを追加
3. Phase 3 (拡張): `organizations/<org>/roles` の `append/override` を追加

機能追加予定（業務適用拡張フェーズ）：

1. Phase 4 (生成連携): 会話出力から TTS / ナレーション原稿 / ショット指示を生成
2. Phase 5 (考査支援): 映像・音声・字幕の自動コンプラチェック用ルール評価を追加
3. Phase 6 (運用基盤): 評価指標（品質・遅延・コスト）と MLOps 向け監視を追加
4. Phase 7 (連携拡張): 外部ベンダー連携を前提に API 契約と入出力スキーマを固定

補足：

- Phase 4 までは内製プロトタイプ中心
- Phase 5 以降は法務/考査フローとの接続を前提に段階導入

組織内の司会/リーダー指定を `config.json` に持たせる案（推奨）：

```json
{
  "organization": "nokuru",
  "talent_ids": ["hinata", "satsuki", "kaede"],
  "role_directives": {
    "hinata": [
      "この会議では司会進行を最優先する",
      "各ターン冒頭でゴールを1文で確認する"
    ],
    "kaede": [
      "技術リーダーとして実装リスクと代替案を必ず提示する"
    ]
  },
  "workflow": "meeting"
}
```

この方式なら、通常運用では `organizations/<org>/roles/` は不要。
実行時は `talents/*.json` の `system_prompt` に `role_directives` を追記して最終プロンプトを組み立てる。

シナリオ生成パラメータ案（同一シナリオのバリエーション生成向け）：

```json
{
  "scenario_id": "camp_planning",
  "organization": "nokuru",
  "workflow": "meeting",
  "generation": {
    "temperature": 0.65,
    "top_p": 0.9,
    "seed": 42,
    "variation_profile": "balanced"
  }
}
```

パラメータ運用の目安：

1. `temperature`: 低いほど安定、高いほど展開が多様
2. `seed`: 同じ出力を再現したいときに固定
3. `variation_profile`: `stable` / `balanced` / `creative` のプリセット名で運用

ゲーム応用を見据えた拡張案（任意）：

```json
{
  "state": {
    "chapter": 2,
    "turn": 5,
    "flags": ["met_mayor", "found_map"],
    "affinity": { "hinata": 62, "satsuki": 45 },
    "inventory": ["old_key", "camp_guide"]
  },
  "constraints": {
    "must_include": ["次の目的地の提示"],
    "must_avoid": ["未確定情報の断定"]
  }
}
```

この構造を追加すると、同じシナリオ定義から「会議運用」と「分岐型ストーリー（ゲーム）」の両方へ展開しやすくなる。

ゲーム用テンプレ（終了条件あり・戦略シム向け）：

```json
{
  "scenario_id": "warring_states_sandbox",
  "mode": "game",
  "game_type": "strategy",
  "state": {
    "turn": 1,
    "max_turn": 24,
    "territories": { "player": 1, "rivals": 5 },
    "resources": { "gold": 300, "food": 500, "troops": 200 }
  },
  "ending_policy": {
    "type": "finite",
    "win_conditions": [
      "territories.player >= 6",
      "rivals == 0"
    ],
    "lose_conditions": [
      "territories.player == 0",
      "resources.food <= 0"
    ],
    "draw_condition": "turn > max_turn"
  }
}
```

ゲーム用テンプレ（終了条件なし・仮想恋愛向け）：

```json
{
  "scenario_id": "virtual_romance_daily",
  "mode": "game",
  "game_type": "romance",
  "state": {
    "day": 1,
    "affinity": { "hinata": 40, "satsuki": 20 },
    "memory_log_limit": 200
  },
  "ending_policy": {
    "type": "endless",
    "session_break_conditions": [
      "user_requested_end",
      "max_turn_per_session_reached"
    ],
    "continuation": "next_session_resume"
  },
  "milestones": {
    "relationship_rank": ["acquaintance", "friend", "close", "partner"]
  }
}
```

運用メモ：

1. `finite` は勝敗条件を満たした時点でシナリオを終了する
2. `endless` はシナリオ自体は終了せず、セッション区切りだけ設ける
3. 仮想恋愛では `endless` + `milestones` の組み合わせが扱いやすい

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

### ログ再読み込み機能（会議運用・ゲーム運用共通）

MultiRoleChat / MultiRoleChatWeb には薄かった「途中再開」を、MultiRoleStudio では正式機能として持つ。

要件案：

1. セッション一覧から過去ログを選択して再開できる
2. 再開時に会話履歴だけでなく `state`（turn, flags, affinity, inventory など）も復元する
3. 再開後は「続きで上書き」ではなく「分岐保存（branch）」を標準にする
4. 参照専用モード（読み取り専用リプレイ）と編集モード（再開して続行）を分ける

最小実装（MVP）案：

1. ログ保存時に `session_id` と `state_snapshot` を同時保存
2. UI に「再開」ボタンを追加し、選択ログから `state_snapshot` を復元
3. 復元後は新しい `session_id` を発行して分岐セッションとして保存

期待効果：

- 会議: 前回議論の文脈を維持したまま継続できる
- ゲーム: セーブ/ロードに相当する体験が作れる
- 恋愛系の endless モード: 日次セッションを自然に積み上げられる

### 会議サマリの議事録化（推奨）

生ログは証跡として保持しつつ、別途「構造化サマリ」を作って議事録として使う。

議事録の最小項目：

1. `decisions`（決定事項）
2. `open_issues`（未決事項）
3. `actions`（担当・期限つきアクション）
4. `evidence_turns`（根拠となる発話ターン）
5. `next_agenda`（次回アジェンダ）

保存フォーマット案：

```json
{
  "session_id": "20260707_nokuru_meeting_01",
  "summary_version": 1,
  "generated_at": "2026-07-07T21:00:00+09:00",
  "minutes": {
    "decisions": [
      "次回までにプロトタイプAを実装する"
    ],
    "open_issues": [
      "データ保存形式をJSONLとSQLiteのどちらにするか"
    ],
    "actions": [
      {
        "owner": "kaede",
        "task": "保存層の比較メモ作成",
        "due": "2026-07-14"
      }
    ],
    "evidence_turns": [12, 18, 24],
    "next_agenda": [
      "保存形式の最終決定",
      "再開UIの仕様確定"
    ]
  }
}
```

運用ルール案：

1. 5〜10ターンごとに「まとめ役ロール」がサマリ更新
2. 会議終了時に最終サマリを確定し、議事録としてエクスポート
3. 再開時は「最新サマリ + 直近生ログ」を入力文脈として利用

### 会議運用とエンタメ運用の抽象化

本設計では、会議とエンタメを別システムとして分けず、同じ実行基盤のモード差分として扱う。

共通抽象（同一基盤）：

1. `talents`: 発話主体の定義
2. `workflows`: 進行ルールの定義
3. `state`: 継続時に復元する実行状態
4. `summary`: 長期文脈を保つ圧縮記録

モードごとの差分（設定で切替）：

1. 会議モード: 決定事項・未決事項・担当期限を重視
2. エンタメモード: 関係変化・転機・次回フックを重視
3. ゲームモード: `ending_policy` と `state` 更新規則を重視

設計上の利点：

1. ログ再開・要約・分岐保存の仕組みを共通化できる
2. 会議議事録と物語ダイジェストを同じパイプラインで生成できる
3. 将来の用途追加（教育、訓練、シミュレーション）に拡張しやすい

### ニュース記事からのシナリオ自動生成メモ

同一基盤を使って、ニュース記事を「事実層」と「演出層」に分離し、再現シナリオへ変換できる。

最小パイプライン案：

1. 記事取り込み（見出し、本文、日付、出典URL）
2. 事実抽出（登場主体、出来事、時系列、数値、未確定情報）
3. シナリオ化（配役、シーン分割、転換点、結末候補）
4. ドラマ化（会話脚本、ナレーション、ショット指示）
5. 監査（出典トレース、推定表現ラベル、脚色箇所の明示）

品質・安全運用ルール案：

1. 事実層は固定し、`temperature` は演出層にのみ適用する
2. 未確認情報は「未確認/推定」と明示し、断定しない
3. 各台詞・要約に出典参照を保持して後追い検証可能にする

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

`model_mapping.example.json` の例（キーは `talents/*.json` のファイル名ベースID）：

```json
{
  "hinata": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "satsuki": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "kaede": { "assistant": "Groq", "model": "openai/gpt-oss-20b" }
}
```

例：`talents/hinata.json` があれば、マッピングキーは `hinata` を使う。
表示名（`ひなた` など）は talent 定義ファイル内の `name` を表示に使う。

読み込み時の想定フロー：

1. 起動時（または組織切替時）に `talents/*.json` を1回スキャンして `id -> talent定義` の索引を作る
2. `organizations/<org>/config.json` は `talent_id` を参照するだけにする
3. `model_mapping.json` は同じ `talent_id` キーで assistant/model を上書きする
4. 索引にない ID が来たらエラー表示し、保存時にもバリデーションする

ユーザーは `.example` をコピーして自分の環境に合わせて書き換える。

**保留理由**：個人利用・クローズド運用では分離のコストが見合わない場合もある。
将来 talents/ への人材プール分離を進めるタイミングで合わせて判断する。

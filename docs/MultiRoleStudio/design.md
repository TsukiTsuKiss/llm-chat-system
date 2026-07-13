# MultiRoleStudio 設計書

作成日: 2026-06-25 / 最終更新: 2026-07-08

本書は MultiRoleStudio の仕様と設計判断をまとめたもの。
確定した仕様（第2〜10章）と、構想段階のアイデア（付録）を明確に分けて記載する。

---

## 1. 背景と目的

### 設計思想の変遷

本システムの設計思想は、次の段階を経て現在の形にまとまった。

| 段階 | 気づき・動機 | 成果物 |
|---|---|---|
| 1 | AI とチャットする | `Chat.py` / `ChatWeb.py` |
| 2 | AI と会議ができれば、会社をシミュレーションできそう | （構想） |
| 3 | AI の組織化にトライする | `MultiRoleChat.py` / `MultiRoleChatWeb.py` |
| 4 | AI 組織は RPG などのゲームとみなせる、という気づき | （本書の設計思想。1.2 節） |
| 5 | ゲームエンジン化すれば応用範囲を拡張できる | `MultiRoleStudio`（本書） |

つまり「チャット → 会議 → 組織 → ゲーム」と抽象度を上げてきた到達点が
1.2 節の二層アナロジー（演劇×ゲーム）であり、MultiRoleStudio は
「会議シミュレータ」ではなく「役割を持つエージェントたちを動かすターン制ゲームエンジン」
として設計する。会議はその上で動くアプリケーションの1つになる。

### 1.1 MultiRoleChat / MultiRoleChatWeb の課題

`MultiRoleChat.py` と `MultiRoleChatWeb.py` は「複数AIが会話する」ことを起点に作られており、
設定（組織・ロール・ワークフロー）はすべて `organizations/<名前>/config.json` に直書きする構造になっている。

使い込むにつれて以下の問題が見えてきた：

- **編集がファイル直接操作**：config.json や roles/*.txt をエディタで開いて手書きする必要がある
- **再利用性が低い**：同じキャラクター（人材）を別の組織で使い回すたびに、定義をコピペする
- **「Chat」という名前が狭い**：クイズ、会議、ブレインストーミング、投票など、会話以外の用途にも使われている
- **実装の二重化**：MultiRoleChatWeb はエンジン（serial/parallel 実行・ストリーミング）を約200行再実装しており、
  ワークフロー機能を拡張するたびに CLI 版と Web 版の2箇所を修正する必要がある

### 1.2 設計思想：演劇×ゲームの二層アナロジー

「会話する」ではなく「役割を持つエージェントを編成して何かをやらせる」という視点で再設計する。
このシステムは2つのアナロジーの重ね合わせとして理解できる。

**静的構造は「演劇」**：何を編成するか。人材（配役）・組織（座組）・ワークフロー（演出）・
シナリオ（脚本）という構成要素の対応は 1.3 節の用語定義の通り。ファイル名 `MultiRoleStudio` もこれに由来する。

**動的実行は「ターン制ゲーム」**：どう動くか。実行系の各仕様は、ターン制ゲームエンジンの
基本構成とそのまま対応する。

| ゲームエンジンの概念 | 本システムでの対応 |
|---|---|
| エンティティ / NPC | 人材（AI モデルを割り当てたもの） |
| プレイヤーキャラクター | human ロール（6.6 節） |
| ゲームループ | ワークフローの loop フェーズ（4章） |
| ルール・勝敗判定 | `exit`（marker / judge）、`ending_policy`（付録A） |
| ゲームステート | `state`（7.2 節） |
| セーブ / ロード | セッション再開と分岐保存（7.2 節） |
| ゲームマスター | judge スロット（4.1 節） |
| エンジンとレンダラーの分離 | イベント駆動エンジンと表示層（CLI / Web）の分離（6章） |

このゲーム抽象がシステム全体の上位概念であり、**会議はその特殊ケース**である
（勝利条件＝「結論が出ること」、プレイログ＝議事録）。エンタメやゲーム運用は
別システムではなく、終了条件と記録の重み付けが異なる同一基盤のモード差分になる（7.4 節）。
MultiRoleChat でハードコードされていた会議モード・クイズモードは、
この抽象に基づきワークフローテンプレート（データ）に置き換える。

ワークフロー設計はゲームデザインの作業（ターン構造・情報の見せ方・終了条件の設計）
そのものである。例えば parallel フェーズの「互いの発言は見えない」（4.3 節）は、
見積もりの同調圧力を防ぐ同時公開メカニクスとして機能する。

### 1.3 用語定義

静的構造（演劇アナロジー）の用語対応：

| 用語 | 演劇での対応 | 定義 |
|---|---|---|
| 人材（talent） | 配役（キャスト） | エージェントの定義。性格・システムプロンプトを持ち、組織横断で再利用する。実体（どの AI モデルか、または人間か）は model_mapping で割り当てる |
| 組織（organization） | 舞台・座組（カンパニー） | 人材の選択・組織文化（ミッション・社風）・役割指示・モデルのマッピング。継続的に育てる資産 |
| ワークフロー（workflow） | ストーリー・演出 | 会話・進行のやり方のテンプレート。組織横断で再利用する |
| スロット（slot） | 役どころ（主役・脇役） | ワークフロー内の役割枠。組織側で人材を割り当てる（4.2 節） |
| シナリオ（scenario） | 脚本 | 全要素を直書きまたは参照で束ねた実行定義。永続管理が不要な使い捨て |

### 1.4 主要な設計判断（確定）

| 判断 | 内容 |
|---|---|
| 旧データ互換は捨てる | 旧 `config.json` / `roles/*.txt` の読み込み互換は実装しない。新形式のサンプルデータを新規作成する（10章）。互換レイヤ（`system_prompt_file`、`inherit/append/override`）は仕様から削除 |
| エンジンは MultiRoleChat から抽出移植 | ワークフロー実行ロジックを `studio/` パッケージへ**コピーして移植**する（旧ファイルへの import 依存は作らない）。Chat.py の強み（APIエラーリトライ・履歴縮約・要約生成・stream_render）も部品として移植する |
| イベント駆動エンジンで CLI / Web 両対応 | エンジンは実行イベントを yield する UI 非依存モジュールとし、CLI 版・Web 版は表示層のみ実装する（6章） |
| 完全移行を前提とする | MultiRoleStudio は MultiRoleChat の上位互換として作り、同等性確認後に旧版を廃止する（9.2 節） |
| 複数編成は組織に持たせない | 旧 `demo_roles` / `organization_roles` のような組織内複数ロールセットは廃止。1組織1編成とし、別編成が必要な場合はシナリオ（参照型）で表現する |
| `role_type` は廃止 | モデレーター等の役割指定はワークフローのスロットに吸収する |
| ID はファイル名 / フォルダ名から導出 | 定義ファイル内に `id` / `organization` / `scenario_id` フィールドを持たない（`talents/hinata.json` → id は `hinata`）。ID とファイル名の二重管理を排除する |
| UI・実行の既定値は組織 config に置かない | stream / temperature / 並列上限の既定値は `studio_config.json`（ユーザーローカル）に分離。組織 config は Git 共有可能な構造定義のみとする |
| アシスタント定義は JSON を正本とする | `ai_assistants_config.json` のみを読む（`models` 一覧を持ちモデル選択 UI に必要）。旧 CSV へのフォールバックは実装しない（現状 Chat.py と MultiRoleChat.py で読み込みが二重実装になっている問題を解消） |
| 検証系を実装前に固定する | 全定義ファイルの JSON Schema（3.7 節）、バリデーションのエラーコード表（5.3 節）、パリティ試験の先行作成（9.3 節）を実装開始前に確定し、機械検証・自動判定できる状態で Phase 1 に入る |

---

## 2. 現状分析（MultiRoleChat 時点のデータ構造・参考）

※ 旧形式との互換は保たない。本章は移植元の理解のための参考情報。

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
人材定義とワークフローはすでに論理的に分離されており、ファイル分離の下地はある。

移植元コードの資産マップ：

| 移植元 | 資産 | 移植先 |
|---|---|---|
| MultiRoleChat.py | `_run_phases` / `_run_engine`（serial/parallel）、`execute_iterative_workflow`（ループ） | `studio/engine.py` |
| MultiRoleChat.py | `TokenUsageTracker` + `model_costs.csv` 連携、ログ生成（Mermaid 図付き） | `studio/logging.py` |
| MultiRoleChat.py | `load_ai_assistants_config`（アシスタント接続層） | `studio/loader.py` |
| code_saver.py + MultiRoleChat.py | `_save_workflow_final_code`（応答からコード抽出 → sandbox/ 保存・実行スクリプト生成） | `studio/artifacts.py` |
| Chat.py | `detect_api_error` / `handle_api_error`（413/429/503/504 リトライ） | `studio/errors.py` |
| Chat.py | `ConversationHistory.reduce_history`（トークン節約） | `studio/history.py` |
| Chat.py | `create_conversation_summary`（要約生成 → 議事録化の土台） | `studio/logging.py` |
| util/stream_render.py | ストリーム表示（モジュール化済み） | そのまま利用 |

---

## 3. データ構造仕様

### 3.1 ディレクトリ構成

```
talents/                ← 人材プール（組織横断で再利用）
  hinata.json           ← name, personality, system_prompt, tags
  satsuki.json
  kaede.json

workflows/              ← ワークフローテンプレート（組織横断で再利用）
  discussion.json       ← 自由討議
  meeting.json          ← 会議（モデレーター付き・ループあり）
  quiz.json             ← クイズ大会

organizations/
  nokuru/
    config.json                 ← 人材選択 + スロット割当 + 役割指示（Git 管理）
    model_mapping.json          ← assistant/model のみ（.gitignore）
    model_mapping.example.json  ← テンプレ（Git 管理）

scenarios/              ← 使い捨て定義（直書き型 / 参照型）
  camp_planning.json

sessions/               ← 実行ログ（7章。JSONL のみ・不変の証跡。.gitignore）
  20260708_120000.jsonl

minutes/                ← 議事録（7.3 節。上書き更新・Git 管理。変遷はコミット履歴で追う）
  nokuru/
    camp_planning.json

sandbox/                ← 開発モードの成果物（7.5 節。セッションから抽出したコード。.gitignore）
  session_20260708_120000/

studio_config.json      ← UI・実行の既定値（stream / temperature / 並列上限。ユーザーローカル・.gitignore）
studio_config.example.json  ← テンプレ（Git 管理）

schemas/                ← 全定義ファイルの JSON Schema（3.7 節。Git 管理）
  talent.schema.json
  organization.schema.json
  workflow.schema.json
  scenario.schema.json
  model_mapping.schema.json
  studio_config.schema.json

tests/                  ← パリティ試験・エンジン単体テスト（9.3 節）
  parity/
```

各定義の ID はファイル名（組織はフォルダ名）から導出する。ファイル内に ID フィールドは持たない。

### 3.2 人材定義（talents/*.json）

ID はファイル名から導出する（`talents/hinata.json` → `hinata`）。

```json
{
  "name": "ひなた",
  "personality": "明るく前向き。対立をやわらげ、会話の流れを整える。",
  "system_prompt": "あなたは『ひなた』。議論を前に進め、発言者ごとの主張を取りこぼさない。回答は『要点』『未確定事項』『次アクション』の3見出しで出し、根拠が弱い点は仮説と明記する。",
  "tags": ["facilitator", "warm", "summary"]
}
```

フィールド仕様：

| フィールド | 必須 | 内容 |
|---|---|---|
| `name` | ✅ | 表示名 |
| `system_prompt` | ✅ | タスク手順・出力形式・禁止事項（実行ルール）。**直書きのみ**（ファイル参照は廃止） |
| `personality` | 任意 | キャラクターの性格・口調・対人スタンス。**最終プロンプトの先頭に前置され、UI の人材一覧表示にも使う**（5章） |
| `tags` | 任意 | 検索・UI フィルタ用 |

`personality` と `system_prompt` の役割分担（確定ルール）：

1. `personality`: 人格・口調（誰であるか）。プロンプト先頭に前置される
2. `system_prompt`: 挙動仕様（何をどう出力するか）
3. 挙動指示を `personality` に書かない。人格説明を `system_prompt` に重複して書かない
4. 全人材共通の出力規約（文字数制限など）は人材に書かず、組織の `common_directives` に置く（3.3 節）

### 3.3 組織定義（organizations/<org>/config.json）

組織名（ID）はフォルダ名から導出する（`organizations/nokuru/` → `nokuru`）。

```json
{
  "name": "のくる",
  "mission": "全員が楽しめるキャンプを企画して実行する",
  "culture": [
    "役職や上下関係のないフラットな仲間として話す",
    "決定は多数決ではなく全員の納得で行う",
    "無理はしない。安全と楽しさを効率より優先する"
  ],
  "talent_ids": ["hinata", "satsuki", "kaede"],
  "default_workflow": "meeting",
  "workflow_bindings": {
    "meeting": {
      "moderator": ["hinata"],
      "member": ["satsuki", "kaede"]
    }
  },
  "common_directives": [
    "1ターン300文字以内で簡潔にまとめる"
  ],
  "role_directives": {
    "hinata": [
      "この会議では司会進行を最優先する",
      "各ターン冒頭でゴールを1文で確認する"
    ],
    "kaede": [
      "装備と安全の担当として、リスクと代替案を必ず提示する"
    ]
  }
}
```

フィールド仕様：

| フィールド | 必須 | 内容 |
|---|---|---|
| `name` | 任意 | 表示名（省略時はフォルダ名を表示に使う） |
| `mission` | 任意 | 組織の目的・使命（1〜2文）。組織コンテキストとして全メンバーのプロンプトに注入される（5章） |
| `culture` | 任意 | 社風・価値観・行動様式（箇条書き）。同上 |
| `talent_ids` | ✅ | 編成メンバー（talents/ の ID を参照）。1組織1編成 |
| `default_workflow` | 任意 | UI 起動時に選択されるワークフロー |
| `workflow_bindings` | 任意 | ワークフローのスロットへの人材割当（4.2 節）。省略時はデフォルト規則を適用 |
| `common_directives` | 任意 | 編成メンバー**全員**への追加指示（出力規約など）。最終プロンプトに追記される（5章）。共通プロンプトのファイル参照層は作らない（旧 `inherit/append` の複雑さを持ち込まないため、この1層のみ） |
| `role_directives` | 任意 | 人材**個別**への組織内追加指示。最終プロンプトに追記される（5章） |

`mission` / `culture` と `common_directives` の役割分担は、人材の `personality` / `system_prompt` と対になる：

| 層 | 「何者か」（アイデンティティ） | 「どう振る舞うか」（実行ルール） |
|---|---|---|
| 人材 | `personality` | `system_prompt` |
| 組織 | `mission` / `culture` | `common_directives` / `role_directives` |

同じ人材でも所属組織の `mission` / `culture` によって振る舞いが変わる。開発チームでの記述例：

```json
{ "mission": "出荷後バグゼロ。品質で信頼を積み上げる",
  "culture": ["テストなきマージを認めない", "曖昧な仕様は実装前に必ず差し戻す"] }
```

```json
{ "mission": "最速でプロトタイプを出し、市場の反応で判断する",
  "culture": ["完璧さより速度。動くものを今日出す", "作り込みは検証が通ってから"] }
```

```json
{ "mission": "PoC で技術的な成立性を見極める。製品化は範囲外",
  "culture": ["スケールや運用は考慮せず、コア仮説の検証に集中する"] }
```

```json
{ "mission": "原理から理解し、再現性のある知見を残す",
  "culture": ["結論より過程を重視する", "根拠は一次情報まで遡って確認する"] }
```

実行時は `talents/*.json` の `system_prompt` に組織コンテキスト（`mission` / `culture`）と
`common_directives` / `role_directives` を追記して最終プロンプトを組み立てる。
組織側にプロンプト本文ファイルは一切置かない（旧 `organizations/<org>/roles/` は廃止）。
UI 初期値（stream / temperature）は組織 config には置かず、`studio_config.json` に置く（3.6 節）。

### 3.4 モデルマッピングの分離（採用方針）

キャラクター定義（共有可）とインフラ設定（環境依存）を分離する。
`.env` / `.env.example` パターンと同じ構造：

| ファイル | 性質 | Git 管理 |
|---|---|---|
| `talents/*.json` | キャラクター定義（共有可） | ✅ commit |
| `organizations/<org>/config.json` | 構造定義（共有可） | ✅ commit |
| `organizations/<org>/model_mapping.json` | 環境依存（個人差あり） | ❌ .gitignore |
| `organizations/<org>/model_mapping.example.json` | テンプレ | ✅ commit |

`model_mapping.example.json` の例（キーは talent の ID）：

```json
{
  "hinata": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "satsuki": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "kaede": { "assistant": "human" }
}
```

**予約アシスタント名 `human`**：人材の実体を AI モデルではなく人間（ユーザー）に割り当てる。
`model` フィールドは不要。その人材の発話ステップでは、エンジンがユーザーに入力を求める（6.6 節）。
マッピングを1行変えるだけで「全員AI」と「人間参加」を切り替えられる
（例：普段はAIのかえでを、今日は自分が演じる）。

**予約アシスタント名 `mock`**：テスト用の決定的な疑似モデル（固定応答・コスト0・API 不要）。
パリティ試験（9.3 節）とエンジン単体テストで使う。`model` フィールドは不要。

ユーザーは `.example` をコピーして自分の環境に合わせて書き換える。
`assistant` の実体（プロバイダー・APIクラス・モデル一覧）は `ai_assistants_config.json` を
正本として使用する（読み込みロジックは `studio/loader.py` へ移植。6.5 節）。

**採用理由**：組織自体はユーザーがカスタムする資産だが、サンプル組織や共有された組織定義を
動かす際に、契約しているプロバイダーがユーザーごとに異なる。モデル割当だけを
`model_mapping.json` に分離しておけば、組織定義はどの環境でもそのまま動かせる。

### 3.5 シナリオ定義（scenarios/*.json）

シナリオの位置づけ（組織との対比）：

| | 人材 | モデル | ワークフロー |
|---|---|---|---|
| 組織 | 参照（talents/ から） | マッピング定義 | 参照（workflows/ から） |
| シナリオ（直書き型） | 直書き（即値） | 直書き（即値） | 直書き（即値） |
| シナリオ（参照型） | 参照（talents/ または organizations/） | 参照（model_mapping）+ 必要時のみ上書き | 参照（workflows/）+ 必要時のみ上書き |

シナリオは「永続管理が不要な使い捨て」。組織は「継続的に育てる資産」。
運用上は、単発実行は直書き型、反復実行や差分検証は参照型を基本とする。
**組織に複数編成を持たせない代わりに、別編成が必要な場合は参照型シナリオで表現する。**

シナリオ ID はファイル名から導出する（`scenarios/camp_planning.json` → `camp_planning`）。

参照型の例（編成の一部差し替え + 生成パラメータ）：

```json
{
  "organization": "nokuru",
  "workflow": "discussion",
  "talent_ids": ["hinata", "satsuki"],
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
3. `variation_profile`: `stable` / `balanced` / `creative` のプリセット名として運用

### 3.6 アプリ設定（studio_config.json）

UI・実行の既定値はユーザーごとの好み（環境差分）なので、Git 管理の組織 config には置かず、
ユーザーローカルの `studio_config.json` に置く（model_mapping と同じ `.example` パターン）。

```json
{
  "stream": true,
  "temperature": 0.7,
  "max_parallel_calls": 8,
  "default_org": "nokuru",
  "upload_limits": {
    "max_files": 5,
    "max_file_size_kb": 256,
    "max_total_chars": 80000
  }
}
```

temperature の優先順位（上が優先）：

1. シナリオの `generation.temperature`（3.5 節）
2. UI での一時変更（スライダー）
3. `studio_config.json` の既定値

`max_parallel_calls` は parallel フェーズでの API 同時呼び出し数の上限
（レート制限対策。UI コンポーネント数の制約ではない）。

`upload_limits` はファイル取り込み（Web アップロード / CLI `--files`）の上限。
既定値は旧 Web 版の実績値（5ファイル / 256KB / 計8万字）を引き継ぐ。
ソースコード一式を渡す開発用途では、モデルのコンテキスト長に応じて引き上げて使う。

### 3.7 スキーマ定義（schemas/）

本章・4章の JSON 例を正本とせず、**JSON Schema（draft 2020-12）を機械検証の正本**として
`schemas/` に置く。定義ファイル種別ごとに1スキーマ（3.1 節のファイル一覧）。

運用ルール：

1. `studio/loader.py` は読み込み時に、UI は保存時に、**同じスキーマファイル**で検証する
   （検証ロジックの二重実装を作らない。Python 実装は `jsonschema` ライブラリを使用）
2. スキーマで検証できるのは形式（必須フィールド・型・列挙値・`count` の `"1"`/`"1+"` パターンなど）まで。
   ファイル間の参照整合性（talent_ids の存在確認など）は 5.2 節のバリデーションが担当する
3. 本章の JSON 例とスキーマが食い違った場合はスキーマを正とし、ドキュメントを直す
4. スキーマは Phase 1 の実装開始前に作成する（1.4 節の設計判断）

---

## 4. ワークフロー仕様

### 4.1 スキーマ

ワークフローは組織横断のテンプレートなので、**人材IDを直書きせず、スロット（役割枠）を宣言する**。
ワークフロー ID はファイル名から導出する（`workflows/meeting.json` → `meeting`）。

```json
{
  "name": "会議（モデレーター付き）",
  "description": "モデレーターが論点整理し、メンバーが意見を出し、結論が出るまで反復する",
  "slots": {
    "moderator": { "description": "進行役。論点整理と結論判定を行う", "count": "1" },
    "member": { "description": "議論参加者", "count": "1+" }
  },
  "phases": [
    {
      "type": "serial",
      "steps": [
        { "slot": "moderator", "action": "議題を確認し、論点を3つ以内で提示する" }
      ]
    },
    {
      "type": "loop",
      "max_iterations": 3,
      "exit": { "type": "marker", "marker": "【結論】" },
      "phases": [
        {
          "type": "parallel",
          "steps": [
            { "slot": "member", "action": "論点に対する意見と根拠を述べる" }
          ]
        },
        {
          "type": "serial",
          "steps": [
            { "slot": "moderator", "action": "意見を集約し、合意可能かを判断する。不足があれば追加論点を提示する" }
          ]
        }
      ]
    }
  ]
}
```

フィールド仕様：

| フィールド | 内容 |
|---|---|
| `slots` | 役割枠の宣言。`count` は `"1"`（ちょうど1人）または `"1+"`（1人以上）の文字列 |
| `phases` | 実行フェーズの配列。`type` は `serial` / `parallel` / `loop` |
| `steps[].slot` | 発話するスロット。スロットに複数人材が割り当てられている場合、その人数分のステップに展開される |
| `steps[].action` | そのステップで人材に与える指示。ユーザーメッセージ側に付加される（5章） |
| `loop.max_iterations` | ループの最大反復回数（`exit.type: "user"` 以外は必須。無限ループ防止） |
| `loop.exit` | 任意。ループ終了判定の方式（下記）。省略時は `max_iterations` 回で必ず終了する |

**ループ終了判定（`exit`）の3方式**：

| type | 判定者 | 仕組み |
|---|---|---|
| `marker` | ループ内の最終ステップの発話者 | 各反復の最終応答に `marker` 文字列が含まれたら終了。発話者が進行と判定を兼ねる最も軽い方式 |
| `judge` | 判定専用のスロット（AI） | 各反復の最後に**判定専用ステップ**を追加実行する。`slot` の人材に `criteria`（終了条件）と直近のやり取りを渡し、継続/終了を判定させる |
| `user` | ユーザー（human-in-the-loop） | 各反復の最後にユーザーへ継続/終了を問い合わせる。CLI は入力待ち、Web は継続/終了ボタン（6.3 節 `await_user` イベント）。`max_iterations` を省略でき、無限継続をユーザー判断で運用できる |

`judge` の記述例（品質レビュー役が合格判定するまで改善ループを回す）：

```json
{
  "type": "loop",
  "max_iterations": 5,
  "exit": {
    "type": "judge",
    "slot": "reviewer",
    "criteria": "指摘事項がすべて解消され、追加の懸念がないこと"
  },
  "phases": [ ... ]
}
```

`user` の記述例（ユーザーが納得するまで会議を続ける）：

```json
{
  "type": "loop",
  "exit": { "type": "user", "prompt": "議論を続けますか？" },
  "phases": [ ... ]
}
```

補足ルール：

1. `judge` の `slot` は通常のスロットと同様に宣言・バインドする（4.2 節の規則に従う）。
   進行役と兼任させたい場合は同じ人材を両スロットに割り当てればよい
2. 判定ステップの出力形式（`【判定】継続` / `【判定】終了` + 理由）はエンジンが指示を自動注入する。
   判定はログには記録するが、**各人材の会話履歴には含めない**（進行制御であって会話ではないため）
3. **終了指示の自動注入**：`marker` 方式でも終了指示を `action` に手書きしない。
   `exit` 定義からエンジンが終了指示文を生成して該当ステップに注入する
   （手書きすると `exit` との二重管理になり、片方だけ変更するとループが黙って壊れるため）
4. `exit` の判定が出なくても `max_iterations` に達したらループを抜ける（`user` 方式を除く）

### 4.2 ロールバインディング

スロットへの人材割当は組織 config の `workflow_bindings` で行う（3.3 節）。

解決規則：

1. `workflow_bindings.<workflow_id>.<slot>` があればそれを使う
2. バインディング未指定で、ワークフローのスロットが**1種類だけ**の場合、組織の `talent_ids` 全員を割り当てる
   （`discussion.json` のような単一スロットのテンプレートは設定なしで動く）
3. スロットが複数種類あるのにバインディング未指定の場合は**起動時エラー**（実行前バリデーション）
4. `count: 1` のスロットに複数人材、`count: "1+"` に0人の割当も起動時エラー

### 4.3 フェーズ実行規則

1. `serial`: steps を順番に実行する。各ステップは同一フェーズ内の先行発言を入力文脈に含む
2. `parallel`: steps をスレッド並列で実行する。互いの発言は見えない。全員完了後に次フェーズへ進む
3. `loop`: 内包する `phases` を反復する。各反復の最後に `exit` の終了判定
   （marker 検出 / judge ステップ実行 / ユーザー問い合わせ）を行い、
   終了判定または `max_iterations` 到達でループを抜ける
4. スロット展開: スロットに N 人が割り当てられている場合、そのステップは N ステップに展開される
   （serial では割当順、parallel では同時実行）

---

## 5. プロンプト解決とバリデーション仕様

### 5.1 プロンプト組み立て

互換レイヤ廃止により、解決ルールは1本化される。

最終システムプロンプトの組み立て（この順で連結）：

```
1. talent.personality        （あれば）
2. talent.system_prompt      （正本・必須）
3. 組織コンテキスト           （org.mission / org.culture があれば。下記形式で注入）
4. org.common_directives     （あれば。箇条書きで追記。全員共通）
5. org.role_directives[id]   （あれば。箇条書きで追記。個別）
```

組織コンテキストの注入形式（エンジンが `mission` / `culture` から生成する）：

```
【所属組織】のくる
【ミッション】全員が楽しめるキャンプを企画して実行する
【文化・行動規範】
- 役職や上下関係のないフラットな仲間として話す
- 決定は多数決ではなく全員の納得で行う
- 無理はしない。安全と楽しさを効率より優先する
```

ステップ実行時のユーザーメッセージ：

```
1. ユーザー入力（またはループでの前フェーズ出力の引き継ぎ）
2. step.action               （あれば。「あなたへの指示: ...」として付加）
3. ループ終了判定の指示       （`exit` 方式に応じてエンジンが自動注入。4.1 節）
4. 添付ファイルコンテキスト（Web: アップロード / CLI: --files。同一ロジックを共用）
```

### 5.2 読み込みフローとバリデーション

1. 各定義ファイルを JSON としてパースし、`schemas/` の JSON Schema で形式を検証する（3.7 節）
2. 起動時（または組織切替時）に `talents/*.json` を1回スキャンして `ID（ファイル名）-> talent定義` の索引を作る
3. `organizations/<org>/config.json` の `talent_ids` を索引と突き合わせ、存在しない ID はエラー
4. `model_mapping.json` を同じ ID キーで読み、割当のない人材はエラー
   （`assistant: "human"` の場合は `model` 不要。それ以外は `assistant` が
   `ai_assistants_config.json` に存在し `model` が指定されていることを検証）
5. ワークフローのスロットバインディングを検証（4.2 節の規則）。
   加えて **`workflow_bindings` に登場する ID がすべて `talent_ids` に含まれること**を検証する
6. `role_directives` のキーが `talent_ids` に含まれることを検証する
7. UI からの保存時にも同じバリデーションを実行する

### 5.3 エラー仕様

バリデーション失敗時のエラーコードと表示文言を固定する（実装・テスト・UI で共通に使う）。

表示ルール：

1. 形式は `[コード] 対象: 内容（修正ヒント）`。UI と CLI で同一文言を使う
2. 1コード = 1原因。最初のエラーで打ち切らず、**検出できたエラーを全件まとめて報告**する
3. CLI 起動時・バッチ実行時: 全件表示して終了コード 1。Web UI 保存時: 保存を中断して警告表示

| コード | 内容 | 表示文言の例 |
|---|---|---|
| E101 | JSON 構文エラー | `[E101] talents/hinata.json: 12行目で JSON パースに失敗しました` |
| E102 | スキーマ違反 | `[E102] workflows/meeting.json: 'slots.moderator.count' は "1" または "1+" である必要があります` |
| E201 | talent 不明 | `[E201] 組織 'nokuru': talent 'yamada' が talents/ にありません（talents/yamada.json を作成するか talent_ids から削除してください）` |
| E202 | model_mapping 欠落 | `[E202] 組織 'nokuru': talent 'kaede' のモデル割当がありません（model_mapping.json に追加してください）` |
| E203 | assistant 不明 | `[E203] model_mapping: 'Gorq' は ai_assistants_config.json にありません（'Groq' の誤りではありませんか）` |
| E204 | model 未指定 | `[E204] model_mapping: 'hinata' の model が未指定です（assistant が human 以外の場合は必須）` |
| E205 | binding の ID が編成外 | `[E205] 組織 'nokuru': workflow_bindings の 'momiji' が talent_ids に含まれていません` |
| E206 | role_directives のキーが編成外 | `[E206] 組織 'nokuru': role_directives の 'momiji' が talent_ids に含まれていません` |
| E207 | workflow 不明 | `[E207] 組織 'nokuru': default_workflow 'meating' が workflows/ にありません` |
| E301 | スロット未バインド | `[E301] workflow 'meeting': スロット 'moderator' への割当がありません（workflow_bindings に追加してください）` |
| E302 | スロット人数違反 | `[E302] workflow 'meeting': スロット 'moderator'（count "1"）に2人が割り当てられています` |
| E303 | max_iterations 欠落 | `[E303] workflow 'meeting': loop に max_iterations がありません（exit.type "user" 以外では必須）` |
| E304 | judge スロット不備 | `[E304] workflow 'review': exit.judge の slot 'reviewer' が slots に宣言されていません` |
| E401 | API キー未設定 | `[E401] assistant 'Groq': 環境変数 GROQ_API_KEY が未設定です` |
| E402 | バッチ実行不可 | `[E402] このワークフローは human 参加または exit.type "user" を含むため --topic による無人実行はできません` |

コード帯の意味：E1xx = ファイル形式、E2xx = 参照整合性、E3xx = ワークフロー構造、E4xx = 実行環境。
新しいエラーを追加する場合はこの帯に従って採番する。

---

## 6. 実行エンジン仕様

### 6.1 方針

- MultiRoleChat の `_run_phases` / `_run_engine` / 反復実行を `studio/engine.py` へ**コピーして移植**する
  （完全移行を前提とするため、旧ファイルへの import 依存は作らない）
- Chat.py の APIエラーリトライ・履歴縮約・要約生成を部品として移植する
  （複数ロールの並列実行ではレート制限に当たる頻度が高く、体系的なリトライが必須）
- エンジンは UI 非依存とし、実行イベントを yield するジェネレータとして実装する
  （MultiRoleChatWeb で起きた「Web 版がエンジンを約200行再実装する」二重化を再発させない）

### 6.2 パッケージ構成

```
studio/
  engine.py      ← ワークフロー実行（serial/parallel/loop、イベント yield）
  loader.py      ← talents / organizations / model_mapping / workflows / scenarios の読み込みと検証
  history.py     ← ロール別会話履歴 + reduce_history（トークン節約）
  errors.py      ← APIエラー検出とリトライ（413/429/503/504）
  logging.py     ← セッションログ（JSONL + Markdown）、トークン・コスト集計、要約生成
  artifacts.py   ← 成果物抽出（コードブロック → sandbox/ 保存。7.5 節）
  vcs.py         ← Git 連携（成果物の採用とコミット。7.6 節。Phase 5）
MultiRoleStudio.py     ← CLI 入口（イベントを print / input() で表示）
MultiRoleStudioWeb.py  ← Web 入口（イベントを Gradio の yield 更新に変換）
```

使い方は従来同様 `python MultiRoleStudioWeb.py --org nokuru` を維持する。

### 6.3 イベント駆動インターフェース

エンジンはセッション実行中に以下のイベントを順次 yield する。CLI / Web は表示方法だけを実装する。

| イベント | ペイロード | CLI の表示例 | Web の表示例 |
|---|---|---|---|
| `session_start` | session_id, org, workflow, 参加人材 | ヘッダ表示 | - |
| `phase_start` | phase 種別, 反復回数 | 区切り線 | - |
| `step_start` | talent_id, 表示名, action | `--- ひなた ---` | 「⏳ 考え中...」吹き出し追加 |
| `chunk` | talent_id, 差分テキスト | `print(end="")` | 吹き出しを逐次更新して yield |
| `step_done` | talent_id, 全文, 経過秒, トークン使用量 | 改行 | 吹き出し確定 |
| `step_error` | talent_id, エラー内容, リトライ状況 | エラー表示 | ❌ 吹き出し |
| `loop_check` | 反復回数, 終了判定の方式と結果（judge の場合は理由も） | 状況表示 | 判定結果の表示 |
| `await_user` | 問いかけ文, 選択肢（継続/終了） | `input()` で入力待ち | 継続/終了ボタンを表示して待機 |
| `session_done` | コスト集計, 総経過秒, ログパス | サマリ表示 | - |

ログ書き込み（7章）とコスト集計はイベント処理としてエンジン側で共通実行する（表示層の責務にしない）。

`await_user` はエンジンが一時停止してユーザーの回答を受け取る双方向イベント
（表示層が回答をエンジンへ返すまで次へ進まない）。ループの `exit.type: "user"`（4.1 節）のほか、
将来の対話型ワークフロー（途中でユーザーが指示を挟む等）にも同じ仕組みを使う。

### 6.4 実行時挙動

1. **会話履歴**: 人材ごとに独立した履歴を保持する。上限超過時は `reduce_history` で自動縮約する
2. **ストリーミング**: ON/OFF 切替可能（既定値は `studio_config.json`）。parallel フェーズでは完了後一括表示（現行 Web 版と同じ）
3. **temperature**: セッション共通値を適用（優先順位は 3.6 節）。非対応モデルのエラーを検出したら温度指定なしで1回だけ再試行する
4. **APIエラーリトライ**: 413/429/503/504 を検出し、待機付きリトライを行う。リトライ上限超過時は
   `step_error` を発行して次ステップへ進む（セッション全体は止めない）
5. **並列実行の上限**: parallel フェーズの API 同時呼び出し数は `studio_config.json` の
   `max_parallel_calls` で制御する（超過分はキューイング）

### 6.5 アシスタント接続層

- プロバイダー定義（アシスタント名 → module / class / `models` 一覧）は
  **`ai_assistants_config.json` を正本**とする。旧 `ai_assistants_config.csv` への
  フォールバックは実装しない
  （現状は Chat.py が「JSON優先・CSVフォールバック」、MultiRoleChat.py が「CSVのみ」と
  読み込みが二重実装かつ不一致になっており、これを解消する。
  `models` 一覧は設定編集 UI のモデル選択プルダウンにも必要）
- 読み込みロジックは `studio/loader.py` へ移植する（旧ファイルへの依存を残さないため）
- API キーは従来通り環境変数で管理する

### 6.6 人間参加ロール（assistant: human）

model_mapping で `"assistant": "human"` を割り当てた人材は、ユーザーが演じるロールになる。
これにより人間も AI と同じ立場で会議・ワークフローに参加できる。

実行規則：

1. human 人材の発話ステップでは、エンジンが `await_user` イベント（6.3 節）を発行して一時停止する。
   ペイロードには人材名・そのステップの `action`・終了判定指示（該当時）を含める
2. ユーザーの入力テキストは、AI の応答とまったく同じ扱いでステップ応答となる
   （各人材の会話履歴に追加、ログに `step` として記録。tokens / cost は 0）
3. human 人材の `personality` / `system_prompt` / `role_directives` は API には送られず、
   入力を求める際に**役割ブリーフィングとして画面に表示**する（「あなたはこの役です」の提示）
4. parallel フェーズに human が含まれる場合、AI の呼び出しは先に並列実行し、
   human の入力完了を待ってからフェーズを完了する
5. judge スロット（4.1 節）にも human を割り当てられる。この場合、ループ終了判定を人間が行う
   （`exit.type: "user"` は「judge に human を割り当てる」の簡易記法に相当する）
6. ストリーミング・temperature・リトライなどの AI 固有の挙動は human ステップには適用しない

想定ユースケース：

- **人間参加の会議**: AI 司会 + AI メンバー + 人間メンバーで議論する。人間の発言も議事録（7.3 節）に載る
- **人間が司会**: moderator スロットに human を割り当て、進行だけ人間が握って発散を抑える
- **ロールプレイ・訓練**: 面接官役や顧客役を AI にやらせ、自分は回答者として練習する
- **ゲーム（付録A）**: プレイヤーキャラクターを human、NPC を AI にする

---

## 7. ログ・セッション管理仕様

### 7.1 ログ形式

セッションの正本は `sessions/<session_id>.jsonl` のみとする。
人間可読の Markdown レポート（Mermaid フロー図・応答時間サマリテーブル付き。現行 multi_logs 形式を踏襲）は
**保存せず、閲覧時・エクスポート時に jsonl から生成する**
（派生物を保存すると、分岐再開後に古いレポートが残る同期問題が生じるため）。

`session_id` は `YYYYMMDD_HHMMSS` 形式のタイムスタンプ。
組織名・ワークフロー名などのメタデータは jsonl 先頭の `session_meta` 行を正本とし、
ファイル名にはエンコードしない（一覧 UI は `session_meta` を読んで表示する）。

JSONL の行種別：

```jsonl
{"type": "session_meta", "organization": "nokuru", "workflow": "meeting", "parent_session_id": null, "talents": {...}, "models": {...}, "generation": {...}}
{"type": "user_input", "text": "...", "attachments": [...]}
{"type": "step", "talent_id": "hinata", "action": "...", "text": "...", "elapsed": 3.2, "tokens": {"in": 512, "out": 320}, "cost": 0.0012}
{"type": "state_snapshot", "state": {"turn": 5, "flags": [...]}}
{"type": "session_end", "total_elapsed": 84.5, "total_cost": 0.031}
```

### 7.2 途中再開（セッション再開）

MultiRoleChat / MultiRoleChatWeb には薄かった「途中再開」を、MultiRoleStudio では正式機能として持つ。

要件：

1. セッション一覧から過去ログ（jsonl）を選択して再開できる
2. 再開時に会話履歴だけでなく `state`（turn, flags, affinity, inventory など）も復元する
3. 再開後は「続きで上書き」ではなく「分岐保存（branch）」を標準にする。新しい `session_id` を発行し、
   `parent_session_id` を記録する
4. 参照専用モード（読み取り専用リプレイ）と編集モード（再開して続行）を分離する

期待効果：

- 会議: 前回議論の文脈を維持したまま継続できる
- ゲーム: セーブ/ロードに相当する体験が作れる
- 恋愛系の endless モード: 日次セッションを自然に積み上げられる

### 7.3 会議サマリの議事録化（上書き + Git 履歴方式）

要約生成は Chat.py の `create_conversation_summary` を移植した `studio/logging.py` の機能を使う。

記録は役割の異なる三層に分ける：

| 層 | ファイル | 更新方式 | 変遷の追い方 | Git |
|---|---|---|---|---|
| 証跡（生ログ） | `sessions/<id>.jsonl` | 追記のみ・不変 | ファイルがそのまま時系列 | 管理しない（.gitignore） |
| 議事録（まとめ） | `minutes/<org>/<テーマ>.json` | **常に上書き**（最新だけを保持） | **Git のコミット履歴で見る** | 管理する |
| 成果物（コード） | `sandbox/session_<id>/` | セッションごとに生成 | 採用コミット（7.6 節） | 採用時に管理 |

議事録を「版を積むファイル」ではなく「上書きされる生きた文書」にするのがポイント。
最新の状態を知りたければファイルを1つ読むだけでよく、
「いつ何が決まり、何が未決から決定に変わったか」という変遷は
生ログを追わなくても **Git の diff / log で見られる**。
バージョン番号フィールドは持たない（版管理は Git の仕事）。

議事録の最小項目：

1. `decisions`（決定事項）
2. `open_issues`（未決事項）
3. `actions`（担当・期限つきアクション）
4. `evidence`（根拠となる発話。継続会議をまたぐためセッション付きで記録）
5. `next_agenda`（次回アジェンダ）

保存フォーマット（`minutes/nokuru/camp_planning.json`）：

```json
{
  "topic": "camp_planning",
  "updated_at": "2026-07-09T21:00:00+09:00",
  "source_sessions": ["20260707_210000", "20260709_190000"],
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
    "evidence": [
      { "session": "20260709_190000", "turns": [12, 18, 24] }
    ],
    "next_agenda": [
      "保存形式の最終決定",
      "再開UIの仕様確定"
    ]
  }
}
```

運用ルール：

1. 5〜10ターンごとに「まとめ役ロール」がサマリを更新（セッション実行中はメモリ上）
2. セッション終了時に議事録ファイルを**上書き保存**し、コミットする
   （7.6 節の仕組みを使い、メッセージに `session_id` を記録。プッシュはしない）
3. 継続会議（7.2 節の再開）では**同じ議事録ファイルを更新し続ける**。
   結果として `git log minutes/nokuru/camp_planning.json` がそのまま議論の変遷史になる
4. 再開時は「最新議事録 + 直近生ログ」を入力文脈として利用

### 7.4 運用モードの抽象化

1.2 節のゲーム抽象に基づき、会議・エンタメ・ゲームは
「終了条件と、記録の重み付けが異なる同一のゲーム」として同じ基盤で扱う。
共通部品は `talents`（発話主体）、`workflows`（進行ルール）、`state`（実行状態）、
`summary`（圧縮記録）の4つで、モードによる違いは設定だけである。

| モード | 勝利条件（終了条件） | 重視する記録 |
|---|---|---|
| 会議 | 結論が出ること | 決定事項・未決事項・担当期限（議事録） |
| 開発（プログラミング） | レビュー合格・要件充足 | 成果物＝コード（7.5 節で抽出・保存） |
| エンタメ | 続けたくなること（または区切り） | 関係変化・転機・次回フック（ダイジェスト） |
| ゲーム | `ending_policy`（付録A） | `state` の更新履歴（プレイログ） |

設計上の利点：

1. ログ再開・要約・分岐保存の仕組みを共通化できる
2. 会議議事録と物語ダイジェストを同じパイプラインで生成できる
3. 将来の用途追加（教育、訓練、シミュレーション）にも拡張しやすい

### 7.5 成果物抽出（プログラミング対応）

開発モードでは会話の記録だけでなく**成果物（コード）**が主産物になる。
旧 MultiRoleChat の `_save_workflow_final_code` + `code_saver.py` を
`studio/artifacts.py` へ移植して正式機能とする。

仕様：

1. セッション終了時（またはユーザー操作時）に、ステップ応答からコードブロック
   （```言語 ... ```）を抽出し、`sandbox/session_<session_id>/` に保存する
2. **ファイル名規約**: コードブロック直前の行に `ファイル名: <相対パス>` と書かれていれば
   そのパスで保存する（サブディレクトリ可）。なければ旧実装同様、言語から自動命名する。
   開発ワークフローの実行時は、この規約をエンジンが指示として自動注入する
   （--files で取り込んだ既存ファイルを修正して同名で保存し直す、という往復ができる）
3. 抽出元は JSONL ログの `step` 行なので、**実行後のセッションからも遡って抽出できる**
   （旧実装のようにメモリ上の蓄積に依存しない）
4. 同一パスのファイルを複数ステップが出力した場合は、**後のステップの出力を採用**する
   （レビュー→修正ループの最終版が残る）
5. 旧実装同様、実行スクリプト（run_all.sh 相当）の生成も引き継ぐ
6. 生成コードの自動実行はしない（保存まで。実行はユーザーの明示操作）
7. `sandbox/` への保存はパス検証を行い、`sandbox/session_<id>/` の外へ書き出さない
   （`../` などのパス指定は拒否する）

開発ワークフローとの組み合わせ：

- ループ + judge（4.1 節）がそのまま開発サイクルになる：
  実装ロールがコードを出す → レビューロールが judge として合否判定 →
  不合格なら指摘を踏まえて次の反復で修正 → 合格でループ終了、最終コードを抽出
- 旧 `codecraft_collective` / `tech_startup` のような開発組織は、
  3.3 節の開発チーム culture 例（バグゼロ / 高速プロトタイプ等）を使って新形式で再構築する

### 7.6 Git 連携（成果物の採用とコミット）

sandbox の成果物を作業ツリーへ反映する「採用（apply）」操作に Git コミットを結びつける。
AI の変更が常に1コミット=1セッションの粒度で履歴に残り、レビューとロールバックが容易になる
（Aider などの AI コードツールと同じ「コミットで守る」思想）。

仕様：

1. **採用はユーザーの明示操作**（CLI: `--apply <session_id>` / Web: セッションタブの「採用」ボタン）。
   エンジンが実行中に作業ツリーへ書き込むことはない（7.5 節の sandbox 隔離を維持）
2. 採用時に、適用したファイル群を **1コミット**として作成する。
   コミットメッセージはセッション要約から生成し、末尾に `session_id` を記録する
   （コミット ⇔ `sessions/<id>.jsonl` の相互トレースができる）
3. **プッシュはしない**（スコープ外として明記）。リモート操作・ブランチ削除・force 系・
   rebase などの破壊的操作も行わない。行うのはステージングとコミットのみ
4. 適用先の作業ツリーに**未コミットの変更がある場合は中断**する
   （ユーザーの作業と AI の変更を1コミットに混ぜない）
5. オプションで採用時に新規ブランチ（例: `studio/<session_id>`）を切ってからコミットできる
6. リポジトリでないディレクトリでは Git 操作をスキップし、ファイル適用のみ行う

実装は `studio/vcs.py`（git コマンドのラッパー）。導入は Phase 5（運用機能）とする。

---

## 8. UI 仕様

### 8.1 CLI 版（MultiRoleStudio.py）

- 組織・ワークフロー・シナリオを引数または対話コマンドで選択して実行する
- エンジンイベントを print で逐次表示（ストリーミング対応）
- セッション再開は `--resume <session_id>` で行う
- **バッチ実行（無人完走）**: 議題まで引数で渡せば、以降ユーザー入力なしで終了まで自動実行する
- **ファイル入力**: `--files` で既存ファイル（ソースコード等）を会話コンテキストに取り込む
  （Web 版のアップロードと同じ取り込みロジックを共用する）
- **成果物の採用**: `--apply <session_id>` で sandbox の成果物を作業ツリーへ適用し、
  コミットを作成する（7.6 節。プッシュはしない）

```bash
python MultiRoleStudio.py --org nokuru --workflow meeting --topic "秋キャンプの行き先を決める"
python MultiRoleStudio.py --org dev_team --workflow dev --topic "バグ修正" --files src/utils.py src/main.py
```

  ワークフローに `assistant: "human"` の人材や `exit.type: "user"` が含まれる場合は
  バッチ実行不可として起動時にエラーにする（実行途中で入力待ちのまま止まるのを防ぐ）

### 8.2 Web 版（MultiRoleStudioWeb.py）タブ構成

```
[💬 チャット] [⚙️ 設定編集] [📄 セッション]
```

### 8.3 チャットタブ

現行 MultiRoleChatWeb の機能を踏襲する：

1. 左ペイン: 組織選択 / ワークフロー選択（「直接送信：全ロール」を先頭に含む）/
   ファイル添付（テキスト系の取り込み）/ ストリーミング ON/OFF / Temperature スライダー / 人材一覧表示 / 履歴クリア
2. ストリーミング・Temperature の初期値は `studio_config.json` から取得する（3.6 節）
3. 右ペイン: 単一スレッドのチャット表示。人材ごとに識別ラベル（色絵文字など。表示層の実装詳細とし仕様では定めない）を付ける
4. 人数上限は設けない。並列 API 呼び出しの同時数は `max_parallel_calls` で制御する（6.4 節）
   （旧 MAX_ROLES = 16 は複数 Component 時代の名残であり、単一スレッド表示では不要）
5. ストリーミング・並列実行の表示挙動は 6.3 節のイベント対応表に従う
6. 人間参加ロール（6.6 節）の入力要求時は、メッセージ入力欄を「〇〇（あなたの役）として発言してください」
   モードに切り替え、役割ブリーフィングとステップ指示を表示する

### 8.4 設定編集タブ

新データ構造（3章）に対応した編集画面にする。旧構造（demo_roles / system_prompt_file）の編集 UI は作らない。

```
左ペイン: 編集対象の選択
  [👤 人材（talents/）]
  [🏢 組織（organizations/）]
  [🔄 ワークフロー（workflows/）]
右ペイン: 選択対象のエディタ
```

1. **人材編集**: 一覧（追加/削除）+ 詳細フォーム（id / name / personality / tags）+
   システムプロンプト本文（テキストエリア）
2. **組織編集**: name / mission / culture の編集（組織プロフィール）/
   talent_ids の選択（人材プールからチェックボックス）/ workflow_bindings のスロット割当 /
   common_directives / role_directives の編集 / model_mapping の編集（assistant はプルダウン、model は選択+自由入力）
3. **ワークフロー編集**: JSON テキストエリア（当面）。保存時に 4.2 節のバリデーションを実行
4. 保存時は 5章のバリデーションを通し、エラーは保存前に警告表示する
5. 保存関数は `save_config(kind, id, data)` の形に抽象化し、構造変更時に UI を触らずに済むようにする

### 8.5 セッションタブ

1. `sessions/` の一覧表示（新しい順。各 jsonl の `session_meta` から組織・ワークフロー・日時を表示）
2. 選択セッションの Markdown レポートを jsonl からその場で生成して閲覧（7.1 節。ファイルとしては保存しない）
3. 「再開」ボタン: 選択セッションの `state_snapshot` を復元し、分岐セッションとして続行（7.2 節）
4. 「議事録」ボタン: 議事録を `minutes/` へ上書き保存し、コミットを作成する（7.3 節）
5. 「エクスポート」ボタン: Markdown レポートをファイル出力する
6. 「採用」ボタン: sandbox の成果物を作業ツリーへ適用し、コミットを作成する（7.6 節。Phase 5）

---

## 9. ロードマップと移行方針

### 9.1 段階導入ロードマップ

実装は歴史（Chat.py → MultiRoleChat.py）をなぞり、**1人 → 複数人 → 進行制御**の順で進める。
各 Phase を「動く道具」として完成させてから次へ進む。
着手前に JSON Schema（3.7 節）とパリティ試験（9.3 節）を先に作成する。

コア構築フェーズ：

1. **Phase 1（1人チャット = Chat.py 相当）**: `studio/` パッケージ + CLI 版の最小形。
   1人組織 + 直接送信。新データ構造（3章）の loader（talents / 組織 / model_mapping /
   studio_config + スキーマ検証・エラー表）、エンジン最小形（serial 1ステップ・イベント yield・
   ストリーミング）、ロール別履歴 + 縮約、APIエラーリトライ、JSONL ログ、CLI（バッチ実行含む）。
   **データ→プロンプト組み立て→実行→ログの縦一気通貫**を最小構成で検証する
2. **Phase 2（複数人 = MultiRoleChat 相当）**: スロット展開と serial / parallel、
   組織コンテキスト（mission / culture）、`discussion.json` / `quiz.json`、
   予約アシスタント `mock` / `human`
3. **Phase 3（進行制御 = Studio 固有）**: loop + `exit`（marker / judge / user）、
   `meeting.json` / `dev.json`、成果物抽出（7.5 節）。サンプルデータ一式（10章）を揃える
4. **Phase 4（Web UI）**: Web 版（チャットタブ + 設定編集タブ + セッションタブ閲覧）
5. **Phase 5（運用機能）**: セッション再開（分岐保存）、議事録化（7.3 節）、Git 連携（7.6 節）、
   旧版からの完全移行完了（9.2 節）

業務適用拡張フェーズ：

6. **Phase 6（生成連携）**: 会話出力から TTS / ナレーション原稿 / ショット指示を生成
7. **Phase 7（考査支援）**: 映像・音声・字幕の自動コンプラチェック用ルール評価を追加
8. **Phase 8（運用基盤）**: 評価指標（品質・遅延・コスト）と MLOps 向け監視を追加
9. **Phase 9（連携拡張）**: 外部ベンダー連携を前提に API 契約と入出力スキーマを固定

補足：

- Phase 6 までは内製プロトタイプ中心
- Phase 7 以降は法務/考査フローとの接続を前提に段階導入

### 9.2 完全移行の方針

MultiRoleStudio は MultiRoleChat / MultiRoleChatWeb の完全な置き換えを目指す。

移行の3段階：

1. **並行運用期**: Studio を新規開発し、日常利用を徐々に Studio へ移す（旧版は凍結・バグ修正のみ）
2. **同等性確認**: 下記パリティチェックリストの全項目が Studio で動くことを確認する
   （判定は 9.3 節のパリティ試験の全件パスで自動化する）
3. **廃止**: MultiRoleChat / MultiRoleChatWeb を `legacy/` へ移動または削除し、README の案内を差し替える

パリティチェックリスト（移行完了の定義）：

- [ ] ワークフロー実行: serial / parallel / ループ（反復 + 打ち切り）
- [ ] 会議進行（モデレーター付き）→ `workflows/meeting.json` で再現
- [ ] クイズ（単発・連続・集計ログ）→ `workflows/quiz.json` で再現
- [ ] ロール間会話（max_turns 制御）→ ワークフロー定義で再現
- [ ] トークン・コスト集計（model_costs.csv 連携）
- [ ] ワークフロー最終コードの保存（sandbox/ への抽出）→ 7.5 節で再現
- [ ] Markdown ログ（Mermaid フロー図・応答時間サマリ）
- [ ] 温度非対応モデルへのフォールバック
- [ ] ストリーミング表示（CLI / Web 両方）
- [ ] ファイル添付の取り込み（Web）
- [ ] 組織・ワークフローの Web 編集

注意事項：

- 旧データ（`organizations/*/config.json` / `roles/*.txt`）の読み込み互換は**実装しない**。
  既存組織を Studio で使いたい場合は、新形式で作り直す（サンプルデータを雛形にする）
- Studio のコードは旧ファイルから import しない（旧ファイルを消せる状態を保つ）

### 9.3 パリティ試験の先行作成（テストファースト）

9.2 のチェックリストは、**実装開始前に** `tests/parity/` の pytest 項目へ変換し、
移行完了判定を「全項目が✅」という手動確認から「パリティ試験の全件パス」という自動判定に置き換える。

方針：

1. LLM の出力は非決定的なので、試験は**応答の内容ではなく実行の構造**を検証する
   （イベント列の種別と順序、JSONL ログの行種別と必須キー、ループの終了条件、
   parallel の実行数、コスト集計の整合など）
2. モデルは予約アシスタント `mock`（3.4 節。決定的な固定応答・コスト0）に差し替えて実行する。
   これにより API キーなし・ゼロコストで CI 実行できる
3. 実行はバッチ実行モード（8.1 節）を使い、`--org` / `--workflow` / `--topic` 指定の無人完走で回す
4. 温度非対応フォールバックやレートリトライは、`mock` に該当エラーを疑似発生させて検証する
5. **human ロールのテスト**: `await_user` は双方向イベント（6.3 節）なので、テストが台本
   （回答リスト）を順に返すことで人間参加ワークフローも無人で検証できる。
   pytest ではイベントへの応答注入、CLI では標準入力のパイプ
   （`printf "発言1\n終了\n" | python MultiRoleStudio.py ...`）を使う

チェックリストとテストの対応（抜粋）：

| チェックリスト項目 | 検証方法（mock 使用） |
|---|---|
| serial / parallel / loop 実行 | イベント列（phase_start / step_start / loop_check）の順序と回数を検証 |
| 会議進行（meeting.json） | moderator → member 並列 → 集約の順でステップが出ること、marker でループが抜けること |
| ロール間会話（max_turns） | ループの反復回数が max_iterations で止まること |
| トークン・コスト集計 | mock の疑似トークン数から session_end の合計が一致すること |
| Markdown ログ | JSONL から生成したレポートに Mermaid ブロックとサマリテーブルが含まれること |
| 温度フォールバック | mock に温度エラーを注入し、温度なしで1回だけ再試行されること |
| ストリーミング | chunk イベントの連結が step_done の全文と一致すること |

Web UI の項目（ファイル添付・設定編集）は Phase 4 実装時に UI テストとして追加する。
それまでは保存関数（`save_config`）とバリデーション（5.2 / 5.3 節）の単体テストで代替する。

---

## 10. サンプルデータ仕様

Phase 3 完了時点で以下のサンプル一式を揃える（旧データからの変換はしない）。
Phase 1 では 1人組織 + 1人材の最小サンプルのみで開始してよい。

### 10.1 人材（3体）

共通の出力規約（文字数制限など）は人材には書かず、組織サンプルの `common_directives` に置く（3.3 節）。

`talents/hinata.json` — ファシリテーター：

```json
{
  "name": "ひなた",
  "personality": "明るく前向き。対立をやわらげ、会話の流れを整える。",
  "system_prompt": "あなたは『ひなた』。議論を前に進め、発言者ごとの主張を取りこぼさない。回答は『要点』『未確定事項』『次アクション』の3見出しで出し、根拠が弱い点は仮説と明記する。",
  "tags": ["facilitator", "warm", "summary"]
}
```

`talents/satsuki.json` — 分析役：

```json
{
  "name": "さつき",
  "personality": "冷静で慎重。データと根拠を重視し、感覚論には必ず確認を入れる。",
  "system_prompt": "あなたは『さつき』。主張には必ず根拠を添え、リスクと不確実性を定量的に指摘する。数値や事実が不明な場合は『要確認』と明記する。",
  "tags": ["analyst", "cautious"]
}
```

`talents/kaede.json` — 技術リード：

```json
{
  "name": "かえで",
  "personality": "実装志向。抽象論を嫌い、常に「どう作るか」に落とし込む。",
  "system_prompt": "あなたは『かえで』。技術的な実現手段・工数感・代替案を必ず提示する。実装リスクが高い提案には代替案を添える。",
  "tags": ["engineer", "pragmatic"]
}
```

### 10.2 ワークフロー（4種）

- `workflows/discussion.json`: 単一スロット `participant`（`"1+"`）。serial 1フェーズ。
  バインディング不要で全組織がそのまま使える最小テンプレート
- `workflows/meeting.json`: `moderator`（`"1"`）+ `member`（`"1+"`）。4.1 節のサンプルそのもの
  （論点提示 → [並列意見 → 集約] × 最大3回、`exit: marker`（【結論】）で早期終了）
- `workflows/quiz.json`: `quizmaster`（`"1"`）+ `answerer`（`"1+"`）。
  出題確認（serial）→ 全員回答（parallel）→ 採点と講評（serial）
- `workflows/dev.json`: `implementer`（`"1+"`）+ `reviewer`（`"1"`）。
  実装（serial）→ [レビュー指摘 → 修正] のループを `exit: judge`（reviewer）で回す。
  成果物抽出（7.5 節）の動作確認を兼ねる開発モードのサンプル

### 10.3 組織・シナリオ・アプリ設定

- `organizations/nokuru/config.json`: 3.3 節のサンプルそのもの
  （キャンプ仲間の組織。mission / culture、3人編成、meeting バインディング、common_directives 付き）
- `organizations/nokuru/model_mapping.example.json`: 3.4 節のサンプルそのもの
- `scenarios/camp_planning.json`: 3.5 節の参照型サンプルそのもの
- `studio_config.example.json`: 3.6 節のサンプルそのもの

このサンプル一式で「バインディングなしで動く discussion」「スロット割当が必要な meeting」
「judge ループと成果物抽出を使う dev」「編成差し替えを行う参照型シナリオ」の4パターンを網羅し、
動作確認とドキュメントの実例を兼ねる。

---

## 11. 未決事項

- Web UI のワークフロー編集はテキストエリア（JSON直書き）で十分か、フォーム化するか
- JSONL ログの長期保管方針（SQLite への移行要否）

---

## 付録A. ゲーム応用の拡張構想（未確定）

1.2 節の通り、ゲームは本システムの上位抽象であり、ゲーム運用は特殊機能ではなく
基盤の自然な使い方である。本付録はその具体的なテンプレート案（内容は未確定）。

シナリオに `state` と `constraints` を追加すると、同じシナリオ定義から
「会議運用」と「分岐型ストーリー（ゲーム）」の両方へ展開しやすくなる。

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

ゲーム用テンプレ（終了条件あり・戦略シム向け）：

```json
{
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

### ゲーム設計者メタロール（構想）

ワークフロー設計はゲームデザインの作業なので（1.2 節）、「ゲーム設計者」を
talents/ の人材として採用し、**ワークフロー定義そのものを設計・生成させる**ことができる。

- ワークフローは JSON データ（4章）なので、LLM の出力として生成可能
- 「この目的・この参加者構成に最適な進行ルールを設計せよ」と依頼し、
  生成された JSON をスキーマ検証（3.7 節）に通してから workflows/ に保存する
- 人間と AI が混在する場の設計（ターン配分・情報の見せ方・テンポ）を
  このロールに担わせれば、システムが自分の進行ルールを自分で改善するメタ構造になる

---

## 付録B. ニュース記事からのシナリオ自動生成（未確定）

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

## 付録C. 外部プラットフォームへの参加（未確定・Phase 9 の具体像）

現在の MultiRoleStudio は「システムが場を提供し、ロールが参加する」形だが、
これを裏返して「AI 人材が外部の場（Teams などの会議・チャット）へ人の代わりに参加する」
使い方へ拡張できる。

| | 場（venue） | 進行の主導権 | AI の立場 |
|---|---|---|---|
| ホスト型（現在） | MultiRoleStudio 自身 | ワークフローエンジン | 招かれた出演者 |
| 参加型（構想） | 外部プラットフォーム | 外部の人間・会議の流れ | 一人の参加者 |

再利用できる部品（そのまま使える）：

1. 人材定義（personality / system_prompt）と組織コンテキスト（mission / culture）
2. プロンプト組み立て（5章）と会話履歴管理・縮約（6.4 節）
3. APIエラーリトライ、コスト集計、セッションログ（JSONL）

参加型で新たに必要になるもの：

1. **発言判断**: ワークフローが順番を決めてくれないため、「今発言すべきか、黙るべきか」を
   判断するロジック（メンション時のみ応答 → 話題が担当領域なら自発発言、と段階導入）
2. **プラットフォームアダプタ**: Teams Bot API 等との接続層。
   CLI / Web と同列の「3つ目の入口」として実装する（6.2 節の構成がそのまま活きる）
3. **アイデンティティと権限**: 発言の帰属（AI であることの明示）、参加範囲の制御

補足：

- ホスト型の human ロール（6.6 節）と参加型は対称の関係にある
  （human ロール = 人がこちらの場に入る / 参加型 = AI が向こうの場に出る）
- Phase 9（連携拡張）で API 契約を固定する際は、この参加型を想定した
  入出力スキーマにしておくと移行しやすい

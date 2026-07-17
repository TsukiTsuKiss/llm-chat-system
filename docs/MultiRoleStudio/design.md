# MultiRoleStudio 設計書

作成日: 2026-06-25 / 最終更新: 2026-07-17（§9.0 Phase 進捗一覧）

本書は MultiRoleStudio の仕様と設計判断をまとめたもの。
確定した仕様（第2〜10章）と、構想段階のアイデア（付録A〜C、付録D の RAG 以降）を明確に分けて記載する。

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
| ユーザーコンテキスト（user_context） | 観客のメモ帳（付録D） | **ユーザー本人**の興味・用語定義・思考の系譜など、セッションをまたいで蓄積する下地。組織 culture や talent とは別レイヤ |

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
| アシスタント定義は JSON を正本とする | `ai_assistants_config.json` のみを読む（接続定義 + UI 用モデル候補。6.5 節）。旧 CSV へのフォールバックは実装しない |
| 検証系を実装前に固定する | 全定義ファイルの JSON Schema（3.7 節）、バリデーションのエラーコード表（5.3 節）、パリティ試験の先行作成（9.3 節）を実装開始前に確定し、機械検証・自動判定できる状態で Phase 1 に入る |
| 同一リポジトリで開発 | 別リポジトリには分離しない。現 `llm-chat-system` に `studio/` 等を追加し、旧コード（MultiRoleChat / Chat）を**参照用に並行維持**する（1.5 節） |

### 1.5 着手前の決定事項（確定）

#### リポジトリ方針

**同一リポジトリ（`llm-chat-system`）のまま開発する。別 repo には分離しない。**

ホワイトボックス開発（旧コードを読みながら `studio/` へコピー移植）と、
パリティ試験・並行運用・完全移行（9.2 節）を同一 workspace で行うため。

```
llm-chat-system/              ← この repo のまま
  studio/                       ← 新規（Phase 1 から）
  schemas/
  tests/parity/
  MultiRoleStudio.py
  MultiRoleChat.py              ← 並行維持（参照用・新機能は追加しない）
  Chat.py
  ai_assistants_config.json     ← 共有
  model_costs.csv               ← 共有
  util/stream_render.py         ← 共有利用可
  web_input_utils.py            ← Phase 4 まで共用可（のち studio/ へ移行検討）
```

#### 旧コードとの関係ルール

| ルール | 内容 |
|---|---|
| import 禁止 | `studio/` から `MultiRoleChat` / `Chat` / `MultiRoleChatWeb` を import しない |
| 共有可能 | `ai_assistants_config.json`, `model_costs.csv`, `util/stream_render.py` |
| 参照方法 | 移植時は旧ファイルを**読んでコピー**する（ホワイトボックス） |
| 旧版の変更 | Phase 5 完了までバグ修正のみ。新機能は Studio 側にのみ追加する |

#### Git 管理（.gitignore 追記対象）

| パス | 理由 |
|---|---|
| `organizations/*/model_mapping.json` | 環境依存（3.4 節） |
| `studio_config.json` | ユーザーローカル（3.6 節） |
| `sessions/` | 実行ログ・不変の証跡（7.1 節） |
| `sandbox/` | 成果物の隔離領域（7.5 節） |
| `user_context/` | ユーザー個人の思考下地（付録D。既定はローカル専用） |
| `user_context/index/` | RAG ベクトル索引（付録D.10。再生成可能） |
| `minutes/` | 議事録（7.3 節）。**運用時は Git 管理**。**開発中は `.gitignore`**（7.3.1 節） |

`minutes/` の Git 方針の詳細は **7.3.1 節**（開発フェーズと運用フェーズの切り替え）。

#### 技術スタック（実装前提）

- Python: 現 repo に合わせる（3.13 対応済み）
- LLM 接続: LangChain（旧版と同様）
- スキーマ検証: `jsonschema`（draft 2020-12）
- テスト: pytest + 予約アシスタント `mock`
- CLI: argparse / Web（Phase 4）: Gradio

#### Phase 1 のスコープ境界

**やる**: `schemas/`（6本）, `tests/parity/`（Phase 1）, `studio/`（loader / errors / history / engine / logging）,
`MultiRoleStudio.py`, 最小サンプル（`organizations/solo/` + 1人材）, `mock` アシスタント

**やらない**: `workflows/` ファイル, mission/culture, parallel/loop/judge, Web UI,
議事録, Git 連携, sandbox 抽出, `minutes/`, `user_context/`（付録D）

### 1.6 プロジェクト・チームの役割（確定）

本プロジェクトは **1人のオーナー + AI アシスタント2種** で進める。
役割を固定し、実装とレビューを分離する。

| 役割 | 担当 | 責務 |
|---|---|---|
| **オーナー** | ユーザー（人間） | 方針判断（採用 / 却下 / Phase 延期）、Phase ゲート、忘れた要件の追記 |
| **設計** | ユーザー + **Composer** | 要件・方針の確定、design.md の正本管理（Composer は起案・追記ドラフト） |
| **実装** | **Composer**（Cursor Agent） | design.md に沿った実装・テスト・縦切り（schemas → parity → `studio/` → CLI） |
| **レビュー** | **GitHub Copilot** | 差分レビュー、design とコードのズレ指摘、第二意見。実装の主担当にはしない |

#### プロジェクトメンバー（記録）

| 表示名 | ID / ツール | モデル（記録時点） | 役割 | 備考 |
|---|---|---|---|---|
| **tsuki-tsuki** | GitHub: `TsukiTsuKiss` | — | 設計責任・最終判断 | 採用 / 却下 / Phase ゲート |
| **Composer** | Cursor Agent | **Composer 2.5** | 設計起案・実装 | 本書（design.md）の執筆支援、Phase 1〜2 実装 |
| **GitHub Copilot** | Copilot（IDE / PR） | **GPT-5.3-Codex** | レビュー | 条件付き合格レビュー、ギャップ指摘 |

- **Composer** は Cursor IDE 上の AI エージェント（本チャットの担当）。表記は `Composer` を正とし、
  文中では「Cursor Agent」と同義で扱う
- **モデル列**は当時の実績記録。ツール側のアップデートで変わるため、Phase 着手時に必要なら更新する
  （後進が「どの組み合わせで Phase 1〜2 を通したか」を追えるようにする）
- 10.4 節のメタサンプル（`studio_dev`）の architect / implementer / reviewer は、
  上記メンバー構成の**架空ロール化**であり、talent 名そのものではない

#### なぜ実装は Composer（Cursor）を主担当にするか

1. design.md を本セッションで段階的に確定してきた**文脈の連続性**がある（細部の判断を毎回説明し直す必要が少ない）
2. Phase 1 は **schemas / parity / loader / engine / logging** の縦一気通貫で、複数ファイルの整合が重要
3. Copilot はファイル単位の提案・レビューは得意だが、**長い設計文脈の保持**は Cursor の方が向く

#### 標準ワークフロー

```
1. オーナー（tsuki-tsuki） … Phase スコープと優先度を指示
2. Composer 2.5   … design.md 通りに実装 + pytest（parity 含む）
3. Copilot（GPT-5.3-Codex） … 差分を design.md と照合レビュー（任意だが Phase 着手前・大きな PR 前は推奨）
4. オーナー       … 指摘の採用/却下、parity 通過で次 Phase へ
```

#### Copilot に向く作業（副担当）

- design.md と実装の**ギャップ洗い出し**（本書の条件付き合格レビュー等）
- 既存 `studio/` の**局所修正**・リファクタ提案
- README / コメント整備

#### Composer に向く作業（主担当）

- Phase 0→1 の**最初の土台**（スキーマ、エンジン骨格、CLI 入口）
- パリティ試験の**先行作成と実装追随**
- design.md 追記（オーナー承認後）

#### 記録ルール

- 設計変更は **design.md を正本**とする（口頭・チャットだけに留めない）
- 思い付き・未確定要件は **11章（未決事項）** に1行メモしてから実装に入る
- git commit は**オーナーが明示したときのみ**（実装担当は勝手に commit しない）
- ツール間の依頼・レビュー・オーナー判断は **`handoff/current.md`**（通信欄）に残す。
  常に最新1枚を上書きし、変遷は Git 履歴で追う（`handoff/README.md` 参照）。
  設計変更そのものは通信欄に書かず design.md へ反映する

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

minutes/                ← 議事録（7.3 節。上書き更新。運用時 Git 管理・開発中 .gitignore → 7.3.1 節）
  nokuru/
    camp_planning.json    ← 正本（機械処理・マージ・再開注入用）
    camp_planning.md      ← 派生（人間閲覧・チャット添付用。JSON から同時生成）

samples/                ← 意図したデモ用会話・議事録（Git 管理。10.5 節）
  sessions/
    nokuru_camp_planning.jsonl
  minutes/
    nokuru/
      camp_planning.json

sandbox/                ← 開発モードの成果物（7.5 節。セッションから抽出したコード。.gitignore）
  session_20260708_120000/

user_context/           ← ユーザー個人の思考下地（付録D。既定 .gitignore）
  my_context.md         ← 興味・用語定義・系譜など（承認式で追記）
  my_context.example.md ← テンプレ（Git 管理可）

studio_config.json      ← UI・実行の既定値（stream / temperature / 並列上限 / user_context。ユーザーローカル・.gitignore）
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
| `organizations/<org>/model_mapping.example.json` | テンプレ（mock 既定） | ✅ commit |
| `organizations/<org>/model_mapping.providers.example.json` | テンプレ（実 LLM・model 付き） | ✅ commit（任意） |

**`model` 文字列の引用元（確定）**: `ai_assistants_config.json` を正本とし、
`ai_assistants_config.csv` の各 `assistant_name` 行の **`model` 列**（JSON では `models` 配列の先頭）を
`model_mapping.json` に書く。例: CSV の `Groq` → `openai/gpt-oss-120b`、`ChatGPT` → `gpt-5.5`、
`Anthropic` → `claude-fable-5`（2026-07-13 時点の CSV 内容）。

`model_mapping.example.json` の例（キーは talent の ID）：

```json
{
  "hinata": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "satsuki": { "assistant": "Groq", "model": "openai/gpt-oss-120b" },
  "kaede": { "assistant": "human" },
  "test_bot": { "assistant": "mock" }
}
```

**予約アシスタント名 `human`**：人材の実体を AI モデルではなく人間（ユーザー）に割り当てる。
`model` フィールドは不要。その人材の発話ステップでは、エンジンがユーザーに入力を求める（6.6 節）。
マッピングを1行変えるだけで「全員AI」と「人間参加」を切り替えられる
（例：普段はAIのかえでを、今日は自分が演じる）。

**予約アシスタント名 `mock`**：テスト用の決定的な疑似モデル（固定応答・コスト0・API 不要）。
パリティ試験（9.3 節）とエンジン単体テストで使う。`model` フィールドは不要。

`mock` の挙動（確定）：

1. 応答本文は `MOCK:{talent_id}:step{step_number}` の決定文字列（`step_number` はセッション内の通し番号）
2. トークン数・コストは 0。ストリーミング時も同文字列を chunk として yield する
3. 環境変数 `STUDIO_MOCK_INJECT_TEMP_ERROR=1` のとき、最初の1回だけ温度非対応エラーを返し、
   2回目以降は通常応答する（温度フォールバックのパリティ試験用）
4. Phase 1 から実装する（パリティ試験の前提）

ユーザーは `.example` をコピーして自分の環境に合わせて書き換える。
**mock テスト用**は `model_mapping.example.json`（`assistant: mock`）、
**実 LLM 用**は `model_mapping.providers.example.json` をコピーし、
`model` は上記 CSV / JSON の `model` 列を引用する。
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

参照型の例（`scenarios/camp_planning.json` と同型 — 編成の一部差し替え + 生成パラメータ）：

```json
{
  "organization": "nokuru",
  "workflow": "meeting",
  "talent_ids": ["hinata", "satsuki"],
  "generation": {
    "temperature": 0.65,
    "top_p": 0.9,
    "seed": 42,
    "variation_profile": "balanced"
  }
}
```

（実ファイル `scenarios/camp_planning.json` は上記のうち `generation` のみ。§10.5 の camp デモは meeting 前提。）

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
  "user_context": {
    "enabled": true,
    "path": "user_context/my_context.md",
    "rag": {
      "enabled": false,
      "corpus_dir": "user_context/corpus",
      "index_dir": "user_context/index",
      "top_k": 5
    }
  },
  "upload_limits": {
    "max_files": 5,
    "max_file_size_kb": 256,
    "max_total_chars": 80000
  }
}
```

`user_context.enabled` の既定値は `true`（ファイルが存在するとき有用）。
**セッション単位で OFF** にしたい場合は Web トグル（**Phase 5d-a**、8.3 節）または CLI `--no-user-context` を使う（付録D）。

temperature の優先順位（上が優先）：

1. シナリオの `generation.temperature`（3.5 節）
2. UI での一時変更（スライダー）
3. `studio_config.json` の既定値

Phase 1（CLI のみ）では CLI からの temperature 上書き（`--temperature` 等）は**提供しない**。
将来追加する場合は **CLI > シナリオ > UI > studio_config** を最優先とする。

stream の優先順位（上が優先）：

1. UI での一時変更（ストリーミング ON/OFF トグル）
2. `studio_config.json` の既定値

シナリオ（3.5 節）から stream を上書きすることはない（演出パラメータは temperature 等のみ）。
セッション開始時点で確定した `stream` / `temperature` は `session_meta.generation` に記録する（7.1 節）。

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
5. `minutes/` の JSON Schema（`minutes.schema.json`）は Phase 5b（議事録化）で追加済み。

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
| `marker` | ループ反復の最終 phase の末尾 step | 各反復で、最終 phase をスロット展開・実行した結果の**末尾1件**の応答に `marker` 文字列が含まれたら終了（判定規則は下記 5） |
| `judge` | 判定専用のスロット（AI） | 各反復の最後に**判定専用ステップ**を追加実行する。`slot` の人材に `criteria`（終了条件）と直近のやり取りを渡し、継続/終了を判定させる |
| `user` | ユーザー（human-in-the-loop） | 各反復の最後にユーザーへ継続/終了を問い合わせる。CLI は y/n 入力、Web は継続/終了ボタン（6.3 節 `await_choice` イベント）。`max_iterations` を省略でき、無限継続をユーザー判断で運用できる |

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
   **パース規則（確定）**: 応答に `【判定】終了` が含まれればループ終了、
   `【判定】継続` が含まれれば継続。どちらも含まれない場合は**継続**（安全側。max_iterations で打ち切る）
3. **終了指示の自動注入**：`marker` 方式でも終了指示を `action` に手書きしない。
   `exit` 定義からエンジンが終了指示文を生成して該当ステップに注入する
   （手書きすると `exit` との二重管理になり、片方だけ変更するとループが黙って壊れるため）
4. `exit` の判定が出なくても `max_iterations` に達したらループを抜ける（`user` 方式を除く）
5. **marker 判定対象（確定）**: 各反復の**最終 phase** 内で、スロット展開後に serial 順で実行した
   step の**末尾1件**の応答全文を判定する（4.3 節の展開規則に従う）。
   最終 phase が `parallel` のワークフローで `exit.type: "marker"` を使う場合は**起動時エラー**
   （E305。marker は serial 最終 step 前提）

### 4.2 ロールバインディング

スロットへの人材割当は組織 config の `workflow_bindings` で行う（3.3 節）。

解決規則：

1. `workflow_bindings.<workflow_id>.<slot>` があればそれを使う
2. バインディング未指定で、ワークフローのスロットが**1種類だけ**の場合、組織の `talent_ids` 全員を割り当てる
   （`discussion.json` のような単一スロットのテンプレートは設定なしで動く）
3. スロットが複数種類あるのにバインディング未指定の場合は**起動時エラー**（実行前バリデーション）
4. `count: "1"` のスロットに複数人材、`count: "1+"` に0人の割当も起動時エラー

### 4.3 フェーズ実行規則

1. `serial`: steps を順番に実行する（文脈の渡し方は下記）
2. `parallel`: steps をスレッド並列で実行する。互いの発言は見えない。全員完了後に次フェーズへ進む
3. `loop`: 内包する `phases` を反復する。各反復の最後に `exit` の終了判定
   （marker 検出 / judge ステップ実行 / ユーザー問い合わせ）を行い、
   終了判定または `max_iterations` 到達でループを抜ける
4. スロット展開: スロットに N 人が割り当てられている場合、そのステップは N ステップに展開される
   （serial では割当順、parallel では同時実行）

**serial フェーズの文脈伝播（確定）**：

- 各人材の会話履歴（history）は**独立**のまま維持する（旧 MultiRoleChat と同様）
- 同一 serial フェーズ内で、後続ステップには先行ステップの応答を
  **user メッセージ末尾**に付加する（history には入れない）：

```
（元の user 入力）

--- 前の発言 ---
{talent_id}: {先行ステップの応答全文}
```

- Phase 1（1人・直接送信）では付加対象がないため、この規則は実質 no-op

### 4.4 直接送信モード（確定）

ワークフロー未指定（CLI: `--workflow` 省略 / Web: 「直接送信：全ロール」）のとき、
`workflows/` のファイルを読まず、以下の疑似ワークフローとして実行する。
Phase 1（1人チャット = Chat.py 相当）の基本形。

```
phases: [
  { "type": "serial", "steps": [ { "slot": "_direct", "action": "" } × talent_ids の人数 ] }
]
```

- スロット `_direct` はワークフロー JSON には書かない。エンジン内部の予約名
- バインディング不要: `talent_ids` の全員を `_direct` に1人ずつ割り当てる
- 各 talent は serial 順に1回ずつ発話（Phase 1 では実質1ステップ）

---

## 5. プロンプト解決とバリデーション仕様

### 5.1 プロンプト組み立て

互換レイヤ廃止により、解決ルールは1本化される。

最終システムプロンプトの組み立て（この順で連結）：

```
1. talent.personality        （あれば）
2. talent.system_prompt      （正本・必須）
3. 組織コンテキスト           （org.mission / org.culture があれば。下記形式で注入）
4. user_context              （付録D。有効時のみ。ユーザーの興味・用語定義・思考系譜）
5. user_context_rag          （付録D.10。有効時のみ。corpus から関連 chunk を検索注入）
6. org.common_directives     （あれば。箇条書きで追記。全員共通）
7. org.role_directives[id]   （あれば。箇条書きで追記。個別）
```

`user_context` / `user_context_rag` の注入は Phase 5d-a / Phase 6 で実装（付録D）。`user_context_rag` は Phase 6 以降。

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
   （`assistant: "human"` / `"mock"` の場合は `model` 不要。それ以外は `assistant` が
   `ai_assistants_config.json` に存在し `model` が指定されていることを検証。
   `mock` / `human` は `ai_assistants_config.json` に登録不要 — エンジンが予約名として処理する）
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
| E204 | model 未指定 | `[E204] model_mapping: 'hinata' の model が未指定です（assistant が human / mock 以外の場合は必須）` |
| E205 | binding の ID が編成外 | `[E205] 組織 'nokuru': workflow_bindings の 'momiji' が talent_ids に含まれていません` |
| E206 | role_directives のキーが編成外 | `[E206] 組織 'nokuru': role_directives の 'momiji' が talent_ids に含まれていません` |
| E207 | workflow 不明 | `[E207] 組織 'nokuru': default_workflow 'meating' が workflows/ にありません` |
| E301 | スロット未バインド | `[E301] workflow 'meeting': スロット 'moderator' への割当がありません（workflow_bindings に追加してください）` |
| E302 | スロット人数違反 | `[E302] workflow 'meeting': スロット 'moderator'（count "1"）に2人が割り当てられています` |
| E303 | max_iterations 欠落 | `[E303] workflow 'meeting': loop に max_iterations がありません（exit.type "user" 以外では必須）` |
| E304 | judge スロット不備 | `[E304] workflow 'review': exit.judge の slot 'reviewer' が slots に宣言されていません` |
| E305 | marker と parallel 衝突 | `[E305] workflow 'meeting': exit.type "marker" ではループ最終 phase を parallel にできません` |
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
| `step_done` | talent_id, assistant, model, 全文, elapsed, tokens, cost, stream | 改行 | 吹き出し確定 |
| `step_error` | talent_id, エラー内容, リトライ状況 | エラー表示 | ❌ 吹き出し |
| `loop_check` | 反復回数, 終了判定の方式と結果（judge の場合は理由も） | 状況表示 | 判定結果の表示 |
| `await_choice` | 問いかけ文, 選択肢（`continue` / `exit`） | `y/n` で入力 | 継続/終了ボタン |
| `await_text` | talent_id, 表示名, action, 役割ブリーフィング | 自由テキスト入力 | テキスト入力欄 |
| `session_done` | コスト集計, 総経過秒, ログパス | サマリ表示 | - |

ログ書き込み（7章）とコスト集計はイベント処理としてエンジン側で共通実行する（表示層の責務にしない）。

**双方向イベント（確定）**: エンジンが一時停止し、表示層が回答を返すまで次へ進まない。
用途ごとにイベントを分ける（1イベント多用途にしない）：

| イベント | 用途 | 表示層が返す値 |
|---|---|---|
| `await_choice` | ループの `exit.type: "user"`（4.1 節） | `"continue"` または `"exit"` |
| `await_text` | human ロールの発話（6.6 節） | 自由テキスト（空文字は再入力を促す） |

**現状（Phase 1〜4）**: 上記2種のみ。AI が自然文でユーザーに質問しても**停止しない**（6.7 節）。

### 6.4 実行時挙動

1. **会話履歴**: 人材ごとに独立した履歴を保持する。上限超過時は `reduce_history` で自動縮約する
2. **ストリーミング**: ON/OFF 切替可能（既定値は `studio_config.json`、優先順位は 3.6 節）。
   parallel フェーズでは API 呼び出しは行うが**表示は完了後一括**（現行 Web 版と同じ）。
   ログには step ごとに `stream`（その step の API がストリーミングだったか）を記録する。
   parallel フェーズの step は `stream: false` 固定（表示一括のため。7.1 節）
3. **temperature**: セッション共通値を適用（優先順位は 3.6 節）。非対応モデルのエラーを検出したら温度指定なしで1回だけ再試行する
4. **APIエラーリトライ**: 413/429/503/504 を検出し、待機付きリトライを行う。リトライ上限超過時は
   `step_error` を発行して次ステップへ進む（セッション全体は止めない）
5. **並列実行の上限**: parallel フェーズの API 同時呼び出し数は `studio_config.json` の
   `max_parallel_calls` で制御する（超過分はキューイング）
6. **応答レンダリング**: LLM 応答の `content` が block 配列（Anthropic 等）の場合、
   `type: "thinking"` / `"redacted_thinking"` のブロックは**表示・ログ・履歴に含めない**。
   `type: "text"` のみをユーザー向け本文とする（旧 ChatWeb.py の `_content_to_text` を
   `studio/` の表示層共通処理として移植）。推論過程の内部テキストがチャット UI に漏れるのを防ぐ

### 6.5 アシスタント接続層

`ai_assistants_config.json` は2層に分かれる：

| 層 | フィールド | 用途 | メンテ |
|---|---|---|---|
| **接続定義** | `module` / `class` | LangChain クラスの特定。**実行に必須** | 手動（新プロバイダ追加時のみ） |
| **モデル候補** | `models`（任意） | Web UI のプルダウン候補。**実行には不要** | **プロバイダごとに手動**（基本方針） |

- 旧 `ai_assistants_config.csv` へのフォールバックは実装しない
  （現状 Chat.py / MultiRoleChat.py の二重実装・不一致を解消する）
- 実行時は `model_mapping.json` の `model` 文字列をそのまま API へ渡す。
  `models` 配列に無いモデル名でも動作する（8.4 節：自由入力可）
- 起動時バリデーション（5.3 節 E203/E204）は `assistant` の存在と `model` フィールドの有無のみ
  （`human` / `mock` は `model` 不要・`ai_assistants_config.json` 登録不要）。
  モデル名の実在確認は API 呼び出し時に委ねる
- 読み込みロジックは `studio/loader.py` へ移植する（旧ファイルへの依存を残さない）
- API キーは従来通り環境変数で管理する

#### モデルカタログのメンテナンス方針（確定）

**基本：プロバイダごとに手動メンテ**

各アシスタントエントリの `models` 配列は、利用者が実際に使うモデルだけを
Git 管理下の `ai_assistants_config.json` に手で書く。
全モデルを網羅する必要はない（プルダウンは候補 + 自由入力）。

**補助：Opper カタログからの同期（Phase 4 以降・任意ツール）**

Opper は `GET /v3/models` で統一カタログ（300+ モデル）を返す。
直接プロバイダ（Groq / Anthropic 等）には一覧 API がバラバラなので、
**Opper を「世の中のモデル一覧」の参照源**として使い、各プロバイダの `models` が
古いときに更新提案する。

```
studio sync-models --from-opper   （CLI。Web UI の「カタログ更新」ボタンでも可）
  1. Opper API で全モデル取得（OPPER_API_KEY 要）
  2. Opper エントリの models[] を Opper 管轄分で更新提案
  3. 各直接プロバイダの models[] と Opper 側を prefix 対応で diff
  4. 追加・退役候補を表示 → ユーザー承認後に ai_assistants_config.json を書き換え
```

ルール：

1. **自動上書きしない**。diff を見せて承認式（破壊的変更を防ぐ）
2. **Opper エントリ**は Opper API からほぼ全件同期可能（`groq/` `anthropic/` 等の Opper 経由 ID）
3. **直接プロバイダ**は Opper の `provider` フィールドでグルーピングし、
   ID の prefix 変換表（例：`groq/llama-3.3-70b-versatile` → Groq 直接の `llama-3.3-70b-versatile`）で対応付ける。
   対応不能な ID は「Opper 専用」として直接プロバイダ側には入れない
4. **`model_costs.csv`** も同コマンドで Opper の pricing 情報から更新**提案**できる（コスト集計用。別ファイルだが同期タイミングを揃える）
5. **実行エンジンは sync 結果に依存しない**。sync は開発者・運用者が config を最新に保つためのツール

Phase 1〜3（CLI のみ）では sync ツールは作らず、手動メンテのみで十分。

### 6.6 人間参加ロール（assistant: human）

model_mapping で `"assistant": "human"` を割り当てた人材は、ユーザーが演じるロールになる。
これにより人間も AI と同じ立場で会議・ワークフローに参加できる。

実行規則：

1. human 人材の発話ステップでは、エンジンが `await_text` イベント（6.3 節）を発行して一時停止する。
   ペイロードには talent_id・表示名・そのステップの `action`・役割ブリーフィング（personality 等）を含める
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

### 6.7 ユーザー割り込み（Phase 5 実装済み）

**背景**: AI 人材が「史書名だけでよいですか？」のように**ユーザーへ問いかける自然文**を出力しても、
エンジンは停止しない（workflow の次フェーズへ進む）。これはバグではなく、
**停止条件が workflow 上の human step / `exit.type: "user"` に限定されている**ため。
（例: `quiz.json` の「回答形式を確認する」指示は、LLM がユーザーへ聞く挙動を誘発しやすい）

**用語（設計メモ）**:

| 概念 | Studio での意味 |
|---|---|
| **サブルーチン** | 一時停止してユーザー入力を受け取るブロック（human step、将来のマーカー割り込み） |
| **コールバック** | 入力を `turn_prior`・各人材履歴に戻し、**中断した workflow を同じ位置から再開**する |
| **割り込み** | 予定外のタイミングでサブルーチンを差し込む（AI 出力の検出により `await_*` を発火） |

**現状でできること（予定サブルーチン）**:

1. `assistant: "human"` の人材 step → `await_text`（6.6 節）
2. ループ `exit.type: "user"` → `await_choice`（4.1 節）
3. workflow JSON に human step を**明示的に挟む**（例: 出題後に `host` human で「確認に答える」）

**Phase 5 以降の拡張案（割り込み + コールバック）**:

AI step の出力に特定マーカーが含まれたら、**その場で**ユーザー入力を求めてから続行する。
`exit.type: "marker"`（4.1 節・`meeting` の【結論】）と同型の機械検出を流用する。

| 方式 | 概要 | 採用 |
|---|---|---|
| **マーカー検出（推奨）** | 例: `【ユーザー確認】` を含む step 全文で `await_text` を発火。workflow に `interrupt_on` マーカー文字列を宣言 | **実装済み**（Phase 5） |
| **自然文・名指し解析** | 「ユーザーさん、〜ですか？」を LLM 出力から推定して停止 | **非推奨**（表現ゆれ・誤検出） |
| **専用 human スロット** | 常に「観客」用 talent（`owner` 等）を workflow に置く | 現状どおり。割り込みの代替ではない |

**実装スケッチ（マーカー方式・案）**:

1. workflow または org `common_directives` に「ユーザーへ聞くときは末尾に `【ユーザー確認】` を付ける」と指示
2. 各 `step_done` 後、直前 step の全文にマーカーがあれば `await_text` を発行（talent_id は予約名 `user` または表示名「あなた」）
3. ユーザーの返答を `user_input` + 仮想 step としてログし、`turn_prior` に追加して**同じフェーズ位置から**再開
4. Web UI は 6.3 節の `await_text` 表示（「あなたへの質問に答えてください」+ 直前 AI 発言の要約）

**Phase との対応**:

- Phase 4: 予定 human / `await_choice` のみ
- Phase 5: マーカー割り込みをエンジン + parity 試験で実装（`studio/interrupt.py`）
- Phase 6: ゲーム（付録A）のプレイヤー選択肢・分岐と組み合わせ可能

**Phase 5 実装フィードバック（2026-07-16）:**

- **宣言**: workflow トップレベル `interrupt_on`（文字列 or 配列）。例: `quiz.json`
- **検出**: 各 `step_done` 後に全文 substring 照合（loop `exit.marker` と同型）
- **停止**: `await_text`（`talent_id: "user"` / 表示名「あなた」、`interrupt: true`）
- **コールバック**: ユーザー返答を `turn_prior` に追加し、同一フェーズの残り step へ継続
- **ログ**: `user_interrupt` 行（`marker` / `prior_speaker` / `prior_text`）
- **バッチ拒否**: `interrupt_on` あり workflow は `--topic` 無人実行不可（E402 系）
- **Web UI**: 直前 AI 発言を案内欄に表示し「質問に答えてください」。ユーザーの返答もチャット履歴に表示する
- **並列フェーズ**: answerer 等の parallel step には serial フェーズまでの `turn_prior` を渡す（他 answerer の出力は含めない）

**クイズ（`quiz.json`）動作確認 — サンプル入力**:

Web UI: 組織 `nokuru`、ワークフロー `quiz`（`workflow_bindings` 済み）。CLI 対話モードでも同様（`--topic` バッチは `interrupt_on` あり workflow では不可）。

| 段階 | 入力例 | 期待される挙動 |
|---|---|---|
| **初回（ユーザー）** | `日本で2番目に面積の大きい都道府県は？` | 出題者（hinata）が問題を提示 |
| **初回（割り込みを誘発）** | `次のクイズ: 光の三原色は何？ 出題前に回答形式を確認して` | 出題者の応答末尾に `【ユーザー確認】` → 一時停止 |
| **割り込み返答（ユーザー）** | `選択肢4択でお願い` / `数字だけで答える形式で` / `自由記述で` | 返答がチャットに表示され、出題確認後に parallel フェーズへ |
| **割り込みなしで完走** | `次のクイズ: 月面着陸の年は？ 形式は自由記述で、そのまま出題して` | マーカーなし → 2名（satsuki, kaede）が並列回答 → 採点 |

**補足**:

- parallel フェーズ中は 2名とも API 完了するまで「考え中」表示が出ない（完了後に一括表示）
- 割り込みは **生成中の停止ではない**。出題者の 1 ターン目が完了し、全文にマーカーが含まれるときだけ発火する

**暫定運用（実装前）**:

- ユーザーへ聞かずに完走させたい → step `action` で「ユーザーへの追加質問はしない」と明示（`quiz` 等）
- 必ず止めたい → human step を workflow に挟む（6.6 節）

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

JSONL の行種別（例）：

```jsonl
{"type": "session_meta", "organization": "nokuru", "workflow": "meeting", "parent_session_id": null, "talents": {"hinata": "ひなた"}, "models": {"hinata": {"assistant": "Opper", "model": "groq/llama-3.3-70b-versatile"}}, "generation": {"stream": true, "temperature": 0.7}}
{"type": "user_input", "text": "...", "attachments": [...]}
{"type": "step", "talent_id": "hinata", "assistant": "Opper", "model": "groq/llama-3.3-70b-versatile", "action": "...", "text": "...", "stream": true, "elapsed": 3.2, "tokens": {"in": 512, "out": 320, "source": "api"}, "cost": 0.0012, "metrics": {"tokens_per_sec": 259.4}}
{"type": "state_snapshot", "state": {"turn": 5, "flags": [...]}}
{"type": "session_end", "total_elapsed": 84.5, "total_cost": 0.031, "by_model": {"Opper/groq/llama-3.3-70b-versatile": {"requests": 12, "elapsed_sum": 48.0, "tokens_in": 6000, "tokens_out": 3200, "cost": 0.031, "stream_on": 8, "stream_off": 4}}}
```

#### 7.1.1 分析用メトリクス（確定）

プロバイダ比較・コスト分析のため、step 行に分析用フィールドを **denormalize** して記録する
（`session_meta` との JOIN なしで集計できるようにする）。

**session_meta.generation**（セッション開始時点で確定した実行条件）：

| フィールド | 内容 |
|---|---|
| `stream` | ストリーミング ON/OFF（3.6 節の優先順位で確定） |
| `temperature` | 適用 temperature（3.6 節の優先順位で確定） |
| `user_context` | ユーザーコンテキストを読み込んだか（付録D。**5d-a 実装済み**） |

プロバイダ横比較では **stream / temperature が異なるセッションを混ぜない**。
分析時は `generation.stream` でフィルタする。

**step 行のフィールド**（LLM step を基準。human / mock は下記「予約 step」）：

| フィールド | LLM step | human / mock step |
|---|---|---|
| `talent_id` | 必須 | 必須 |
| `assistant` | 必須 | `"human"` / `"mock"` |
| `model` | 必須 | **省略**（null 不可・キー自体を書かない） |
| `stream` | 必須 | mock: セッション設定に従う / human: `false` |
| `elapsed` | 必須 | `0` |
| `tokens.in` / `tokens.out` | 必須 | `0` |
| `tokens.source` | `"api"` または `"estimate"` | `"none"` |
| `cost` | 必須 | `0` |
| `metrics.tokens_per_sec` | elapsed > 0 のときのみ（省略可） | **省略** |

`tokens.source` の許容値は **`"api"` / `"estimate"` / `"none"`** の3値（スキーマでも同じ）。

**トークン数の取得優先順位**：

1. LangChain の `response_metadata` / `usage_metadata`（API 実値 → `source: "api"`）
2. 取れなければ文字数推定（`TokenUsageTracker` 移植 → `source: "estimate"`）
3. human / mock → `0`、`source: "none"`

**session_end.by_model**（モデル別ロールアップ）：

step 行を scan しなくてもプロバイダ別サマリが取れるよう、セッション終了時に集計して記録する。
キーは `"<assistant>/<model>"` 形式（human / mock は `"human/"` / `"mock/"` — model なし）。
`stream_on` / `stream_off` は stream 条件別の件数（比較分析用）。
human / mock step は `by_model` 集計から**除外**してよい（コスト・elapsed 分析対象外）。

**elapsed の計測定義**：

| 粒度 | フィールド | 内容 |
|---|---|---|
| step | `elapsed` | 1 回の LLM API 呼び出し時間（プロンプト組み立ては含めない） |
| セッション | `total_elapsed` | wall clock（human 待ち・並列待ち・UI 表示含む） |

ストリーミング ON でも `elapsed` は**最終トークン到着まで**の時間。
体感の速さ（初回トークンまでの TTFT）とは異なるため、分析時は `stream` で条件を揃える。
将来 TTFT が必要になったら `metrics.elapsed_ttft` を追加する（Phase 4 以降・任意）。

**横断分析**：

Phase 8 向けに `studio analyze-sessions --by model [--stream on|off]` で jsonl を集計する CLI を想定する。
**開発セッション単位のコスト表示**（§7.5 開発セッションのコスト表示）も同じ集計基盤を使う。
正本は jsonl のまま。派生 CSV / SQLite は分析ツール側で生成してよい。

### 7.2 途中再開（セッション再開）

MultiRoleChat / MultiRoleChatWeb には薄かった「途中再開」を、MultiRoleStudio では正式機能として持つ。

要件：

1. セッション一覧から過去ログ（jsonl）を選択して再開できる
2. 再開時に会話履歴だけでなく `state`（turn, flags, affinity, inventory など）も復元する
3. 再開後は「続きで上書き」ではなく「分岐保存（branch）」を標準にする。新しい `session_id` を発行し、
   `parent_session_id` を記録する
4. 参照専用モード（読み取り専用リプレイ）と編集モード（再開して続行）を分離する

**state_snapshot の記録タイミング（確定）**：

| タイミング | 内容 |
|---|---|
| 各 **phase 完了時** | エンジン内部 state（会話履歴・反復回数・ゲーム state 等）を JSONL に追記 |
| **session_end 時** | 最終 state を追記（phase 完了時点と同一でもよい） |

毎 step ごとのスナップショットは取らない（ログ肥大を避ける）。
再開時は jsonl 内の**最後の `state_snapshot` 行**を復元点とする。

期待効果：

- 会議: 前回議論の文脈を維持したまま継続できる
- ゲーム: セーブ/ロードに相当する体験が作れる
- 恋愛系の endless モード: 日次セッションを自然に積み上げられる

### 7.3 会議サマリの議事録化（上書き + Git 履歴方式）

要約生成は Chat.py の `create_conversation_summary` を移植した `studio/logging.py` の機能を使う。

記録は役割の異なる三層に分ける：

| 層 | ファイル | 更新方式 | 変遷の追い方 | Git |
|---|---|---|---|---|
| 証跡（生ログ） | `sessions/<id>.jsonl` | 追記のみ・不変 | ファイルがそのまま時系列 | 管理しない（`.gitignore`） |
| 議事録（まとめ） | `minutes/<org>/<テーマ>.json` + `.md` | **常に上書き**（最新だけを保持） | **Git のコミット履歴で見る** | **運用時 Git 管理**（開発中 `.gitignore` → 7.3.1 節） |
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

**二層出力（Phase 5b 追補）:**

| ファイル | 読者 | 用途 |
|---|---|---|
| `.json` | アプリ / LLM | 正本。マージ・schema 検証・再開時の文脈注入（未実装） |
| `.md` | 人間 | JSON から派生。閲覧・チャット添付（`read_attachment_files` と同様にテキスト注入可） |

1回の保存で `.json` と `.md` を同時に書き出す。正本は常に JSON とし、Markdown は再生成可能なビューとする。

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

#### 7.3.1 議事録の Git 管理（開発フェーズと運用フェーズ）

**方針**: エンドユーザー運用では `minutes/` を Git 管理し、上書き保存 + 自動コミットで変遷を
`git log` / `git diff` で追う（7.3 節）。一方、**本リポジトリの Studio 開発中**は
試行錯誤の議事録が混ざるため、**`minutes/` を `.gitignore` に置く**。

| フェーズ | `minutes/` | `samples/` | 備考 |
|---|---|---|---|
| **開発中**（Phase 5 実装〜サンプル整備前） | `.gitignore` | 未整備 or 整備中 | 雑な試験会話はローカルのみ |
| **リリース前**（サンプル確定後） | **`.gitignore` から削除** | Git 管理 | ユーザー運用と同じ Git 連携を有効化 |
| **運用時**（ユーザー環境） | Git 管理 | 参照用デモ（任意） | 議事録保存時に自動コミット（7.6 節） |

**開発中に Git へ載せるもの**（`sessions/` と同様、ランタイム出力ではなく **意図したサンプルのみ**）:

- `samples/sessions/<name>.jsonl` — デモ・parity 試験用の固定会話（10.5 節）
- `samples/minutes/<org>/<topic>.json` — 上記から生成した期待議事録

**リリース時チェックリスト**（対応忘れ防止）:

1. `.gitignore` から `minutes/` の行を**削除**する
2. `samples/` 一式が commit 済みであることを確認する
3. ローカル `minutes/` の試験データを整理する（本番用議事録だけ残す、または空にする）
4. セッションタブ「議事録」の UI メッセージは **保存成功のみ**表示（Git 詳細は出さない）

**UI メッセージ**: 運用時、ユーザーに Git の成否（dirty tree 等）は見せない。
保存は常に行い、コミットは作業ツリーがクリーンなときだけ裏で実行する。

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

**開発セッションのコスト表示（構想・Phase 8）:**

`dev` ワークフロー等でプログラムを生成したとき、jsonl に既に記録されている
`elapsed` / `tokens` / `cost`（`model_costs.csv` 連携）から**その成果物の製造コスト**を
算出・表示する。実装データは揃っており、集計と UI 配線が主な作業になる。

想定する表示タイミングと内容：

1. **セッション終了時**（CLI `session_done` / Web チャット）— 総コスト・総経過秒・トークン in/out
2. **セッションタブの Markdown レポート**（§8.5）— モデル別内訳表（`session_end.by_model`）
3. **成果物採用時**（§7.6）— 採用成功メッセージにコストサマリを併記（任意でコミットメッセージにも追記）
4. **sandbox 派生** — `sandbox/session_<id>/cost_summary.json`（任意）で機械可読に保存

集計ルール（案）：

- 正本は `sessions/<id>.jsonl` の `step` / `session_end` 行。再計算可能
- human / mock step はコスト集計から除外（既存ルールと同じ）
- ループ反復ごとのコスト内訳（implement / review / judge 各フェーズ）も出せる
- 横断分析 CLI（下記 §7.1 横断分析）と共用の集計関数を `studio/logging.py` または `studio/analyze.py` に置く

### 7.6 Git 連携（成果物の採用とコミット）

sandbox の成果物を作業ツリーへ反映する「採用（apply）」操作に Git コミットを結びつける。
AI の変更が常に1コミット=1セッションの粒度で履歴に残り、レビューとロールバックが容易になる
（Aider などの AI コードツールと同じ「コミットで守る」思想）。

仕様：

1. **採用はユーザーの明示操作**（CLI: `--apply <session_id>` / Web: セッションタブの「成果物採用」ボタン）。
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

### 7.8 Zenn 草稿生成（Phase 6 以降・後回し）

旧 `ChatWeb.py` の Zenn 対応を Studio に取り込む構想。**Phase 4 では実装しない**。

要件（案）：

1. チャット入力または専用ボタンで「Zenn 草稿生成」を起動する
2. セッション jsonl（または in-memory 履歴）を入力に、Zenn 記事向けプロンプトで LLM 要約する
3. 出力は Markdown 草稿（見出し・本文・`[[keyword]]` / `#tag` 等。旧 `summaries/` の Foam 形式を参考）
4. 保存先は `drafts/zenn/<topic>.md` 等（Git 管理するかは未決。`minutes/` とは別系統）
5. 生成結果は**会話履歴に含めない**（旧 ChatWeb と同様。トークン節約）
6. 7.3 節の構造化議事録（`minutes/*.json`）とは用途が異なる（議事録 = 決定事項、Zenn = 執筆草稿）

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

Gradio 起動・終了の共通仕様（8.6 節）に従う。

### 8.3 チャットタブ

現行 MultiRoleChatWeb の機能を踏襲する：

1. 左ペイン: 組織選択 / ワークフロー選択（「直接送信：全ロール」を先頭に含む）/
   ファイル添付（テキスト系の取り込み）/ ストリーミング ON/OFF / Temperature スライダー /
   人材一覧表示 / **新規チャット**（旧「履歴クリア」に相当）
   ※ **ユーザーコンテキスト ON/OFF トグル**（付録D。Phase 5d-a 実装済み）
2. ストリーミング・Temperature の初期値は `studio_config.json` から取得する（3.6 節）
3. 右ペイン: 単一スレッドのチャット表示。人材ごとに識別ラベル（色絵文字など。表示層の実装詳細とし仕様では定めない）を付ける
4. 人数上限は設けない。並列 API 呼び出しの同時数は `max_parallel_calls` で制御する（6.4 節）
   （旧 MAX_ROLES = 16 は複数 Component 時代の名残であり、単一スレッド表示では不要）
5. ストリーミング・並列実行の表示挙動は 6.3 節のイベント対応表に従う
6. 人間参加ロール（6.6 節）の入力要求時は、メッセージ入力欄を「〇〇（あなたの役）として発言してください」
   モードに切り替え、役割ブリーフィングとステップ指示を表示する
7. **新規チャット**: 表示中の会話をクリアし、**新しい `session_id` で新規 jsonl を開始**する
   （他チャットアプリの「新規会話」と同じ。旧 jsonl への上書き追記はしない）
8. **送信後アップロード自動クリア**: メッセージ送信完了後、ファイル添付コンポーネントを空にする
   （旧 ChatWeb.py 踏襲）
9. **空メッセージ + ファイルのみ**: テキスト未入力でファイルだけ添付された場合、
   自動的に「添付ファイルの内容を要約してください。」を user 入力として扱う
   （旧 MultiRoleChatWeb.py 踏襲）
10. **API キー未設定の assistant**: `model_mapping` 編集時、E401 該当 assistant は
    プルダウンで選択不可（グレーアウト + 理由表示。旧 ChatWeb.py 踏襲）
11. **thinking ブロック非表示**: 6.4 節。推論モデル（Claude extended thinking 等）の
    「考え中」内部テキストは UI に表示しない
12. **ワークフロー未設定の案内**（Phase 4e 追補）: 組織で実行不可な workflow はプルダウンに
    ` — 未設定` 付きで表示する。選択時は有効な workflow に戻し、プルダウン直下の案内欄に
    `workflow_bindings` 追加方法と設定済み組織名を表示する（E401 の assistant 選択不可と同系統の「選べない理由を見せる」UX）

**Phase 4a/4b 実装フィードバック（2026-07-14）:**

- **状態欄**: 1 ターン（ワークフロー 1 周）完了後は **「待機中（メッセージを入力してください）」** を表示する。
  `loop_check` 等の最終イベント後に「実行中…」が残ると、処理完了と誤認される（4b で修正）
- **続行 / 終了ボタン**: `await_choice`（`exit.type: "user"` のワークフロー）のときのみ表示。
  `meeting` 等の marker 終了では **出ない**（design どおり）
- **チャット欄の高さ**: 初回表示で **メッセージ欄・送信ボタンが viewport 内** に収まるよう、Chatbot の初期高さを
  `clamp(200px, calc(100dvh - 22rem), 480px)` 程度に抑える（`resizable=True` で拡大可）
- **連続メッセージ**: Gradio 6 の `group_consecutive_messages` デフォルト **OFF** + トグル（同一 talent の連続発話を 1 吹き出しにまとめない）
- **メッセージ欄キー操作**: `lines=1` + `max_lines=6` — **Enter で送信**、**Shift+Enter で改行**（Gemini / ChatWeb / VS Code チャット慣習。`lines≥2` だと Gradio 既定で Enter=改行になる）
- **強制停止**: Web UI にキャンセルボタンは **未実装**（Phase 4 スコープ外）。当面は新規チャット / サーバー `q` 終了

**Phase 4c 実装フィードバック（2026-07-14）:**

- **ファイル添付**: 左ペインに `gr.File`（`type="filepath"`, 複数可）。CLI と同じ `read_attachment_files` + `studio_config.json` の `upload_limits` を使用
- **送信後クリア**: 送信受理時（ユーザー吹き出し追加直後）にアップロード欄を空にする（旧 ChatWeb 踏襲）
- **ファイルのみ送信**: テキスト未入力時は「添付ファイルの内容を要約してください。」を user 入力として扱う
- **表示**: チャット上の user 吹き出しに `📎 添付: ファイル名` を付与。JSONL の `user_input.attachments` にも記録

**Phase 4d 実装フィードバック（2026-07-14）:**

- **model_mapping フォーム**: JSON テキスト欄を廃止し、人材プール全員分の **静的行**（`gr.Group` + `visible` 切替）で assistant / model を編集
- **E401 UI**: API キー未設定 assistant はプルダウンに `(APIキー未設定)` ラベルで表示し、選択時は **前の値に戻す** + 理由を `org_mapping_note` に表示（旧 ChatWeb 踏襲）
- **model**: `ai_assistants_config.json` の候補 + `allow_custom_value` で自由入力
- **talent_ids 連動**: チェック変更時に mapping state をマージ（新規 talent は `mock` 既定）。`input` → `then` の2段イベントで行表示を更新（初回チェック取りこぼし防止）
- **表示順**: talent_ids チェックボックス（人材プール一覧）と同じ順。`alpha` は一覧先頭なら mapping も先頭
- **組織切替**: `@gr.render` は使わない（行数変動で Gradio `fn_index` 不一致になるため）
- **保存ボタン**: model_mapping フォームの**下**に配置

**Phase 4e 実装フィードバック（2026-07-14）:**

- **セッション一覧**: `sessions/*.jsonl` を新しい順。`session_meta` から組織・ワークフロー・日時を Dropdown ラベルに表示
- **Markdown レポート**: jsonl からその場生成（Mermaid フロー + 応答時間表 + 会話ログ）。ファイルとしては保存しない
- **フロー図テーマ**: ライト / ダーク切替（Mermaid `themeVariables` + CSS フォールバック）。既定はダーク
- **エクスポート**: `sessions/exports/<session_id>.md` に出力（`.gitignore` 対象）
- **Phase 5 ボタン**: 再開・議事録（5a/5b 実装済み）、成果物採用（5c 実装済み）
- **parallel フロー図**: JSONL の `step_metrics.phase_type`（`serial` / `parallel`）に基づき Mermaid で fork/sync 表示。
  Phase 4e 以前の jsonl には `phase_type` が無く serial 直列表示になる

**Phase 4e 追補 — チャットタブ workflow UX（2026-07-14）:**

- **組織連動プルダウン**: 組織変更時、ワークフロー選択肢を `load_session_context` 相当の検証結果で更新する。
  「直接送信（全ロール）」は常に先頭。単一スロット workflow（例: `discussion`）は `workflow_bindings` 省略可（4.2 節の自動割当）
- **未設定ラベル**: 当該組織で実行不可な workflow は **非表示にせず**、ラベル末尾に ` — 未設定` を付ける
  （例: `quiz — 未設定`）。複数スロット workflow で `workflow_bindings` 未登録の場合が該当
- **案内欄**: ワークフロープルダウン直下に `wf_note_md` を置く。未設定 workflow を選んだとき、
  選択は直前の有効値に戻し、案内欄に理由を**残す**（`workflow_bindings` 追加を促す。
  他組織に設定済みなら `設定済みの組織: trio` 等を列挙）。組織変更・別 workflow 選択でクリア
- **フォールバック**: 組織変更で現選択が無効になった場合、`default_workflow` → なければ「直接送信」へ
- **参加人材欄のエラー**: 読み込み失敗時、汎用「model_mapping 等」ではなく E301 等の**検証メッセージ全文**を表示
- **設定タブ連動**: 組織 config / model_mapping / workflow 保存時もチャット側プルダウンを組織向けに再計算

**Phase 4f 追補 — workflow_bindings フォーム（2026-07-16）:**

- **§8.4 完了**: 組織タブの `workflow_bindings` を JSON テキストからフォームへ置換。
  `count: "1"` はラジオ（単一選択）、`count: "1+"` はチェックボックス（複数選択）。
  選択肢は `talent_ids` チェックボックスと連動
- **保存**: フォーム変更だけではチャットに反映されない。**「組織 config を保存」** で
  `organizations/<id>/config.json` に書き込む（`model_mapping を保存` とは別）
- **レイアウト**: スロット割当フォームは **保存ボタンより上** に配置（保存忘れ防止）
- **実装**: `studio/bindings_form.py` + `tests/parity/test_bindings_form.py`

**Phase 5a 実装フィードバック（2026-07-14）:**

- **再開**: 選択セッションの履歴をチャットタブへ再現し、続きは分岐 jsonl（`parent_session_id`）として保存
- **UX**: 操作メッセージはボタン行直下。エクスポート結果ファイル欄は成功時のみ `visible=True`
- **再開後チャット**: チャットタブへ自動切替し、履歴の**最下行**（再開案内付近）を表示（JS）

**Phase 5a 追補 — 再開 UX・Gradio イベント（2026-07-15）:**

- **タブ横断の inputs 罠**: セッションタブの「再開」にチャットタブの `stream_cb` / `temp_sl` / `user_context_cb` を
  `inputs` に含めると、**非表示タブの値は `None`** になり Python 側で例外または不正な既定値になる。
  再開の `inputs` は **`session_dd` + `WebSession`（`gr.State`）のみ**とし、
  ストリーミング / Temperature / user_context は `WebSession` に保持する（コントロール変更時に `sync_chat_prefs` で同期）
- **JS の実行タイミング**: Gradio の `js` は **Python `fn` より先**に実行される（8.6 節）。
  再開で「先にチャットタブへ切替 → 後から chatbot 更新」とすると、**更新前の空履歴が表示されたまま**になる。
  タブ切替・最下行スクロールは **`resume_btn.click(...).then(fn=None, js=...)`** で Python 完了後に実行する
- **chatbot 出力**: 再開時は `gr.update(value=messages)` で明示更新（他 output が `gr.update` のときの不整合を避ける）
- **リプレイ生成**: `build_replay_messages` の絵文字定数は `studio/display.py` の `SPEAKER_EMOJIS` を参照
  （`session_resume` が `web_ui` 経由で `gradio` を import しないよう分離。parity 試験で確認）

**Phase 5b 実装フィードバック（2026-07-14）:**

- **議事録**: jsonl から構造化 JSON を生成し `minutes/<org>/<topic>.json` へ上書き（mock / LLM）
- **Markdown 派生**: 同一保存で `.md` を同時出力（`document_to_markdown`）。人間閲覧・添付用
- **Git**: 保存後に自動コミット（dirty tree 時は保存のみ）。UI には Git 詳細を出さない（7.3.1 節）
- **開発中 `.gitignore`**: `minutes/` はローカルのみ。リリース前に解除（7.3.1 節）。サンプルは `samples/`（10.5 節）
- **ボタンラベル**: `議事録 (.json + .md)` / `エクスポート (.md)` / `成果物採用`
- **トピック**: 常時入力欄は置かず、最初の user 入力からファイル名 slug を自動生成

**Phase 5c 実装フィードバック（2026-07-15）:**

- **成果物採用**: `sandbox/session_<id>/` → 作業ツリーへコピー + Git 1コミット（プッシュなし）
- **dirty tree**: 採用**前**に未コミット変更があれば全体中断（議事録とは異なり excluding なし）
- **sandbox 未作成時**: jsonl から再抽出してから適用
- **除外**: `run_all.sh` は sandbox 検証用のため作業ツリーへコピーしない
- **CLI**: `--apply <session_id>` / 任意 `--apply-branch`（`studio/<session_id>`）
- **UI**: Git 成否は message に載せない（議事録と同型）

**Phase 5d-a 実装フィードバック（2026-07-15）:**

- **user_context**: `my_context.md` 読込 → §5.1 組織コンテキスト直後に注入
- **ON/OFF**: `studio_config.user_context.enabled` / Web トグル / CLI `--no-user-context`
- **記録**: `session_meta.generation.user_context` に true/false
- **テンプレ**: `user_context/my_context.example.md`（Git 管理、`my_context.md` は .gitignore）

**Phase 5d-b 実装フィードバック（2026-07-15）:**

- **更新案**: セッション jsonl から `user_context/drafts/<session_id>.md` を生成（mock / LLM）
- **採用**: `## 提案追記` の箇条書きを `my_context.md` の `## 蓄積メモ` 末尾へ追記（承認式。自動マージなし）
- **CLI**: `--user-context-draft` / `--user-context-apply` / `--user-context-summarize`
- **Web**: セッションタブ「コンテキスト更新案」「コンテキスト採用」（プレビューは `session_msg` に Markdown 表示）
- **要約（D.8）**: `studio_config.user_context.max_chars` 超過時は `my_context.summary.md` を注入（無ければ先頭 truncate + 案内）
- **未実装**: RAG（D.10 / Phase 6）、要約の Web 専用ボタン（CLI のみ。必要なら追補可）

**Phase 5d-b 追補（2026-07-15）:**

- **スキーマ**: `studio_config.user_context.max_chars` を `schemas/studio_config.schema.json` に追加（E102 回避）
- **パス**: `root.resolve()` で draft 相対パス表示（CLI `--root .` でも動作）
- **UI 文言**: ボタンは「コンテキスト更新案 / 採用」、メッセージは「ユーザーコンテキスト〜」（「下地」は設計本文の比喩のみ）

**Phase 5 Web UX 追補（2026-07-15）:**

- **`--org` 優先順位**: CLI `--org` > `studio_config.default_org` > 環境変数。`--org nokuru` が `default_org: solo` より優先される
- **セッション小窓**: 固定 `max-height` 式はボタン行追加で破綻するため、`#studio-session-panel` を flex 縦積み +
  `height: calc(100dvh - 9rem - 30px)`、小窓のみ `flex:1` + 内部スクロール（操作ボタン 2 行は常時表示）

新データ構造（3章）に対応した編集画面にする。旧構造（demo_roles / system_prompt_file）の編集 UI は作らない。
**人材・組織・ワークフローの新規作成・編集・削除**を Web から行える（旧 MultiRoleChatWeb の
ロール CRUD を新方式 `talents/` + 組織 config + `workflows/` に置き換える）。

```
左ペイン: 編集対象の選択
  [👤 人材（talents/）]
  [🏢 組織（organizations/）]
  [🔄 ワークフロー（workflows/）]
右ペイン: 選択対象のエディタ
  [➕ 新規作成]  [🗑 削除]  （種別ごと）
```

1. **人材編集（talents/）**: 一覧 + **新規作成**（`talents/<id>.json`）/ 削除 +
   詳細フォーム（id / name / personality / tags）+ システムプロンプト本文（テキストエリア）。
   id はファイル名と一致（3.1 節）
2. **組織編集（organizations/）**: 一覧 + **新規作成**（`organizations/<id>/` + config.json +
   `model_mapping.example.json`）/ 削除 + name / mission / culture の編集 /
   talent_ids の選択（人材プールからチェックボックス）/ workflow_bindings のスロット割当 /
   common_directives / role_directives の編集 / model_mapping の編集
   （assistant はプルダウン、model は候補選択 + 自由入力。候補は `ai_assistants_config.json` の手動リスト。
   Phase 4 以降は Opper 同期ツールでリスト更新可 — 6.5 節）
3. **ワークフロー編集（workflows/）**: 一覧 + **新規作成**（`workflows/<id>.json`）/ 削除 +
   JSON テキストエリア（当面）。保存時に 4.2 節のバリデーションを実行
4. 保存時は 5章のバリデーションを通し、エラーは保存前に警告表示する
5. 保存関数は `save_config(kind, id, data)` の形に抽象化し、構造変更時に UI を触らずに済むようにする

**Phase 4b 実装フィードバック（2026-07-14）:**

- **レイアウト**: 8.4 の「左ペイン / 右ペイン」図は、実装では **タブ内サブタブ**（👤 人材 / 🏢 組織 / 🔄 ワークフロー）+ フォームに置き換えた（Gradio の `Tabs` 構成の方が CRUD 操作と整合しやすい）
- **ID 操作 UI**: 「編集対象 ID」（Dropdown）と「新規 ID」（Textbox）を **分離** する。同一フィールドに兼用しない（`allow_custom_value` だけでは初見ユーザーが混乱する）
- **ボタン配置**: 各サブタブ先頭を **2 グループ** にする — `[既存 ID ▼] [削除]` / `[新規 ID] [新規作成]`。削除・新規作成ボタンは入力欄の **下端に揃え**、`equal_height` でラベルまで伸ばさない（Soft テーマの項目名チップとボタンが混同される）
- **保存**: フォーム下部の **保存** は primary。設定タブ内の削除・新規作成も同系統の操作ボタンとして扱う（Phase 4b では CSS `--button-*` で全 Web 共通色を上書き。項目ラベルは Soft テーマの紫チップのまま）

### 8.5 セッションタブ

1. `sessions/` の一覧表示（新しい順。各 jsonl の `session_meta` から組織・ワークフロー・日時を表示）
2. 選択セッションの Markdown レポートを jsonl からその場で生成して閲覧（7.1 節。ファイルとしては保存しない）
3. 「再開」ボタン: 選択セッションの `state_snapshot` を復元し、分岐セッションとして続行（7.2 節。Phase 5a）
4. 「議事録 (.json + .md)」ボタン: JSON 正本 + Markdown 派生を `minutes/` へ同時上書き（7.3 節。Phase 5b）
5. 「エクスポート (.md)」ボタン: Markdown レポートを `sessions/exports/` へファイル出力
6. 「成果物採用」ボタン: sandbox の成果物を作業ツリーへ適用し、コミットを作成する（7.6 節。Phase 5c）
7. 操作メッセージはボタン行直下。エクスポート結果ファイル欄は成功時のみ表示
8. **レポート閲覧 UX**: 長い Markdown レポートは内部スクロールの小窓（`#studio-session-panel` を `height: calc(100dvh - 9rem - 30px)` の flex 縦積み、小窓は `flex:1` で残り全高）。操作ボタンは小窓の下に固定（2 行）
9. **再開 UX**: 「再開」後は **Python で chatbot を更新したあと**、チャットタブへ切替え、
   チャット欄を最下行までスクロール（`.then(fn=None, js=...)`。§8.3 Phase 5a 追補）
10. **ユーザーコンテキスト更新（5d-b）**: 「コンテキスト更新案」で `user_context/drafts/<session_id>.md` を生成・プレビュー。
    「コンテキスト採用」で `my_context.md` の蓄積メモへ追記（付録D.7）

### 8.6 Web 共通（Gradio 起動・UX）

Phase 4 で Gradio Web 版に共通して適用する。

| 項目 | 内容 | Phase |
|---|---|---|
| **ユーザー割り込み** | workflow `interrupt_on` マーカーで step 後 `await_text`（§6.7） | 5e |
| **`q` + Enter 終了** | `prevent_thread_lock` + 入力待ち。コンソールで `q` 入力でサーバ停止（旧 ChatWeb.py 踏襲） | 4 |
| **Gradio フッター非表示** | `footer { display: none !important; }` を CSS 注入（旧 MultiRoleChatWeb.py 踏襲） | 4 |
| **`--port` / `--share`** | 起動引数・環境変数でポート指定・Gradio 公開トンネル（旧 Web 版踏襲） | 4 |
| **Soft テーマ** | Gradio テーマ（任意。旧 ChatWeb.py 踏襲） | 4 |
| **操作ボタン色** | CSS 変数 `--button-primary-*` / `--button-secondary-*` で全タブの primary ボタンを統一（Phase 4b: 水色。項目ラベルは Soft テーマの紫チップのまま） | 4b |
| **日本語ページ・翻訳バー抑制** | Gradio 6 の HTML テンプレートは `<html lang="en">` 固定。`launch(head=…)` や JS だけでは view-source / Edge 翻訳バーに効かない。**`templates/gradio/frontend/index.html`（`lang="ja"` + `notranslate`）を Jinja2 ChoiceLoader で優先**（`studio/gradio_template.py`）。Gradio バージョンアップ時は asset ハッシュ要確認 | 4b |
| **イベント JS の順序** | `click(..., js=...)` の `js` は **Python `fn` より先**に実行される。タブ切替・スクロール等「更新後にやりたい」クライアント処理は **`.then(fn=None, js=...)`** で後段に置く（Phase 5a 再開で実証） | 5a |
| **起動時 `--org`** | `MultiRoleStudioWeb.py --org <id>` は `studio_config.default_org` より優先（8.3 節） | 5 |

**補足（Gradio 6 / Soft テーマ）:**

- 項目名（`block_title`）は **紫背景のチップ** 表示がデフォルト。ボタンと混同しやすいため、操作ボタンは別色（上表）で区別する
- `head=` パラメータの HTML は **サーバー HTML に埋め込まれず**、`gradio_config` 経由のクライアント注入。言語属性の変更にはテンプレート差し替えが必要

### 8.7 ChatWeb 由来機能（後回し）

旧 `ChatWeb.py` にあって Studio 本体とは別系統の機能。**Phase 4 では実装しない**。

| 機能 | 内容 | Phase |
|---|---|---|
| **Zenn 草稿生成** | 会話を Zenn 記事向けプロンプトで要約し Markdown 草稿を出力 | **6 以降**（7.8 節） |
| **チャット内自然言語要約** | 「まとめて」等の入力で LLM 要約（Foam 形式 `[[keyword]]` / `#tag`） | 6 以降 or 7.3 議事録で代替 |
| **CSV ログ再開（同一ファイル追記）** | 旧 `logs/*.csv` 形式 | **実装しない**（7.1 JSONL + 7.2 分岐再開） |
| **まとめ読込 2モード** | system 追記 / 履歴注入 | Phase 5 再開文脈（7.2 / 7.3）で代替検討 |

---

## 9. ロードマップと移行方針

### 9.0 Phase 進捗一覧（正本）

**ここを見れば「今どこまで終わっているか」が分かる。** README の Phase 行は本表への要約リンク。
状態の凡例: ✅ 完了 · 🔶 一部 / 任意残 · ⬜ 未着手

| Phase | 名称 | 状態 | 概要 |
|---|---|---|---|
| **1** | 1人 CLI | ✅ | `studio/` + `MultiRoleStudio.py`、mock、JSONL ログ、parity |
| **2** | 複数人 | ✅ | serial / parallel、`discussion` / `quiz`、`human` |
| **3** | 進行制御 | ✅ | loop + exit、`meeting` / `dev`、sandbox 成果物抽出 |
| **4a** | Web チャット | ✅ | `MultiRoleStudioWeb.py` チャットタブ |
| **4b** | 設定編集 | ✅ | 人材・組織・workflow CRUD、バリデーション |
| **4c** | ファイル添付 | ✅ | Web + CLI `--files`、`upload_limits` |
| **4d** | model_mapping フォーム | ✅ | assistant / model プルダウン、キー未設定は選択不可 |
| **4e** | セッションタブ | ✅ | 一覧、Markdown レポート、エクスポート、Mermaid |
| **4e 追補** | workflow UX | ✅ | 組織連動プルダウン、`— 未設定` ラベル、案内欄 |
| **4f 追補** | workflow_bindings フォーム | ✅ | 組織タブのスロット割当 UI（§8.4） |
| **5a** | セッション再開 | ✅ | 分岐 jsonl、`parent_session_id`、チャット履歴再現 |
| **5b** | 議事録 | ✅ | jsonl → `minutes/`（JSON + MD）。開発中は `.gitignore` |
| **5c** | 成果物採用 | ✅ | sandbox → 作業ツリー + Git 1 コミット（§7.6） |
| **5d-a** | user_context 注入 | ✅ | `my_context.md`、Web トグル / `--no-user-context` |
| **5d-b** | user_context 更新 | ✅ | 更新案生成・採用・要約（CLI / Web） |
| **5e** | ユーザー割り込み | ✅ | `interrupt_on` → `await_text`（§6.7）、`quiz.json` |
| **5e 追補** | 割り込み・クイズ UX | ✅ | parallel `turn_prior`、返答のチャット表示、設定タブ同期 |
| **5f** | サンプル整備 | ✅ | `samples/` 固定 jsonl + 議事録（§10.5） |
| **5g** | 旧版移行 | ⬜ | MultiRoleChat / Chat → `legacy/`、README 差替（§9.2） |
| **5h** | studio_dev メタサンプル | ⬜ | 自己改善開発チーム（§10.4・任意） |
| **—** | Web 生成中キャンセル | ⬜ | 強制停止ボタン（§8.3。Phase 4 スコープ外として延期） |
| **—** | sync-models CLI | 🔶 | Opper カタログ同期（§6.5・任意・未実装） |
| **6** | 生成連携 | ⬜ | TTS / ナレーション、Zenn 草稿（§7.8）、user_context RAG（付録D.10） |
| **7** | 考査支援 | ⬜ | 映像・音声・字幕のコンプラチェック |
| **8** | 運用基盤 | ⬜ | 品質・遅延・コスト監視、`analyze-sessions`、dev セッションコスト表示 |
| **9** | 連携拡張 | ⬜ | 外部ベンダー API 契約固定（付録C） |

**現在の位置**: Phase **5** コアは完了。**残りは 5g（移行）と 5h（任意）**。Phase 6 以降は未着手。

**通信欄**: 直近の作業メモは [handoff/current.md](../../handoff/current.md)。

### 9.1 段階導入ロードマップ

実装は歴史（Chat.py → MultiRoleChat.py）をなぞり、**1人 → 複数人 → 進行制御**の順で進める。
各 Phase を「動く道具」として完成させてから次へ進む。
着手前に JSON Schema（3.7 節）とパリティ試験（9.3 節）を先に作成する。

コア構築フェーズ：

1. **Phase 1（1人チャット = Chat.py 相当）**: `studio/` パッケージ + CLI 版の最小形。
   1人組織 + 直接送信（4.4 節）。新データ構造（3章）の loader（talents / 組織 / model_mapping /
   studio_config + スキーマ検証・エラー表）、エンジン最小形（直接送信 + serial 1ステップ・
   イベント yield・ストリーミング）、ロール別履歴 + 縮約、APIエラーリトライ、JSONL ログ、
   CLI（バッチ実行含む）、予約アシスタント `mock`（パリティ試験用）。
   **データ→プロンプト組み立て→実行→ログの縦一気通貫**を最小構成で検証する
2. **Phase 2（複数人 = MultiRoleChat 相当）**: スロット展開と serial / parallel、
   組織コンテキスト（mission / culture）、`discussion.json` / `quiz.json`、
   予約アシスタント `human`
3. **Phase 3（進行制御 = Studio 固有）**: loop + `exit`（marker / judge / user）、
   `meeting.json` / `dev.json`、成果物抽出（7.5 節）。サンプルデータ一式（10章）を揃える
4. **Phase 4（Web UI）**: Web 版（チャットタブ + 設定編集タブ + セッションタブ）。
   新規作成 UI（8.4 節）、Gradio 共通 UX（8.6 節）、ChatWeb 由来機能のうち Phase 4 分。
   モデルカタログ同期 CLI（`studio sync-models --from-opper`）を任意で同梱。
   **user_context は Phase 5d-a/b 実装済み**（付録D。RAG は Phase 6）
5. **Phase 5（運用機能）**: セッション再開（分岐保存・**5a 実装済み**）、議事録化（7.3 節・**5b 実装済み**）、
   Git 連携・成果物採用（7.6 節・**5c 実装済み**）、   **ユーザーコンテキスト**（付録D・**5d-a/b 実装済み**）、
   **ユーザー割り込み**（6.7 節・マーカー方式・**実装済み**）、
   旧版からの完全移行完了（9.2 節）。**workflow_bindings フォーム（§8.4）は実装済み**（Phase 4f 追補）

業務適用拡張フェーズ：

6. **Phase 6（生成連携）**: 会話出力から TTS / ナレーション原稿 / ショット指示を生成。
   **Zenn 草稿生成**（7.8 節）、**user_context RAG**（付録D.10）もここで検討
7. **Phase 7（考査支援）**: 映像・音声・字幕の自動コンプラチェック用ルール評価を追加
8. **Phase 8（運用基盤）**: 評価指標（品質・遅延・コスト）と MLOps 向け監視を追加。
   **開発セッションのコスト表示**（§7.5）— 成果物生成時に時間・トークン・USD をサマリ表示、
   セッションレポート・採用 UI・`analyze-sessions` CLI と連携
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
- [x] ファイル添付の取り込み（Web）
- [x] 組織・ワークフローの Web 編集

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
5. **human ロールのテスト**: `await_text` / `await_choice` は双方向イベント（6.3 節）なので、
   テストが台本（回答リスト）を順に返すことで人間参加ワークフローも無人で検証できる。
   pytest ではイベントへの応答注入、CLI では標準入力のパイプを使う
   （human 発話: `printf "私の意見です\n" | ...`、ループ継続判定: `printf "exit\n" | ...`）

チェックリストとテストの対応（抜粋）：

| チェックリスト項目 | 検証方法（mock 使用） |
|---|---|
| serial / parallel / loop 実行 | イベント列（phase_start / step_start / loop_check）の順序と回数を検証 |
| 会議進行（meeting.json） | moderator → member 並列 → 集約の順でステップが出ること、marker でループが抜けること |
| ロール間会話（max_turns） | ループの反復回数が max_iterations で止まること |
| トークン・コスト集計 | 各 step の tokens/cost/elapsed が記録され、session_end.by_model と整合すること（mock は全て 0） |
| Markdown ログ | JSONL から生成したレポートに Mermaid ブロックとサマリテーブルが含まれること |
| 温度フォールバック | mock に温度エラーを注入し、温度なしで1回だけ再試行されること |
| ストリーミング | chunk イベントの連結が step_done の全文と一致すること |

Web UI の項目（ファイル添付・設定編集）は Phase 4 実装時に UI テストとして追加する。
それまでは保存関数（`save_config`）とバリデーション（5.2 / 5.3 節）の単体テストで代替する。

---

## 10. サンプルデータ仕様

Phase 3 完了時点で以下のサンプル一式を揃える（旧データからの変換はしない）。
Phase 1 では `organizations/solo/`（1人組織）+ `talents/` 1人 + 各 `.example` の最小サンプルのみで開始する。

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
  出題確認（serial）→ 全員回答（parallel）→ 採点と講評（serial）。
  `interrupt_on: "【ユーザー確認】"` を宣言。`organizations/nokuru/config.json` にバインディング例あり
  （`quizmaster: hinata`, `answerer: satsuki, kaede`）。動作確認用入力は **6.7 節**のサンプル表を参照
- `workflows/dev.json`: `implementer`（`"1+"`）+ `reviewer`（`"1"`）。
  実装（serial）→ [レビュー指摘 → 修正] のループを `exit: judge`（reviewer）で回す。
  成果物抽出（7.5 節）の動作確認を兼ねる開発モードのサンプル

**任意拡張（§10.2 の4種に含めない）**

- `workflows/discussion_sourced.json`: `participant` + `source_checker`。
  出典確認ループ（`exit: marker`、最大3回）のデモ。nokuru / trio にバインディング例あり。
  Phase 3 で追加。10.2 の4種パターンとは別枠の運用サンプル。

### 10.3 組織・シナリオ・アプリ設定

- `organizations/nokuru/config.json`: 3.3 節のサンプルそのもの
  （キャンプ仲間の組織。mission / culture、3人編成、meeting / quiz バインディング、common_directives 付き）
- `organizations/nokuru/model_mapping.example.json`: 3.4 節のサンプルそのもの
- `scenarios/camp_planning.json`: 3.5 節の参照型サンプルそのもの
- `studio_config.example.json`: 3.6 節のサンプルそのもの

このサンプル一式で「バインディングなしで動く discussion」「スロット割当が必要な meeting」
「judge ループと成果物抽出を使う dev」「編成差し替えを行う参照型シナリオ」の4パターンを網羅し、
動作確認とドキュメントの実例を兼ねる。

### 10.5 サンプル会話・議事録（Phase 5b 以降・**整備済み**）

開発中の試行会話（`sessions/`）やローカル議事録（`minutes/`）は `.gitignore` のため Git に載せない。
代わりに **意図したデモ用データ**を `samples/` に置く（7.3.1 節）。

| パス | 内容 |
|---|---|
| `samples/sessions/nokuru_camp_planning.jsonl` | nokuru + meeting + 「秋キャンプの行き先」（mock・`【結論】` で 1 反復終了） |
| `samples/minutes/nokuru/camp_planning.json` | 上記に対応する期待議事録（参照セッション ID: `20260714_120000`） |
| `samples/README.md` | 再生成手順 |

`scenarios/camp_planning.json` は **workflow: meeting**（nokuru 既定の camp デモと一致）。

用途:

1. parity 試験（セッション再開・レポート・議事録パイプライン）
2. README / 手動デモの固定入力
3. リリース前の `.gitignore` 解除時、議事録 Git 連携の動作確認

**整備タイミング**: Phase 5b 完了後〜リリース前。`.gitignore` から `minutes/` を外す**前**に
`samples/` を commit しておく。

### 10.4 自己改善開発チーム（メタサンプル・Phase 5 以降）

**MultiRoleStudio 自身の開発・改善に Studio を使う**デモ兼実用サンプル。
「自己改善プログラム開発チーム」——設計書を読んだ AI ロールが、実装・レビュー・次 Phase を議論する。

#### 位置づけ

| 項目 | 内容 |
|---|---|
| 目的 | 本書（`design.md`）を文脈に、Studio の次の改善をチームで進める |
| Phase | **5 以降**（`dev.json` + user_context + 議事録が揃ってから。Phase 1 では作らない） |
| 既存サンプルとの関係 | `workflows/dev.json`（10.2）の**運用例**。組織・シナリオ・corpus が追加 |

#### 構成案

```
organizations/studio_dev/
  config.json              ← mission: 「MultiRoleStudio を design.md に沿って改善する」
  model_mapping.example.json
talents/
  architect.json           ← 設計整合・Phase 判断（design.md 参照を directive に）
  implementer.json         ← かえでと役割分担可。studio/ 実装寄り
  reviewer.json            ← Copilot 的レビュー役。parity / スキーマ矛盾を指摘
scenarios/studio_phase1.json  ← org: studio_dev, workflow: dev, --files schemas/ studio/
user_context/
  my_context.example.md    ← オーナーの興味・用語（付録D）
  corpus/
    design_summary.md      ← design.md の要約（RAG 用。D.10）
    parity_checklist.md    ← 9.3 節の抜粋
```

#### 使い方（例）

```bash
# Phase 5 以降想定
python MultiRoleStudio.py --org studio_dev --workflow dev \
  --topic "Phase 1: loader の E204 mock 対応を実装" \
  --files docs/MultiRoleStudio/design.md schemas/
```

1. **architect** が design.md（添付 or corpus RAG）と parity 要件を踏まえてタスク分解
2. **implementer** が sandbox/ にコード案を出力（7.5 節）
3. **reviewer** が judge ループで「design 矛盾なし」まで回す
4. オーナーが `--apply` または手動で採用（7.6 節）
5. 気づきは user_context 更新案として保存（付録D.7 — 承認式）

#### common_directives の例（studio_dev 組織）

- 回答は `design.md` と矛盾させない。矛盾を見つけたら E102 形式で指摘する
- 実装提案は Phase スコープ（1.5 節）を超えない
- コード変更は sandbox 経由。作業ツリー直書きはしない（7.5 節）

#### 自己言及（メタ）の注意

- `design.md` 全文を毎回注入しない。要約 + RAG（付録D.10）+ `--files` 添付の組み合わせ
- 設計書とコードがズレたら **corpus を更新**（自動追記しない）
- 1.6 節のチーム役割（Cursor 実装 / Copilot レビュー / オーナー判断）と対応づけて使う

このサンプルは「Studio で Studio を育てる」具体例として、README と Phase 5 完了時のデモに載せる。

---

## 11. 未決事項

- Web UI のワークフロー編集はテキストエリア（JSON直書き）で十分か、フォーム化するか
- JSONL ログの長期保管方針（SQLite への移行要否）
- ユーザーコンテキストの詳細は付録D（**5d-a/b 実装済み**）。RAG 拡張は D.10（Phase 6）
- **ユーザー割り込み**（6.7 節）: マーカー文字列の workflow 宣言 vs org 共通指示のみ、予約 talent_id（`user`）の要否
- 10.4 節メタサンプル（studio_dev）の corpus 要約の更新頻度・design.md との同期方法

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

---

## 付録D. ユーザーコンテキスト（Phase 5d 実装済み / RAG 未実装）

Gemini 等の商用チャットで「以前の会話が出てくる」体験に近いが、**Studio 版はユーザーが内容を見て制御できる**レイヤとして設計する。

### D.1 背景（LLM の限界と対策）

LLM はパラメータ中に論理や系譜をメタデータとして保存しているわけではなく、文脈なしでは
「失敗」のような多義語は**一般的な意味の確率**に引っ張られる。高度な応答には、会話の前に
**確率の海を制御する下地（コンテキスト）**を与える必要がある。

Studio では org `mission` / `culture`（組織）と talent `system_prompt`（配役）で既に下地を与えている。
本付録はその**ユーザー本人**向けの第4レイヤ——**性格・興味・用語定義・思考の系譜**が
セッションをまたいで蓄積される仕組み——を定義する。

### D.2 既存レイヤとの関係

| レイヤ | 例 | 共有 | 主役 |
|---|---|---|---|
| talent | ひなたの facilitator 性格 | 組織横断 | AI 配役 |
| organization | のくるの mission / culture | Git 共有可能 | チーム |
| **user_context** | 「失敗＝予測と現実のズレ」、失敗学→創造学の関心 | **個人**（既定 .gitignore） | **ユーザー本人** |
| sessions (jsonl) | 発話の証跡 | ローカル | 監査・再開 |

### D.3 ファイル構成

```
user_context/
  my_context.example.md   ← テンプレ（Git 管理可）
  my_context.md           ← コア本体（短い定義・常時注入向け。1.5 節 .gitignore）
  my_context.summary.md   ← 要約版（D.8。任意）
  corpus/                 ← RAG 用ドキュメント群（D.10。承認済みのみ）
  drafts/                 ← 更新案（D.7）
  index/                  ← ベクトル索引（D.10。.gitignore）
```

`my_context.md` の想定セクション（Markdown 自由記述）：

1. **興味・関心** — 追いたいテーマ、系譜（例：失敗学 → 創造学）
2. **用語定義** — ユーザー固有の意味（例：「失敗」＝次へのデータ）
3. **出力の好み** — 一般論より意外な切り口、構造の共通性を重視、等
4. **蓄積メモ** — 承認済みの気づき・定義の追記（時系列）

### D.4 プロンプトへの注入（5.1 節）

有効時のみ、組織コンテキストの直後に注入する：

```
【ユーザーコンテキスト】
（my_context.md の本文。長大時は要約版を使用 — D.6）
```

### D.5 ON / OFF（必須）

通常は有用だが、**下地なしで fresh に話したい**場面がある。3段階で制御する。

| レベル | 操作 | 用途 |
|---|---|---|
| **グローバル** | `studio_config.json` の `user_context.enabled` | 機能自体の既定 |
| **セッション** | Web トグル（**Phase 5d-a 実装済み**） / CLI `--no-user-context` | 今回だけ OFF |
| **シナリオ**（任意） | `"user_context": false` | 使い捨て実行で下地を除外 |

OFF 時は `session_meta.generation.user_context: false` を記録する（7.1.1 節）。
ON/OFF は jsonl に残し、後から「下地あり/なし」で分析できるようにする。

### D.6 商用サービスとの類似（参考）

| | Gemini / ChatGPT 等 | Studio user_context |
|---|---|---|
| 保存場所 | プロバイダ側（非透明） | ローカル `my_context.md`（**ユーザーが開ける**） |
| 内容 | 過去会話から自動抽出 | 手動 + **承認式**追記 |
| OFF | サービス設定に依存 | **セッション単位で OFF 可能** |
| プロバイダ差 | サービスごとに別 | 同一ファイルを Opper/Groq どちらでも注入 |

「以前の会話が出てくる」体験の**意図的・透明なローカル版**として位置づける。

### D.7 更新サイクル（承認式）

完全自動追記は**採用しない**（幻覚の固定化・矛盾蓄積を防ぐ）。7.5 sandbox / 7.6 Git 採用と同型。

```
1. セッション終了時（またはユーザー操作）に「ユーザーコンテキスト更新案」を生成
2. user_context/drafts/<session_id>.md に diff 案を保存
3. ユーザーが Web / CLI でプレビュー → 採用で my_context.md にマージ
4. 次回セッション開始時に更新済み my_context.md を読み込む
```

追記時は可能なら **evidence**（根拠となった発言・session_id）を添える（7.3 節の議事録と同型）。

### D.8 トークン管理

- 全文毎回投入は不可。`my_context.md` が上限超過時は `reduce_history` と同様に**要約版**
  `my_context.summary.md` を生成して注入する
- 要約生成もユーザー承認式

### D.9 実装 Phase

| Phase | 内容 | 状態 |
|---|---|---|
| 1〜4 | **実装しない**（1.5 節） | — |
| **5d-a** | `my_context.md` 読み込み + ON/OFF + 5.1 注入 + Web トグル / CLI | **実装済み**（2026-07-15） |
| **5d-b** | 更新案生成・承認 UI、要約版（D.7〜D.8） | **実装済み**（2026-07-15） |
| **6** | **RAG 拡張**（D.10）：corpus / index / 関連 chunk 注入 | 未実装 |

### D.10 RAG 拡張（Phase 6 以降・構想）

`my_context.md` が長くなったとき、全文注入（D.4）や要約版（D.8）に加え、
**承認済みドキュメント群から関連部分だけ検索して注入**する方式。

#### なぜ RAG か

| 方式 | 向くケース |
|---|---|
| 全文注入 | コア定義が短く、毎回確実に効かせたい |
| 要約版 | 中程度の長さ。全体像を圧縮 |
| **RAG** | 蓄積が大きい。話題に応じて**関連メモだけ**引きたい |

**ハイブリッド推奨**：用語定義・出力好みなどは `my_context.md` に残し、
時系列の蓄積メモ・長文ノートは `corpus/` に置いて RAG で引く。

#### ディレクトリ

```
user_context/corpus/
  20260713_failure_study.md    ← 承認済み chunk の元ファイル（Markdown）
  ...
user_context/index/            ← ローカルベクトル DB（Chroma / FAISS 等。.gitignore）
```

- **jsonl（sessions/）は index に入れない**。証跡は jsonl、学習素材は**承認済み distill** のみ
- corpus 追加・削除時に index を再構築（`studio user-context reindex` 等）

#### プロンプト注入（5.1 節）

`user_context.enabled` かつ `user_context.rag.enabled` のとき、
現在の user 入力（または step 直前の論点）をクエリに top-k chunk を検索し注入：

```
【ユーザーコンテキスト（関連する過去の思考）】
--- chunk: 20260713_failure_study.md (score: 0.82) ---
（本文抜粋）
...
```

検索に使った chunk id / score は optional で step ログに記録する（7.1 節 `context_chunks`）。

#### ON / OFF

| レベル | 操作 |
|---|---|
| グローバル | `studio_config.json` の `user_context.rag.enabled`（既定 `false`） |
| セッション | `user_context` OFF なら RAG も自動 OFF。RAG 単独 OFF トグルも可 |
| シナリオ | `"user_context_rag": false`（任意） |

#### 更新サイクル（D.7 との連携）

```
承認済み更新案 → my_context.md（短い定義）または corpus/*.md（長い蓄積）
                → reindex → 次回セッションで RAG 検索
```

自動で corpus に追加しない。D.7 の承認フローを共通利用する。

#### 注意点

1. **検索ミス**：無関係 chunk が混ざる → コア定義は `my_context.md` 全文注入のまま維持
2. **embedding コスト**：index 構築時のみ。検索はローカル
3. **プロバイダ非依存**：同一 corpus / index を Opper / Groq どちらの会話でも共用
4. **ファインチューニングではない**：パラメータ更新ではなく、検索による文脈拡張

#### 実装 Phase

| Phase | 内容 |
|---|---|
| 5 | RAG **なし**（`my_context.md` 注入のみ） |
| **6** | corpus + ローカル index + 5.1 注入 + reindex CLI |
| 6+ | Web UI で corpus 閲覧・検索結果プレビュー |

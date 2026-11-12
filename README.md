# LLM Chat System - 高度なAI協働システム

このシステムは、複数のAIが協力して問題解決を行う革新的なチャットシステムです。

> **MultiRoleStudio**（`studio/` + `MultiRoleStudio.py`）が現行のメイン UI です。  
> 旧 `Chat.py` / `MultiRoleChat.py` 系は **Phase 5g** で [`legacy/`](legacy/README.md) に移行しました（タグ: `legacy-ui-pre-migration`）。

## 🎙️ MultiRoleStudio とは

複数の LLM にそれぞれ役割（人材）を与え、会議・議論・企画・開発・ニュース番組のような会話を、設定ファイル（JSON）だけで組み立てて実行します。結果は、テキストで読めるほか、VOICEVOX で音声にして、ラジオ番組のように聴けます。

あなたが経営者、人事、プロジェクトマネージャー、プロデューサーになったつもりで、AI の組織を組み上げて、動かしてみませんか。人材を選び、役割を決め、進め方（ワークフロー）を書けば、会議や番組、プログラミングの仕事が動き出します。

### 4 つの部品（すべて JSON）

| 部品 | 役割 |
|---|---|
| 組織（`organizations/`） | 番組・会議の目的、方針、参加する人材、使うワークフロー |
| 人材（`talents/`） | 人物の性格と、話し方の指示（LLM は問わない） |
| ワークフロー（`workflows/`） | 発言の順序。直列・並列・ループ（合格や結論が出るまで繰り返す）を組み合わせる |
| 割り当て（`model_mapping.json` / `voice_mapping.json`） | 人材ごとの LLM（Claude、Gemini、GPT、Groq など）と、VOICEVOX の声 |

部品を差し替えるだけで、別の番組や会議になります。共有・育成するのは、数 KB の設定ファイルです。

### 仕組みと必要なもの

- **コアは LangChain**: LLM との接続は LangChain（`langchain-core` と、各社のプロバイダーパッケージ）で行います。人材ごとに、OpenAI、Anthropic、Gemini、Groq、Mistral などの LLM を選べます。
- **LLM の API キーが必要**: LLM はクラウドの API を呼びます。使うサービスの API キーを環境変数に設定してください（少なくとも 1 つ。設定方法は[クイックスタート](#-クイックスタート)）。API の利用料は、各サービスにかかります。
- **ローカル LLM・GPU・Docker は不要**: Python（3.13 推奨）と `pip install -r requirements.txt` で動きます。
- **VOICEVOX は任意**: 読み上げ（音声）を使うときだけ必要です。

### 使い方の例（同梱の組織）

同梱の組織は、そのまま試せるほか、人材やワークフローを差し替えて、自分の用途に合わせられます。

| 用途 | 組織 | 内容 |
|---|---|---|
| 📰 ニュース・時事解説 | `broadcast_studio` | 事実を扱うので、いきなり話させません。ディレクター（みどり）がウェブ検索で下調べをして、使える出典の一覧を作り、出演者が議論したあと、放送後に出典と日付を点検します |
| 🏕️ キャラクターエンタメ | `nokuru` | 野外活動サークルの 4 人（元気なひなた、部長のかえで、のんびりした関西弁のさつき、ゲストのゆき）が、キャンプの企画を話し合います。会話の脱線や、アドリブも楽しみのうちです |
| 🏢 会社・コンサルティング | `default_company`、`consulting_firm`、`tech_startup` | 企画、分析、デザイン、プログラマー、マーケティング、秘書などの職種の人材が、事業計画、製品開発、市場調査、戦略立案を、順に検討して、議事をまとめます |
| 💻 開発チーム | `tech_startup`、`codecraft_collective`、`studio_dev` | 設計、実装、レビュー、テストの役割で、コードを書き、合格が出るまで繰り返します。成果物は `sandbox/` に保存され、採用すると作業ツリーへ反映してコミットできます（`studio_dev` は、MultiRoleStudio 自身の改善） |
| ⚖️ 意思決定の支援 | `decision_balance_org`、`groq_fast_discussion` | 楽観と悲観の視点を並べて判断を助けます。Groq の高速な推論で、素早く議論する構成もあります |
| 💡 アイデア出し | `creative_org` | 常識にとらわれない発想や、未来のシナリオを、複数の人材で出し合います |
| 🎓 クイズ・AI の評価 | `quiz_evaluation` | AI・技術分野のクイズで、複数のモデルを競わせて、性能を比べます |

### 主な機能

- **読み上げ**: VOICEVOX のエンジンを複数台指定すると、文単位で、空いているエンジンに振り分けて並列に合成します。保存した音声は、タイミング再生で聴き直せて、声を変えたときは、「音声を作り直して再生」で作り直せます。誤読は、LLM が候補を見つけて、未承認の辞書（`voice_dictionary.pending.json`）に入れ、本登録は人が承認します。詳しくは、[ニュース番組と読み上げ（VOICEVOX）](#ニュース番組と読み上げvoicevox) を参照してください。
- **記録・レポート・再開**: 会話は `sessions/` に保存され、発言の流れを Mermaid の図で示した Markdown のレポートを見たり、エクスポートしたりできます。過去のセッションは、分岐セッションとして再開できます。
- **議事録**: セッションから、決定事項などをまとめた議事録を、`minutes/<組織>/<テーマ>.json` と `.md` に作ります。上書きで最新を保ち、版の履歴は Git で見る方式です。
- **成果物の採用**: 開発系のワークフローが出力したコードは、`sandbox/` に保存され、採用すると作業ツリーへ反映して、Git にコミットできます。
- **費用の表示**: 発言ごとの費用と、セッション終了時のモデル別の集計表（回数・トークン・費用）を表示します。費用は、`model_costs.csv` の単価から計算した推定値で、単価（目安）は、自分で設定・更新できます。単価を更新していないと、実際の請求と差が出ます。**単価の単位は 1K（1,000）トークンあたりの米ドル**です（100 万トークンあたりの価格は 1000 で割って入れる）。`model_costs.csv` にないモデルは既定単価（`default` 行）で概算され、ベンチマークでは「単価未登録」と警告します。通貨は `currency` 列（`USD`、`JPY`）で、空欄は `USD` です。円のモデルは `¥` で表示し、セッションの合計は `total_cost`（USD）と `total_cost_other`（他の通貨、通貨別）に分けます（通貨をまたいでは合算しません）。

設計の詳細は、[設計書](docs/MultiRoleStudio/design.md) を参照してください。

## 🎯 主要コンポーネント

### 1. MultiRoleChat - マルチロールAI協働システム

複数のAIアシスタントが異なる専門役割を担当し、チームとして協働するシステム

**主要機能:**
- 🎭 **複数ロール管理** - 企画、分析、実装、デザインなど専門ロール
- 🔄 **ワークフロー自動化** - 定義済みプロセスの自動実行
- 🏢 **組織シミュレーション** - 企業やチームの会議・議論をシミュレート
- ⚡ **プロバイダー分散** - API制限回避とパフォーマンス最適化
- 🔍 **強化診断機能** - エラー発生時の詳細分析とトラブルシューティング
- 💰 **統合コスト管理システム** - リアルタイムコスト追跡と価格管理
- 💾 **自動コード保存機能** - AIが生成したコードを`sandbox/`に自動保存

**新機能 (v1.6.1):**
- 🐛 **Markdownログ修正** - `---` 前の空行欠落により見出し誤解釈される問題を修正

**新機能 (v1.6.0):**
- 🔀 **phases スキーマ** - serial / parallel / loop / call によるネストワークフロー
- 📞 **サブルーチン呼び出し** - `type: "call"` で汎用ワークフローを再利用可能
- 📊 **Mermaid subgraph 展開** - call 先の中身をログのフロー図に可視化

**新機能 (v1.5.0):**
- 🏕️ **新規組織追加** - `groq_fast_discussion`（高速議論・ディベート）、`nokuru`（キャラクター会話シミュレーションの実験的サンプル）
- 💡 **使い方ガイド拡充** - 仮想会社会議・ディベート・フィクションへの応用例をREADMEに追加

**新機能 (v1.4.0):**
- 🎯 **クイズ評価システム** - 複数AIプロバイダーの性能比較・ベンチマーク機能
- ⚡ **応答時間測定** - クイズモードでの詳細パフォーマンス分析
- 📊 **性能統計レポート** - 正解率・応答速度・早押しクイズ分析
- 🏆 **8プロバイダー対応** - OpenAI/Google/Anthropic/Groq/Mistral/Together/Grok参加制限解除

**新機能 (v1.3.0):**
- 💾 **自動コード保存システム** - AI生成コードの`sandbox/`自動保存機能
- 🔧 **コード保存管理** - セッション別ファイル管理と実行スクリプト生成
- 📁 **分離実行環境** - 生成と実行の完全分離による安全性確保

**新機能 (v1.2.0):**
- 🔧 **統合管理ユーティリティ** - AI設定とコスト管理の一元化 (`update_ai_config.py`)
- 🔍 **プロバイダーマッピング** - AI設定からコスト情報への自動マッピング
- ⚖️ **整合性チェック機能** - AI設定とコスト情報の不整合を自動検出

**新機能 (v1.1.0):**
- 🏢 **組織別設定システム** - 独立した組織とワークフローの管理
- ⚡ **ワークフロー直接実行** - コマンドラインから直接ワークフロー起動
- 🎨 **創造性特化組織** - ブレインストーミングと革新的思考に特化
- 🤖 **スタンドアロンモード** - 組織設定からの単独実行機能
- 💬 **インタラクティブ会議** - `-i`オプションで人間も会議に参加可能
- 👨‍💼 **モデレーター機能** - `role_type: "moderator"`で会議の自動まとめ
- ⚡ **並列処理対応** - quiz/meetingコマンドの高速化
- 🛡️ **レート制限対策** - APIリクエストを0.3秒ずつずらして送信
- 🔢 **ラウンド数指定** - `-r`オプションで会議のラウンド数をカスタマイズ

**新機能 (v1.0.0):**
- 📊 組織情報とプロバイダー情報を含む詳細エラー診断
- 🛠️ 設定ファイル検証ツール (`test_config.py`)
- 📋 リアルタイム設定確認コマンド (`config`, `debug`)
- 🔧 ロール名統一とプロバイダー分散による安定性向上

### 2. MultiRoleStudio - 次世代マルチロール基盤（Phase 1〜3）

[設計書](docs/MultiRoleStudio/design.md) に沿って構築中。

**Phase 進捗一覧（正本）:** [design.md §9.0](docs/MultiRoleStudio/design.md#90-phase-進捗一覧正本)  
**開発チーム通信欄:** [handoff/current.md](handoff/current.md)（Composer ↔ Copilot ↔ オーナー。[handoff/README.md](handoff/README.md)）

<details>
<summary>Phase 一覧（§9.0 と同内容・折りたたみ）</summary>

| Phase | 状態 | 概要 |
|---|---|---|
| 1 | ✅ | 1人 CLI |
| 2 | ✅ | 複数人 serial / parallel |
| 3 | ✅ | loop / meeting / dev / sandbox |
| 4a〜4f | ✅ | Web UI（チャット・設定・添付・mapping・セッション・bindings） |
| 5a〜5f | ✅ | 再開・議事録・採用・user_context・割り込み・samples |
| 5g | ✅ | 旧版移行（§9.2） |
| 5h | ✅ | studio_dev（§10.4） |
| 6 | 🔶 | user_context RAG（D.10）✅。VOICEVOX 読み上げ（§7.9）✅。Zenn 草稿は未着手 |
| 7〜9 | ⬜ | 考査・運用・外部連携 |

</details>

#### セットアップ

```bash
pip install -r requirements.txt          # .venv13 推奨
cp organizations/solo/model_mapping.example.json organizations/solo/model_mapping.json
cp organizations/trio/model_mapping.example.json organizations/trio/model_mapping.json
cp organizations/nokuru/model_mapping.example.json organizations/nokuru/model_mapping.json
cp organizations/studio_dev/model_mapping.example.json organizations/studio_dev/model_mapping.json
# 実 LLM 用（model は ai_assistants_config.json の models から引用）
# cp organizations/trio/model_mapping.providers.example.json organizations/trio/model_mapping.json
# nokuru も同様に organizations/nokuru/model_mapping.json を編集（hinata/satsuki/kaede ごとに assistant + model）
```

#### 実行例

```bash
# --- Phase 1: 1人 ---
python MultiRoleStudio.py --org solo                          # 対話
python MultiRoleStudio.py --org solo --topic "テスト" --stream off   # バッチ

# --- Phase 2: 3人（trio）---
python MultiRoleStudio.py --org trio                           # 直接送信（全員 serial）
python MultiRoleStudio.py --org trio --workflow discussion --topic "議題" --stream off
python MultiRoleStudio.py --org trio --workflow discussion_sourced --topic "議題" --stream off
python MultiRoleStudio.py --org trio --workflow quiz --topic "日本の首都は？" --stream off
#   quiz: 出題(serial) → 全員回答(parallel) → 採点(serial)

# --- Phase 3: 会議・開発（nokuru）---
python MultiRoleStudio.py --org nokuru --workflow meeting --topic "秋キャンプの行き先" --stream off
python MultiRoleStudio.py --org nokuru --workflow dev --topic "hello 関数" --stream off

# --- Phase 5h: 自己改善開発チーム（studio_dev）---
python MultiRoleStudio.py --org studio_dev --workflow meeting \
  --topic "次 Phase のスコープを design.md に沿って整理" --stream off
python MultiRoleStudio.py --org studio_dev --workflow dev \
  --topic "loader の E204 mock 対応を実装" \
  --files user_context/corpus/design_summary.md schemas/ --stream off
# §10.4: design.md 全文の毎回注入は非推奨（corpus 要約 + 必要時 --files が推奨）
# user_context: cp user_context/my_context.example.md user_context/my_context.md

# dev 終了後: セッション出力に表示される成果物ディレクトリで検証
#   例) 成果物: sandbox/session_20260713_180000
cd sandbox/session_<session_id>
./run_all.sh    # pytest と __main__ 付きスクリプトを順に実行（PYTHONPATH=. 済み）

# --- ニュース番組（broadcast_studio）+ VOICEVOX 読み上げ ---
# 詳細は「ニュース番組と読み上げ」節
python MultiRoleStudio.py --org broadcast_studio --workflow broadcast_news_show \
  --topic "今日の日本のニュースをお願いします" --web-search --voice

# --- Phase 5c: 成果物採用（作業ツリーへ反映 + Git 1コミット）---
python MultiRoleStudio.py --apply <session_id>
python MultiRoleStudio.py --apply <session_id> --apply-branch   # studio/<session_id> ブランチでコミット
# Web: セッションタブ → 「成果物採用」。dirty tree 時は中断（§7.6）

# --- テスト（API キー不要）---
python -m pytest tests/parity/ -v

# --- Phase 4: Web UI ---
python MultiRoleStudioWeb.py --org solo          # チャット + 設定編集 + ファイル添付（port 7862）
python MultiRoleStudioWeb.py --org trio --port 7863
python MultiRoleStudioWeb.py --org nokuru      # quiz / meeting デモ（hinata, satsuki, kaede）
python MultiRoleStudioWeb.py --org broadcast_studio --no-browser --host 0.0.0.0 \
  --voicevox-url http://192.168.1.20:50021   # サーバー用 PC（ブラウザは別 PC）
# 終了: コンソールで q + Enter（design.md §8.6）
# RAG（Phase 6）: studio_config で user_context.rag.enabled → Web「コンテキスト RAG」で index 再構築
```

**クイズ（Web UI）サンプル入力** — 組織 `nokuru`、ワークフロー `quiz`（詳細は design.md §6.7）:

| 段階 | 例 |
|---|---|
| 初回 | `日本で2番目に面積の大きい都道府県は？` |
| 割り込みを誘発 | `光の三原色は何？ 出題前に回答形式を確認して` |
| 割り込み返答 | `選択肢4択でお願い` |
| 割り込みなし | `月面着陸の年は？ 自由記述でそのまま出題して` |

`quiz` は `interrupt_on` ありのため Web UI / 対話モードで試す（`--topic` バッチ不可）。

`dev` ワークフローは implementer → reviewer → judge のループでコードを改善し、
終了時に `studio/artifacts.py` がコードブロックを `sandbox/session_<id>/` へ抽出する。
レビュー・judge ステップの例示コードは成果物に含めない（誤抽出防止）。

`discussion_sourced` は participant → source_checker を最大3反復し、
確認不要時は source_checker が `【確認完了】` でループを終了する。
「ソースは？」への有効な回答は URL・正式資料名、または事実主張の取り下げ（仮説への格下げ）のみ。
「要確認・再調査予定」だけでは完了扱いにしない。

| オプション | 説明 |
|---|---|
| `--org` | 組織 ID（`solo`, `trio` 等） |
| `--workflow` | 省略時は**直接送信**。`discussion` / `discussion_sourced` / `quiz` / `meeting` / `dev` |
| `--topic` | 指定時は**バッチ**（1 発完走）。省略時は対話（`q` で終了） |
| `--apply` | sandbox 成果物を作業ツリーへ適用し Git コミット（§7.6） |
| `--apply-branch` | `--apply` 時に `studio/<session_id>` ブランチを作成 |
| `--no-user-context` | ユーザーコンテキストを注入しない（付録D） |
| `--no-user-context-rag` | RAG のみ注入しない（付録D.10。`my_context` は維持） |
| `--user-context-reindex` | `user_context/corpus/` から index 再構築 |
| `--stream off` | ストリーミング OFF（推奨: 速度比較・ログ確認） |
| `--web-search` | ウェブ検索を有効にする。`model_mapping` で `"web_search": true` の人材のみ。対応: Groq / OpenAI / xAI / Anthropic / Gemini |
| `--voice` | VOICEVOX で発言を読み上げ、`sessions/audio/<session_id>/` に wav を保存 |
| `--voicevox-url` | VOICEVOX の接続先（既定: 環境変数 `VOICEVOX_URL`、なければ `http://127.0.0.1:50021`）。カンマ区切りで複数指定すると並列合成 |
| `--benchmark` | 問題セット（JSON / JSONL）を組織の全モデルに流し、自動採点・集計する（下の「クイズ・ベンチマーク」） |

各 step 終了時に `[assistant/model] | 秒 | in=… out=… (api/estimate) | tok/s | $…` を表示する。

- **in** … 入力トークン数（システムプロンプト・議題・指示・`--- 前の発言 ---`・履歴など、モデルへ送った全文）
- **out** … 出力トークン数（その step の応答テキスト）
- **(api)** … プロバイダー API が返した実数。**(estimate)** … API 非対応時の文字数概算
- **$** … `model_costs.csv` に基づく推定コスト（USD）

セッション終了時はモデル別集計を **Markdown 表**で表示（この部分のみ Markdown。他はプレーンテキスト）。
集計の正本は `sessions/<id>.jsonl` の `session_end.by_model`（JSON）に保存される。

**model_mapping:** 実行時に読む正本は `organizations/<org>/model_mapping.json`（`.gitignore`）。
`assistant` は `ai_assistants_config.json` のキー、`model` はその JSON 内の文字列。
`ai_assistants_config.json` の各プロバイダーには、任意で `model_param`（モデル名を渡す引数名。既定 `model`）、`system_param`（システムプロンプトを渡す引数名。無ければメッセージ）、`base_url`（https の接続先）、`api_key_env`（API キーを読む環境変数名）を書ける（例: Opper は `model_name` / `instructions`、さくらの AI Engine は `ChatOpenAI` + `base_url` + `SAKURA_AI_API_KEY`）。これらはサーバー側の設定だけから読み、アップロードファイルからは受け付けない（API キーを別のサーバーへ送られないようにするため）。旧版（`legacy/`）はこれらを読まない。さくらの AI Engine のアカウントトークンは `<UUID>:<シークレット>` の形式で、この文字列全体を環境変数に入れる。
`.example` / `.providers.example` をコピーして編集する。CSV の `model` 列は**手動で写すときの参照用**（実行時には読まない）。

#### クイズ・ベンチマーク（`--benchmark`）

同じ問題セットを、組織の全モデル（`model_mapping.json` の割当）に同条件で流し、正解率・速度・コストを自動で集計する。人格は付けず、共通の簡素な指示を使う（`--style answer` で答えだけ、`--style reason` で簡潔な理由つき）。

```bash
python MultiRoleStudio.py --org quiz_evaluation --benchmark samples/benchmark/questions.example.json --trials 3
```

- **問題セット**: JSON（配列または `{"questions": [...]}`）または JSONL。置き場所は自由で、`--benchmark` にパスを渡す（自分用は `benchmark_questions/` に置くと `.gitignore` される。同梱例: `benchmark_questions/*.example.json` は追跡）。各問は `id`（省略時は通し番号）、`question`、`choices`（`{"A": "…"}`、省略可）、`answer`（省略すると採点しない）。例: [samples/benchmark/questions.example.json](samples/benchmark/questions.example.json)。
- **採点**: 回答の最終行『答え: ○』を読む（選択肢がある問題は記号、ない問題は文字列の一致）。取れない回答は誤答扱い。
- **安定性**: `--trials` で回数を増やすと、速度は平均より外れ値に強い中央値と p95 で見られる。失敗した呼び出しは `--retries` 回まで再試行し、それでも失敗したものはエラーとして記録（正解率の分母に入れない）。`--per-provider` でプロバイダーごとの同時数を抑えると、レート制限を避けやすい。`--rpm N` でモデルごとの 1 分あたりの呼び出し数を上限できる（例: Gemini Tier 1 の 25 回/分なら `--rpm 20`）。それでも 429 が出たときは、サーバーが示す秒数だけ同じモデルを止めて再試行し、待ち時間は応答時間に含めない（ライブラリ内部の再試行を無効化する。対応しないクライアントでは内部の再試行が残るので、コンソールに `Retrying ...` が出たら速度を高めに見ておく）。待った回数はレポートに記録する。
- **temperature**: 既定は 0（正解率と再現性を見るため固定）。`--temperature default` でプロバイダー既定値にできる。温度を受け付けないモデルは自動で既定値になるため、レポートの条件に「既定値で実行したモデル」を記録し、`results.csv` の `temperature` 列に実際の値を残す。
- **出力**: `benchmark_results/<日時>/` に `summary.md`（実行条件〔問題セットのパスと内容の hash、試行、指示、temperature、同時数、実行コマンド〕・タレントとプロバイダー・モデルの対応表・順位表・問題別の正解数・誤答した問題・使用した問題の一覧。表は「プロバイダー (モデル)」で表示し、タレント名は対応表だけに出す。記事にそのまま貼れる）、`results.csv`（試行ごと、Excel で開ける）、`summary.csv`（モデル別）、`raw.jsonl`（回答全文つき）を保存し、記事に貼れる Markdown の順位表と、誤答のあった問題を画面に表示する。順位は正解率優先、同率は中央値の短い順。
- 問題集は著作権に注意する（結果フォルダ `benchmark_results/` は `.gitignore`）。
- **Web UI**: `python MultiRoleStudioWeb.py` の「🎯 ベンチマーク」タブで、同じことができる。組織と対象モデルを選び、問題セット（JSON / JSONL）をアップロード（または `benchmark_questions/` から選択）し、試行回数・指示・temperature・呼び出し上限・同時数を指定して実行する。実行前に API 呼び出し回数の見積もりを表示し、実行中は進捗と「中断」ボタン、終わったら順位表などを画面に出して結果ファイル（`summary.md` あり）をダウンロードできる。過去の結果も一覧から開ける。中断したときは、そこまでの結果を保存する。

#### ニュース番組と読み上げ（VOICEVOX）

組織 `broadcast_studio`（ワークフロー `broadcast_news_show`）は、ディレクターが進行表を作り、メイン・サブ・コメンテーター・天気・スポーツの順に放送し、最後にディレクターが事実を点検する。
ウェブ検索と VOICEVOX による読み上げに対応する。

**準備**

1. `organizations/broadcast_studio/model_mapping.example.json`（mock）をコピーして `model_mapping.json` を作り、人材ごとに `assistant` / `model` を設定する。検索する人材には `"web_search": true` を付ける。
2. [VOICEVOX](https://voicevox.hiroshiba.jp/) を起動しておく（アプリ版でも ENGINE 単体でもよい。既定は `http://127.0.0.1:50021`）。
3. `voice_mapping.example.json` をコピーして `organizations/broadcast_studio/voice_mapping.json` を作り、人材 ID ごとに話者 ID を設定する。

```json
{ "akari": { "label": "冥鳴ひまり", "speaker": 14, "speed": 1.0 } }
```

- `speaker` は VOICEVOX の話者（スタイル）ID。一覧は `http://127.0.0.1:50021/speakers` で確認できる。
- `speed` / `pitch` / `intonation` は任意（話速・高さ・抑揚）。`label` は人間用のメモで、読み込みには使わない。
- マッピングのない人材は読み上げない。
- `when_action` は任意。指定すると、その文字列を `action` に含む step だけを読み上げる。ディレクターは進行表（放送前）と点検（放送後）の 2 回発言するため、`"when_action": "放送後"` で点検だけを読ませる（`.example` の設定）。この step は「ディレクター点検」以降も含めて全文を読む。
- 人材名と声のキャラ名は合わせる必要がない。声は組織ごとのファイルで紐づける（`talents/*.json` には書かない）。
- `voice_mapping.json` は環境依存のため `.gitignore` 対象。コミットするのは `.example`。
- 読みを直したい語は `voice_dictionary.json` に `"表記": "カタカナの読み"` で追加する（例: `"株探": "カブタン"`）。読み上げの直前に置換するだけで、画面とログの本文は変わらない。
  - ルート直下は全組織共通、`organizations/<org>/voice_dictionary.json` は組織専用。同じ表記は組織側が優先される。
  - 表記の空白は有無どちらも一致し、英数字と日本語の境目も空白を問わない（`H II領域` で `HII領域` や `H II 領域` も一致。数字どうしの間は厳密）。空白が入りうる語は、空白入りで書く（空白なしで書いた表記は、空白入りの本文に一致しない）。正規表現を使いたいときは、表記を `re:` で始める（例: `"re:(\\d+)分": "\\1フン"`）。不正な式や空文字に一致する式は警告して無視する。
- 出典の引用記号（`【1†L79-L84】` 等）は読み上げ時に誤読されるため、`broadcast_studio` / `solo` の `common_directives` で「報道機関名を文章で言う」よう指示している。
- 発言末尾の「（進行メモ）…」「ディレクター点検」以降、Markdown 記号、URL は読み上げない。

**CLI**

```bash
python MultiRoleStudio.py --org broadcast_studio --workflow broadcast_news_show \
  --topic "今日の東京株式市場の動きについて解説してください。" --web-search --voice
```

- `--workflow broadcast_news_show` が必要（省略すると全員が順に話す直接送信になる）。
- 全員の発言を生成してから読み上げが始まり、再生が終わるまでコマンドは終了しない。
- VOICEVOX に接続できない場合は警告を出して読み上げなしで続行する。
- 生成した wav は `sessions/audio/<session_id>/NN_<talent_id>.wav` に残る。

**Web UI（ブラウザで再生）**

```bash
python MultiRoleStudioWeb.py --org broadcast_studio
```

左の「ウェブ検索」「読み上げ（VOICEVOX）」にチェックを入れて送信する。発言ごとの音声が、読み上げプレイヤーで順に自動再生される。
ブラウザの自動再生制限で音が出ない場合は、プレイヤーを一度手動で再生する。

**3 台構成（Studio サーバー / VOICEVOX サーバー / ブラウザ）**

```bash
# Studio サーバー
python MultiRoleStudioWeb.py --org broadcast_studio --no-browser --host 0.0.0.0 \
  --voicevox-url http://<VOICEVOX の PC>:50021
# ブラウザ: http://<Studio サーバーの PC>:7862
```

PowerShell では行継続に `` ` `` を使うか、1 行で書く（`\` は使えない）。

```powershell
python MultiRoleStudioWeb.py --org broadcast_studio --no-browser --host 0.0.0.0 `
  --voicevox-url http://<VOICEVOX の PC>:50021
```

**VOICEVOX ENGINE の起動（VOICEVOX サーバー側）**

```powershell
# Windows 配布版（CPU 版）。既定は 127.0.0.1:50021 のため、別 PC から使うなら --host が必須
.\run.exe --host 0.0.0.0
# スレッド数を指定する場合（未指定なら自動。同じ PC で LLM 等も動かすなら絞る）
.\run.exe --host 0.0.0.0 --cpu_num_threads 4
```

```bash
# Docker（CPU 版）。127.0.0.1: を付けると外部から接続できない
docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
```

```powershell
# Windows ファイアウォールの許可（管理者権限の PowerShell。RemoteAddress は自分の LAN に合わせる）
New-NetFirewallRule -DisplayName "VOICEVOX 50021" -Direction Inbound -Protocol TCP -LocalPort 50021 -Action Allow -RemoteAddress 192.168.0.0/24
```

```bash
# Studio サーバー側の PC から疎通確認
curl http://<VOICEVOX の PC>:50021/version
```

- 既定ポートは `50021`。変える場合は `--port` を指定し、ファイアウォールと `--voicevox-url` も合わせる。
- オプションは ENGINE のバージョンで変わることがある。`run.exe --help` で確認する。
- VOICEVOX 側は、外部からの接続を受ける設定（`--host 0.0.0.0`）で起動する。
- **VOICEVOX / Web UI とも認証がない。** 信頼できる LAN 内でのみ使い、インターネットには公開しない（`--share` も使わない）。
- 合成は Studio サーバーが VOICEVOX に依頼し、できた音声をブラウザへ渡す。ブラウザから VOICEVOX へは直接つながない。
- `--voicevox-url` にカンマ区切りで複数の ENGINE を指定すると、発言内の文を空いている ENGINE に振り分けて並列合成する（例: `--voicevox-url http://pc1:50021,http://pc2:50021`）。接続できない ENGINE は外して続行する。全 ENGINE を同じ VOICEVOX バージョンに揃えること（speaker ID が違うと声が変わる）。

| Web 起動オプション | 説明 |
|---|---|
| `--org` | 初期の組織 ID |
| `--workflow` | 起動時に選択するワークフロー ID。省略時は組織の `default_workflow`、なければ直接送信。その組織で使えないときは警告して `default_workflow` で起動する |
| `--port` | ポート番号（既定 7862） |
| `--no-browser` | 起動時にブラウザを開かない |
| `--host` | 待ち受けアドレス。既定は自分の PC のみ。別 PC から開くなら `0.0.0.0` |
| `--voicevox-url` | VOICEVOX の接続先 |
| `--share` | Gradio 公開トンネル（認証なしのため非推奨） |

**注意**

- VOICEVOX の音声は、キャラごとに利用規約とクレジット表記のルールがある。配信・公開する場合は確認する。
- CPU 合成は遅いことがある（Core i7 2600K で数十秒〜）。発言を長くしすぎない。

#### 時事解説チャンネル風（broadcast_studio / `broadcast_topic_show`）

こちらが入れたお題について、**事実 → 背景・深掘り → 予想・推測**の順に話す運用。`broadcast_news_show` と違い、天気・スポーツは扱わない。

| 役割 | 人材 ID | 内容 |
|---|---|---|
| ディレクター | `midori`（みどり） | 放送前にお題を調べてリサーチメモを作り、放送後に点検する |
| 司会 | `akari`（あかり） | 導入、パートの合間のつなぎ、締め |
| 事実担当 | `souta`（そうた） | 起きたことを事実だけで伝える |
| 解説者 | `gou`（ごう） | 背景、深掘り、用語のかみ砕き |
| 予想担当 | `yuuma`（ゆうま） | 見通し、2 つのシナリオ、確度と根拠 |

人材 ID は人物名で、役割名・組織名を含めない。役割は `workflow_bindings`（スロットへの割当）と組織の `role_directives`（キーはスロット名）で与える。

- 人材を入れ替えるときは、`organizations/broadcast_studio/config.json` の `workflow_bindings` を変える。役割の指示は新しい人材に自動でついていく。
- `model_mapping.json` と `voice_mapping.json` は人材 ID で紐づいているため、新しい人材の分を足す。
- 注意事項（同じキーの適用、複数スロット、直接送信など）は、[設計書 §3.3](docs/MultiRoleStudio/design.md) の「role_directives の使い方と注意事項」を参照。

```bash
# model_mapping.json は .gitignore。初回は .example をコピーして編集
cp organizations/broadcast_studio/model_mapping.example.json organizations/broadcast_studio/model_mapping.json

python MultiRoleStudio.py --org broadcast_studio --workflow broadcast_topic_show \
  --topic "食料品の消費税減税法案について" --web-search --voice

python MultiRoleStudioWeb.py --org broadcast_studio --workflow broadcast_topic_show   # Web では入力欄にお題を入れる
```

- `--workflow broadcast_topic_show` が必要（省略すると全員が順に話す直接送信になる）。
- 読み上げは `voice_mapping.example.json` をコピーして `voice_mapping.json` を作る。ディレクターは `when_action` を使い、放送後の点検だけを読み上げる。
- 予想は「予想では」「と見られます」と言い分け、事実と同じ文に混ぜない（`common_directives`）。点検でも、予想を事実のように言った箇所を指摘する。

#### 主要ファイル

| パス | 内容 |
|------|------|
| `MultiRoleStudio.py` | CLI 入口 |
| `MultiRoleStudioWeb.py` | Web 入口（Phase 4a〜4e） |
| `studio/assistant_availability.py` | API キー未設定 assistant の判定（§8.3 #10） |
| `studio/mapping_form.py` | model_mapping フォーム用データ変換 |
| `studio/session_report.py` | セッション一覧・Markdown レポート生成（§8.5） |
| `studio/sessions_ui.py` | セッションタブ UI |
| `studio/web_ui.py` | エンジンイベント → Gradio 表示、組織別 workflow 選択肢 |
| `studio/voice.py` | VOICEVOX 読み上げ（合成・保存・ブラウザ再生キュー・読み辞書） |
| `studio/benchmark.py` | クイズ・ベンチマーク（問題セット・並列実行・自動採点・集計） |
| `studio/benchmark_ui.py` | ベンチマークタブ UI（問題セット選択・実行・結果表示） |
| `studio/config_store.py` | 設定の保存・削除・バリデーション |
| `studio/settings_ui.py` | 設定編集タブ UI |
| `studio/` | loader / engine / bindings / logging / artifacts |
| `workflows/` | `discussion.json`, `discussion_sourced.json`, `quiz.json`, `meeting.json`, `dev.json` |
| `samples/` | 固定デモ用 jsonl / 議事録（§10.5） |
| `talents/*.json` | 人材定義（`hinata`, `satsuki`, `kaede` 等） |
| `sandbox/session_<id>/` | dev 成果物と `run_all.sh`（**.gitignore**） |
| `organizations/<org>/config.json` | 編成・バインディング |
| `organizations/<org>/model_mapping.json` | assistant + model（**.gitignore**） |

### 3. Single Chat - 高度なAIチャットシステム

複数プロバイダー対応の洗練されたチャット機能

**主要機能:**
- 🎯 **複数プロバイダー対応** - OpenAI/Anthropic/Google/Groq/Mistral/Together対応
- 📋 **まとめ機能** - AI による会話履歴の自動要約とファイル保存
- 🔄 **高度なエラーハンドリング** - API制限エラーの自動対応とリトライ機能
- 💾 **会話履歴管理** - CSVログとセッション復元機能
- ⚡ **トークン節約機能** - まとめエントリの履歴除外によるトークン消費削減
- 🔧 **複数行編集** - 高度な行編集機能（もとい/ちゃいちゃい）

**実行時間表示に関する注意（Single Chat）**
- 「実行時間」はストリーム表示の描画時間を含みます（char/char-punct の待機時間など）。
- LLM自体の応答速度を比較したい場合は、`stream=false` で測定してください。
- 読みやすさと速度の両立には、chunk または batch モードが有効です。

**新機能 (v8.2.0):**
- 🤖 **Opper.ai API対応** - Opper.aiプロバイダーを追加（`OPPER_API_KEY`で利用可能）

**新機能 (v8.0.0):**
- 🚨 **包括的API制限エラー対応** - 413/429/503/504エラーの自動検出・対応
- 📏 **自動履歴削減** - 413エラー時の会話履歴自動削減とリトライ
- 💡 **トークン節約機能** - まとめを会話履歴から除外してトークン消費削減
- 🎯 **エラー種別判定** - エラーコードとキーワードベースの正確な判定
- ⏰ **スマートリトライ** - エラー種別に応じた最適化された再試行戦略

## 📚 ドキュメント

### MultiRoleStudio
- 📐 **[設計書](docs/MultiRoleStudio/design.md)** — 仕様・Phase ロードマップ・データ構造（正本）

### MultiRoleChat
- 📖 **[メインガイド](docs/multi-role-chat/README.md)** - 基本機能と使用方法（Web UI 含む）
- ⚙️ **[設定ガイド](docs/multi-role-chat/configuration-guide.md)** - 組織設定・プロバイダー分散・エラー診断
- 🔧 **[設定管理ガイド](docs/multi-role-chat/configuration-management.md)** - 設定ファイル管理・バージョン管理  
- 🚨 **[トラブルシューティング](docs/multi-role-chat/troubleshooting.md)** - エラー解決・診断ツール
- 🚀 **[クイックスタート](docs/multi-role-chat/quickstart.md)** - 迅速な導入手順
- 💡 **[実例集](docs/multi-role-chat/examples.md)** - 実際の使用例とベストプラクティス
- 💰 **[コスト管理](docs/cost-management.md)** - 統合コスト管理とプロバイダーマッピング
- 💾 **[コード保存機能](docs/code-saving-feature.md)** - AI生成コードの自動保存と安全実行

### Single Chat
- 🚀 **[クイックスタート](docs/single-chat/quickstart.md)** - 高度なチャット機能の使用方法
- 📖 **[メインガイド](docs/single-chat/README.md)** - 基本機能と設定（Web UI 含む）
- 🚨 **[エラーハンドリング](docs/single-chat/error-handling.md)** - API制限エラー対応機能

### MyPedia
- 🌐 **[MyPedia ガイド](docs/mypedia/README.md)** - Web Q&A の起動方法・引数・API仕様

## 🔧 統合管理ユーティリティ

### 1. モデルコスト管理（SQLite） - `model_costs_db.py`

**NEW!** `model_costs.csv`をSQLiteデータベースとして管理し、高度な分析が可能：

```bash
# データベースにロード
python model_costs_db.py load

# 最安値モデルを検索
python model_costs_db.py cheapest --limit 5

# プロバイダー別比較
python model_costs_db.py provider OpenAI

# 2つのCSVファイルを比較
python model_costs_db.py compare-files model_costs.csv model_costs_backup.csv

# 価格変動を分析
python model_costs_db.py price-changes

# SQLクエリを実行
python model_costs_db.py sql "SELECT * FROM model_costs WHERE provider='OpenAI'"

# インタラクティブSQLモード
python model_costs_db.py sql-interactive

# グラフ生成（matplotlibが必要）
python model_costs_db.py price-changes --graph
```

**SQLクエリ集（`sql/`フォルダ）:**
- `01_check_dates.sql` - 日付確認
- `02_cheapest_models.sql` - 最安値モデル
- `03_provider_comparison.sql` - プロバイダー比較
- `04_price_changes.sql` - 価格変動分析
- `05_groq_models.sql` - Groqモデル一覧
- `06_new_models.sql` - 新規追加モデル
- 他多数...

### 2. 組織設定バリデーション - `validate_org_configs.py`

組織設定ファイルのモデル名を`model_costs.csv`と照合し、自動修正：

```bash
# 全組織の設定を検証
python validate_org_configs.py validate

# 自動修正（同じタイプのモデルに置換）
python validate_org_configs.py fix

# 即座に修正を適用
python validate_org_configs.py fix-force
```

**機能:**
- ✅ モデル名の存在確認
- ✅ 同じタイプのモデルへの自動置換（Opus→Opus、70B→70B）
- ✅ バックアップ自動作成
- ✅ 詳細レポート出力

### 3. AI設定とコスト管理 - `update_ai_config.py`

AI設定とコスト管理を一元的に行うツール：

```bash
# AI設定の更新（最新モデル情報を取得）
python update_ai_config.py

# コスト一覧の表示
python update_ai_config.py costs list

# AI設定とコスト情報の整合性確認
python update_ai_config.py costs verify

# モデルコスト情報の追加
python update_ai_config.py costs add gpt-5 OpenAI 0.005 0.015 "Latest GPT-5 pricing"

# 最新価格情報の自動取得
python update_ai_config.py costs crawl all
```

詳細は [コスト管理ドキュメント](docs/cost-management.md) を参照してください。

## 🚀 クイックスタート

### 必要な準備

```bash
pip install langchain-openai langchain-anthropic langchain-google-genai langchain-groq langchain-together langchain-mistralai opperai
```

### 環境設定

**⚠️ 重要: APIキーの設定**

使用するプロバイダーに応じて環境変数を設定してください：

```bash
set OPENAI_API_KEY=your_openai_key
set ANTHROPIC_API_KEY=your_anthropic_key
set GOOGLE_API_KEY=your_google_key
set GROQ_API_KEY=your_groq_key
set TOGETHER_API_KEY=your_together_key
set MISTRAL_API_KEY=your_mistral_key
set OPPER_API_KEY=your_opper_key
```

**📝 注意事項:**
- 使用するAIモデルに対応するAPIキーの設定が必要です
- APIキーが設定されていない場合、認証エラーが発生します
- 少なくとも1つのAPIキー（推奨：GROQ_API_KEY）を設定してください

### MultiRoleChat（legacy）

旧版は `legacy/` に移行済みです。詳細は [legacy/README.md](legacy/README.md)。

```bash
# 1. インタラクティブ会議（NEW v1.1.0）- あなたも参加！
python -m legacy.MultiRoleChat --org creative_org --demo
🎭 MultiRoleChat> meeting -i "革新的なAIサービスアイデア"

# 2. 組織指定とワークフロー直接実行（推奨）
python -m legacy.MultiRoleChat --org creative_org --workflow creative_brainstorm --topic "革新的なAIサービス"

# 3. クイズ評価システム（並列処理対応）- AIモデル性能比較
python -m legacy.MultiRoleChat --org quiz_evaluation --demo
🎭 MultiRoleChat> quiz multiline continuous

# 4. 利用可能な組織とワークフローの確認
python -m legacy.MultiRoleChat --org creative_org

# 5. 組織を指定して対話モードで起動
python -m legacy.MultiRoleChat --org tech_startup

# 6. デモモードでの起動
python -m legacy.MultiRoleChat --demo

# 7. ワークフロー実行（対話モード内）
🎭 MultiRoleChat> workflow product_development "LLM仮想会社会議チャットボット"

# 8. 高速並列クイズ（対話モード内）
🎭 MultiRoleChat> quiz "日本で2番目に面積の大きい都道府県は？"
```

### Single Chat（legacy）

```bash
python -m legacy.Chat
python -m legacy.ChatWeb
```

## 🔧 設定ファイル構造

```
llm-chat-system/
├── MultiRoleStudio.py                 # MultiRoleStudio CLI（現行）
├── legacy/                            # 旧 Chat / MultiRoleChat（Phase 5g）
│   ├── Chat.py
│   ├── ChatWeb.py
│   ├── MultiRoleChat.py
│   └── MultiRoleChatWeb.py
├── studio/                            # 新エンジン（旧コードから import しない）
├── schemas/                           # JSON Schema（定義の正本）
├── talents/                           # 人材プール（MultiRoleStudio）
├── organizations/
│   ├── solo/                          # Phase 1 最小組織（config + model_mapping.example）
│   ├── creative_org/                  # 創造性特化組織（旧 MultiRoleChat）
│   │   ├── config.json               # 組織設定とワークフロー
│   │   └── roles/                    # 組織専用ロール
│   │       ├── wild_innovator.txt    # ワイルドアイデア・ジェネレーター
│   │       ├── devil_advocate.txt    # 悪魔の代弁者
│   │       ├── visionary.txt         # ビジョナリー
│   │       ├── creative.txt          # 創造性重視
│   │       └── moderator.txt         # モデレーター
│   ├── quiz_evaluation/              # クイズ評価組織（NEW）
│   │   ├── config.json               # 8つのAIプロバイダー設定
│   │   ├── README.md                 # 性能評価結果・使用方法
│   │   └── roles/
│   │       └── quiz_king.txt         # 自称クイズ王キャラクター
│   ├── groq_fast_discussion/          # Groq専用高速議論・ディベート組織
│   │   ├── config.json               # 3ワークフロー: quick_discussion/debate/issue_discussion
│   │   └── roles/                    # リーダー・アナリスト・リスク評価・ファシリテーター
│   ├── nokuru/                        # Phase 3 サンプル（meeting / dev、hinata・さつき・かえで）
│   ├── studio_dev/                    # Phase 5h メタサンプル（自己改善開発チーム）
│   │   ├── config.json               # workflow_bindings、role_directives
│   │   ├── model_mapping.example.json
│   │   └── roles/                    # 旧 MultiRoleChat 用（Studio は talents/*.json を使用）
│   ├── tech_startup/config.json      # テックスタートアップ組織
│   ├── consulting_firm/config.json   # コンサルティング組織
│   └── default_company/config.json   # デフォルト組織
├── sessions/                          # MultiRoleStudio 実行ログ（.gitignore）
├── tests/parity/                      # MultiRoleStudio パリティ試験
└── docs/                             # ドキュメント
    ├── MultiRoleStudio/              # MultiRoleStudio 設計書
    ├── multi-role-chat/              # MultiRoleChatドキュメント
    ├── single-chat/                  # SingleChatドキュメント
    └── cost-management.md            # コスト管理システムガイド
```

## 🎭 MultiRoleChat の特徴

### 組織とロールの管理

**テックスタートアップ組織例:**
- 📋 **企画** - 戦略立案とアイデア創出
- 🔬 **分析専門** - データ分析と市場調査  
- 💻 **実装専門** - 技術実装と開発
- 🎨 **デザイナー** - UI/UXデザイン
- 📢 **マーケター** - 市場戦略と販促
- 📝 **秘書** - 会議管理と総括

### プロバイダー分散戦略

API制限を回避し、安定した運用を実現するため、各ロールを異なるAIプロバイダーに分散配置：

| ロール | プロバイダー | モデル | 特徴 |
|--------|-------------|--------|------|
| 企画 | Gemini | gemini-2.5-flash | 創造性・高速 |
| 分析専門 | ChatGPT | gpt-5-chat-latest | 論理思考・高品質 |
| 実装専門 | Groq | llama-4-scout | 高速処理 |
| デザイナー | Grok | grok-3-mini-fast | 創造性・独自性 |
| マーケター | Mistral | devstral-small | 効率性・軽量 |
| 秘書 | Anthropic | claude-3-5-haiku | 安全性・丁寧 |

### 💡 こんな使い方もできます

MultiRoleChatの本質は **「役割を持ったエージェントに初期条件を与えて自律展開させる」** シミュレーターです。  
`roles/*.txt`（専門性・性格の定義）と `config.json`（場面・フロー構成）の組み合わせで、以下のような幅広い用途に対応できます。

| 要素 | 仮想会社として | ディベートとして | フィクションとして |
|------|--------------|----------------|------------------|
| `roles/*.txt` | 社員の専門性・職責 | 論者の立場・論拠スタイル | キャラクターの性格・裏設定 |
| `config.json workflows` | 会議の進行手順 | 賛否往復のラウンド構成 | 幕・章・シーンの構成 |
| `initial_message` | 議題 | 論題 | 物語の発端・状況設定 |
| `moderator` ロール | 司会・議事録 | 審判・論点整理 | ナレーター・舞台監督 |
| `max_rounds` | 議論の持ち時間 | ラウンド数 | シーンの尺 |

**例: 仮想会社会議**
```bash
python -m legacy.MultiRoleChat --org tech_startup --workflow product_development --topic "次世代AIアシスタントのMVP設計"
```

**例: 高速ディベート**
```bash
python -m legacy.MultiRoleChat --org groq_fast_discussion --workflow debate --topic "AIによる意思決定は人間の判断より信頼できるか"
```

**例: キャラクター会話シミュレーション（実験的サンプル）**
```bash
python -m legacy.MultiRoleChat --org nokuru --workflow camp_planning --topic "春休みのキャンプ計画"
```

> 💡 **裏設定の重要性**  
> 表に出さない動機・コンプレックス・人間関係の歴史をロール設定に含めると、  
> キャラクターの発言が表面的な役割を超えた深みを持ちます。  
> これは小説家が語る「キャラが勝手に動く」感覚に近い現象です。

### 強化された診断機能

エラー発生時に詳細な診断情報を提供：

```
🚨 詳細診断情報:
[企画] 🚨 エラー詳細
  Organization: tech_startup
  Config: multi_role_config_tech_startup.json
  Source: role/default_org/planner.txt
  Provider: langchain_google_genai.ChatGoogleGenerativeAI
  Assistant: Gemini
  Model: gemini-2.5-flash
  Error: ⚠️ API制限に達しました
```

## 🔍 診断とトラブルシューティング

### 設定診断ツール

```bash
# 組織設定の事前検証
python test_organizations.py

# 特定組織の詳細確認
python MultiRoleChat.py --org creative_org

# 出力例
✨ 組織: creative_org (創造性特化組織)
� 説明: 制約のない発想と革新的思考に特化した創造的組織

🎭 利用可能なロール (5個):
  ✅ ワイルドアイデア: 常識を破る革新的発想を生み出す
  ✅ ビジョナリー: 未来志向の戦略的視点を提供

🔄 利用可能なワークフロー (4個):
  ✅ creative_brainstorm: 制約のない自由な発想から革新的なアイデアを生み出す
```

### リアルタイム診断

```bash
🎭 MultiRoleChat> config      # 全体設定状況
🎭 MultiRoleChat> list        # ロール一覧と詳細
🎭 MultiRoleChat> debug ワイルドアイデア  # 特定ロールの詳細診断
```

## 📊 ワークフローの例

### 製品開発ワークフロー

```bash
workflow product_development "LLM仮想会社会議チャットボット"
```

**実行ステップ:**
1. **企画** - 要求仕様の整理と優先順位付け
2. **実装専門** - 技術アーキテクチャと実装計画
3. **企画** - ユーザーインターフェース設計
4. **分析専門** - 品質評価とリスク分析
5. **秘書** - 開発スケジュールと成果物整理

### コード生成と自動保存

```bash
# AIがコードを生成してsandboxに自動保存
python MultiRoleChat.py -o tech_startup -w simple_coding -t "フィボナッチ関数の実装"

💾 2 ファイル保存: sandbox/session_20250814_141337/
📁 実行可能ファイル: 2 ファイル保存済み (sandbox/session_20250814_141337/)

# 保存されたファイル構造
sandbox/session_20250814_141337/
├── code_000.py          # Python実装
├── code_001.js          # JavaScript実装
├── run_all.sh           # 実行スクリプト
└── session_info.json    # セッション情報
```

## 🚨 よくある問題と解決策

### API制限エラー
**症状:** `⚠️ API制限に達しました`
**解決策:** プロバイダー分散設定の適用、Fast Modelの使用

### ロール名不一致
**症状:** `⚠️ ロール 'XXX' が見つかりません`
**解決策:** 設定診断ツールでワークフローとロール定義の名前統一

### クレジット不足
**症状:** `⚠️ APIクレジットが不足しています`
**解決策:** 他のプロバイダーへの切り替え、軽量モデルの使用

## 🔄 更新履歴

## 📈 バージョン履歴

### MultiRoleStudioWeb v0.12.3 / MultiRoleStudio v0.7.7 (2026-11-12)
- 💴 **費用を通貨ごとに扱う（円のまま）** - `model_costs.csv` の `currency` 列を読み、円のモデルは `¥` で表示。セッションログに `currency`、終了時の合計に `total_cost_other`（USD 以外を通貨別）を追加（USD のみのログは従来どおり）。ベンチマークの結果・集計に `currency` 列と、通貨が混ざるときの注記を追加
- 🌸 **さくらの AI Engine の単価（円）を登録** - 8 モデル（1K トークンあたり、税込）。無償枠（Chat 全体で月 3,000 リクエスト）内は実際は請求が発生しない

### MultiRoleStudioWeb v0.12.2 / MultiRoleStudio v0.7.6 (2026-11-12)
- 🔌 **プロバイダー設定を設定ファイルで定義** - `ai_assistants_config.json` に `model_param` / `system_param` / `base_url` / `api_key_env` を追加。Opper（`ChatOpperAI`）が `model=` を黙って無視し、既定モデルで動いていた問題を修正。temperature を持たないクライアントでは渡さず、実効値を記録する
- 🌸 **さくらの AI Engine をプロバイダーに追加**（`SakuraAI`、OpenAI 互換 Chat Completions、`SAKURA_AI_API_KEY`）

### MultiRoleStudioWeb v0.12.1 / MultiRoleStudio v0.7.5 (2026-11-12)
- 💰 **単価の単位を修正** - `model_costs.csv` の 2025 年登録分（48 行）が 100 万トークンあたりの値で、列の単位（1K トークンあたり）と 1000 倍ずれていたのを、換算して直す。桁違いを検知するテストを追加
- ⚠️ **単価未登録の警告（ベンチマーク）** - 単価表にないモデルを、実行開始時・Web の見積もり・`summary.md`（コスト欄の `*` と条件）で警告する。`summary.csv` に `price_known` 列を追加

### MultiRoleStudioWeb v0.12.0 / MultiRoleStudio v0.7.4 (2026-11-12)
- 🎯 **Web の「ベンチマーク」タブ** - 問題セット（JSON / JSONL）をアップロードして、組織のモデルを並列実行。進捗表示・中断・順位表・結果ファイルのダウンロード・過去の結果の閉覧に対応。実行本体は CLI と共通（`studio/benchmark.py` に中断を追加）

### MultiRoleStudio v0.7.3 (2026-11-12)
- 🚦 **ベンチマークのレート制限対策** - `--rpm` でモデルごとの呼び出し頻度を上限。429 はサーバーが示す秒数だけ同じモデルを止めて再試行し、待ち時間を応答時間に含めない（ライブラリ内部の再試行を無効化）。待った回数をレポートに記録
- 🧭 **プロバイダー・モデル基準のレポート** - 表示を「プロバイダー (モデル)」にし、タレントとの対応表を追加

### MultiRoleStudio v0.7.2 (2026-11-12)
- 📝 **ベンチマークレポートに条件と問題を記録** - `summary.md` に、問題セットのパスと hash・対象モデル・試行・指示・temperature・同時数・実行コマンド・使用した問題の一覧を追加。温度を受け付けず既定値で動いたモデルも記録する。`--temperature default` を追加

### MultiRoleStudio v0.7.1 (2026-11-12)
- 📄 **ベンチマーク結果の Markdown** - `--benchmark` の結果フォルダに `summary.md`（条件・順位表・問題別の正解数・誤答した問題）を追加

### MultiRoleStudio v0.7.0 (2026-11-12)
- 🎯 **クイズ・ベンチマーク（`--benchmark`）** - 問題セット（JSON / JSONL）を組織の全モデルに並列で流し、『答え: ○』を自動採点。複数回試行・再試行・プロバイダー別の同時数制限に対応し、正解率・中央値/p95・コストを CSV と Markdown 表で出力する

### MultiRoleStudioWeb v0.11.2 / MultiRoleStudio v0.6.5 (2026-11-11)
- 🔤 **読み辞書の空白ゆれを吸収、正規表現も選べる** - 表記の空白の有無を問わず一致する（`H II領域` ↔ `HII領域`）。`re:` で始めた表記は正規表現として扱う（普通の表記は従来どおり）

### MultiRoleStudioWeb v0.11.1 (2026-11-11)
- ⏭️ **前・次の発言へ移動** - タイミング再生に「前の発言」「次の発言」ボタンを追加。「前」は今の発言を 2 秒以上聞いていればその頭、そうでなければひとつ前の発言の頭へ戻る
- 🔤 **辞書の空白ゆれを修正** - 辞書の表記に特殊な空白（U+202F など）が混ざっていて、「H II領域」のような語が置換されなかったのを、読み込み時の正規化で直す

### MultiRoleStudioWeb v0.11.0 (2026-11-11)
- ▶️ **連続再生モード（既定）** - タイミング再生に「再生方式」を追加。「連続」は回答・合成の待ちの無音を飛ばして発言を続けて再生し（発言の間は 0.3 秒）、テキストの強調やチャットの吹き出しとも同期する。「実時間」を選ぶと、記録した時刻どおりに再生する

### MultiRoleStudioWeb v0.10.5 (2026-11-09)
- 🚦 **ストリーミング中の画面更新を間引き** - チャンクごとの更新を 0.2 秒間隔にし、ブラウザの描画が追いつかずに「状態が待機に戻らない」「入力欄が遅れる」となるのを防ぐ

### MultiRoleStudioWeb v0.10.4 (2026-11-09)
- ✨ **読み上げ中の発言の枠が点滅するのを修正** - チャットの再描画で強調のクラスが消え、次の更新まで付かない間だけ枠が消えていた。消えた直後に付け直す

### MultiRoleStudioWeb v0.10.3 / MultiRoleStudio v0.6.4 (2026-11-09)
- ⚡ **人材の読み込みを高速化** - `talents/` の走査と検証結果を、ファイルの更新時刻が変わるまで使い回す。人材が増えても、組織・ワークフローの選択肢を作る初回の待ち時間が伸びにくい（人材 60 人・ワークフロー 44 本で、約 1.05 秒→約 0.35 秒）

### MultiRoleStudioWeb v0.10.2 (2026-11-09)
- ⌨️ **実行中も入力欄に文字を入れられる** - 実行中の画面更新が、入力中の文字を消していたのを修正。入力欄を空にするのは、送信を受け付けた直後の1回だけ

### MultiRoleStudioWeb v0.10.1 (2026-11-09)
- 📎 **質問への返答でもファイルを添付** - `【ユーザー確認】`（`interrupt_on`）や human 発言で止まったとき、返答欄でもファイルを添付できる。添付の内容は、以降の発言で参照される
- 📰 **技術記事の編集組織** - 組織 `tech_editorial`（Tech編集部）と、ワークフロー `tech_article_edit`（新規）・`tech_article_polish`（既存記事）を追加

### MultiRoleStudio v0.6.3 (2026-11-06)
- 🔊 **`--voicevox-url` で読み上げを有効化** - CLI で `--voicevox-url` を指定すると、`--voice` を付けなくても読み上げる（Web 版と同じ感覚）。`--voice` だけを付けたときの接続先は、従来どおり既定（環境変数 `VOICEVOX_URL`、なければ `http://127.0.0.1:50021`）

### MultiRoleStudioWeb v0.10.0 / MultiRoleStudio v0.6.2 (2026-11-04)
- 💾 **sandbox へ保存** - セッションタブに「sandbox へ保存」ボタンを追加。保存済みセッションの成果物を、後から `sandbox/` へ取り出せる
- 🔇 **コードブロックの読み飛ばし** - 読み上げでコードブロックを読まない
- ⏹️ **読み上げを止める** - 音声プレーヤーの下のボタンで、再生中の音声と待ち行列を止める（次の送信で再開）
- 🛡️ **並列フェーズの失敗継続** - 並列フェーズで一部の発言が失敗しても、残りを続ける（`step_error` を通知）
- 🔁 **再試行の拡充** - 空応答と gpt-oss の tool_call エラーを再試行の対象に追加。Anthropic の `max_tokens` を 8192 に変更
- 🧹 **新規チャットの修正** - 実行中に新規チャットを押しても、古い生成が画面を上書きしないよう修正。注入 chunk の欄も空にする
- 🏢 **組織の移植** - `default_company` / `tech_startup` ほか、旧形式の組織を Studio 形式へ移植（旧設定は `config.legacy.json`）

### MultiRoleStudioWeb v0.9.1 (2026-10-28)
- 🔤 **読み点検の対象を拡大** - 英字語に加え、漢字語・記号（`未達`→ヒツジタチ、`+`→タス 等）も候補に。漢字・記号の候補は「要確認」として承認するまで読み上げに適用しない
- 🧹 **候補のノイズ除去** - すでに正しく読まれている語・カナだけの表記を除外
- 🔄 **セッションタブ** - タブを開くと一覧を自動更新

### MultiRoleStudioWeb v0.9.0 (2026-10-28)
- 🔤 **読み点検・未承認辞書** - セッションタブに「読みを点検（誤読候補）」「選択を辞書へ本登録」「選択を却下」を追加。LLM（既定 Groq、`studio_config.json` の `voice_suggest`）が誤読候補を `organizations/<org>/voice_dictionary.pending.json` へ追記し、人が採用した分だけ組織辞書へ入る
- 🖥️ **CLI** - `python -m studio.voice_check <session_id> [--ascii-only | --suggest]`

### MultiRoleStudio v0.6.1 / MultiRoleStudioWeb v0.8.1 (2026-10-28)
- 🧹 **broadcast 統合** - `news_studio` / `topic_studio` を統合し、運用組織を `broadcast_studio` に一本化
- 🔤 **workflow 命名整理** - `broadcast_news_show` / `broadcast_news_digest` / `broadcast_topic_show` / `broadcast_topic_debate` を標準化
- 🛡️ **話者ガード強化** - `broadcast_topic_show` / `broadcast_topic_debate` に使用可能ソース制約・完結文制約を追加（出典逸脱と文崩れを抑制）
- 🧭 **UI 体験改善** - 組織に未設定のワークフロー選択後でも、正常選択へ戻った際に警告表示が残留しないよう修正

### MultiRoleStudio Phase 3 (2026-07-13)
- 🆕 **loop フェーズ** — `exit`: marker / judge / user、`loop_check` イベント
- 🆕 **workflows/** — `meeting.json`, `dev.json`
- 🆕 **成果物抽出** — `studio/artifacts.py` → `sandbox/session_<id>/`
- 🆕 **nokuru サンプル** — hinata/satsuki/kaede + `scenarios/camp_planning.json`
- 🆕 **パリティ試験** — Phase 3 向け 6 件追加（計 26 件）

### MultiRoleStudio Phase 2 (2026-07-13)
- 🆕 **serial / parallel** — ワークフロー実行エンジン、`studio/bindings.py`
- 🆕 **workflows/** — `discussion.json`, `quiz.json`
- 🆕 **trio 組織** — 3 人 + プロバイダー混在デモ（alpha/beta/gamma）
- 🆕 **パリティ試験** — Phase 2 向け 4 件追加（計 20 件）

### MultiRoleStudio Phase 1 (2026-07-13)
- 🆕 **studio/ パッケージ** — loader / engine / JSONL ログ / mock アシスタント
- 🆕 **CLI** — `MultiRoleStudio.py`（直接送信・対話 / バッチ `--topic`）
- 🆕 **schemas/** — 6 本の JSON Schema、**tests/parity/** — 16 件
- 🆕 **solo 組織** — `talents/solo_bot.json` + `organizations/solo/`

### v1.6.1 (2026-05-03)
- 🐛 **バグ修正** - Markdownログで `---` 前の空行が欠落し、直前テキストが setext H2 見出しとして描画される問題を修正

### v1.6.0 (2026-04-23)
- 🔀 **phases スキーマ** - serial / parallel / loop / call の4タイプによるネストワークフロー
- 📞 **サブルーチン呼び出し** - `type: "call"` で汎用ワークフローを複数箇所から再利用
- 🔒 **循環呼び出し検出** - frozenset による call_stack 管理で無限ループを防止
- 📊 **Mermaid subgraph 展開** - call 先の中身をログのフロー図に自動展開・可視化

### v1.5.0 (2026-03-15)
- 🏕️ **新規組織追加** - `groq_fast_discussion`（高速議論・ディベート）、`nokuru`（キャラクター会話シミュレーションの実験的サンプル）
- 💡 **使い方ガイド拡充** - 仮想会社・ディベート・フィクションへの応用例をREADMEに追記
- 🔖 **モデル更新** - 各組織の使用モデルを最新版に更新

### v1.4.0 (2025-08-16)
- 🎯 **クイズ評価システム** - quiz_evaluation組織による複数AIプロバイダー性能比較機能
- ⚡ **応答時間測定** - クイズモードでの詳細パフォーマンス分析と統計
- 📊 **性能統計レポート** - 正解率・応答速度・早押しクイズ王決定戦分析
- 🏆 **8プロバイダー対応** - OpenAI/Google/Anthropic/Groq/Mistral/Together/Grok参加制限解除
- 🔧 **API問題解決** - Together APIのモデル変更とG検定ベース評価システム確立

### v1.3.0 (2025-08-14)
- 💾 **自動コード保存システム** - AI生成コードの`sandbox/`自動保存機能
- 🔧 **コード保存管理** - セッション別ファイル管理と実行スクリプト生成  
- 📁 **分離実行環境** - 生成と実行の完全分離による安全性確保
- 🐳 **Docker統合準備** - コード実行環境のコンテナ化サポート

### v1.2.0 (2025-08-14)
- 🔧 **統合管理ユーティリティ** - AI設定とコスト管理の一元化 (`update_ai_config.py`)
- 🔍 **プロバイダーマッピング** - AI設定からコスト情報への自動マッピング
- ⚖️ **整合性チェック機能** - AI設定とコスト情報の不整合を自動検出
- 📊 **強化ログヘッダー** - 組織名とロール詳細情報を含む包括的なログ
- 💰 **CSV基盤コスト管理** - ハードコードから動的データベースへの移行
- 🗑️ **重複ツール削除** - `manage_model_costs.py`を統合により廃止

### v1.1.0 (2025-08-14)
- 🆕 **組織別設定システム** - 独立した組織とワークフローの管理
- 🆕 **ワークフロー直接実行** - コマンドラインから直接ワークフロー起動
- 🆕 **創造性特化組織（creative_org）** - ブレインストーミングと革新的思考に特化
- 🆕 **スタンドアロンモード** - 組織設定からの単独実行機能
- 🗑️ **Legacy削除** - 古い設定システムを完全に削除、新システムに一本化
- 🆕 **包括的ドキュメント拡充** - 組織別設定ガイドの追加

### v1.0.0 (2025-08-13)
- 🆕 強化された診断機能とエラー報告
- 🆕 組織情報とプロバイダー情報を含む詳細ログ
- 🆕 設定診断ツール (`test_config.py`)
- 🆕 プロバイダー分散戦略による安定性向上
- 🆕 ロール名統一とワークフロー最適化
- 🆕 包括的なドキュメント整備

## 🤝 コントリビューション

プロジェクトへの貢献を歓迎します：

1. **問題報告** - エラーログと設定情報を含めて報告
2. **機能提案** - 新しいロールやワークフローのアイデア
3. **設定共有** - 業界特化の設定ファイル例
4. **ドキュメント改善** - 使いやすさの向上

## 🧪 テスト

`tests/`ディレクトリには各機能の検証スクリプトが含まれています：

```bash
# MultiRoleStudio パリティ試験（Phase 1・mock・API キー不要）
python -m pytest tests/parity/ -v

# 設定ファイルの検証
python tests/test_config.py

# 組織設定の整合性チェック
python tests/test_organizations.py

# ワークフロー機能のテスト
python tests/test_workflow_logging.py
```

詳細は [`tests/README.md`](tests/README.md) を参照してください。

## ⚡ パフォーマンス参考値

MultiRoleChat での応答時間ベンチマーク（2026-04-27 / nokuru2組織 / 4ロール並列）

| 構成 | R1（並列） | R2（並列） | R3（並列） | 備考 |
|------|-----------|-----------|-----------|------|
| Opper + `anthropic/claude-opus-4` | 22.7秒 | 33.4秒 | 265.0秒 | ラウンドが進むと遅延増加・タイムアウト疑い |
| Opper + `groq/llama-3.3-70b-versatile` | 4.0秒 | 2.8秒 | 4.0秒 | 安定・最速 |
| Groq直 + `openai/gpt-oss-120b` | 4.2秒 | 5.3秒 | 6.6秒 | 安定・実用的 |

**ポイント:**
- Groq系（直接・Opper経由ともに）は Anthropic系の約6〜80倍高速
- Opper経由でもGroqモデルの速度は健在
- Opper使用時はシステムプロンプトを `instructions` パラメータで渡す必要あり（LangChainの `SystemMessage` では無視される）

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルを参照してください。

---

**LLM Chat System v1.6.1** - AI協働の新しい可能性を探求

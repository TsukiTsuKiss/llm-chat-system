# デモの実行と録画

公開済みのデモ動画: [YouTube](https://youtu.be/D945_WjE9tY)

`demo/make_demo.py` が、MultiRoleStudioWeb の画面を自動で操作し、機能を順に見せる。デモ専用のプロジェクトルートを一時フォルダ（リポジトリの外）に作って、そこで Web UI を起動するため、実データ（`sessions/` や `organizations/` など）には触れない。画面下部のキャプションは、ページに重ねるだけで、アプリ本体は変更しない。

## 事前準備

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

- 読み上げのシーンには VOICEVOX が必要（`--voicevox-url` で接続先を指定する。カンマ区切りで複数指定できる）。複数台を指定すると、文単位で並列に合成し、ライブのタイムラインに ENGINE ごとの合成が並んで映る。
- API キーは、通常の起動と同じく環境変数で渡す。
- `--record` には ffmpeg が必要（PATH に通す）。

## 実行

```bash
# 全シーンを画面なしで録画し、mp4 を出力する（推奨）
python demo/make_demo.py --record ../demo_out --size 1920x1300 \
  --voicevox-url http://<host1>:50021,http://<host2>:50021

# シーンを指定する
python demo/make_demo.py --scenes chat,session

# 費用ゼロの通し確認（LLM を mock に置き換える）
python demo/make_demo.py --mock --no-voice --headless

# ブラウザを開き、Enter を待つ（OBS などで別に録画する場合）
python demo/make_demo.py --wait --size 1920x1300
```

| オプション | 内容 |
|---|---|
| `--scenes` | 実行するシーンをカンマ区切りで指定（既定は全部） |
| `--record DIR` | 画面なしで実行し、画面と声を 1 本の mp4 にして `DIR` に出す |
| `--loudness LUFS` | `--record` の声の目標ラウドネス（既定 -16。0 なら調整しない）。VOICEVOX の原音は小さいので、既定で上げる |
| `--wait` | ブラウザを開いたあと Enter まで待つ（`--record` とは併用しない） |
| `--size 幅x高さ` | ページの表示領域（既定 1920x1300） |
| `--speed` | 待ち時間の倍率（動作確認用。0.3 など） |
| `--mock` / `--no-voice` | LLM を mock に置き換える / 読み上げを省く |
| `--headless` | ブラウザを表示しない（開発時の確認用） |
| `--keep-root` | 終了後もデモ用ルートを残す |

## シーン

| シーン | 内容 |
|---|---|
| `chat` | 番組のワークフローを、ウェブ検索と読み上げ付きで実行（ライブのタイムライン） |
| `session` | セッションのレポートとフロー図（Mermaid）、エクスポート、議事録、sandbox、タイミング再生 |
| `voice` | 読みの点検（誤読候補を探し、辞書に本登録） |
| `context` | ユーザーコンテキスト、RAG、ウェブ検索、ファイル添付 |
| `interrupt` | 【ユーザー確認】での割り込み質問と、続行・終了の選択 |
| `settings` | 人材・組織・ワークフローの作成、保存、削除 |
| `benchmark` | 問題セットの選択、実行、結果、過去の結果（「LLMベンチマーク」タブ） |
| `voicevox` | VOICEVOX タブ（ENGINE 一覧、速さのベンチマークとタイムライン、過去セッションの集計）。`--voicevox-url` の ENGINE を使う（ないとスキップ）。実際に合成を流す |
| `voicemap` | 設定編集の「🔊 声」サブタブ（人材ごとの声・速さ、役割での切り替え、試聴）。`--voicevox-url` が必要（ないとスキップ）。保存はしない |

## 仕組みと注意点

- `--record` は、Playwright の画面録画（映像）と、セッションの `timeline.jsonl` の再生開始時刻に発言の wav を並べた音声を、ffmpeg で合成する。声が入るのは `chat` シーンだけ。リモートデスクトップや OBS の音声転送を通さないので、声が早回しにならない。
- ライブのタイムライン（高さ約 400px）をスクロールなしで見せるには、`--size` の縦が 1250 以上必要。
- 途中のシーンが失敗しても、`--record` ならそこまでの録画を `demo_<日時>_partial.mp4` として残す。
- 実 LLM を呼ぶので、費用がかかり、内容は毎回変わる。実行時間は番組 1 回分（生成と読み上げ）で十数分かかる。
- デモ用ルートは `git init` 済みで、議事録・成果物採用の Git コミットは、実リポジトリではなくデモ用ルートに入る。

## 保守

画面・ワークフロー・設定などの機能を追加したら、`demo/make_demo.py` のシーンとキャプションも見直して追加する。

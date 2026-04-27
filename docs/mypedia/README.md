# MyPedia ガイド

MyPedia は、`Chat.py` のアシスタント設定を利用して動く FastAPI ベースの Web Q&A アプリです。

- フロント: シンプルな 1 ページ UI（質問入力、回答表示、戻る/進む）
- バック: `/ask` API で LLM に問い合わせ
- 目的: 回答内の重要語を次の検索に繋げる対話型探索

## 主な機能

- 外部 LLM 接続（`Chat.py` の `load_ai_assistants_config`, `load_assistant` を利用）
- プロバイダー/モード切替（Web UI から `ai_assistants_config.csv` の設定を利用）
- 回答時間の表示（クライアント表示時間 + サーバ処理時間）
- 回答中の語句リンク化
- `[[語句]]` 形式のヒントを優先リンク化
- 戻る / 進む（クライアント側履歴）
- 見出しの正規化（`参考になる検索語句:`）
- Temperature 変更時の保留表示（`次のAskで反映`）

## 起動方法

プロジェクトルートで実行します。

```bash
. venv/bin/activate
python3 MyPedia.py
```

既定値:

- アシスタント: `Groq`
- ホスト: `127.0.0.1`
- ポート: `8765`

アクセス先:

- http://127.0.0.1:8765

## よく使う起動例

### プロバイダー指定

```bash
python3 MyPedia.py -a Groq
python3 MyPedia.py -a Grok
python3 MyPedia.py -a Gemini
```

### モデルを直接上書き

```bash
python3 MyPedia.py -a Grok --model grok-3
python3 MyPedia.py -a Grok --model grok-4.20
```

### fast_model を使う

```bash
python3 MyPedia.py -a Grok --fast
```

### ポート変更

```bash
python3 MyPedia.py --port 8080
```

## CLI オプション

- `-a`, `--assistant`: アシスタント名（`ai_assistants_config.csv` の `assistant_name`）
- `-m`, `--model`: モデル名を直接指定
- `--fast`: `fast_model` を使用
- `--host`: バインドホスト（既定: `127.0.0.1`）
- `--port`: ポート番号（既定: `8765`）
- `--reload`: 開発用リロード

## 環境変数

以下でも切り替え可能です。

- `MYPEDIA_ASSISTANT`
- `MYPEDIA_MODEL`
- `MYPEDIA_FAST`

例:

```bash
MYPEDIA_ASSISTANT=Grok MYPEDIA_MODEL=grok-3 python3 MyPedia.py
```

## API エンドポイント

- `GET /` : UI
- `GET /help` : ヘルプ表示
- `POST /ping` : ヘルスチェック
- `GET /settings` : 現在の LLM 設定と選択肢を取得
- `POST /settings` : LLM 設定（assistant/mode/model）を更新
- `POST /ask` : 質問応答

`POST /ask` リクエスト例:

```json
{"question":"かぐや姫の出した難題とは何だい？", "temperature": 0.0}
```

レスポンス例:

```json
{
  "answer": "...",
  "server_ms": 1234.56,
  "assistant": "Groq",
  "model": "openai/gpt-oss-120b"
}
```

## 運用メモ

- 既存プロセスが 8765 を使用中なら、起動前に停止してください。

```bash
fuser -k 8765/tcp 2>/dev/null
```

- モデルの有効性はプロバイダー側で変化します。エラー時は `--model` を別名で再試行してください。
- 速度重視なら Groq、内容重視なら Grok 系の上位モデルが有効なケースが多いです。

## Temperature について

UI のスライダーで `0` ～ `2` の範囲で指定できます。

| 値 | 特性 |
|---|---|
| 0 | 確定的・事実寄り。同じ質問には同じ答えが返りやすい |
| 0.5〜1.0 | バランス型。自然な文体で適度に多様 |
| 1.5〜2.0 | 創造的・多様。詩や発想出しに向くが誤りも増える |

Q&A 用途では `0` ～ `0.5` が推奨です。

補足:

- Temperature を変更すると、UI に小さく `次のAskで反映` と表示されます。
- 実際に反映されるのは次回 `Ask` 実行時です（変更だけでは検索は走りません）。

## 既知の注意点

- **ハルシネーション（事実誤認）に注意してください。** LLM は実在しない書籍・商品・人物・日付などを自信を持って答えることがあります。重要な情報は必ず別途検索エンジンや信頼できる情報源で確認してください。
- 同一クエリ連続送信はフロント側でガードされています（`query + temperature + assistant + mode` が同一なら再送しない）。
- プロバイダー/モード変更や Temperature 変更後は、重複ガード状態がクリアされるため同一質問でも `Ask` 可能です。
- 回答はリンク化のため HTML エスケープ後に加工されます。
- LLM 初期化に失敗した場合、`/ask` は 500 を返します。

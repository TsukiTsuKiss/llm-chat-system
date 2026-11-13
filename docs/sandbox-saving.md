# sandbox 保存（成果物の抽出）

AI が応答に書いたコードを、セッション終了時に `sandbox/session_<session_id>/` へ保存する機能です。実装は `studio/artifacts.py`、仕様は [設計書 §7.5・§7.6](MultiRoleStudio/design.md) にあります。

- 保存だけを行い、生成コードの実行はしません。実行は利用者の明示操作です。
- `sandbox/` は `.gitignore` 対象です。作業ツリーへ反映するときは「成果物採用」を使います。
- どのワークフローでも、抽出できるコードブロックがあれば保存されます。主な用途は `dev`（implementer → reviewer → judge のループ）です。

## 使い方

```bash
# 実行すると、終了時に「成果物: sandbox/session_<id>」と表示される
python MultiRoleStudio.py --org nokuru --workflow dev --topic "フィボナッチ関数を作って"

cd sandbox/session_<session_id>
./run_all.sh     # テストとスクリプトを順に実行（PYTHONPATH=. 済み）
```

実行済みのセッションから、あとで作り直すこともできます。Web UI のセッションタブで保存済みセッションを選び、「sandbox に保存」を押します。既存の `sandbox/session_<id>/` は削除して作り直します。

## 保存されるもの

```
sandbox/session_<id>/
├── <相対パス>/<ファイル名>   # コードブロックに付いたパスのまま（サブディレクトリ可）
├── __init__.py              # サブディレクトリがある場合に自動で補う
└── run_all.sh               # 実行スクリプト
```

### ファイル名の決まり方

コードブロック（```` ```言語 ```` で囲んだ部分）ごとに、次の順で名前を探します。

1. 直前の行の `ファイル名: <相対パス>`（推奨。AI にこの書式で書かせるのが確実）
2. 直前の行にあるファイル名だけの行（`` `hello.py` ``、`### hello.py` など）
3. コードの先頭 3 行以内の `# <相対パス>` コメント
4. 見つからなければ `code_<人材ID>_<アクション>_<連番>.<拡張子>`

絶対パスと `..` を含むパスは拒否します（`sandbox/session_<id>/` の外へは書き出しません）。

### 保存の対象

| 項目 | 扱い |
|---|---|
| 拡張子 | `.py` / `.js` / `.sh` / `.html` / `.css` / `.json` / `.md` / `.toml` のみ保存 |
| 同じパスを複数のステップが出力 | 後のステップの内容を採用（レビュー後の修正版が残る） |
| レビュー・動作確認・終了条件（judge）のステップ | 例示コードを含むため、抽出しない |
| 不完全なテストの断片 | 取り除く |

### run_all.sh

- テストファイル（`test_*.py` など）は `pytest -q` で実行します。
- `__main__` を持つスクリプト、またはトップレベルにある実行用スクリプトは `python` で実行します。

## 成果物を作業ツリーに反映する（採用）

sandbox の内容を作業ツリーへ書き込み、1 コミットにまとめます。プッシュはしません。作業ツリーに未コミットの変更があるときは中断します（[設計書 §7.6](MultiRoleStudio/design.md)）。

```bash
python MultiRoleStudio.py --apply <session_id>
python MultiRoleStudio.py --apply <session_id> --apply-branch   # studio/<session_id> ブランチでコミット
```

Web UI では、セッションタブの「成果物採用」を使います。

## 隔離して実行する

AI が書いたコードは信頼できないものとして扱い、必要なら Docker で実行します。

```bash
cd sandbox/session_<session_id>
docker run --rm -v "$(pwd):/app" -w /app python:3.11-slim python hello.py
```

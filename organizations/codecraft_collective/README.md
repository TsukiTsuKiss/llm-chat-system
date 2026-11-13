# コードクラフト・コレクティブ（codecraft_collective）

要求から動作するアプリを素早く作り、品質を確かめて届ける最小構成の開発組織です。議論は最小限にして、動くものを優先します。

## メンバー

| 人材 | 役割（スロット） | 内容 |
|---|---|---|
| 全能 統（`zen_tou`） | `builder` | フルスタック開発者。フロント・バックエンド・設定ファイルまで一人で実装する |
| 検証 確（`kensa_tashika`） | `tester` | テストエンジニア。品質の観点から動作を検証し、改善を提案する |

## ワークフロー

| ワークフロー | 構成 | 内容 |
|---|---|---|
| `instant_build` | 全能 統 | 議論なしで、要求から動作するアプリを即座に生成する |
| `rapid_mvp`（既定） | 全能 統 → 検証 確 | 最小限の機能のプロダクトを 2 ステップで作り、検証する |

## 使い方

```bash
python MultiRoleStudio.py --org codecraft_collective --workflow instant_build --topic "シンプルな電卓"
python MultiRoleStudio.py --org codecraft_collective --workflow rapid_mvp --topic "じゃんけんゲーム"
```

`model_mapping.json` は、初回に `model_mapping.example.json` をコピーして assistant と model を指定します。

## 生成物の確認

実行が終わると、コードブロックが `sandbox/session_<session_id>/` に保存されます（[sandbox 保存](../../docs/sandbox-saving.md)）。ファイル名は、AI がコードブロックの直前に書いた `ファイル名: <相対パス>` の行で決まります。

```bash
cd sandbox/session_<session_id>
bash run_all.sh                 # テストとスクリプトを順に実行

# Web アプリ（index.html など）は、簡易サーバーで確認する
python -m http.server 8080      # http://localhost:8080
```

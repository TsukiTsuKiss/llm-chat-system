# Workflowネスト化 宿題メモ

更新日: 2026-04-22
対象: MultiRoleChat の workflow 設計

## 背景
- 現行の `steps` / `parallel_steps` + フラグ方式では、
  - 途中で「各自が個別検討」
  - その後「各自が発表」
  - 最後に「司会が統合」
  のような段取りを自然に表現しにくい。
- 将来的には、ワークフローをネスト構造で表現できる形にしたい。

## 現状の実装（2026-04-22 時点）
- `_execute_timed_response`: モデル呼び出し・時間計測・整形の共通化 ✅
- `_run_engine(exec_plan, topic, ...)`: 直列/並列を統一処理する実行エンジン ✅
  - `exec_plan = [[step], [step], [step1, step2, ...]]` の形式
  - 1件グループ → 直列、複数件グループ → 並列
  - LangGraph は不使用（for ループ + ThreadPoolExecutor で実装）
- `execute_workflow` / `execute_iterative_workflow`: `_run_engine` を呼ぶだけに整理 ✅
- ログフッター（`**実行完了**` / `**実時間**`）を全ログ種別に統一 ✅

> **注意**: LangGraph は現時点で依存を外した。ネスト型実装時に再導入予定。

## ゴール
- `sequence` と `parallel` を入れ子にできる workflow 定義を導入する。
- 既存設定（`steps` / `parallel_steps`）は互換維持したまま使えるようにする。
- ユーザー向けコマンド（`workflow`, `meeting`, `quiz`）の表向き仕様は維持する。

## 宿題タスク

### 1. 実行スキーマ案を確定する
- `flow.type`: `task` / `sequence` / `parallel` を基本とする
- `task` は `role`, `action` を持つ
- 必要なら将来拡張用に `branch`, `repeat` を予約する

### 2. 互換レイヤを作る
- 既存 `steps` を `flow: sequence(task...)` に変換
- 既存 `parallel_steps` を `flow: parallel(task...)` に変換
- 変換後の `exec_plan` を `_run_engine` に渡す形に統一

### 3. `_run_engine` をネスト対応に拡張する ⬅️ **LangGraph 再導入予定**
- `exec_plan` の代わりに `flow` ノードを再帰評価できるようにする
- `sequence / parallel / branch / repeat` の解釈をここに集約
- チェックポイント（途中保存・再開）が必要になったら `StateGraph` を内部で使う
- グラフ可視化が必要になったら `langgraph.graph` を再び import する
- ループ終了条件（`should_continue` 相当）も `_run_engine` に閉じ込める

### 4. ログ仕様を固定する
- 見出し階層、経過時間、埋め込み見出し補正の契約を明文化
- 並列ブロックの記録単位（ブロック時間と各タスク時間）を決める

### 5. meeting / quiz を段階移行する ⬅️ **インタラクティブ入力が必要な部分は後回し**
- まず内部で workflow 変換して `_run_engine` を呼ぶラッパー化
- インタラクティブ入力（ユーザー介入）の挿入点は LangGraph の Human-in-the-loop 機能が候補

## 検討ポイント
- 並列実行の表示順: 完了順か、定義順か
- 失敗時の継続ポリシー: fail-fast / best-effort
- 将来の条件分岐導入時、設定の可読性を保てるか
- LangGraph の `interrupt_before` / `interrupt_after` による Human-in-the-loop の活用タイミング

## LangGraph 活用計画
| 機能 | 現状 | 導入タイミング |
|---|---|---|
| 直列・並列ステップ実行 | `_run_engine` で代替 | 不要（現状維持） |
| 条件分岐ループ | `for + break` で代替 | ネスト型 `branch/repeat` 実装時 |
| チェックポイント（中断・再開） | 未実装 | ネスト型エンジン拡張時 |
| Human-in-the-loop | 未実装 | meeting/quiz の workflow 移行時 |
| グラフ可視化 | 未実装 | デバッグ用途として任意追加 |

## 受け入れ基準（暫定）
- 既存組織の config を変更しなくても従来どおり実行できる
- ネスト定義を1つ追加し、`parallel -> sequence -> task` が実行できる
- ログで構造が崩れず確認できる

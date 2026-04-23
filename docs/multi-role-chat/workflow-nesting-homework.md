# Workflowネスト化 宿題メモ

更新日: 2026-04-23
対象: MultiRoleChat の workflow 設計

## 背景
- 現行の `steps` / `parallel_steps` + フラグ方式では、
  - 途中で「各自が個別検討」
  - その後「各自が発表」
  - 最後に「司会が統合」
  のような段取りを自然に表現しにくい。
- 将来的には、ワークフローをネスト構造で表現できる形にしたい。

## 現状の実装（2026-04-23 時点）
- `_execute_timed_response`: モデル呼び出し・時間計測・整形の共通化 ✅
- `_run_engine(exec_plan, topic, ...)`: 直列/並列を統一処理する実行エンジン ✅
  - `exec_plan = [[step], [step], [step1, step2, ...]]` の形式
  - 1件グループ → 直列、複数件グループ → 並列
  - LangGraph は不使用（for ループ + ThreadPoolExecutor で実装）
- `_run_phases(phases, topic, ...)`: phases スキーマの再帰実行エンジン ✅
  - `serial` / `parallel` / `loop` / `call` の4タイプ対応
  - `call` タイプで別ワークフローをサブルーチンとして呼び出せる
  - 循環呼び出し検出（`frozenset` による call_stack 管理）✅
- `workflow_to_mermaid()`: Mermaid フローチャート生成 ✅
  - `call` ノードを `subgraph` として展開（内部構造を可視化）✅
  - 循環時はフォールバックで単一ノード表示
- ログの `## 🔀 フロー設計` に subgraph 展開済み Mermaid を自動埋め込み ✅
- nokuru 組織に `vote_base`（汎用投票サブルーチン）実装・動作確認済み ✅

> **注意**: LangGraph は現時点で依存を外した。ネスト型実装時に再導入を再評価する。

## ゴール
- `sequence` と `parallel` を入れ子にできる workflow 定義を導入する。
- 既存設定（`steps` / `parallel_steps`）は互換維持したまま使えるようにする。
- ユーザー向けコマンド（`workflow`, `meeting`, `quiz`）の表向き仕様は維持する。

## 宿題タスク

### ✅ 完了済み（2026-04-23）
- [x] phases スキーマ（serial / parallel / loop）の実装
- [x] `type: "call"` によるサブワークフロー呼び出し
- [x] 循環呼び出し検出
- [x] Mermaid の `subgraph` 展開（call 先の中身を可視化）
- [x] nokuru に `vote_base`（汎用投票ループ）を実装・動作確認

---

### 1. `parallel_call` 型の実装 ⬅️ **次の宿題**

複数のサブワークフローを並列に呼び出せるようにする。

**ユースケース**: ブレスト → 分科会A・分科会B（同時） → 最終投票

```json
{
  "type": "parallel_call",
  "workflows": ["sub_a", "sub_b"]
}
```

**現状の壁**:
- `parallel` フェーズは `steps`（ロール単位）しか並列化できない
- サブワークフロー同士を同時実行するには `_run_phases` の並列化拡張が必要
- `acc`（累積結果）のマージ方法（順序・ラベリング）を決める必要がある

**Mermaid 表現案**:
```
subgraph SG_A ["📞 分科会A"]
  ...
end
subgraph SG_B ["📞 分科会B"]
  ...
end
J1[ ]
J1 --> SG_A_入口
J1 --> SG_B_入口
SG_A_出口 --> J2
SG_B_出口 --> J2
```

---

### 2. call 深さ制限（安全弁）

- `max_call_depth`（デフォルト 3）を設定できるようにする
- 超えたら `⚠️ 最大ネスト深さを超えました` として単一ノードにフォールバック
- config に `"max_call_depth": 2` と書けば組織ごとに調整できる

---

### 3. acc コンテキスト圧縮

深いネストではコンテキストが積み上がりAPIコストが増大する。

- 「まとめ役ステップ」をサブワークフロー末尾に置いてサマリーを `acc` に追加し、
  それ以前の生ログを `acc` から切り離す仕組み
- または `max_acc_tokens` を設けて古いエントリを自動トリム

---

### 4. ログ参加者リストの重複排除

- `call` 先のロールが親ワークフローと重複するとヘッダーに同名が複数並ぶ
- `_initialize_workflow_log` の参加者収集で `dict.fromkeys()` などで重複排除する

---

### 5. meeting / quiz の workflow 移行 ⬅️ **インタラクティブ入力が必要な部分は後回し**
- まず内部で workflow 変換して `_run_engine` を呼ぶラッパー化
- インタラクティブ入力（ユーザー介入）の挿入点は LangGraph の Human-in-the-loop 機能が候補

## 検討ポイント
- 並列実行の表示順: 完了順か、定義順か
- 失敗時の継続ポリシー: fail-fast / best-effort
- `parallel_call` での `acc` マージ順序（分科会Aが先か定義順か）
- call 深さが深いほど Mermaid が縦長になる → 折りたたみ表示の検討
- LangGraph の `interrupt_before` / `interrupt_after` による Human-in-the-loop の活用タイミング

## LangGraph 活用計画
| 機能 | 現状 | 導入タイミング |
|---|---|---|
| 直列・並列ステップ実行 | `_run_engine` で代替 | 不要（現状維持） |
| 条件分岐ループ | `loop` フェーズ + `exit_condition` で代替 | 不要（現状維持） |
| サブルーチン呼び出し | `call` フェーズで実装済み | 不要（現状維持） |
| チェックポイント（中断・再開） | 未実装 | `parallel_call` 拡張時に検討 |
| Human-in-the-loop | 未実装 | meeting/quiz の workflow 移行時 |
| グラフ可視化 | Mermaid で代替 | 不要（現状維持） |

## 受け入れ基準（暫定）
- 既存組織の config を変更しなくても従来どおり実行できる ✅
- ネスト定義を1つ追加し、`parallel -> serial -> task` が実行できる ✅
- `call` によるサブワークフロー呼び出しができる ✅
- ログのフロー設計に subgraph 展開で call 先の中身が見える ✅
- **次のゴール**: `parallel_call` で複数サブワークフローの並列実行ができる

# 通信欄 — MultiRoleStudio ユーザー割り込み（§6.7）

| 項目 | 値 |
|---|---|
| Phase | 5e（Phase 5 残タスク 2） |
| 状態 | コミット待ち |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` §6.7 |

---

## Composer → オーナー

workflow `interrupt_on` マーカー検出によるユーザー割り込みを実装。AI step 完了後に `await_text` で停止し、返答を `turn_prior` に載せて workflow を継続。

### 本コミットに含むもの

- `studio/interrupt.py` — マーカー解決・照合
- `studio/engine.py` — step 後割り込み・`user_interrupt` ログ
- `schemas/workflow.schema.json` — `interrupt_on`
- `workflows/quiz.json` — サンプル宣言 + action 追記
- Web / CLI 表示、`--topic` バッチ拒否（interrupt_on 時）
- `tests/parity/test_user_interrupt.py`（6件 PASS）

### 使い方

1. workflow JSON に `"interrupt_on": "【ユーザー確認】"` を追加
2. 人材の action / common_directives で、ユーザーへ聞くとき末尾にマーカーを付けるよう指示
3. AI 応答にマーカーが含まれるとチャットが一時停止し、回答入力を求める

---

## 次: Phase 5 残

- サンプル整備 / 旧版移行（§9.2）

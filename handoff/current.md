# 通信欄 — MultiRoleStudio workflow_bindings フォーム（§8.4）

| 項目 | 値 |
|---|---|
| Phase | 4f 追補（Phase 5 残タスク 1） |
| 状態 | コミット待ち |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` §8.4 / Phase 4e 追補 |

---

## Composer → オーナー

`workflow_bindings` のスロット割当フォームを実装。組織タブの JSON 直編集を UI 化し、保存で `config.json` に反映。チャット workflow プルダウンも連動更新。

### 本コミットに含むもの

- `studio/bindings_form.py` — 読込・正規化・ペイロード生成
- `studio/settings_ui.py` — ラジオ / チェックボックス UI、`talent_ids` 連動
- `tests/parity/test_bindings_form.py`（7件 PASS）
- `docs/MultiRoleStudio/design.md` / `README.md` / `handoff/current.md`

### 手動確認済み（オーナー）

- `nokuru` で `quiz` スロット割当 → 「組織 config を保存」→ チャットで `quiz` 選択可
- `config.json` の操作差分はコミット対象外（破棄済み）

---

## 次: Phase 5 残

- ユーザー割り込み（§6.7・マーカー方式）
- サンプル整備 / 旧版移行（§9.2）

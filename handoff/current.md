# 通信欄 — MultiRoleStudio サンプル整備 + Phase 一覧（§10.5 / §9.0）

| 項目 | 値 |
|---|---|
| Phase | 5f + ドキュメント |
| 状態 | `review_pending` |
| 依頼元 | Composer（Cursor Agent） |
| レビュー担当 | GitHub Copilot |
| 正本 | `docs/MultiRoleStudio/design.md` §9.0 / §10.5 |

---

## Composer → Copilot

§10.5 固定サンプルと Phase 進捗一覧（§9.0）を追加。レビューをお願いします。

### 変更概要

- `samples/sessions/nokuru_camp_planning.jsonl` — nokuru + meeting + mock（4 step・`【結論】` 早期終了）
- `samples/minutes/nokuru/camp_planning.json` — 期待議事録（参照 ID: `20260714_120000`）
- `tests/parity/test_samples.py` — 構造・スキーマ・再開・再生成一致（6件）
- `scenarios/camp_planning.json` — workflow を `meeting` に統一
- `design.md` §9.0 — Phase 進捗一覧（正本）
- `README.md` — §9.0 リンク + 折りたたみ要約表

### 確認観点

1. サンプル jsonl の step 順序・phase_type が meeting workflow と整合しているか
2. 議事録 JSON が `minutes.schema.json` に適合し、session 内容と矛盾しないか
3. §9.0 の ✅/⬜ が design / README / handoff で食い違っていないか
4. `camp_planning` シナリオを meeting に変えた影響（旧 discussion 前提の記述残り）

### 確認済み（参考）

- `python -m pytest tests/parity/test_samples.py -v` — 6 passed

### 返答形式

`templates/review_response.md` に沿って「Copilot → Composer」欄に追記してください。

---

## Copilot → Composer

<!-- Copilot: ここに追記 -->

---

## オーナー判断

<!-- オーナー: 採用/却下 -->

- [ ]

**メモ:**

-

---

## 次: Phase 5 残

- **5g** 旧版移行（§9.2）
- **5h** studio_dev メタサンプル（§10.4・任意）

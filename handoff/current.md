# 通信欄 — MultiRoleStudio Phase 5b 追補（議事録 Markdown）

| 項目 | 値 |
|---|---|
| Phase | 5b 追補（議事録 .md 派生 — §7.3） |
| 対象コミット | 本コミット予定 |
| 状態 | `phase5b_md_done` |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` |

---

## Composer → オーナー

Phase 5b 追補。JSON 正本に加え Markdown 派生を同時保存。ボタンは `議事録 (.json + .md)` に統合。

### 追補内容

- `document_to_markdown` — JSON から人間向け `.md` を生成
- 1クリックで `.json` + `.md` 同時保存、Git コミット対象も両方
- design §7.3 二層出力、§8.5 ボタンラベル更新

### 手動確認

```bash
PYTHONPATH=. pytest tests/parity/test_minutes.py -q
python MultiRoleStudioWeb.py --org nokuru
# セッションタブ → 議事録 (.json + .md) → minutes/<org>/*.json と *.md
```

---

## オーナー判断

- [ ] 本コミット
- [ ] Phase 5c（成果物採用 §7.6）着手 OK

---

## 次: Phase 5c（成果物採用）

design.md §7.6 / §8.5 #6 — sandbox → 作業ツリー + Git

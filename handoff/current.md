# 通信欄 — MultiRoleStudio Phase 5d-a（user_context コア）

| 項目 | 値 |
|---|---|
| Phase | 5d-a（user_context — 付録D） |
| 状態 | `phase5d_a_done`（コミット前） |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` 付録D |

---

## Composer → オーナー

Phase 5d-a 実装。`my_context.md` をプロンプトに注入し、セッション単位で ON/OFF 可能にした。

### 実装内容

- `studio/user_context.py` — 読込・有効判定
- `studio/prompts.py` — §5.1 #4 注入（組織コンテキスト直後）
- `studio/engine.py` — `generation.user_context` 記録
- `MultiRoleStudio.py` — `--no-user-context`
- `MultiRoleStudioWeb.py` — チャットタブ「ユーザーコンテキスト」トグル
- `user_context/my_context.example.md`
- `tests/parity/test_user_context.py`

### 手動確認

```bash
cp user_context/my_context.example.md user_context/my_context.md
# my_context.md を編集
PYTHONPATH=. pytest tests/parity/test_user_context.py -q
python MultiRoleStudioWeb.py --org solo
# トグル ON/OFF で応答差を確認
python MultiRoleStudio.py --org solo --topic "テスト" --no-user-context --stream off
```

---

## 次: Phase 5d-b

D.7〜D.8 — 更新案生成・承認マージ、要約版

## オーナー判断

- [ ] 本コミット
- [ ] 5d-b 着手 OK

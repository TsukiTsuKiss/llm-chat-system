# 通信欄 — Phase 5g 旧版移行（§9.2）

| 項目 | 値 |
|---|---|
| Phase | 5g |
| 状態 | `done` |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` §9.2 / §9.0 |

---

## 実施内容

- タグ `legacy-ui-pre-migration` — 移行前スナップショット
- `Chat.py` / `ChatWeb.py` / `MultiRoleChat.py` / `MultiRoleChatWeb.py` → `legacy/`
- `legacy/README.md` — 起動方法・タグ参照
- `MyPedia.py` / legacy テスト — `legacy.*` import に更新
- `README.md` / `design.md` §9.0 — 5g ✅

### 起動（legacy）

```bash
python -m legacy.Chat
python -m legacy.ChatWeb
python -m legacy.MultiRoleChat --org creative_org --demo
python -m legacy.MultiRoleChatWeb --org tech_startup
```

---

## 次: Phase 5 残

- **5h** studio_dev メタサンプル（§10.4・任意）

---

## オーナー判断

- [ ] **採用** — 5g 完了確認

**メモ:**

- タグ `legacy-ui-pre-migration` は `origin` にプッシュ済み

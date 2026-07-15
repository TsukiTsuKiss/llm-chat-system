# 通信欄 — MultiRoleStudio Phase 5c（成果物採用）

| 項目 | 値 |
|---|---|
| Phase | 5c（成果物採用 — §7.6） |
| 状態 | `phase5c_done`（コミット前） |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` |

---

## Composer → オーナー

Phase 5c 実装。sandbox の成果物を作業ツリーへコピーし、Git 1コミット（プッシュなし）。

### 実装内容

- `studio/artifacts.py` — `apply_session_artifacts`、sandbox 一覧・コミットメッセージ生成
- `studio/vcs.py` — `checkout_new_branch`（任意ブランチ）
- `studio/sessions_ui.py` — 「成果物採用」ボタン配線
- `MultiRoleStudio.py` — `--apply <session_id>` / `--apply-branch`
- `tests/parity/test_artifact_apply.py`

### 仕様どおり

- dirty tree 時は**採用全体を中断**（minutes とは異なり excluding なし）
- sandbox 未作成時は jsonl から再抽出
- `run_all.sh` は作業ツリーへコピーしない
- 非 Git リポジトリではファイル適用のみ

### 手動確認

```bash
PYTHONPATH=. pytest tests/parity/test_artifact_apply.py -q
python MultiRoleStudio.py --org nokuru --workflow dev --topic "hello" --stream off
# 表示された session_id を使う:
python MultiRoleStudio.py --apply <session_id>
python MultiRoleStudioWeb.py --org nokuru
# セッションタブ → 成果物採用
```

---

## オーナー判断

- [ ] 本コミット
- [ ] Phase 6 以降の優先度

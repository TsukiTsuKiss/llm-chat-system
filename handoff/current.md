# 通信欄 — MultiRoleStudio クイズ・割り込み改善

| 項目 | 値 |
|---|---|
| Phase | 5e 追補 |
| 状態 | コミット済み（次 PR / push 待ち） |
| 依頼元 | Composer（Cursor Agent） |
| 正本 | `docs/MultiRoleStudio/design.md` §6.7 / §10.2 |

---

## Composer → オーナー

クイズ workflow の実運用で見つかった不具合を修正し、nokuru サンプルとドキュメントを整備。

### 本コミットに含むもの

- `studio/engine.py` — parallel step へ `turn_prior` 伝播、割り込みマーカー action 自動注入
- `studio/web_ui.py` — 割り込み返答をチャット履歴に表示
- `studio/settings_ui.py` — 設定タブをチャットの組織/workflow と同期
- `organizations/nokuru/config.json` — `quiz` バインディング（hinata / satsuki, kaede）
- `tests/parity/` — parallel prior / Web 割り込み表示 / nokuru quiz 利用可能
- `docs/MultiRoleStudio/design.md` / `README.md` — **クイズ・割り込みのサンプル入力表**

### クイズ試行（Web UI）

1. `python MultiRoleStudioWeb.py --org nokuru`
2. ワークフロー `quiz` を選択
3. 初回: `光の三原色は何？ 出題前に回答形式を確認して`
4. 割り込み返答: `選択肢4択でお願い`
5. satsuki / kaede の並列回答 → hinata 採点まで完走を確認

---

## 次: Phase 5 残

- サンプル整備 / 旧版移行（§9.2）

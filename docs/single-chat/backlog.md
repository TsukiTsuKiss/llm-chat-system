# Chat / ChatWeb バックログ

更新日: 2026-06-24

---

## ✅ 完了済み（最近）

- [x] `ai_assistants_config.json` 導入（JSON-first 読み込み、CSV フォールバック）
- [x] ChatWeb: プロバイダーごとのモデル選択ドロップダウン
- [x] ChatWeb: ログ・まとめのツリー表示パネル
- [x] ChatWeb: まとめの保存（`save_summary_to_file` 呼び出し）
- [x] ChatWeb: セッションごとの CSV ログ自動保存 (`_log_store` / `_write_log`)
- [x] ChatWeb: まとめファイル名に親ログ名を埋め込み (`_from_<log_stem>`)
- [x] ChatWeb: ログ再開時に `_log_store` をセット（同一 CSV への追記）
- [x] `_build_log_tree`: `_from_` サフィックスによる確実な紐付け＋タイムスタンプ比較フォールバック
- [x] ボタン名「ログ再開」→「ログ・まとめ読込」

---

## 📋 未着手・検討中

### Chat.py

| 優先度 | 内容 | メモ |
|---|---|---|
| 中 | `conversation_log_filename` の未定義ケースを確認・保護 | main() のコードパスによっては未定義の可能性 |

### ChatWeb.py

| 優先度 | 内容 | メモ |
|---|---|---|
| 高 | キーワード検索（ログ・まとめ対象） | ファイルが増えてきたときに必須 |
| 中 | ファイル添付・画像送信 | マルチモーダル対応モデル（GPT-4o など）向け |
| 低 | ログ一覧のページネーション | 件数が多くなったときのUX改善 |

### MultiRoleChat.py

→ [workflow-nesting-homework.md](../multi-role-chat/workflow-nesting-homework.md) を参照

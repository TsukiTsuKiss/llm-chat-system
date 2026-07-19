# パリティチェックリスト（§9.2 抜粋）

> 移行完了の定義。自動判定は `tests/parity/` の pytest。

## 機能 parity

- [ ] ワークフロー: serial / parallel / loop（反復 + 打ち切り）
- [ ] 会議進行（モデレーター）→ `workflows/meeting.json`
- [ ] クイズ → `workflows/quiz.json`
- [ ] ロール間会話（max_turns）→ ワークフロー定義
- [ ] トークン・コスト集計（model_costs.csv）
- [ ] ワークフロー最終コード → sandbox/（§7.5）
- [ ] Markdown ログ（Mermaid・応答時間）
- [ ] 温度非対応モデルへのフォールバック
- [ ] ストリーミング（CLI / Web）
- [x] ファイル添付（Web）
- [x] 組織・ワークフロー Web 編集

## studio_dev での使い方

1. **architect**（meeting）— タスク分解・Phase 判断
2. **implementer + reviewer**（dev）— sandbox にコード案 → judge ループ
3. オーナー — `--apply` または手動採用（§7.6）
4. 気づき — user_context 更新案（付録D.7）

## 注意

- 旧 `organizations/*/roles/*.txt` 形式は Studio 非互換（新形式で作り直し）
- design 全文の毎回注入は避ける（要約 + corpus + `--files`）

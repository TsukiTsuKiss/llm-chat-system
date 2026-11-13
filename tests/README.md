# テスト

pytest で実行します。API キーは不要です（LLM は mock を使います）。

```bash
python -m pytest tests -q                      # 全件
python -m pytest tests/parity -v               # MultiRoleStudio（エンジン・Web UI・音声・成果物など）
python -m pytest tests/parity/test_repo_organizations.py -v   # 組織・人材・ワークフローの参照整合性
```

## 構成

| パス | 内容 |
|---|---|
| `tests/parity/` | MultiRoleStudio 本体のテスト |
| `tests/parity/test_repo_organizations.py` | 同梱の組織・人材が schema に通ること、`talent_ids` / `workflow_bindings` / `default_workflow` の参照先が存在すること、`model_mapping.example.json` がメンバーを過不足なく含むこと |
| `tests/test_api_error_retry.py` | API エラーの検出とリトライ |
| `tests/test_quota.py` | 無料枠の集計と案内 |
| `tests/test_currency.py` / `test_model_costs.py` | 費用の通貨・単価 |
| `tests/test_ai_model_sync.py` | `ai_model_sync.py`（モデル一覧の同期） |

組織や人材を追加・統合したときは、`test_repo_organizations.py` で参照の抜けを確認できます。

# MultiRoleStudio サンプルデータ（design.md §10.5）

意図したデモ用の固定会話・議事録。ランタイム出力（`sessions/` / `minutes/`）とは別に Git 管理する。

| パス | 内容 |
|---|---|
| `sessions/nokuru_camp_planning.jsonl` | nokuru + `meeting` + 「秋キャンプの行き先」（mock 生成・`【結論】` で 1 反復終了） |
| `minutes/nokuru/camp_planning.json` | 上記セッションに対応する期待議事録 |

**参照セッション ID**: `20260714_120000`（議事録 `source_sessions` および parity 試験で `sessions/` にコピーして使用）

## 再生成（開発者向け）

```bash
STUDIO_MOCK_MARKER='【結論】' python -m pytest tests/parity/test_samples.py::test_regenerate_sample_session_matches_committed -v
```

手動で mock セッションを走らせる場合:

```bash
# organizations/nokuru/model_mapping.json を mock にしたうえで
STUDIO_MOCK_MARKER='【結論】' python MultiRoleStudio.py --org nokuru --workflow meeting --topic "秋キャンプの行き先" --stream off --no-user-context
```

生成後、`samples/sessions/nokuru_camp_planning.jsonl` と `session_end.log_path` を更新し、議事録 JSON を合わせて commit する。

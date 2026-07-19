# MultiRoleStudio 設計要約（corpus / RAG 用）

> design.md の抜粋。全文は `--files docs/MultiRoleStudio/design.md` で添付する。
> 設計とズレたら **このファイルを手動更新**（自動追記しない）。

## 正本と構成

- 設計正本: `docs/MultiRoleStudio/design.md`
- エンジン: `studio/`（legacy / Chat / MultiRoleChat から **import 禁止**）
- 定義: `talents/`, `organizations/*/config.json`, `workflows/*.json`, `schemas/`
- 実行ログ: `sessions/*.jsonl`（不変の証跡）

## Phase スコープ（§1.5）

- 同一リポジトリで開発。旧版は `legacy/` に移行済み（Phase 5g）
- 共有: `ai_assistants_config.json`, `model_costs.csv`
- Git ignore: `model_mapping.json`, `studio_config.json`, `sessions/`, `sandbox/`, `user_context/my_context.md`

## プロンプト注入順（§5.1）

1. talent personality + system_prompt
2. organization mission / culture / common_directives / role_directives
3. workflow slot / action
4. user_context（有効時）
5. user_context_rag（Phase 6 以降）

## dev ワークフロー（§10.2 / workflows/dev.json）

- implementer → reviewer → judge ループ（最大5反復）
- 成果物は sandbox に抽出（§7.5）。採用は `--apply` または手動（§7.6）

## エラーコード（抜粋）

- E102: スキーマ違反
- E201: talent 未定義
- E202: model_mapping 欠落
- E205: workflow_bindings が talent_ids と不一致

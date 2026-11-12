# Legacy UI（Chat / MultiRoleChat）

Phase 5g で `legacy/` に移行しました。日常利用は **MultiRoleStudio**（`MultiRoleStudio.py`）を使ってください。

## 起動方法

リポジトリルート（`llm-chat-system/`）から:

```bash
# 1対1チャット
python -m legacy.Chat
python -m legacy.ChatWeb

# マルチロール
python -m legacy.MultiRoleChat --org creative_org --demo
python -m legacy.MultiRoleChatWeb --org tech_startup
```

## 移行前の版を取り出す

```bash
git checkout legacy-ui-pre-migration
# または特定ファイルだけ
git show legacy-ui-pre-migration:Chat.py
```

## 新しいプロバイダー設定について

`ai_assistants_config.json` の `model_param` / `system_param` / `base_url` / `api_key_env` は Studio 専用です。旧版は読みません（Opper の特別扱いは旧版のコード内に残っています）。`SakuraAI` など、これらの設定が必要なプロバイダーは、旧版では動きません。

## ドキュメント

- [MultiRoleChat マニュアル](../docs/multi-role-chat/README.md)
- [Chat.py マニュアル](../docs/single-chat/README.md)
- [MultiRoleStudio 設計書](../docs/MultiRoleStudio/design.md) §9.2

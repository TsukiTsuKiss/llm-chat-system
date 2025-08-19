# テストスクリプト集

このディレクトリには、LLM Chat Systemの各機能をテストするためのスクリプトが含まれています。

## テストファイル一覧

### Windows用バッチファイル
- **quick_test.bat** - 組織設定の簡易テスト（Windows用）
- **test_organizations.bat** - 組織設定の包括的テスト（Windows用）

### 設定関連
- **test_config.py** - 設定ファイルの診断とテストツール
- **test_organizations.py** - 組織別設定の検証スクリプト

### 機能関連  
- **test_workflow_logging.py** - ワークフローログ機能のテスト
- **test_auto_programming.py** - 自動プログラミング機能のテスト
- **test_scenario.py** - シナリオ機能のテスト
- **test_final_code_saving.py** - コード保存機能のテスト

## 実行方法

### Windows環境
```cmd
REM 簡易テスト実行
tests\quick_test.bat

REM 包括的テスト実行  
tests\test_organizations.bat
```

### Linux/Unix環境
```bash
cd llm-chat-system
python tests/test_config.py          # 設定ファイル検証
python tests/test_organizations.py   # 組織設定検証
python tests/test_workflow_logging.py # ワークフローテスト
```

## 注意事項

- テスト実行時は適切なAI設定が必要です
- 一部のテストはAPIキーとネットワーク接続が必要です
- テスト実行により実際のAPIコールが発生する場合があります
- BATファイルはプロジェクトルートから実行される想定で作成されています

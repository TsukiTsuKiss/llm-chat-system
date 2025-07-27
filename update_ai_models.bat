@echo off
chcp 65001 > nul
echo ================================
echo AI Assistants モデル更新スクリプト
echo ================================
echo.

echo 実行前の設定確認:
if exist ai_assistants_config.csv (
    echo [✓] ai_assistants_config.csv が存在します
    echo.
    echo 現在の設定:
    type ai_assistants_config.csv
    echo.
) else (
    echo [!] ai_assistants_config.csv が見つかりません
    echo.
)

echo 環境変数の確認:
if defined OPENAI_API_KEY (
    echo [✓] OPENAI_API_KEY: 設定済み
) else (
    echo [!] OPENAI_API_KEY: 未設定
)

if defined GOOGLE_API_KEY (
    echo [✓] GOOGLE_API_KEY: 設定済み
) else (
    echo [!] GOOGLE_API_KEY: 未設定
)

if defined GROQ_API_KEY (
    echo [✓] GROQ_API_KEY: 設定済み
) else (
    echo [!] GROQ_API_KEY: 未設定
)

if defined MISTRAL_API_KEY (
    echo [✓] MISTRAL_API_KEY: 設定済み
) else (
    echo [!] MISTRAL_API_KEY: 未設定
)

if defined TOGETHER_API_KEY (
    echo [✓] TOGETHER_API_KEY: 設定済み
) else (
    echo [!] TOGETHER_API_KEY: 未設定
)

if defined ANTHROPIC_API_KEY (
    echo [✓] ANTHROPIC_API_KEY: 設定済み
) else (
    echo [!] ANTHROPIC_API_KEY: 未設定
)

echo.
echo ================================
echo 更新スクリプトを実行します...
echo ================================
echo.

python update_ai_config.py

echo.
echo ================================
echo 更新後の設定:
echo ================================
if exist ai_assistants_config.csv (
    type ai_assistants_config.csv
) else (
    echo [!] 設定ファイルが見つかりません
)

echo.
echo 完了しました。何かキーを押してください...
pause > nul

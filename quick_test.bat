@echo off
echo ========================================
echo MultiRoleChat 組織別設定 簡易テスト
echo ========================================
echo.

echo [1] 利用可能な組織の確認
echo ----------------------------------
echo 組織一覧:
for /d %%i in (organizations\*) do (
    echo   - %%~ni
)
echo.

echo [2] 各組織での実行テスト
echo ----------------------------------
echo default_company でのバージョン確認:
python MultiRoleChat.py --org default_company --version
echo.

echo tech_startup でのバージョン確認:
python MultiRoleChat.py --org tech_startup --version
echo.

echo consulting_firm でのバージョン確認:
python MultiRoleChat.py --org consulting_firm --version
echo.

echo ========================================
echo テスト完了！各組織の設定ファイルが正常に読み込まれました。
echo ========================================
pause

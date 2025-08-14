@echo off
echo ========================================
echo MultiRoleChat 組織別設定テストスクリプト
echo ========================================
echo.

REM 利用可能な組織一覧を表示
echo [テスト1] 利用可能な組織の確認
echo ----------------------------------
echo 利用可能な組織:
for /d %%i in (organizations\*) do (
    echo   - %%~ni
)
echo.

REM 各組織の設定ファイル存在確認
echo [テスト2] 設定ファイルの存在確認
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\config.json" (
        echo [OK] %%~ni: config.json 存在
    ) else (
        echo [NG] %%~ni: config.json 不存在
    )
)
echo.

REM 各組織のrolesフォルダ存在確認
echo [テスト3] rolesフォルダの存在確認
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\roles" (
        echo [OK] %%~ni: rolesフォルダ 存在
    ) else (
        echo [NG] %%~ni: rolesフォルダ 不存在
    )
)
echo.

REM JSONファイルの構文チェック（Pythonを使用）
echo [テスト4] JSON構文チェック
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\config.json" (
        echo %%~ni の設定ファイルをチェック中...
        python -c "import json; json.load(open('%%i\\config.json', 'r', encoding='utf-8')); print('[OK] %%~ni: JSON構文 正常')" 2>nul || echo [NG] %%~ni: JSON構文 エラー
    )
)
echo.

REM 必須ロールファイルの存在確認
echo [テスト5] 必須ロールファイルの存在確認
echo ----------------------------------
set required_roles=secretary.txt planner.txt programmer.txt analyst.txt
for /d %%i in (organizations\*) do (
    echo %%~ni:
    for %%r in (%required_roles%) do (
        if exist "%%i\roles\%%r" (
            echo   [OK] %%r
        ) else (
            echo   [NG] %%r
        )
    )
    echo.
)

REM MultiRoleChat.pyのヘルプ表示テスト
echo [テスト6] MultiRoleChat.py ヘルプ表示テスト
echo ----------------------------------
echo MultiRoleChat.py --help の実行結果:
python MultiRoleChat.py --config "organizations\default_company\config.json" --help 2>nul || echo [NG] MultiRoleChat.py の実行に失敗
echo.

REM 設定ファイル指定テスト（ドライラン）
echo [テスト7] 設定ファイル指定テスト（ドライラン）
echo ----------------------------------
for /d %%i in (organizations\*) do (
    echo %%~ni の設定でバージョン情報を表示:
    python MultiRoleChat.py --config "%%i\config.json" --version 2>nul || echo [NG] %%~ni: 設定ファイル読み込みエラー
    echo.
)

echo ========================================
echo テスト完了
echo ========================================
pause

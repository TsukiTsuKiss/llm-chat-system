@echo off
echo ========================================
echo MultiRoleChat Organization Quick Test
echo ========================================
echo.

echo [1] Available Organizations
echo ----------------------------------
echo Organization List:
for /d %%i in (..\organizations\*) do (
    echo   - %%~ni
)
echo.

echo [2] Test Execution for Each Organization  
echo ----------------------------------
echo Version check with default_company:
cd ..
python MultiRoleChat.py --org default_company --version
cd tests
echo.

echo [3] Quick Workflow Test
echo ----------------------------------
echo Testing project_planning workflow:
cd ..
python MultiRoleChat.py --org default_company --workflow project_planning --topic "Quick test execution"
cd tests
echo.

echo ========================================
echo Test Completed
echo ========================================
pause

@echo off
echo ========================================
echo MultiRoleChat Organization Test Script
echo ========================================
echo.

REM Display available organizations
echo [Test 1] Available Organizations Check
echo ----------------------------------
echo Available Organizations:
for /d %%i in (..\organizations\*) do (
    echo   - %%~ni
)
echo.

echo [Test 2] Organization Structure Validation
echo ----------------------------------
cd ..
python tests\test_organizations.py
cd tests
echo.

echo [Test 3] Configuration File Validation  
echo ----------------------------------
cd ..
python tests\test_config.py
cd tests
echo.

echo ========================================
echo All Tests Completed
echo ========================================
pause

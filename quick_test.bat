@echo off
echo ========================================
echo MultiRoleChat �g�D�ʐݒ� �ȈՃe�X�g
echo ========================================
echo.

echo [1] ���p�\�ȑg�D�̊m�F
echo ----------------------------------
echo �g�D�ꗗ:
for /d %%i in (organizations\*) do (
    echo   - %%~ni
)
echo.

echo [2] �e�g�D�ł̎��s�e�X�g
echo ----------------------------------
echo default_company �ł̃o�[�W�����m�F:
python MultiRoleChat.py --org default_company --version
echo.

echo tech_startup �ł̃o�[�W�����m�F:
python MultiRoleChat.py --org tech_startup --version
echo.

echo consulting_firm �ł̃o�[�W�����m�F:
python MultiRoleChat.py --org consulting_firm --version
echo.

echo ========================================
echo �e�X�g�����I�e�g�D�̐ݒ�t�@�C��������ɓǂݍ��܂�܂����B
echo ========================================
pause

@echo off
echo ========================================
echo MultiRoleChat �g�D�ʐݒ�e�X�g�X�N���v�g
echo ========================================
echo.

REM ���p�\�ȑg�D�ꗗ��\��
echo [�e�X�g1] ���p�\�ȑg�D�̊m�F
echo ----------------------------------
echo ���p�\�ȑg�D:
for /d %%i in (organizations\*) do (
    echo   - %%~ni
)
echo.

REM �e�g�D�̐ݒ�t�@�C�����݊m�F
echo [�e�X�g2] �ݒ�t�@�C���̑��݊m�F
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\config.json" (
        echo [OK] %%~ni: config.json ����
    ) else (
        echo [NG] %%~ni: config.json �s����
    )
)
echo.

REM �e�g�D��roles�t�H���_���݊m�F
echo [�e�X�g3] roles�t�H���_�̑��݊m�F
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\roles" (
        echo [OK] %%~ni: roles�t�H���_ ����
    ) else (
        echo [NG] %%~ni: roles�t�H���_ �s����
    )
)
echo.

REM JSON�t�@�C���̍\���`�F�b�N�iPython���g�p�j
echo [�e�X�g4] JSON�\���`�F�b�N
echo ----------------------------------
for /d %%i in (organizations\*) do (
    if exist "%%i\config.json" (
        echo %%~ni �̐ݒ�t�@�C�����`�F�b�N��...
        python -c "import json; json.load(open('%%i\\config.json', 'r', encoding='utf-8')); print('[OK] %%~ni: JSON�\�� ����')" 2>nul || echo [NG] %%~ni: JSON�\�� �G���[
    )
)
echo.

REM �K�{���[���t�@�C���̑��݊m�F
echo [�e�X�g5] �K�{���[���t�@�C���̑��݊m�F
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

REM MultiRoleChat.py�̃w���v�\���e�X�g
echo [�e�X�g6] MultiRoleChat.py �w���v�\���e�X�g
echo ----------------------------------
echo MultiRoleChat.py --help �̎��s����:
python MultiRoleChat.py --config "organizations\default_company\config.json" --help 2>nul || echo [NG] MultiRoleChat.py �̎��s�Ɏ��s
echo.

REM �ݒ�t�@�C���w��e�X�g�i�h���C�����j
echo [�e�X�g7] �ݒ�t�@�C���w��e�X�g�i�h���C�����j
echo ----------------------------------
for /d %%i in (organizations\*) do (
    echo %%~ni �̐ݒ�Ńo�[�W��������\��:
    python MultiRoleChat.py --config "%%i\config.json" --version 2>nul || echo [NG] %%~ni: �ݒ�t�@�C���ǂݍ��݃G���[
    echo.
)

echo ========================================
echo �e�X�g����
echo ========================================
pause

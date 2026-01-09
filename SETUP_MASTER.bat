@echo off
chcp 65001 >nul
title VE3 - Setup Master (Voice to Excel)

:: Use pushd for UNC path support
pushd "%~dp0"

echo ============================================
echo   VE3 TOOL - SETUP MAY CHU (MASTER)
echo   Dung cho: run_excel.bat, run_edit.bat
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python chua duoc cai dat!
    echo         Tai tai: https://www.python.org/downloads/
    echo         Nho tick "Add Python to PATH" khi cai!
    popd
    pause
    exit /b 1
)
echo [OK] Python da cai

:: Install core dependencies
echo.
echo [1/3] Cai thu vien co ban...
pip install pyyaml openpyxl requests pillow pyperclip -q

:: Install Whisper (for voice to SRT)
echo.
echo [2/3] Cai Whisper (Voice to SRT)...
echo       (Co the mat 5-10 phut)
pip install openai-whisper -q

:: Check/Setup FFmpeg
echo.
echo [3/3] Kiem tra FFmpeg...
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    :: Check if FFmpeg exists in tools folder
    if exist "tools\ffmpeg\ffmpeg.exe" (
        echo [OK] Tim thay FFmpeg trong tools\ffmpeg\
        echo.
        echo [!] Them vao PATH vinh vien...
        setx PATH "%CD%\tools\ffmpeg;%PATH%" >nul 2>&1
        set "PATH=%CD%\tools\ffmpeg;%PATH%"
        echo [OK] Da them vao PATH
    ) else (
        echo [!] Chua co FFmpeg!
        echo.
        echo     Cach 1: Tai va giai nen vao tools\ffmpeg\
        echo            https://www.gyan.dev/ffmpeg/builds/
        echo.
        echo     Cach 2: Cai bang winget:
        echo            winget install ffmpeg
        echo.
        echo     Sau do chay lai SETUP_MASTER.bat
    )
) else (
    echo [OK] FFmpeg da co trong PATH
)

echo.
echo ============================================
echo   HOAN TAT SETUP MAY CHU!
echo ============================================
echo.
echo   Cac lenh co the chay:
echo   - run_excel.bat  : Tao Excel tu voice
echo   - run_edit.bat   : Ghep video MP4
echo.
echo ============================================

popd
pause

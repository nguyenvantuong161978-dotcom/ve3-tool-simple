@echo off
chcp 65001 >nul
title VE3 - Switch Branch

echo ============================================
echo   VE3 TOOL - CHUYEN BRANCH
echo ============================================
echo.

:: Ask for branch
set /p BRANCH="Nhap ten branch (vd: claude/fix-video-reload-DtCEu): "

if "%BRANCH%"=="" (
    echo [ERROR] Chua nhap ten branch!
    pause
    exit /b 1
)

:: Check if git is available
git --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Dang chuyen bang Git...
    git fetch origin %BRANCH%
    git checkout %BRANCH% 2>nul || git checkout -b %BRANCH% origin/%BRANCH%
    git pull origin %BRANCH%
    goto :done
)

:: Fallback: Use PowerShell to download branch
echo [*] Git khong co, dung PowerShell...
echo [*] Dang tai branch: %BRANCH%

:: Replace / with - for URL
set "BRANCH_URL=%BRANCH:/=-%"

:: Download zip from GitHub branch
powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/criggerbrannon-hash/ve3-tool-simple/archive/refs/heads/%BRANCH%.zip' -OutFile 'update.zip' }"

if not exist "update.zip" (
    echo [ERROR] Khong the tai branch: %BRANCH%
    echo         Kiem tra lai ten branch!
    pause
    exit /b 1
)

:: Extract
echo [*] Dang giai nen...
powershell -Command "Expand-Archive -Path 'update.zip' -DestinationPath 'update_temp' -Force"

:: Find extracted folder and copy
echo [*] Dang cap nhat files...
for /D %%d in (update_temp\*) do (
    xcopy /E /Y /I "%%d\*" "." >nul 2>&1
)

:: Cleanup
echo [*] Don dep...
del /Q "update.zip" 2>nul
rmdir /S /Q "update_temp" 2>nul

:done
echo.
echo ============================================
echo   [OK] DA CHUYEN SANG: %BRANCH%
echo ============================================
echo.

pause

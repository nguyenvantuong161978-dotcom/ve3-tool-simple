@echo off
chcp 65001 >nul
title VE3 - Switch Branch

echo ============================================
echo   VE3 TOOL - CHUYEN BRANCH
echo ============================================
echo.

:: Show current
echo Branch hien tai:
git branch --show-current
echo.

:: Ask for branch
set /p BRANCH="Nhap ten branch (vd: claude/fix-video-reload-DtCEu): "

if "%BRANCH%"=="" (
    echo [ERROR] Chua nhap ten branch!
    pause
    exit /b 1
)

echo.
echo [*] Dang chuyen sang: %BRANCH%

:: Fetch and checkout
git fetch origin %BRANCH%
git checkout %BRANCH% 2>nul || git checkout -b %BRANCH% origin/%BRANCH%
git pull origin %BRANCH%

echo.
echo [OK] Da chuyen sang branch: %BRANCH%
echo.
git log -1 --format="Phien ban: %%h - %%s"
echo.

pause

@echo off
chcp 65001 >nul
title VE3 - Update

echo ============================================
echo   VE3 TOOL - CAP NHAT
echo ============================================
echo.

:: Pull latest
echo [*] Dang cap nhat...
git pull

echo.
echo [OK] Hoan tat!
echo.
git log -1 --format="Phien ban: %%h - %%s"
echo.

pause

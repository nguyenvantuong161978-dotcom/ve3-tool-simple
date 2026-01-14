@echo off
chcp 65001 >nul
title VE3 - Update

echo ============================================
echo   VE3 TOOL - CAP NHAT
echo ============================================
echo.

:: Check if git is available
git --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Dang cap nhat bang Git...
    git pull
    goto :done
)

:: Fallback: Use PowerShell to download
echo [*] Git khong co, dung PowerShell...
echo [*] Dang tai phien ban moi tu GitHub...

:: Download zip from GitHub
powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/criggerbrannon-hash/ve3-tool-simple/archive/refs/heads/main.zip' -OutFile 'update.zip' }"

if not exist "update.zip" (
    echo [ERROR] Khong the tai xuong!
    pause
    exit /b 1
)

:: Extract
echo [*] Dang giai nen...
powershell -Command "Expand-Archive -Path 'update.zip' -DestinationPath 'update_temp' -Force"

:: Copy files (preserve local config)
echo [*] Dang cap nhat files...
if exist "update_temp\ve3-tool-simple-main" (
    xcopy /E /Y /I "update_temp\ve3-tool-simple-main\*" "." >nul 2>&1
)

:: Cleanup
echo [*] Don dep...
del /Q "update.zip" 2>nul
rmdir /S /Q "update_temp" 2>nul

:done
echo.
echo ============================================
echo   [OK] CAP NHAT HOAN TAT!
echo ============================================
echo.

pause

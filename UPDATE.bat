@echo off
chcp 65001 >nul
pushd "%~dp0"

echo ========================================
echo   VE3 Tool - CAP NHAT
echo ========================================
python UPDATE.py

popd
pause

@echo off
cd /d "%~dp0"
echo ============================================
echo   VE3 SERVER v4.0 - Web Dashboard
echo   http://localhost:5000/
echo ============================================
echo.
python -u server/app.py %*
pause

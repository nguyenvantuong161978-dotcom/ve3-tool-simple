@echo off
cd /d "%~dp0"
python -u server/start_server.py %*
pause

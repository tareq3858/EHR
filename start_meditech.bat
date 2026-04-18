@echo off
title Meditech EHR
cd /d "%~dp0"
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000"
python app.py
pause

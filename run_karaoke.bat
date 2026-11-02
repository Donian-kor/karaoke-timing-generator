@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%1"=="" (
    start /min "" "%~f0" minimized
    exit /b
)
if not exist ".venv\Scripts\python.exe" (
    echo .venv 가 없습니다. 먼저 python -m venv .venv 후 패키지를 설치하세요.
    pause
    exit /b 1
)
.\.venv\Scripts\python.exe karaoke_gui.py
if errorlevel 1 pause
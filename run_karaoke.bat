@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo .venv not found. Please run: python -m venv .venv
    pause
    exit /b 1
)
.\.venv\Scripts\python.exe karaoke_gui.py
if errorlevel 1 pause

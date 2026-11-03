@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo .venv 가 없습니다.
    pause
    exit /b 1
)
set MODEL_NAME=large-v3
set COMPUTE_TYPE=int8
.\.venv\Scripts\python.exe -m uvicorn stt_server:app --host 127.0.0.1 --port 8000
pause
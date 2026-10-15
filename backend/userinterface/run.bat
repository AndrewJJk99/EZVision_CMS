@echo off
chcp 65001 >nul
setlocal
if not defined UI_API_PORT set "UI_API_PORT=18000"

set "PY=%~dp0..\..\.venv\Scripts\python.exe"
cd /d "%~dp0"

netstat -ano | find ":%UI_API_PORT% " | find "LISTENING" >nul
if not errorlevel 1 (
  echo UI API가 이미 %UI_API_PORT% 포트에서 실행 중입니다.
  echo 그래서 이 창이 바로 닫혔습니다. 새로 시작하려면 기존 python 프로세스를 종료하세요.
  pause
  exit /b 0
)

"%PY%" main.py
if errorlevel 1 (
  echo.
  echo UI API 시작에 실패했습니다.
  pause
)

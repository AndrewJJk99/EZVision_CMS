@echo off
chcp 65001 >nul

call C:\Users\User\miniconda3\Scripts\activate.bat C:\Users\User\miniconda3
call conda activate ezvision
cd /d "%~dp0"

netstat -ano | find ":8000" | find "LISTENING" >nul
if not errorlevel 1 (
  echo UI API가 이미 8000 포트에서 실행 중입니다.
  echo 그래서 이 창이 바로 닫혔습니다. 새로 시작하려면 기존 python 프로세스를 종료하세요.
  pause
  exit /b 0
)

python main.py
if errorlevel 1 (
  echo.
  echo UI API 시작에 실패했습니다.
  pause
)

@echo off

set "PY=%~dp0..\..\.venv\Scripts\python.exe"
cd /d "%~dp0"
"%PY%" main.py
if errorlevel 1 pause

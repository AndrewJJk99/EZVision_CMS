@echo off

call "%~dp0..\.venv\Scripts\activate.bat"
cd /d "%~dp0"
python main.py

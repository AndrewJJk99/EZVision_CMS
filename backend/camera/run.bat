@echo off
cd /d "%~dp0"

call C:\Users\User\miniconda3\Scripts\activate.bat C:\Users\User\miniconda3
call conda activate ezvision
python "%~dp0main.py"
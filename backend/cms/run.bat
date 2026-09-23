@echo off

call C:\Users\User\miniconda3\Scripts\activate.bat C:\Users\User\miniconda3
call conda activate ezvision
cd /d "%~dp0"
python main.py

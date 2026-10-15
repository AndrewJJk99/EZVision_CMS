@echo off
setlocal
if not defined PORT set "PORT=13000"

cd /d "%~dp0"
npm start

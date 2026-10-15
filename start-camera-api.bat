@echo off
setlocal
set "CAMERA_API_PORT=17070"
set "UI_API_URL=http://localhost:18000"
call "%~dp0backend\camera\run.bat"

@echo off
setlocal
set "CMS_API_PORT=17060"
set "CAMERA_URL=http://localhost:17070"
call "%~dp0backend\cms\run.bat"

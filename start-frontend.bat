@echo off
setlocal
set "PORT=13000"
set "REACT_APP_CAMERA_API=http://localhost:17070"
set "REACT_APP_CMS_API=http://localhost:17060"
set "REACT_APP_UI_API=http://localhost:18000"
call "%~dp0frontend\run.bat"

@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 1
call tools\windows_env.bat
if errorlevel 1 goto failed
".venv\Scripts\python.exe" main.py %*
set "BNE_EXIT=%errorlevel%"
goto finished

:failed
set "BNE_EXIT=1"

:finished
popd
if not "%BNE_EXIT%"=="0" if not defined CI pause
exit /b %BNE_EXIT%

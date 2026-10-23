@echo off
rem Called by start.bat/build.bat with the repository as the working directory.
set "PYGAME_HIDE_SUPPORT_PROMPT=1"
if exist ".venv\Scripts\python.exe" goto check_python

where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 exit /b 1
goto check_python

:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -m venv .venv
if errorlevel 1 exit /b 1

:check_python
".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info < (3, 10))"
if errorlevel 1 goto missing_python
".venv\Scripts\python.exe" -c "import pygame; assert pygame.IS_CE" >nul 2>nul
if not errorlevel 1 exit /b 0
".venv\Scripts\python.exe" -m pip install -e "."
exit /b %errorlevel%

:missing_python
echo.
echo BNE requires Python 3.10 or newer.
echo Install Python with the "Add Python to PATH" option, then try again.
exit /b 1

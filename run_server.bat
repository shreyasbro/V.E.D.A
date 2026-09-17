@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. MOBILE API GATEWAY LAUNCHER
:: Hosts local REST & SSE API for the Android V.E.D.A. app.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"
cd /d "%PROJECT_ROOT%"

set "PYTHON_EXE="
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if "%PYTHON_EXE%"=="" if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"

echo Starting V.E.D.A. Mobile API Gateway...
"%PYTHON_EXE%" -m veda.server --port 8765
pause

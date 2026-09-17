@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. PORTABLE STANDALONE BUILD SCRIPT
:: Automatically derives PROJECT_ROOT from script directory.
:: Never depends on current command prompt working directory.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"

cd /d "%PROJECT_ROOT%"

set "LOGS_DIR=%PROJECT_ROOT%\logs"
if not exist "%LOGS_DIR%" (
    mkdir "%LOGS_DIR%" >nul 2>nul
)
set "LOG_FILE=%LOGS_DIR%\build_error.log"

:: Discover Python environment dynamically
set "PYTHON_EXE="

:: 1. Check project-local virtual environments
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)
if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
    goto :PYTHON_FOUND
)

:: 2. Check system PATH python
where python >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where python') do (
        set "PYTHON_EXE=%%I"
        goto :PYTHON_FOUND
    )
)

:: 3. Check Windows py launcher
where py >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where py') do (
        set "PYTHON_EXE=%%I"
        goto :PYTHON_FOUND
    )
)

:PYTHON_FOUND
if "%PYTHON_EXE%"=="" (
    echo.
    echo ========================================================
    echo  V.E.D.A. BUILD ERROR
    echo ========================================================
    echo  Python was not found in PATH or local virtual environment.
    echo.
    echo  Expected:
    echo   Project-local .venv OR Python available in PATH.
    echo.
    echo  Detected project:
    echo   "%PROJECT_ROOT%"
    echo ========================================================
    echo [%date% %time%] ERROR: Python not found for build in %PROJECT_ROOT% >> "%LOG_FILE%"
    echo.
    echo Please install Python 3.10+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)

:: Delegate orchestration to portable build.py with full diagnostics
"%PYTHON_EXE%" "%PROJECT_ROOT%\build.py"
set "BUILD_STATUS=!ERRORLEVEL!"

if !BUILD_STATUS! NEQ 0 (
    echo.
    echo ========================================================
    echo  [ERROR] Build failed with exit code !BUILD_STATUS!.
    echo ========================================================
    echo [%date% %time%] ERROR: build.py failed with exit code !BUILD_STATUS! >> "%LOG_FILE%"
    pause
    exit /b !BUILD_STATUS!
)

echo.
echo ========================================================
echo  [SUCCESS] Standalone V.E.D.A. build complete.
echo ========================================================
pause
exit /b 0

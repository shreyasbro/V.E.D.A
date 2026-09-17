@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. PORTABLE 1-CLICK LAUNCHER
:: Determines PROJECT_ROOT from script directory (%~dp0).
:: Fully portable across any folder, drive, or user directory.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"

cd /d "%PROJECT_ROOT%"

set "LOGS_DIR=%PROJECT_ROOT%\logs"
if not exist "%LOGS_DIR%" (
    mkdir "%LOGS_DIR%" >nul 2>nul
)
set "LOG_FILE=%LOGS_DIR%\startup_error.log"

:: Verify main entry point exists
if not exist "%PROJECT_ROOT%\main.py" (
    echo.
    echo ========================================================
    echo  V.E.D.A. STARTUP ERROR
    echo ========================================================
    echo  Missing entry point: main.py
    echo  Detected project: "%PROJECT_ROOT%"
    echo ========================================================
    echo [%date% %time%] ERROR: Entry point main.py missing in %PROJECT_ROOT% >> "%LOG_FILE%"
    echo.
    pause
    exit /b 1
)

:: Priority 1: Project-local virtual environments (.venv or venv)
if exist "%PROJECT_ROOT%\.venv\Scripts\pythonw.exe" (
    set "PY_RUNNER=%PROJECT_ROOT%\.venv\Scripts\pythonw.exe"
    set "PY_CHECK=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    goto :VERIFY_AND_RUN
)
if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PY_RUNNER=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    set "PY_CHECK=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    goto :VERIFY_AND_RUN
)
if exist "%PROJECT_ROOT%\venv\Scripts\pythonw.exe" (
    set "PY_RUNNER=%PROJECT_ROOT%\venv\Scripts\pythonw.exe"
    set "PY_CHECK=%PROJECT_ROOT%\venv\Scripts\python.exe"
    goto :VERIFY_AND_RUN
)
if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PY_RUNNER=%PROJECT_ROOT%\venv\Scripts\python.exe"
    set "PY_CHECK=%PROJECT_ROOT%\venv\Scripts\python.exe"
    goto :VERIFY_AND_RUN
)

:: Priority 2: PATH pythonw
where pythonw >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where pythonw') do (
        set "PY_RUNNER=%%I"
        set "PY_CHECK=%%I"
        goto :VERIFY_AND_RUN
    )
)

:: Priority 3: PATH python
where python >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where python') do (
        set "PY_RUNNER=%%I"
        set "PY_CHECK=%%I"
        goto :VERIFY_AND_RUN
    )
)

:: Priority 4: Windows py launcher
where py >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    set "PY_RUNNER=py"
    set "PY_CHECK=py"
    goto :VERIFY_AND_RUN
)

:: Python not detected anywhere
echo.
echo ========================================================
echo  V.E.D.A. STARTUP ERROR
echo ========================================================
echo  Python was not found.
echo.
echo  Expected:
echo   Project-local .venv OR Python available in PATH.
echo.
echo  Detected project:
echo   "%PROJECT_ROOT%"
echo.
echo  Detected Python:
echo   NOT FOUND
echo ========================================================
echo [%date% %time%] ERROR: Python not found in local venv or PATH >> "%LOG_FILE%"
echo.
echo Please install Python 3.10+ from https://www.python.org/
echo and ensure "Add python.exe to PATH" is checked.
echo.
pause
exit /b 1

:VERIFY_AND_RUN
:: Test that Python executable actually runs
"%PY_CHECK%" --version >nul 2>nul
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================================
    echo  V.E.D.A. STARTUP ERROR
    echo ========================================================
    echo  Python interpreter detected but failed execution test.
    echo  Interpreter: "%PY_RUNNER%"
    echo ========================================================
    echo [%date% %time%] ERROR: Interpreter %PY_RUNNER% failed execution test >> "%LOG_FILE%"
    echo.
    pause
    exit /b 1
)

:: Launch V.E.D.A. cleanly
start "" "%PY_RUNNER%" "%PROJECT_ROOT%\main.py"
exit /b 0

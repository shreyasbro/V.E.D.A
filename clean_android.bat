@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. ANDROID CLEAN SCRIPT
:: Cleans Gradle caches and intermediate build directories.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"
set "ANDROID_DIR=%PROJECT_ROOT%\android"

echo Cleaning Android build artifacts...
if exist "%ANDROID_DIR%\gradlew.bat" (
    cd /d "%ANDROID_DIR%"
    call gradlew.bat clean
)

if exist "%ANDROID_DIR%\.gradle" (
    rmdir /s /q "%ANDROID_DIR%\.gradle" >nul 2>nul
)
if exist "%ANDROID_DIR%\app\build" (
    rmdir /s /q "%ANDROID_DIR%\app\build" >nul 2>nul
)

echo Clean complete.
exit /b 0

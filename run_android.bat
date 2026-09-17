@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. ANDROID INSTALL & RUN SCRIPT
:: Deploys and launches APK via ADB to connected device.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"
set "APK_PATH=%PROJECT_ROOT%\dist\android\V.E.D.A.-Android-debug.apk"

:: Build if APK does not exist
if not exist "%APK_PATH%" (
    echo APK not found in dist\android. Running build_android.bat...
    call "%PROJECT_ROOT%\build_android.bat"
    if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
)

:: Locate ADB
set "ADB_EXE="
where adb >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where adb') do (
        if not defined ADB_EXE set "ADB_EXE=%%I"
    )
)
if "%ADB_EXE%"=="" (
    if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
        set "ADB_EXE=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    )
)

if "%ADB_EXE%"=="" (
    echo [ERROR] ADB not found. Please enable USB debugging or start an Android emulator.
    pause
    exit /b 1
)

echo [ADB] Checking connected devices...
"%ADB_EXE%" devices

echo.
echo [ADB] Installing V.E.D.A. to connected Android device...
"%ADB_EXE%" install -r "%APK_PATH%"

if !ERRORLEVEL! EQU 0 (
    echo.
    echo [ADB] Launching V.E.D.A. on device...
    "%ADB_EXE%" shell am start -n com.veda.assistant.debug/com.veda.assistant.MainActivity
    echo [SUCCESS] App launched.
) else (
    echo [ERROR] Failed to install APK on device.
)

pause
exit /b 0

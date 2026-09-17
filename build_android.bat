@echo off
setlocal enabledelayedexpansion

:: ========================================================
:: V.E.D.A. ANDROID STANDALONE BUILD SCRIPT
:: Builds APK from command-line without Android Studio.
:: Dynamic path resolution - Works from any folder / drive.
:: ========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR:~0,-1%"
set "ANDROID_DIR=%PROJECT_ROOT%\android"
set "DIST_ANDROID=%PROJECT_ROOT%\dist\android"

echo ========================================================
echo  V.E.D.A. ANDROID BUILD PIPELINE (NO ANDROID STUDIO)
echo ========================================================
echo  Project Root: "%PROJECT_ROOT%"
echo  Android Dir:  "%ANDROID_DIR%"
echo ========================================================

:: 1. Ensure dist output directory exists
if not exist "%DIST_ANDROID%" (
    mkdir "%DIST_ANDROID%" >nul 2>nul
)

:: 2. Detect Java / JDK
set "JAVA_EXE="
where java >nul 2>nul
if !ERRORLEVEL! EQU 0 (
    for /f "delims=" %%I in ('where java') do (
        if not defined JAVA_EXE set "JAVA_EXE=%%I"
    )
)

if "%JAVA_EXE%"=="" (
    echo [ERROR] Java/JDK was not detected in PATH.
    echo Please ensure OpenJDK 17 or higher is installed and on PATH.
    pause
    exit /b 1
)

:: 3. Detect Android SDK
set "TARGET_SDK="
if defined ANDROID_HOME (
    if exist "%ANDROID_HOME%" set "TARGET_SDK=%ANDROID_HOME%"
)
if "%TARGET_SDK%"=="" if defined ANDROID_SDK_ROOT (
    if exist "%ANDROID_SDK_ROOT%" set "TARGET_SDK=%ANDROID_SDK_ROOT%"
)
if "%TARGET_SDK%"=="" (
    if exist "%LOCALAPPDATA%\Android\Sdk" set "TARGET_SDK=%LOCALAPPDATA%\Android\Sdk"
)

if "%TARGET_SDK%"=="" (
    echo [ERROR] Android SDK was not found in ANDROID_HOME or %LOCALAPPDATA%\Android\Sdk.
    pause
    exit /b 1
)

echo [OK] Detected Android SDK: "%TARGET_SDK%"

:: Write local.properties dynamically
(
    set "ESCAPED_SDK=%TARGET_SDK:\=\\%"
    echo sdk.dir=!ESCAPED_SDK!
) > "%ANDROID_DIR%\local.properties"

:: 4. Locate Gradle Wrapper
if not exist "%ANDROID_DIR%\gradlew.bat" (
    echo [ERROR] Gradle Wrapper gradlew.bat not found in "%ANDROID_DIR%".
    pause
    exit /b 1
)

:: 5. Execute Gradle Build
echo.
echo [BUILD] Building V.E.D.A. Android Debug APK...
cd /d "%ANDROID_DIR%"
call gradlew.bat :app:assembleDebug

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo [ERROR] Android APK build failed. Check the error output above.
    pause
    exit /b 1
)

:: 6. Copy Built APK to dist/android/
set "SRC_APK=%ANDROID_DIR%\app\build\outputs\apk\debug\app-debug.apk"
set "DEST_APK=%DIST_ANDROID%\V.E.D.A.-Android-debug.apk"

if exist "%SRC_APK%" (
    copy /y "%SRC_APK%" "%DEST_APK%" >nul
    echo.
    echo ========================================================
    echo  [SUCCESS] APK BUILD COMPLETE!
    echo ========================================================
    echo  Output APK: "%DEST_APK%"
    echo ========================================================
) else (
    echo [ERROR] Built APK not found at "%SRC_APK%".
    pause
    exit /b 1
)

exit /b 0

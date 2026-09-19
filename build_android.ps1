$ErrorActionPreference = "Stop"

Write-Host "=================================================="
Write-Host " Building Standalone V.E.D.A. for Android "
Write-Host "=================================================="

$androidDir = Join-Path $PSScriptRoot "android"
if (-not (Test-Path $androidDir)) {
    throw "Android directory not found at $androidDir"
}

Push-Location $androidDir
try {
    Write-Host "`n[1/3] Running Gradle assembleDebug..."
    cmd.exe /c ".\gradlew.bat assembleDebug"

    $outputApk = Join-Path $androidDir "app\build\outputs\apk\debug\app-debug.apk"
    if (Test-Path $outputApk) {
        $finalApkName = "V.E.D.A.-Android.apk"
        $destApk = Join-Path $PSScriptRoot $finalApkName
        Copy-Item -Path $outputApk -Destination $destApk -Force
        
        $apkItem = Get-Item $destApk
        $sizeMb = [math]::Round($apkItem.Length / 1MB, 2)

        Write-Host "`n[2/3] Computing SHA-256 Checksum..."
        $sha = (Get-FileHash -Path $destApk -Algorithm SHA256).Hash.ToLower()
        "$sha  $finalApkName" | Out-File -FilePath "$destApk.sha256" -Encoding ascii

        Write-Host "`n=================================================="
        Write-Host " BUILD SUCCESSFUL"
        Write-Host " Output APK: $destApk"
        Write-Host " Size: $sizeMb MB"
        Write-Host " SHA-256: $sha"
        Write-Host "=================================================="
    } else {
        throw "APK was not found at $outputApk"
    }
} finally {
    Pop-Location
}

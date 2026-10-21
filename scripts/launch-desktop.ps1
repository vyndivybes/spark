# Desktop entry point: keep startup diagnostics and display failures.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $env:LOCALAPPDATA 'SPARK\logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory "desktop-launch-$PID.log"
Start-Transcript -Path $logPath -Append | Out-Null
try {
    & (Join-Path $root 'start-spark.ps1') -Desktop
} catch {
    Write-Output ('SPARK startup failed: ' + $_.Exception.Message)
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "SPARK could not start. See the startup log:`n$logPath`n`n$($_.Exception.Message)",
        'SPARK startup', 'OK', 'Error') | Out-Null
    exit 1
} finally {
    Stop-Transcript | Out-Null
}

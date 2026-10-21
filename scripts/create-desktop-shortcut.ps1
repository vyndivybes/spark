# Create (or refresh) the SPARK desktop shortcut.
# Uses the desktop PowerShell entry point and the SPARK application icon.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'SPARK.lnk'
$target = Join-Path $root 'scripts\launch-desktop.ps1'
$scriptHost = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$icon = Join-Path $root 'public\spark.ico'

if (-not (Test-Path -LiteralPath $target)) { throw "Launcher not found: $target" }
if (-not (Test-Path -LiteralPath $scriptHost)) { throw "Windows PowerShell not found: $scriptHost" }
if (-not (Test-Path -LiteralPath $icon)) {
    Write-Host 'Icon missing; generating public/spark.ico...' -ForegroundColor Cyan
    & node (Join-Path $root 'scripts\make_spark_icon.mjs')
}

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = $scriptHost
$sc.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $target + '"'
$sc.WorkingDirectory = $root
$sc.IconLocation = $icon + ',0'
$sc.Description = 'SPARK - Immersive AI Workstation'
$sc.WindowStyle = 7
$sc.Save()
Write-Host "SPARK shortcut ready: $lnkPath" -ForegroundColor Green

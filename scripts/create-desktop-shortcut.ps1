# Create (or refresh) the SPARK desktop shortcut.
# Points at Launch-SPARK.vbs and uses public/spark.ico as its icon.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'SPARK.lnk'
$target = Join-Path $root 'Launch-SPARK.vbs'
$icon = Join-Path $root 'public\spark.ico'

if (-not (Test-Path -LiteralPath $target)) { throw "Launcher not found: $target" }
if (-not (Test-Path -LiteralPath $icon)) {
    Write-Host 'Icon missing; generating public/spark.ico...' -ForegroundColor Cyan
    & node (Join-Path $root 'scripts\make_spark_icon.mjs')
}

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = $target
$sc.WorkingDirectory = $root
$sc.IconLocation = $icon
$sc.Description = 'SPARK - Immersive AI Workstation'
$sc.WindowStyle = 1
$sc.Save()
Write-Host "SPARK shortcut ready: $lnkPath" -ForegroundColor Green

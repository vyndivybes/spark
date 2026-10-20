# Remove the SPARK desktop shortcut and (optionally) generated icon assets.
# Default: removes the shortcut only. Pass -PurgeAssets to also delete
# public/spark.ico and public/spark.png.
param(
    [switch]$PurgeAssets
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'SPARK.lnk'

if (Test-Path -LiteralPath $lnkPath) {
    Remove-Item -LiteralPath $lnkPath -Force
    Write-Host "Removed shortcut: $lnkPath" -ForegroundColor Green
} else {
    Write-Host "No shortcut found at $lnkPath (nothing to do)." -ForegroundColor Yellow
}

if ($PurgeAssets) {
    foreach ($f in @('public\spark.ico', 'public\spark.png')) {
        $p = Join-Path $root $f
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force
            Write-Host "Removed asset: $p" -ForegroundColor Green
        }
    }
}

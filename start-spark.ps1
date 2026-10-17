# Launch SPARK on Windows. This script installs open-source assets only on request.
# No paid services, API credentials, permissions, or OS security policies are modified.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows before launching SPARK.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or newer before launching SPARK.' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python and add it to PATH, or set SPARK_PYTHON to its full path.' }
if (-not (Test-Path '.\\vendor\\holo-gestures\\holo.html') -or -not (Test-Path '.\\vendor\\brain-map\\build.py')) {
  Write-Host 'Installing pinned MIT HOLO and Brain Map source and assets...' -ForegroundColor Cyan
  & git submodule update --init --recursive
  if ($LASTEXITCODE -ne 0) { throw 'The experience submodules could not be installed.' }
}
if (-not (Test-Path '.\\node_modules\\electron')) {
  Write-Host 'Installing SPARK Node dependencies...' -ForegroundColor Cyan
  & npm.cmd ci --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'SPARK dependency installation failed.' }
}
Write-Host 'Launching SPARK · ADA engine + HOLO Deck + Neural Atlas' -ForegroundColor Green
& npm.cmd run dev
if ($LASTEXITCODE -ne 0) { throw 'SPARK failed to start. Review the displayed error.' }

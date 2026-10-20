# Build a self-contained, relocatable Python runtime for packaged SPARK builds.
#
# Downloads the official Windows "embeddable" Python distribution, bootstraps
# pip into it, and installs requirements-runtime.txt into a local Lib\site-packages
# that the embedded python311._pth points at. Output: python-runtime\ which
# electron-builder ships as an extraResource and electron/main.js prefers.
#
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-python-runtime.ps1
# Options:
#   -PythonVersion 3.11.9   (default; must be an embeddable release)
#   -Force                  (rebuild even if python-runtime already exists)
param(
    [string]$PythonVersion = '3.11.9',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$outDir = Join-Path $root 'python-runtime'
$reqFile = Join-Path $root 'requirements-runtime.txt'
$tmp = Join-Path $env:TEMP ("spark-pyrt-" + [guid]::NewGuid().ToString('N'))

if (Test-Path -LiteralPath $outDir) {
    if (-not $Force) {
        Write-Host "python-runtime already exists. Use -Force to rebuild." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item -LiteralPath $outDir -Recurse -Force
}

$rel = ($PythonVersion -split '\.')[0..1] -join ''
$zipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$zip = Join-Path $tmp 'python-embed.zip'
$getPip = Join-Path $tmp 'get-pip.py'

New-Item -ItemType Directory -Path $tmp -Force | Out-Null
try {
    Write-Host "Downloading $zipUrl" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
    Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $getPip -UseBasicParsing

    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $outDir -Force

    # The embeddable dist disables site-packages; re-enable it and add Lib\site-packages.
    $pth = Join-Path $outDir "python$rel._pth"
    @(
        "python$rel.zip",
        ".",
        "Lib\site-packages",
        "",
        "# Uncomment to run site.main() automatically",
        "import site"
    ) | Set-Content -LiteralPath $pth -Encoding ASCII

    $py = Join-Path $outDir 'python.exe'
    Write-Host 'Bootstrapping pip...' -ForegroundColor Cyan
    & $py $getPip --no-warn-script-location

    if (-not (Test-Path -LiteralPath $reqFile)) {
        throw "Missing requirements file: $reqFile"
    }
    Write-Host "Installing runtime requirements into $outDir\Lib\site-packages" -ForegroundColor Cyan
    & $py -m pip install --no-warn-script-location --upgrade -r $reqFile

    & $py -c "import fastapi, uvicorn, socketio, cv2, mediapipe; print('runtime OK')"

    $sizeMb = [Math]::Round(((Get-ChildItem $outDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host "Python runtime ready: $outDir ($sizeMb MB)" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

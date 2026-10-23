# Runs only read-only OpenJarvis 16-feature source checks on native Windows.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $root '.venv\Scripts\python.exe'
$python = if (Test-Path $venv) { $venv } else { 'python' }
Push-Location $root
try {
    & $python backend\spark_openjarvis_readiness.py --root $root
    if ($LASTEXITCODE -ne 0) { throw 'OpenJarvis readiness inventory failed.' }
    & $python -m unittest discover -s tests -p test_spark_openjarvis_readiness.py -v
    if ($LASTEXITCODE -ne 0) { throw 'OpenJarvis readiness inventory tests failed.' }
}
finally { Pop-Location }

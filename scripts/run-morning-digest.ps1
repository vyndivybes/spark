# Interactive-user background job. This launches no voice or camera session.
param([string]$WorkspaceRoot, [switch]$TestDelivery)
$ErrorActionPreference = 'Stop'
if ($WorkspaceRoot) { $env:SPARK_WORKSPACE_DATA_ROOT = $WorkspaceRoot }
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$logs = Join-Path $env:LOCALAPPDATA 'SPARK\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
Set-Location -LiteralPath $root
try {
    # Windows PowerShell treats native stderr as ErrorRecord objects. MCP's
    # normal stderr diagnostics must not terminate an otherwise healthy job.
    $arguments = @('-B', ('"' + (Join-Path $PSScriptRoot 'run-morning-digest.py') + '"'))
    if ($TestDelivery) { $arguments += '--test-delivery' }
    $process = Start-Process -FilePath $python -WindowStyle Hidden -Wait -PassThru `
        -ArgumentList $arguments `
        -WorkingDirectory $root `
        -RedirectStandardOutput (Join-Path $logs "morning-digest-$PID.log") `
        -RedirectStandardError (Join-Path $logs "morning-digest-$PID-error.log")
    exit $process.ExitCode
} catch {
    # Provider response text and credential material do not belong in this log.
    Add-Content -LiteralPath (Join-Path $logs 'morning-digest-schedule-error.log') 'Scheduled digest runner failed.'
    exit 1
}

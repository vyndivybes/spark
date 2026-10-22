param(
    [Parameter(Mandatory=$true)][string]$IsolationRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$isolation = [IO.Path]::GetFullPath($IsolationRoot)
$original = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $repo) 'spark'))
if ($repo -eq $original -or $isolation -eq $repo -or $isolation.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase) -or $isolation.StartsWith($original + '\', [StringComparison]::OrdinalIgnoreCase) -or $isolation -eq $original) {
    throw 'Commissioning must use a separate checkout and data directory.'
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Select an installed Python interpreter.' }
$electron = Join-Path $repo 'node_modules\electron\dist\electron.exe'
$pidFile = Join-Path $isolation 'electron-root-pid.txt'
if ($Restart -and (Test-Path -LiteralPath $pidFile)) {
    $rootId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $snapshot = @(Get-CimInstance Win32_Process)
    $rootProcess = $snapshot | Where-Object ProcessId -eq $rootId
    if ($rootProcess) {
        if ($rootId -in 24824,16360 -or $rootProcess.ExecutablePath -ne $electron -or $rootProcess.CommandLine -notlike ('*--user-data-dir=' + $isolation + '\appdata\spark*')) {
            throw 'Recorded PID is not the owned commissioning Electron process. No process was stopped.'
        }
        $ids = @($rootId)
        do {
            $next = @($snapshot | Where-Object { $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids } | ForEach-Object ProcessId)
            $ids += $next
        } while ($next.Count)
        if (24824 -in $ids -or 16360 -in $ids) { throw 'Protected original PID found. No process was stopped.' }
        [array]::Reverse($ids)
        foreach ($processId in $ids) {
            $old = $snapshot | Where-Object ProcessId -eq $processId
            $live = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
            if ($live -and $live.CreationDate -eq $old.CreationDate) {
                $handle = Get-Process -Id $processId -ErrorAction SilentlyContinue
                Stop-Process -Id $processId -Force
                # Stop-Process returns before Windows releases the singleton lock.
                if ($handle -and -not $handle.WaitForExit(10000)) { throw 'Owned process did not exit; launch cancelled.' }
            }
        }
    }
}
foreach ($port in 8010,9223) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is occupied. No foreign process will be stopped." }
}
New-Item -ItemType Directory -Path (Join-Path $isolation 'logs') -Force | Out-Null
$tokenFile = Join-Path $isolation 'workspace-token.txt'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    ([BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()) | Set-Content -LiteralPath $tokenFile
}
$env:SPARK_WORKSPACE_TOKEN = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
if ($env:SPARK_WORKSPACE_TOKEN -notmatch '^[a-f0-9]{64}$') { throw 'Invalid isolated workspace token.' }
$env:SPARK_BACKEND_PORT = '8010'
$env:SPARK_WORKSPACE_DATA_ROOT = Join-Path $isolation 'data'
$env:SPARK_NOTES_DIR = Join-Path $isolation 'notes'
$env:SPARK_MCP_SERVERS = '{}'
$env:SPARK_PYTHON = $PythonPath
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:NODE_ENV = 'production'
$arguments = @(('"' + $repo + '"'), ('"--user-data-dir=' + (Join-Path $isolation 'appdata\spark') + '"'), '--remote-debugging-port=9223', '--no-first-run', '--no-default-browser-check')
$process = Start-Process -FilePath $electron -ArgumentList $arguments -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $isolation 'logs\electron-out.log') -RedirectStandardError (Join-Path $isolation 'logs\electron-err.log')
$process.Id | Set-Content -LiteralPath $pidFile
# Return promptly. Backend readiness and exact cockpit target are separate checks.
[pscustomobject]@{RootPid=$process.Id; BackendPort=8010; DebugPort=9223; HostMcpInherited=$false}

# Start the existing OmniRoute installation for SPARK's configured OpenCode
# provider. Credentials and upstream account configuration remain with OmniRoute.
$ErrorActionPreference = 'Stop'
$gatewayDirectory = Join-Path $env:APPDATA 'npm\node_modules\omniroute'
$gatewayScript = Join-Path $gatewayDirectory 'bin\omniroute.mjs'
if (-not (Test-Path -LiteralPath $gatewayScript)) {
    Write-Warning 'The configured OpenCode gateway is not installed. Other SPARK integrations can still start.'
    return
}
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 20128 -ErrorAction SilentlyContinue)
if ($listeners.Count) {
    foreach ($listener in $listeners) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if (-not $owner -or $owner.Name -ne 'node.exe' -or
            $owner.CommandLine -notlike "*$gatewayDirectory*" -or
            $listener.LocalAddress -notin @('127.0.0.1', '::1')) {
            Write-Warning 'OpenCode gateway port is occupied by another listener. No process was stopped.'
            return
        }
    }
    Write-Host 'Existing local OpenCode gateway is listening.'
    return
}
$node = (Get-Command node.exe -ErrorAction Stop).Source
$logs = Join-Path $env:LOCALAPPDATA 'SPARK\logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$previousBind = $env:OMNIROUTE_SERVER_HOST
try {
    $env:OMNIROUTE_SERVER_HOST = '127.0.0.1'
    $process = Start-Process -FilePath $node -WindowStyle Hidden -PassThru `
        -ArgumentList @(('"' + $gatewayScript + '"'), 'serve', '--headless', '--no-open', '--no-tray', '--no-recovery') `
        -RedirectStandardOutput (Join-Path $logs "opencode-gateway-$PID.log") `
        -RedirectStandardError (Join-Path $logs "opencode-gateway-$PID-error.log")
    Write-Host "Local OpenCode gateway started with PID $($process.Id); readiness is checked by the model client."
} finally {
    if ($null -eq $previousBind) {
        Remove-Item Env:OMNIROUTE_SERVER_HOST -ErrorAction SilentlyContinue
    } else {
        $env:OMNIROUTE_SERVER_HOST = $previousBind
    }
}

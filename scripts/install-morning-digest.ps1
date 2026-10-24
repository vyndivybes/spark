param(
    [ValidatePattern('^([01]\d|2[0-3]):[0-5]\d$')]
    [string]$TimeIST = '07:00'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run-morning-digest.ps1'
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'SPARK Python environment is missing.' }
$taskName = 'SPARK Morning Digest'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$scriptHost = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"'
$ownedArguments = $arguments
$workspaceRoot = if ($env:SPARK_WORKSPACE_DATA_ROOT) { $env:SPARK_WORKSPACE_DATA_ROOT } else { Join-Path $env:LOCALAPPDATA 'SPARK\workspace' }
$workspaceRoot = [IO.Path]::GetFullPath($workspaceRoot)
$arguments += ' -WorkspaceRoot "' + $workspaceRoot + '"'
if ($existing -and ($existing.Actions.Count -ne 1 -or
    $existing.Actions[0].Execute -ne $scriptHost -or -not $existing.Actions[0].Arguments.StartsWith($ownedArguments))) {
    throw 'A different task already uses this name. No existing scheduled task was changed.'
}
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $scriptHost -Argument $arguments -WorkingDirectory $root
$todayIST = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::Now, 'India Standard Time').ToString('yyyy-MM-dd')
$date = [datetime]::ParseExact(($todayIST + ' ' + $TimeIST), 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
$boundary = [DateTimeOffset]::new([datetime]::SpecifyKind($date, [DateTimeKind]::Unspecified), [TimeSpan]::FromMinutes(330))
$trigger = New-ScheduledTaskTrigger -Daily -At $date
$trigger.StartBoundary = $boundary.ToString('yyyy-MM-ddTHH:mm:sszzz')
$settings = New-ScheduledTaskSettingsSet -Priority 5 -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$task = New-ScheduledTask -Action $action -Principal $principal -Trigger $trigger -Settings $settings `
    -Description 'Read-only SPARK Morning Digest and local desktop notification. Requires the signed-in Windows user; catches up after a missed run.'
& $python -B (Join-Path $PSScriptRoot 'run-morning-digest.py') --set-time $TimeIST
if ($LASTEXITCODE -ne 0) { throw 'Could not save the Morning Digest schedule.' }
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
& $python -B (Join-Path $PSScriptRoot 'run-morning-digest.py') --mark-installed
if ($LASTEXITCODE -ne 0) { throw 'Scheduled task exists but its local registration could not be recorded.' }
Write-Output "Morning Digest scheduled for $TimeIST IST daily, using the signed-in Windows account."

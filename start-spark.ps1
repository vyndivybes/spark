# SPARK Windows launcher: isolated Python runtime, no global pip changes or paid services.
# First run installs only the documented runtime packages. Large CAD/Playwright browser
# binaries and machine-control permissions remain separate explicit choices.
param(
    [switch]$SkipBackendSetup,
    [switch]$UseArkusGeminiKey,
    [ValidateSet('gemini-3.8-live', 'gemini-3.1-flash-live-preview')]
    [string]$LiveModel = 'gemini-3.8-live',
    [ValidateSet('full', 'voice', 'cinematic', 'cinematic_tools', 'cinematic_search')]
    [string]$LiveProfile = 'cinematic',
    [switch]$EnableGoogleSearch,
    [switch]$EnableGroqVision,
    [switch]$EnableGraphiti,
    [switch]$EnableHermes,
    [switch]$EnableObsidian,
    [string]$ObsidianVault,
    [ValidateSet('browser_aec', 'native')]
    [string]$AudioTransport = 'browser_aec',
    [ValidateSet('gemini', 'groq')]
    [string]$AIProvider = 'gemini',
    [ValidateSet('openai/gpt-oss-20b', 'llama-3.1-8b-instant')]
    [string]$GroqModel = 'openai/gpt-oss-20b'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Install Git for Windows before launching SPARK.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or newer before launching SPARK.' }

function Find-SupportedPython {
    if ($env:SPARK_PYTHON) {
        if (-not (Test-Path $env:SPARK_PYTHON)) { throw 'SPARK_PYTHON does not point to an existing Python executable.' }
        return $env:SPARK_PYTHON
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        foreach ($version in @('3.12','3.11','3.13')) {
            try {
                $path = & py.exe "-$version" -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path.Trim())) { return $path.Trim() }
            } catch {}
        }
    }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $path = (Get-Command python.exe).Source
        $ok = & $path -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $path }
    }
    throw 'SPARK needs Python 3.11-3.13 (3.12 recommended). Install Python 3.12 for Windows, then rerun this script. Your Python 3.14 installation remains unchanged.'
}

function Get-SparkWorkspaceRoot {
    # Mirrors backend/server.py so the sidecars read the stores SPARK writes.
    $base = $env:LOCALAPPDATA
    if ([string]::IsNullOrWhiteSpace($base)) { $base = Join-Path $env:USERPROFILE '.spark' }
    return (Join-Path $base 'SPARK\workspace')
}

function Install-OptionalEnvironment {
    # Each optional stack gets its own virtual environment, and neither can share
    # SPARK's runtime one: graphiti-core resolves google-genai 2.x while the
    # Gemini Live path is pinned to 1.x, and hermes-agent ships 23 un-namespaced
    # top-level packages (agent, cli, tools, utils) that would shadow the backend.
    param([string]$Directory, [string]$Requirements, [string]$HostPython)
    $python = Join-Path $PSScriptRoot "$Directory\Scripts\python.exe"
    if (Test-Path -LiteralPath $python) { return $python }
    Write-Host "Creating the dedicated $Directory environment (SPARK's own environment is untouched)..." -ForegroundColor Cyan
    & $HostPython -m venv (Join-Path $PSScriptRoot $Directory)
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not create $Directory; that optional service stays unregistered."; return $null }
    & $python -m pip --disable-pip-version-check install -r (Join-Path $PSScriptRoot $Requirements)
    if ($LASTEXITCODE -ne 0) { Write-Warning "Installing $Requirements failed; that optional service stays unregistered."; return $null }
    return $python
}

function Get-SparkMcpServers {
    # Register host-configured read-only MCP services. SPARK's backend never
    # accepts executable paths from a socket; this is the only place they are set.
    param([string]$GraphitiPython, [string]$HermesPython)
    $servers = [ordered]@{}

    $graphifyMcp = Join-Path $PSScriptRoot '.venv\Scripts\graphify-mcp.exe'
    $graphPath = Join-Path $PSScriptRoot 'graphify-out\graph.json'
    if (Test-Path -LiteralPath $graphifyMcp) {
        $servers['graphify'] = @{
            command    = $graphifyMcp
            args       = @('--graph', $graphPath)
            read_tools = @('query_graph')
        }
    }

    if ($GraphitiPython) {
        $workspace = Get-SparkWorkspaceRoot
        $servers['graphiti'] = @{
            command    = $GraphitiPython
            args       = @((Join-Path $PSScriptRoot 'backend\spark_graphiti_mcp.py'),
                           '--workspace', $workspace,
                           '--db', (Join-Path $workspace 'graphiti'))
            # refresh_project_graph is the one tool that writes, and it writes only
            # the sidecar's own Kuzu database; SPARK's stores are opened read-only.
            read_tools = @('search_temporal_facts', 'get_entity_timeline', 'graph_status', 'refresh_project_graph')
        }
    }

    if ($HermesPython) {
        $servers['hermes'] = @{
            command    = $HermesPython
            args       = @((Join-Path $PSScriptRoot 'backend\spark_hermes_mcp.py'))
            read_tools = @('hermes_learned_skills', 'hermes_memory_cards', 'hermes_learning_status')
        }
    }

    if ($servers.Count -eq 0) { return $null }
    return ($servers | ConvertTo-Json -Depth 6 -Compress)
}

$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    $hostPython = Find-SupportedPython
    Write-Host 'Creating dedicated SPARK Python environment (not modifying system Python)...' -ForegroundColor Cyan
    & $hostPython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) { throw 'Could not create SPARK Python environment.' }
}

# Explicit opt-in: reuse the user's existing local ARKUS Gemini key
# in this process only. Do not print, write or copy credentials to source.
if ($UseArkusGeminiKey -and [string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)) {
    $arkusConfig = Join-Path $env:APPDATA 'arkus\config.json'
    if (-not (Test-Path -LiteralPath $arkusConfig)) {
        throw 'The local ARKUS Gemini configuration was not found. Use backend/.env instead.'
    }
    try {
        $arkusSettings = Get-Content -LiteralPath $arkusConfig -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw 'Cannot parse ARKUS configuration. SPARK made no changes.'
    }
    if ([string]::IsNullOrWhiteSpace($arkusSettings.api_key)) {
        throw 'No Gemini API key is configured in ARKUS.'
    }
    $env:GEMINI_API_KEY = [string]$arkusSettings.api_key
    Write-Host 'SPARK Gemini credential: imported from local ARKUS configuration (process only).' -ForegroundColor Green
}
if ($AIProvider -eq 'groq' -and $GroqModel -eq 'llama-3.1-8b-instant') {
    throw 'Groq retired llama-3.1-8b-instant on 2026-08-16 for free/developer plans. Relaunch with -GroqModel openai/gpt-oss-20b.'
}
if ($AIProvider -eq 'groq' -and $AudioTransport -ne 'browser_aec') {
    throw 'Groq voice requires the existing Chromium browser_aec microphone and speaker path.'
}
if ($EnableGroqVision -and $AIProvider -ne 'groq') {
    throw 'Groq vision requires -AIProvider groq.'
}
$env:SPARK_GROQ_VISION_ENABLED = if ($EnableGroqVision) { '1' } else { '0' }
if ($EnableGroqVision) {
    Write-Warning 'Groq preview vision is ON for this launch. Each explicit camera question consumes Groq model quota. Verify your Groq project has no paid billing before use.'
}
$env:SPARK_AI_PROVIDER = $AIProvider
$env:SPARK_GROQ_MODEL = $GroqModel
if ($AIProvider -eq 'groq') {
    Write-Host "SPARK AI: Groq cloud (no Ollama, no Gemini Live)" -ForegroundColor Cyan
    Write-Warning 'Groq free-plan quotas apply. Use a Groq project without paid billing. Never place its API key in Git.'
}
$env:SPARK_LIVE_MODEL = $LiveModel
if ($LiveProfile -eq 'cinematic_search' -and -not $EnableGoogleSearch) {
    throw 'Google Search is opt-in. Add -EnableGoogleSearch only if your Google AI project is on the free tier or you accept its potential grounding charges.'
}
$env:SPARK_ENABLE_GOOGLE_SEARCH = if ($EnableGoogleSearch -and $LiveProfile -eq 'cinematic_search') { '1' } else { '0' }
if ($env:SPARK_ENABLE_GOOGLE_SEARCH -eq '1') {
    Write-Warning 'Google Search grounding is enabled for this SPARK session. On paid-tier Google AI projects, Google may bill per Search query after free monthly allowances. SPARK does not activate billing or guarantee zero cost.'
}
$env:SPARK_LIVE_PROFILE = $LiveProfile
$env:SPARK_AUDIO_TRANSPORT = $AudioTransport
Write-Host "SPARK audio: $AudioTransport" -ForegroundColor Cyan
if ($AIProvider -eq 'gemini') {
    Write-Host "SPARK Live profile: $LiveProfile (model $LiveModel)" -ForegroundColor Cyan
} else {
    Write-Host "SPARK chat model: $GroqModel; voice: Windows/Chromium local English TTS" -ForegroundColor Cyan
}

$env:SPARK_PYTHON = $venvPython
if (-not $SkipBackendSetup) {
    & $venvPython '.\scripts\runtime_preflight.py'
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing missing Python runtime dependencies locally. Optional CAD kernel and browsers are excluded.' -ForegroundColor Cyan
        & $venvPython -m pip --disable-pip-version-check install -r '.\requirements-runtime.txt'
        if ($LASTEXITCODE -ne 0) { throw 'SPARK Python package installation failed. See pip output; no global packages were changed.' }
        & $venvPython '.\scripts\runtime_preflight.py'
        if ($LASTEXITCODE -ne 0) { throw 'SPARK Python dependencies are incomplete or this Python version is unsupported.' }
    }
}

if (-not (Test-Path '.\vendor\holo-gestures\holo.html') -or -not (Test-Path '.\vendor\brain-map\build.py')) {
    Write-Host 'Installing pinned MIT HOLO and Brain Map source assets...' -ForegroundColor Cyan
    & git submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) { throw 'Original source experiences could not be installed.' }
}
if (-not (Test-Path '.\node_modules\electron')) {
    Write-Host 'Installing SPARK Node dependencies...' -ForegroundColor Cyan
    & npm.cmd ci --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'SPARK Node dependency installation failed.' }
}

# Graphify architecture graph: build once if missing so the query_spark_graph
# voice tool has a real graph to answer from. Rebuild is opt-in (see README).
if (-not (Test-Path '.\graphify-out\graph.json')) {
    Write-Host 'Building SPARK Graphify architecture graph (first run)...' -ForegroundColor Cyan
    & $venvPython -m graphify update . --code-only 2>&1 | ForEach-Object { Write-Host "[graphify] $_" }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path '.\graphify-out\graph.json')) {
        Write-Warning 'Graphify graph build failed. query_spark_graph will report "MCP unavailable" until it is rebuilt.'
    }
}
$graphitiPython = $null
$hermesPython = $null
if ($EnableGraphiti -or $EnableHermes) {
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Create the SPARK Python environment before enabling an optional sidecar.' }
}
if ($EnableGraphiti) {
    # Per-launch opt-in, like -EnableGoogleSearch: no cloud extraction happens on
    # a launch that did not ask for it, even if .venv-graphiti already exists.
    Write-Warning 'Graphiti is ON for this launch. Refreshing a project sends that project''s memory and knowledge text to Groq for fact extraction and to Gemini for embeddings, and every query is embedded by Gemini. Your existing keys are used; SPARK does not activate billing or guarantee zero cost.'
    if ([string]::IsNullOrWhiteSpace($env:GROQ_API_KEY) -or [string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)) {
        Write-Warning 'Graphiti needs GROQ_API_KEY and GEMINI_API_KEY in backend/.env. Without them it registers but reports that credentials are missing.'
    }
    $graphitiPython = Install-OptionalEnvironment -Directory '.venv-graphiti' -Requirements 'requirements-graphiti.txt' -HostPython $venvPython
    if ($graphitiPython) { Write-Host 'Graphiti ready: own environment, embedded Kuzu, telemetry off, no database server.' -ForegroundColor Cyan }
}
if ($EnableHermes) {
    $hermesPython = Install-OptionalEnvironment -Directory '.venv-hermes' -Requirements 'requirements-hermes.txt' -HostPython $venvPython
    if ($hermesPython) { Write-Host 'Hermes Agent ready: own environment, read-only journey query, no inference.' -ForegroundColor Cyan }
}
$mcpServers = Get-SparkMcpServers -GraphitiPython $graphitiPython -HermesPython $hermesPython
# These two switches are what Gemini Live reads when it builds its tool
# declarations, so a sidecar that failed to install is never advertised to the
# model. Like SPARK_ENABLE_GOOGLE_SEARCH they are set only here, only for this
# launch, and default to off.
$env:SPARK_ENABLE_GRAPHITI = if ($graphitiPython) { '1' } else { '0' }
$env:SPARK_ENABLE_HERMES = if ($hermesPython) { '1' } else { '0' }
$env:SPARK_ENABLE_OBSIDIAN = if ($EnableObsidian) { '1' } else { '0' }
if ($EnableObsidian) {
    if ($ObsidianVault) { $env:SPARK_OBSIDIAN_VAULT = $ObsidianVault }
    $vaultPath = if ($env:SPARK_OBSIDIAN_VAULT) { $env:SPARK_OBSIDIAN_VAULT } else { Join-Path $HOME 'Documents\Obsidian Vault' }
    if (Test-Path -LiteralPath $vaultPath) {
        Write-Host "Obsidian ready: vault at $vaultPath (read-only)." -ForegroundColor Cyan
    } else {
        Write-Warning "Obsidian enabled but no vault found at $vaultPath. Pass -ObsidianVault '<path>' or set SPARK_OBSIDIAN_VAULT."
    }
}
if ($mcpServers) {
    $env:SPARK_MCP_SERVERS = $mcpServers
    $registered = @()
    if ($mcpServers -match '"graphify"') { $registered += 'graphify (query_graph)' }
    if ($mcpServers -match '"graphiti"') { $registered += 'graphiti (temporal facts)' }
    if ($mcpServers -match '"hermes"') { $registered += 'hermes (learned experience)' }
    Write-Host ("MCP services registered read-only: " + ($registered -join ', ') + '.') -ForegroundColor Cyan
} else {
    Write-Warning 'No MCP service could be registered; architecture, temporal graph and Hermes queries will be unavailable.'
}

Write-Host 'Starting SPARK cockpit with original ADA, HOLO and Brain Map experiences.' -ForegroundColor Green
& npm.cmd run dev
if ($LASTEXITCODE -ne 0) { throw 'SPARK launch failed. Check the first backend error above.' }
Write-Host 'SPARK window closed normally.' -ForegroundColor Green

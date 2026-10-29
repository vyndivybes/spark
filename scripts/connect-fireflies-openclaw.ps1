# Fireflies OAuth onboarding for the existing local OpenClaw/REX Gateway.
# Run only by the owner on the Windows host. No API key required or stored here.
$ErrorActionPreference='Stop'
if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
  throw 'OpenClaw CLI is not installed on this Windows host.'
}
$server = 'fireflies'
$existing = & openclaw mcp show $server 2>$null
if ($LASTEXITCODE -ne 0) {
  & openclaw mcp add $server --url 'https://api.fireflies.ai/mcp' --transport streamable-http --include 'get_user,fireflies_get_user,get_transcripts,fireflies_get_transcripts,get_summary,fireflies_get_summary'
  if ($LASTEXITCODE -ne 0) { throw 'OpenClaw Fireflies server registration failed.' }
} else {
  Write-Host 'Fireflies MCP already registered. Existing settings preserved.'
}
Write-Host 'A browser OAuth authorization is required for this separate OpenClaw runtime.'
Write-Host 'Gateway will be stopped only for the local OAuth CLI handshake.'
& openclaw gateway stop
try {
  & openclaw mcp login $server
  if ($LASTEXITCODE -ne 0) { throw 'Fireflies OAuth authorization did not complete.' }
} finally {
  & openclaw gateway start
}
& openclaw mcp doctor $server --probe
if ($LASTEXITCODE -ne 0) { throw 'Fireflies MCP live probe did not pass. Review account authorization.' }
Write-Host 'OpenClaw Fireflies MCP probe succeeded. Restrict REX agent tool permissions before use.'

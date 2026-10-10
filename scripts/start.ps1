param(
    [ValidateRange(1,65535)][int]$Port = 5173,
    [ValidateSet('serve','build','test','ingest','check')][string]$Task = 'serve',
    [string]$Document = 'backend/knowledge/seed.json',
    [switch]$Lan,
    [string]$NodePath
)
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$nodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue
if (-not $NodePath -and $env:HAEDAP_NODE) { $NodePath = $env:HAEDAP_NODE }
if (-not $NodePath -and $nodeCommand) { $NodePath = $nodeCommand.Source }
if (-not $NodePath) { Write-Host 'Install official Node.js 24 LTS, reopen the terminal, and run scripts\start.cmd.'; exit 1 }
$env:PATH = (Split-Path -Parent $NodePath) + ';' + $env:PATH
$env:NEXT_TELEMETRY_DISABLED = '1'
& $NodePath 'scripts/check-runtime.cjs'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$major = [int]((& $NodePath -p 'process.versions.node.split(String.fromCharCode(46))[0]') | Select-Object -Last 1)
if ($major -lt 24) { Write-Host 'Node.js 24 or newer is required.'; exit 1 }
if ($Task -eq 'check') { exit 0 }
$npmCommand = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue
if (-not $npmCommand) { Write-Host 'npm.cmd was not found. Install Node.js with npm.'; exit 1 }
function Invoke-Npm([string[]]$NpmArgs) {
    & $npmCommand.Source @NpmArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath 'node_modules/next/package.json')) {
    Write-Host 'Installing dependencies (internet is required for the first installation)...'
    Invoke-Npm -NpmArgs @('ci')
}
if ($Task -eq 'serve' -or $Task -eq 'test') {
    if (-not $env:HAEDAP_UV -and (Test-Path -LiteralPath '.env')) {
        foreach ($line in Get-Content -LiteralPath '.env') {
            if ($line -match '^\s*HAEDAP_UV\s*=(.*)$') { $env:HAEDAP_UV = $Matches[1].Trim().Trim('"').Trim("'") }
        }
    }
    $uvName = if ($env:HAEDAP_UV) { $env:HAEDAP_UV } else { 'uv' }
    $uvCommand = Get-Command $uvName -CommandType Application -ErrorAction SilentlyContinue
    if (-not $uvCommand) { Write-Host 'Install uv and reopen the terminal before starting FastAPI.'; exit 1 }
    & $uvCommand.Source 'sync' '--locked' '--project' 'backend'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Task -eq 'build') { Invoke-Npm -NpmArgs @('run','build'); exit 0 }
if ($Task -eq 'test') { Invoke-Npm -NpmArgs @('test'); exit 0 }
if ($Task -eq 'ingest') { & $NodePath 'scripts/ingest.mjs' $Document; exit $LASTEXITCODE }
if ($Task -eq 'serve' -and -not (Test-Path -LiteralPath 'frontend/.next/BUILD_ID')) {
    Write-Host 'Building Next.js for the first run...'
    Invoke-Npm -NpmArgs @('run','build')
}
$runArguments = @('scripts/run.mjs')
if ($PSBoundParameters.ContainsKey('Port')) { $runArguments += @('--port',[string]$Port) }
if ($Lan) { $runArguments += '--lan' }
& $NodePath @runArguments
exit $LASTEXITCODE

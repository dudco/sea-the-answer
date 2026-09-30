param(
    [ValidateRange(1, 65535)][int]$Port = 5173,
    [ValidateSet('serve', 'test', 'ingest', 'check')][string]$Task = 'serve',
    [string]$Document = 'knowledge/seed.json',
    [switch]$Lan,
    [string]$NodePath
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# Probe native executables without PowerShell treating stderr warnings as fatal errors.
function Test-NodeRuntime([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    $probe = New-Object System.Diagnostics.Process
    $probe.StartInfo.FileName = $Executable
    $probe.StartInfo.Arguments = '"' + (Join-Path $PSScriptRoot 'scripts\check-runtime.cjs') + '"'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    $probe.StartInfo.EnvironmentVariables['ELECTRON_RUN_AS_NODE'] = '1'
    try {
        [void]$probe.Start()
        $probe.StandardOutput.ReadToEnd() | Out-Null
        $probeError = $probe.StandardError.ReadToEnd()
        $probe.WaitForExit()
        if ($probe.ExitCode -ne 0) {
            Write-Host "Skipping incompatible runtime: $Executable"
            if ($probeError) { Write-Host $probeError.Trim() }
        }
        return $probe.ExitCode -eq 0
    } catch { return $false }
    finally { $probe.Dispose() }
}

$taskArguments = @(switch ($Task) {
    'test' { @('--test') + @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'tests') -Filter '*.test.mjs' | ForEach-Object FullName) }
    'ingest' { @('scripts/ingest.mjs', $Document) }
    'check' { @('-p', 'process.version') }
    default { @('server.mjs') }
})
if ($Task -eq 'serve') {
    if ($PSBoundParameters.ContainsKey('Port')) { $taskArguments += @('--port', [string]$Port) }
    if ($Lan) { $taskArguments += '--lan' }
}
$nodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue
$candidates = @()
if ($NodePath) { $candidates += $NodePath }
if ($env:HAEDAP_NODE) { $candidates += $env:HAEDAP_NODE }
if ($nodeCommand) { $candidates += $nodeCommand.Source }
$candidates += @(
    (Join-Path $env:ProgramFiles 'nodejs\node.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\Code.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft VS Code\Code.exe')
)
$previousElectronMode = $env:ELECTRON_RUN_AS_NODE
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (Test-NodeRuntime $candidate) {
        Write-Host "Runtime: $candidate"
        if ($Task -eq 'check') { Write-Host 'SQLite + FTS5 ready' }
        $env:ELECTRON_RUN_AS_NODE = '1'
        # Piping also waits for Windows GUI executables such as Code.exe.
        $ErrorActionPreference = 'Continue'
        try {
            & $candidate @taskArguments | Out-Host
            $taskExitCode = $LASTEXITCODE
        } finally { $env:ELECTRON_RUN_AS_NODE = $previousElectronMode }
        exit $taskExitCode
    }
}
Write-Host 'No compatible runtime found. Install official Node.js 24 LTS (with SQLite FTS5), then reopen the terminal and run start.cmd.'
Write-Host 'Download: https://nodejs.org/en/download'
exit 1

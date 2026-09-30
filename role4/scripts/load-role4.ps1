param([string]$PgBin = 'C:\Program Files\PostgreSQL\18\bin', [string]$DataDir = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$data = if ($DataDir) { (Resolve-Path -LiteralPath $DataDir).Path } else { Join-Path $repo 'data/role4/2026-09-30-v2' }
$psql = Join-Path $PgBin 'psql.exe'
$line = Get-Content -LiteralPath (Join-Path $repo '.env.local') | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1
if (-not $line) { throw 'DATABASE_URL missing in .env.local' }
$uri = [uri](($line -replace '^DATABASE_URL=', '') -replace '^postgresql\+psycopg:', 'postgresql:')
if ($uri.Host -notin @('localhost','127.0.0.1')) { throw 'Only local database loading is supported.' }
$auth = $uri.UserInfo.Split(':',2)
$oldPassword = $env:PGPASSWORD
$env:PGPASSWORD = [uri]::UnescapeDataString($auth[1])
$argsPg = @('-X','-w','-h',$uri.Host,'-p',[string]$uri.Port,'-U',[uri]::UnescapeDataString($auth[0]),'-d',$uri.AbsolutePath.TrimStart('/'),'-v','ON_ERROR_STOP=1')
$tempSql = Join-Path ([IO.Path]::GetTempPath()) ('role4-load-' + [guid]::NewGuid() + '.sql')
try {
    $exists = & $psql @argsPg -Atc "SELECT count(*) FROM information_schema.schemata WHERE schema_name='role4'"
    if ($LASTEXITCODE -ne 0) { throw 'Database connection failed.' }
    if (($exists -join '').Trim() -ne '0') { throw 'role4 schema already exists; refusing to overwrite or reload.' }
    $schema = Get-Content -LiteralPath (Join-Path $repo 'docs/role4/role4_schema.sql') -Raw
    $schema = $schema -replace '(?m)^BEGIN;\s*$', '' -replace '(?m)^COMMIT;\s*$', ''
    $sql = "BEGIN;`n$schema`n"
    foreach ($table in @('source_files','vessels','synthetic_voyages','annual_reports','synthetic_noon','quality_issues')) {
        $file = $table + '.csv'
        if (-not (Test-Path -LiteralPath (Join-Path $data ($table + '.csv')))) { throw "Missing input: $table" }
        $sql += "\copy role4.$table FROM '$file' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8', NULL '');`n"
    }
    $sql += Get-Content -LiteralPath (Join-Path $repo 'docs/role4/verify_load.sql') -Raw
    $sql += "`nCOMMIT;`n"
    [IO.File]::WriteAllText($tempSql, $sql, [Text.UTF8Encoding]::new($false))
    Push-Location $data
    try {
        & $psql @argsPg -f $tempSql
        if ($LASTEXITCODE -ne 0) { throw 'Load failed; transaction rolled back.' }
    } finally { Pop-Location }
} finally {
    $env:PGPASSWORD = $oldPassword
    if (Test-Path -LiteralPath $tempSql) { Remove-Item -LiteralPath $tempSql }
}

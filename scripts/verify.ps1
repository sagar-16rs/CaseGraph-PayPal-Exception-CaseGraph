$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
New-Item -ItemType Directory -Force -Path ".data" | Out-Null

function Invoke-Checked([string]$Name, [scriptblock]$Command) {
    Write-Host "`n=== $Name ==="
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

Invoke-Checked "Python compilation" { python -m compileall -q backend evaluation validation submission scripts tests migrations }

$db = (Join-Path $Root ".data/verification.db").Replace('\','/')
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Root ".data/verification.db")
$oldDb = $env:DATABASE_URL
$env:DATABASE_URL = "sqlite:///$db"
try {
    Invoke-Checked "Alembic upgrade" { alembic upgrade head }
    Invoke-Checked "Alembic downgrade" { alembic downgrade base }
    Invoke-Checked "Alembic re-upgrade" { alembic upgrade head }
    Invoke-Checked "Repository doctor" { python scripts/doctor.py }
} finally {
    $env:DATABASE_URL = $oldDb
}

$oldAuto = $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$testFiles = Get-ChildItem tests\test_*.py | Sort-Object Name
try {
    foreach ($test in $testFiles) {
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Root ".data/casegraph.db")
        Invoke-Checked "pytest: $($test.Name)" { python -m pytest -q -p pytest_asyncio.plugin $test.FullName }
    }
} finally {
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = $oldAuto
}

if (Get-Command tsc -ErrorAction SilentlyContinue) {
    Invoke-Checked "Frontend offline TypeScript smoke" { tsc -p frontend/tsconfig.offline.json --pretty false }
} else {
    Write-Host "`nSKIP: global tsc not installed. Run: cd frontend; npm install; npm run typecheck; npm run build"
}

Invoke-Checked "Release scan" { python scripts/release_scan.py }
Write-Host "`nVERIFICATION PASS: $($testFiles.Count) isolated test files"
Write-Host "External production gates: docs/RELEASE_CHECKLIST.md"

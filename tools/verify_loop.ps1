# tools/verify_loop.ps1 — Test-Gate fuer den LightOS Loop-Modus
#
# Aufruf (aus dem Repo-Root):
#   ./tools/verify_loop.ps1                       -> Syntax-Check + VOLLE Suite (217 Tests)
#   ./tools/verify_loop.ps1 tests/test_efx_path.py  -> Syntax-Check + nur diese Tests
#
# Exit 0 = gruen, sonst rot. Headless: conftest.py setzt QT_QPA_PLATFORM=offscreen.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$TestArgs)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
$py = Join-Path $repo "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "[verify] FEHLER: venv-Python nicht gefunden: $py"; exit 2 }

Push-Location $repo
try {
    Write-Host "[verify] 1/2 Syntax-Check (compileall src) ..."
    & $py -m compileall -q src
    if ($LASTEXITCODE -ne 0) { Write-Host "[verify] SYNTAX-FEHLER"; exit 1 }

    $target = if ($TestArgs) { $TestArgs } else { @("tests/") }
    Write-Host "[verify] 2/2 pytest $($target -join ' ') ..."
    & $py -m pytest @target -q --tb=short -p no:cacheprovider -o addopts=""
    $code = $LASTEXITCODE
    if ($code -ne 0) { Write-Host "[verify] TESTS ROT (exit $code)"; exit $code }

    Write-Host "[verify] GRUEN - alles bestanden."
}
finally { Pop-Location }

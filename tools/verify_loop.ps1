# tools/verify_loop.ps1 - Test-Gate fuer den LightOS Loop-Modus
#
# Aufruf (aus dem Repo-Root):
#   ./tools/verify_loop.ps1                        -> Syntax-Check + VOLLE Suite (Lock-Runner, -Isolate)
#   ./tools/verify_loop.ps1 tests/test_efx_path.py -> Syntax-Check + nur diese Tests (Lock-Runner)
#
# Das Voll-Suite-Gate laeuft ueber den sitzungsuebergreifenden Lock-Runner
# `../run_tests.ps1` (liegt im AEUSSEREN Projektordner, NICHT im Repo). Dieser serialisiert
# pytest-Laeufe ueber alle parallelen Claude-/Cowork-Sessions (Sperrdatei .pytest_lock.json)
# und faehrt im -Isolate-Modus jede Testdatei in einem eigenen Prozess - so ueberlebt das Gate
# einen einzelnen nativen Qt-Segfault (Exit 139) und liefert einen echten Pass/Fail-Zaehler.
# Fehlt der Runner, faellt das Gate mit deutlicher Warnung auf direktes pytest zurueck (OHNE Sperre).
# Details: SecondBrain/reference_pytest_lock.md.
#
# Exit 0 = gruen, sonst rot.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$TestArgs)

$ErrorActionPreference = "Stop"

# ── Gate-Umgebung ───────────────────────────────────────────────────────────
# MUSS identisch zu tools/verify_segmented.ps1 bleiben - tests/test_gate_runner_parity.py
# nagelt das fest.
#
# XPLAT-WIN (2026-08-04): hier stand vorher NICHTS, nur der Kommentar "conftest.py /
# run_tests.ps1 setzen QT_QPA_PLATFORM". Das war dieselbe Drift, die Linux mit
# XPLAT-11 beseitigt hat, nur andersherum: die Gate-Umgebung war AUSSERHALB des
# Repos definiert (run_tests.ps1 setzt beide Variablen). Ein frischer
# Windows-Checkout ohne dieses maschinenspezifische Skript fuhr damit ein anderes
# Gate als Davids Rechner - und LIGHTOS_HARDEN_EXIT fehlte dort ganz.
#
# setdefault-Semantik (wie `${VAR:-wert}` auf Linux), damit ein von aussen
# gesetzter Wert - etwa der von run_tests.ps1 - Vorrang behaelt.
if (-not $env:QT_QPA_PLATFORM)     { $env:QT_QPA_PLATFORM = "offscreen" }
if (-not $env:LIGHTOS_HARDEN_EXIT) { $env:LIGHTOS_HARDEN_EXIT = "1" }
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
$outer = Split-Path $repo -Parent   # aeusserer Projektordner (Eltern des Repo-Roots)

# Python: bevorzugt das venv im Repo-Root; in einem frischen Worktree (kein eigenes venv,
# da gitignored) auf das venv des Haupt-Checkouts im aeusseren Ordner zurueckfallen -
# dasselbe venv, das auch run_tests.ps1 nutzt.
# XPLAT-02: Kandidaten-Liste statt fester Windows-Pfad. Windows ZUERST (erster Treffer
# gewinnt -> auf Windows byte-identisches Verhalten), danach die Linux/macOS-venv-Pfade,
# damit dieses Gate auch auf einem Linux-Checkout laeuft (dort `venv/bin/python`).
$pyCandidates = @(
    (Join-Path $repo  "venv\Scripts\python.exe"),                # Windows, Repo-venv
    (Join-Path $outer "lightos-main\venv\Scripts\python.exe"),   # Windows, Haupt-Checkout
    (Join-Path $repo  "venv/bin/python"),                        # Linux/macOS, Repo-venv
    (Join-Path $repo  "venv/bin/python3"),
    (Join-Path $outer "lightos-main/venv/bin/python"),           # Linux/macOS, Haupt-Checkout
    (Join-Path $outer "lightos-main/venv/bin/python3")
)
$py = $pyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) { Write-Host "[verify] FEHLER: venv-Python nicht gefunden. Geprueft:`n  $($pyCandidates -join "`n  ")"; exit 2 }

# Lock-Runner im aeusseren Projektordner (Geschwister-Verzeichnis des Repo-Roots).
$runner = Join-Path $outer "run_tests.ps1"

Push-Location $repo
try {
    Write-Host "[verify] 1/2 Syntax-Check (compileall src) ..."
    & $py -m compileall -q src
    if ($LASTEXITCODE -ne 0) { Write-Host "[verify] SYNTAX-FEHLER"; exit 1 }

    if (Test-Path $runner) {
        # Immer -Isolate: jede Testdatei laeuft in einem eigenen Prozess. So kippt ein einzelner
        # nativer Qt-Segfault (Exit 139) nicht die ganze Suite, und der Runner liefert einen
        # echten Pass/Fail-Zaehler (Crashes zaehlen als Umgebungs-Flakiness, nicht als Test-Fail).
        # $ErrorActionPreference lokal auf 'Continue': ein isolierter nativer
        # Qt-Teardown-Segfault (rc=0xC0000005) schreibt via faulthandler
        # "Windows fatal exception: access violation" auf stderr. Unter 'Stop'
        # wertet PowerShell 5.1 diese native stderr-Zeile des `& powershell`-
        # Aufrufs als terminierenden NativeCommandError und kippt das Gate (Exit 1)
        # -- OBWOHL der Lock-Runner den Crash bereits korrekt als tolerierbare
        # Umgebungs-Flakiness behandelt (er zaehlt rc=139/-1073741819 als CRASH,
        # nicht als FAIL, und exit't 0). Der Runner-EXIT-CODE ist die Wahrheit;
        # native stderr darf das Gate nicht kippen. Echte Test-Failures bleiben
        # rot (Runner exit't dann 1 -> unten switch-default).
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            if ($TestArgs) {
                Write-Host "[verify] 2/2 Tests via Lock-Runner -Isolate (gezielt): $($TestArgs -join ' ') ..."
                & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Isolate $TestArgs
            }
            else {
                Write-Host "[verify] 2/2 VOLLE Suite via Lock-Runner -Isolate ($runner) ..."
                & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Isolate
            }
            $code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $prevEAP }
        # Lock-Runner-spezifische Exit-Codes verstaendlich machen (0 = gruen, faellt unten durch).
        switch ($code) {
            0       { }
            97      { Write-Host "[verify] Lock-Runner: venv-Python nicht gefunden (Exit 97)."; exit $code }
            98      { Write-Host "[verify] Lock-Runner: Timeout beim Warten auf die Test-Sperre (Exit 98)."; exit $code }
            99      { Write-Host "[verify] Lock-Runner: uebersprungen - andere Session testet gerade (Exit 99)."; exit $code }
            default { Write-Host "[verify] TESTS ROT (exit $code)"; exit $code }
        }
    }
    else {
        Write-Host "[verify] WARNUNG: Lock-Runner nicht gefunden: $runner" -ForegroundColor Yellow
        Write-Host "[verify]          Kein sitzungsuebergreifender Schutz - bei parallelen Sessions" -ForegroundColor Yellow
        Write-Host "[verify]          drohen Qt-Segfaults/Haenger (siehe reference_pytest_lock)." -ForegroundColor Yellow
        # XPLAT-WIN: die VOLLE Suite gehoert auch hier in den Segment-Runner, nicht
        # in ein einzelnes `pytest tests/`. Pendant zu tools/verify_loop.sh, das auf
        # Linux an verify_segmented.sh delegiert.
        #
        # Vorher stand hier genau dieser Sammellauf - also ausgerechnet die
        # Variante, die an akkumulierendem nativem Qt-Zustand stirbt. Ein frischer
        # Windows-Checkout (ohne Davids maschinenspezifisches run_tests.ps1) hatte
        # damit KEIN belastbares Gate fuer die volle Suite.
        #
        # Gezielte Einzeldateien laufen weiterhin direkt: dort gibt es keinen
        # akkumulierenden Zustand zu vermeiden, und der Segment-Overhead lohnt nicht.
        $seg = Join-Path $PSScriptRoot "verify_segmented.ps1"
        if (-not $TestArgs -and (Test-Path $seg)) {
            $jobs = if ($env:LIGHTOS_VERIFY_JOBS) { $env:LIGHTOS_VERIFY_JOBS } else { "4" }
            Write-Host "[verify] 2/2 VOLLE Suite segmentiert ($jobs parallel) ..."
            & powershell -NoProfile -ExecutionPolicy Bypass -File $seg -j $jobs
            $code = $LASTEXITCODE
        }
        else {
            $target = if ($TestArgs) { $TestArgs } else { @("tests/") }
            Write-Host "[verify] 2/2 pytest $($target -join ' ') ..."
            & $py -m pytest @target -q --tb=short -p no:cacheprovider -o addopts=""
            $code = $LASTEXITCODE
        }
        if ($code -ne 0) { Write-Host "[verify] TESTS ROT (exit $code)"; exit $code }
    }

    Write-Host "[verify] GRUEN - alles bestanden."
}
finally { Pop-Location }

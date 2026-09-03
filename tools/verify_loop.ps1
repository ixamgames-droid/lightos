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

# -- Sitzungsuebergreifende Sperre fuer die VOLLE Suite (XPLAT-23) ------------
#
# Pendant zu `_verify_lock` in tools/verify_loop.sh. Bis hierhin lag die
# Serialisierung des Windows-Gates AUSSCHLIESSLICH in ../run_tests.ps1 - einer
# Datei ausserhalb des Repos. Ein frischer Windows-Checkout fuhr die volle
# Suite damit ungesperrt: zwei parallele Sitzungen (real seit 2026-08-06) sahen
# rote Segmente, die einander gehoerten. Auf Linux steht die Sperre seit
# PROC-02 im Repo; hier fehlte sie.
#
# Nur die VOLLE Suite wird gesperrt. Gezielte Einzellaeufe sind kurz und
# billig; sie zu serialisieren wuerde nur bremsen (gleiche Regel wie Linux).
#
# Die Sperrdatei haengt am GEMEINSAMEN Git-Verzeichnis (`--git-common-dir`),
# nicht am Elternordner: nur so sehen ein Haupt-Checkout und ein VERSCHACHTELTER
# Worktree dieselbe Datei. Das ist PROC-02b, und die Begruendung dort gilt hier
# unveraendert - eine Sperre, die stillschweigend nicht greift, ist schlimmer
# als keine.
#
# Windows hat kein `flock`. Die Entsprechung ist eine Datei, die exklusiv
# geoeffnet gehalten wird (FileShare::None): ein zweiter Oeffner bekommt eine
# IOException, und das Betriebssystem gibt das Handle beim Prozessende in jedem
# Fall frei - auch nach einem harten Abbruch, wo ein `finally` nicht mehr
# laeuft.
function Get-SperrPfad {
    if ($env:LIGHTOS_LOCKFILE) { return $env:LIGHTOS_LOCKFILE }
    $common = $null
    # PowerShell 5.1 macht aus einer stderr-Zeile eines NATIVEN Programms einen
    # NativeCommandError - unter "Stop" ist der terminierend. `git` schreibt
    # ausserhalb eines Repos genau dorthin. Das lokale "Continue" muss deshalb
    # im finally zurueck, sonst laeuft der REST des Gates mit veraenderter
    # Fehlerbehandlung weiter, wenn der Aufruf wirft.
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $common = (& git -C $repo rev-parse --git-common-dir 2>$null | Select-Object -First 1)
    } catch { $common = $null }
    finally { $ErrorActionPreference = $prevEAP }
    if ($common) {
        $common = $common.Trim()
        if (-not [System.IO.Path]::IsPathRooted($common)) { $common = Join-Path $repo $common }
        if (Test-Path $common) { return (Join-Path (Resolve-Path $common).Path ".pytest_lock") }
    }
    # Kein Git (Tarball-Kopie)? Dann wie bisher der Elternordner.
    return (Join-Path $outer ".pytest_lock")
}

$script:sperrPfad   = Get-SperrPfad
$script:sperrHandle = $null

# ERROR_SHARING_VIOLATION (32) und ERROR_LOCK_VIOLATION (33) - die einzigen
# beiden Faelle, in denen Warten sinnvoll ist. Alles andere ist ein kaputter
# Pfad, kein belegter.
$script:SPERR_BELEGT = @(32, 33)

function Melde-SperreUnbrauchbar($fehler) {
    while ($fehler.InnerException) { $fehler = $fehler.InnerException }
    Write-Host "[verify] FEHLER: Sperrdatei nicht benutzbar: $script:sperrPfad" -ForegroundColor Red
    Write-Host ("[verify]        {0} (Win32 {1}): {2}" -f `
                $fehler.GetType().Name, ($fehler.HResult -band 0xFFFF), $fehler.Message) -ForegroundColor Red
    Write-Host "[verify]        Pfad pruefen (LIGHTOS_LOCKFILE?) - hier wird NICHT gewartet." -ForegroundColor Red
    exit 2
}

function Enter-Sperre {
    if ($TestArgs) { return }                    # gezielter Lauf: keine Sperre
    if ($env:LIGHTOS_VERIFY_NOLOCK) {
        # Ein Volllauf OHNE Sperre ist am Exit-Code nicht von einem gesperrten
        # zu unterscheiden. Er muss es also sagen - sonst haelt jemand ein
        # gruenes Ergebnis fuer eines, das die Serialisierung hatte.
        Write-Host "[verify] Hinweis: LIGHTOS_VERIFY_NOLOCK gesetzt - die volle Suite laeuft UNGESPERRT."
        return
    }
    if ($env:LIGHTOS_LOCKFILE) {
        Write-Host "[verify] Hinweis: Sperrdatei per LIGHTOS_LOCKFILE umgelenkt: $script:sperrPfad"
    }
    $gemeldet = $false
    $beginn   = [datetime]::UtcNow
    $gemerkt  = 0
    while ($true) {
        try {
            $script:sperrHandle = [System.IO.File]::Open(
                $script:sperrPfad,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None)
            if ($gemeldet) { Write-Host "[verify] Sperre frei, starte." }
            return
        }
        catch [System.UnauthorizedAccessException] {
            # Erbt NICHT von IOException (gemessen, Win32 5) und flog deshalb
            # ungefangen aus dem Skript - Enter-Sperre steht ausserhalb des
            # try/finally, der Aufrufer sah einen rohen Fehlerdump statt einer
            # Diagnose. Realer Fall: der Sperrpfad zeigt auf einen ORDNER.
            Melde-SperreUnbrauchbar $_.Exception
        }
        catch [System.IO.IOException] {
            # ⚠ Hier stand zuerst nur `catch [System.IO.IOException]` und sonst
            # nichts - und das war ein Fehler mit genau der Wirkung, gegen die
            # dieses Gate gebaut ist. DirectoryNotFoundException ERBT von
            # IOException (gemessen: HResult 0x80070003). Ein LIGHTOS_LOCKFILE
            # mit vertipptem Ordner lief damit nicht in einen Fehler, sondern in
            # eine ENDLOSSCHLEIFE - und meldete dabei "eine andere Sitzung
            # faehrt gerade die volle Suite". Das ist keine fehlende Diagnose,
            # das ist eine falsche: man sucht die andere Sitzung, die es nicht
            # gibt. Gemessen am 02.09.2026: der Lauf haing nach 45 s noch.
            $fehler = $_.Exception
            while ($fehler.InnerException) { $fehler = $fehler.InnerException }
            $win32 = $fehler.HResult -band 0xFFFF
            if ($script:SPERR_BELEGT -notcontains $win32) { Melde-SperreUnbrauchbar $fehler }
            if (-not $gemeldet) {
                Write-Host "[verify] Eine andere Sitzung faehrt gerade die volle Suite - warte ..."
                $gemeldet = $true
            }
            # Ein Volllauf dauert eine Viertelstunde; das Warten ist also normal.
            # Stumm darf es trotzdem nicht sein - sonst ist ein haengendes Gate
            # von einem wartenden nicht zu unterscheiden.
            $verstrichen = [int]([datetime]::UtcNow - $beginn).TotalSeconds
            if ($verstrichen -ge $gemerkt + 60) {
                $gemerkt = $verstrichen - ($verstrichen % 60)
                Write-Host ("[verify] ... warte weiter auf die Sperre ({0} s): {1}" -f `
                            $gemerkt, $script:sperrPfad)
            }
            Start-Sleep -Milliseconds 200
        }
    }
}
function Exit-Sperre {
    if ($script:sperrHandle) {
        $script:sperrHandle.Close()
        $script:sperrHandle = $null
    }
}

Enter-Sperre

Push-Location $repo
try {
    # XPLAT-26: `tools` gehoert mit hinein - Pendant zu verify_loop.sh seit
    # QA-51(e). Bis hierhin kompilierte das WINDOWS-Gate die Werkzeuge nicht;
    # ein Syntaxfehler dort fiel erst auf, wenn jemand das Werkzeug benutzte.
    # Besonders unangenehm bei gen_tools_index.py, das einen SyntaxError beim
    # Einlesen einer Datei in die harmlose Index-Zelle "(Docstring nicht
    # lesbar)" verwandelt: die kaputte Datei erscheint damit ordentlich im
    # Verzeichnis, und der Index bestaetigt sie sogar.
    Write-Host "[verify] 1/2 Syntax-Check (compileall src tools) ..."
    & $py -m compileall -q src tools
    if ($LASTEXITCODE -ne 0) { Write-Host "[verify] SYNTAX-FEHLER"; exit 1 }

    # QA-53/PROC-02b-Pendant: Ausstieg NACH dem Syntax-Check, VOR dem Testlauf.
    #
    # Nur fuer den Test ZU dieser Sperre. Ohne ihn muesste er den Runner ohne
    # Argumente starten - also die VOLLE Suite, mitten im laufenden Gate. Genau
    # das war QA-53 (95 pytest-Prozesse auf EINER geerbten Show-Datenbank).
    # Der zu pruefende Mechanismus - Sperre nehmen, warten, weitergehen - laeuft
    # hier vollstaendig echt; es entfaellt nur die Nutzlast.
    #
    # Der Sperrpfad wird gemeldet, weil er die einzige Angabe ist, die von
    # aussen nicht nachpruefbar waere: ein Test muesste die Aufloesung sonst
    # nachbauen und damit seine eigene Kopie pruefen statt das Skript (PROC-02b).
    #
    # LIGHTOS_VERIFY_DRYRUN_HOLD_MS haelt die Sperre danach noch die angegebene
    # Zeit. Das ist der einzige Weg, die Serialisierung SKRIPT GEGEN SKRIPT zu
    # messen statt gegen einen nachgebauten Halter - ohne dafuer zwei volle
    # Suiten zu fahren.
    #
    # WARNUNG: der Schalter macht das Gate zum No-Op. Er gehoert NICHT in CI und
    # nicht in eine dauerhaft gesetzte Umgebung: ein Lauf mit gesetztem DRYRUN
    # endet mit 0, ohne einen einzigen Test gefahren zu haben. Deshalb bleibt
    # "GRUEN - alles bestanden" hier bewusst aus.
    if ($env:LIGHTOS_VERIFY_DRYRUN) {
        Write-Host "[verify] Sperrdatei: $script:sperrPfad"
        if ($env:LIGHTOS_VERIFY_DRYRUN_HOLD_MS) {
            Start-Sleep -Milliseconds ([int]$env:LIGHTOS_VERIFY_DRYRUN_HOLD_MS)
        }
        Write-Host "[verify] LIGHTOS_VERIFY_DRYRUN - Sperre und Syntax-Check erledigt, KEIN Testlauf."
        Write-Host "[verify] Das ist KEINE bestandene Pruefung."
        exit 0
    }

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
finally { Exit-Sperre; Pop-Location }

# tools/verify_segmented.ps1 - Test-Gate in Segmenten (Windows-Pendant zu tools/verify_segmented.sh).
#
# WARUM ES DAS GIBT: dasselbe Argument wie auf Linux - ein pytest-Prozess je
# Testdatei, damit sich nativer Qt-Zustand nicht ueber Dateigrenzen hinweg
# aufbaut und ein einzelner Absturz auf die verursachende Datei lokalisiert wird.
#
# WARUM ES IM REPO LIEGT (XPLAT-WIN, 2026-08-04): die Segmentierung lag auf
# Windows bisher AUSSCHLIESSLICH in `../run_tests.ps1`, also ausserhalb des
# Repos. Das ist genau die Lage, die Linux mit XPLAT-11 verlassen hat, und sie
# kostet dasselbe doppelt:
#   * ein frischer Windows-Checkout hat gar kein Gate fuer die volle Suite
#     (verify_loop.ps1 fiel auf ein einzelnes `pytest tests/` zurueck - die
#     Variante, die an akkumulierendem Qt-Zustand stirbt), und
#   * die beiden Plattform-Gates driften auseinander, ohne dass es auffaellt.
#
# Die Arbeitsteilung ist bewusst:
#   * `../run_tests.ps1` haelt die SITZUNGSUEBERGREIFENDE SPERRE. Die ist
#     maschinenspezifisch (Davids parallele Sessions auf EINEM Rechner) und
#     gehoert deshalb weiterhin ausserhalb des Repos.
#   * DIESES Skript macht die Segmentierung. Daran ist nichts rechnerspezifisch,
#     also gehoert es versioniert ins Repo - unter dieselben Tests wie der Rest.
#
#   .\tools\verify_segmented.ps1                     alle Testdateien
#   .\tools\verify_segmented.ps1 -j 6                mit 6 parallelen Segmenten
#   .\tools\verify_segmented.ps1 tests\test_x.py     nur diese Dateien
#
# Ausgabe je Segment in $env:LIGHTOS_SEG_OUT (Default: .pytest_segments\ im Repo).
#
# ── UNTERSCHIED ZU LINUX, DER KEIN VERSEHEN IST ─────────────────────────────
# `verify_segmented.sh` zaehlt JEDEN rc != 0 als rotes Segment (auch SIGSEGV).
# Hier NICHT: ein nativer Absturz (NTSTATUS, erscheint als grosser NEGATIVER
# Exit-Code, z.B. 0xC0000005 = -1073741819) zaehlt als Umgebungs-Flakiness und
# faerbt das Gate nicht rot - exakt die Regel, die `run_tests.ps1 -Isolate`
# seit jeher anwendet und auf die sich das Windows-Gate stuetzt.
#
# Der Grund ist gemessen, nicht geraten: auf Windows/PySide6 crasht der FINALE
# native Interpreter-Exit sporadisch NACH bestandenen Tests (bekanntester Fall
# test_viz10_ui_repairs.py - 22 Tests gruen, danach 0xC0000005). Wuerde das rot
# zaehlen, waere das Gate als Merge-Kriterium sofort wertlos. Echte
# pytest-Failures liefern kleine positive Codes (1..5) und bleiben rot.
# Wer das aendert, macht das Windows-Gate unbrauchbar - bitte vorher die
# Crash-Rate messen, nicht einen Einzellauf interpretieren.
# PositionalBinding=$false ist Pflicht, nicht Stil: sonst schnappt sich
# -TimeoutSec das erste freie Argument, und `verify_segmented.ps1 -j 3
# tests\test_x.py` stirbt mit "Der Wert tests\test_x.py kann nicht in den Typ
# System.Int32 konvertiert werden". Dateinamen sollen ausschliesslich in
# $Targets landen.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Alias('j')][int]$Jobs = 0,
    [int]$TimeoutSec = 300,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Targets
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# venv-Python: identische Kandidaten-Reihenfolge wie tools/verify_loop.ps1
# (Windows zuerst, danach die Linux-Pfade fuer einen Git-Bash-/WSL-Checkout).
$outer = Split-Path $repo -Parent
$pyCandidates = @(
    (Join-Path $repo  "venv\Scripts\python.exe"),
    (Join-Path $outer "lightos-main\venv\Scripts\python.exe"),
    (Join-Path $repo  "venv/bin/python"),
    (Join-Path $outer "lightos-main/venv/bin/python")
)
$py = $pyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $py) {
    Write-Host "[seg] FEHLER: venv-Python nicht gefunden. Geprueft:`n  $($pyCandidates -join "`n  ")"
    exit 2
}

# ── Gate-Umgebung ───────────────────────────────────────────────────────────
# MUSS identisch zu tools/verify_loop.ps1 / verify_segmented.sh bleiben -
# tests/test_gate_runner_parity.py nagelt das fest. Genau diese Drift war
# XPLAT-11 auf der Linux-Seite.
if (-not $env:QT_QPA_PLATFORM)   { $env:QT_QPA_PLATFORM = "offscreen" }
if (-not $env:LIGHTOS_HARDEN_EXIT) { $env:LIGHTOS_HARDEN_EXIT = "1" }

if ($Jobs -le 0) {
    if ($env:LIGHTOS_VERIFY_JOBS) { $Jobs = [int]$env:LIGHTOS_VERIFY_JOBS } else { $Jobs = 4 }
}

# Dateiliste. Pfade werden auf "/" normalisiert - results.tsv bleibt damit
# zeichengleich zur Linux-Fassung, und Auswertungen funktionieren auf beiden
# Plattformen (die Slash-Richtung war genau die XPLAT-WIN-Falle).
if ($Targets -and $Targets.Count) {
    $files = @($Targets | ForEach-Object { $_ -replace '\\', '/' })
}
else {
    $files = @(Get-ChildItem -Path (Join-Path $repo "tests") -Filter "test_*.py" -File |
               Sort-Object Name | ForEach-Object { "tests/" + $_.Name })
}

$outDir = if ($env:LIGHTOS_SEG_OUT) { $env:LIGHTOS_SEG_OUT } else { Join-Path $repo ".pytest_segments" }
if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force }
$null = New-Item -ItemType Directory -Path $outDir -Force
$resultsTsv = Join-Path $outDir "results.tsv"

function Get-LogPfad([string]$rel) {
    Join-Path $outDir (($rel -replace '[\\/:]', '_') + ".log")
}

# ── Zwei Spuren: WebEngine seriell, Rest parallel ───────────────────────────
# Uebernommen aus verify_segmented.sh (2026-08-01), inklusive Begruendung:
# Segmente, die eine echte three.js-Szene hochfahren, brauchen je einen
# WebGL-Kontext. Laufen mehrere gleichzeitig, scheitert einer reproduzierbar mit
# "THREE.WebGLRenderer: Error creating WebGL context" - an WECHSELNDEN Dateien,
# isoliert sind dieselben gruen. Das ist Kontext-Konkurrenz, kein Testfehler.
#
# Keine Wiederholungslogik (die wuerde echte Fehler mitheilen), sondern an die
# Ursache: WebEngine-Dateien laufen in einer eigenen Spur mit genau EINEM
# Prozess, NEBEN der schnellen Spur. Marker ist der Import von QWebEngineView -
# den hat jede Datei, die eine Seite laden kann, und keine andere.
$web = @(); $rest = @()
foreach ($f in $files) {
    $voll = Join-Path $repo ($f -replace '/', '\')
    if ((Test-Path $voll) -and (Select-String -Path $voll -Pattern 'QWebEngineView' -SimpleMatch -Quiet)) {
        $web += $f
    } else { $rest += $f }
}

Write-Host ("[seg] {0} Testdateien, {1} parallel + 1 WebEngine-Spur, Ausgabe: {2}" -f $files.Count, $Jobs, $outDir) -ForegroundColor Cyan
Write-Host ("[seg] Spuren: {0} parallel, {1} WebEngine seriell" -f $rest.Count, $web.Count) -ForegroundColor Cyan

# XPLAT-17: vor einem WebEngine-Segment warten, bis die Chromium-Kindprozesse
# des vorigen wirklich weg sind. Gedeckelt (3 s), damit es nie haengt - laeuft
# nebenher Davids LightOS-Instanz, halten deren Kinder die Bedingung dauerhaft
# offen und wir laufen sehenden Auges in den Deckel statt in eine Endlosschleife.
$script:gpuDeckelTreffer = @()
$script:letzterWebStart = $null
function Wait-FreieGpu {
    # ⚠️ Es wird auf die Chromium-Kinder des VORIGEN WebEngine-Segments gewartet,
    # NICHT auf "laeuft ueberhaupt irgendein QtWebEngineProcess".
    #
    # Die erste Fassung fragte genau das - und lief damit in dieselbe Falle, die
    # verify_segmented.sh fuer Linux dokumentiert (dort traf `pgrep -f` die eigene
    # Shell). Hier genuegt EIN verwaister QtWebEngineProcess aus einem frueheren
    # Lauf, damit die Bedingung nie erfuellt ist. Gemessen 2026-08-06: PID 27520,
    # acht Minuten vor Gate-Start entstanden und nie gestorben -> 34 von 34
    # WebEngine-Segmenten liefen stumpf in den 3-s-Deckel, das Warten kostete
    # 102 s und bewirkte nichts. Ein Waechter, den ein beliebiger Fremdprozess
    # dauerhaft ausschaltet, ist keiner.
    #
    # Der Zeitstempel-Filter macht ihn wieder scharf: relevant sind nur Prozesse,
    # die NACH dem Start des vorigen Segments entstanden - also dessen Kinder.
    if (-not $script:letzterWebStart) { return $true }   # erstes Segment: nichts abzuwarten
    for ($i = 0; $i -lt 30; $i++) {
        $offen = @(Get-Process -Name "QtWebEngineProcess" -ErrorAction SilentlyContinue |
                   Where-Object {
                       # StartTime wirft bei Prozessen ohne Zugriffsrecht -> als
                       # "nicht unser Kind" behandeln statt das Gate zu kippen.
                       try { $_.StartTime -ge $script:letzterWebStart } catch { $false }
                   })
        if ($offen.Count -eq 0) { return $true }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

# ── Prozess-Pool ────────────────────────────────────────────────────────────
# Windows PowerShell 5.1 hat KEIN `ForEach-Object -Parallel` (das kam mit PS 7),
# und Start-Job serialisiert hier ueber die Runspace-Erzeugung mehr, als es
# einbringt. Deshalb ein eigener Pool aus Start-Process + Poll-Schleife.
$laufend = New-Object System.Collections.ArrayList
$restQueue = New-Object System.Collections.Queue
foreach ($f in $rest) { $null = $restQueue.Enqueue($f) }
$webQueue = New-Object System.Collections.Queue
foreach ($f in $web) { $null = $webQueue.Enqueue($f) }

$okCount = 0; $fail = @(); $crash = @(); $timeout = @()

function Start-Segment([string]$rel, [bool]$istWeb) {
    $log = Get-LogPfad $rel
    $err = $log + ".err"
    $p = Start-Process -FilePath $py `
        -ArgumentList @('-m', 'pytest', $rel, '-q', '--tb=short', '-rf', '-p', 'no:cacheprovider') `
        -WorkingDirectory $repo -NoNewWindow -PassThru `
        -RedirectStandardOutput $log -RedirectStandardError $err
    # ⚠️ PS-5.1-Quirk: ohne einmal gelesenes (und damit gecachtes) Handle liefert
    # $p.ExitCode nach Prozessende dauerhaft $null -> ALLES wuerde als FAIL
    # klassifiziert. Real passiert beim ersten Gate-Lauf am 2026-07-19:
    # 440/440 falsch-FAIL. Diese Zeile ist der Fix, nicht Kosmetik.
    $null = $p.Handle
    [pscustomobject]@{
        Proc = $p; Rel = $rel; Log = $log; Err = $err
        Start = Get-Date; IstWeb = $istWeb
    }
}

function Merge-SegmentLog($rec) {
    # stderr an das Log anhaengen -> EIN Log je Segment, wie auf Linux. MUSS vor
    # der Einstufung laufen: Test-NativerAbbau liest genau dieses Log, und der
    # faulthandler-Auszug landet auf stderr.
    if (Test-Path $rec.Err) {
        $e = Get-Content $rec.Err -Raw -ErrorAction SilentlyContinue
        if ($e) { Add-Content -Path $rec.Log -Value $e }
        Remove-Item $rec.Err -Force -ErrorAction SilentlyContinue
    }
}

function Test-NativerAbbau([string]$log) {
    <#
      Nativer Absturz ohne Test-Fehlschlag? Dann Umgebungs-Flakiness, nicht rot.

      ⚠️ WARUM NACH LOG-INHALT UND NICHT NUR NACH EXIT-CODE: derselbe bekannte
      Defekt liefert nicht immer denselben Code. `test_viz10_ui_repairs.py`
      stirbt reproduzierbar sporadisch an einer Access Violation in der
      Teardown-Fixture `_cleanup_vc_canvases` — mal als NTSTATUS
      (0xC0000005 = -1073741819, faellt in die Crash-Familie oben), mal meldet
      pytest darueber schlicht `exit 3` (internal error). Gemessen 2026-08-06:
      derselbe Lauf, dieselbe Datei, einmal CRASH und einmal ROT. Ein Gate, das
      denselben Defekt mal so und mal so wertet, ist als Merge-Kriterium wertlos.

      ⚠️ UND WARUM DAS TROTZDEM ENG BLEIBT: `^FAILED` im Log ist das
      Ausschlusskriterium. Ist auch nur EIN Test fehlgeschlagen, bleibt das
      Segment rot — egal wie spektakulaer der Abbau danach aussah. Ohne diese
      Klammer waere es genau die Gewoehnung, hinter der sich XPLAT-09 auf der
      Linux-Seite neun Testdateien lang versteckt hat: "sieht nach Abbau aus,
      wird schon nichts sein".
    #>
    if (-not (Test-Path $log)) { return $false }
    if (Select-String -Path $log -Pattern '^FAILED' -Quiet) { return $false }
    return [bool](Select-String -Path $log -SimpleMatch -Quiet `
        -Pattern 'Windows fatal exception', 'Fatal Python error')
}

function Complete-Segment($rec, [int]$rc, [string]$art) {
    Add-Content -Path $resultsTsv -Value ("{0}`t{1}" -f $rc, $rec.Rel)
    switch ($art) {
        "ok"      { $script:okCount++; Write-Host ("   ok   " + $rec.Rel) -ForegroundColor Green }
        "zeit"    { $script:timeout += $rec.Rel; Write-Host ("  ZEIT  {0} (>{1}s abgebrochen)" -f $rec.Rel, $TimeoutSec) -ForegroundColor Magenta }
        "crash"   { $script:crash += $rec.Rel; Write-Host ("  CRASH {0} (rc={1}, nativer Abbau)" -f $rec.Rel, $rc) -ForegroundColor Magenta }
        default   { $script:fail += $rec.Rel; Write-Host ("  ROT   {0} (exit {1})" -f $rec.Rel, $rc) -ForegroundColor Red }
    }
}

while ($restQueue.Count -or $webQueue.Count -or $laufend.Count) {

    # WebEngine-Spur: genau EIN Prozess gleichzeitig.
    if ($webQueue.Count -and -not ($laufend | Where-Object { $_.IstWeb })) {
        if (-not (Wait-FreieGpu)) { $script:gpuDeckelTreffer += $webQueue.Peek() }
        $script:letzterWebStart = Get-Date   # Bezugspunkt fuer das naechste Warten
        $null = $laufend.Add((Start-Segment $webQueue.Dequeue() $true))
    }

    # Schnelle Spur bis zum Job-Limit auffuellen.
    while ($restQueue.Count -and (@($laufend | Where-Object { -not $_.IstWeb }).Count -lt $Jobs)) {
        $null = $laufend.Add((Start-Segment $restQueue.Dequeue() $false))
    }

    Start-Sleep -Milliseconds 120

    foreach ($rec in @($laufend)) {
        if ($rec.Proc.HasExited) {
            $rec.Proc.WaitForExit()      # argloser Flush -> finaler ExitCode
            $rc = $rec.Proc.ExitCode
            Merge-SegmentLog $rec        # VOR der Einstufung (s. Test-NativerAbbau)
            if ($null -eq $rc) {
                # Sollte mit gecachtem Handle nie passieren - falls doch:
                # Umgebungs-Flakiness melden statt Phantom-FAILs zu erzeugen.
                Complete-Segment $rec -1 "crash"
            }
            elseif ($rc -eq 0) { Complete-Segment $rec 0 "ok" }
            # Crash-Familie konsistent (uebernommen aus run_tests.ps1): Unix
            # 128+Signal ODER Windows-NTSTATUS (0x8000xxxx/0xC000xxxx erscheinen
            # als grosse NEGATIVE Codes). Frueher zaehlten nur 139/-1073741819 ->
            # dieselbe QtWebEngine-Instabilitaet kippte das Gate mal so, mal so.
            elseif (($rc -ge 129 -and $rc -le 192) -or $rc -lt -100000000) {
                Complete-Segment $rec $rc "crash"
            }
            # Derselbe native Abbau, aber von pytest als `exit 3` (internal error)
            # gemeldet statt als NTSTATUS. Nur wenn KEIN Test fehlschlug.
            elseif (Test-NativerAbbau $rec.Log) {
                Complete-Segment $rec $rc "crash"
            }
            else { Complete-Segment $rec $rc "fail" }
            $laufend.Remove($rec)
        }
        elseif (((Get-Date) - $rec.Start).TotalSeconds -gt $TimeoutSec) {
            # Prozessbaum beenden - pytest kann Qt-/WebEngine-Kinder haben.
            & taskkill /PID $rec.Proc.Id /T /F 2>$null | Out-Null
            Start-Sleep -Milliseconds 300     # taskkill nachlaufen lassen, dann Log lesbar
            Merge-SegmentLog $rec
            Complete-Segment $rec 124 "zeit"
            $laufend.Remove($rec)
        }
    }
}

# ── Bilanz ──────────────────────────────────────────────────────────────────
Write-Host ""
if ($script:gpuDeckelTreffer.Count) {
    Write-Host ("[seg] HINWEIS (XPLAT-17): {0} WebEngine-Segmente starteten, obwohl noch" -f $script:gpuDeckelTreffer.Count) -ForegroundColor DarkYellow
    Write-Host "[seg]   Chromium-Kindprozesse liefen (3-s-Deckel erreicht)." -ForegroundColor DarkYellow
    Write-Host "[seg]   Laeuft nebenher eine LightOS-Instanz? Dann ist das erwartet." -ForegroundColor DarkYellow
}
Write-Host ("[seg] {0}/{1} Segmente gruen, {2} Failures, {3} Crashes, {4} Timeouts." -f `
    $okCount, $files.Count, $fail.Count, $crash.Count, $timeout.Count) -ForegroundColor Cyan
if ($fail.Count)    { Write-Host ("  Failures: " + ($fail    -join ", ")) -ForegroundColor Red }
if ($crash.Count)   { Write-Host ("  Crashes : " + ($crash   -join ", ")) -ForegroundColor Magenta }
if ($timeout.Count) { Write-Host ("  Timeouts: " + ($timeout -join ", ")) -ForegroundColor Magenta }

# XPLAT-17: die EINE bekannte Fremd-Ursache beim Namen nennen. Das Segment
# bleibt rot - hier wird nichts gruen gerechnet und nichts wiederholt. Der Name
# ist der ganze Zweck: ohne ihn steht der Mensch vor einem namenlosen roten
# Viz-Segment und muss raten, ob es der bekannte Kontextverlust ist oder ein
# echter Fehler. Erkannt wird die URSACHE, nicht ihre Folge - die
# "Error creating WebGL context"-Zeile erscheint NICHT immer.
$sig = @()
foreach ($rel in @($fail + $crash)) {
    $lg = Get-LogPfad $rel
    if ((Test-Path $lg) -and (Select-String -Path $lg -Pattern 'Context lost during MakeCurrent', 'context already lost' -Quiet)) {
        $sig += $rel
    }
}
if ($sig.Count) {
    Write-Host "[seg] XPLAT-17-Signatur - GPU-Kontextverlust im eigenen Prozess:" -ForegroundColor DarkYellow
    $sig | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor DarkYellow }
    Write-Host "[seg]   Gegenprobe: .\tools\verify_loop.ps1 <datei> - bleibt sie isoliert" -ForegroundColor DarkYellow
    Write-Host "[seg]   gruen, war es dieser Fall. ROT bleibt trotzdem ROT." -ForegroundColor DarkYellow
}

# Zweite bekannte Fremd-Ursache: das Seitenladen eines WebEngine-Segments reisst
# unter paralleler Last sein Zeitbudget (40 s in den Szenen-Tests).
#
# Auch hier gilt: das Segment bleibt ROT, es wird nichts wiederholt und nichts
# gruen gerechnet — Wiederholungslogik wuerde echte Fehler mitheilen. Der Name
# ist der Zweck: ohne ihn steht der Mensch vor einem roten Viz-Segment und muss
# raten, ob die Szene kaputt ist oder der Rechner nur beschaeftigt war.
#
# Gemessene Haeufigkeit (2026-08-06, -j 4): einmal ueber drei volle Laeufe; in
# einer gezielten Messreihe unter Last 0 von 6. Selten, aber nicht null — wer
# haeufiger darueber stolpert, senkt LIGHTOS_VERIFY_JOBS.
$last = @()
foreach ($rel in @($fail + $timeout)) {
    $lg = Get-LogPfad $rel
    if ((Test-Path $lg) -and (Select-String -Path $lg -SimpleMatch -Quiet `
            -Pattern 'loadFinished nie ausgeloest', '__lightosAppReady')) {
        $last += $rel
    }
}
if ($last.Count) {
    Write-Host "[seg] Zeitbudget beim Seitenladen gerissen (Last-Verdacht):" -ForegroundColor DarkYellow
    $last | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor DarkYellow }
    Write-Host "[seg]   Gegenprobe: .\tools\verify_loop.ps1 <datei> - bleibt sie isoliert" -ForegroundColor DarkYellow
    Write-Host "[seg]   gruen, war es die Last. ROT bleibt trotzdem ROT." -ForegroundColor DarkYellow
    Write-Host "[seg]   Dauerhaft? LIGHTOS_VERIFY_JOBS kleiner setzen (Default 4)." -ForegroundColor DarkYellow
}

# Wichtig fuer die Triage: steht hier nichts, ist KEIN Test fehlgeschlagen -
# dann sind die roten Segmente native Abbau-Crashes. Das ist aber nur eine
# Dringlichkeits-Einstufung, keine Entwarnung (XPLAT-09 versteckte sich neun
# Dateien lang hinter genau dieser Lesart).
if ($fail.Count) {
    Write-Host "[seg] Fehlgeschlagene Tests:" -ForegroundColor Red
    Get-ChildItem $outDir -Filter "*.log" | ForEach-Object {
        Select-String -Path $_.FullName -Pattern '^FAILED' -ErrorAction SilentlyContinue
    } | ForEach-Object { $_.Line } | Sort-Object -Unique | ForEach-Object { Write-Host ("  " + $_) }
}

# Exit-Vertrag wie run_tests.ps1 -Isolate: NUR echte Test-Failures faerben rot.
# Crashes/Timeouts sind Umgebungs-Flakiness (s. Kopf). Bewusst 1 statt der
# Segmentanzahl wie auf Linux - verify_loop.ps1 deutet 97/98/99 als
# Lock-Runner-Codes, eine Zaehlung koennte dort kollidieren.
if ($fail.Count) { exit 1 } else { exit 0 }

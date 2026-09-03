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
#
# ── DASSELBE GILT FUER DAS ZEITLIMIT, UND ZWAR AUS DEMSELBEN GRUND ──────────
# ★ XPLAT-28 (01.09.2026): hier stand bis heute NICHTS ueber Timeouts. Der
# Exit-Vertrag unten nimmt sie seit jeher genauso aus wie Crashes, nur stand
# die Begruendung allein bei den Crashes - und weil sie fehlte, sind ZWEI
# Sitzungen unabhaengig voneinander auf „das ist mitgeschleift, nicht gemeint"
# gekommen. Die Regel war richtig, die Begruendung unvollstaendig; das ist
# teurer als es aussieht, denn beide haben daraufhin einen Umbau erwogen.
#
# Warum ein Zeitlimit hier dasselbe ist wie ein Crash - gemessen, nicht
# vermutet: `pytest.ini` setzt `timeout = 60` (`timeout_method = thread`,
# `pytest_timeout` ruft `os._exit(1)`). Ein Haenger IM TEST stirbt damit nach
# ~60 s mit Exit 1, faellt in den `fail`-Zweig und ist HEUTE SCHON ROT - er
# erreicht die 300 s nie. Was die 300 s ueberhaupt erreicht, ist per
# Konstruktion der Crash-Zwilling: der finale native Abbau NACH bestandenen
# Tests, haengend statt crashend (gegengeprueft: das Log traegt dann eine
# vollstaendige gruene pytest-Zusammenfassung). Die Timeout-Toleranz wird also
# von derselben Messung getragen wie die Crash-Toleranz.
#
# ⚠️ WAS DIESE BEGRUENDUNG NICHT DECKT (offen als eigenes Item):
# `pytest-timeout` schuetzt nur `pytest_runtest_protocol`/`_call`. COLLECTION,
# Modul-Import und Session-Teardown sind ungeschuetzt - ein Haenger DORT laeuft
# wirklich in die 300 s, ohne dass etwas gemessen wurde, und wird trotzdem
# toleriert. Und wenn KEIN EINZIGES Segment gruen ist, ist das nie
# Abbau-Flakiness, sondern eine kaputte Umgebung; der Lauf meldet trotzdem
# Exit 0. Beides ruft nach einem Anteils-Schutz, nicht nach einer Aenderung
# dieser Einzelregel.
#
# Zeitreserve, auf BEIDEN Plattformen gemessen (echter Voll-Lauf):
#
#                      Linux (647 Seg.)   Windows (646 Seg., -j 6)
#   Median                    1,32 s              8,3 s
#   p99                      31,2  s             73,5 s
#   Max                      72,3  s            158,3 s
#   Abstand zu 300 s        Faktor 4,15        Faktor 1,90
#
# ⚠️ Die Reserve ist auf WINDOWS nicht einmal halb so gross wie auf Linux, und
# das ist kein Messartefakt: die schwersten Segmente sind dieselben Dateien
# (test_zeitbomben_gate 158 s, test_fm14_pixel_head_scene 149 s,
# test_viz50b_weissband_scene 145 s), sie brauchen hier nur doppelt so lang.
# Null Segmente ueber der Grenze - die 300 s sind also auch hier sicher, aber
# mit deutlich weniger Luft, als die Linux-Zahl vermuten laesst. Wer die Grenze
# senken will, muss sie an der WINDOWS-Zahl bemessen.
#
# Die Windows-Zahl enthaelt einen Aufschlag von 6,5 s je Segment fuer
# Prozessstart und conftest (Kopie der Geraetebibliothek + Qt), separat
# gemessen; die pytest-Zeit allein liegt im Median bei 1,78 s. Der Aufschlag
# ist eine Naeherung aus einem EINZELLAUF - unter Volllast duerfte er groesser
# sein, die Reserve also eher kleiner als hier ausgewiesen.
#
# Und sie schrumpft weiter: die serielle WebEngine-Spur ist von 208 s/29
# Dateien (alter Kommentar) auf gemessene 501 s/42 Dateien gewachsen.
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

# XPLAT-23: die rechnerweite WebEngine-Sperre liegt in einer EIGENEN Datei,
# nicht als Kopie hier - Pendant zu tools/_gate_webengine.sh, das aus
# demselben Grund geteilt wird (XPLAT-11 war die Drift zweier Runner).
. (Join-Path $PSScriptRoot "_gate_webengine.ps1")
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

# XPLAT-27: Merkmal fuer die Kinder — "du laeufst als Segment eines Gate-Laufs".
# Bewusst HART gesetzt und nicht per setdefault: die Aussage gilt hier immer,
# und ein von aussen geerbter Wert duerfte sie nicht ueberschreiben.
#
# WOFUER: ein Test, der selbst einen Runner startet, erzeugt im Volllauf ein
# Gate IM Gate (QA-53). Bisher konnte er das gar nicht erkennen - es gab kein
# Merkmal. `LIGHTOS_SEG_OUT` sieht danach aus, taugt aber nicht: der Runner
# LIEST es nur (mit Default) und setzt es nie, ein Kind sieht es also nur,
# wenn der Mensch es von Hand gesetzt hat. Genau diese Annahme hat mich hier
# einen Anlauf gekostet.
$env:LIGHTOS_IM_SEGMENT = "1"

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

# -- XPLAT-29 (a): das Aufraeumen darf den Lauf nicht beenden ----------------
#
# Gemessen am 01.09.2026: der Start endete sofort, ohne ein einziges Segment,
# mit "Das Element ...tests_test_viz50a_panel_koerper_scene.py.log kann nicht
# entfernt werden ... da sie von einem anderen Prozess verwendet wird". Am
# Leben waren zwei python und ein QtWebEngineProcess aus dem VORIGEN Lauf -
# Windows reisst Prozessbaeume nicht mit.
#
# ★ Ein Lauf, der VOR dem ersten Segment endet, sieht aus wie ein rotes Gate
# und hat dabei nichts gemessen. Das ist die teuerste Variante: dieselbe Klasse
# wie XPLAT-27 und XPLAT-31 - der Runner soll mit dem Schaden umgehen, statt an
# ihm zu sterben.
#
# Ausgewichen wird in ein UNTERverzeichnis, nicht auf einen Geschwister-Ordner:
# `.gitignore` deckt `.pytest_segments/` ab, ein `.pytest_segments-<zeit>`
# daneben waere NICHT ignoriert und landete als unversionierter Muell im
# `git status` eines oeffentlichen Repos.
#
# Waisen werden BENANNT, nicht beendet. Sie wirklich zu toeten ist XPLAT-29(b)
# und liegt bei Robin - es hiesse, dass ein Absturz des Hauptprozesses den
# DMX-Worker mitreisst. Ausserdem haelt die laufende App des Menschen selbst
# Chromium-Kinder ("Die laufende App gehoert dem Menschen", COORDINATION.md).
function Nenne-Waisen {
    $gefunden = @()
    foreach ($name in @("python", "pythonw", "QtWebEngineProcess")) {
        foreach ($p in @(Get-Process -Name $name -ErrorAction SilentlyContinue)) {
            $seit = try { $p.StartTime.ToString("HH:mm:ss") } catch { "?" }
            $cmd = $null
            try {
                $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" `
                        -ErrorAction Stop).CommandLine
            } catch { $cmd = $null }
            # Die laufende App ist KEIN Waise - sie ausdruecklich auszunehmen
            # verhindert, dass jemand sie beim Aufraeumen abschiesst.
            $hinweis = if ($cmd -and $cmd -match "main\.py") {
                "   <- die laufende App, kein Waise"
            } else { "" }
            $gefunden += ("[seg]          PID {0,-6} {1,-18} seit {2}{3}" -f `
                          $p.Id, $p.ProcessName, $seit, $hinweis)
        }
    }
    if ($gefunden.Count) {
        Write-Host "[seg]        Diese Prozesse laufen noch und koennen Dateien halten:" -ForegroundColor DarkYellow
        $gefunden | ForEach-Object { Write-Host $_ -ForegroundColor DarkYellow }
    }
    Write-Host "[seg]        Es wurde NICHTS beendet (XPLAT-29(b) liegt bei Robin)." -ForegroundColor DarkYellow
}

function Initialize-Ausgabeverzeichnis($pfad) {
    if (Test-Path $pfad) {
        try {
            Remove-Item $pfad -Recurse -Force -ErrorAction Stop
        }
        catch {
            Write-Host "[seg] HINWEIS (XPLAT-29): das Ausgabeverzeichnis des vorigen Laufs" -ForegroundColor DarkYellow
            Write-Host "[seg]        laesst sich nicht raeumen - der Lauf geht trotzdem weiter." -ForegroundColor DarkYellow
            Write-Host "[seg]        $($_.Exception.Message)" -ForegroundColor DarkYellow
            Nenne-Waisen
            $ausweich = Join-Path $pfad ("lauf-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            try {
                $null = New-Item -ItemType Directory -Path $ausweich -Force -ErrorAction Stop
            }
            catch {
                # Hier ist wirklich Schluss: kein Ausgabeort, also kein Lauf.
                # Das ist ein ehrliches Scheitern VOR dem ersten Segment - im
                # Gegensatz zu vorher sagt es aber, woran es lag.
                Write-Host "[seg] FEHLER: auch das Ausweichverzeichnis liess sich nicht anlegen:" -ForegroundColor Red
                Write-Host "[seg]        $ausweich" -ForegroundColor Red
                Write-Host "[seg]        $($_.Exception.Message)" -ForegroundColor Red
                exit 2
            }
            Write-Host "[seg]        Ausgewichen auf: $ausweich" -ForegroundColor DarkYellow
            return $ausweich
        }
    }
    $null = New-Item -ItemType Directory -Path $pfad -Force
    return $pfad
}

$outDir = if ($env:LIGHTOS_SEG_OUT) { $env:LIGHTOS_SEG_OUT } else { Join-Path $repo ".pytest_segments" }
$outDir = Initialize-Ausgabeverzeichnis $outDir
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
    # XPLAT-23: `Join-Path $repo` auf einen ABSOLUTEN Pfad ergibt Unsinn, und
    # `Test-Path` schlaegt dann fehl - eine absolut angegebene WebEngine-Datei
    # landete damit still in der schnellen Spur statt in der seriellen, also
    # ausgerechnet ohne die Serialisierung, fuer die es die Spur gibt.
    # Gefunden beim Bau der WebEngine-Sperre (Sitzung B, 03.09.2026).
    $voll = if ([System.IO.Path]::IsPathRooted($f)) { $f }
            else { Join-Path $repo ($f -replace '/', '\') }
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
$script:gpuWartezeitMs = 0
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
    # XPLAT-23: die WARTEZEIT mitschreiben, nicht nur den ausgeschoepften
    # Deckel. $gpuDeckelTreffer zaehlt ausschliesslich Segmente, bei denen die
    # 3 s VOLL abgelaufen sind; wer 2,9 s wartet und dann durchkommt, erscheint
    # dort als Nicht-Treffer. "0 Treffer" heisst also "der Deckel lief nie aus"
    # und NICHT "es wurde nicht gewartet" - genau die Frage, die das Item
    # stellt, konnte das Instrument nicht beantworten.
    $uhr = [System.Diagnostics.Stopwatch]::StartNew()
    for ($i = 0; $i -lt 30; $i++) {
        $offen = @(Get-Process -Name "QtWebEngineProcess" -ErrorAction SilentlyContinue |
                   Where-Object {
                       # StartTime wirft bei Prozessen ohne Zugriffsrecht -> als
                       # "nicht unser Kind" behandeln statt das Gate zu kippen.
                       try { $_.StartTime -ge $script:letzterWebStart } catch { $false }
                   })
        if ($offen.Count -eq 0) {
            $script:gpuWartezeitMs += $uhr.ElapsedMilliseconds
            return $true
        }
        Start-Sleep -Milliseconds 100
    }
    $script:gpuWartezeitMs += $uhr.ElapsedMilliseconds
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
$script:ergebnisSchreibfehler = 0

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
    # XPLAT-23/QA-53: die Ergebniszeile darf den Lauf nicht mitreissen.
    # Gemessen: `Add-Content` auf eine exklusiv gehaltene Datei wirft eine
    # IOException, und unter `$ErrorActionPreference = "Stop"` beendet die den
    # ganzen Lauf - mitten drin, nach getaner Arbeit, die damit verloren ist.
    # Dieselbe Klasse wie XPLAT-27 und XPLAT-29: der Runner soll mit dem Schaden
    # umgehen, statt an ihm zu sterben. Die fehlende Zeile bleibt sichtbar - die
    # Vollstaendigkeits-Pruefung unten faerbt den Lauf dafuer rot.
    try {
        Add-Content -Path $resultsTsv -Value ("{0}`t{1}" -f $rc, $rec.Rel) -ErrorAction Stop
    }
    catch {
        if (-not $script:ergebnisSchreibfehler) {
            Write-Host "[seg] WARNUNG: Ergebniszeile nicht schreibbar - die Bilanz wird unvollstaendig." -ForegroundColor DarkYellow
            Write-Host ("[seg]   {0}" -f $_.Exception.Message) -ForegroundColor DarkYellow
        }
        $script:ergebnisSchreibfehler++
    }
    switch ($art) {
        "ok"      { $script:okCount++; Write-Host ("   ok   " + $rec.Rel) -ForegroundColor Green }
        "zeit"    { $script:timeout += $rec.Rel; Write-Host ("  ZEIT  {0} (>{1}s abgebrochen)" -f $rec.Rel, $TimeoutSec) -ForegroundColor Magenta }
        "crash"   { $script:crash += $rec.Rel; Write-Host ("  CRASH {0} (rc={1}, nativer Abbau)" -f $rec.Rel, $rc) -ForegroundColor Magenta }
        default   { $script:fail += $rec.Rel; Write-Host ("  ROT   {0} (exit {1})" -f $rec.Rel, $rc) -ForegroundColor Red }
    }
}

while ($restQueue.Count -or $webQueue.Count -or $laufend.Count) {

    # XPLAT-23: die schmale Sperre nur so lange halten, wie wirklich ein
    # WebEngine-Segment laeuft. Ein Punkt, beide Enden - egal ob das Segment
    # normal endete oder ins Zeitlimit lief.
    if (-not ($laufend | Where-Object { $_.IstWeb })) { Exit-WebEngineSperre }

    # WebEngine-Spur: genau EIN Prozess gleichzeitig - im Lauf ueber diese
    # Bedingung, RECHNERWEIT ueber die Sperre aus _gate_webengine.ps1.
    if ($webQueue.Count -and -not ($laufend | Where-Object { $_.IstWeb })) {
        $null = Enter-WebEngineSperre
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
            #
            # ★ XPLAT-27: `$ErrorActionPreference` MUSS hier lokal auf 'Continue'.
            # `taskkill` schreibt auf stderr, sobald ein Kind nicht beendet werden
            # kann ("FEHLER: Der Prozess mit PID <n> (untergeordnetem Prozess von
            # PID <m>) konnte nicht beendet werden") - und genau das ist bei einem
            # haengenden Qt-/WebEngine-Segment der Normalfall, nicht die Ausnahme.
            # PowerShell 5.1 wertet native stderr-Zeilen unter 'Stop' als
            # TERMINIERENDEN NativeCommandError; `2>$null` unterdrueckt nur die
            # Anzeige, nicht den ErrorRecord. Der ganze Gate-Lauf brach damit an
            # dieser Zeile ab, statt das eine Segment als "zeit" zu zaehlen und
            # weiterzumachen.
            #
            # Gemessen am 01.09.2026 auf `main`: der Lauf endete nach 404 von 646
            # Segmenten mit Exit 1. Das sah aus wie ein rotes Gate und war ein
            # abgebrochenes - der Unterschied ist erheblich, denn 242 Dateien
            # waren schlicht nicht gefahren, und die Bilanz darunter zaehlt nur,
            # was sie gesehen hat.
            #
            # Dieselbe Falle ist in `verify_loop.ps1` (beim `& powershell`-Aufruf
            # des Lock-Runners) laengst benannt und genauso geloest; hier fehlte
            # sie noch. Der Timeout selbst ist die Aussage - ob `taskkill` jedes
            # Kind erwischt, aendert daran nichts.
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & taskkill /PID $rec.Proc.Id /T /F 2>$null | Out-Null
            }
            finally { $ErrorActionPreference = $prevEAP }
            Start-Sleep -Milliseconds 300     # taskkill nachlaufen lassen, dann Log lesbar
            Merge-SegmentLog $rec
            Complete-Segment $rec 124 "zeit"
            $laufend.Remove($rec)
        }
    }
}

Exit-WebEngineSperre        # XPLAT-23: nicht ueber die Bilanz hinaus halten

# ── Bilanz ──────────────────────────────────────────────────────────────────
Write-Host ""
if ($script:gpuWartezeitMs -gt 0) {
    Write-Host ("[seg] WebEngine-Deckel: insgesamt {0:N1}s auf die Chromium-Kinder des" -f ($script:gpuWartezeitMs / 1000.0)) -ForegroundColor DarkYellow
    Write-Host ("[seg]   vorigen Segments gewartet, verteilt auf {0} Segmente." -f $web.Count) -ForegroundColor DarkYellow
}
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

# ── QA-53 auf der Windows-Seite: im Zweifel rot ─────────────────────────────
#
# Die Zahl oben zaehlt, was in results.tsv steht. Steht dort weniger, als
# gefahren wurde, ist die Bilanz nicht bloss ungenau - sie ist irrefuehrend:
# ein Teillauf sieht aus wie ein Volllauf, und die roten Zeilen darunter
# koennten aus einem FREMDEN Lauf stammen.
#
# ★ Der Fall ist auf Windows real und NICHT theoretisch: beide Runner benutzen
# dasselbe Ausgabeverzeichnis, egal ob Volllauf oder gezielter Einzellauf
# (`LIGHTOS_SEG_OUT`, sonst `.pytest_segments`). Wer waehrend eines Volllaufs
# einen Einzeltest startet, raeumt dem Volllauf die Ergebniszeilen weg - der
# zaehlt danach nur noch seinen Rest. Die Voll-Suiten-Sperre aus XPLAT-23
# Scheibe 1 faengt das nicht: gezielte Laeufe sind bewusst ungesperrt.
#
# Zweite Quelle: eine Ergebniszeile, die sich nicht schreiben liess (s.
# Complete-Segment).
#
# Die gefaehrlichere Haelfte ist dabei nicht die falsche Zahl - die sieht man -,
# sondern das falsche GRUEN darunter. Deshalb hier dieselbe Regel wie auf der
# .sh-Seite: wer nicht weiss, ob alles gelaufen ist, hat kein bestandenes Gate,
# sondern ein kaputtes Messgeraet.
$zeilenImErgebnis = 0
if (Test-Path $resultsTsv) {
    $zeilenImErgebnis = @(Get-Content $resultsTsv -ErrorAction SilentlyContinue).Count
}
$unvollstaendig = ($zeilenImErgebnis -ne $files.Count)
if ($unvollstaendig) {
    Write-Host ("[seg] WARNUNG: results.tsv hat {0} Zeilen, gefahren wurden {1} Dateien." -f `
                $zeilenImErgebnis, $files.Count) -ForegroundColor DarkYellow
    Write-Host "[seg]   Die Zahl oben ist damit UNVOLLSTAENDIG - vermutlich hat ein zweiter" -ForegroundColor DarkYellow
    Write-Host ("[seg]   Lauf im selben Repo das Ausgabeverzeichnis geleert ({0})." -f $outDir) -ForegroundColor DarkYellow
    Write-Host "[seg]   Rote Zeilen koennen aus dem fremden Lauf stammen. Vor dem Deuten:" -ForegroundColor DarkYellow
    Write-Host "[seg]   nachsehen, ob nebenher eine zweite Suite lief (QA-53)." -ForegroundColor DarkYellow
    Write-Host "[seg]   Dieser Lauf gilt als NICHT bestanden - s. Exit-Code unten." -ForegroundColor DarkYellow
}

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
# Auch hier gilt: es wird nichts wiederholt und nichts gruen gerechnet —
# Wiederholungslogik wuerde echte Fehler mitheilen. Der Name ist der Zweck:
# ohne ihn steht der Mensch vor einem auffaelligen Viz-Segment und muss raten,
# ob die Szene kaputt ist oder der Rechner nur beschaeftigt war.
#
# ⚠️ XPLAT-28: hier stand „das Segment bleibt ROT". Das stimmt nur fuer die
# Haelfte der Schleife. Sie laeuft ueber `$fail + $timeout`; ROT ist davon nur
# `$fail`. Ein Segment im ZEITLIMIT faerbt das Gate nach dem Exit-Vertrag
# ausdruecklich NICHT rot (s. Kopf) — die Zusage sagte also mehr zu, als der
# Code haelt, und zwar ausgerechnet an der Stelle, an der jemand nachliest,
# was ein auffaelliges Segment fuer ihn bedeutet.
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
    Write-Host "[seg]   gruen, war es die Last. Ein FAILURE bleibt trotzdem rot;" -ForegroundColor DarkYellow
    Write-Host "[seg]   ein ZEITLIMIT faerbt nicht rot (Exit-Vertrag, s. Skriptkopf)." -ForegroundColor DarkYellow
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
if ($fail.Count) { exit 1 }
# QA-53: unvollstaendige Ergebnisliste -> KEIN Gruen. Bewusst NACH der
# Failure-Regel: ein roter Lauf ist ohnehin rot, und die Reihenfolge haelt
# die begruendete Toleranz aus XPLAT-28 unangetastet.
if ($unvollstaendig) {
    Write-Host "[seg] Ergebnisliste unvollstaendig -> KEIN Gruen (QA-53)." -ForegroundColor Red
    exit 1
}
# ★ XPLAT-31: Anteils-Schutz. Die Toleranz oben gilt dem EINZELFALL - ein
# Segment, das nach bestandenen Tests nativ abbaut oder haengt. Sie war nie als
# Aussage ueber einen ganzen Lauf gemeint.
#
# Ist KEIN EINZIGES Segment gruen, ist das nie Abbau-Flakiness, sondern eine
# kaputte Umgebung: kein venv, keine Bibliothek, ein Prozess der jede Datei
# blockiert. Ohne diese Zeile meldete so ein Lauf "0/3 Segmente gruen" und
# trotzdem Exit 0 - beobachtet beim Testbau zu XPLAT-27. Ein Mensch liest
# "0 von 3 gruen" als rot; das Gate sagte das Gegenteil.
#
# Bewusst als ANTEIL formuliert und nicht als Aenderung der Einzelregel: die
# begruendete Toleranz (s. Kopf) bleibt vollstaendig erhalten, nur der
# Totalausfall wird sichtbar. Vorschlag stammt aus der XPLAT-28-Klaerung.
#
# Auf Linux deckt `verify_segmented.sh` denselben Fall bereits ab, weil es
# JEDEN rc != 0 rot zaehlt - sind alle Segmente auffaellig, ist BAD > 0. Diese
# Zeile stellt also Gleichstand her, sie fuehrt nichts Neues ein.
elseif ($files.Count -gt 0 -and $okCount -eq 0) {
    Write-Host ("[seg] KEIN EINZIGES der {0} Segmente ist gruen - das ist keine " -f $files.Count) -ForegroundColor Red
    Write-Host "[seg] Umgebungs-Flakiness mehr, sondern eine kaputte Umgebung." -ForegroundColor Red
    Write-Host "[seg] Erste Verdaechtige: venv/Python fehlt, Geraetebibliothek nicht" -ForegroundColor Red
    Write-Host "[seg] lesbar, oder ein Prozess haelt etwas, das jedes Segment braucht." -ForegroundColor Red
    exit 1
}
else { exit 0 }

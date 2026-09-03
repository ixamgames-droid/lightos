# tools/_gate_webengine.ps1 - rechnerweite WebEngine-Absicherung des Windows-Gates.
#
# Wird von tools/verify_segmented.ps1 per Dot-Sourcing eingebunden, nicht
# gestartet. Pendant zu tools/_gate_webengine.sh; dass es eine eigene Datei ist
# und keine Kopie im Runner, ist Absicht - XPLAT-11 war genau die Drift zweier
# Gate-Runner, die auseinandergelaufen sind.
#
# ── XPLAT-23: warum es diese Datei gibt ──────────────────────────────────────
#
# verify_segmented.ps1 faehrt WebEngine-Segmente seit XPLAT-17 in einer
# seriellen Spur: INNERHALB eines Laufs ist immer nur eines gleichzeitig
# unterwegs. Ungeschuetzt war der Fall ZWISCHEN Prozessen - ein gezielter
# Einzellauf auf eine WebEngine-Datei neben einem Volllauf, oder zwei Sitzungen
# auf demselben Rechner (seit 2026-08-06 der Normalfall, COORDINATION.md).
# Dann leben zwei WebGL-Kontexte gleichzeitig, und genau das ist die Ursache,
# gegen die PROC-02c auf Linux die schmale Sperre gebaut hat.
#
# Frischer Beleg (Sitzung B, Nacht 02./03.09.2026): ein eigener Gate-Lauf
# meldete "1 WebEngine-Segment startete, obwohl noch Chromium-Kindprozesse
# liefen (3-s-Deckel erreicht)".
#
# ★ Die Sperre ist SCHMAL. Sie gilt nur je WebEngine-Segment, nicht fuer den
# ganzen Lauf - die schmale Sperre minutenlang zu halten waere genau der
# Zustand, den PROC-02c abschaffen wollte.
#
# ⚠️ Sie darf das Gate NIE blockieren. Laeuft die Wartezeit ab oder ist die
# Sperrdatei unbrauchbar, wird gewarnt und weitergemacht. Das ist der
# Unterschied zur Voll-Suiten-Sperre in verify_loop.ps1, die bei einem kaputten
# Pfad ABBRICHT: jene schuetzt die Gueltigkeit des Ergebnisses, diese hier nur
# eine knappe Ressource. Eine Sperre, die haengt, waere schlimmer als keine -
# so steht es auch im Kopf der .sh-Fassung.
#
# ⚠️ Was sie NICHT kann (vollstaendig, damit niemand die Zahl im
# XPLAT-17-Hinweis fuer unmoeglich haelt):
#   * Wer pytest DIREKT startet, an beiden Gate-Runnern vorbei, nimmt sie nicht
#     und wird von ihr auch nicht aufgehalten (WORKFLOW.md verbietet das, die
#     Sperre kann es nicht erzwingen).
#   * Die laufende LightOS-Instanz des Menschen haelt eigene Chromium-Kinder.
#     Sie gehoert ihm, nicht dem Gate (COORDINATION.md).

$script:webSperreHandle = $null

#: Sharing- und Lock-Violation - die einzigen Faelle, in denen Warten sinnvoll
#: ist. Gemessen fuer XPLAT-23 Scheibe 1: echte Belegung ergibt Win32 32,
#: ein fehlender Ordner 3, ein Verzeichnis als Pfad 5.
$script:WEB_SPERRE_BELEGT = @(32, 33)

function Get-WebEngineSperrPfad {
    <#
        .SYNOPSIS
        Pfad der schmalen WebEngine-Sperre - am GEMEINSAMEN Git-Verzeichnis.

        PROC-02b: nur so sehen ein Haupt-Checkout und ein VERSCHACHTELTER
        Worktree dieselbe Datei. Haengte sie am Elternordner, bekaeme jeder
        Worktree eine eigene - und die Serialisierung griffe ausgerechnet dort
        nicht, wo parallel gearbeitet wird.
    #>
    if ($env:LIGHTOS_WEBENGINE_LOCKFILE) { return $env:LIGHTOS_WEBENGINE_LOCKFILE }
    $common = $null
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $common = (& git -C $repo rev-parse --git-common-dir 2>$null | Select-Object -First 1)
    }
    catch { $common = $null }
    finally { $ErrorActionPreference = $prevEAP }
    if ($common) {
        $common = $common.Trim()
        if (-not [System.IO.Path]::IsPathRooted($common)) { $common = Join-Path $repo $common }
        if (Test-Path $common) { return (Join-Path (Resolve-Path $common).Path ".webengine_lock") }
    }
    return (Join-Path $outer ".webengine_lock")
}

function Enter-WebEngineSperre {
    <#
        .SYNOPSIS
        Genau EIN WebEngine-Segment rechnerweit. Gibt zurueck, ob sie gehalten wird.

        ★ Wiedereintritt: ein Runner, der INNERHALB eines Segments laeuft, das
        die Sperre bereits haelt, darf sie nicht noch einmal nehmen - er wartete
        sonst auf sich selbst, bis die Wartezeit ablaeuft. Der Fall ist real:
        die Gate-Tests zaehlen selbst als WebEngine-Segment und starten den
        Segment-Runner erneut.
    #>
    if ($script:webSperreHandle) { return $true }         # schon gehalten
    if ($env:LIGHTOS_WEBENGINE_LOCK_HELD) { return $false }   # Wiedereintritt
    if ($env:LIGHTOS_WEBENGINE_NOLOCK) {
        Write-Host "[seg] Hinweis: LIGHTOS_WEBENGINE_NOLOCK gesetzt - WebEngine-Segmente laufen UNGESPERRT." -ForegroundColor DarkYellow
        return $false
    }

    $pfad = Get-WebEngineSperrPfad
    $wartezeit = if ($env:LIGHTOS_WEBENGINE_SPERRE_WARTE) {
        [int]$env:LIGHTOS_WEBENGINE_SPERRE_WARTE
    } else { 900 }
    $ende = (Get-Date).AddSeconds($wartezeit)
    $gemeldet = $false
    while ($true) {
        try {
            $script:webSperreHandle = [System.IO.File]::Open(
                $pfad, [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
            $env:LIGHTOS_WEBENGINE_LOCK_HELD = "1"
            return $true
        }
        catch {
            $fehler = $_.Exception
            while ($fehler.InnerException) { $fehler = $fehler.InnerException }
            $win32 = $fehler.HResult -band 0xFFFF
            if ($script:WEB_SPERRE_BELEGT -notcontains $win32) {
                # Unbrauchbarer Pfad. Hier wird NICHT abgebrochen: die Sperre
                # ist eine Optimierung, kein Korrektheitskriterium.
                Write-Host ("[seg] Hinweis: WebEngine-Sperre nicht benutzbar ({0}, Win32 {1}) - weiter ohne." -f `
                            $fehler.GetType().Name, $win32) -ForegroundColor DarkYellow
                Write-Host ("[seg]   Pfad: {0}" -f $pfad) -ForegroundColor DarkYellow
                return $false
            }
            if ((Get-Date) -ge $ende) {
                Write-Host ("[seg] Hinweis: WebEngine-Sperre nach {0}s nicht bekommen - weiter ohne." -f $wartezeit) -ForegroundColor DarkYellow
                Write-Host "[seg]   Laeuft nebenher ein zweiter Gate-Lauf oder LightOS selbst?" -ForegroundColor DarkYellow
                return $false
            }
            if (-not $gemeldet) {
                Write-Host "[seg] WebEngine-Segment wartet auf die rechnerweite Sperre ..." -ForegroundColor DarkYellow
                $gemeldet = $true
            }
            Start-Sleep -Milliseconds 200
        }
    }
}

function Exit-WebEngineSperre {
    <#
        .SYNOPSIS
        Gibt die Sperre frei - aber nur, wenn dieser Lauf sie auch genommen hat.

        ⚠️ Die Bedingung haengt am HANDLE, nicht am Merkmal. Ein geerbtes
        LIGHTOS_WEBENGINE_LOCK_HELD gehoert dem Elternlauf, der sie noch haelt;
        loeschte man es hier mit, wuerde der naechste Enter-Aufruf in diesem
        Prozess auf den eigenen Elternlauf warten - genau die Verklemmung, die
        der Wiedereintritts-Schutz verhindern soll. Das Merkmal wird an genau
        einer Stelle gesetzt (beim erfolgreichen Open) und an genau dieser
        wieder entfernt.
    #>
    if (-not $script:webSperreHandle) { return }
    $script:webSperreHandle.Close()
    $script:webSperreHandle = $null
    Remove-Item Env:\LIGHTOS_WEBENGINE_LOCK_HELD -ErrorAction SilentlyContinue
}

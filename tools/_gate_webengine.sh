#!/usr/bin/env bash
# tools/_gate_webengine.sh — gemeinsame WebEngine-Absicherung der Linux-Gate-Runner.
#
# Wird von tools/verify_loop.sh UND tools/verify_segmented.sh GESOURCET, nicht
# gestartet. Dass beide dieselbe Datei benutzen, ist Absicht: XPLAT-11 war genau
# die Drift zweier Gate-Runner, die auseinandergelaufen sind.
#
# ── PROC-02c: warum es diese Datei gibt ──────────────────────────────────────
#
# `verify_segmented.sh` faehrt WebEngine-Segmente seit XPLAT-17 in einer
# seriellen Spur und wartete vor jedem bis zu 3 s darauf, dass "keine
# Chromium-Kindprozesse mehr laufen". Die Bedingung war
#
#     pgrep -u <uid> -x QtWebEngineProc
#
# — also RECHNERWEIT, ueber alle Sitzungen hinweg. Solange ein Mensch allein am
# Rechner sass, war das dasselbe wie "meine eigenen Kinder". Mit parallel
# arbeitenden Agenten ist es das nicht mehr: fremde Laeufe halten die Bedingung
# dauerhaft offen, jedes Segment laeuft stumpf in den Deckel, und das Warten
# bewirkt nichts ausser Verzoegerung. Gemessen 12./13.08.2026: ohne Last 1
# Segment im Deckel, mit einem Agenten 11, im Workflow 25 (PROC-02c).
#
# ★ NACHGEMESSEN 2026-08-18, und die Messung hat den naheliegenden Vorschlag
#   widerlegt statt bestaetigt:
#
#   (1) 41 WebEngine-Dateien, je ein eigener Segmentlauf, Zuordnung ueber die
#       Prozessgruppe: die EIGENEN Chromium-Kinder eines Segments sind nach
#       spaetestens 0,037 s weg (Median 0,022 s) — sie waren schon tot, bevor
#       `wait` auf den pytest-Prozess zurueckkam. Der 3-s-Deckel hat also NIE
#       auf eigene Kinder gewartet. Ihn dynamisch zu machen (Vorschlag (a) im
#       Item) haette nur laenger auf FREMDE Prozesse gewartet, auf die man
#       keinen Zugriff hat.
#   (2) Unter kuenstlicher Parallellast (3 nebenherlaufende WebEngine-Schleifen)
#       liefen 41 von 41 WebEngine-Segmenten in den Deckel — schlimmer als die
#       25 aus dem Item. Kosten: 123 s pro Lauf, Wirkung: keine.
#
# Deshalb hier zwei getrennte Dinge:
#
#  1. `webengine_sperre_nehmen` — eine RECHNERWEITE Sperre, die genau EIN
#     WebEngine-Segment gleichzeitig zulaesst, ueber Worktrees und Sitzungen
#     hinweg (Vorschlag (b) im Item). Das ist der Teil, der die Ursache trifft:
#     zwei gleichzeitig lebende WebGL-Kontexte.
#  2. `webengine_warte_auf_kinder` — das Warten, nur eben auf die EIGENE
#     Prozessgruppe und BEVOR die Sperre weitergereicht wird. Damit uebergibt
#     kein Lauf die Sperre, waehrend seine eigenen Chromium-Kinder noch leben.
#
# ⚠️ Beides darf das Gate nie blockieren. Fehlt `flock`, oder laeuft eine
# Wartezeit ab, wird gewarnt und weitergemacht — eine Sperre, die haengt, waere
# schlimmer als keine.
#
# ⚠️ Was das NICHT kann — vollstaendig, damit niemand die Zahl in
# `fremdes_chromium.txt` fuer unmoeglich haelt und sie deshalb falsch deutet:
#
#   * Wer pytest DIREKT startet, an beiden Gate-Runnern vorbei, nimmt die Sperre
#     nicht und wird von ihr auch nicht aufgehalten (WORKFLOW.md verbietet das,
#     die Sperre kann es nicht erzwingen).
#   * `LIGHTOS_VERIFY_SINGLE=1` faehrt die volle Suite bewusst in EINEM
#     pytest-Prozess. Dieser Weg nimmt die WebEngine-Sperre nicht — er haelt
#     die Voll-Suiten-Sperre ohnehin ueber die ganze Laufzeit, und die schmale
#     Sperre 7 Minuten am Stueck zu halten waere genau der Zustand, den PROC-02c
#     abstellt (jeder gezielte Lauf wartete dann auf die ganze Spur).
#   * Ein Lauf, dessen Wartezeit abgelaufen ist (Rueckgabe 3), laeuft
#     ausdruecklich UNGESPERRT weiter — eine haengende Sperre waere schlimmer
#     als keine.
#   * Ein Runner INNERHALB eines gesperrten Segments laeuft per
#     Wiedereintritts-Schutz ohne eigene Sperre (er ist ja schon gedeckt).

# ── Erkennung: zaehlt eine Testdatei als WebEngine-Datei? ────────────────────
# Dasselbe Merkmal wie in der Spur-Aufteilung von verify_segmented.sh: den
# Import von QWebEngineView hat jede Datei, die eine Seite laden kann, und
# keine andere (test_viz12_service.py etwa arbeitet nur am Service).
webengine_datei() {
    grep -q 'QWebEngineView' "$1" 2>/dev/null
}

# Dasselbe fuer einen beliebigen Pfad: Datei ODER Verzeichnis.
webengine_pfad() {
    if [ -d "$1" ]; then
        grep -rq --include='test_*.py' 'QWebEngineView' "$1" 2>/dev/null
    else
        webengine_datei "$1"
    fi
}

# ── Erkennung: beruehrt ein GEZIELTER Lauf WebEngine? ───────────────────────
# Bekommt die pytest-Argumente, antwortet 0 = ja (Sperre noetig), 1 = nein.
#
# ★ NACHTRAG 2026-08-19 — die erste Fassung von PROC-02c pruefte nur
# `[ -f "$pfad" ]` und uebersprang damit STILL genau die beiden Aufrufe, die am
# meisten WebEngine laden. Gemessen an der Arbeitsfassung, mit gehaltener
# Sperre und `LIGHTOS_WEBENGINE_SPERRE_WARTE=2`:
#
#   ./tools/verify_loop.sh <datei>.py   -> "Sperre nicht bekommen"  (gesperrt)
#   ./tools/verify_loop.sh <verz>/      -> keine Zeile              (UNGESPERRT!)
#
# Ein Verzeichnis ist kein Sonderfall, sondern der schlimmste Fall: `verify_loop.sh
# tests/` faehrt ALLE 41 WebEngine-Dateien in EINEM pytest-Prozess — und lief
# genau dabei an der Sperre vorbei. Ohne Pfadargument (`verify_loop.sh -k viz`)
# sammelt pytest die Vorgabe, also ebenfalls die ganze Suite.
#
# Die Richtung des Zweifels ist Absicht: im Unklaren wird gesperrt. Falsch
# gesperrt kostet Wartezeit, falsch offen kostet ein rotes Segment, das isoliert
# gruen ist — und das ist der Fehler, den dieses Item behebt.
webengine_argumente() {
    local hatte_pfad=0 arg pfad
    for arg in "$@"; do
        case "$arg" in -*) continue ;; esac
        pfad="${arg%%::*}"
        [ -e "$pfad" ] || continue          # z. B. der Wert hinter `-k`
        hatte_pfad=1
        webengine_pfad "$pfad" && return 0
    done
    [ "$hatte_pfad" = "1" ] && return 1
    # Kein Pfad dabei: pytest sammelt ab dem Arbeitsverzeichnis (pytest.ini setzt
    # kein `testpaths`), und beide Runner haben vorher in den Repo-Root
    # gewechselt — `tests/` ist damit immer Teil der Sammlung.
    webengine_pfad tests
}

# ── Sperrdatei ──────────────────────────────────────────────────────────────
# Am GEMEINSAMEN Git-Verzeichnis, damit sie fuer jeden Worktree desselben Repos
# dieselbe Datei ist — verschachtelte Agenten-Worktrees eingeschlossen. Das ist
# die Lehre aus PROC-02b: eine Sperre, die je Worktree eine eigene Datei nimmt,
# greift genau dort nicht, wo tatsaechlich parallel gearbeitet wird.
webengine_sperrdatei() {
    if [ -n "${LIGHTOS_WEBENGINE_LOCKFILE:-}" ]; then
        echo "$LIGHTOS_WEBENGINE_LOCKFILE"
        return 0
    fi
    local common
    common="$(git rev-parse --git-common-dir 2>/dev/null)"
    if [ -n "$common" ] && [ -d "$common" ]; then
        echo "$(cd "$common" && pwd)/.webengine_lock"
    else
        echo "$(cd .. 2>/dev/null && pwd)/.webengine_lock"
    fi
}

# Nimmt die Sperre auf Dateideskriptor 8.
#   0 = sofort bekommen        1 = nach Warten bekommen
#   2 = bewusst nicht genommen 3 = Wartezeit abgelaufen, laeuft UNGESPERRT weiter
# Der Rueckgabewert ist zum Protokollieren da; das Gate laeuft in jedem Fall weiter.
#
# Obergrenze fuers Warten: hergeleitet, nicht geraten. Ein Segment wird nach
# 300 s per `timeout` abgeschossen — laenger kann ein fremder Halter die Sperre
# im Segmentbetrieb nicht halten. Das Dreifache gibt auch einem gezielten Lauf
# ueber mehrere WebEngine-Dateien Luft.
webengine_sperre_nehmen() {
    WEBENGINE_SPERRE_GEHALTEN=0
    # ★ Wiedereintritt: ein Runner, der INNERHALB eines Segments laeuft, das die
    # Sperre bereits haelt, darf sie nicht noch einmal nehmen — er wartete sonst
    # auf sich selbst, bis die Wartezeit ablaeuft. Der Fall ist real:
    # tests/test_gate_webengine_lane.py zaehlt selbst als WebEngine-Segment und
    # startet den Segment-Runner erneut.
    [ -n "${LIGHTOS_WEBENGINE_LOCK_HELD:-}" ] && return 2
    command -v flock >/dev/null 2>&1 || return 2
    local datei warte
    datei="$(webengine_sperrdatei)"
    warte="${LIGHTOS_WEBENGINE_SPERRE_WARTE:-900}"
    exec 8>"$datei" 2>/dev/null || return 2
    if flock -n 8; then
        WEBENGINE_SPERRE_GEHALTEN=1
        export LIGHTOS_WEBENGINE_LOCK_HELD=1
        return 0
    fi
    if flock -w "$warte" 8; then
        WEBENGINE_SPERRE_GEHALTEN=1
        export LIGHTOS_WEBENGINE_LOCK_HELD=1
        return 1
    fi
    exec 8>&-
    return 3
}

webengine_sperre_freigeben() {
    [ "${WEBENGINE_SPERRE_GEHALTEN:-0}" = "1" ] || return 0
    unset LIGHTOS_WEBENGINE_LOCK_HELD
    exec 8>&-
    WEBENGINE_SPERRE_GEHALTEN=0
}

# ── Prozessgruppe eines gestarteten Segments ────────────────────────────────
# `timeout(1)` legt fuer den Befehl eine eigene Prozessgruppe an; die
# Chromium-Kinder erben sie und BEHALTEN sie, wenn ihr Elternprozess stirbt und
# sie an init umgehaengt werden. Damit ist die Prozessgruppe die zuverlaessige
# Zuordnung "eigenes Kind".
#
# ⚠️ Nicht ueber eine Umgebungsvariable: nachgemessen 2026-08-18 — QtWebEngine
# reicht die eigene Umgebung NICHT an seine Hilfsprozesse weiter, ein Etikett in
# `LIGHTOS_...` steht in deren /proc/<pid>/environ nicht. Und nicht ueber die
# Elternkette: die reisst genau dann, wenn es darauf ankaeme.
webengine_pgid() {
    local pid="${1:-}" pgid=""
    [ -n "$pid" ] || return 0
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    if [ -z "$pgid" ] && [ -r "/proc/$pid/stat" ]; then
        pgid="$(awk '{print $5}' "/proc/$pid/stat" 2>/dev/null)"
    fi
    echo "${pgid:-$pid}"
}

# 0 = keine eigenen Kinder mehr, 1 = Deckel erreicht.
#
# Deckel: ★ hergeleitet aus der Messung vom 2026-08-18 (41 WebEngine-Dateien, je
# ein eigener Segmentlauf) — laengster gemessener Wert 0,037 s. 2 s ist rund das
# 54-Fache: genug Luft fuer eine deutlich langsamere Maschine und klein genug,
# dass der Normalfall (Kinder sind bereits tot, die erste Abfrage genuegt)
# nichts kostet. Ein groesserer Deckel brachte nichts — er wuerde nur laenger
# auf etwas warten, das es nicht gibt.
webengine_warte_auf_kinder() {
    local pgid="${1:-}"
    [ -n "$pgid" ] || return 0
    local deckel runden uid i=0
    deckel="${LIGHTOS_WEBENGINE_KIND_DECKEL:-2.0}"
    runden=$(awk -v d="$deckel" 'BEGIN{printf "%d", (d*10)+0.5}')
    [ "$runden" -lt 1 ] && runden=1
    uid="$(id -u)"
    while [ "$i" -lt "$runden" ]; do
        # -g grenzt auf die Prozessgruppe ein, -x auf den PROZESSNAMEN.
        # ⚠️ Nicht `-f` auf die Kommandozeile: damit traefe das Muster die
        # eigene Shell, die Bedingung waere nie erfuellt und jedes Segment
        # liefe stumpf in den Deckel — so war die erste Fassung in
        # verify_segmented.sh gebaut. Der Name ist "QtWebEngineProc";
        # Linux kuerzt comm auf 15 Zeichen.
        pgrep -u "$uid" -g "$pgid" -x QtWebEngineProc >/dev/null 2>&1
        case $? in
            1) return 0 ;;   # keine gefunden -> frei
            0) : ;;          # noch welche da -> warten
            *) return 0 ;;   # pgrep kennt kein -g: nicht blockieren
        esac
        sleep 0.1
        i=$((i + 1))
    done
    return 1
}

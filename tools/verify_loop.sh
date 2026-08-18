#!/usr/bin/env bash
# tools/verify_loop.sh — Test-Gate fuer Linux/macOS (Pendant zu verify_loop.ps1).
#
# XPLAT-02: verify_loop.ps1 UND der sitzungsuebergreifende Lock-Runner ../run_tests.ps1
# sind PowerShell/Windows-spezifisch (run_tests.ps1 liegt zudem ausserhalb des Repos und
# fehlt einem frischen Linux-Checkout ganz). Der Lock-Runner serialisiert Davids mehrere
# gleichzeitige Windows-Sessions; auf einem gewoehnlichen Linux-Checkout/CI gibt es diese
# Parallelitaet nicht -> hier der direkte, plattformneutrale Weg: Syntax-Check (compileall
# src) + pytest. conftest.py setzt QT_QPA_PLATFORM=offscreen selbst; wir setzen es zur
# Sicherheit vorab.
#
# Aufruf (aus dem Repo-Root):
#   ./tools/verify_loop.sh                  # compileall + VOLLE Suite
#   ./tools/verify_loop.sh tests/test_x.py  # compileall + nur diese Tests
#
# Exit 0 = gruen, sonst rot.
set -u
cd "$(dirname "$0")/.." || { echo "[verify] FEHLER: Repo-Root nicht gefunden"; exit 2; }

# venv-Python finden: Linux/macOS zuerst, dann Windows-Git-Bash-Fallback.
PY=""
for cand in venv/bin/python venv/bin/python3 venv/Scripts/python.exe; do
    if [ -x "$cand" ] || [ -f "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "[verify] FEHLER: venv-Python nicht gefunden (venv/bin/python). venv anlegen: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 2
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

# PROC-02c: dieselbe WebEngine-Absicherung, die auch der Segment-Runner benutzt.
# Ueber den Repo-Root, nicht ueber $(dirname "$0"): oben wurde bereits dorthin
# gewechselt, ein relativer Aufrufpfad zeigte hier sonst ins Leere.
# shellcheck source=tools/_gate_webengine.sh
. "./tools/_gate_webengine.sh" || {
    echo "[verify] FEHLER: tools/_gate_webengine.sh fehlt oder ist fehlerhaft"; exit 2; }

# Exit-Haertung wie beim Windows-Lock-Runner: QtWebEngine-Sessions sterben auf
# Linux beim FINALEN Interpreter-Exit sporadisch mit SIGSEGV — NACH dem
# gemeldeten Ergebnis, die Assertions bestehen. conftest.py beendet den Prozess
# dann mit dem echten exitstatus (maskiert also keine Failures) und ueberspringt
# die crashende Abbauphase. Bewusst nur hier im Gate gesetzt, nicht fuer
# interaktives pytest — dort soll ein Teardown-Crash sichtbar bleiben.
export LIGHTOS_HARDEN_EXIT="${LIGHTOS_HARDEN_EXIT:-1}"

# ── PROC-02: Sperre gegen zwei gleichzeitige VOLLE Suiten ────────────────────
#
# ★ Die Annahme im Kopf dieser Datei — „auf einem gewoehnlichen Linux-Checkout
# gibt es diese Parallelitaet nicht" — stimmt seit dem 2026-08-06 nicht mehr:
# seitdem arbeiten zwei Claude-Sitzungen auf DEMSELBEN Linux-Rechner (s.
# COORDINATION.md). Der Windows-Lock-Runner hat hier kein Gegenstueck, es gab
# also gar nichts, was zwei volle Laeufe auseinandergehalten haette.
#
# Warum das nicht bloss langsam, sondern FALSCH ist: XPLAT-17 hat gemessen, dass
# schon EIN rechenintensives Nachbar-Segment (~1,3 s CPU) die WebEngine-Spur in
# 3 von 3 Laeufen reissen liess. Eine zweite komplette Suite ist ein sehr viel
# groesserer Nachbar. Beide Sitzungen saehen dann rote Segmente, die nichts mit
# ihrem Code zu tun haben — und wuerden sie deuten.
#
# Nur die VOLLE Suite wird gesperrt. Gezielte Einzellaeufe
# (`verify_loop.sh tests/test_x.py`) sind kurz und billig; sie zu serialisieren
# wuerde die Arbeit ausbremsen, ohne das Problem zu loesen.
#
# Die Sperrdatei haengt am GEMEINSAMEN Git-Verzeichnis (`--git-common-dir`) —
# das ist fuer jeden Worktree desselben Repos dieselbe Datei, egal wo er liegt.
#
# ★ PROC-02b: Vorher wurde sie als „Elternverzeichnis des Worktrees" bestimmt
# (`cd .. && pwd`). Das stimmt nur, solange alle Worktrees GESCHWISTER von
# `repo/` sind — die dokumentierte Konvention `~/projects/lightos/wt-<kurz>`.
# Agenten-Worktrees liegen aber VERSCHACHTELT unter `repo/.claude/worktrees/`
# und bekamen damit eine eigene Sperrdatei: die Serialisierung griff genau
# dort nicht, wo tatsaechlich parallel gearbeitet wird. Gemessen am
# 12.08.2026 — zwei volle Suiten liefen gleichzeitig, 11 WebEngine-Segmente
# starteten mit noch laufenden Chromium-Kindprozessen, zwei Segmente wurden
# rot. Eine Sperre, die stillschweigend nicht greift, ist schlimmer als
# keine: sie laesst das Ergebnis vertrauenswuerdig aussehen.
# Ohne `flock` (z. B. macOS) laeuft alles wie bisher weiter, nur mit Hinweis:
# eine fehlende Sperre darf das Gate nicht blockieren.
# Pfadbestimmung und Sperrnahme sind GETRENNT. Der Test zu dieser Sperre laeuft
# innerhalb der vollen Suite, die die echte Sperre bereits haelt — er darf den
# Pfad also erfragen koennen, ohne ihn zu belegen (sonst wartet er bis zum
# Timeout auf den eigenen Gate-Lauf; genau so ist es am 12.08. passiert).
_lockfile_pfad() {
    if [ -n "${LIGHTOS_LOCKFILE:-}" ]; then
        echo "$LIGHTOS_LOCKFILE"
        return 0
    fi
    # Kein Git (Tarball-Kopie)? Dann wie bisher das Elternverzeichnis.
    _common="$(git rev-parse --git-common-dir 2>/dev/null)"
    if [ -n "$_common" ] && [ -d "$_common" ]; then
        echo "$(cd "$_common" && pwd)/.pytest_lock"
    else
        echo "$(cd .. 2>/dev/null && pwd)/.pytest_lock"
    fi
}

LOCKFILE="$(_lockfile_pfad)"

_verify_lock() {
    [ "$#" -gt 0 ] && return 0                      # gezielter Lauf: keine Sperre
    [ -n "${LIGHTOS_VERIFY_NOLOCK:-}" ] && return 0
    command -v flock >/dev/null 2>&1 || {
        echo "[verify] Hinweis: kein flock — parallele Suiten sind nicht gesperrt"
        return 0
    }
    exec 9>"$LOCKFILE" 2>/dev/null || return 0
    if ! flock -n 9; then
        echo "[verify] Eine andere Sitzung faehrt gerade die volle Suite — warte ..."
        flock 9
        echo "[verify] Sperre frei, starte."
    fi
}
_verify_lock "$@"

# ★ QA-51: `tools` gehoert mit hinein. Bis hierhin kompilierte KEIN Gate die
# Werkzeuge — ein Syntaxfehler dort fiel erst auf, wenn jemand das Werkzeug
# benutzte. Besonders unangenehm bei `gen_tools_index.py`, das einen
# SyntaxError beim Einlesen einer Datei in die harmlose Index-Zelle
# „(Docstring nicht lesbar)" verwandelt: die kaputte Datei erscheint damit
# ordentlich im Verzeichnis, und der Index bestaetigt sie sogar.
echo "[verify] 1/2 Syntax-Check (compileall src tools) ..."
if ! "$PY" -m compileall -q src tools; then
    echo "[verify] SYNTAX-FEHLER"
    exit 1
fi

# ★ QA-53: Ausstieg NACH dem Syntax-Check, VOR dem Testlauf.
#
# Nur fuer den Test ZU dieser Sperre (test_verify_loop_sperre.py). Der startete
# bis hierhin den Runner ohne Argumente — und das ist die VOLLE Suite. Er hat
# damit mitten im laufenden Gate ein ZWEITES vollstaendiges Gate mit -j 3
# gestartet: gemessen 95 pytest-Prozesse, die sich ueber das geerbte
# LIGHTOS_SHOW_DB EINE Show-Datenbank teilten und sie einander beim
# conftest-Import per os.remove wegloeschten, dazu ein `rm -rf` auf das
# .pytest_segments des aeusseren Laufs. Das erklaert beides: die wandernden
# roten Segmente UND die falsche Abschlusszahl.
#
# Warum der Ausstieg HIER steht und nicht direkt nach `_verify_lock`: die
# Positivkontrolle des Tests ("der Runner laeuft ohne Sperre wirklich los")
# prueft auf den Syntax-Check. Steigt er davor aus, bewiese sie nichts mehr.
# Der zu testende Mechanismus — Sperre nehmen, warten, weitergehen — laeuft
# vollstaendig echt; es entfaellt nur die Nutzlast.
#
# ⚠️ Der Schalter macht das Gate zum No-Op. Er gehoert NICHT in CI und nicht in
# eine dauerhaft exportierte Umgebung: ein Lauf mit gesetztem DRYRUN beendet
# sich mit 0, ohne einen einzigen Test gefahren zu haben. Deshalb bleibt die
# Zeile „GRUEN - alles bestanden" hier bewusst aus — wer nur den Exit-Code
# liest, findet in der Ausgabe darueber wenigstens den Grund.
if [ -n "${LIGHTOS_VERIFY_DRYRUN:-}" ]; then
    # PROC-02b: Der Sperrpfad ist die einzige Angabe, die von aussen nicht
    # nachpruefbar waere — ein Test muesste sonst die Shell-Logik nachbauen und
    # damit seine eigene Kopie pruefen statt das Skript.
    echo "[verify] Sperrdatei: ${LOCKFILE:-<keine>}"
    echo "[verify] LIGHTOS_VERIFY_DRYRUN - Sperre und Syntax-Check erledigt, KEIN Testlauf."
    echo "[verify] Das ist KEINE bestandene Pruefung."
    exit 0
fi

if [ "$#" -gt 0 ]; then
    # Gezielte Dateien: direkt, in EINEM Prozess. Hier gibt es keinen ueber
    # Dateigrenzen akkumulierenden Zustand zu vermeiden, und der Weg ist schnell.
    #
    # ★ PROC-02c: von der VOLLEN-Suite-Sperre bleiben gezielte Laeufe bewusst
    # ausgenommen — kurz und billig, sie zu serialisieren wuerde nur bremsen.
    # Fuer WebEngine-Dateien stimmt das aber nur bei der Rechenzeit, nicht beim
    # WebGL-Kontext: davon gibt es rechnerweit nur einen brauchbaren Satz. Und
    # Agenten fahren fast ausschliesslich gezielte Laeufe — genau daran ging die
    # Annahme kaputt. Ein solcher Lauf nimmt deshalb dieselbe schmale
    # WebEngine-Sperre wie die WebEngine-Spur der vollen Suite. Alles andere
    # (die grosse Mehrheit) laeuft unveraendert ungebremst.
    _web=0
    for _arg in "$@"; do
        case "$_arg" in -*) continue ;; esac
        _pfad="${_arg%%::*}"
        if [ -f "$_pfad" ] && webengine_datei "$_pfad"; then _web=1; break; fi
    done
    echo "[verify] 2/2 pytest $* ..."
    if [ "$_web" = "1" ]; then
        webengine_sperre_nehmen
        case $? in
            1) echo "[verify] WebEngine-Sperre war belegt — gewartet, laufe jetzt exklusiv." ;;
            3) echo "[verify] ⚠ WebEngine-Sperre nicht bekommen, laufe UNGESPERRT weiter." ;;
        esac
    fi
    # `8>&-` schliesst den Sperr-Deskriptor im Kind: ein geerbtes Duplikat
    # hielte die Sperre sonst ueber das Laufende hinaus offen.
    "$PY" -m pytest "$@" -q --tb=short -p no:cacheprovider 8>&- &
    _pid=$!
    _pgid="$(webengine_pgid "$_pid")"
    wait "$_pid"
    _rc=$?
    if [ "$_web" = "1" ]; then
        # Erst die eigenen Chromium-Kinder abwarten, dann freigeben.
        webengine_warte_auf_kinder "$_pgid" || true
        webengine_sperre_freigeben
    fi
    if [ "$_rc" -ne 0 ]; then
        echo "[verify] TESTS ROT"
        exit 1
    fi
else
    # VOLLE SUITE: segmentiert, ein Prozess pro Testdatei (XPLAT-11).
    # Pendant zu Windows, wo verify_loop.ps1 an run_tests.ps1 -Isolate delegiert.
    # Grund: die volle Suite in EINEM Prozess starb auf Linux reproduzierbar bei
    # ~69 % an akkumulierendem nativem Qt-Zustand — an wechselnden Dateien, die
    # isoliert gruen laufen. Wer den Ein-Prozess-Lauf trotzdem will (z. B. um zu
    # pruefen, ob das noch gilt): LIGHTOS_VERIFY_SINGLE=1 setzen.
    if [ -n "${LIGHTOS_VERIFY_SINGLE:-}" ]; then
        echo "[verify] 2/2 pytest tests/ (volle Suite, EIN Prozess - LIGHTOS_VERIFY_SINGLE) ..."
        if ! "$PY" -m pytest tests/ -q --tb=short -p no:cacheprovider; then
            echo "[verify] TESTS ROT"
            exit 1
        fi
    else
        SEG="$(dirname "$0")/verify_segmented.sh"
        if [ ! -x "$SEG" ]; then
            echo "[verify] FEHLER: $SEG fehlt oder ist nicht ausfuehrbar"
            exit 2
        fi
        echo "[verify] 2/2 volle Suite segmentiert (${LIGHTOS_VERIFY_JOBS:-3} parallel) ..."
        if ! "$SEG" -j "${LIGHTOS_VERIFY_JOBS:-3}"; then
            echo "[verify] TESTS ROT"
            exit 1
        fi
    fi
fi

echo "[verify] GRUEN - alles bestanden."

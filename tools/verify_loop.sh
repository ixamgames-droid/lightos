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
# Die Sperrdatei liegt im PROJEKTORDNER, also ausserhalb des Repos — sonst
# haette jeder Worktree seine eigene und die Sperre waere wirkungslos.
# Ohne `flock` (z. B. macOS) laeuft alles wie bisher weiter, nur mit Hinweis:
# eine fehlende Sperre darf das Gate nicht blockieren.
_verify_lock() {
    [ "$#" -gt 0 ] && return 0                      # gezielter Lauf: keine Sperre
    [ -n "${LIGHTOS_VERIFY_NOLOCK:-}" ] && return 0
    command -v flock >/dev/null 2>&1 || {
        echo "[verify] Hinweis: kein flock — parallele Suiten sind nicht gesperrt"
        return 0
    }
    # Umlenkbar — und das ist keine Bequemlichkeit: der Test zu dieser Sperre
    # startet den Runner selbst und laeuft dabei INNERHALB der vollen Suite,
    # die die echte Sperre bereits haelt. Ohne eigene Datei pruefte er sich
    # gegen den eigenen Gate-Lauf und waere immer rot (bzw., schlimmer, gruen
    # aus dem falschen Grund).
    LOCKFILE="${LIGHTOS_LOCKFILE:-$(cd .. 2>/dev/null && pwd)/.pytest_lock}"
    exec 9>"$LOCKFILE" 2>/dev/null || return 0
    if ! flock -n 9; then
        echo "[verify] Eine andere Sitzung faehrt gerade die volle Suite — warte ..."
        flock 9
        echo "[verify] Sperre frei, starte."
    fi
}
_verify_lock "$@"

echo "[verify] 1/2 Syntax-Check (compileall src) ..."
if ! "$PY" -m compileall -q src; then
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
    echo "[verify] LIGHTOS_VERIFY_DRYRUN - Sperre und Syntax-Check erledigt, KEIN Testlauf."
    echo "[verify] Das ist KEINE bestandene Pruefung."
    exit 0
fi

if [ "$#" -gt 0 ]; then
    # Gezielte Dateien: direkt, in EINEM Prozess. Hier gibt es keinen ueber
    # Dateigrenzen akkumulierenden Zustand zu vermeiden, und der Weg ist schnell.
    echo "[verify] 2/2 pytest $* ..."
    if ! "$PY" -m pytest "$@" -q --tb=short -p no:cacheprovider; then
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

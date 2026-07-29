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

echo "[verify] 1/2 Syntax-Check (compileall src) ..."
if ! "$PY" -m compileall -q src; then
    echo "[verify] SYNTAX-FEHLER"
    exit 1
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

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

echo "[verify] 1/2 Syntax-Check (compileall src) ..."
if ! "$PY" -m compileall -q src; then
    echo "[verify] SYNTAX-FEHLER"
    exit 1
fi

if [ "$#" -gt 0 ]; then
    echo "[verify] 2/2 pytest $* ..."
    TARGET=("$@")
else
    echo "[verify] 2/2 pytest tests/ (volle Suite) ..."
    TARGET=(tests/)
fi

if ! "$PY" -m pytest "${TARGET[@]}" -q --tb=short -p no:cacheprovider; then
    echo "[verify] TESTS ROT"
    exit 1
fi

echo "[verify] GRUEN - alles bestanden."

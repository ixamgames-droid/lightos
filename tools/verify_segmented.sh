#!/usr/bin/env bash
# tools/verify_segmented.sh — Test-Gate in Segmenten (Linux-Pendant zu run_tests.ps1 -Isolate).
#
# WARUM ES DAS GIBT: Die volle Suite in EINEM pytest-Prozess starb auf Linux
# reproduzierbar bei ~69 % mit "Fatal Python error: Segmentation fault ...
# Garbage-collecting" — an wechselnden Dateien (test_snapshot_teardown_gc,
# test_sync_safe_subscribe), die isoliert gruen laufen. Ursache war also
# akkumulierender nativer Qt-Zustand, kein einzelner Test.
#
# Dieses Skript startet pro Testdatei einen eigenen pytest-Prozess. Nativer Zustand
# kann sich damit nicht ueber Dateigrenzen hinweg aufbauen. Langsamer als ein
# Sammellauf, dafuer aussagekraeftig — und es lokalisiert einen Crash auf die Datei.
#
# WARUM ES IM REPO LIEGT (XPLAT-11): bis 2026-07-29 lag es als bin/verify_segmented.sh
# ausserhalb des Repos, analog zu Davids run_tests.ps1. Das war der falsche Vergleich:
# run_tests.ps1 serialisiert Davids parallele Windows-Sessions und ist damit
# maschinenspezifisch — an diesem Skript hier ist nichts rechnerspezifisch. Die Folge
# war doppelt schaedlich: ein frischer Linux-Checkout hatte gar kein Gate fuer die
# volle Suite, und die beiden Runner drifteten auseinander (die Exit-Haertung aus
# XPLAT-08 landete nur in verify_loop.sh, weshalb ausgerechnet das real benutzte Gate
# 12 rote viz-Segmente meldete, die verify_loop.sh gruen sah).
#
#   ./tools/verify_segmented.sh                    alle Testdateien
#   ./tools/verify_segmented.sh -j 4               mit 4 parallelen Segmenten
#   ./tools/verify_segmented.sh tests/test_x.py    nur diese Dateien
#
# Ausgabe je Segment in $LIGHTOS_SEG_OUT (Default: .pytest_segments/ im Repo).
# Exit 0 = alles gruen. Sonst Anzahl roter Segmente.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || { echo "[seg] FEHLER: Repo-Root nicht gefunden"; exit 2; }

# venv-Python finden: Linux/macOS zuerst, dann Windows-Git-Bash-Fallback
# (identische Reihenfolge wie tools/verify_loop.sh).
PY=""
for c in venv/bin/python venv/bin/python3 venv/Scripts/python.exe; do
    if [ -x "$c" ] || [ -f "$c" ]; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
    echo "[seg] FEHLER: venv-Python nicht gefunden (venv/bin/python). venv anlegen: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 2
fi

JOBS=1
if [ "${1:-}" = "-j" ]; then JOBS="${2:-1}"; shift 2; fi

if [ "$#" -gt 0 ]; then FILES=("$@"); else
  mapfile -t FILES < <(find tests -name 'test_*.py' -type f | sort)
fi

OUTDIR="${LIGHTOS_SEG_OUT:-$REPO/.pytest_segments}"
rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"

# ── Gate-Umgebung ───────────────────────────────────────────────────────────
# MUSS identisch zu tools/verify_loop.sh bleiben — test_gate_runner_parity.py
# nagelt das fest. Genau diese Drift war XPLAT-11.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export LIGHTOS_HARDEN_EXIT="${LIGHTOS_HARDEN_EXIT:-1}"

echo "[seg] ${#FILES[@]} Testdateien, $JOBS parallel, Ausgabe: $OUTDIR"

run_one() {
    local f="$1"
    local safe="${f//\//_}"
    local log="$OUTDIR/${safe}.log"
    timeout 300 "$PY" -m pytest "$f" -q --tb=short -rf -p no:cacheprovider > "$log" 2>&1
    local rc=$?
    printf '%s\t%s\n' "$rc" "$f" >> "$OUTDIR/results.tsv"
    case $rc in
        0)   printf '  \033[32m ok \033[0m %s\n' "$f" ;;
        124) printf '  \033[33mZEIT\033[0m %s (>300s abgebrochen)\n' "$f" ;;
        13[0-9]|139) printf '  \033[31mSEGV\033[0m %s (Signal %s)\n' "$f" "$rc" ;;
        *)   printf '  \033[31mROT \033[0m %s (exit %s)\n' "$f" "$rc" ;;
    esac
}
export -f run_one; export PY OUTDIR

# ── Zwei Spuren: WebEngine seriell, Rest parallel ───────────────────────────
# WARUM (2026-08-01): Segmente, die eine echte three.js-Szene hochfahren,
# brauchen jeweils einen WebGL-Kontext. Laufen mehrere davon gleichzeitig,
# scheitert einer reproduzierbar mit
#   "THREE.WebGLRenderer: Error creating WebGL context"
# und faerbt das Gate rot — bei EINEM Fehlschlag pro Lauf, an wechselnden
# Dateien. Isoliert sind dieselben Dateien gruen (3/3 nachgemessen). Das ist
# also Kontext-Konkurrenz, kein Testfehler.
#
# Das ist gefaehrlicher als es klingt: Wer diese Rotfaerbung einmal als
# "das flackert halt" abtut, hat das Gate als Merge-Kriterium aufgegeben —
# ab dann sieht ein ECHTER roter Viz-Test genauso aus wie das Rauschen.
#
# Deshalb keine Wiederholungslogik (die wuerde echte Fehler mitheilen),
# sondern die Ursache weg: WebEngine-Dateien laufen in einer eigenen Spur
# mit genau EINEM Prozess. Die Spur laeuft NEBEN der normalen, nicht davor
# oder danach — gemessen 208 s seriell gegen ~390 s Gesamt-Gate, die
# serielle Spur ist also nicht der kritische Pfad und kostet keine Zeit.
#
# Marker ist der Import von QWebEngineView: den hat jede Datei, die eine
# Seite laden kann, und keine andere (test_viz12_service.py etwa arbeitet
# nur am Service und bleibt korrekt in der schnellen Spur).
WEB=(); REST=()
for f in "${FILES[@]}"; do
    if grep -q 'QWebEngineView' "$f" 2>/dev/null; then WEB+=("$f"); else REST+=("$f"); fi
done

if [ "$JOBS" -gt 1 ] && command -v xargs >/dev/null 2>&1; then
    echo "[seg] Spuren: ${#REST[@]} parallel ($JOBS), ${#WEB[@]} WebEngine seriell"
    web_pid=""
    if [ "${#WEB[@]}" -gt 0 ]; then
        ( for f in "${WEB[@]}"; do run_one "$f"; done ) &
        web_pid=$!
    fi
    if [ "${#REST[@]}" -gt 0 ]; then
        printf '%s\n' "${REST[@]}" | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
    fi
    [ -n "$web_pid" ] && wait "$web_pid"
else
    for f in "${FILES[@]}"; do run_one "$f"; done
fi

echo
BAD=$(awk -F'\t' '$1!=0' "$OUTDIR/results.tsv" 2>/dev/null | wc -l)
TOT=$(wc -l < "$OUTDIR/results.tsv" 2>/dev/null || echo 0)
echo "[seg] $((TOT-BAD))/$TOT Segmente gruen"
if [ "$BAD" -gt 0 ]; then
    echo "[seg] Rote Segmente:"
    awk -F'\t' '$1!=0 {printf "  exit %-4s %s\n", $1, $2}' "$OUTDIR/results.tsv"
    echo
    # Wichtig fuer die Triage: steht hier nichts, ist KEIN Test fehlgeschlagen —
    # dann sind die roten Segmente native Abbau-Crashes (QA-24). Das ist aber nur
    # eine Dringlichkeits-Einstufung, keine Entwarnung: XPLAT-09 versteckte sich
    # neun Dateien lang genau hinter dieser Lesart.
    echo "[seg] Fehlgeschlagene Tests:"
    grep -h '^FAILED' "$OUTDIR"/*.log 2>/dev/null | sed 's/^/  /' | sort -u
fi
exit "$BAD"

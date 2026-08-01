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

# XPLAT-17: warten, bis die Chromium-Kindprozesse des VORIGEN WebEngine-Segments
# wirklich weg sind.
#
# Die serielle Spur aus XPLAT-16 serialisiert die pytest-Prozesse — nicht deren
# Kinder. QtWebEngine startet einen eigenen GPU-Prozess, und der stirbt nach dem
# Elternprozess, nicht mit ihm. Zwei GPU-Prozesse koennen sich damit trotz Spur
# ueberlappen und um den GL-Kontext des Treibers konkurrieren.
#
# ★ GEMESSEN 2026-08-01 (6 volle Laeufe, 3210 Segment-Logs) — und die Vermutung
# oben stimmt so NICHT. Zwei harte Befunde:
#
#  1. Es gibt gar keinen "--type=gpu"-Hilfsprozess. QtWebEngine faehrt den
#     GPU-Dienst hier IM EIGENEN Prozess (nachgemessen waehrend eines Segments:
#     3x --type=zygote, 1x --type=renderer, 0x gpu; und die GPU-Fehlerzeilen im
#     Log tragen die pid:tid des pytest-Prozesses selbst). Die serielle Spur
#     serialisiert den GPU-Dienst damit bereits vollstaendig — zwei
#     konkurrierende GPU-Prozesse, die dieses Warten verhindern soll, kann es
#     zwischen den Segmenten nicht geben.
#  2. Der verbliebene Ausfall ist ein Kontextverlust INNERHALB des Prozesses:
#       RasterDecoderImpl: Context lost during MakeCurrent
#       -> SharedImageStub: context already lost
#       -> THREE.WebGLRenderer: Error creating WebGL context.   (die FOLGE)
#     Diese Signatur steht in genau 1 von 3210 Logs — sie ist der Fehler
#     selbst, kein Hintergrundrauschen.
#
# Rate mit Spur + diesem Warten: 1 Ausfall in 6 vollen Laeufen (davor: rund
# einer pro Lauf ohne Spur, 2 von 5 mit Spur ohne Warten).
#
# WARUM DAS WARTEN TROTZDEM BLEIBT: es wartet nachweislich auf etwas anderes
# als gedacht (Zygote-/Renderer-Kinder, nicht auf einen GPU-Prozess), aber ob
# es die Rate beeinflusst, ist NICHT gemessen — 1/6 gegen 2/5 ist bei diesen
# Zahlen kein Unterschied, den man behaupten kann. Es zu entfernen, weil die
# BEGRUENDUNG falsch war, hiesse eine unbelegte Behauptung durch die naechste
# zu ersetzen. Der Kommentar sagt jetzt, was es wirklich tut.
#
# Und die Konsequenz aus 2.: gegen einen Kontextverlust im eigenen Prozess
# hilft dem Gate kein Warten mehr. Der Ausweg liegt im Produkt — der
# Szenen-Start-Waechter (VIZ-SCENE-SELFHEAL, visualizer_window.py) laedt die
# Szene nach genau einem verlorenen Kontext neu, statt schwarz zu bleiben.
#
# Gedeckelt, damit es nie haengt: laeuft nebenher Davids LightOS-Instanz, halten
# deren Kindprozesse die Bedingung dauerhaft offen, und wir laufen sehenden Auges
# in den Deckel statt in eine Endlosschleife.
_warte_auf_freie_gpu() {
    local deckel=30            # 30 * 0.1 s = 3 s
    while [ "$deckel" -gt 0 ]; do
        # -x auf den PROZESSNAMEN, nicht -f auf die Kommandozeile: mit -f
        # trifft das Muster die eigene Shell (deren Kommandozeile den Text
        # ja enthaelt), die Bedingung ist dann NIE erfuellt und jedes
        # Segment laeuft stumpf in den Deckel. Genau das passierte in der
        # ersten Fassung: 27 von 27 Segmenten meldeten den Deckel, das
        # Warten war wirkungslos und kostete 81 s. Der Name ist "QtWeb-
        # EngineProc" — Linux kuerzt comm auf 15 Zeichen ab.
        pgrep -u "$(id -u)" -x QtWebEngineProc >/dev/null 2>&1 || return 0
        sleep 0.1
        deckel=$((deckel - 1))
    done
    return 1
}

run_one() {
    local f="$1"
    local safe="${f//\//_}"
    local log="$OUTDIR/${safe}.log"
    if [ "${SEG_WEBENGINE:-0}" = "1" ]; then
        _warte_auf_freie_gpu || echo "$f" >> "$OUTDIR/gpu_wartete_vergeblich.txt"
    fi
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
export -f run_one _warte_auf_freie_gpu; export PY OUTDIR

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
# sondern an die Ursache: WebEngine-Dateien laufen in einer eigenen Spur
# mit genau EINEM Prozess. Die Spur laeuft NEBEN der normalen, nicht davor
# oder danach — gemessen 208 s seriell gegen ~390 s Gesamt-Gate, die
# serielle Spur ist also nicht der kritische Pfad und kostet keine Zeit.
#
# ★ NACHTRAG 2026-08-01, XPLAT-17: das reicht NICHT — aber anders als zuerst
# gedacht. Der urspruengliche Eintrag sagte "Ursache weg", das war zu frueh
# geschlossen. Gemessen (6 volle Laeufe): 1 Ausfall, und zwar ein
# Kontextverlust IM EIGENEN Prozess, nicht zwischen zweien (Herleitung im
# Block bei _warte_auf_freie_gpu). Die Spur bleibt richtig und billig, sie
# kann diesen Rest aber prinzipiell nicht abfangen. Getroffen werden
# ausschliesslich Dateien, die view.show() aufrufen (5 der 29) — nur die
# realisieren eine echte Fensterflaeche.
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
        ( export SEG_WEBENGINE=1; for f in "${WEB[@]}"; do run_one "$f"; done ) &
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
if [ -f "$OUTDIR/gpu_wartete_vergeblich.txt" ]; then
    echo "[seg] HINWEIS (XPLAT-17): $(wc -l < "$OUTDIR/gpu_wartete_vergeblich.txt") WebEngine-Segmente"
    echo "[seg]   starteten, obwohl noch Chromium-Kindprozesse liefen (3-s-Deckel erreicht)."
    echo "[seg]   Laeuft nebenher eine LightOS-Instanz? Dann ist das erwartet."
fi
echo "[seg] $((TOT-BAD))/$TOT Segmente gruen"
if [ "$BAD" -gt 0 ]; then
    echo "[seg] Rote Segmente:"
    awk -F'\t' '$1!=0 {printf "  exit %-4s %s\n", $1, $2}' "$OUTDIR/results.tsv"
    echo
    # XPLAT-17: die EINE bekannte Fremd-Ursache beim Namen nennen.
    #
    # Das Segment bleibt rot und der Exit-Code ungleich 0 — hier wird nichts
    # gruen gerechnet und nichts wiederholt. Der Name ist der ganze Zweck:
    # ohne ihn steht der Mensch vor einem namenlosen roten Viz-Segment und muss
    # raten, ob es der bekannte Kontextverlust ist oder ein echter Fehler. Und
    # "im Zweifel Rauschen" ist genau die Gewoehnung, hinter der sich XPLAT-09
    # neun Testdateien lang versteckt hat.
    SIG=""
    while IFS=$'\t' read -r rc f; do
        [ "${rc:-0}" = "0" ] && continue
        lg="$OUTDIR/${f//\//_}.log"
        if grep -q 'Context lost during MakeCurrent' "$lg" 2>/dev/null \
           && grep -q 'Error creating WebGL context' "$lg" 2>/dev/null; then
            SIG="$SIG  $f"$'\n'
        fi
    done < "$OUTDIR/results.tsv"
    if [ -n "$SIG" ]; then
        echo "[seg] XPLAT-17-Signatur — GPU-Kontextverlust im eigenen Prozess:"
        printf '%s' "$SIG"
        echo "[seg]   'Context lost during MakeCurrent' + 'Error creating WebGL context'"
        echo "[seg]   Gemessen: 1 Ausfall in 6 vollen Laeufen (2026-08-01)."
        echo "[seg]   Gegenprobe: ./tools/verify_loop.sh <datei> — bleibt sie isoliert"
        echo "[seg]   gruen, war es dieser Fall. ROT bleibt trotzdem ROT."
        echo
    fi
    # Wichtig fuer die Triage: steht hier nichts, ist KEIN Test fehlgeschlagen —
    # dann sind die roten Segmente native Abbau-Crashes (QA-24). Das ist aber nur
    # eine Dringlichkeits-Einstufung, keine Entwarnung: XPLAT-09 versteckte sich
    # neun Dateien lang genau hinter dieser Lesart.
    echo "[seg] Fehlgeschlagene Tests:"
    grep -h '^FAILED' "$OUTDIR"/*.log 2>/dev/null | sed 's/^/  /' | sort -u
fi
exit "$BAD"

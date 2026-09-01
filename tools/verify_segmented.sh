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

# PROC-02c: die gemeinsame WebEngine-Absicherung beider Gate-Runner. Sie liegt
# in einer eigenen Datei, weil verify_loop.sh sie fuer gezielte Einzellaeufe
# genauso braucht — zwei Kopien derselben Sperre waeren die naechste XPLAT-11.
# shellcheck source=tools/_gate_webengine.sh
. "$REPO/tools/_gate_webengine.sh" || {
    echo "[seg] FEHLER: tools/_gate_webengine.sh fehlt oder ist fehlerhaft"; exit 2; }

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

# XPLAT-27: Merkmal fuer die Kinder — "du laeufst als Segment eines Gate-Laufs".
# Bewusst HART gesetzt und nicht per ${VAR:-wert}: die Aussage gilt hier immer.
# Wofuer: ein Test, der selbst einen Runner startet, erzeugt im Volllauf ein
# Gate IM Gate (QA-53) und konnte das bisher gar nicht erkennen — es gab kein
# Merkmal. Hier gesetzt, damit beide Plattformen dasselbe anbieten; auf Windows
# steht die Entsprechung in verify_segmented.ps1.
export LIGHTOS_IM_SEGMENT=1

echo "[seg] ${#FILES[@]} Testdateien, $JOBS parallel, Ausgabe: $OUTDIR"

# XPLAT-17 / PROC-02c: was vor einem WebEngine-Segment passiert.
#
# Die serielle Spur aus XPLAT-16 serialisiert die pytest-Prozesse — aber nur die
# DIESES Laufs. Bis 2026-08-18 stand hier zusaetzlich ein Warten von bis zu 3 s
# auf die Bedingung `pgrep -u <uid> -x QtWebEngineProc`: rechnerweit, ueber alle
# Sitzungen hinweg.
#
# ★ GEMESSEN 2026-08-18, und die Messung hat diesen Waechter widerlegt:
#
#  1. Die EIGENEN Chromium-Kinder eines Segments sind nach spaetestens 0,037 s
#     weg (41 WebEngine-Dateien, je ein eigener Segmentlauf, Zuordnung ueber die
#     Prozessgruppe; Median 0,022 s). Sie waren schon tot, bevor `wait` auf den
#     pytest-Prozess zurueckkam. Das Warten hat also NIE auf eigene Kinder
#     gewartet.
#  2. Unter Parallellast wartete es folglich nur auf FREMDE Prozesse — und die
#     verschwinden nicht, weil wir warten. Mit drei nebenherlaufenden
#     WebEngine-Schleifen liefen 41 von 41 Segmenten in den Deckel (3 Laeufe,
#     41/41/41). Kosten: 123 s je Lauf. Wirkung: keine.
#
# Der Deckel "dynamisch" zu machen (Vorschlag (a) in PROC-02c) haette das
# schlimmer gemacht, nicht besser: laenger auf etwas warten, worauf man keinen
# Zugriff hat. Stattdessen jetzt zwei Dinge, beide in tools/_gate_webengine.sh:
#
#   * eine RECHNERWEITE Sperre, die genau EIN WebEngine-Segment gleichzeitig
#     zulaesst — ueber Worktrees, Sitzungen und auch ueber gezielte Einzellaeufe
#     hinweg (verify_loop.sh nimmt dieselbe). Das trifft die Ursache: zwei
#     gleichzeitig lebende WebGL-Kontexte.
#   * das Warten auf die EIGENE Prozessgruppe, und zwar BEVOR die Sperre
#     weitergereicht wird. So uebergibt kein Lauf die Sperre, waehrend seine
#     eigenen Chromium-Kinder noch leben.
#
# Die Zahl aus dem Befund bleibt messbar: `fremdes_chromium.txt` zaehlt weiter,
# wie viele WebEngine-Segmente mit lebenden FREMDEN Chromium-Prozessen starten —
# nur kostet dieser Zustand jetzt keine Wartezeit mehr, sondern wird gemeldet.
#
# ── Was von XPLAT-17 gilt und hier nicht verlorengehen darf ─────────────────
# Gemessen 2026-08-01 (6 volle Laeufe, 3210 Segment-Logs):
#  * Es gibt gar keinen "--type=gpu"-Hilfsprozess. QtWebEngine faehrt den
#    GPU-Dienst IM EIGENEN Prozess (waehrend eines Segments nachgezaehlt:
#    3x --type=zygote, 1x --type=renderer, 0x gpu). Die serielle Spur
#    serialisiert ihn damit bereits — zwei konkurrierende GPU-Prozesse ZWISCHEN
#    zwei Segmenten desselben Laufs kann es nicht geben. Deshalb war das alte
#    Warten schon innerhalb eines Laufs wirkungslos.
#  * Der verbliebene Ausfall ist ein Kontextverlust INNERHALB des Prozesses:
#      RasterDecoderImpl: Context lost during MakeCurrent
#      -> SharedImageStub: context already lost
#      -> THREE.WebGLRenderer: Error creating WebGL context.   (die FOLGE)
#    Dagegen hilft dem Gate kein Warten; der Ausweg liegt im Produkt — der
#    Szenen-Start-Waechter (VIZ-SCENE-SELFHEAL, visualizer_window.py) laedt die
#    Szene nach genau einem verlorenen Kontext neu, statt schwarz zu bleiben.
#
# ⚠️ EHRLICH ZUR MESSGRENZE (2026-08-18): der Ausfall selbst liess sich hier
# nicht reproduzieren. In 123 WebEngine-Segmenten unter Parallellast (3 volle
# Durchlaeufe der Spur) plus 175 rohen pytest-Laeufen der Lastarbeiter kam KEIN
# einziges rotes Segment vor — weder vor noch nach dieser Aenderung. Die
# Wirkung ist deshalb an der Deckel-/Nachbarschaftszahl belegt (41 von 41 auf
# 0), nicht an einer Rate roter Segmente. Wer sie messen will, braucht einen
# Rechner, auf dem der Kontextverlust wieder auftritt.

run_one() {
    local f="$1"
    local safe="${f//\//_}"
    local log="$OUTDIR/${safe}.log"
    # ★ PROC-02c: die Spur kommt als ARGUMENT, nicht aus der Umgebung.
    #
    # Vorher stand hier `SEG_WEBENGINE`, gesetzt per `export` in der Spur —
    # und ein `export` erbt der pytest-Prozess mit. Startet ein Test darin
    # wieder einen Segment-Runner (tests/test_gate_webengine_lane.py und
    # tests/test_proc02c_webengine_sperre.py tun genau das), dann hielt der
    # INNERE Runner jede seiner Dateien fuer ein WebEngine-Segment — auch die
    # der schnellen Spur. Solange daran nur ein 3-s-Warten hing, fiel es nicht
    # auf; mit einer rechnerweiten Sperre haette es die schnelle Spur des
    # inneren Laufs serialisiert. Gefunden hat es der Test, nicht der Kopf:
    # er meldete "2 WebEngine-Segmente" fuer einen Lauf mit "0 WebEngine
    # seriell" in derselben Ausgabe.
    local web="${2:-0}"

    if [ "$web" = "1" ]; then
        webengine_sperre_nehmen
        case $? in
            1) echo "$f" >> "$OUTDIR/sperre_gewartet.txt" ;;
            3) echo "$f" >> "$OUTDIR/sperre_vergeblich.txt" ;;
        esac
        # Die Messgroesse aus PROC-02c, jetzt als reine Diagnose: laeuft JETZT
        # fremdes Chromium? Ein Nachbar, der ueber eines der beiden Gates geht,
        # kann das nicht mehr ausloesen — die Sperre haelt ihn auf. Bleibt die
        # Zahl gross, faehrt jemand pytest direkt (an beiden Gates vorbei) oder
        # es laeuft eine LightOS-Instanz.
        if pgrep -u "$(id -u)" -x QtWebEngineProc >/dev/null 2>&1; then
            echo "$f" >> "$OUTDIR/fremdes_chromium.txt"
        fi
    fi

    # Im Hintergrund, um die Prozessgruppe des Segments zu erfahren — `timeout`
    # legt dafuer eine eigene an. `8>&-` schliesst den Sperr-Deskriptor im Kind:
    # sonst haelt ein geerbtes Duplikat die Sperre ueber das Segmentende hinaus
    # offen (flock loest erst, wenn die LETZTE Kopie zu ist).
    timeout 300 "$PY" -m pytest "$f" -q --tb=short -rf -p no:cacheprovider \
        8>&- 9>&- > "$log" 2>&1 &
    local seg_pid=$! pgid=""
    [ "$web" = "1" ] && pgid="$(webengine_pgid "$seg_pid")"
    wait "$seg_pid"
    local rc=$?

    if [ "$web" = "1" ]; then
        # Erst warten, DANN freigeben — in dieser Reihenfolge liegt der Sinn:
        # sonst uebernaehme der naechste Lauf die Sperre, waehrend unsere
        # eigenen Chromium-Kinder noch leben.
        webengine_warte_auf_kinder "$pgid" || echo "$f" >> "$OUTDIR/kinder_deckel.txt"
        webengine_sperre_freigeben
    fi

    printf '%s\t%s\n' "$rc" "$f" >> "$OUTDIR/results.tsv"
    case $rc in
        0)   printf '  \033[32m ok \033[0m %s\n' "$f" ;;
        124) printf '  \033[33mZEIT\033[0m %s (>300s abgebrochen)\n' "$f" ;;
        13[0-9]|139) printf '  \033[31mSEGV\033[0m %s (Signal %s)\n' "$f" "$rc" ;;
        *)   printf '  \033[31mROT \033[0m %s (exit %s)\n' "$f" "$rc" ;;
    esac
}
export -f run_one webengine_sperre_nehmen webengine_sperre_freigeben \
          webengine_warte_auf_kinder webengine_pgid webengine_sperrdatei
export PY OUTDIR

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
# XPLAT-17-Block weiter oben). Die Spur bleibt richtig und billig, sie
# kann diesen Rest aber prinzipiell nicht abfangen. Getroffen werden
# ausschliesslich Dateien, die view.show() aufrufen (5 der 29) — nur die
# realisieren eine echte Fensterflaeche.
#
# Marker ist der Import von QWebEngineView: den hat jede Datei, die eine
# Seite laden kann, und keine andere (test_viz12_service.py etwa arbeitet
# nur am Service und bleibt korrekt in der schnellen Spur).
WEB=(); REST=()
for f in "${FILES[@]}"; do
    if webengine_pfad "$f"; then WEB+=("$f"); else REST+=("$f"); fi
done

if [ "$JOBS" -gt 1 ] && command -v xargs >/dev/null 2>&1; then
    echo "[seg] Spuren: ${#REST[@]} parallel ($JOBS), ${#WEB[@]} WebEngine seriell"
    web_pid=""
    if [ "${#WEB[@]}" -gt 0 ]; then
        ( for f in "${WEB[@]}"; do run_one "$f" 1; done ) &
        web_pid=$!
    fi
    if [ "${#REST[@]}" -gt 0 ]; then
        printf '%s\n' "${REST[@]}" | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
    fi
    [ -n "$web_pid" ] && wait "$web_pid"
else
    # Serieller Notweg (-j 1 oder kein xargs): die Spur-Trennung entfaellt hier,
    # die WebEngine-Absicherung nicht — sie gilt rechnerweit und haengt nicht
    # daran, wie DIESER Lauf seine Segmente verteilt.
    for f in "${FILES[@]}"; do
        if webengine_pfad "$f"; then run_one "$f" 1; else run_one "$f" 0; fi
    done
fi

echo
BAD=$(awk -F'\t' '$1!=0' "$OUTDIR/results.tsv" 2>/dev/null | wc -l)
TOT=$(wc -l < "$OUTDIR/results.tsv" 2>/dev/null || echo 0)
if [ -f "$OUTDIR/sperre_gewartet.txt" ]; then
    echo "[seg] $(wc -l < "$OUTDIR/sperre_gewartet.txt") WebEngine-Segmente warteten auf die rechnerweite"
    echo "[seg]   Sperre (.webengine_lock). Das ist der Normalfall bei paralleler Arbeit —"
    echo "[seg]   sie warten, statt sich gegenseitig den WebGL-Kontext wegzunehmen."
fi
if [ -f "$OUTDIR/sperre_vergeblich.txt" ]; then
    echo "[seg] ⚠ $(wc -l < "$OUTDIR/sperre_vergeblich.txt") WebEngine-Segmente bekamen die Sperre nicht"
    echo "[seg]   und liefen UNGESPERRT. Haengt ein Prozess auf .webengine_lock?"
fi
if [ -f "$OUTDIR/fremdes_chromium.txt" ]; then
    echo "[seg] HINWEIS (PROC-02c): $(wc -l < "$OUTDIR/fremdes_chromium.txt") WebEngine-Segmente starteten,"
    echo "[seg]   waehrend FREMDE Chromium-Prozesse liefen. Ein Nachbar, der ueber eines"
    echo "[seg]   der beiden Gates geht, wird von der Sperre aufgehalten — bleibt also:"
    echo "[seg]   eine laufende LightOS-Instanz, jemand mit direktem pytest, ein Lauf mit"
    echo "[seg]   LIGHTOS_VERIFY_SINGLE, oder ein Nachbar, dem die Sperre abgelaufen ist"
    echo "[seg]   (der meldet das seinerseits). Die vollstaendige Liste steht im Kopf von"
    echo "[seg]   tools/_gate_webengine.sh — sie ist ausdruecklich nicht leer."
    echo "[seg]   (Vor PROC-02c kostete dieser Zustand 3 s Wartezeit je Segment und"
    echo "[seg]   bewirkte nichts; gemessen 41 von 41 Segmenten unter Parallellast.)"
fi
if [ -f "$OUTDIR/kinder_deckel.txt" ]; then
    echo "[seg] ⚠ $(wc -l < "$OUTDIR/kinder_deckel.txt") WebEngine-Segmente hatten nach dem Deckel noch"
    echo "[seg]   EIGENE Chromium-Kinder. Gemessen sind die sonst nach <0,04 s weg —"
    echo "[seg]   diese Zeile sollte praktisch nie erscheinen."
fi
echo "[seg] $((TOT-BAD))/$TOT Segmente gruen"
# ★ QA-53: Die Abschlusszahl gegen die WIRKLICH gefahrene Dateizahl halten.
#
# Am 2026-08-06 meldete dieser Lauf „68/69 Segmente gruen", gefahren wurden 584
# Dateien. Die Vermutung damals — ein Zaehler aus der parallelen Spur erreicht
# den Elternprozess nicht — war falsch. TOT zaehlt die Zeilen in results.tsv,
# und ein ZWEITER Lauf im selben Repo beginnt mit `rm -rf "$OUTDIR"`: er raeumt
# die Zeilen des ersten weg, der zaehlt danach nur noch seinen Rest. Wer die
# Zahl liest, haelt einen Volllauf fuer einen Teillauf — und uebersieht, dass
# die roten Zeilen darunter womoeglich aus einem FREMDEN Lauf stammen.
#
# Die Ursache ist mit dem DRYRUN-Ausstieg in verify_loop.sh behoben; diese
# Pruefung bleibt, weil zwei Sitzungen auf einem Rechner denselben Fall jederzeit
# wieder erzeugen koennen (COORDINATION.md). Sie rechnet nichts gruen: sie sagt
# nur, dass die Zahl daneben nicht zu trauen ist.
UNVOLLSTAENDIG=0
if [ "$TOT" -ne "${#FILES[@]}" ]; then
    UNVOLLSTAENDIG=1
    echo "[seg] ⚠ WARNUNG: results.tsv hat $TOT Zeilen, gefahren wurden ${#FILES[@]} Dateien."
    echo "[seg]   Die Zahl oben ist damit UNVOLLSTAENDIG — vermutlich hat ein zweiter"
    echo "[seg]   Lauf im selben Repo das Ausgabeverzeichnis geleert ($OUTDIR)."
    echo "[seg]   Rote Zeilen koennen aus dem fremden Lauf stammen. Vor dem Deuten:"
    echo "[seg]   nachsehen, ob nebenher eine zweite Suite lief (QA-53)."
    echo "[seg]   Dieser Lauf gilt als NICHT bestanden — s. Exit-Code unten."
fi
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
        # ★ KORREKTUR 2026-08-01 (noch am selben Tag): hier stand ein UND auf
        # beide Zeilen -- Kontextverlust UND "Error creating WebGL context".
        # Das war falsch, und zwar aus einem Grund, der im Item selbst schon
        # stand: die WebGL-Zeile ist die FOLGE, nicht die Ursache, und sie
        # erscheint NICHT immer. Gemessen an einem dritten Ausfall desselben
        # Tages (test_viz14_place_ghost_scene.py): Kontextverlust im Log,
        # three.js schwieg, die Szene kam nur nicht hoch (Timeout auf
        # __lightosAppReady) -- die Signatur griff nicht.
        #
        # Das ist die GEFAEHRLICHERE Richtung: eine zu enge Erkennung sagt
        # "keine Signatur, also ein echter Fehler" und gibt damit falsche
        # Sicherheit -- genau die Verwechslung, gegen die sie gebaut wurde.
        # Erkannt wird deshalb die URSACHE, unabhaengig von ihrer Folge.
        if grep -qE 'Context lost during MakeCurrent|context already lost' "$lg" 2>/dev/null; then
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
# ★★ QA-53: Eine unvollstaendige Ergebnisliste darf NICHT gruen sein.
#
# `BAD` zaehlt die roten Zeilen in results.tsv — aus derselben Datei, die ein
# zweiter Lauf per `rm -rf` wegraeumt. Mit ihr verschwinden auch die ROTEN
# Zeilen: BAD wird 0, der Exit-Code 0, und das Gate meldet **gruen, obwohl
# Segmente rot waren**. Das ist die gefaehrlichere Haelfte des Befunds — die
# falsche Zahl sieht man, das falsche Gruen nicht.
#
# Deshalb hier „im Zweifel rot": wer nicht weiss, ob alles gelaufen ist, hat
# kein bestandenes Gate, sondern ein kaputtes Messgeraet.
if [ "$UNVOLLSTAENDIG" -eq 1 ] && [ "$BAD" -eq 0 ]; then
    echo "[seg] Ergebnisliste unvollstaendig -> KEIN Gruen (QA-53)."
    exit 1
fi
exit "$BAD"

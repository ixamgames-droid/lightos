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
    # ★ PROC-02c hat eine ZWEITE Sperrdatei dazugestellt — und dieselbe Frage
    # wie PROC-02b: gilt sie ueber Worktree-Grenzen? Sie hier zu melden ist der
    # einzige Weg, das an der ECHTEN Aufloesung zu messen statt an einer
    # nachgebauten Formel. Ohne diese Zeile blieb die Mutation „je Worktree eine
    # eigene Datei" gruen — nachgemessen 2026-08-19, alle 35 Gate-Tests gruen.
    echo "[verify] WebEngine-Sperrdatei: $(webengine_sperrdatei)"
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
    # Die Entscheidung liegt in webengine_argumente (tools/_gate_webengine.sh),
    # weil sie mehr Faelle kennt als „ist das eine Datei mit dem Marker": ein
    # VERZEICHNIS-Argument und ein Lauf ganz ohne Pfad laden beide die ganze
    # Suite — die frueheste Fassung hier uebersprang genau die, still.
    _web=0
    if webengine_argumente "$@"; then _web=1; fi
    echo "[verify] 2/2 pytest $* ..."
    if [ "$_web" = "1" ]; then
        webengine_sperre_nehmen
        case $? in
            1) echo "[verify] WebEngine-Sperre war belegt — gewartet, laufe jetzt exklusiv." ;;
            3) echo "[verify] ⚠ WebEngine-Sperre nicht bekommen, laufe UNGESPERRT weiter." ;;
        esac
    fi
    # ★ VORDERGRUND, anders als im Segment-Runner — und das ist gemessen, nicht
    # Geschmack. Dort laeuft pytest unter `timeout`, das per setpgid eine eigene
    # Prozessgruppe anlegt; nur deshalb braucht es dort den Umweg ueber `&` und
    # `wait`, um die Gruppen-ID zu erfahren. Hier gibt es kein `timeout`: ein
    # Hintergrundjob einer nicht-interaktiven Shell bleibt in der Gruppe des
    # Skripts (nachgemessen 2026-08-19: Skript pgid 7346, Hintergrundkind pgid
    # 7346, `timeout`-Kind pgid 7356). Das `&` haette hier also NICHTS gebracht
    # und eines gekostet: die Standardeingabe eines asynchronen Befehls wird auf
    # /dev/null gelegt. Gemessen am selben Tag unter echtem Terminal — mit `&`
    # meldete `pytest -s` fd 0 als /dev/null (isatty False), ohne als /dev/pts/1.
    # Damit waren `--pdb`, `breakpoint()` und `--trace` in JEDEM gezielten Lauf
    # tot, WebEngine hin oder her.
    #
    # `8>&-` schliesst den Sperr-Deskriptor im Kind: ein geerbtes Duplikat
    # hielte die Sperre sonst ueber das Laufende hinaus offen (flock loest erst,
    # wenn die LETZTE Kopie zu ist).
    #
    # ★ PROC-02d: Hier steht bewusst KEIN `9>&-` daneben, obwohl fd 9 die
    # Voll-Suiten-Sperre traegt. Auf diesem Zweig wird sie gar nicht genommen —
    # `_verify_lock` steigt bei Argumenten aus, BEVOR `exec 9>` laeuft.
    # Nachgemessen 2026-08-19 in einem Wegwerf-Repo: nach einem gezielten Lauf
    # existiert die Sperrdatei nicht einmal, und im pytest-Prozess zeigt fd 9
    # auf das, was der AUFRUFER dort offen hatte. Ein `9>&-` waere damit nicht
    # pruefbar (die Mutation bliebe zwangslaeufig gruen) und schloesse nur einen
    # fremden Deskriptor. Dass dieser Zweig sperrfrei bleibt, haelt
    # tests/test_verify_loop_sperre.py fest
    # (test_gezielter_lauf_wird_nicht_gesperrt) — wer das aendert, wird dort rot
    # und findet ueber diesen Kommentar zurueck.
    "$PY" -m pytest "$@" -q --tb=short -p no:cacheprovider 8>&-
    _rc=$?
    if [ "$_web" = "1" ]; then
        # Erst die eigenen Chromium-Kinder abwarten, DANN freigeben — sonst
        # uebernimmt der naechste Lauf die Sperre, waehrend unsere noch leben.
        # Die Prozessgruppe ist die dieses Laufs (Skript + Nachkommen): enger
        # als rechnerweit, weiter als nur der pytest-Prozess. Genau die Gruppe,
        # in der die Chromium-Kinder haengen bleiben.
        webengine_warte_auf_kinder "$(webengine_pgid $$)" || \
            echo "[verify] ⚠ Nach dem Deckel liefen noch EIGENE Chromium-Kinder. Gemessen sind die sonst nach <0,04 s weg."
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
    #
    # ★★ PROC-02d — `9>&-` an BEIDEN Wegen der vollen Suite.
    #
    # Ab hier ist fd 9 die gehaltene Voll-Suiten-Sperre. Ohne den Schluss erbt
    # sie JEDER Nachkomme: der Segment-Runner, jedes `timeout`, jeder
    # Segment-pytest und jedes Chromium-Kind darunter. `flock` loest aber erst,
    # wenn die LETZTE Kopie des Deskriptors zu ist — ein einziges ueberlebendes
    # Kind haelt die Sperre damit ueber das Gate-Ende hinaus, und zwar
    # rechnerweit (die Datei haengt am gemeinsamen Git-Verzeichnis, s. o.). Der
    # naechste volle Lauf auf diesem Rechner wartet dann ohne Deckel: `flock 9`
    # in `_verify_lock` hat keine Wartezeit, das Gate steht einfach.
    #
    # Gemessen 2026-08-19 in einem Wegwerf-Repo, vor der Aenderung, mit einem
    # Testkind, das `sleep 300` abgekoppelt und mit `close_fds=False` startet
    # (so startet Chromium seine Hilfsprozesse): in /proc/<enkel>/fd stand
    # `9 -> .../.git/.pytest_lock`, und `flock -n` bekam die Sperre nicht — auf
    # BEIDEN Wegen, dem segmentierten wie dem Ein-Prozess-Lauf.
    #
    # ⚠️ Der Deskriptor muss je Befehl geschlossen werden, nicht global: ein
    # `exec 9>&-` waere die Freigabe der Sperre selbst.
    if [ -n "${LIGHTOS_VERIFY_SINGLE:-}" ]; then
        echo "[verify] 2/2 pytest tests/ (volle Suite, EIN Prozess - LIGHTOS_VERIFY_SINGLE) ..."
        if ! "$PY" -m pytest tests/ -q --tb=short -p no:cacheprovider 9>&-; then
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
        # ★ HIER bewusst OHNE `9>&-` — das ist eine Korrektur an der ersten
        # Fassung dieses Fixes, und der Grund ist ein Tausch, den sie nicht
        # benannt hat:
        #
        # `9>&-` an DIESER Stelle nimmt dem Segment-Runner die Sperre komplett,
        # nicht nur seinen Blaettern. Stirbt dann die oberste
        # `verify_loop.sh`-Shell (kill, Harness-Abbruch, OOM), waehrend
        # `verify_segmented.sh` samt Segment-pytests weiterlaeuft, ist die
        # rechnerweite Sperre SOFORT frei — und ein zweiter voller Lauf startet
        # neben dem noch laufenden ersten. Genau dieser Zustand ist teuer
        # belegt: PROC-02b (zwei gleichzeitige Suiten, 11 WebEngine-Segmente
        # mit laufenden Chromium-Kindern) und QA-53 (der zweite Lauf raeumt das
        # `.pytest_segments` des ersten ab).
        #
        # Vor dem Leck hielten die Kinder die Sperre in genau diesem Fall. Das
        # war Nebenwirkung eines Fehlers — aber es war Schutz, und ihn
        # kommentarlos einzutauschen waere eine Verschlechterung gewesen.
        #
        # Der Waisen-Fall ist stattdessen am BLATT geschlossen
        # (`tools/verify_segmented.sh`, `timeout 300 … 8>&- 9>&-`): dort erbt
        # kein timeout/pytest/Chromium mehr etwas, und der Runner selbst behaelt
        # die Sperre ueber seine ganze Lebensdauer. Dasselbe Muster benutzt die
        # WebEngine-Sperre fuer fd 8.
        if ! "$SEG" -j "${LIGHTOS_VERIFY_JOBS:-3}"; then
            echo "[verify] TESTS ROT"
            exit 1
        fi
    fi
fi

echo "[verify] GRUEN - alles bestanden."

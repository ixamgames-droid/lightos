#!/usr/bin/env bash
# tools/app.sh — Linux-Pendant zu tools/app.ps1 (App-Steuerung fuer UI-Verifikation).
#
# app.ps1 nutzt Windows-APIs (GDI/Win32) fuer Fenstersteuerung und Screenshots.
# Hier der X11-Weg ueber wmctrl + gnome-screenshot.
#
# WARUM ES IM REPO LIEGT (2026-07-30): es lag als ../tools/app.sh ausserhalb, mit
# der Begruendung "wie run_tests.ps1 auf Windows". Das war derselbe falsche
# Vergleich wie bei XPLAT-11: run_tests.ps1 serialisiert Davids parallele
# Windows-Sessions und ist damit MASCHINEN-spezifisch — an diesem Skript hier ist
# nichts rechnerspezifisch, und sein Windows-Gegenstueck tools/app.ps1 liegt
# ohnehin im Repo. Die Folge war dieselbe: ein frischer Linux-Checkout hatte kein
# App-Steuerskript, und drei Fehler darin (s. _running_pid / _win_id) blieben
# ungetestet und unreviewed liegen, bis sie eine UI-Verifikation still
# entwertet haben.
#
#   ./tools/app.sh start            App starten (headed, im Hintergrund)
#   ./tools/app.sh stop             App beenden (SIGTERM, dann SIGKILL)
#   ./tools/app.sh restart          stop + start
#   ./tools/app.sh wait [sek]       warten bis das LightOS-Fenster da ist (Default 60)
#   ./tools/app.sh shot <pfad> [-w] Screenshot; -w = nur aktives Fenster
#   ./tools/app.sh fg               LightOS-Fenster nach vorn holen
#   ./tools/app.sh untop            "immer im Vordergrund" abschalten
#   ./tools/app.sh status           laeuft die App? Fenster da?
#
# Exit 0 = ok, sonst Fehler.
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/lightos-app.pid"
LOGFILE="$ROOT/logs/app.log"
WIN_PATTERN="${LIGHTOS_WIN_PATTERN:-LightOS}"

die() { echo "[app] FEHLER: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 nicht installiert (sudo apt install $2)"; }

# ★ Die App zuverlaessig finden — 2026-07-30 gleich dreifach schiefgegangen.
#
# Das PID-File haelt die PID von `start.sh`. Die beendet sich, sobald sie Python
# gestartet hat -> `_running_pid` schlug fehl, `stop` meldete "laeuft nicht",
# `restart` wurde still zum No-op. Man screenshottet dann den ALTEN Build und
# glaubt, verifiziert zu haben. Genau so ist mir eine UI-Verifikation entgangen.
#
# Der Fallback in cmd_stop suchte zudem nach `$REPO/venv/bin/python.*main.py`,
# also dem ABSOLUTEN Pfad — die echte Kommandozeile ist aber relativ
# (`venv/bin/python main.py`), weil start.sh vorher ins Repo wechselt. Er konnte
# also nie greifen.
#
# Darum: erst das PID-File, dann eine Prozesssuche, die ueber das
# ARBEITSVERZEICHNIS abgleicht statt ueber die Pfad-Schreibweise. Das trifft
# genau diesen Checkout und keinen zweiten daneben.
_app_pid_by_scan() {
    local p
    for p in $(pgrep -f "venv/bin/python.*main\.py" 2>/dev/null); do
        [ "$(readlink -f "/proc/$p/cwd" 2>/dev/null)" = "$(readlink -f "$REPO")" ] \
            && { echo "$p"; return 0; }
    done
    return 1
}

_running_pid() {
    local pid
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
        rm -f "$PIDFILE"
    fi
    _app_pid_by_scan
}

# Alle PIDs unterhalb (und einschliesslich) einer PID — der Fenster-Prozess ist
# ein KIND von start.sh, nicht die PID aus dem PID-File.
_pid_tree() {
    local roots="$1" next
    while [ -n "$roots" ]; do
        echo "$roots" | tr ' ' '\n'
        next=""
        for p in $roots; do
            next="$next $(pgrep -P "$p" 2>/dev/null | tr '\n' ' ')"
        done
        roots="$(echo "$next" | xargs 2>/dev/null)"
    done
}

_win_id() {
    command -v wmctrl >/dev/null 2>&1 || return 1
    # ★ PID-basiert, NICHT ueber den Fenstertitel. Der Titelabgleich griff auf
    # `grep -F "LightOS"` — und traf damit auch das Firefox-Fenster des
    # Backlog-Dashboards ("Second Brain — LightOS Backlog — Mozilla Firefox").
    # Folge: `shot -w` fotografierte still das FALSCHE Fenster, und eine
    # UI-Verifikation war damit wertlos, ohne dass es auffiel (2026-07-30 live
    # passiert). Der Fenster-Prozess ist ein Kind von start.sh, darum der
    # ganze Prozessbaum statt eines PID-Vergleichs.
    local pid ids
    if pid=$(_running_pid); then
        ids=$(_pid_tree "$pid" | sort -u | tr '\n' '|' | sed 's/|$//')
        if [ -n "$ids" ]; then
            local hit
            hit=$(wmctrl -lp 2>/dev/null | awk -v re="^($ids)$" '$3 ~ re {print $1; exit}')
            [ -n "$hit" ] && { echo "$hit"; return 0; }
        fi
    fi
    # Fallback ohne laufende PID (z. B. App von Hand gestartet): EXAKTER Titel
    # statt Teilstring — sonst wieder der Firefox-Treffer oben.
    wmctrl -l 2>/dev/null \
        | awk -v want="$WIN_PATTERN" '{ $1=$1; t=""; for(i=4;i<=NF;i++) t=t (i>4?" ":"") $i;
                                        if (t == want) { print $1; exit } }'
}

cmd_start() {
    if pid=$(_running_pid); then echo "[app] laeuft bereits (PID $pid)"; return 0; fi
    [ -x "$REPO/start.sh" ] || die "start.sh nicht gefunden unter $REPO"
    mkdir -p "$(dirname "$LOGFILE")"
    ( cd "$REPO" && nohup ./start.sh >>"$LOGFILE" 2>&1 & echo $! >"$PIDFILE" )
    sleep 1
    if pid=$(_running_pid); then echo "[app] gestartet (PID $pid), Log: $LOGFILE"; else
        die "Start fehlgeschlagen — letzte Zeilen:$(printf '\n'; tail -15 "$LOGFILE" 2>/dev/null)"
    fi
}

cmd_stop() {
    # Der frühere Fallback suchte hier nach dem ABSOLUTEN Pfad
    # ($REPO/venv/bin/python...) und konnte deshalb nie greifen — die echte
    # Kommandozeile ist relativ. Die Suche steckt jetzt in _running_pid und
    # gleicht über das Arbeitsverzeichnis ab.
    if ! pid=$(_running_pid); then echo "[app] laeuft nicht"; return 0; fi
    kill -TERM "$pid" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
    if kill -0 "$pid" 2>/dev/null; then
        echo "[app] reagiert nicht auf SIGTERM -> SIGKILL"; kill -KILL "$pid" 2>/dev/null
    fi
    rm -f "$PIDFILE"; echo "[app] beendet"
}

cmd_wait() {
    local limit="${1:-60}"
    need wmctrl wmctrl
    for _ in $(seq 1 "$limit"); do
        [ -n "$(_win_id)" ] && { echo "[app] Fenster da"; return 0; }
        sleep 1
    done
    die "Fenster '$WIN_PATTERN' nach ${limit}s nicht erschienen"
}

cmd_shot() {
    local out="${1:-}"; shift || true
    [ -n "$out" ] || die "Pfad fehlt: app.sh shot <pfad> [-w]"
    need gnome-screenshot gnome-screenshot
    mkdir -p "$(dirname "$out")"
    if [ "${1:-}" = "-w" ]; then
        cmd_fg; sleep 0.6
        gnome-screenshot -w -B -f "$out" || die "Screenshot fehlgeschlagen"
    else
        gnome-screenshot -f "$out" || die "Screenshot fehlgeschlagen"
    fi
    [ -s "$out" ] || die "Screenshot leer: $out"
    echo "[app] Screenshot: $out ($(stat -c%s "$out") Bytes)"
}

cmd_fg() {
    need wmctrl wmctrl
    local id; id=$(_win_id) || true
    [ -n "$id" ] || die "kein Fenster '$WIN_PATTERN' gefunden"
    wmctrl -i -a "$id" && echo "[app] Fenster nach vorn geholt"
}

cmd_untop() {
    need wmctrl wmctrl
    local id; id=$(_win_id) || true
    [ -n "$id" ] || { echo "[app] kein Fenster — nichts zu tun"; return 0; }
    wmctrl -i -r "$id" -b remove,above && echo "[app] 'immer im Vordergrund' aus"
}

cmd_status() {
    if pid=$(_running_pid); then echo "prozess: laeuft (PID $pid)"; else echo "prozess: laeuft nicht"; fi
    if command -v wmctrl >/dev/null 2>&1; then
        local id; id=$(_win_id) || true
        [ -n "$id" ] && echo "fenster: $id" || echo "fenster: keins"
    fi
}

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
    wait)    shift; cmd_wait "$@" ;;
    shot)    shift; cmd_shot "$@" ;;
    fg)      cmd_fg ;;
    untop)   cmd_untop ;;
    status)  cmd_status ;;
    *) sed -n '5,20p' "$0"; exit 2 ;;
esac

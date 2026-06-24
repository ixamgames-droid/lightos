"""STAB-01: Crash-Logging-Infrastruktur.

Ziel: crash.log so aussagekraeftig machen, dass man hinterher erkennt **WANN**
und **WIE** LightOS abgestuerzt ist. Frueher fehlten dafuer mehrere Bausteine:
kein Session-Start-/Exit-Marker (man wusste nicht, welcher Eintrag zu welchem Lauf
gehoert), native Crashes (Access Violations) ohne Zeitbezug, Standby/Resume wurde
als stundenlanger "Freeze" fehlgedeutet, Worker-Thread-Fehler tauchten gar nicht
auf, und ein Fehler-Sturm (ein Fehler je Frame) blies das Log mit identischen
Tracebacks zu.

Dieses Modul buendelt die **reine Logik** (ohne Qt/faulthandler) — dadurch ist sie
ohne laufende GUI testbar. `main.py` verdrahtet sie mit faulthandler,
`sys`/`threading.excepthook`, dem Qt-Message-Handler und dem Freeze-Watchdog.

Wie "Absturz vs. sauberes Beenden" erkannt wird (deckt AUCH native Crashes ab, die
kein Python-Hook sieht):
- Beim Start wird eine ``lightos_running.flag`` angelegt und beim sauberen Exit
  (``atexit``) wieder geloescht. Liegt sie beim naechsten Start noch da, ist die
  vorherige Sitzung NICHT sauber zu Ende gegangen (nativer Crash/Kill/Stromausfall).
- Ein Daemon-Thread schreibt ~alle 4 s einen Zeitstempel nach ``last_alive.txt``.
  Der zeigt beim naechsten Start, *wann* die abgestuerzte Sitzung zuletzt lebte —
  selbst wenn faulthandler dem nativen Dump keinen Zeitstempel voranstellen kann
  (faulthandler schreibt per Datei-Deskriptor, nicht ueber Python ``write()``).
"""
from __future__ import annotations

import datetime
import os
import sys
import traceback

# --- Schwellen -------------------------------------------------------------
FREEZE_THRESHOLD_S = 10.0      # Heartbeat-Stillstand ab hier = UI-Freeze (Dump)
SUSPEND_LOOP_GAP_S = 30.0      # War der Watch-Thread SELBST so lange weg -> Standby


def _ts(now: datetime.datetime | None = None) -> str:
    """ISO-Zeitstempel auf Sekunden (lokal). ``now`` injizierbar fuer Tests."""
    return (now or datetime.datetime.now()).isoformat(timespec="seconds")


# --- Rotation --------------------------------------------------------------
def rotate_if_large(path: str, max_bytes: int = 2 * 1024 * 1024,
                    backups: int = 3) -> bool:
    """Rotiert ``path`` -> ``path.1`` … ``path.N``, wenn er ``max_bytes`` ueber-
    schreitet, und gibt True zurueck, wenn rotiert wurde.

    Verhindert, dass crash.log/lightos.log ueber Monate unbegrenzt waechst
    (das alte lightos.log war ~9,8 MB). Logging darf NIE den Start verhindern —
    daher faengt die Funktion alle Fehler ab und gibt dann einfach False zurueck.
    """
    try:
        if not path or not os.path.exists(path):
            return False
        if os.path.getsize(path) <= max_bytes:
            return False
        oldest = f"{path}.{backups}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for i in range(backups - 1, 0, -1):
            src = f"{path}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{path}.{i + 1}")
        os.replace(path, f"{path}.1")
        return True
    except Exception:
        return False


# --- Marker-Zeilen ---------------------------------------------------------
def session_banner(version: str = "?", now: datetime.datetime | None = None,
                   pid: int | None = None) -> str:
    """Start-Banner — trennt Laeufe im append-only-Log und nennt Umgebung."""
    import platform
    pid = os.getpid() if pid is None else pid
    return (f"\n=== LightOS STARTED {_ts(now)} | v{version} | "
            f"Python {sys.version.split()[0]} | "
            f"{platform.system()} {platform.release()} | PID {pid} ===\n")


def clean_exit_marker(now: datetime.datetime | None = None) -> str:
    """Wird per ``atexit`` geschrieben. SEIN FEHLEN = die Sitzung ist abgestuerzt."""
    return f"=== LightOS CLOSED (sauberer Exit) {_ts(now)} ===\n"


def fatal_exit_marker(now: datetime.datetime | None = None) -> str:
    """STAB-05: Wird per ``atexit`` geschrieben, wenn die Sitzung NACH einer
    ungefangenen (Main-Thread-)Exception endet. BEWUSST kein Clean-Marker — sonst
    wuerde die Vorige-Sitzung-Erkennung den Absturz beim naechsten Start nicht
    sehen (der Clean-Marker bzw. die geloeschte Running-Flag wuerde 'sauber'
    suggerieren)."""
    return f"=== LightOS ABGESTUERZT (ungefangene Exception) {_ts(now)} ===\n"


def previous_crash_notice(last_alive_ts: str | None,
                          now: datetime.datetime | None = None) -> str:
    """Beim Start geschrieben, wenn die vorige Sitzung nicht sauber endete."""
    when = last_alive_ts or "unbekannt"
    return (f"=== VORHERIGE SITZUNG NICHT SAUBER BEENDET "
            f"(Absturz/Kill/Stromausfall) — zuletzt lebendig ~{when} "
            f"[erkannt {_ts(now)}] ===\n")


def suspend_notice(loop_gap: float, now: datetime.datetime | None = None) -> str:
    """Statt eines Fake-Freezes: Standby/Resume klar als solches kennzeichnen."""
    return (f"\n=== WATCHDOG: System-Standby/Resume erkannt "
            f"({loop_gap:.0f}s Luecke) {_ts(now)} — Heartbeat zurueckgesetzt, "
            f"KEIN echter UI-Freeze ===\n")


def freeze_header(stall: float, now: datetime.datetime | None = None) -> str:
    return (f"\n=== UI-FREEZE erkannt {_ts(now)} "
            f"({stall:.0f}s ohne Event-Loop) — Stacks aller Threads: ===\n")


# --- Freeze/Standby-Klassifikation (rein, testbar) -------------------------
def is_freeze(stall: float, threshold: float = FREEZE_THRESHOLD_S) -> bool:
    """UI-Freeze: der GUI-Heartbeat stand >= ``threshold`` Sekunden still."""
    return stall >= threshold


def is_suspend(loop_gap: float, threshold: float = SUSPEND_LOOP_GAP_S) -> bool:
    """Standby: der WATCH-Thread selbst war viel laenger als seine 2-s-Schleife
    weg -> der ganze Prozess war eingefroren (Suspend), kein reiner UI-Freeze.

    Das ist der zuverlaessige Diskriminator: ein echter UI-Freeze blockiert nur
    den GUI-Thread; der Daemon-Watch-Thread tickt dann normal weiter (loop_gap ~2s).
    Bei Standby steht auch der Watch-Thread -> loop_gap wird riesig.
    """
    return loop_gap > threshold


# --- Exception-Formatierung + Sturm-Drossel --------------------------------
def exc_signature(exc_type, exc_tb) -> str:
    """Kompakte Signatur ``Typ@datei:zeile`` aus dem untersten Frame — Basis fuer
    die Dedup (gleicher Fehler an gleicher Stelle = ein Sturm)."""
    name = getattr(exc_type, "__name__", str(exc_type))
    last = None
    tb = exc_tb
    while tb is not None:
        last = tb
        tb = tb.tb_next
    if last is not None:
        code = last.tb_frame.f_code
        return f"{name}@{os.path.basename(code.co_filename)}:{last.tb_lineno}"
    return name


def format_python_exception(exc_type, exc_value, exc_tb,
                            now: datetime.datetime | None = None,
                            thread_name: str | None = None) -> str:
    """Voller Traceback-Block mit Zeitstempel (und ggf. Worker-Thread-Name)."""
    head = f"\n=== Python Exception {_ts(now)}"
    if thread_name:
        head += f" [Thread: {thread_name}]"
    head += " ===\n"
    return head + "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


class ExceptionDedup:
    """Drosselt Fehler-Stuerme. Pro Signatur hoechstens 1 Volltext-Traceback je
    ``min_interval`` Sekunden; dazwischen wird nur gezaehlt. Beim naechsten
    Volltext derselben Signatur wird die Zahl der unterdrueckten als Hinweis
    vorangestellt. Verhindert das fruehere Verhalten (ein Fehler je Maus-Frame
    -> hunderte identische Tracebacks, Log unlesbar).

    ``now`` ist eine monotone Zeit (z. B. ``time.monotonic()``), in Tests ein float.
    """

    def __init__(self, min_interval: float = 5.0):
        self.min_interval = min_interval
        self._last_full: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}

    def decide(self, sig: str, now: float) -> tuple[bool, int]:
        """Gibt ``(volltext_schreiben, anzahl_unterdrueckt)`` zurueck.

        ``anzahl_unterdrueckt`` > 0 nur, wenn jetzt wieder Volltext faellig ist und
        seit dem letzten Volltext gleichartige Fehler gedrosselt wurden.
        """
        last = self._last_full.get(sig)
        if last is None or (now - last) >= self.min_interval:
            suppressed = self._suppressed.get(sig, 0)
            self._last_full[sig] = now
            self._suppressed[sig] = 0
            return True, suppressed
        self._suppressed[sig] = self._suppressed.get(sig, 0) + 1
        return False, 0


# --- "zuletzt lebendig" + Running-Flag (Crash-vs-sauber-Erkennung) ---------
def write_last_alive(path: str | None, now: datetime.datetime | None = None) -> None:
    """Einzeilige Datei mit dem aktuellen Zeitstempel (truncate). Vom Watchdog
    periodisch aktualisiert -> nach einem nativen Crash steht hier ~die Crash-Zeit."""
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_ts(now))
    except Exception:
        pass


def read_last_alive(path: str | None) -> str | None:
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception:
        return None


def mark_running(flag_path: str | None) -> bool:
    """Legt die Running-Flag an (Inhalt: PID). Beim sauberen Exit wieder geloescht."""
    if not flag_path:
        return False
    try:
        with open(flag_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def clear_running(flag_path: str | None) -> None:
    if not flag_path:
        return
    try:
        if os.path.exists(flag_path):
            os.remove(flag_path)
    except Exception:
        pass


def finalize_exit(log_handle, flag_path: str | None, had_fatal: bool,
                  now: datetime.datetime | None = None) -> None:
    """STAB-05: atexit-Finalisierung als reine, GUI-freie Logik (damit
    ``main._on_exit`` nur noch verdrahtet und testbar bleibt).

    - ``had_fatal`` (es lief eine ungefangene Main-Thread-Exception): KEIN
      Clean-Marker, und die Running-Flag BLEIBT liegen -> der naechste Start
      erkennt den Absturz, genau wie bei einem nativen Crash.
    - sonst: Clean-Marker schreiben + Running-Flag entfernen (sauberer Exit).
    """
    try:
        if log_handle is not None:
            log_handle.write(fatal_exit_marker(now) if had_fatal
                             else clean_exit_marker(now))
            log_handle.flush()
    except Exception:
        pass
    if not had_fatal:
        clear_running(flag_path)

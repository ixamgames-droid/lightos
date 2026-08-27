"""OUT-54: Haelt schon jemand diesen seriellen Port?

WARUM
-----
Am 26.08.2026 hingen an Davids ``/dev/ttyUSB0`` **fuenf** Prozesse gleichzeitig:
vier verwaiste Ausgabe-Worker frueherer LightOS-Laeufe plus der Worker der
laufenden App. Je ~15,6 kB/s; bei 57600 Baud traegt die Leitung 5760 B/s — also
13,5-fach ueberbucht.

Das Fehlerbild sah aus wie ein Softwarefehler in der Show: das Geraet blinkte,
nichts war steuerbar — **aber Blackout funktionierte**. Diese Asymmetrie ist das
Erkennungszeichen und lohnt sich zu merken: *Dunkel ist der einzige Zustand,
ueber den sich mehrere konkurrierende Sender einig sind.* Jedes „an" kaempft
gegen die anderen, jedes „aus" wird von allen bestaetigt.

OUT-53 hat die haeufigste Quelle beseitigt (der Worker beendet sich jetzt mit
seinem Elternprozess). Dieses Modul deckt den Rest ab, den OUT-53 nicht kann:

* eine **zweite LightOS-Instanz**,
* ein **fremdes Programm** auf demselben Port (QLC+, ein Terminal, ein Skript),
* ein Waisenkind aus einer **aelteren Version** ohne den OUT-53-Fix.

★ **Es wird nur GEWARNT, nicht blockiert.** Ein Ausgang, der sich wegen einer
Vermutung selbst abschaltet, ist im Live-Betrieb schlimmer als einer, der sich
die Leitung teilt: Der Nutzer steht dann im dunklen Saal vor einer Meldung. Die
Warnung nennt PID und Kommandozeile — damit ist der Fehler in Sekunden zu
finden statt in einer Stunde.

Nur Linux (``/proc``). Auf anderen Systemen liefert die Pruefung eine leere
Liste; sie darf den Start nie behindern.
"""
from __future__ import annotations

import os
import sys


def port_belegt_von(port: str, eigene_pid: int | None = None,
                    proc_root: str = "/proc") -> list[tuple[int, str]]:
    """Welche fremden Prozesse halten ``port`` offen? ``[(pid, kommandozeile)]``.

    Der eigene Prozess wird ausgelassen (``eigene_pid``, Vorgabe ``os.getpid()``)
    — sonst meldete jede Pruefung nach dem eigenen Oeffnen einen Treffer.
    Defensiv: jede Unlesbarkeit eines einzelnen ``/proc``-Eintrags wird
    uebersprungen, nicht propagiert. Ein Diagnose-Helfer darf den Start der
    Ausgabe niemals verhindern.
    """
    if eigene_pid is None:
        eigene_pid = os.getpid()
    treffer: list[tuple[int, str]] = []
    try:
        eintraege = os.listdir(proc_root)
    except OSError:
        return treffer
    for eintrag in eintraege:
        if not eintrag.isdigit():
            continue
        pid = int(eintrag)
        if pid == eigene_pid:
            continue
        fd_dir = os.path.join(proc_root, eintrag, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue                      # fremder Nutzer / Prozess schon weg
        for fd in fds:
            try:
                if os.readlink(os.path.join(fd_dir, fd)) != port:
                    continue
            except OSError:
                continue
            try:
                with open(os.path.join(proc_root, eintrag, "cmdline"), "rb") as fh:
                    cmd = fh.read().replace(b"\0", b" ").decode(errors="replace").strip()
            except OSError:
                cmd = ""
            treffer.append((pid, cmd[:120]))
            break
    return treffer


def warne_wenn_belegt(port: str, ausgabe=None) -> list[tuple[int, str]]:
    """Meldet fremde Halter des Ports auf stderr. Gibt sie zurueck (fuer Tests).

    Blockiert NICHT — siehe Modulkopf.
    """
    if ausgabe is None:
        ausgabe = sys.stderr
    treffer = port_belegt_von(port)
    if not treffer:
        return treffer
    print(f"[OutputManager] WARNUNG: {port} wird bereits von "
          f"{len(treffer)} anderen Prozess(en) gehalten:", file=ausgabe)
    for pid, cmd in treffer:
        print(f"[OutputManager]   PID {pid}  {cmd}", file=ausgabe)
    print("[OutputManager] Zwei Sender auf einer seriellen Leitung ergeben "
          "zerhacktes DMX: das Geraet blinkt und reagiert nicht, waehrend "
          "Blackout scheinbar funktioniert.", file=ausgabe)
    print("[OutputManager] Laeuft LightOS doppelt? Sonst sind es Waisen eines "
          "hart beendeten Laufs — einzeln per PID beenden.", file=ausgabe)
    return treffer

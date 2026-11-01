"""MTC-04: Cues nach MIDI Time Code ausloesen.

Eine Cue mit gesetztem Feld ``timecode`` ("HH:MM:SS:FF") wird ausgeloest, wenn
der empfangene MTC diesen Wert **erreicht oder ueberschreitet**: zwischen der
vorigen und der aktuellen Position liegt ihr Timecode (``vorher < tc <= jetzt``).
Ueberspringt der MTC mehrere Cues einer Liste in einem Schritt (Vorspulen,
verlorene Pakete), springt die Liste nur auf die **letzte** davon — kein
Durchblitzen der dazwischen.

**Ruecksprung:** laeuft der Timecode rueckwaerts (DAW auf Anfang, Schleife),
wird nichts ausgeloest; die Position gilt als neu gesetzt, und Cues danach
loesen beim erneuten Erreichen wieder aus. Beim ersten Timecode und nach einem
Ruecksprung zaehlt zusaetzlich ein kurzer Anlauf (``ANLAUF_S``): eine Cue
genau am Startpunkt (z. B. 00:00:00:00) wuerde sonst nie ausgeloest, weil der
erste vollstaendige Quarter-Frame-Satz erst zwei Frames spaeter ankommt.

**Wo ausgeloest wird (ENG-33):** der MTC kommt im MIDI-Dispatch-Thread an;
``melden`` merkt sich nur die Position. Ausgeloest wird im Render-Takt —
``PlaybackEngine.compute_merged`` ruft ``anwenden`` vor dem Ticken der Listen,
derselbe Weg wie faellige Follow-Cues. So schaltet der MIDI-Thread nie selbst
an einer Cueliste, und der Folge-Fade startet im selben Bild.

Es zaehlen nur Cuelisten, die auf einem Executor liegen (alle Pages).
"""
from __future__ import annotations

import threading

#: Anlauf beim ersten Timecode / nach Ruecksprung (Sekunden).
ANLAUF_S = 0.2


def tc_sekunden(timecode: str, fps: float) -> float | None:
    """ "HH:MM:SS:FF" -> Sekunden bei ``fps`` (None bei ungueltiger Angabe)."""
    try:
        h, m, s, f = (int(t) for t in str(timecode).split(":"))
    except (TypeError, ValueError):
        return None
    fps = float(fps) if fps and fps > 0 else 25.0
    return h * 3600 + m * 60 + s + f / fps


class TimecodeAusloeser:
    def __init__(self):
        self._lock = threading.Lock()
        self._neu: tuple[float, float] | None = None   # (sekunden, fps)
        self._letzte: float | None = None

    def melden(self, h: int, m: int, s: int, f: int, fps: float = 25.0) -> None:
        """Neue MTC-Position (beliebiger Thread)."""
        fps = float(fps) if fps and fps > 0 else 25.0
        with self._lock:
            self._neu = (h * 3600 + m * 60 + s + f / fps, fps)

    def zuruecksetzen(self) -> None:
        with self._lock:
            self._neu = None
            self._letzte = None

    def anwenden(self, stacks) -> list:
        """Im Render-Takt: faellige Timecode-Cues ausloesen. Liefert
        ``[(stack, cue_nummer), …]`` der ausgeloesten Spruenge."""
        with self._lock:
            neu, self._neu = self._neu, None
        if neu is None:
            return []
        jetzt, fps = neu
        vorher, self._letzte = self._letzte, jetzt
        if vorher is None or jetzt < vorher:
            vorher = jetzt - ANLAUF_S          # erster Wert / Ruecksprung
        if jetzt == vorher:
            return []
        ausgeloest = []
        gesehen: set[int] = set()
        for stack in stacks:
            if stack is None or id(stack) in gesehen:
                continue
            gesehen.add(id(stack))
            ziel, ziel_t = None, None
            for cue in list(getattr(stack, "cues", ()) or ()):
                tc = getattr(cue, "timecode", None)
                if not tc:
                    continue
                t = tc_sekunden(tc, fps)
                if t is None or not (vorher < t <= jetzt):
                    continue
                if ziel_t is None or t >= ziel_t:
                    ziel, ziel_t = cue, t
            if ziel is None:
                continue
            if getattr(stack, "current_cue", None) is ziel:
                continue
            try:
                stack.go_to(ziel.number)
                ausgeloest.append((stack, ziel.number))
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("mtc.cue", e)
        return ausgeloest


_ausloeser: TimecodeAusloeser | None = None


def vorhandener_ausloeser() -> TimecodeAusloeser | None:
    """Der Ausloeser, falls schon verdrahtet (sonst None — kein MTC, nichts zu tun)."""
    return _ausloeser


def verdrahten(midi_manager=None) -> TimecodeAusloeser:
    """MTC-Leser an die gemeinsame MIDI-Empfangsschleife haengen und seine
    Positionen an den Ausloeser geben. Idempotent (App-Start, MIDI-Autoconnect)."""
    global _ausloeser
    from .mtc_reader import get_mtc_reader
    reader = get_mtc_reader()
    if _ausloeser is None:
        a = TimecodeAusloeser()

        def _weiter(h, m, s, f, _r=reader, _a=a):
            _a.melden(h, m, s, f, _r.fps())

        reader.subscribe(_weiter)
        _ausloeser = a
    reader.an_manager_haengen(midi_manager)
    return _ausloeser

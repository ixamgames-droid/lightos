"""ENG-33 — gemeinsame, ersetzbare Show-Zeit fuer Cue-Fades, Follow-Cues und Effekte.

Vorher hatte jede Ebene ihre eigene Uhr: Cue-Fades ``perf_counter`` (QA-89),
Follow-Cues einen ``threading.Timer``, die Effekt-Vorschau ``time.monotonic``,
der Render-Pfad der Effekte das ``dt`` des Ausgabe-Takts. Wer Bild fuer Bild
rendert (Aufnahmen, Headless-Pruefungen, ``_render_frame`` in einer Schleife),
sah deshalb Effekte laufen, aber keinen Fade und keinen Follow.

Jetzt lesen Cue-Fades, Follow-Faelligkeit und die Effekt-Vorschau ``jetzt()``.

* **Standard** ist ``time.perf_counter`` — dieselbe Uhr wie die Fades seit
  QA-89. In der App aendert sich nichts: unter Windows ist ``perf_counter``
  QueryPerformanceCounter (100 ns), ``monotonic`` dagegen ``GetTickCount64``
  mit 15,625-ms-Raster; unter Linux sind beide dieselbe Uhr.
* **Ersetzt** wird sie fuer Aufnahmen und Tests: ``manuelle_uhr()`` setzt eine
  Uhr ein, die nur auf ``vorruecken(dt)`` weiterlaeuft — z. B. um 1/44 s je
  gerendertem Bild. Kein Schlafen, kein Wettlauf mit der Wanduhr.

⚠️ Prozessweit, nicht je Thread: die App rendert in EINEM Ausgabe-Thread, und
genau dort soll die Zeit gelten. Nur umschalten, wenn nichts laeuft
(Aufnahme-Start, Testanfang): Zeitanker, die vor dem Wechsel gesetzt wurden,
stammen von der alten Uhr (anderer Nullpunkt) — ein laufender Fade spraenge.

Bewusst NICHT an dieser Uhr: Tap-Tempo (``tap_uhr`` — misst echte Tastendruecke),
der BPM-Takt (``bpm_manager.takt_uhr`` — echte Musik), Audio-Funktionen
(spielen echtes Audio in Echtzeit) und Zeitlimits/Entprellungen der Ausgabe.
"""
from __future__ import annotations

import contextlib
import threading
import time
from typing import Callable, Iterator

#: Uhr der App — unveraendert die Fade-Uhr seit QA-89.
STANDARD_UHR: Callable[[], float] = time.perf_counter

_uhr: Callable[[], float] = STANDARD_UHR


def jetzt() -> float:
    """Aktuelle Show-Zeit in Sekunden (nur fuer Abstaende; Nullpunkt beliebig)."""
    return _uhr()


def aktuelle_uhr() -> Callable[[], float]:
    return _uhr


def setze_uhr(uhr: Callable[[], float] | None) -> Callable[[], float]:
    """Show-Uhr ersetzen (``None`` = Standard). Liefert die bisherige Uhr."""
    global _uhr
    alt = _uhr
    _uhr = STANDARD_UHR if uhr is None else uhr
    return alt


class ManuelleUhr:
    """Uhr, die nur auf ``vorruecken`` weiterlaeuft (Bild-fuer-Bild, Tests)."""

    def __init__(self, start: float = 0.0):
        self._t = float(start)
        self._lock = threading.Lock()

    def __call__(self) -> float:
        return self._t

    def vorruecken(self, dt: float) -> float:
        if dt < 0:
            raise ValueError("Show-Zeit laeuft nicht rueckwaerts")
        with self._lock:
            self._t += float(dt)
            return self._t


@contextlib.contextmanager
def manuelle_uhr(start: float = 0.0) -> Iterator[ManuelleUhr]:
    """``with manuelle_uhr() as uhr: ... uhr.vorruecken(1/44)`` — danach wieder die alte Uhr."""
    uhr = ManuelleUhr(start)
    alt = setze_uhr(uhr)
    try:
        yield uhr
    finally:
        setze_uhr(alt)

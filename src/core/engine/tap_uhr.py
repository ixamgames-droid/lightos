"""Zeitquelle fuer Tap-Tempo (QA-87) — hochaufloesend auf allen Plattformen.

``time.monotonic()`` ist unter Windows ``GetTickCount64()`` und hat eine
Aufloesung von 15,625 ms (gemessen 2026-10-08, Windows 11: zwei Aufrufe direkt
hintereinander liefern denselben Wert). Fuer Tap-Tempo heisst das:

* Zwei Taps im selben Tick haben den Abstand 0 — der Tap wird verworfen bzw.
  teilte im lokalen ``VCSpeedDial``-Zweig durch null.
* Jeder Abstand ist auf 15,625 ms gerastert. Simuliert mit IDEAL getappten
  Schlaegen (also ohne jedes menschliche Zittern) liegt die Tap-BPM bei
  130 BPM nach zwei Taps bis 2,4 BPM daneben, nach fuenf Taps (Mittel ueber
  vier Abstaende) noch bis 0,9 BPM; bei 174 BPM bis 7,0 bzw. 1,4 BPM.

``time.perf_counter()`` ist unter Windows ``QueryPerformanceCounter``
(100 ns) und auf Linux dieselbe monotone Uhr wie ``monotonic`` — dort aendert
sich also nichts.

⚠️ Nur fuer ABSTAENDE zwischen Taps gedacht. ``perf_counter`` und
``monotonic`` haben verschiedene Nullpunkte: wer einen Tap-Zeitpunkt mit
anderen Zeitstempeln vergleicht (Beat-Anker ``_last_beat_mono``, Musik-Raster),
muss dieselbe Uhr nehmen. Deshalb eine eigene, benannte Quelle statt
verstreuter ``perf_counter``-Aufrufe — und Tests koennen ``jetzt`` gezielt
ersetzen, ohne die Uhr des ganzen Prozesses zu verbiegen.
"""
from __future__ import annotations

import time

#: Name der Uhr fuer ``time.get_clock_info`` (der Test prueft ihre Aufloesung).
UHR = "perf_counter"


def jetzt() -> float:
    """Zeitstempel eines Taps in Sekunden — nur fuer Abstaende zwischen Taps."""
    return time.perf_counter()

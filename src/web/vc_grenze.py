"""WEB-15: Grenze je Verbindung fuer Aktionen der Handy-Konsole.

Socket.IO laeuft mit ``async_mode='threading'``: jede Nachricht bekommt einen
eigenen Thread, und jede Aktion wartet bis zu ``ZEITLIMIT_S`` auf den
UI-Thread. Ein Geraet mit gueltigem Konsolen-Schluessel (etwa ein
weitergegebener Link) konnte so beliebig viele Threads anstellen und die
Oberflaeche zuschuetten.

Zwei einfache Grenzen je Verbindung:

* **gleichzeitig** laufende Aktionen (Vorgabe 4). Ein Fader-Zug belegt dabei
  hoechstens EINEN Platz: kommt ein neuer Wert, waehrend der vorige noch
  laeuft, wird er gemerkt und danach nachgeholt — nur der neueste, die
  Zwischenstaende braucht niemand (wie die Folgenummern von WEB-09).
* **Rate** als Eimer mit Marken (Vorgabe 200 je Sekunde, Vorrat 400). Ein
  Fader-Zug auf einem 120-Hz-Display und schnelles Tippen bleiben weit
  darunter; eine Flut wird gebremst.

Der Aufrufer nimmt Loslassen, STOP und Blackout AN aus — sie machen nichts an
und muessen immer durchgehen.

Reines Python ohne Qt; wirft nie.
"""
from __future__ import annotations

import threading
import time

ZU_VIELE = "zu_viele"
LOS = "los"
NACHGEHOLT = "nachgeholt"


class _Stand:
    __slots__ = ("laufend", "schluessel", "nachholen", "marken", "zeit")

    def __init__(self, marken: float, zeit: float):
        self.laufend = 0
        self.schluessel: set = set()
        self.nachholen: dict = {}
        self.marken = marken
        self.zeit = zeit


class VerbindungsGrenze:
    def __init__(self, gleichzeitig: int = 4, rate: float = 200.0,
                 vorrat: float = 400.0, uhr=time.monotonic):
        self.gleichzeitig = int(gleichzeitig)
        self.rate = float(rate)
        self.vorrat = float(vorrat)
        self._uhr = uhr
        self._lock = threading.Lock()
        self._je: dict = {}

    def _auffuellen(self, st: _Stand) -> None:
        jetzt = self._uhr()
        st.marken = min(self.vorrat, st.marken + max(0.0, jetzt - st.zeit) * self.rate)
        st.zeit = jetzt

    def herein(self, sid, schluessel=None, nachholbar=None) -> str:
        """Darf die Aktion laufen? ``LOS`` (Platz belegt — danach
        :meth:`fertig` rufen), ``NACHGEHOLT`` (laeuft nach der laufenden
        Aktion mit demselben ``schluessel``) oder ``ZU_VIELE``."""
        with self._lock:
            st = self._je.get(sid)
            if st is None:
                st = self._je[sid] = _Stand(self.vorrat, self._uhr())
            if (schluessel is not None and nachholbar is not None
                    and schluessel in st.schluessel):
                st.nachholen[schluessel] = nachholbar      # neuester Wert gewinnt
                return NACHGEHOLT
            self._auffuellen(st)
            if st.marken < 1.0 or st.laufend >= self.gleichzeitig:
                return ZU_VIELE
            st.marken -= 1.0
            st.laufend += 1
            if schluessel is not None:
                st.schluessel.add(schluessel)
            return LOS

    def fertig(self, sid, schluessel=None):
        """Aktion ist durch. Liefert die nachzuholende Aktion desselben
        ``schluessel`` (der Platz bleibt dann belegt — danach erneut
        ``fertig`` rufen) oder None (Platz frei)."""
        with self._lock:
            st = self._je.get(sid)
            if st is None:
                return None
            if schluessel is not None:
                fn = st.nachholen.pop(schluessel, None)
                if fn is not None:
                    return fn
                st.schluessel.discard(schluessel)
            st.laufend = max(0, st.laufend - 1)
            return None

    def vergessen(self, sid) -> None:
        """Verbindung weg."""
        with self._lock:
            self._je.pop(sid, None)

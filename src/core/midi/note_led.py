"""MIDI-18: Tasten-LEDs eines Pults per Note zurueckmelden (ohne Qt).

Mackie-Control-Pulte (MCU, Behringer X-Touch, iCON …) schalten ihre Tasten-
LEDs nicht selbst: das Programm schickt dieselbe Note wie die Taste, Wert 127
= an, 0 = aus (1 = blinkt, hier nicht benutzt). Dieser Baustein haelt fest,
was zuletzt gesendet wurde, und schickt nur Aenderungen:

* ``abgleichen(wunsch)`` — ``{(kanal, note): an}``; was nicht mehr im Wunsch
  steht (Taste geloescht, andere Seite), geht aus;
* erst senden, DANN merken — ein misslungenes Senden (kein Ausgang offen)
  wird beim naechsten Abgleich wiederholt;
* alle ``AUFFRISCHEN_S`` Sekunden wird alles noch einmal gesendet, damit ein
  aus- und wieder eingestecktes Pult seine LEDs zurueckbekommt.

Die Uhr ist austauschbar (Tests).
"""
from __future__ import annotations

import time

LED_AN = 127
LED_AUS = 0
AUFFRISCHEN_S = 5.0


def note_bytes(kanal: int, note: int, wert: int) -> list[int]:
    """Note-On auf ``kanal`` (1..16)."""
    return [0x90 | ((int(kanal) - 1) & 0x0F), int(note) & 0x7F, int(wert) & 0x7F]


class NoteLedSpiegel:
    def __init__(self, senden, uhr=time.monotonic):
        self._senden = senden            # (bytes) -> bool
        self._uhr = uhr
        self._stand: dict[tuple[int, int], int] = {}
        self._zuletzt_voll = uhr()

    @property
    def stand(self) -> dict[tuple[int, int], int]:
        return dict(self._stand)

    def abgleichen(self, wunsch: dict) -> int:
        """Gewuenschte LEDs herstellen. Rueckgabe: Zahl der gesendeten Noten."""
        jetzt = self._uhr()
        voll = jetzt - self._zuletzt_voll >= AUFFRISCHEN_S
        if voll:
            self._zuletzt_voll = jetzt   # alles einmal neu senden
        ziel = {k: (LED_AN if an else LED_AUS) for k, an in wunsch.items()}
        # Was nicht mehr gewuenscht ist und an war, geht aus.
        for k, wert in self._stand.items():
            if k not in ziel and wert != LED_AUS:
                ziel[k] = LED_AUS
        gesendet = 0
        for k, wert in ziel.items():
            if not voll and self._stand.get(k) == wert:
                continue
            if not self._senden_sicher(note_bytes(k[0], k[1], wert)):
                continue                 # beim naechsten Abgleich erneut
            gesendet += 1
            if k in wunsch:
                self._stand[k] = wert
            else:
                self._stand.pop(k, None)  # aus und nicht mehr gewuenscht
        return gesendet

    def alle_aus(self) -> int:
        """Alles, was dieser Spiegel angeschaltet hat, ausschalten."""
        return self.abgleichen({})

    def _senden_sicher(self, msg) -> bool:
        try:
            return bool(self._senden(msg))
        except Exception:
            return False

"""MIDI-17: Motor eines einzelnen Faders nachfuehren (VC-Fader).

Die MIDI-Ansicht fuehrt Motorfader schon nach (MIDI-14/15, ``midi_mapper``),
aber nur fuer Mappings an Executor-Fader und Grand Master. Ein VC-Fader hat
keinen Mapping-Eintrag — er bindet den Pult-Fader selbst. Diese Klasse ist
derselbe Ablauf fuer genau einen Fader, ohne Qt und mit eigener Uhr, damit
sie sich ohne Pult pruefen laesst. Die Regeln und Zeiten sind die aus
``midi_mapper``:

* **Hand vor Motor.** Kommt vom Fader eine Eingabe, geht ``MOTOR_HAND_RUHE_S``
  lang nichts an den Motor; der Auftrag wird gemerkt und danach nachgetragen
  (Mackie-Pulte fahren nach dem Loslassen auf den zuletzt GESENDETEN Wert —
  ohne Nachtrag spraenge der Fader zurueck).
* **Echo ist keine Eingabe.** Was kurz nach einer eigenen Sendung zurueckkommt,
  ist der Bericht der Motorfahrt (``MOTOR_ECHO_FENSTER_S``, mit Nachlauf
  ``MOTOR_NACHLAUF_S`` / ``MOTOR_ECHO_TOLERANZ``).
* **Touch-Sperre.** Solange der Beruehrungssensor meldet, nichts senden;
  Loslassen traegt sofort nach. Ein verlorenes Loslassen loest die Sperre
  nach ``MOTOR_BERUEHRT_MAX_S``.

Werte sind 14 Bit (0..16383), wie sie das Pult als Pitchbend sendet.
"""
from __future__ import annotations

import time
from typing import Callable

from src.core.midi.midi_mapper import (
    MOTOR_BERUEHRT_MAX_S, MOTOR_ECHO_FENSTER_S, MOTOR_ECHO_TOLERANZ,
    MOTOR_HAND_RUHE_S, MOTOR_NACHLAUF_S, MOTOR_SCHRITT,
)

VOLL = 16383


class MotorFader:
    """Zustand der Motor-Nachfuehrung eines Faders.

    ``senden(wert14)`` schickt den Wert ans Pult und gibt ``True`` zurueck,
    wenn das geklappt hat. ``uhr`` liefert Sekunden (monoton)."""

    def __init__(self, senden: Callable[[int], bool],
                 uhr: Callable[[], float] = time.monotonic):
        self._senden = senden
        self._uhr = uhr
        self.vergessen()

    def vergessen(self, sensor: bool = False) -> None:
        """Laufzustand zuruecksetzen (Show geladen, Bank verlassen). Ob der
        Fader einen Beruehrungssensor hat, bleibt — ausser ``sensor=True``
        (anderer Pult-Fader gebunden)."""
        if sensor or not hasattr(self, "_sensor"):
            self._sensor = False      # der Fader hat einen Beruehrungssensor
        self._hand_ts = float("-inf")
        self._send_ts = float("-inf")
        self._gesendet: int | None = None
        self._offen: int | None = None
        self._beruehrt = False
        self._beruehrt_ts = float("-inf")

    # ── Eingang vom Pult ──────────────────────────────────────────────────────

    def eingang(self, wert14: int) -> bool:
        """Pitchbend vom Fader einordnen. ``True`` = Bericht einer eigenen
        Motorfahrt, nicht ausfuehren. Sonst merkt sich die Klasse die Hand."""
        jetzt = self._uhr()
        if self._beruehrt:
            self._hand_ts = jetzt
            self._beruehrt_ts = jetzt
            return False
        seit = jetzt - self._send_ts
        if seit < MOTOR_ECHO_FENSTER_S:
            return True
        if seit < MOTOR_NACHLAUF_S:
            if self._sensor:
                return True             # ohne Beruehrung keine Hand
            if (self._hand_ts <= self._send_ts and self._gesendet is not None
                    and abs(wert14 - self._gesendet) / VOLL <= MOTOR_ECHO_TOLERANZ):
                return True             # der Motor schwingt noch ein
        self._hand_ts = jetzt
        return False

    def beruehrung(self, beruehrt: bool) -> bool:
        """Beruehrungssensor. Loslassen traegt sofort nach; ``True`` = dabei
        gesendet."""
        jetzt = self._uhr()
        if beruehrt:
            self._beruehrt = True
            self._beruehrt_ts = jetzt
            self._sensor = True
            return False
        return self._losgelassen(jetzt)

    def _losgelassen(self, jetzt: float) -> bool:
        if not self._beruehrt:
            return False
        self._beruehrt = False
        self._hand_ts = float("-inf")   # der Sensor weiss es genau: keine Wartezeit
        offen = self._offen
        if offen is None:
            return False
        self._gesendet = None           # auch wenn der Wert gleich ist
        return self._schicken(offen, jetzt)

    # ── Ausgang zum Motor ─────────────────────────────────────────────────────

    def melden(self, wert14: int, erzwingen: bool = False) -> bool:
        """Den Motor auf ``wert14`` fahren — oder den Auftrag merken, solange
        die Hand am Fader ist. ``erzwingen`` sendet auch einen unveraenderten
        Wert (z. B. nach einem Bankwechsel). ``True`` = gesendet."""
        wert14 = max(0, min(VOLL, int(wert14)))
        jetzt = self._uhr()
        self._sperre_pruefen(jetzt)
        if self._beruehrt or (jetzt - self._hand_ts) < MOTOR_HAND_RUHE_S:
            self._offen = wert14
            return False
        if (not erzwingen and self._gesendet is not None
                and self._hand_ts <= self._send_ts
                and abs(wert14 - self._gesendet) / VOLL < MOTOR_SCHRITT):
            self._offen = None
            return False
        return self._schicken(wert14, jetzt, erzwingen=erzwingen)

    def nachtrag(self) -> bool:
        """Gemerkten Auftrag senden, sobald die Hand lange genug ruht."""
        jetzt = self._uhr()
        self._sperre_pruefen(jetzt)
        if self._offen is None or self._beruehrt:
            return False
        if (jetzt - self._hand_ts) < MOTOR_HAND_RUHE_S:
            return False
        return self._schicken(self._offen, jetzt)

    @property
    def wartet(self) -> bool:
        """Liegt ein Auftrag bereit, der spaeter nachgetragen werden muss?"""
        return self._offen is not None

    def _sperre_pruefen(self, jetzt: float) -> None:
        if self._beruehrt and jetzt - self._beruehrt_ts >= MOTOR_BERUEHRT_MAX_S:
            self._beruehrt = False
            self._hand_ts = float("-inf")
            self._gesendet = None

    def _schicken(self, wert14: int, jetzt: float, erzwingen: bool = False) -> bool:
        if (not erzwingen and self._gesendet == wert14
                and self._hand_ts <= self._send_ts):
            self._offen = None
            return False                # steht schon dort, niemand hat ihn bewegt
        # VOR dem Senden merken: was gleich zurueckkommt, gilt schon als Echo.
        alt = (self._gesendet, self._send_ts)
        self._gesendet = wert14
        self._send_ts = jetzt
        self._offen = None
        try:
            ok = bool(self._senden(wert14))
        except Exception:
            ok = False
        if not ok:
            # nichts ist angekommen (kein Ausgang offen): nicht als gesendet
            # merken, sonst schluckt die Doppel-Sperre den Wert spaeter.
            self._gesendet, self._send_ts = alt
        return ok

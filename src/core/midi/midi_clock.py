"""MIDI-7: MIDI-Clock (0xF8) eines Pults/einer DAW als BPM-Quelle.

MIDI-Clock sendet 24 Ticks je Viertelnote (24 PPQN). Aus den Abstaenden der
Ticks ergibt sich das Tempo: ``BPM = 60 / (24 * Tick-Abstand)``.

**Glaettung:** gemessen wird ueber ein gleitendes Fenster der letzten
``FENSTER`` Ticks (zwei Viertel): ``(t_letzter - t_erster) / Anzahl Abstaende``.
Ein einzelner verspaeteter Tick verschiebt so nur die Enden des Fensters, nicht
jede Messung (Zeitstempel kommen aus der gemeinsamen MIDI-Empfangsschleife,
nicht vom Treiber). Gemeldet wird hoechstens einmal je Viertel (alle 24 Ticks)
und nur, wenn sich der auf ``AUFLOESUNG`` gerundete Wert aendert.

**Transport:** Start (0xFA) und Continue (0xFB) beginnen die Messung neu (das
Pult setzt dort neu an), Stop (0xFC) verwirft das Fenster. Der zuletzt
gemeldete Takt bleibt nach Stop stehen — ein angehaltenes Pult heisst nicht
„Tempo 0" (dafuer gibt es die Quelle „Aus", BPM-33). Viele Pulte senden die
Clock auch im Stand weiter; solche Ticks zaehlen fuer das Tempo mit.
Eine Luecke ueber ``LUECKE_S`` (Kabel gezogen, Pult neu gestartet) beginnt die
Messung ebenfalls neu, statt einen viel zu langsamen Takt zu melden.

**Ein Port:** senden zwei Eingaenge Clock (Pult und DAW, Geraet plus
Durchleitung), mischten sich ihre Ticks zu doppeltem Tempo. Gezaehlt wird daher
nur der Port, von dem der erste Tick kam; ein anderer uebernimmt erst nach einer
Luecke ueber ``LUECKE_S`` (der bisherige schweigt) oder nach Stop.

Gemeldet wird ueber ``BPMManager.request_bpm(bpm, "midi_clock")`` — dieselbe
Praezedenz wie OS2L (Manuell/Lock blocken). Aktiv ist die Quelle nur, wenn der
BPM-Quellen-Umschalter (``bpm_source_controller``) „MIDI-Clock" gewaehlt hat;
er ruft ``aktivieren``/``deaktivieren``.

Empfang: beide Plattform-Pfade (python-rtmidi, WinMM per ctypes) liefern in
die gemeinsame Empfangsschleife des ``MidiManager``; die Clock-Bytes kommen
dort ueber ``subscribe_echtzeit`` an (nicht ueber die Mapping-Abonnenten).
"""
from __future__ import annotations

import threading
from collections import deque

from .midi_manager import CLOCK_CONTINUE, CLOCK_START, CLOCK_STOP, CLOCK_TICK

PPQN = 24
FENSTER = 48          # Ticks im Messfenster (2 Viertel)
MIN_ABSTAENDE = 24    # erst nach einem vollen Viertel melden
LUECKE_S = 0.5        # Tick-Abstand > 0,5 s (< 5 BPM) = Neuanfang
AUFLOESUNG = 0.1      # gemeldete BPM auf 0,1 gerundet
QUELLE = "midi_clock"


class MidiClock:
    """Misst das Tempo aus MIDI-Clock-Ticks und meldet es dem BPM-Manager."""

    def __init__(self, mgr=None):
        self._mgr = mgr
        self._lock = threading.Lock()
        self._zeiten: deque[float] = deque(maxlen=FENSTER + 1)
        self._seit_meldung = 0
        self._gemeldet: float | None = None
        self.laeuft = False            # Transport (Start/Continue … Stop)
        self._manager = None           # MidiManager, an dem wir haengen
        self._port: str | None = None  # Port, dessen Ticks gezaehlt werden
        self._port_zeit: float | None = None   # letzter Tick dieses Ports

    # ── An-/Abmelden (vom Quellen-Umschalter) ───────────────────────────────
    @property
    def aktiv(self) -> bool:
        return self._manager is not None

    def aktivieren(self, midi_manager=None) -> None:
        if self._manager is not None:
            return
        if midi_manager is None:
            from .midi_manager import get_midi_manager
            midi_manager = get_midi_manager()
        midi_manager.subscribe_echtzeit(self._on_echtzeit)
        self._manager = midi_manager
        self._neu_messen()

    def deaktivieren(self) -> None:
        mm, self._manager = self._manager, None
        if mm is not None:
            try:
                mm.unsubscribe_echtzeit(self._on_echtzeit)
            except Exception:
                pass
        self._neu_messen()

    # ── Empfang ─────────────────────────────────────────────────────────────
    def _on_echtzeit(self, raw, port_name, zeit) -> None:
        if not raw:
            return
        if not self._port_passt(raw[0], port_name, zeit):
            return
        self.einspeisen(raw[0], zeit)

    def _port_passt(self, status: int, port_name, zeit: float) -> bool:
        """Nur EIN Port zaehlt (s. Modulkopf). Stop gibt den Port frei."""
        with self._lock:
            frei = (self._port is None
                    or (self._port_zeit is not None and zeit - self._port_zeit > LUECKE_S))
            if not frei and port_name != self._port:
                return False
            if status == CLOCK_STOP:
                self._port = self._port_zeit = None
                return True
            self._port, self._port_zeit = port_name, float(zeit)
            return True

    def einspeisen(self, status: int, zeit: float) -> float | None:
        """Eine Clock-/Transport-Nachricht verarbeiten. Liefert die gemeldete
        BPM, wenn diese Nachricht eine Meldung ausgeloest hat, sonst None."""
        if status == CLOCK_START or status == CLOCK_CONTINUE:
            self.laeuft = True
            self._neu_messen()
            return None
        if status == CLOCK_STOP:
            self.laeuft = False
            self._neu_messen()
            return None
        if status != CLOCK_TICK:
            return None
        with self._lock:
            if self._zeiten and zeit - self._zeiten[-1] > LUECKE_S:
                self._zeiten.clear()
                self._seit_meldung = 0
            self._zeiten.append(float(zeit))
            self._seit_meldung += 1
            abstaende = len(self._zeiten) - 1
            if abstaende < MIN_ABSTAENDE or self._seit_meldung < PPQN:
                return None
            self._seit_meldung = 0
            dauer = self._zeiten[-1] - self._zeiten[0]
            if dauer <= 0:
                return None
            bpm = 60.0 * abstaende / (PPQN * dauer)
            bpm = round(round(bpm / AUFLOESUNG) * AUFLOESUNG, 1)
            if self._gemeldet is not None and abs(bpm - self._gemeldet) < AUFLOESUNG / 2:
                return None
            self._gemeldet = bpm
        self._melden(bpm)
        return bpm

    def bpm(self) -> float | None:
        """Zuletzt gemeldetes Tempo (None = noch keines)."""
        return self._gemeldet

    def _neu_messen(self) -> None:
        with self._lock:
            self._port = self._port_zeit = None
            self._zeiten.clear()
            self._seit_meldung = 0
            self._gemeldet = None

    def _melden(self, bpm: float) -> None:
        try:
            mgr = self._mgr
            if mgr is None:
                from src.core.engine.bpm_manager import get_bpm_manager
                mgr = get_bpm_manager()
            mgr.request_bpm(bpm, QUELLE)
        except Exception as e:
            from src.core.diagnose_log import melde_still
            melde_still("midi.clock", e)


_clock: MidiClock | None = None
_clock_lock = threading.Lock()


def get_midi_clock() -> MidiClock:
    global _clock
    if _clock is None:
        with _clock_lock:
            if _clock is None:
                _clock = MidiClock()
    return _clock

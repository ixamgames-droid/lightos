"""APC Mini LED Feedback — sendet LED-Zustaende an den APC Mini Output.

Das APC Mini (original) empfaengt Note-On-Nachrichten auf Channel 1
zur LED-Steuerung. Velocity-Werte:
  0 = aus
  1 = gruen (solid)
  2 = gruen (blink)
  3 = rot (solid)
  4 = rot (blink)
  5 = gelb/amber (solid)
  6 = gelb/amber (blink)
"""
from __future__ import annotations

try:
    import rtmidi as _rtmidi
    _RTMIDI = True
except ImportError:
    _RTMIDI = False

LED_OFF          = 0
LED_GREEN        = 1
LED_GREEN_BLINK  = 2
LED_RED          = 3
LED_RED_BLINK    = 4
LED_YELLOW       = 5
LED_YELLOW_BLINK = 6

_instance: "APCMiniFeedback | None" = None


def get_apc_feedback() -> "APCMiniFeedback | None":
    return _instance


class APCMiniFeedback:
    """Oeffnet den APC Mini MIDI Output und aktualisiert LEDs per QTimer.

    Verwendung:
        fb = APCMiniFeedback()
        fb.attach(app_state)   # startet Polling (Hauptthread)
        # ...
        fb.close()
    """

    # Note-Nummern gemaess APC Mini MIDI Implementation Guide
    GRID_ROW0  = list(range(0, 8))    # unterste Reihe (GO-Buttons)
    GRID_ROW1  = list(range(8, 16))   # 2. Reihe (Flash-Buttons)
    TRACK_BTNS = list(range(64, 72))  # Track-Buttons unten (BACK)
    SIDE_BTNS  = list(range(82, 90))  # Seiten-Buttons rechts (Page)

    def __init__(self, port_hint: str = "APC"):
        global _instance
        _instance = self
        self._hint = port_hint
        self._out: object | None = None
        self._state = None
        self._timer = None
        self._cache: dict[int, int] = {}
        self._open()

    # ── Port oeffnen ─────────────────────────────────────────────────────────

    def _open(self) -> bool:
        if _RTMIDI:
            try:
                m = _rtmidi.MidiOut()
                ports = [m.get_port_name(i) for i in range(m.get_port_count())]
                idx = next((i for i, p in enumerate(ports)
                            if self._hint.lower() in p.lower()), None)
                if idx is None:
                    del m
                    print(f"[APCMiniFeedback] Kein Output-Port mit '{self._hint}' gefunden.")
                    return False
                m.open_port(idx)
                self._out = m
                print(f"[APCMiniFeedback] Output geoeffnet: {ports[idx]}")
                return True
            except Exception as e:
                print(f"[APCMiniFeedback] Fehler beim Öffnen: {e}")
                return False
        # WinMM-Fallback (kein Compiler noetig, laeuft nativ auf ARM64)
        try:
            from .midi_backend_winmm import WINMM_OK, list_outputs as _wm_out, WinMMOutput as _WMOut
            if not WINMM_OK:
                print("[APCMiniFeedback] Weder rtmidi noch WinMM verfügbar.")
                return False
            ports = _wm_out()
            idx = next((i for i, p in enumerate(ports)
                        if self._hint.lower() in p.lower()), None)
            if idx is None:
                print(f"[APCMiniFeedback] Kein WinMM-Output mit '{self._hint}' gefunden. Ports: {ports}")
                return False
            self._out = _WMOut(idx)
            print(f"[APCMiniFeedback] WinMM Output geoeffnet: {ports[idx]}")
            return True
        except Exception as e:
            print(f"[APCMiniFeedback] WinMM Fehler: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._out is not None

    # ── Attach / Detach ──────────────────────────────────────────────────────

    def attach(self, app_state, interval_ms: int = 150):
        """Startet LED-Polling (muss im Qt-Hauptthread aufgerufen werden)."""
        from PySide6.QtCore import QTimer
        self._state = app_state
        if self._out is None:
            print("[APCMiniFeedback] Kein Output-Port — LEDs deaktiviert.")
            return
        self.clear_all()
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._update)
        self._timer.start()
        print("[APCMiniFeedback] LED-Feedback gestartet.")

    def detach(self):
        if self._timer:
            self._timer.stop()
            self._timer = None

    def close(self):
        global _instance
        self.detach()
        if self._out:
            try:
                self.clear_all()
            except Exception:
                pass
            try:
                self._out.close_port()
            except Exception:
                pass
            self._out = None
        if _instance is self:
            _instance = None
        print("[APCMiniFeedback] Geschlossen.")

    # ── LED senden ───────────────────────────────────────────────────────────

    def set_led(self, note: int, velocity: int):
        """Setzt eine LED direkt (Diff-Update: sendet nur bei Aenderung)."""
        if self._cache.get(note) == velocity:
            return
        self._cache[note] = velocity
        if self._out:
            try:
                self._out.send_message([0x90, note & 0x7F, velocity & 0x7F])
            except Exception:
                pass

    def clear_all(self):
        """Alle relevanten APC-Mini-LEDs ausschalten."""
        for note in (*self.GRID_ROW0, *self.GRID_ROW1,
                     *self.TRACK_BTNS, *self.SIDE_BTNS):
            self.set_led(note, LED_OFF)

    # ── Update-Loop (QTimer) ─────────────────────────────────────────────────

    def _update(self):
        if self._out is None or self._state is None:
            return
        try:
            pe = self._state.playback_engine
            if pe is None:
                return
            execs = pe.executors      # aktuelle Page
            page  = pe.current_page  # 0-basiert

            for i in range(8):
                ex = execs[i] if i < len(execs) else None

                note_go    = self.GRID_ROW0[i]
                note_flash = self.GRID_ROW1[i]
                note_back  = self.TRACK_BTNS[i]

                if ex is None:
                    self.set_led(note_go,    LED_OFF)
                    self.set_led(note_flash, LED_OFF)
                    self.set_led(note_back,  LED_OFF)
                    continue

                # Flash-Reihe: rot wenn Flash gehalten
                self.set_led(note_flash,
                             LED_RED if ex._flash_active else LED_OFF)

                # GO-Reihe: gruen wenn Stack aktiv und Output hat
                if ex.stack is not None and ex.get_output():
                    self.set_led(note_go, LED_GREEN)
                elif ex.stack is not None:
                    self.set_led(note_go, LED_GREEN_BLINK)
                else:
                    self.set_led(note_go, LED_OFF)

                # BACK-Reihe: gedimmtes Gruen wenn Stack geladen
                self.set_led(note_back,
                             LED_GREEN if ex.stack else LED_OFF)

            # Seiten-Buttons: aktive Seite gelb
            for i in range(8):
                note = self.SIDE_BTNS[i]
                self.set_led(note,
                             LED_YELLOW if i == page else LED_OFF)

        except Exception as e:
            print(f"[APCMiniFeedback] Update-Fehler: {e}")

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
        # Beim geteilten MidiManager-Ausgang: Port, auf den gebunden wurde.
        # Vor jedem Senden pruefen, sonst gehen LED-Noten an ein fremdes Geraet.
        self._out_name: str | None = None
        self._state = None
        self._timer = None
        self._cache: dict[int, int] = {}
        self._open()

    # ── Port oeffnen ─────────────────────────────────────────────────────────

    def _open(self) -> bool:
        if _RTMIDI:
            try:
                from .midi_manager import get_midi_manager
                m = get_midi_manager()
                ports = m.list_outputs()
                idx = next((i for i, p in enumerate(ports)
                            if self._hint.lower() in p.lower()), None)
                if idx is None:
                    print(f"[APCMiniFeedback] Kein Output-Port mit '{self._hint}' gefunden.")
                    return False
                want = ports[idx]
                # Den GETEILTEN Ausgang nur uebernehmen, wenn er frei ist oder
                # ohnehin schon auf den APC zeigt — er gehoert der MIDI-Ansicht
                # bzw. dem Mapping-Feedback. Ist er belegt, bleibt er
                # unangetastet; gesendet wird trotzdem, portadressiert.
                current = ""
                try:
                    current = str(m.current_output_name() or "")
                except Exception:
                    current = ""
                frei = (not current or current == want
                        or self._hint.lower() in current.lower())
                self._out = m
                if frei and m.open_output(want):
                    self._out_name = str(m.current_output_name() or want)
                    print(f"[APCMiniFeedback] Output geoeffnet: {self._out_name}")
                else:
                    # Kein Grund aufzugeben: send_message_to adressiert den APC
                    # direkt. Frueher blieben die LEDs hier einfach dunkel.
                    self._out_name = want
                    print(f"[APCMiniFeedback] MIDI-Ausgang '{current}' ist belegt — "
                          f"LED-Feedback laeuft portadressiert an '{want}'.")
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
            # Den GETEILTEN MidiManager-Port nicht aus einem einzelnen
            # LED-Feedback-Widget heraus schliessen — der gehoert dem Manager.
            # Einen EIGENEN Handle (WinMM-Fallback ohne python-rtmidi, u. a. auf
            # ARM-Windows) aber sehr wohl: sonst bleibt der midiOut-Handle bis
            # zum Prozessende offen und das Geraet belegt.
            if self._out_name is None:
                try:
                    self._out.close_port()
                except Exception:
                    pass
            else:
                # Einen fuer uns geoeffneten Zweit-Ausgang freigeben. Zeigt der
                # Haupt-Ausgang selbst auf den APC, gibt es keinen — dann ist
                # das ein No-Op und ruehrt den geteilten Port nicht an.
                try:
                    self._out.close_aux_output(self._out_name)
                except Exception:
                    pass
            self._out = None
        self._out_name = None
        if _instance is self:
            _instance = None
        print("[APCMiniFeedback] Geschlossen.")

    # ── LED senden ───────────────────────────────────────────────────────────

    def set_led(self, note: int, velocity: int):
        """Setzt eine LED direkt (Diff-Update: sendet nur bei Aenderung)."""
        if self._cache.get(note) == velocity:
            return
        # ★ Erst senden, DANN merken. Andersherum vergiftet ein misslungener
        # Sendeversuch den Diff-Cache: er behauptet, die LED stehe schon auf
        # dem Wunschwert, und genau derselbe Wunsch wird nie wiederholt — die
        # LED bleibt dauerhaft falsch statt nur voruebergehend.
        if self._send([0x90, note & 0x7F, velocity & 0x7F]):
            self._cache[note] = velocity

    def _send(self, msg) -> bool:
        """Portadressiert an UNSEREN APC senden.

        ★ MIDI-LED-AUX. Frueher ging die Note ueber den GETEILTEN Ausgang, und
        damit sie nicht auf einem fremden Geraet klimperte, sendete der Treiber
        nur, solange dieser Ausgang noch auf den APC zeigte. Wer in der
        MIDI-Ansicht etwas anderes waehlte, verlor das LED-Feedback still.

        ``send_message_to`` nennt den Ziel-Port beim Namen: die Note kann das
        fremde Geraet gar nicht erreichen, unabhaengig davon, was die Ansicht
        gerade anzeigt. Der Manager benutzt dabei den Haupt-Ausgang, wenn der
        ohnehin dorthin zeigt, und sonst einen gehaltenen Zweit-Handle.
        """
        if self._out is None:
            return False
        try:
            if self._out_name is not None:
                return bool(self._out.send_message_to(self._out_name, msg))
            # Eigener WinMM-Handle (ARM-Windows ohne python-rtmidi): der zeigt
            # per Konstruktion auf den APC, da gibt es nichts zu adressieren.
            self._out.send_message(msg)
            return True
        except Exception:
            return False

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

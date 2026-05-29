"""APC mini mk2 RGB-LED-Feedback.

Anders als das Original-APC mini (apc_mini_feedback.py, Velocity 0-6 = grün/rot/gelb)
nutzt das mk2 ein RGB-Protokoll:
    Note-On  0x9{n}   n = MIDI-Kanal 0..15 = Helligkeit/Modus
    velocity = Farbindex 0..127 aus fester Palette

Kanal-Modi (0x90 + n):
    0x90 = 10%, 0x91 = 25%, 0x92 = 50%, 0x93 = 65%,
    0x94 = 75%, 0x95 = 90%, 0x96 = 100% (solid),
    0x97..0x9A = Pulsing, 0x9B..0x9F = Blinking

Dieses Modul spiegelt den Zustand der VC-Buttons (geteachte MIDI-Note) auf die
8x8-Pads: belegt = gedimmtes Blau, aktiv = Grün, gerade gedrueckt = Rot.
"""
from __future__ import annotations

try:
    import rtmidi as _rtmidi
    _RTMIDI = True
except ImportError:
    _RTMIDI = False

# ── Helligkeits-/Modus-Kanaele (Status-Byte) ──────────────────────────────────
DIM   = 0x90   # 10 %
MID   = 0x92   # 50 %
FULL  = 0x96   # 100 % solid
PULSE = 0x98   # pulsierend
BLINK = 0x9C   # blinkend

# ── Farbpalette (Velocity-Index, empirisch am Geraet verifiziert) ─────────────
OFF     = 0
WHITE   = 3
RED     = 5
ORANGE  = 9
YELLOW  = 13
GREEN   = 21
CYAN    = 37
AZURE   = 41
BLUE    = 45
VIOLET  = 53
MAGENTA = 57

PAD_MIN, PAD_MAX = 0, 63   # 8x8-Grid


class ApcMk2Feedback:
    """Spiegelt VC-Button-Zustaende als RGB auf die APC-mini-mk2-Pads.

    Schnittstelle bewusst kompatibel zu APCMiniFeedback:
        is_connected, attach(state=None), close()
    """

    def __init__(self, canvas, port_hint: str = "APC"):
        self._canvas = canvas
        self._hint = port_hint
        self._out = None
        self._timer = None
        self._cache: dict[int, tuple[int, int]] = {}   # note -> (mode, color)
        # Standard-Farbschema (spaeter pro Button konfigurierbar)
        self.color_bound  = (DIM,  BLUE)     # belegt, inaktiv
        self.color_active = (FULL, GREEN)    # Toggle/Funktion aktiv
        self.color_press  = (FULL, RED)      # gerade gedrueckt
        self._open()

    # ── Port oeffnen ──────────────────────────────────────────────────────────

    def _pick_port(self, ports: list[str]) -> int | None:
        # Bevorzugt den primaeren APC-Port (nicht den sekundaeren MIDIOUT2-Port)
        idx = next((i for i, p in enumerate(ports)
                    if self._hint.lower() in p.lower() and "midiout2" not in p.lower()), None)
        if idx is None:
            idx = next((i for i, p in enumerate(ports)
                        if self._hint.lower() in p.lower()), None)
        return idx

    def _open(self) -> bool:
        if _RTMIDI:
            try:
                m = _rtmidi.MidiOut()
                ports = [m.get_port_name(i) for i in range(m.get_port_count())]
                idx = self._pick_port(ports)
                if idx is None:
                    del m
                    return False
                m.open_port(idx)
                self._out = m
                print(f"[ApcMk2] Output geoeffnet: {ports[idx]}")
                return True
            except Exception as e:
                print(f"[ApcMk2] rtmidi Fehler: {e}")
                return False
        try:
            from .midi_backend_winmm import WINMM_OK, list_outputs as _wm_out, WinMMOutput as _WMOut
            if not WINMM_OK:
                return False
            ports = _wm_out()
            idx = self._pick_port(ports)
            if idx is None:
                print(f"[ApcMk2] Kein APC-Output gefunden. Ports: {ports}")
                return False
            self._out = _WMOut(idx)
            print(f"[ApcMk2] WinMM Output geoeffnet: {ports[idx]}")
            return True
        except Exception as e:
            print(f"[ApcMk2] WinMM Fehler: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._out is not None

    # ── LED senden (Diff-Update) ───────────────────────────────────────────────

    def set_pad(self, note: int, color: int, mode: int = FULL):
        if not (PAD_MIN <= note <= PAD_MAX):
            return
        key = note
        val = (mode, color)
        if self._cache.get(key) == val:
            return
        self._cache[key] = val
        if self._out:
            try:
                self._out.send_message([mode, note & 0x7F, color & 0x7F])
            except Exception:
                pass

    def clear_all(self):
        for n in range(64):
            self.set_pad(n, OFF, FULL)

    # ── Lifecycle (kompatibel zu APCMiniFeedback) ──────────────────────────────

    def attach(self, state=None, interval_ms: int = 120):
        from PySide6.QtCore import QTimer
        if self._out is None:
            return
        self.clear_all()
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._update)
        self._timer.start()
        print("[ApcMk2] LED-Feedback gestartet.")

    def close(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
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
        print("[ApcMk2] Geschlossen.")

    # ── Update-Loop (UI-Thread via QTimer) ─────────────────────────────────────

    def _update(self):
        if self._out is None or self._canvas is None:
            return
        try:
            desired = self._collect_desired()
            for n in range(64):
                mode, color = desired.get(n, (FULL, OFF))
                self.set_pad(n, color, mode)
        except Exception as e:
            print(f"[ApcMk2] Update-Fehler: {e}")

    def _collect_desired(self) -> dict[int, tuple[int, int]]:
        """Ermittelt pro Pad-Note (0-63) den gewuenschten (mode, color)."""
        from src.ui.virtualconsole.vc_button import VCButton
        desired: dict[int, tuple[int, int]] = {}
        for w in self._canvas.findChildren(VCButton):
            note = getattr(w, "midi_data1", -1)
            if note is None or not (PAD_MIN <= note <= PAD_MAX):
                continue
            if getattr(w, "midi_type", "note_on") != "note_on":
                continue
            desired[note] = self._led_for_button(w)
        return desired

    def _led_for_button(self, w) -> tuple[int, int]:
        if getattr(w, "_pressed", False):
            return self.color_press
        if self._is_active(w):
            return self.color_active
        return self.color_bound

    def _is_active(self, w) -> bool:
        from src.ui.virtualconsole.vc_button import ButtonAction
        from src.core.app_state import get_state
        try:
            st = get_state()
            fid = getattr(w, "function_id", None)
            if fid is None:
                return False
            fid = int(fid)
            if w.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
                return bool(st.function_manager.is_running(fid))
            if w.action in (ButtonAction.TOGGLE, ButtonAction.FLASH):
                execs = st.playback_engine.executors if st.playback_engine else []
                if 0 <= fid < len(execs):
                    return bool(execs[fid].get_output())
        except Exception:
            pass
        return False

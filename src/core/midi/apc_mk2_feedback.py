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

# Repraesentative RGB-Werte der bekannten Paletten-Indizes — fuer das
# Faerben von VCColor-Pads in ihrer tatsaechlichen Farbe (nearest match).
_PALETTE_RGB: list[tuple[int, tuple[int, int, int]]] = [
    (OFF,     (0, 0, 0)),
    (WHITE,   (255, 255, 255)),
    (RED,     (255, 0, 0)),
    (ORANGE,  (255, 128, 0)),
    (YELLOW,  (255, 255, 0)),
    (GREEN,   (0, 255, 0)),
    (CYAN,    (0, 255, 255)),
    (AZURE,   (0, 128, 255)),
    (BLUE,    (0, 0, 255)),
    (VIOLET,  (128, 0, 255)),
    (MAGENTA, (255, 0, 255)),
]


def rgb_to_mk2_index(r: int, g: int, b: int) -> int:
    """Findet den naechstliegenden mk2-Paletten-Index zu einem RGB-Wert."""
    best_idx, best_dist = WHITE, None
    for idx, (pr, pg, pb) in _PALETTE_RGB:
        if idx == OFF and (r or g or b):
            continue  # Schwarz nur fuer echtes (0,0,0)
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_dist is None or d < best_dist:
            best_dist, best_idx = d, idx
    return best_idx


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
        # Animationen: Ripple-Wellen, die beim Ausloesen ueber die Pads laufen
        self._ripples: list[dict] = []          # {note, rgb, t0}
        self._prev_active: set[int] = set()     # aktive Notes im letzten Frame
        self._active_notes: set[int] = set()
        self._note_rgb: dict[int, tuple] = {}   # note -> (r,g,b) fuer Ripple-Farbe
        self._note_style: dict[int, str] = {}   # note -> pad_style
        self._wave_last: dict[int, float] = {}  # note -> letzte Dauer-Welle (Zeit)
        self.ripple_enabled = True
        # Beat: TAP-Pad blinkt im BPM-Takt
        self._bm = None
        self._last_beat_time: float = 0.0
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

    def attach(self, state=None, interval_ms: int = 70):
        from PySide6.QtCore import QTimer
        if self._out is None:
            return
        self._cache.clear()      # frischer Start -> keine stale LEDs nach Reconnect
        self.clear_all()
        # BPM-Beats abonnieren, damit das TAP-Pad im Takt blinkt.
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            self._bm = get_bpm_manager()
            self._bm.subscribe_beat(self._on_bpm_beat)
        except Exception as e:
            print(f"[ApcMk2] BPM subscribe error: {e}")
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._update)
        self._timer.start()
        print("[ApcMk2] LED-Feedback gestartet.")

    def _on_bpm_beat(self, idx: int):
        """BPM-Beat (Background-Thread) — nur Zeitstempel merken (thread-arm)."""
        import time
        self._last_beat_time = time.monotonic()

    def close(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        if self._bm is not None:
            try:
                self._bm.unsubscribe_beat(self._on_bpm_beat)
            except Exception:
                pass
            self._bm = None
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
        import time
        try:
            now = time.monotonic()
            desired = self._collect_desired(now)
            if self.ripple_enabled:
                # Welle nur fuer Pads mit Stil 'wave' (Farb-Kacheln gelten als
                # 'wave', s. _collect_desired). Effekt-/Funktions-Buttons wellen
                # NICHT mehr bei jedem Druck — David-Wunsch: Wave nur bei Farben,
                # nicht beim Umschalten von Effekten.
                for note in (self._active_notes - self._prev_active):
                    if self._note_style.get(note) != "wave":
                        continue
                    self._ripples.append({"note": note, "t0": now,
                                          "rgb": self._note_rgb.get(note, (255, 255, 255))})
                # Pad-Stil 'wave': dauerhaft Wellen nachschieben, solange aktiv.
                for note in self._active_notes:
                    if self._note_style.get(note) == "wave" and \
                            now - self._wave_last.get(note, 0.0) > 0.55:
                        self._wave_last[note] = now
                        self._ripples.append({"note": note, "t0": now,
                                              "rgb": self._note_rgb.get(note, (255, 255, 255))})
                self._prev_active = set(self._active_notes)
                self._apply_ripples(desired, now)
            for n in range(64):
                mode, color = desired.get(n, (FULL, OFF))
                self.set_pad(n, color, mode)
        except Exception as e:
            print(f"[ApcMk2] Update-Fehler: {e}")

    def _apply_ripples(self, desired: dict, now: float):
        """Ueberlagert expandierende Farb-Ringe (Wellen) auf das Pad-Raster."""
        DURATION = 0.6
        SPEED = 10.0            # Pads pro Sekunde (gemaechliche, sichtbare Welle)
        alive = []
        for rp in self._ripples:
            age = now - rp["t0"]
            if age > DURATION:
                continue
            alive.append(rp)
            radius = age * SPEED
            r0, c0 = rp["note"] // 8, rp["note"] % 8
            idx = rgb_to_mk2_index(*rp["rgb"])
            bright = FULL if age < DURATION * 0.5 else MID
            for n in range(16, 64):     # nur VC-Pads; untere 2 Reihen = Mapper
                d = max(abs(n // 8 - r0), abs(n % 8 - c0))
                if d > 0 and abs(d - radius) < 0.7:
                    desired[n] = (bright, idx)
        self._ripples = alive

    def _collect_desired(self, now: float = 0.0) -> dict[int, tuple[int, int]]:
        """Ermittelt pro Pad-Note (0-63) den gewuenschten (mode, color) und merkt
        sich aktive Pads + Pad-Farben (fuer Ripple-Animationen)."""
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
        from src.ui.virtualconsole.vc_color import VCColor
        desired: dict[int, tuple[int, int]] = {}
        active: set[int] = set()
        note_rgb: dict[int, tuple] = {}
        note_style: dict[int, str] = {}
        bpm = self._bm.bpm if self._bm is not None else 0.0
        on_bank = getattr(self._canvas, "on_active_bank", None)
        for w in self._canvas.findChildren(VCButton):
            note = getattr(w, "midi_data1", -1)
            if note is None or not (PAD_MIN <= note <= PAD_MAX):
                continue
            if getattr(w, "midi_type", "note_on") != "note_on":
                continue
            if on_bank is not None and not on_bank(w):
                continue   # Pad gehoert zu einer anderen Bank -> aus
            # TAP-Pad: blinkt im BPM-Takt (Beat = heller Blitz).
            if getattr(w, "action", None) == ButtonAction.TAP:
                if bpm > 0 and (now - self._last_beat_time) < 0.11:
                    desired[note] = (FULL, WHITE)
                elif bpm > 0:
                    desired[note] = (MID, AZURE)
                else:
                    desired[note] = (DIM, BLUE)
                note_rgb[note] = (80, 120, 255)
                continue
            desired[note] = self._led_for_button(w, now)
            note_style[note] = getattr(w, "pad_style", "mirror")
            try:
                bg = w._bg_color
                note_rgb[note] = (bg.red(), bg.green(), bg.blue())
            except Exception:
                note_rgb[note] = (255, 255, 255)
            if self._is_active(w) or getattr(w, "_pressed", False):
                active.add(note)
        # Farb-Kacheln: Pad in der tatsaechlichen Farbe leuchten lassen.
        # Die AKTUELL angewaehlte Farbe (= Programmer-Farbe) blinkt (PULSE),
        # damit auf dem APC sichtbar ist, welcher Farbkanal gerade aktiv ist.
        active_color = self._active_color_rgb()
        for w in self._canvas.findChildren(VCColor):
            note = getattr(w, "midi_data1", -1)
            if note is None or not (PAD_MIN <= note <= PAD_MAX):
                continue
            if getattr(w, "midi_type", "note_on") != "note_on":
                continue
            if on_bank is not None and not on_bank(w):
                continue
            # Weiss-Kanal in die LED-Farbe einrechnen, sonst zeigt eine reine
            # W-Kachel (RGB 0,0,0, W>0) faelschlich OFF (4. Pad blieb dunkel).
            cw = int(getattr(w, "color_w", 0) or 0)
            disp = (min(255, w.color_r + cw), min(255, w.color_g + cw),
                    min(255, w.color_b + cw))
            color = rgb_to_mk2_index(*disp)
            tile_rgb = disp
            is_selected = active_color is not None and \
                (w.color_r, w.color_g, w.color_b) == active_color
            if getattr(w, "_pressed", False):
                mode = FULL
            elif is_selected:
                mode = PULSE          # aktive Farbe blinkt
            else:
                mode = MID
            desired[note] = (mode, color)
            note_rgb[note] = tile_rgb
            note_style[note] = "wave"   # Farb-Kacheln wellen (David: bei Farben cool)
            # Nur beim tatsaechlichen Druck eine Welle ausloesen; die aktive Farbe
            # blinkt via PULSE (kein Dauer-Wellen-Spam, solange sie ausgewaehlt ist).
            if getattr(w, "_pressed", False):
                active.add(note)
        self._active_notes = active
        self._note_rgb = note_rgb
        self._note_style = note_style
        return desired

    def _led_for_button(self, w, now: float = 0.0) -> tuple[int, int]:
        from src.ui.virtualconsole.vc_button import ButtonAction
        if getattr(w, "_pressed", False):
            return (FULL, WHITE)
        action = getattr(w, "action", None)
        is_func = action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                             ButtonAction.TOGGLE, ButtonAction.FLASH)
        try:
            bg = w._bg_color
            bg_idx = rgb_to_mk2_index(bg.red(), bg.green(), bg.blue())
        except Exception:
            bg, bg_idx = None, BLUE
        if action == ButtonAction.LIBRARY_SNAP:
            # Bibliothek-Farb-/Snap-Taste: Pad in der Snap-Farbe, hell wenn aktiv.
            sc = None
            try:
                sc = w._snap_swatch_color()
            except Exception:
                sc = None
            idx = (rgb_to_mk2_index(sc.red(), sc.green(), sc.blue())
                   if sc is not None else bg_idx)
            return (FULL if self._is_active(w) else MID, idx)
        if not is_func:
            # Snapshot / Clear: feste Button-Farbe halten.
            return (MID, bg_idx)
        if not self._is_active(w):
            return (DIM, RED)        # inaktiv = gedimmtes Rot
        # AKTIV -> Pad-Stil rendern
        style = getattr(w, "pad_style", "mirror")
        if style == "solid":
            return (FULL, bg_idx)
        if style == "pulse":
            return (PULSE, bg_idx)   # Hardware pulsiert von selbst
        if style == "alternate":
            c2 = getattr(w, "pad_color2", (0, 0, 255))
            phase = int(now / 0.25) % 2     # ~0.25 s Wechsel
            return (FULL, bg_idx if phase == 0 else rgb_to_mk2_index(*c2))
        # mirror / wave: aktuelle Rig-Farbe (wave triggert zusaetzlich Wellen in _update)
        rgb = self._current_rig_color()
        if rgb and sum(rgb) > 12:
            return (FULL, rgb_to_mk2_index(*rgb))
        return (FULL, bg_idx) if style == "wave" else (DIM, GREEN)

    def _active_color_rgb(self):
        """Die aktuell im Programmer gesetzte Farbe (color_r/g/b) — fuer das
        Blinken der angewaehlten Farb-Kachel. None, wenn keine Farbe aktiv ist."""
        try:
            from src.core.app_state import get_state
            st = get_state()
            for attrs in st.programmer.values():
                if not isinstance(attrs, dict):
                    continue
                if any(k in attrs for k in ("color_r", "color_g", "color_b")):
                    return (int(attrs.get("color_r", 0)),
                            int(attrs.get("color_g", 0)),
                            int(attrs.get("color_b", 0)))
        except Exception:
            pass
        return None

    def _current_rig_color(self):
        """Aktuelle Farbe des ersten gepatchten Fixtures aus dem Live-Universe
        (inkl. Intensitaet/Weiss) — fuer animiertes Pad-Feedback aktiver Effekte."""
        try:
            from src.core.app_state import get_state, get_channels_for_patched
            st = get_state()
            fx = st.get_patched_fixtures()
            if not fx:
                return None
            f = fx[0]
            u = st.universes.get(f.universe)
            if u is None:
                return None
            cmap = {c.attribute: c.channel_number for c in get_channels_for_patched(f)}

            def rd(attr):
                cn = cmap.get(attr)
                return u.get_channel(f.address + cn - 1) if cn else 0

            scale = (rd("intensity") / 255.0) if "intensity" in cmap else 1.0
            w = rd("color_w")
            r = min(255, int((rd("color_r") + w) * scale))
            g = min(255, int((rd("color_g") + w) * scale))
            b = min(255, int((rd("color_b") + w) * scale))
            return (r, g, b)
        except Exception:
            return None

    def _is_active(self, w) -> bool:
        from src.ui.virtualconsole.vc_button import ButtonAction
        from src.core.app_state import get_state
        try:
            # Bibliothek-Snap-Toggle: aktiv = Snap liegt im Programmer.
            if getattr(w, "action", None) == ButtonAction.LIBRARY_SNAP:
                return bool(getattr(w, "_snap_active", False))
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

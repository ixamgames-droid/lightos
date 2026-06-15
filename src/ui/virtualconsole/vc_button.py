"""VCButton — Virtual Console Button Widget."""
from __future__ import annotations
import os
import json
from enum import Enum
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSizePolicy, QSpinBox, QLabel,
                                QCheckBox)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget

_SNAPSHOTS_FILE = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS", "snapshots.json"
)


class ButtonAction(str, Enum):
    TOGGLE   = "Toggle"
    FLASH    = "Flash"
    FUNCTION_TOGGLE = "FunctionToggle"
    FUNCTION_FLASH  = "FunctionFlash"
    BLACKOUT = "Blackout"
    STOP_ALL = "StopAll"
    SNAPSHOT = "Snapshot"
    # Bibliothek-Snap (Farbe/Look aus der Show-Bibliothek) auf die Taste legen.
    # Verhalten ueber snap_mode: set (bleibt), flash (nur gehalten), toggle (an/aus).
    LIBRARY_SNAP = "LibrarySnap"
    CLEAR    = "Clear"        # Programmer leeren (manuelle Farben/Snaps freigeben)
    TAP      = "Tap"          # Tap-Tempo: setzt globale BPM (beat-Effekte folgen)
    AUDIO_BPM = "AudioBpm"    # Musik-Modus: BPM aus dem Audio-Eingang (an/aus)
    # Phase 6: loest eine Effekt-Aktion aus (effect_action_key), z. B. add_color,
    # next_color, toggle_bounce, toggle_freeze, clear_live_override, reverse_direction.
    EFFECT_ACTION = "EffectAction"
    # F-24: waehlt die Fixtures einer Gruppe (group_name) in den Programmer —
    # damit lassen sich Gruppen live per Pad/MIDI auswaehlen (statt nur Funktionen).
    SELECT_GROUP = "SelectGroup"
    # Musik-Player (core/audio/media_player.py): Wiedergabe steuern (z. B. APC-Pads).
    MEDIA_PLAY_PAUSE = "MediaPlayPause"
    MEDIA_NEXT = "MediaNext"
    MEDIA_PREV = "MediaPrev"


# Benutzerfreundliche deutsche Labels für die Aktions-Auswahl (statt der rohen
# Enum-Codes). Reihenfolge = Anzeige im Dropdown.
BUTTON_ACTION_LABELS: list[tuple[str, str]] = [
    (ButtonAction.FUNCTION_TOGGLE, "Funktion an/aus"),
    (ButtonAction.FUNCTION_FLASH,  "Funktion (nur gehalten)"),
    (ButtonAction.EFFECT_ACTION,   "Effekt-Aktion (Live)"),
    (ButtonAction.SELECT_GROUP,    "Gruppe auswählen"),
    (ButtonAction.LIBRARY_SNAP,    "Bibliothek-Farbe/Snap"),
    (ButtonAction.SNAPSHOT,        "Snapshot abrufen"),
    (ButtonAction.CLEAR,           "Programmer leeren (Clear)"),
    (ButtonAction.STOP_ALL,        "Alles stoppen"),
    (ButtonAction.BLACKOUT,        "Blackout"),
    (ButtonAction.TAP,             "Tap-Tempo"),
    (ButtonAction.AUDIO_BPM,       "Musik-BPM"),
    (ButtonAction.MEDIA_PLAY_PAUSE, "Musik: Play/Pause"),
    (ButtonAction.MEDIA_NEXT,      "Musik: Nächstes Lied"),
    (ButtonAction.MEDIA_PREV,      "Musik: Voriges Lied"),
    (ButtonAction.TOGGLE,          "Executor: Umschalten (Go)"),
    (ButtonAction.FLASH,           "Executor: Flash"),
]


# Kuratierte Effekt-Aktionen (ButtonAction.EFFECT_ACTION) mit deutschen Labels —
# ersetzt das fehleranfällige Freitext-Feld. Power-User können bei einem gebundenen
# Effekt zusätzlich dessen eigene Aktionen (effect_live.list_actions) sehen.
EFFECT_ACTION_LABELS: list[tuple[str, str]] = [
    ("next_color",          "Nächste Farbe"),
    ("prev_color",          "Vorherige Farbe"),
    ("add_color",           "Farbe hinzufügen"),
    ("remove_color",        "Farbe entfernen"),
    ("toggle_color",        "Farbe an/aus"),
    ("reverse_direction",   "Richtung umkehren"),
    ("toggle_bounce",       "Bounce an/aus"),
    ("toggle_freeze",       "Einfrieren an/aus"),
    ("reseed",              "Zufall neu würfeln (Random/EFX)"),
    ("clear_live_override", "Live-Overrides löschen"),
    ("commit_live",         "Live-Werte übernehmen"),
    ("tap",                 "Tap-Tempo"),
]


class VCButton(VCWidget):
    """Pushbutton — Flash / Toggle / Blackout / StopAll / Snapshot."""

    def __init__(self, caption: str = "Button", parent=None):
        super().__init__(caption, parent)
        self.action = ButtonAction.TOGGLE
        self.function_id: int | None = None
        self.snapshot_index: int | None = None
        # Bibliothek-Snap (ButtonAction.LIBRARY_SNAP): Referenz auf einen Snap der
        # Show-Bibliothek (src.core.engine.snap_library) + Tastenverhalten.
        self.snap_id: int | None = None
        self.snap_mode: str = "toggle"      # "set" | "flash" | "toggle"
        self._snap_active: bool = False     # Laufzeit-Zustand fuer toggle
        # Vorherige Programmer-Werte (fuer Toggle/Flash-Ruecknahme):
        # {(fid, attr): alter_wert_oder_None}
        self._snap_prev: dict[tuple[int, str], int | None] = {}
        # Phase 6: Effekt-Aktions-Name fuer ButtonAction.EFFECT_ACTION.
        self.effect_action_key: str = "next_color"
        # F-24: Gruppenname fuer ButtonAction.SELECT_GROUP.
        self.group_name: str = ""
        # Live-Bearbeitung: macht den gestarteten Effekt zum aktiven Bearbeitungsziel
        # dieses Slots (FUNCTION_TOGGLE/FLASH). Fader/Farb-Kacheln mit gleichem
        # edit_slot bearbeiten dann GENAU diesen Effekt (quadrantenweise exklusiv).
        self.edit_slot: str = ""
        # BTN-01: zusaetzliche Aktionen, die beim Druck (nach der Primaer-Aktion)
        # der Reihe nach ausgefuehrt werden. Jede Aktion = Dict:
        # {type, function_id, snapshot_index, snap_id, effect_action_key, mode, delay}.
        # Leer = klassischer Ein-Aktions-Button (vollstaendig rueckwaertskompatibel).
        self.actions: list[dict] = []
        # Verhalten beim Starten einer Funktion:
        #   exclusive        -> stoppt alle anderen Funktionen (nur 1 aktiv)
        #   solo_fixtures    -> stoppt nur andere Effekte, die DIESELBEN Geraete
        #                       benutzen (chirurgisch: neuer Farb-Effekt loest den
        #                       alten auf denselben Strahlern ab, Effekte auf
        #                       anderen Geraeten laufen weiter). Loest das
        #                       „Effekt aus einer anderen Bank ueberschreibt mit".
        #   clear_programmer -> leert vorher den Programmer (manuelle Farben/Snaps
        #                       blockieren sonst den Effekt, da Programmer = hoechste Prioritaet)
        self.exclusive: bool = False
        self.solo_fixtures: bool = False
        self.clear_programmer: bool = False
        # APC-Pad-Anzeige-Stil: mirror = Effekt-Farbe spiegeln, solid = feste Farbe,
        # pulse = pulsieren, alternate = zwei Farben im Wechsel, wave = Dauer-Welle.
        self.pad_style: str = "mirror"
        self.pad_color2 = (0, 0, 255)   # zweite Farbe fuer 'alternate'

        # MIDI binding (-1 = keine Bindung)
        self.midi_ch: int = 0          # 0 = alle Kanäle
        self.midi_data1: int = -1      # Note / CC-Nummer
        self.midi_type: str = "note_on"
        self.key_binding: str = ""     # Tastatur-Hotkey ("Ctrl+F5", "" = keiner)

        self._pressed = False
        self._midi_armed = False       # leuchtet auf im MIDI-Learn-Modus
        self._bg_color = QColor("#1a3a5c")
        self._fg_color = QColor("#ffffff")
        self.resize(120, 60)

    # ── MIDI-Learn ───────────────────────────────────────────────────────────

    def arm_midi_learn(self):
        """Aktiviert den MIDI-Learn-Modus für diesen Button (visuelles Feedback)."""
        self._midi_armed = True
        self.update()

    def accept_midi(self, ch: int, data1: int, msg_type: str):
        """Speichert die empfangene MIDI-Bindung."""
        self.midi_ch = ch
        self.midi_data1 = data1
        self.midi_type = msg_type
        self._midi_armed = False
        self.update()

    # ── MLV: Effekt-Bindung (siehe VCWidget) ───────────────────────────────────

    def is_effect_bound(self) -> bool:
        return self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                               ButtonAction.EFFECT_ACTION)

    def live_effect_function_id(self):
        return self.function_id

    # ── MIDI Teach (siehe VCWidget) ────────────────────────────────────────────

    def supports_midi_teach(self) -> bool:
        return True

    def current_midi_binding(self):
        if self.midi_data1 is None or self.midi_data1 < 0:
            return None
        return (self.midi_type, self.midi_ch, self.midi_data1)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_data1 = -1
            return
        # APC-Tasten -> note_on, Fader -> cc (VCButton kann beides auswerten)
        self.midi_type = "cc" if msg_type == "cc" else "note_on"
        self.midi_ch = channel or 0
        self.midi_data1 = data1

    def matches_midi(self, msg) -> bool:
        """True wenn die MIDI-Message zu dieser Bindung passt (T-6: zentral)."""
        from .vc_widget import midi_binding_matches
        return midi_binding_matches(msg, self.midi_type, self.midi_ch, self.midi_data1)

    def handle_midi(self, msg) -> bool:
        if not self.matches_midi(msg):
            return False
        self.trigger_from_midi(msg)
        return True

    # ── Keyboard-Bindung (analog MIDI) ───────────────────────────────────────

    def supports_key_teach(self) -> bool:
        return True

    def current_key_binding(self) -> str:
        return self.key_binding or ""

    def apply_key_binding(self, seq: str):
        self.key_binding = (seq or "").strip()

    def handle_key(self, seq: str, pressed: bool) -> bool:
        """Hotkey wie eine MIDI-Note behandeln: Press = note_on, Release =
        note_off — damit funktionieren Toggle UND Flash exakt wie über MIDI."""
        if not self.key_binding or seq != self.key_binding:
            return False
        self._pressed = pressed
        self._trigger(pressed)
        self.update()
        return True

    def trigger_from_midi(self, msg):
        """Löst den Button durch eine MIDI-Message aus."""
        if msg.msg_type == "note_on" and msg.data2 > 0:
            self._pressed = True
            self._trigger(True)
            self.update()
        elif msg.msg_type in ("note_off",) or (msg.msg_type == "note_on" and msg.data2 == 0):
            self._pressed = False
            self._trigger(False)
            self.update()
        elif msg.msg_type == "cc":
            press = msg.data2 > 63
            if press != self._pressed:
                self._pressed = press
                self._trigger(press)
                self.update()

    # ── Snapshot ─────────────────────────────────────────────────────────────

    def _apply_snapshot(self, index: int):
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list) or index >= len(payload):
                return
            snap_data = payload[index]
            if not snap_data:
                return
            raw = snap_data.get("values", {})
            from src.core.app_state import get_state
            state = get_state()
            for k, attrs in raw.items():
                for attr, val in attrs.items():
                    try:
                        state.set_programmer_value(int(k), attr, int(val))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[VCButton] Snapshot-Apply-Fehler: {e}")

    # ── Bibliothek-Snap (Farbe / Look) ───────────────────────────────────────

    def _library_snap(self):
        """Liefert den referenzierten Snap aus der Show-Bibliothek (oder None)."""
        if self.snap_id is None:
            return None
        try:
            from src.core.engine.snap_library import get_snap_library
            return get_snap_library().get(int(self.snap_id))
        except Exception as e:
            print(f"[VCButton] Snap-Lookup-Fehler: {e}")
            return None

    def _apply_library_snap(self):
        """Schreibt die Werte des Bibliothek-Snaps in den Programmer und merkt
        sich die vorherigen Werte, damit Toggle/Flash sie zuruecknehmen koennen."""
        snap = self._library_snap()
        if snap is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            self._snap_prev = {}
            for fid, attrs in snap.values.items():
                for attr, val in attrs.items():
                    fid_i = int(fid)
                    self._snap_prev[(fid_i, attr)] = state.get_programmer_value(fid_i, attr)
                    state.set_programmer_value(fid_i, attr, int(val))
        except Exception as e:
            print(f"[VCButton] Snap-Apply-Fehler: {e}")

    def _restore_library_snap(self):
        """Stellt die vor dem Snap aktiven Programmer-Werte wieder her."""
        if not self._snap_prev:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            for (fid, attr), old in self._snap_prev.items():
                if old is None:
                    state.clear_programmer_value(fid, attr)
                else:
                    state.set_programmer_value(fid, attr, int(old))
        except Exception as e:
            print(f"[VCButton] Snap-Restore-Fehler: {e}")
        finally:
            self._snap_prev = {}

    def _snap_swatch_color(self) -> QColor | None:
        """Repraesentative Farbe des Snaps (erstes Fixture mit RGB) fuer die Kachel."""
        snap = self._library_snap()
        if snap is None:
            return None
        for attrs in snap.values.values():
            r = attrs.get("color_r"); g = attrs.get("color_g"); b = attrs.get("color_b")
            if r is not None or g is not None or b is not None:
                return QColor(int(r or 0), int(g or 0), int(b or 0))
        return None

    # ── Action ───────────────────────────────────────────────────────────────

    def _trigger(self, press: bool):
        """Primaer-Aktion + (auf Druck) die zusaetzlichen Multi-Aktionen (BTN-01)."""
        self._trigger_primary(press)
        if press and self.actions:
            self._run_extra_actions()

    def _run_extra_actions(self):
        from PySide6.QtCore import QTimer
        for entry in list(self.actions):
            try:
                delay = float(entry.get("delay", 0) or 0)
            except (TypeError, ValueError):
                delay = 0.0
            if delay > 0:
                QTimer.singleShot(int(delay * 1000),
                                  lambda e=entry: self._execute_extra(e))
            else:
                self._execute_extra(entry)

    def _execute_extra(self, entry: dict):
        """Fuehrt eine einzelne Zusatz-Aktion diskret aus (kein Press/Release-State).
        Unterstuetzt: function (on/off/toggle), effect_action, snapshot, library_snap,
        blackout (on/off), stop_all, clear, clear_non_vc, tap."""
        from src.core.app_state import get_state
        state = get_state()
        t = str(entry.get("type", ""))
        mode = str(entry.get("mode", "toggle"))
        try:
            if t == "function":
                fid = entry.get("function_id")
                if fid is None:
                    return
                fid = int(fid)
                fm = state.function_manager
                if mode == "on":
                    fm.start(fid)
                elif mode == "off":
                    fm.stop(fid)
                else:
                    fm.stop(fid) if fm.is_running(fid) else fm.start(fid)
            elif t == "effect_action":
                from src.core.engine import effect_live
                effect_live.do_action(entry.get("effect_action_key", "next_color"),
                                      entry.get("function_id"))
            elif t == "snapshot":
                idx = entry.get("snapshot_index")
                if idx is not None:
                    self._apply_snapshot(int(idx))
            elif t == "library_snap":
                self._apply_snap_id_oneshot(entry.get("snap_id"))
            elif t == "blackout":
                state.output_manager.set_blackout(mode != "off")
            elif t == "stop_all":
                state.playback_engine.stop_all()
            elif t == "clear":
                state.clear_programmer()
            elif t == "clear_non_vc":
                state.clear_all_non_vc()
            elif t == "tap":
                from src.core.engine.bpm_manager import get_bpm_manager
                get_bpm_manager().tap()
        except Exception as e:
            print(f"[VCButton] extra action '{t}' error: {e}")

    def _apply_snap_id_oneshot(self, snap_id):
        """Schreibt einen Bibliothek-Snap einmalig in den Programmer (ohne Restore)."""
        if snap_id is None:
            return
        try:
            from src.core.engine.snap_library import get_snap_library
            from src.core.app_state import get_state
            snap = get_snap_library().get(int(snap_id))
            if snap is None:
                return
            state = get_state()
            for fid, attrs in snap.values.items():
                for attr, val in attrs.items():
                    state.set_programmer_value(int(fid), attr, int(val))
        except Exception as e:
            print(f"[VCButton] oneshot snap error: {e}")

    def _trigger_primary(self, press: bool):
        if press:
            try:
                from .vc_frame import VCFrame
                p = self.parent()
                while p is not None:
                    if isinstance(p, VCFrame) and p.is_solo():
                        p.on_child_activated(self)
                        break
                    p = p.parent()
            except Exception:
                pass

        from src.core.app_state import get_state
        state = get_state()

        if self.action == ButtonAction.BLACKOUT:
            state.output_manager.set_blackout(bool(press))
            return

        if self.action == ButtonAction.STOP_ALL:
            if press:
                state.playback_engine.stop_all()
            return

        if self.action == ButtonAction.SNAPSHOT:
            if press and self.snapshot_index is not None:
                self._apply_snapshot(self.snapshot_index)
            return

        if self.action == ButtonAction.LIBRARY_SNAP:
            if self.snap_mode == "flash":
                # Halten: beim Druck setzen, beim Loslassen zuruecknehmen.
                if press:
                    self._apply_library_snap()
                else:
                    self._restore_library_snap()
            elif self.snap_mode == "set":
                # Setzen: bleibt bestehen (kein Toggle/Restore).
                if press:
                    self._apply_library_snap()
                    self._snap_active = True
            else:  # "toggle"
                if press:
                    if self._snap_active:
                        self._restore_library_snap()
                        self._snap_active = False
                    else:
                        self._apply_library_snap()
                        self._snap_active = True
            return

        if self.action == ButtonAction.CLEAR:
            if press:
                try:
                    state.clear_programmer()
                except Exception:
                    pass
            return

        if self.action == ButtonAction.SELECT_GROUP:
            # F-24: Fixtures der Gruppe in den Programmer waehlen (Live-Auswahl per Pad).
            if press and self.group_name:
                try:
                    state.select_group_by_name(self.group_name)
                except Exception as e:
                    print(f"[VCButton] select group error: {e}")
            return

        if self.action == ButtonAction.TAP:
            if press:
                try:
                    from src.core.engine.bpm_manager import get_bpm_manager
                    get_bpm_manager().tap()
                except Exception:
                    pass
            return

        if self.action == ButtonAction.AUDIO_BPM:
            if press:
                try:
                    from src.core.engine.bpm_manager import get_bpm_manager
                    mgr = get_bpm_manager()
                    mgr.use_audio_source(not mgr.audio_active)
                except Exception as e:
                    print(f"[VCButton] audio-bpm toggle error: {e}")
                self.update()
            return

        if self.action in (ButtonAction.MEDIA_PLAY_PAUSE, ButtonAction.MEDIA_NEXT,
                           ButtonAction.MEDIA_PREV):
            if press:
                try:
                    from src.core.audio.media_player import get_media_player
                    mp = get_media_player()
                    if self.action == ButtonAction.MEDIA_PLAY_PAUSE:
                        mp.toggle()
                    elif self.action == ButtonAction.MEDIA_NEXT:
                        mp.next()
                    else:
                        mp.prev()
                except Exception as e:
                    print(f"[VCButton] media action error: {e}")
            return

        if self.action == ButtonAction.EFFECT_ACTION:
            # Phase 6: Effekt-Aktion auf dem gebundenen / aktiven Effekt ausloesen.
            # Live-Bearbeitung: ohne feste function_id den Effekt aus dem Edit-Slot nehmen.
            if press:
                try:
                    from src.core.engine import effect_live
                    fid = self.function_id
                    if fid is None and self.edit_slot:
                        fid = effect_live.get_edit_target(self.edit_slot)
                    effect_live.do_action(self.effect_action_key, fid)
                except Exception:
                    pass
            return

        if self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            if self.function_id is None:
                return
            fid = int(self.function_id)
            fm = state.function_manager

            def _begin():
                # Manuelle Farben/Snaps freigeben + ggf. andere Funktionen stoppen,
                # damit der Effekt sichtbar wird bzw. nur einer laeuft.
                if self.clear_programmer:
                    try:
                        state.clear_programmer()
                    except Exception:
                        pass
                # Live-Edit-Slot: pro Slot nur EIN Effekt — den vorigen Slot-Effekt
                # stoppen (quadrantenweise exklusiv, ohne globales stop_all).
                if self.edit_slot:
                    try:
                        from src.core.engine import effect_live
                        prev = effect_live.get_edit_target(self.edit_slot)
                        if prev is not None and prev != fid and fm.is_running(prev):
                            fm.stop(prev)
                    except Exception:
                        pass
                elif self.exclusive:
                    try:
                        fm.stop_all()
                    except Exception:
                        pass
                # Solo auf gleichen Geraeten: andere laufende Effekte, die
                # DIESELBEN Strahler benutzen, werden ersetzt (auch aus einer
                # anderen Bank). Effekte auf anderen Geraeten laufen weiter.
                if self.solo_fixtures:
                    try:
                        fm.stop_others_sharing_fixtures(fid)
                    except Exception:
                        pass
                fm.start(fid)
                # Dieser Effekt wird das aktive Bearbeitungsziel des Slots.
                if self.edit_slot:
                    try:
                        from src.core.engine import effect_live
                        effect_live.set_edit_target(self.edit_slot, fid)
                    except Exception:
                        pass

            if self.action == ButtonAction.FUNCTION_TOGGLE:
                if press:
                    if fm.is_running(fid):
                        fm.stop(fid)
                    else:
                        _begin()
            else:  # FUNCTION_FLASH
                if press:
                    _begin()
                else:
                    fm.stop(fid)
            return

        if self.function_id is None:
            return
        slot = self.function_id
        executors = state.playback_engine.executors
        if slot >= len(executors):
            return
        ex = executors[slot]
        if self.action == ButtonAction.FLASH:
            ex.press_btn("flash") if press else ex.release_btn("flash")
        elif self.action == ButtonAction.TOGGLE and press:
            ex.press_btn("go")

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():       # Display-only: Touch gesperrt
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._trigger(True)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._trigger(False)
            self.update()
        event.accept()

    def _function_running(self) -> bool:
        """True, wenn dieser Button eine Funktion steuert, die gerade laeuft.
        Quelle der On-Screen-Rueckmeldung (Toggle-Pad bleibt beleuchtet, solange
        sein Effekt laeuft). Die VC-View repaintet den Button bei jedem Wechsel
        des Laufzustands (UI-Thread-Timer)."""
        if self.action not in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            return False
        if self.function_id is None:
            return False
        try:
            from src.core.app_state import get_state
            return get_state().function_manager.is_running(int(self.function_id))
        except Exception:
            return False

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        # "lit" = gedrueckt ODER ein Bibliothek-Snap-Toggle ist aktiv (bleibt an).
        snap_on = (self.action == ButtonAction.LIBRARY_SNAP and self._snap_active)
        audio_on = False
        if self.action == ButtonAction.AUDIO_BPM:
            try:
                from src.core.engine.bpm_manager import get_bpm_manager
                audio_on = get_bpm_manager().audio_active
            except Exception:
                audio_on = False
        # Laufzustand der gebundenen Funktion: ein Toggle-Pad bleibt „an", solange
        # sein Effekt laeuft — nicht nur waehrend des Drucks. Sonst sah es aus, als
        # liefe nichts mehr, obwohl die Geraete sich noch bewegten (Anzeige-Desync).
        func_on = self._function_running()
        lit = self._pressed or snap_on or audio_on or func_on
        bg = self._bg_color.lighter(160) if lit else self._bg_color
        p.fillRect(self.rect(), bg)

        # "Gedrueckt"-Feedback (Maus ODER MIDI): deutlicher heller Rahmen
        if self._pressed:
            p.setPen(QPen(QColor("#ffe680"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        elif func_on:
            # Funktion laeuft (Toggle aktiv): gruener Rahmen (an, aber nicht gedrueckt).
            p.setPen(QPen(QColor("#3fb950"), 2))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        elif snap_on:
            # Aktiver Snap-Toggle: dezenter gruener Rahmen (an, aber nicht gedrueckt).
            p.setPen(QPen(QColor("#58d68d"), 2))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
        elif audio_on:
            # Musik-Modus aktiv: cyaner Rahmen (BPM kommt vom Audio-Eingang).
            p.setPen(QPen(QColor("#00d4ff"), 2))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        # MIDI-Learn-Arm: orange Rahmen pulsieren
        if self._midi_armed:
            p.setPen(QPen(QColor("#ff8800"), 3))
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))

        p.setPen(self._fg_color)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)

        # Snapshot-Index anzeigen wenn Snapshot-Aktion
        display = self.caption
        if self.action == ButtonAction.SNAPSHOT and self.snapshot_index is not None:
            display += f"\n[Snap {self.snapshot_index + 1}]"

        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, display)

        # Farbbalken unten je nach Aktion
        if self.action == ButtonAction.FLASH:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff8800"))
        elif self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#3fb950"))
        elif self.action == ButtonAction.BLACKOUT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff2222"))
        elif self.action == ButtonAction.SNAPSHOT:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ffd700"))
        elif self.action == ButtonAction.LIBRARY_SNAP:
            # Farbbalken in der Snap-Farbe (Bibliothek-Look auf einen Blick).
            sc = self._snap_swatch_color() or QColor("#b388ff")
            p.fillRect(0, self.height() - 4, self.width(), 4, sc)
        elif self.action == ButtonAction.AUDIO_BPM:
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#00d4ff"))
        elif self.action in (ButtonAction.MEDIA_PLAY_PAUSE, ButtonAction.MEDIA_NEXT,
                             ButtonAction.MEDIA_PREV):
            p.fillRect(0, self.height() - 4, self.width(), 4, QColor("#ff5fb0"))

        # MIDI-Bindung-Indikator oben rechts
        if self.midi_data1 >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))

        # Tastatur-Bindung: Taste klein oben links anzeigen (⌨ + Sequenz);
        # rückt nach rechts, wenn der Multi-Action-Indikator dort sitzt.
        if self.key_binding:
            kx = 16 if self.actions else 2
            p.setPen(QColor("#9acbff"))
            p.setFont(QFont("Segoe UI", 6))
            p.drawText(QRect(kx, 0, self.width() - kx - 10, 10),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"⌨{self.key_binding}")

        # BTN-01: Multi-Action-Indikator oben links (Anzahl Zusatz-Aktionen)
        if self.actions:
            p.fillRect(0, 0, 14, 10, QColor("#b388ff"))
            p.setPen(QColor("#000000"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRect(0, 0, 14, 10), Qt.AlignmentFlag.AlignCenter, f"+{len(self.actions)}")

        p.end()

    # ── Properties dialog ────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Button Einstellungen")
        form = QFormLayout(dlg)

        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)

        act = QComboBox()
        for a, lbl in BUTTON_ACTION_LABELS:
            act.addItem(lbl, a.value)        # Label sichtbar, Enum-Wert als Data
        for i in range(act.count()):
            if act.itemData(i) == self.action.value:
                act.setCurrentIndex(i)
                break
        form.addRow("Aktion:", act)

        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot / Function-ID:", slot)

        # Funktion/Chase nach Namen auswaehlen -> fuellt das Function-ID-Feld.
        func_combo = QComboBox()
        func_combo.addItem("(nach ID/Slot oben)", -1)
        self._populate_function_combo(func_combo)
        if self.function_id is not None:
            for i in range(func_combo.count()):
                if func_combo.itemData(i) == self.function_id:
                    func_combo.setCurrentIndex(i)
                    break
        func_combo.currentIndexChanged.connect(
            lambda _i: slot.setText(str(func_combo.currentData()))
            if func_combo.currentData() is not None and func_combo.currentData() >= 0
            else None
        )
        form.addRow("Funktion/Chase (Name):", func_combo)

        # Snapshot-Auswahl
        snap_combo = QComboBox()
        snap_combo.addItem("(keiner)", -1)
        self._populate_snapshot_combo(snap_combo)
        if self.snapshot_index is not None:
            for i in range(snap_combo.count()):
                if snap_combo.itemData(i) == self.snapshot_index:
                    snap_combo.setCurrentIndex(i)
                    break
        form.addRow("Snapshot:", snap_combo)

        # Bibliothek-Snap (Farbe/Look) — Aktion = LibrarySnap
        lib_combo = QComboBox()
        lib_combo.addItem("(keiner)", -1)
        self._populate_library_combo(lib_combo)
        if self.snap_id is not None:
            for i in range(lib_combo.count()):
                if lib_combo.itemData(i) == self.snap_id:
                    lib_combo.setCurrentIndex(i)
                    break
        form.addRow("Bibliothek-Farbe/Snap:", lib_combo)

        snap_mode_combo = QComboBox()
        _SNAP_MODES = [("toggle", "Umschalten (an/aus)"),
                       ("set", "Setzen (bleibt)"),
                       ("flash", "Halten (nur gedrückt)")]
        for key, label in _SNAP_MODES:
            snap_mode_combo.addItem(label, key)
        for i, (key, _l) in enumerate(_SNAP_MODES):
            if key == self.snap_mode:
                snap_mode_combo.setCurrentIndex(i)
                break
        form.addRow("Tasten-Modus (Snap):", snap_mode_combo)

        # Phase 6: Effekt-Aktion (nur bei Aktion = EffectAction) — Auswahl mit
        # deutschen Labels statt Freitext. Aktionen eines gebundenen Effekts
        # (list_actions) werden ergänzt; der gespeicherte Key bleibt immer erhalten.
        eff_action_combo = QComboBox()
        _eff_keys: list[str] = []
        for _k, _lbl in EFFECT_ACTION_LABELS:
            eff_action_combo.addItem(_lbl, _k)
            _eff_keys.append(_k)
        try:
            from src.core.engine import effect_live
            for _k, _lbl in effect_live.list_actions(self.function_id):
                if _k not in _eff_keys:
                    eff_action_combo.addItem(f"{_lbl}  ({_k})", _k)
                    _eff_keys.append(_k)
        except Exception:
            pass
        if self.effect_action_key not in _eff_keys:   # gespeicherten Key erhalten
            eff_action_combo.addItem(self.effect_action_key, self.effect_action_key)
            _eff_keys.append(self.effect_action_key)
        for i in range(eff_action_combo.count()):
            if eff_action_combo.itemData(i) == self.effect_action_key:
                eff_action_combo.setCurrentIndex(i)
                break
        eff_action_combo.setToolTip("Welche Live-Aktion der gebundene Effekt ausführt.")
        form.addRow("Effekt-Aktion (EffectAction):", eff_action_combo)

        # F-24: Gruppenname (nur bei Aktion = SelectGroup).
        group_combo = QComboBox()
        group_combo.setEditable(True)
        group_combo.addItem("")
        try:
            from sqlalchemy import select
            from src.core.database.models import FixtureGroup
            from src.core.app_state import get_state as _gs
            with _gs()._session() as _s:
                for _gn in _s.execute(select(FixtureGroup.name)).scalars().all():
                    group_combo.addItem(_gn)
        except Exception:
            pass
        group_combo.setCurrentText(self.group_name or "")
        group_combo.setToolTip("Fixture-Gruppe für Aktion = SelectGroup.")
        form.addRow("Gruppe (SelectGroup):", group_combo)

        # Live-Edit-Slot (FUNCTION_TOGGLE/FLASH): macht den Effekt zum aktiven
        # Bearbeitungsziel des Slots; Fader/Farben mit gleichem Slot editieren ihn.
        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext, z. B. MH oder MX). Beim Start "
                                  "wird dieser Effekt das Bearbeitungsziel des Slots; Fader/"
                                  "Farb-Kacheln mit demselben Slot bearbeiten ihn (pro Quadrant).")
        form.addRow("Live-Edit-Slot:", edit_slot_edit)

        # Start-Verhalten (nur Funktions-Aktionen): exklusiv + Programmer leeren.
        exclusive_cb = QCheckBox("Andere Funktionen stoppen (nur diese aktiv)")
        exclusive_cb.setChecked(self.exclusive)
        exclusive_cb.setToolTip("Beim Start dieser Funktion alle anderen laufenden "
                                "Funktionen stoppen (Solo). Nur FUNCTION-Aktionen.")
        form.addRow("Exklusiv:", exclusive_cb)
        solo_fix_cb = QCheckBox("Andere Effekte auf denselben Geräten stoppen")
        solo_fix_cb.setChecked(self.solo_fixtures)
        solo_fix_cb.setToolTip("Beim Start nur die Effekte stoppen, die DIESELBEN "
                               "Strahler benutzen (auch aus einer anderen Bank) — der "
                               "neue Effekt löst den alten auf diesen Geräten ab. "
                               "Effekte auf anderen Geräten laufen weiter. "
                               "Nur FUNCTION-Aktionen.")
        form.addRow("Geräte-Solo:", solo_fix_cb)
        clear_prog_cb = QCheckBox("Programmer vorher leeren")
        clear_prog_cb.setChecked(self.clear_programmer)
        clear_prog_cb.setToolTip("Vor dem Start den Programmer leeren — manuelle "
                                 "Farben/Snaps haben sonst Vorrang und überdecken den "
                                 "Effekt. Nur FUNCTION-Aktionen.")
        form.addRow("Programmer leeren:", clear_prog_cb)

        form.addRow(QLabel("── MIDI-Bindung ──"))

        midi_type_combo = QComboBox()
        midi_type_combo.addItems(["note_on", "cc"])
        midi_type_combo.setCurrentText(self.midi_type)
        form.addRow("MIDI-Typ:", midi_type_combo)

        midi_ch_spin = QSpinBox()
        midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch)
        midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)

        midi_note_spin = QSpinBox()
        midi_note_spin.setRange(-1, 127)
        midi_note_spin.setValue(self.midi_data1)
        midi_note_spin.setSpecialValueText("keine")
        form.addRow("Note / CC (-1=keine):", midi_note_spin)

        form.addRow(QLabel("── APC-Pad-Anzeige ──"))
        pad_style_combo = QComboBox()
        _PAD_STYLES = [("mirror", "Spiegel (Effekt-Farbe)"), ("solid", "Feste Farbe"),
                       ("pulse", "Pulsieren"), ("alternate", "Zwei Farben im Wechsel"),
                       ("wave", "Dauer-Welle")]
        for key, label in _PAD_STYLES:
            pad_style_combo.addItem(label, key)
        for i, (key, _l) in enumerate(_PAD_STYLES):
            if key == self.pad_style:
                pad_style_combo.setCurrentIndex(i)
                break
        form.addRow("Pad-Stil:", pad_style_combo)

        # Zweite Wechselfarbe (nur Pad-Stil = "Zwei Farben im Wechsel").
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtWidgets import QColorDialog
        _pad2 = {"rgb": tuple(self.pad_color2)}
        pad_color2_btn = QPushButton()

        def _refresh_pad2_btn():
            r, g, b = _pad2["rgb"]
            pad_color2_btn.setText(f"RGB {r},{g},{b}")
            pad_color2_btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: #fff;")

        def _pick_pad2():
            r, g, b = _pad2["rgb"]
            c = QColorDialog.getColor(QColor(r, g, b), dlg, "Zweite Pad-Farbe")
            if c.isValid():
                _pad2["rgb"] = (c.red(), c.green(), c.blue())
                _refresh_pad2_btn()

        _refresh_pad2_btn()
        pad_color2_btn.clicked.connect(_pick_pad2)
        pad_color2_btn.setToolTip("Zweite Farbe für Pad-Stil 'Zwei Farben im Wechsel'.")
        form.addRow("2. Pad-Farbe (Wechsel):", pad_color2_btn)

        # BTN-01: zusaetzliche Aktionen (Multi-Action) bearbeiten.
        _edited = {"list": [dict(a) for a in self.actions]}
        actions_btn = QPushButton(f"Mehrfach-Aktionen… ({len(self.actions)})")

        def _edit_actions():
            from src.ui.widgets.multi_action_dialog import MultiActionDialog
            d2 = MultiActionDialog(_edited["list"], dlg)
            if d2.exec() == QDialog.DialogCode.Accepted:
                _edited["list"] = d2.get_actions()
                actions_btn.setText(f"Mehrfach-Aktionen… ({len(_edited['list'])})")

        actions_btn.clicked.connect(_edit_actions)
        form.addRow("Zusatz-Aktionen:", actions_btn)

        # ── Kontextabhängige Feld-Sichtbarkeit ──
        # Zeigt je Aktion nur die passenden Felder (statt immer alle ~12 Zeilen).
        # Caption/Aktion/MIDI/Pad bleiben immer sichtbar.
        FT, FF = ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH
        EA, SG = ButtonAction.EFFECT_ACTION, ButtonAction.SELECT_GROUP
        LS, SN = ButtonAction.LIBRARY_SNAP, ButtonAction.SNAPSHOT
        TG, FL = ButtonAction.TOGGLE, ButtonAction.FLASH

        def _update_field_visibility():
            a = act.currentData()        # roher Enum-Wert (str)
            func_like = a in (FT, FF, EA, TG, FL)
            vis = {
                slot:            func_like,
                func_combo:      func_like,
                snap_combo:      a == SN,
                lib_combo:       a == LS,
                snap_mode_combo: a == LS,
                eff_action_combo: a == EA,
                group_combo:     a == SG,
                edit_slot_edit:  a in (FT, FF, EA),
                exclusive_cb:    a in (FT, FF),
                solo_fix_cb:     a in (FT, FF),
                clear_prog_cb:   a in (FT, FF),
                pad_color2_btn:  self.pad_style == "alternate" or
                                 pad_style_combo.currentData() == "alternate",
            }
            for widget, show in vis.items():
                form.setRowVisible(widget, bool(show))

        act.currentIndexChanged.connect(lambda _i: _update_field_visibility())
        pad_style_combo.currentIndexChanged.connect(lambda _i: _update_field_visibility())
        _update_field_visibility()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.action = ButtonAction(act.currentData() or self.action.value)
            try:
                _fid = int(slot.text())
                self.function_id = _fid if _fid >= 0 else None
            except ValueError:
                self.function_id = None
            snap_idx = snap_combo.currentData()
            self.snapshot_index = snap_idx if snap_idx >= 0 else None
            lib_id = lib_combo.currentData()
            self.snap_id = lib_id if lib_id is not None and lib_id >= 0 else None
            self.snap_mode = snap_mode_combo.currentData() or "toggle"
            self._snap_active = False
            self._snap_prev = {}
            self.effect_action_key = eff_action_combo.currentData() or self.effect_action_key
            self.group_name = group_combo.currentText().strip()
            self.edit_slot = edit_slot_edit.text().strip()
            self.midi_type = midi_type_combo.currentText()
            self.midi_ch = midi_ch_spin.value()
            self.midi_data1 = midi_note_spin.value()
            self.pad_style = pad_style_combo.currentData() or "mirror"
            self.pad_color2 = tuple(_pad2["rgb"])
            self.exclusive = exclusive_cb.isChecked()
            self.solo_fixtures = solo_fix_cb.isChecked()
            self.clear_programmer = clear_prog_cb.isChecked()
            self.actions = _edited["list"]
            self.update()

    def _populate_function_combo(self, combo: QComboBox):
        """Listet alle Funktionen (Chases/Sequences/Scenes...) nach Namen auf."""
        try:
            from src.core.app_state import get_state
            funcs = get_state().function_manager.all()
            for f in sorted(funcs, key=lambda x: (x.name or "").lower()):
                ftype = getattr(f.function_type, "value", str(f.function_type))
                combo.addItem(f"{f.name}  [{ftype} #{f.id}]", int(f.id))
        except Exception as e:
            print(f"[VCButton] function combo error: {e}")

    def _populate_snapshot_combo(self, combo: QComboBox):
        try:
            with open(_SNAPSHOTS_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, list):
                return
            for i, s in enumerate(payload):
                if s and s.get("values"):
                    name = s.get("name") or f"Snap {i + 1}"
                    combo.addItem(f"{i + 1}: {name}", i)
        except Exception:
            pass

    def _populate_library_combo(self, combo: QComboBox):
        """Listet die Snaps der Show-Bibliothek (Farben/Looks) nach Ordner+Name."""
        try:
            from src.core.engine.snap_library import get_snap_library
            for s in get_snap_library().snaps_sorted():
                label = f"{s.folder}/{s.name}" if s.folder else s.name
                combo.addItem(label, int(s.id))
        except Exception as e:
            print(f"[VCButton] library combo error: {e}")

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["action"] = self.action.value
        d["function_id"] = self.function_id
        d["snapshot_index"] = self.snapshot_index
        d["snap_id"] = self.snap_id
        d["snap_mode"] = self.snap_mode
        d["effect_action_key"] = self.effect_action_key
        d["group_name"] = self.group_name
        d["edit_slot"] = self.edit_slot
        d["actions"] = [dict(a) for a in self.actions]
        d["exclusive"] = self.exclusive
        d["solo_fixtures"] = self.solo_fixtures
        d["clear_programmer"] = self.clear_programmer
        d["pad_style"] = self.pad_style
        d["pad_color2"] = list(self.pad_color2)
        d["midi_ch"] = self.midi_ch
        d["midi_data1"] = self.midi_data1
        d["midi_type"] = self.midi_type
        d["key_binding"] = self.key_binding
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.action = ButtonAction(d.get("action", "Toggle"))
        self.function_id = d.get("function_id")
        self.snapshot_index = d.get("snapshot_index")
        self.snap_id = d.get("snap_id")
        self.snap_mode = d.get("snap_mode", "toggle")
        self.effect_action_key = d.get("effect_action_key", "next_color")
        self.group_name = d.get("group_name", "")
        self.edit_slot = d.get("edit_slot", "")
        self.actions = [dict(a) for a in d.get("actions", []) if isinstance(a, dict)]
        self.exclusive = bool(d.get("exclusive", False))
        self.solo_fixtures = bool(d.get("solo_fixtures", False))
        self.clear_programmer = bool(d.get("clear_programmer", False))
        self.pad_style = d.get("pad_style", "mirror")
        c2 = d.get("pad_color2", [0, 0, 255])
        self.pad_color2 = tuple(c2) if isinstance(c2, (list, tuple)) and len(c2) == 3 else (0, 0, 255)
        self.midi_ch = d.get("midi_ch", 0)
        self.midi_data1 = d.get("midi_data1", -1)
        self.midi_type = d.get("midi_type", "note_on")
        self.key_binding = d.get("key_binding", "") or ""

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

# Quadratische Standard-Groesse fuer NEU angelegte Buttons (Pad-Look wie im
# Demo-Show-Generator, PAD=56 → hier etwas grosszuegiger fuer Hand-Platzierung).
# GRID-aligned (8 px) damit der Button beim Anlegen sauber einrastet. Bestehende
# Shows laden ihre eigene Geometrie aus to_dict → unveraendert (nur Neuanlage).
DEFAULT_BUTTON_SIZE = 72


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
    # WP-8: BPM-Manager live ueber Pads/MIDI steuern. Werte explizit (str-Enum) →
    # to_dict/from_dict funktionieren by-NAME wie by-VALUE, Reihenfolge egal.
    BPM_NUDGE_UP   = "BpmNudgeUp"     # Tempo um +1 BPM nachziehen (→ MANUAL)
    BPM_NUDGE_DOWN = "BpmNudgeDown"   # Tempo um -1 BPM nachziehen (→ MANUAL)
    BPM_MODE_TOGGLE = "BpmModeToggle" # Betriebsart AUTO ↔ MANUAL umschalten
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
    # Tempo-Sync Phase 5: benannte Tempo-Buses (A/B/C/D) live steuern. Wirken ueber
    # tempo_bus_id auf get_tempo_bus_manager().resolve(bus) — unabhaengig vom globalen
    # BPM-Leader (TAP/AUDIO_BPM bleiben global).
    TAP_BUS  = "TapBus"      # Tap-Tempo auf einen benannten Bus
    SYNC_BUS = "SyncBus"     # Bus re-ankern + Downbeat ("jetzt ist die Eins")
    ARM_BUS  = "ArmBus"      # Bus scharf schalten (armed_bus_id) fuer Pads/MIDI
    # ── Farb-/Effekt-VC (F3): globale Show-Aktionen ───────────────────────────
    ALL_WHITE    = "AllWhite"     # Moment-Override: alles weiss 100% (nur gehalten); flasht die gebundene Weiss-Szene
    FREEZE       = "Freeze"       # BPM einfrieren (alle Buses + globaler Leader -> 0), Toggle; bus-gekoppelte Effekte halten (F5)
    STOP_EFFECTS = "StopEffects"  # alle laufenden Effekt-Funktionen stoppen (Tempo/BPM bleiben) -> Pause/Effekt-Stop
    AUTO_SYNC    = "AutoSync"     # Auto-Sync an/aus: neu startende bus-gekoppelte Effekte phasengleich am gemeinsamen Beat-Raster


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
    (ButtonAction.STOP_EFFECTS,    "Effekte stoppen (Tempo bleibt)"),
    (ButtonAction.BLACKOUT,        "Blackout"),
    (ButtonAction.ALL_WHITE,       "Alles Weiß (gehalten)"),
    (ButtonAction.FREEZE,          "Freeze (BPM einfrieren)"),
    (ButtonAction.AUTO_SYNC,       "Auto-Sync an/aus"),
    (ButtonAction.TAP,             "Tap-Tempo"),
    (ButtonAction.AUDIO_BPM,       "Musik-BPM"),
    (ButtonAction.BPM_NUDGE_UP,    "BPM +1 (Nudge)"),
    (ButtonAction.BPM_NUDGE_DOWN,  "BPM -1 (Nudge)"),
    (ButtonAction.BPM_MODE_TOGGLE, "BPM-Modus AUTO/MANUAL"),
    (ButtonAction.TAP_BUS,         "Tap-Tempo (Bus)"),
    (ButtonAction.SYNC_BUS,        "Sync (Bus)"),
    (ButtonAction.ARM_BUS,         "Bus scharf schalten"),
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
        # Phase E (Multi-Effekt): weitere gekoppelte Effekt-IDs. FUNCTION_TOGGLE/
        # FUNCTION_FLASH wirken auf function_id + alle function_ids. Leer =
        # klassischer Ein-Funktions-Button (vollstaendig rueckwaertskompatibel).
        self.function_ids: list[int] = []
        self.snapshot_index: int | None = None
        # Bibliothek-Snap (ButtonAction.LIBRARY_SNAP): Referenz auf einen Snap der
        # Show-Bibliothek (src.core.engine.snap_library) + Tastenverhalten.
        self.snap_id: int | None = None
        # Weitere Bibliothek-Snaps, die gemeinsam mit snap_id geschaltet werden.
        # Analog function_ids: snap_id bleibt das Primaerziel, snap_ids sind Extras.
        self.snap_ids: list[int] = []
        self.snap_mode: str = "toggle"      # "set" | "flash" | "toggle"
        self._snap_active: bool = False     # Laufzeit-Zustand fuer toggle
        # Vorherige Programmer-Werte (fuer Toggle/Flash-Ruecknahme):
        # {(fid, attr): alter_wert_oder_None}
        self._snap_prev: dict[tuple[int, str], int | None] = {}
        # Phase 6: Effekt-Aktions-Name fuer ButtonAction.EFFECT_ACTION.
        self.effect_action_key: str = "next_color"
        # F-24: Gruppenname fuer ButtonAction.SELECT_GROUP.
        self.group_name: str = ""
        # Tempo-Sync Phase 5: Ziel-Bus fuer TAP_BUS/SYNC_BUS/ARM_BUS ("" = aktiver/Default-Bus).
        self.tempo_bus_id: str = ""
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
        # Welle 4 (O): Long-Press im Live-Modus oeffnet den Effekt-Mini-Editor
        # (deferred apply). Pro Button schaltbar (Flash-Buttons sollen es nicht haben).
        self.long_press_editor: bool = False
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
        # Long-Press-Timer (Welle 4, O): feuert nach ~500 ms gedrueckt-halten.
        from PySide6.QtCore import QTimer
        self._lp_timer = QTimer(self)
        self._lp_timer.setSingleShot(True)
        self._lp_timer.setInterval(500)
        self._lp_timer.timeout.connect(self._open_live_mini_editor)
        self._live_editor = None
        self._bg_color = QColor("#1a3a5c")
        self._fg_color = QColor("#ffffff")

        # Farb-Vorschau-Badge (oben rechts): zeigt die Farbe(n) des gebundenen
        # Farb-Effekts/-Snaps. Mehrere Farben (Farbwechsel) => Eck-Icon wechselt
        # zyklisch durch (animiert). Aufloesung pro Bindung gecacht (paintEvent
        # laeuft oft); Timer nur aktiv, solange das Widget sichtbar UND mehrfarbig
        # ist (off-bank/einfarbig = keine CPU).
        self._badge_colors: list[QColor] = []
        self._badge_cache_key = None
        self._badge_index = 0
        self._badge_timer = QTimer(self)
        self._badge_timer.setInterval(900)   # ~0.9 s pro Farbe
        self._badge_timer.timeout.connect(self._advance_badge)

        self.resize(DEFAULT_BUTTON_SIZE, DEFAULT_BUTTON_SIZE)

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

    def _all_function_ids(self) -> list[int]:
        """Phase E: alle gekoppelten Funktions-IDs (function_id + function_ids),
        function_id zuerst, dedupliziert. Leer = keine Bindung."""
        ids: list[int] = []
        if self.function_id is not None:
            ids.append(int(self.function_id))
        for i in self.function_ids:
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if iv not in ids:
                ids.append(iv)
        return ids

    def _all_snap_ids(self) -> list[int]:
        """Alle gekoppelten Bibliothek-Snap-IDs (snap_id + snap_ids),
        snap_id zuerst, dedupliziert. Leer = keine Snap-Bindung."""
        ids: list[int] = []
        if self.snap_id is not None:
            try:
                ids.append(int(self.snap_id))
            except (TypeError, ValueError):
                pass
        for i in self.snap_ids:
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if iv not in ids:
                ids.append(iv)
        return ids

    @staticmethod
    def _snap_binding_for_action(action, sids):
        """snap_id/snap_ids fuer eine Aktion bestimmen: nur LIBRARY_SNAP traegt
        Snaps, jede andere Aktion -> (None, []). VCB-31: verhindert ein stale
        snap_id, das beim Wechsel WEG von LIBRARY_SNAP sonst in to_dict/Trigger
        zurueckbliebe (Show-Serialisierung mit Phantom-ID)."""
        if action == ButtonAction.LIBRARY_SNAP:
            ids = list(sids or [])
            return (ids[0] if ids else None, ids[1:])
        return (None, [])

    def _start_function_group(self, state, fids: list[int]):
        """Startet alle gebundenen Funktionen als atomare Button-Gruppe.

        Startregeln wie Edit-Slot, Exklusivitaet und Geraete-Solo werden einmal
        auf die gesamte Gruppe angewendet. Sonst wuerde der zweite Effekt den
        gerade gestarteten ersten Effekt sofort wieder stoppen.
        """
        fm = state.function_manager

        if self.clear_programmer:
            try:
                state.clear_programmer()
            except Exception:
                pass

        # EFX-Ziele vor der Konfliktpruefung automatisch mit Moving-Heads
        # belegen. Erst dann kennt Geraete-Solo ihre tatsaechlichen Fixtures.
        for fid in fids:
            try:
                fn = fm.get(fid)
                if (fn is not None and hasattr(fn, "assign_movers_auto")
                        and not getattr(fn, "fixtures", None)):
                    fn.assign_movers_auto(allow_all=True)
            except Exception:
                pass

        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                previous = effect_live.get_edit_target(self.edit_slot)
                if (previous is not None and previous not in fids
                        and fm.is_running(previous)):
                    fm.stop(previous)
            except Exception:
                pass
        elif self.exclusive:
            try:
                fm.stop_all()
            except Exception:
                pass

        if self.solo_fixtures:
            try:
                stop_group = getattr(fm, "stop_others_sharing_fixture_group", None)
                if callable(stop_group):
                    stop_group(fids)
                else:
                    for fid in fids:
                        fm.stop_others_sharing_fixtures(fid)
            except Exception:
                pass

        for fid in fids:
            fm.start(fid)
            try:
                problem = fm.start_problem(fid)
            except Exception:
                problem = None
            if problem:
                self._show_status(problem)

        # Ein Edit-Slot kann genau ein Live-Bearbeitungsziel halten. Bei einer
        # Gruppe ist das erste erfolgreich gestartete Ziel der stabile Master.
        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                edit_fid = next((fid for fid in fids if fm.is_running(fid)), None)
                effect_live.set_edit_target(self.edit_slot, edit_fid)
            except Exception:
                pass

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
            # VCB-09: auch negativen Index abfangen — sonst laedt payload[-1] den
            # letzten Snapshot statt abzubrechen.
            if not isinstance(payload, list) or not (0 <= index < len(payload)):
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

    def _library_snaps(self) -> list:
        """Alle referenzierten Bibliothek-Snaps in Schalt-Reihenfolge."""
        ids = self._all_snap_ids()
        if not ids:
            return []
        out: list = []
        try:
            from src.core.engine.snap_library import get_snap_library
            lib = get_snap_library()
            for sid in ids:
                snap = lib.get(int(sid))
                if snap is not None:
                    out.append(snap)
        except Exception as e:
            print(f"[VCButton] Snap-Gruppen-Lookup-Fehler: {e}")
        return out

    def _apply_library_snap(self):
        """Schreibt die Werte der Bibliothek-Snaps in den Programmer und merkt
        sich die vorherigen Werte, damit Toggle/Flash sie zuruecknehmen koennen."""
        snaps = self._library_snaps()
        if not snaps:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            self._snap_prev = {}
            for snap in snaps:
                for fid, attrs in snap.values.items():
                    for attr, val in attrs.items():
                        fid_i = int(fid)
                        key = (fid_i, attr)
                        if key not in self._snap_prev:
                            self._snap_prev[key] = state.get_programmer_value(fid_i, attr)
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

    def deactivate_for_solo(self):
        """Schaltet diesen Button fuer einen Solo-Frame gezielt aus.

        ``_pressed`` beschreibt nur den physischen Tastendruck. Toggle-Buttons
        bleiben dagegen ueber den laufenden Effekt bzw. ``_snap_active`` aktiv.
        Ein blosses ``_trigger(False)`` kann diese Zustaende nicht beenden, weil
        FUNCTION_TOGGLE und Library-Snap-Toggle nur auf den Druck reagieren.
        """
        was_pressed = self._pressed
        self._pressed = False

        if self.action in (ButtonAction.FUNCTION_TOGGLE,
                           ButtonAction.FUNCTION_FLASH):
            try:
                from src.core.app_state import get_state
                fm = get_state().function_manager
                for fid in self._all_function_ids():
                    if fm.is_running(fid):
                        # Solo bedeutet wirklich nur ein aktiver Button. Ein
                        # Fade-Out duerfte den alten Effekt sonst parallel zum
                        # neu gestarteten weiterlaufen lassen.
                        fm.stop(fid, allow_release=False)
            except Exception:
                pass
        elif self.action == ButtonAction.LIBRARY_SNAP:
            if self._snap_active or was_pressed:
                self._restore_library_snap()
            self._snap_active = False
        elif was_pressed:
            # Moment-Aktionen wie Blackout, AllWhite, Executor-Flash usw.
            # benoetigen ihr normales Release, wenn waehrend des Haltens ein
            # anderer Button im Solo-Frame gedrueckt wird.
            try:
                self._trigger_primary(False)
            except Exception:
                pass

        self.update()

    def _snap_swatch_color(self) -> QColor | None:
        """Repraesentative Farbe des Snaps (erstes Fixture mit Farbe) fuer die Kachel.

        Faltet ueber ``display_rgb_from_attrs`` den Weiss-Kanal (RGBW) additiv in
        die Anzeige-RGB — reines Weiss (``color_w=255``, RGB=0) wird damit **weiss**
        statt schwarz (frueher las diese Methode nur ``color_r/g/b``)."""
        from src.core.color_utils import display_rgb_from_attrs
        for snap in self._library_snaps():
            for attrs in snap.values.values():
                rgb = display_rgb_from_attrs(attrs)
                if rgb is not None:
                    return QColor(*rgb)
        return None

    # ── Farb-Vorschau-Badge (oben rechts) ────────────────────────────────────
    def _color_badge_colors(self) -> list:
        """Anzeige-Farben des gebundenen Farb-Effekts/-Snaps (gecacht pro Bindung).

        Eine Farbe => einfarbiges Badge; mehrere => Farbwechsel (animiert). Leer =>
        kein Badge (Button steuert keine Farbe)."""
        # UI-14: Die ColorSequence eines gebundenen Farb-Effekts kann LIVE geaendert
        # werden (VCColor EFFECT/EFFECT_ADD, add_color/toggle_color ueber
        # effect_live), OHNE dass sich Bindung (action/snap_ids/function_id) aendert.
        # Eine Signatur der aktuellen Effekt-Farben in den Cache-Key aufnehmen, sonst
        # liefert der Cache (auch in showEvent) das alte _badge_colors zurueck und
        # das Badge zeigt entfernte/alte Farben + falschen Cycle-Zustand bis zum
        # naechsten Bindungswechsel.
        sig = None
        if (self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                            ButtonAction.EFFECT_ACTION)
                and self.function_id is not None):
            try:
                from src.core.engine import effect_live
                seq = effect_live.get_param("colors", int(self.function_id))
                if seq is not None and hasattr(seq, "enabled_colors"):
                    sig = tuple(tuple(int(x) for x in c)
                                for c in seq.enabled_colors())
                elif isinstance(seq, (list, tuple)):
                    sig = tuple(tuple(c) for c in seq
                                if isinstance(c, (list, tuple)))
            except Exception:
                sig = None
        key = (self.action, tuple(self._all_snap_ids()), self.function_id, sig)
        if getattr(self, "_badge_cache_key", None) == key:
            return self._badge_colors
        cols = self._resolve_badge_colors()
        self._badge_cache_key = key
        self._badge_colors = cols
        if self._badge_index >= len(cols):
            self._badge_index = 0
        self._sync_badge_timer()
        return cols

    def _resolve_badge_colors(self) -> list:
        """Loest die Vorschau-Farben auf: aus Bibliothek-Snaps (LIBRARY_SNAP, mit
        W-Faltung) oder aus der Color-Sequence eines gebundenen Farb-Effekts
        (FUNCTION_TOGGLE/FLASH/EFFECT_ACTION). Nicht-farbige Effekte (Dimmer-/
        Shutter-Style → ``has_colors=False``) liefern bewusst KEIN Badge."""
        out: list = []
        seen: set = set()

        def _push(qc: QColor):
            n = qc.name()
            if n not in seen:
                seen.add(n)
                out.append(qc)

        try:
            from src.core.color_utils import display_rgb_from_attrs
            if self.action == ButtonAction.LIBRARY_SNAP:
                for snap in self._library_snaps():
                    for attrs in snap.values.values():
                        rgb = display_rgb_from_attrs(attrs)
                        if rgb is not None:
                            _push(QColor(*rgb))
            elif (self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                                  ButtonAction.EFFECT_ACTION)
                  and self.function_id is not None):
                fid = int(self.function_id)
                # Nur fuer Effekte, die wirklich Farbe steuern (Style-Guard spiegeln).
                from src.ui.virtualconsole.vc_effect_meta import function_capabilities
                caps = function_capabilities(fid)
                if not getattr(caps, "has_colors", False):
                    return []
                from src.core.engine import effect_live
                seq = effect_live.get_param("colors", fid)
                rgbs = []
                if seq is not None and hasattr(seq, "enabled_colors"):
                    rgbs = list(seq.enabled_colors())
                elif isinstance(seq, (list, tuple)):
                    rgbs = [c for c in seq
                            if isinstance(c, (list, tuple)) and len(c) >= 3]
                for rgb in rgbs:
                    _push(QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])))
        except Exception:
            return []
        return out[:8]   # mehr als 8 Zyklus-Farben braucht das Eck-Icon nicht

    def _sync_badge_timer(self):
        """Cycle-Timer nur laufen lassen, wenn sichtbar UND mehrfarbig."""
        multi = len(self._badge_colors) > 1
        if multi and self.isVisible():
            if not self._badge_timer.isActive():
                self._badge_timer.start()
        else:
            if self._badge_timer.isActive():
                self._badge_timer.stop()
            if not multi:
                self._badge_index = 0

    def _advance_badge(self):
        n = len(self._badge_colors)
        if n <= 1:
            self._badge_timer.stop()
            return
        self._badge_index = (self._badge_index + 1) % n
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # Beim Sichtbarwerden (Bank-Wechsel) Farben frisch aufloesen + Timer steuern.
        self._color_badge_colors()
        self._sync_badge_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._badge_timer.isActive():
            self._badge_timer.stop()

    def _gobo_icon(self):
        """Gobo-Icon (QPixmap) wenn dieser Button einen Gobo setzt, sonst None.

        Erkennt Gobos aus einem Bibliothek-Snap (LIBRARY_SNAP) ODER einer Szene
        (FUNCTION_TOGGLE/FLASH): findet einen ``gobo_wheel``-Wert, schlaegt im
        Fixture-Profil den Range-Namen nach und zeichnet ihn ueber gobo_icons.
        Ergebnis wird pro Bindung gecacht (paintEvent laeuft oft)."""
        key = (self.action, tuple(self._all_snap_ids()), self.function_id)
        if getattr(self, "_gobo_cache_key", None) == key:
            return getattr(self, "_gobo_cache_pm", None)
        pm = self._resolve_gobo_icon()
        self._gobo_cache_key = key
        self._gobo_cache_pm = pm
        return pm

    def _resolve_gobo_icon(self):
        cands: list[tuple[int, int]] = []   # (fid, gobo_wheel-Wert)
        try:
            if self.action == ButtonAction.LIBRARY_SNAP:
                for snap in self._library_snaps():
                    for fid, attrs in snap.values.items():
                        if "gobo_wheel" in attrs:
                            cands.append((int(fid), int(attrs["gobo_wheel"])))
            elif (self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH)
                  and self.function_id is not None):
                from src.core.app_state import get_state, get_channels_for_patched
                from src.core.engine.scene import Scene
                st = get_state()
                fn = st.function_manager.get(int(self.function_id))
                if isinstance(fn, Scene):
                    fxs = {f.fid: f for f in st.get_patched_fixtures()}
                    for sv in fn.values:
                        fx = fxs.get(sv.fixture_id)
                        if fx is None:
                            continue
                        ch = next((c for c in get_channels_for_patched(fx)
                                   if c.channel_number == sv.channel), None)
                        if ch is not None and (ch.attribute or "") == "gobo_wheel":
                            cands.append((sv.fixture_id, int(sv.value)))
            if not cands:
                return None
            from src.core.app_state import get_state, get_channels_for_patched
            from src.ui.widgets.gobo_icons import gobo_pixmap_for_name, gobo_style_for
            st = get_state()
            fxs = {f.fid: f for f in st.get_patched_fixtures()}
            for fid, val in cands:
                fx = fxs.get(fid)
                if fx is None:
                    continue
                gch = next((c for c in get_channels_for_patched(fx)
                            if (c.attribute or "") == "gobo_wheel"), None)
                if gch is None:
                    continue
                rng = next((r for r in getattr(gch, "ranges", [])
                            if r.range_from <= val <= r.range_to), None)
                if rng is None or (getattr(rng, "kind", "") or "") not in ("gobo", "shake", "rotate"):
                    continue
                if not gobo_style_for(rng.name):   # nur echte Muster (kein "offen")
                    continue
                pm = gobo_pixmap_for_name(rng.name, size=26)
                if pm is not None and not pm.isNull():
                    return pm
        except Exception:
            return None
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

        if self.action == ButtonAction.STOP_EFFECTS:
            # F3: Effekte aus, aber Tempo/BPM bleiben (Pause / Effekt-Stop).
            if press:
                try:
                    state.function_manager.stop_all()
                except Exception:
                    pass
            return

        if self.action == ButtonAction.ALL_WHITE:
            # F3: Moment-Override "alles weiss 100%". Blitzt die gebundene
            # (hochpriore) Weiss-Szene; beim Loslassen zurueck. Korrekt pro Gerät
            # (PAR/Spider RGBW, MH Farbrad-Weiss) -> die Szene weiss das, nicht der Button.
            fids = self._all_function_ids()
            if fids:
                fm = state.function_manager
                if press:
                    for fid in fids:
                        fm.start(fid)
                else:
                    for fid in fids:
                        fm.stop(fid)
            return

        if self.action == ButtonAction.FREEZE:
            # F3: Tempo einfrieren — alle Buses + globaler Leader auf 0 (Toggle).
            # Bus-gekoppelte Effekte halten dann ihre Position (F5).
            if press:
                try:
                    from src.core.engine.tempo_bus import get_tempo_bus_manager
                    get_tempo_bus_manager().toggle_freeze()
                except Exception as e:
                    print(f"[VCButton] freeze error: {e}")
                self.update()
            return

        if self.action == ButtonAction.AUTO_SYNC:
            # Auto-Sync an/aus (Toggle): neu startende bus-gekoppelte Effekte uebernehmen
            # den gemeinsamen Beat-Raster-Ursprung -> phasengleicher Start, egal wann.
            if press:
                try:
                    from src.core.engine.tempo_bus import get_tempo_bus_manager
                    m = get_tempo_bus_manager()
                    m.set_auto_sync(not m.auto_sync)
                except Exception as e:
                    print(f"[VCButton] auto-sync toggle error: {e}")
                self.update()
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

        if self.action in (ButtonAction.TAP_BUS, ButtonAction.SYNC_BUS,
                           ButtonAction.ARM_BUS):
            # Tempo-Sync Phase 5: auf einen benannten Tempo-Bus wirken.
            if press:
                try:
                    from src.core.engine.tempo_bus import get_tempo_bus_manager
                    mgr = get_tempo_bus_manager()
                    if self.action == ButtonAction.ARM_BUS:
                        mgr.armed_bus_id = self.tempo_bus_id
                    else:
                        bus = mgr.resolve(self.tempo_bus_id)
                        if bus is not None:
                            if self.action == ButtonAction.TAP_BUS:
                                bus.tap()
                            else:
                                bus.sync(reset_downbeat=True)
                except Exception as e:
                    print(f"[VCButton] tempo-bus action error: {e}")
                self.update()
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

        if self.action in (ButtonAction.BPM_NUDGE_UP, ButtonAction.BPM_NUDGE_DOWN):
            # WP-8: Tempo manuell nachziehen (+/-1 BPM → MANUAL). Kein
            # per-Button-Schritt vorhanden, daher fester Default d = 1.0.
            if press:
                try:
                    from src.core.engine.bpm_manager import get_bpm_manager
                    d = 1.0 if self.action == ButtonAction.BPM_NUDGE_UP else -1.0
                    get_bpm_manager().nudge(d)
                except Exception as e:
                    print(f"[VCButton] bpm-nudge error: {e}")
            return

        if self.action == ButtonAction.BPM_MODE_TOGGLE:
            # WP-8: Betriebsart AUTO ↔ MANUAL umschalten.
            if press:
                try:
                    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
                    mgr = get_bpm_manager()
                    new_mode = BpmMode.MANUAL if mgr.mode == BpmMode.AUTO else BpmMode.AUTO
                    mgr.set_mode(new_mode)
                except Exception as e:
                    print(f"[VCButton] bpm-mode toggle error: {e}")
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
                    fids = self._all_function_ids()
                    if fids:
                        for fid in fids:
                            effect_live.do_action(self.effect_action_key, fid)
                        return
                    fid = None
                    if self.edit_slot:
                        fid = effect_live.get_edit_target(self.edit_slot)
                    effect_live.do_action(self.effect_action_key, fid)
                except Exception:
                    pass
            return

        if self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            fids = self._all_function_ids()
            if not fids:
                return
            fm = state.function_manager

            if self.action == ButtonAction.FUNCTION_TOGGLE:
                # Laeuft irgendein Gruppenmitglied, schaltet der naechste Druck
                # die komplette Gruppe aus. Nur eine komplett inaktive Gruppe
                # wird gemeinsam gestartet.
                if press:
                    if any(fm.is_running(fid) for fid in fids):
                        for fid in fids:
                            if fm.is_running(fid):
                                fm.stop(fid)
                    else:
                        self._start_function_group(state, fids)
            else:  # FUNCTION_FLASH
                if press:
                    self._start_function_group(state, fids)
                else:
                    for fid in fids:
                        fm.stop(fid)
            return

        if self.function_id is None:
            return
        slot = self.function_id
        executors = state.playback_engine.executors
        # VCB-08: negativer slot (z. B. aus korrupter Show) wuerde sonst executors[-1]
        # (den letzten Executor) treffen statt zu stoppen.
        if slot < 0 or slot >= len(executors):
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
            self._maybe_arm_long_press()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._lp_timer.stop()           # kurzer Tap -> Long-Press abbrechen
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._trigger(False)
            self.update()
        event.accept()

    # ── Live-Mini-Editor (Welle 4, O): Long-Press im Live-Modus ───────────────

    def _maybe_arm_long_press(self):
        """Startet den Long-Press-Timer, wenn dieser Button das Editor-Oeffnen
        erlaubt (pro-Button-Flag) UND einen Effekt steuert. Nur Toggle/Effekt-
        Aktion — bei FLASH wuerde Halten mit dem Flash kollidieren."""
        if (self.long_press_editor
                and self.action in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.EFFECT_ACTION)
                and self.live_effect_function_id() is not None):
            self._lp_timer.start()

    def _open_live_mini_editor(self):
        """Timer-Callback: oeffnet den nicht-modalen Deferred-Apply-Editor fuer den
        gebundenen Effekt (Werte werden erst beim Klick auf „Anwenden" gesendet)."""
        fid = self.live_effect_function_id()
        if fid is None:
            ids = self._all_function_ids()
            fid = ids[0] if ids else None
        if fid is None:
            return
        try:
            from .vc_live_editor import VCLiveEditor
            ed = VCLiveEditor(int(fid), self)
            self._live_editor = ed       # Referenz halten (nicht-modal)
            ed.show()
            ed.raise_()
        except Exception:
            pass

    def _binding_unresolved(self) -> bool:
        """True, wenn dieser Funktions-Button auf eine ID zeigt, die der
        FunctionManager nicht (mehr) kennt — eine tote Bindung (z. B. Effekt
        geloescht/neu angelegt, Button behaelt die alte ID). Quelle des roten
        „ungebunden"-Markers im paintEvent. Nur Toggle/Flash mit gesetzter ID;
        bei Lookup-Fehlern defensiv False (kein Fehlalarm beim Laden)."""
        if self.action not in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH,
                               ButtonAction.EFFECT_ACTION, ButtonAction.ALL_WHITE):
            return False
        fids = self._all_function_ids()
        if not fids:
            return False
        try:
            from src.core.app_state import get_state
            fm = get_state().function_manager
            return any(fm.get(fid) is None for fid in fids)
        except Exception:
            return False

    def _show_status(self, msg: str, ms: int = 4000):
        """Kurzer Hinweis fuer den Nutzer — bevorzugt in der Statusleiste des
        Hauptfensters, sonst (Popout/ohne Statusleiste) als Log. Best effort,
        nie eine Exception nach aussen."""
        try:
            win = self.window()
            sb = win.statusBar() if hasattr(win, "statusBar") else None
            if sb is not None:
                sb.showMessage(f"⚠ {msg}", ms)
                return
        except Exception:
            pass
        print(f"[vc_button] {msg}")

    def _function_running(self) -> bool:
        """True, wenn dieser Button eine Funktion steuert, die gerade laeuft.
        Quelle der On-Screen-Rueckmeldung (Toggle-Pad bleibt beleuchtet, solange
        sein Effekt laeuft). Die VC-View repaintet den Button bei jedem Wechsel
        des Laufzustands (UI-Thread-Timer)."""
        if self.action not in (ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH):
            return False
        fids = self._all_function_ids()
        if not fids:
            return False
        try:
            from src.core.app_state import get_state
            fm = get_state().function_manager
            return any(fm.is_running(fid) for fid in fids)
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
        # VCI-01: Aktiv-Zustand der Tempo-Toggle-Pads sichtbar machen (analog AUDIO_BPM),
        # damit Freeze/Auto-Sync/BPM-Modus auf einen Blick erkennbar sind.
        action_on = False
        try:
            if self.action == ButtonAction.FREEZE:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                action_on = get_tempo_bus_manager().is_frozen()
            elif self.action == ButtonAction.AUTO_SYNC:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                action_on = bool(get_tempo_bus_manager().auto_sync)
            elif self.action == ButtonAction.BPM_MODE_TOGGLE:
                from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
                action_on = (get_bpm_manager().mode == BpmMode.MANUAL)
        except Exception:
            action_on = False
        # Laufzustand der gebundenen Funktion: ein Toggle-Pad bleibt „an", solange
        # sein Effekt laeuft — nicht nur waehrend des Drucks. Sonst sah es aus, als
        # liefe nichts mehr, obwohl die Geraete sich noch bewegten (Anzeige-Desync).
        func_on = self._function_running()
        lit = self._pressed or snap_on or audio_on or func_on or action_on
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
        elif action_on:
            # VCI-01: Tempo-Toggle aktiv (Freeze/Auto-Sync/BPM-Modus): amber Rahmen.
            p.setPen(QPen(QColor("#ffb000"), 2))
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

        # Gobo-Icon (oben rechts), wenn dieser Button einen Gobo setzt.
        _gpm = self._gobo_icon()
        if _gpm is not None and not _gpm.isNull():
            p.drawPixmap(self.width() - _gpm.width() - 4, 4, _gpm)

        # Farb-Vorschau-Badge (oben rechts): kleiner Kreis in der aktuellen
        # Effekt-/Snap-Farbe. Mehrere Farben (Farbwechsel) => der Kreis wechselt
        # zyklisch durch (Timer). Liegt schon ein Gobo oben rechts, wird das Badge
        # darunter gestapelt, damit beide sichtbar bleiben.
        _badge = self._color_badge_colors()
        if _badge:
            d = 16
            bx = self.width() - d - 4
            by = 4
            if _gpm is not None and not _gpm.isNull():
                by = 4 + _gpm.height() + 2
            idx = self._badge_index if self._badge_index < len(_badge) else 0
            cur = _badge[idx]
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor(0, 0, 0, 170), 1))   # dunkler Ring → helle Farben sichtbar
            p.setBrush(cur)
            p.drawEllipse(bx, by, d, d)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

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

        # Tote Bindung: zeigt der Button auf eine nicht (mehr) existierende
        # Funktions-ID, einen roten gestrichelten Rahmen + ⚠ zeichnen, damit der
        # Klick nicht still ins Leere geht (statt frustfreiem "passiert nichts").
        if self._binding_unresolved():
            pen = QPen(QColor("#ff5555"), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
            p.setPen(QColor("#ff5555"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(self.rect().adjusted(0, 2, -4, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "⚠")
            self.setToolTip(f"Funktion #{self.function_id} nicht gefunden — "
                            f"tote Bindung. Funktion neu zuweisen.")

        # BTN-01: Multi-Action-Indikator oben links (Anzahl Zusatz-Aktionen)
        if self.actions:
            p.fillRect(0, 0, 14, 10, QColor("#b388ff"))
            p.setPen(QColor("#000000"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRect(0, 0, 14, 10), Qt.AlignmentFlag.AlignCenter, f"+{len(self.actions)}")

        p.end()

    # ── Properties dialog ────────────────────────────────────────────────────

    def _build_settings(self, host, live=False):
        """Baut alle Eigenschafts-Felder + Apply-/Sichtbarkeits-Logik EINMAL und gibt
        eine Struktur zurueck, aus der sowohl der modale Dialog (``_open_properties``)
        als auch das Inspector-Panel (``build_inspector_body``) ihr Layout
        zusammensetzen. ``live=True`` = jede Aenderung wird sofort angewendet
        (Inspector); ``live=False`` = erst beim OK (modaler Dialog)."""
        from PySide6.QtWidgets import QPushButton, QColorDialog
        from .target_list_editor import TargetListEditor, SnapListEditor

        cap = QLineEdit(self.caption)

        act = QComboBox()
        for a, lbl in BUTTON_ACTION_LABELS:
            act.addItem(lbl, a.value)        # Label sichtbar, Enum-Wert als Data
        for i in range(act.count()):
            if act.itemData(i) == self.action.value:
                act.setCurrentIndex(i)
                break

        # HAUPTWEG: Funktion/Chase nach NAME auswaehlen; Roh-ID/Slot liegt unter „Erweitert".
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        slot.setToolTip("Roh-Function-ID bzw. Executor-Slot-Nummer (Aktion 'Executor'). "
                        "Normalerweise per Namen gewählt.")

        func_combo = QComboBox()
        func_combo.addItem("(per Erweitert / Roh-ID)", -1)
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

        extra_ids = QLineEdit(",".join(str(i) for i in self.function_ids))
        extra_ids.setToolTip("Weitere Funktions-IDs (Komma-getrennt) — Toggle/Flash "
                             "wirkt zusaetzlich auf diese Funktionen (als Gruppe).")

        target_editor = TargetListEditor(with_params=False, title="Schaltet mit")
        _t0 = ([int(self.function_id)] if self.function_id is not None else []) \
            + [int(i) for i in self.function_ids]
        target_editor.set_targets(_t0)
        target_editor.setToolTip("Funktionen/Effekte, die dieser Button schaltet — "
                                 "per Dropdown auswählen, mit ✕ entfernen, „+\" hinzufügen.")

        snap_combo = QComboBox()
        snap_combo.addItem("(keiner)", -1)
        self._populate_snapshot_combo(snap_combo)
        if self.snapshot_index is not None:
            for i in range(snap_combo.count()):
                if snap_combo.itemData(i) == self.snapshot_index:
                    snap_combo.setCurrentIndex(i)
                    break

        # Bibliothek-Snap (Aktion = LibrarySnap): der SnapListEditor verwaltet
        # Einzel- UND Mehrfach-Snaps; die fruehere, immer unsichtbare Einzel-Combo
        # (lib_combo) entfaellt (Audit-Bug: Einzel-Snap war nicht mehr waehlbar).
        snap_editor = SnapListEditor(title="Schaltet Snaps")
        snap_editor.set_targets(self._all_snap_ids())
        snap_editor.setToolTip("Bibliothek-Snaps/Looks, die dieser Button gemeinsam "
                               "setzt, flasht oder toggelt. Auch fuer einen einzelnen "
                               "Snap. Ideal fuer mehrere Strobe-Snaps verschiedener Gruppen.")

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

        bus_combo = QComboBox()
        for _bid, _blbl in (("", "(aktiver/Default-Bus)"), ("A", "Bus A"),
                            ("B", "Bus B"), ("C", "Bus C"), ("D", "Bus D")):
            bus_combo.addItem(_blbl, _bid)
        for i in range(bus_combo.count()):
            if bus_combo.itemData(i) == self.tempo_bus_id:
                bus_combo.setCurrentIndex(i)
                break
        bus_combo.setToolTip("Auf welchen Tempo-Bus Tap/Sync/Scharfschalten wirkt.")

        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext, z. B. MH oder MX). Beim Start "
                                  "wird dieser Effekt das Bearbeitungsziel des Slots; Fader/"
                                  "Farb-Kacheln mit demselben Slot bearbeiten ihn (pro Quadrant).")

        exclusive_cb = QCheckBox("Andere Funktionen stoppen (nur diese aktiv)")
        exclusive_cb.setChecked(self.exclusive)
        exclusive_cb.setToolTip("Beim Start dieser Funktion alle anderen laufenden "
                                "Funktionen stoppen (Solo). Nur FUNCTION-Aktionen.")
        solo_fix_cb = QCheckBox("Andere Effekte auf denselben Geräten stoppen")
        solo_fix_cb.setChecked(self.solo_fixtures)
        solo_fix_cb.setToolTip("Beim Start nur die Effekte stoppen, die DIESELBEN "
                               "Strahler benutzen (auch aus einer anderen Bank) — der "
                               "neue Effekt löst den alten auf diesen Geräten ab. "
                               "Effekte auf anderen Geräten laufen weiter. "
                               "Nur FUNCTION-Aktionen.")
        clear_prog_cb = QCheckBox("Programmer vorher leeren")
        clear_prog_cb.setChecked(self.clear_programmer)
        clear_prog_cb.setToolTip("Vor dem Start den Programmer leeren — manuelle "
                                 "Farben/Snaps haben sonst Vorrang und überdecken den "
                                 "Effekt. Nur FUNCTION-Aktionen.")

        midi_type_combo = QComboBox()
        midi_type_combo.addItems(["note_on", "cc"])
        midi_type_combo.setCurrentText(self.midi_type)
        midi_ch_spin = QSpinBox()
        midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch)
        midi_ch_spin.setSpecialValueText("Alle")
        midi_note_spin = QSpinBox()
        midi_note_spin.setRange(-1, 127)
        midi_note_spin.setValue(self.midi_data1)
        midi_note_spin.setSpecialValueText("keine")

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

        _pad2 = {"rgb": tuple(self.pad_color2)}
        pad_color2_btn = QPushButton()

        def _refresh_pad2_btn():
            r, g, b = _pad2["rgb"]
            pad_color2_btn.setText(f"RGB {r},{g},{b}")
            pad_color2_btn.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: #fff;")

        def _pick_pad2():
            r, g, b = _pad2["rgb"]
            c = QColorDialog.getColor(QColor(r, g, b), host, "Zweite Pad-Farbe")
            if c.isValid():
                _pad2["rgb"] = (c.red(), c.green(), c.blue())
                _refresh_pad2_btn()
                _live()

        _refresh_pad2_btn()
        pad_color2_btn.clicked.connect(_pick_pad2)
        pad_color2_btn.setToolTip("Zweite Farbe für Pad-Stil 'Zwei Farben im Wechsel'.")

        _edited = {"list": [dict(a) for a in self.actions]}
        actions_btn = QPushButton(f"Mehrfach-Aktionen… ({len(self.actions)})")

        def _edit_actions():
            from src.ui.widgets.multi_action_dialog import MultiActionDialog
            d2 = MultiActionDialog(_edited["list"], host)
            if d2.exec() == QDialog.DialogCode.Accepted:
                _edited["list"] = d2.get_actions()
                actions_btn.setText(f"Mehrfach-Aktionen… ({len(_edited['list'])})")
                _live()

        actions_btn.clicked.connect(_edit_actions)

        long_press_cb = QCheckBox("Lang drücken → Live-Einstellungen (erst Anwenden sendet)")
        long_press_cb.setChecked(self.long_press_editor)
        long_press_cb.setToolTip("Im Live-Modus den Button lange halten, um die Effekt-"
                                 "Parameter zu bearbeiten (deferred apply). Bei Flash sinnlos.")

        # ── Aktions-Konstanten (Sichtbarkeit) ──
        FT, FF = ButtonAction.FUNCTION_TOGGLE, ButtonAction.FUNCTION_FLASH
        EA, SG = ButtonAction.EFFECT_ACTION, ButtonAction.SELECT_GROUP
        LS, SN = ButtonAction.LIBRARY_SNAP, ButtonAction.SNAPSHOT
        TG, FL = ButtonAction.TOGGLE, ButtonAction.FLASH
        TB, SB, AB = ButtonAction.TAP_BUS, ButtonAction.SYNC_BUS, ButtonAction.ARM_BUS
        AW = ButtonAction.ALL_WHITE   # bindet die (hochpriore) Weiss-Szene wie ein Flash

        def apply():
            self.caption = cap.text() or self.caption
            self.action = ButtonAction(act.currentData() or self.action.value)
            try:
                _fid = int(slot.text())
                self.function_id = _fid if _fid >= 0 else None
            except ValueError:
                self.function_id = None
            _eids = []
            for part in extra_ids.text().split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    _eids.append(int(part))
                except ValueError:
                    pass
            self.function_ids = _eids
            # „Schaltet mit"-Liste hat Vorrang, wenn befuellt (nur Funktions-Aktionen).
            if self.action in (FT, FF, EA, AW):
                _tids = target_editor.ids()
                self.function_id = _tids[0] if _tids else None
                self.function_ids = _tids[1:]
            snap_idx = snap_combo.currentData()
            self.snapshot_index = snap_idx if snap_idx >= 0 else None
            # VCB-31: snap_id/snap_ids zentral aus der Aktion ableiten — bei einem
            # Wechsel WEG von LIBRARY_SNAP wird snap_id jetzt geleert (vorher blieb
            # es als Phantom-ID stehen und wanderte in to_dict).
            _sids = snap_editor.ids() if self.action == LS else []
            self.snap_id, self.snap_ids = self._snap_binding_for_action(self.action, _sids)
            self.snap_mode = snap_mode_combo.currentData() or "toggle"
            self._snap_active = False
            self._snap_prev = {}
            self.effect_action_key = eff_action_combo.currentData() or self.effect_action_key
            self.group_name = group_combo.currentText().strip()
            self.edit_slot = edit_slot_edit.text().strip()
            self.tempo_bus_id = bus_combo.currentData() or ""
            self.midi_type = midi_type_combo.currentText()
            self.midi_ch = midi_ch_spin.value()
            self.midi_data1 = midi_note_spin.value()
            self.pad_style = pad_style_combo.currentData() or "mirror"
            self.pad_color2 = tuple(_pad2["rgb"])
            self.exclusive = exclusive_cb.isChecked()
            self.solo_fixtures = solo_fix_cb.isChecked()
            self.clear_programmer = clear_prog_cb.isChecked()
            self.long_press_editor = long_press_cb.isChecked()
            self.actions = _edited["list"]
            self.update()

        def _live():
            if live:
                apply()

        def update_visibility(set_row_visible, set_section_visible=None):
            a = act.currentData()        # roher Enum-Wert (str)
            func_like = a in (FT, FF, EA, TG, FL, AW)
            target_editor.set_title("Aktion auf" if a == EA else "Schaltet mit")
            rows = {
                target_editor:    a in (FT, FF, EA, AW),
                snap_combo:       a == SN,
                snap_editor:      a == LS,
                snap_mode_combo:  a == LS,
                eff_action_combo: a == EA,
                group_combo:      a == SG,
                bus_combo:        a in (TB, SB, AB),
                edit_slot_edit:   a in (FT, FF, EA),
                exclusive_cb:     a in (FT, FF),
                solo_fix_cb:      a in (FT, FF),
                clear_prog_cb:    a in (FT, FF),
                long_press_cb:    a in (FT, EA),
                actions_btn:      True,
                pad_style_combo:  True,
                pad_color2_btn:   pad_style_combo.currentData() == "alternate",
                midi_type_combo:  True,
                midi_ch_spin:     True,
                midi_note_spin:   True,
            }
            for widget, show in rows.items():
                set_row_visible(widget, bool(show))
            if set_section_visible is not None:
                set_section_visible("advanced", func_like)

        # Live-Modus: jede Aenderung sofort anwenden (Inspector-Panel).
        if live:
            cap.textChanged.connect(lambda *_: _live())
            act.currentIndexChanged.connect(lambda *_: _live())
            slot.textChanged.connect(lambda *_: _live())
            extra_ids.textChanged.connect(lambda *_: _live())
            func_combo.currentIndexChanged.connect(lambda *_: _live())
            target_editor.changed.connect(lambda *_: _live())
            snap_combo.currentIndexChanged.connect(lambda *_: _live())
            snap_editor.changed.connect(lambda *_: _live())
            snap_mode_combo.currentIndexChanged.connect(lambda *_: _live())
            eff_action_combo.currentIndexChanged.connect(lambda *_: _live())
            group_combo.currentTextChanged.connect(lambda *_: _live())
            bus_combo.currentIndexChanged.connect(lambda *_: _live())
            edit_slot_edit.textChanged.connect(lambda *_: _live())
            exclusive_cb.toggled.connect(lambda *_: _live())
            solo_fix_cb.toggled.connect(lambda *_: _live())
            clear_prog_cb.toggled.connect(lambda *_: _live())
            long_press_cb.toggled.connect(lambda *_: _live())
            midi_type_combo.currentIndexChanged.connect(lambda *_: _live())
            midi_ch_spin.valueChanged.connect(lambda *_: _live())
            midi_note_spin.valueChanged.connect(lambda *_: _live())
            pad_style_combo.currentIndexChanged.connect(lambda *_: _live())

        return {
            "apply": apply,
            "update_visibility": update_visibility,
            "action_combo": act,
            "pad_combo": pad_style_combo,
            "top": [("Beschriftung:", cap), ("Aktion:", act)],
            "sections": [
                ("target", "Ziel und Verhalten", False, "vc_button_sec_target", [
                    ("Ziele:", target_editor),
                    ("Snapshot:", snap_combo),
                    ("Snap-Ziele:", snap_editor),
                    ("Tasten-Modus (Snap):", snap_mode_combo),
                    ("Effekt-Aktion:", eff_action_combo),
                    ("Gruppe (SelectGroup):", group_combo),
                    ("Tempo-Bus:", bus_combo),
                    ("Live-Edit-Slot:", edit_slot_edit),
                    ("Exklusiv:", exclusive_cb),
                    ("Geräte-Solo:", solo_fix_cb),
                    ("Programmer leeren:", clear_prog_cb),
                    ("Long-Press:", long_press_cb),
                    ("Zusatz-Aktionen:", actions_btn),
                ]),
                ("apc", "APC-Pad", False, "vc_button_sec_apc", [
                    ("Pad-Stil:", pad_style_combo),
                    ("2. Pad-Farbe (Wechsel):", pad_color2_btn),
                ]),
                ("midi", "MIDI und Tastatur", True, "vc_button_sec_midi", [
                    ("MIDI-Typ:", midi_type_combo),
                    ("MIDI-Kanal (0=alle):", midi_ch_spin),
                    ("Note / CC (-1=keine):", midi_note_spin),
                ]),
                ("advanced", "Erweitert (Roh-ID / Executor-Slot)", True, "vc_button_advanced", [
                    ("Funktion / Chase (Name):", func_combo),
                    ("Executor-Slot / Function-ID:", slot),
                    ("Weitere Schalt-IDs:", extra_ids),
                ]),
            ],
        }

    def _open_properties(self):
        """Modaler Eigenschaften-Dialog (Fallback / Doppelklick ausserhalb des
        Inspector-Panels). Baut die Felder ueber ``_build_settings`` und legt sie als
        flaches Formular mit Sektions-Trennern + „Erweitert"-Klappbereich aus."""
        from PySide6.QtWidgets import QWidget as _QWidget, QVBoxLayout  # noqa: F401
        from src.ui.widgets.collapsible_section import CollapsibleSection
        dlg = QDialog(self)
        dlg.setWindowTitle("Button Einstellungen")
        form = QFormLayout(dlg)
        S = self._build_settings(dlg, live=False)

        for label, w in S["top"]:
            form.addRow(label, w)

        adv_section = None
        for key, title, _collapsed, prefs, rows in S["sections"]:
            if key == "advanced":
                inner = _QWidget()
                inner_form = QFormLayout(inner)
                inner_form.setContentsMargins(0, 0, 0, 0)
                for label, w in rows:
                    inner_form.addRow(label, w)
                adv_section = CollapsibleSection(title, inner, collapsed=True, prefs_key=prefs)
                form.addRow(adv_section)
            else:
                form.addRow(QLabel(f"── {title} ──"))
                for label, w in rows:
                    form.addRow(label, w)

        def set_row_visible(w, show):
            try:
                form.setRowVisible(w, bool(show))
            except Exception:
                w.setVisible(bool(show))

        def set_section_visible(k, show):
            if k == "advanced" and adv_section is not None:
                try:
                    form.setRowVisible(adv_section, bool(show))
                except Exception:
                    adv_section.setVisible(bool(show))

        def refresh():
            S["update_visibility"](set_row_visible, set_section_visible)

        S["action_combo"].currentIndexChanged.connect(lambda _i: refresh())
        S["pad_combo"].currentIndexChanged.connect(lambda _i: refresh())
        refresh()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            S["apply"]()

    def build_inspector_body(self, host=None):
        """Liefert den in Sektionen gegliederten Einstellungs-Inhalt fuer das
        Inspector-Panel (Live-Bearbeitung). Speichert die Apply-Funktion unter
        ``self._inspector_apply``, damit das Panel beim Verlassen ein letztes Mal
        anwenden und einen Undo-Punkt setzen kann."""
        from PySide6.QtWidgets import QWidget as _QWidget, QVBoxLayout
        from src.ui.widgets.collapsible_section import CollapsibleSection
        host = host or self
        S = self._build_settings(host, live=True)
        self._inspector_apply = S["apply"]

        container = _QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        top_inner = _QWidget()
        top_form = QFormLayout(top_inner)
        top_form.setContentsMargins(0, 0, 0, 0)
        for label, w in S["top"]:
            top_form.addRow(label, w)
        v.addWidget(top_inner)

        row_form_of = {}
        sections = []   # (key, CollapsibleSection, [row_widgets])
        for key, title, collapsed, prefs, rows in S["sections"]:
            inner = _QWidget()
            f = QFormLayout(inner)
            f.setContentsMargins(0, 0, 0, 0)
            row_widgets = []
            for label, w in rows:
                f.addRow(label, w)
                row_form_of[w] = f
                row_widgets.append(w)
            sec = CollapsibleSection(title, inner, collapsed=collapsed, prefs_key=prefs)
            v.addWidget(sec)
            sections.append((key, sec, row_widgets))
        v.addStretch(1)

        shown = {}

        def set_row_visible(w, show):
            shown[w] = bool(show)
            f = row_form_of.get(w)
            if f is not None:
                try:
                    f.setRowVisible(w, bool(show))
                except Exception:
                    w.setVisible(bool(show))

        def set_section_visible(k, show):
            for key, sec, _rws in sections:
                if key == k:
                    sec.setVisible(bool(show))

        def refresh():
            S["update_visibility"](set_row_visible, set_section_visible)
            # Leere Sektionen ausblenden (advanced wird per Predicate gesteuert).
            for key, sec, row_widgets in sections:
                if key == "advanced":
                    continue
                sec.setVisible(any(shown.get(w, True) for w in row_widgets))

        S["action_combo"].currentIndexChanged.connect(lambda _i: refresh())
        S["pad_combo"].currentIndexChanged.connect(lambda _i: refresh())
        refresh()
        return container

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
        d["function_ids"] = list(self.function_ids)
        d["snapshot_index"] = self.snapshot_index
        d["snap_id"] = self.snap_id
        # VCI-14: snap_ids auch beim Speichern deduplizieren (snap_id + Doppelte raus),
        # konsistent zum Lade-Pfad in apply_dict — sonst persistieren zur Laufzeit
        # angesammelte Duplikate in die Show-Datei.
        _save_sids = []
        for i in self.snap_ids:
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if iv != self.snap_id and iv not in _save_sids:
                _save_sids.append(iv)
        d["snap_ids"] = _save_sids
        d["snap_mode"] = self.snap_mode
        d["effect_action_key"] = self.effect_action_key
        d["group_name"] = self.group_name
        d["tempo_bus_id"] = self.tempo_bus_id
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
        d["long_press_editor"] = self.long_press_editor
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        try:
            self.action = ButtonAction(d.get("action", "Toggle"))
        except ValueError:
            # Unbekannte Aktion (z. B. aus einer neueren Version) -> sicherer Default
            # statt Absturz; das Widget bleibt erhalten (Vorwaerts-/Rueckwaerts-Kompat).
            self.action = ButtonAction.TOGGLE
        self.function_id = d.get("function_id")
        _fids = []
        for i in d.get("function_ids", []):
            try:
                _fids.append(int(i))
            except (TypeError, ValueError):
                pass
        self.function_ids = _fids
        self.snapshot_index = d.get("snapshot_index")
        try:
            _sid0 = d.get("snap_id")
            self.snap_id = int(_sid0) if _sid0 is not None else None
        except (TypeError, ValueError):
            self.snap_id = None
        _sids = []
        for i in d.get("snap_ids", []):
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if iv != self.snap_id and iv not in _sids:
                _sids.append(iv)
        self.snap_ids = _sids
        self.snap_mode = d.get("snap_mode", "toggle")
        self.effect_action_key = d.get("effect_action_key", "next_color")
        self.group_name = d.get("group_name", "")
        self.tempo_bus_id = d.get("tempo_bus_id", "") or ""
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
        # VCB-18: Laufzeit-Snap-Toggle-Zustand zuruecksetzen. Wird eine Show neu
        # geladen, waehrend ein LIBRARY_SNAP-Toggle aktiv war, schriebe der naechste
        # Druck sonst ueber stale _snap_prev alte DMX-Werte in den Programmer.
        self._snap_active = False
        self._snap_prev = {}
        self.long_press_editor = bool(d.get("long_press_editor", False))

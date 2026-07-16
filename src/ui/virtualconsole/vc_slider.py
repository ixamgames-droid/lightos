"""VCSlider — Virtual Console Fader Widget."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                                QDialogButtonBox, QSizePolicy, QSpinBox, QLabel,
                                QCheckBox, QWidget, QVBoxLayout, QHBoxLayout)
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen
from .vc_widget import VCWidget
from .vc_style import paint_slider_handle   # VC3D-02: plastischer Fader-Griff


def _clear_submaster_slot(slot):
    """Raeumt den Submaster-Slot eines geloeschten oder umgestellten Faders im
    OutputManager (sonst dimmt sein letzter Wert als Geist weiter)."""
    try:
        from src.core.app_state import get_state
        get_state().output_manager.clear_submaster(slot)
    except Exception:
        pass


def _clear_feature_dimmer_slot(slot):
    """F-26b: raeumt den Feature-Dimmer-Slot eines geloeschten/umgestellten Faders
    in AppState.feature_dimmers (sonst dimmt sein letzter Wert als Geist weiter)."""
    try:
        from src.core.app_state import get_state
        get_state().feature_dimmers.pop(slot, None)
    except Exception:
        pass


class SliderMode(str):
    LEVEL    = "Level"
    PLAYBACK = "Playback"
    SUBMASTER = "Submaster"
    GRANDMASTER = "GrandMaster"   # steuert die globale Gesamthelligkeit
    PROGRAMMER  = "Programmer"    # setzt ein Programmer-Attribut (programmer_attr)
    BPM         = "BPM"           # steuert das globale Tempo (Beat-Effekte folgen)
    SPEED       = "Speed"         # steuert die Geschwindigkeit ALLER laufenden Effekte
    EFFECT_INTENSITY = "EffectIntensity"  # Helligkeits-Master EINES Effekts
    EFFECT_SPEED     = "EffectSpeed"       # Tempo-Master EINES Effekts
    # Phase 6: bindet einen BELIEBIGEN Effekt-Parameter (param_key) live —
    # Fader 0..255 wird auf den Wertebereich der ParamSpec abgebildet.
    EFFECT_PARAM     = "EffectParam"
    # F-25: multiplikativer Gruppen-Dimmer — der Fader skaliert die Helligkeit
    # einer festen Fixture-Gruppe (programmer_group) über set_group_dimmer().
    GROUP_DIMMER     = "GroupDimmer"
    # F-26b: Feature-Dimmer-Master — wie GROUP_DIMMER, aber dimmt eine WAEHLBARE
    # Feature-Gruppe (feature_attr: Intensity/Color/Gobo/Beam/Position/Effect) statt
    # nur der Helligkeit; effekt-unabhaengig via set_feature_dimmer (Render 4b²).
    FEATURE_DIMMER   = "FeatureDimmer"
    # Tempo-Sync Phase 5: steuert die BPM EINES benannten Tempo-Bus (A/B/C/D),
    # unabhaengig vom globalen Leader (tempo_bus_id, "" = aktiver/Default-Bus).
    TEMPO_BUS        = "TempoBus"


# Benutzerfreundliche deutsche Labels für die Modus-Auswahl (statt roher Codes).
SLIDER_MODE_LABELS: list[tuple[str, str]] = [
    (SliderMode.EFFECT_INTENSITY, "Effekt-Helligkeit"),
    (SliderMode.EFFECT_SPEED,     "Effekt-Tempo"),
    (SliderMode.EFFECT_PARAM,     "Effekt-Parameter"),
    (SliderMode.PROGRAMMER,       "Programmer-Attribut"),
    (SliderMode.GROUP_DIMMER,     "Gruppen-Dimmer"),
    (SliderMode.FEATURE_DIMMER,   "Feature-Dimmer (Gruppe)"),
    (SliderMode.SUBMASTER,        "Submaster"),
    (SliderMode.GRANDMASTER,      "Grand Master"),
    (SliderMode.SPEED,            "Speed (alle Effekte)"),
    (SliderMode.BPM,              "Tempo (BPM)"),
    (SliderMode.TEMPO_BUS,        "Tempo-Bus (BPM)"),
    (SliderMode.PLAYBACK,         "Playback (Executor)"),
    (SliderMode.LEVEL,            "DMX-Kanal (Level)"),
]

# VCI-05: gueltige Modi (SliderMode ist kein echtes Enum) — fuer die Validierung
# beim Laden, damit ein unbekannter Modus nicht still ein wirkungsloses Widget ergibt.
_VALID_SLIDER_MODES = frozenset(m for m, _ in SLIDER_MODE_LABELS)


class VCSlider(VCWidget):
    """Vertikaler Fader — Level / Playback / Submaster."""

    # Soft-Takeover / „Pickup" (global, von der VC-Toolbar gesetzt): für nicht-
    # motorisierte Controller (APC mini & Co.). Nach einem Bank-/Seitenwechsel steht
    # der physische Fader woanders als der VC-Wert — bei aktivem Pickup übernimmt der
    # Fader erst, wenn er den aktuellen VC-Wert EINMAL durchfahren hat (kein Sprung).
    soft_takeover: bool = False

    def is_effect_bound(self) -> bool:
        return self.mode in (SliderMode.EFFECT_PARAM, SliderMode.EFFECT_INTENSITY,
                             SliderMode.EFFECT_SPEED)

    def live_effect_function_id(self):
        if self.function_ids:
            return self.function_ids[0]
        return self.function_id

    def __init__(self, caption: str = "Fader", parent=None):
        super().__init__(caption, parent)
        self.mode = SliderMode.LEVEL
        self.function_id: int | None = None
        # DQ-2: dedizierter Executor-Slot fuer den PLAYBACK-Modus (frueher wurde
        # function_id zweckentfremdet). None = nicht gesetzt.
        self.playback_slot: int | None = None
        # Mehrere Effekt-IDs = Gruppen-Submaster: der Fader regelt in den
        # EFFECT_*-Modi ALLE gelisteten Effekte gemeinsam (Intensitaet/Speed).
        # Leer -> Einzel-Effekt ueber function_id (bzw. aktiver Effekt).
        self.function_ids: list[int] = []
        self.dmx_channel: int = 1
        self.dmx_universe: int = 1
        self.programmer_attr: str = "intensity"   # fuer PROGRAMMER-Modus
        # FDR-01: Reichweite im PROGRAMMER-Modus — "all" = alle gepatchten Fixtures,
        # "selected" = nur die aktuelle Programmer-Auswahl, "group" = eine FESTE
        # Fixture-Gruppe (programmer_group), unabhaengig von der Live-Auswahl
        # (APC-Probier To-Do #4: PAR-Dim trifft die PARs ohne vorher anzuklicken).
        self.programmer_scope: str = "all"
        self.programmer_group: str = ""           # Gruppenname fuer scope == "group"
        # LAS-Speed: im PROGRAMMER-Modus 0..100% auf ein Wert-Teilband [min,max]
        # mappen (Default 0/255 = volle Reichweite = altes Verhalten). Für Laser
        # z. B. gobo_rotation-Dynamikbereich 192..223 = „Geschwindigkeit im
        # Uhrzeigersinn-Modus" (Fader hält das Muster im Modus + regelt Tempo).
        self.programmer_min: int = 0
        self.programmer_max: int = 255
        # F-26b: zu dimmende Feature-Gruppe im FEATURE_DIMMER-Modus (classify_attr-
        # Gruppenname: Intensity/Color/Gobo/Beam/Position/Effect). "" = Intensity.
        self.feature_attr: str = "Intensity"
        self.param_key: str = "speed"             # fuer EFFECT_PARAM-Modus
        # Phase E (Multi-Effekt): je gekoppeltem Effekt ein eigener gesteuerter
        # Parameter (Map fid -> param_key). Fehlt ein Eintrag -> param_key (Default).
        # Greift nur im EFFECT_PARAM-Modus; leer = alle Ziele nutzen param_key.
        self.param_keys_per_id: dict[int, str] = {}
        self.tempo_bus_id: str = ""               # fuer TEMPO_BUS-Modus ("" = aktiv/Default)
        # Live-Bearbeitung: bearbeitet den Effekt im benannten Edit-Slot (von einem
        # Effekt-Pad gesetzt). Greift nur, wenn keine feste function_id/-ids gesetzt
        # sind — dann statt „aktiver Effekt" das Slot-Ziel.
        self.edit_slot: str = ""
        # Effekt-Fader-Verhalten am unteren Anschlag (nur EFFECT_*-Modi):
        #   False = Fader REGELT nur (Effekt muss separat gestartet werden;
        #           bei 0 laeuft der Effekt mit Wert 0 weiter) — bisheriges Verhalten.
        #   True  = Fader STEUERT AN/AUS: Wert > 0 startet den/die Ziel-Effekte
        #           (falls noch nicht laufend), Wert == 0 stoppt sie wirklich.
        self.effect_autostart: bool = False
        self._value: int = 0          # 0–255
        self._drag_y: int | None = None
        self._drag_start_val: int = 0
        self._bg_color = QColor("#1a1a2e")
        self._fg_color = QColor("#ffffff")
        # MIDI CC binding
        self.midi_cc: int = -1        # -1 = kein MIDI
        self.midi_ch: int = 0         # 0 = alle Kanäle
        # Soft-Takeover-Laufzeitzustand (s. Klassen-Flag soft_takeover):
        #   _pickup_armed = True  -> wartet, bis der physische Fader den VC-Wert
        #                            durchfährt; bis dahin wird MIDI ignoriert.
        #   _last_cc      = letzter empfangener CC-Wert (0–255) zur Richtungs-/
        #                   Durchfahr-Erkennung; None = noch keine Referenz.
        self._pickup_armed: bool = False
        self._last_cc: int | None = None
        # Wert-Leitplanken: der Fader bildet seinen Hub 0..255 auf
        # [range_min, range_max] ab; invert dreht die Richtung. So lassen sich
        # Kanäle/Effekte bewusst nur in einem Teilbereich regeln ("halb anpassen"),
        # z. B. ein Dimmer der nie unter 30% oder ein invertierter Nebel-Fader.
        self.invert: bool = False
        self.range_min: int = 0       # 0–255
        self.range_max: int = 255     # 0–255
        self.resize(60, 200)
        # Zuweisbarer Submaster: jeder Fader ist ein eigener Submaster-Slot (eindeutig
        # pro Widget, id(self)). Wird der Fader geloescht, muss sein Slot im
        # OutputManager geraeumt werden — sonst dimmt sein letzter Wert weiter.
        self.destroyed.connect(lambda *_, s=id(self): _clear_submaster_slot(s))
        # F-26b: ebenso den Feature-Dimmer-Slot raeumen (sonst Geister-Feature-Dimmer).
        self.destroyed.connect(lambda *_, s=id(self): _clear_feature_dimmer_slot(s))

    # ── Value ─────────────────────────────────────────────────────────────────

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, v: int):
        self._value = max(0, min(255, v))
        self._apply()
        self.update()

    def _effective_value(self) -> int:
        """Tatsächlicher Ausgabewert: der Hub 0..255 wird auf [range_min, range_max]
        abgebildet, optional invertiert. min==max -> konstanter Wert (kein
        Division-by-zero, da hier nicht geteilt wird). Ergebnis stets 0..255."""
        ratio = self._value / 255.0
        if self.invert:
            ratio = 1.0 - ratio
        lo, hi = self.range_min, self.range_max
        if lo > hi:                       # vertauschte Grenzen tolerieren
            lo, hi = hi, lo
        return max(0, min(255, int(round(lo + ratio * (hi - lo)))))

    def _programmer_mapped(self, v) -> int:
        """0..255-Faderwert auf das Teilband [programmer_min, programmer_max]
        abbilden (Default 0/255 = identisch). Für Laser-Speed: der Fader hält den
        Kanal im gewählten Dynamik-Bereich und regelt darin das Tempo."""
        lo = max(0, min(255, int(getattr(self, "programmer_min", 0))))
        hi = max(0, min(255, int(getattr(self, "programmer_max", 255))))
        if hi < lo:
            lo, hi = hi, lo
        if lo == 0 and hi == 255:
            return int(v)
        return int(round(lo + (int(v) / 255.0) * (hi - lo)))

    def _apply(self):
        from src.core.app_state import get_state
        state = get_state()
        v = self._effective_value()       # Leitplanken (Range/Invert) angewandt
        # Optional: Effekt-Fader steuert auch An/Aus (siehe effect_autostart).
        if self.mode in (SliderMode.EFFECT_INTENSITY, SliderMode.EFFECT_SPEED,
                         SliderMode.EFFECT_PARAM):
            self._autostart_targets()
        if self.mode == SliderMode.GRANDMASTER:
            try:
                state.output_manager.set_grand_master(v / 255.0)
            except Exception:
                pass
        elif self.mode == SliderMode.BPM:
            # Globales Tempo 30..300 BPM -> Beat-Effekte folgen.
            # WP-8: set_manual_bpm() statt set_bpm() — das Ziehen des BPM-Faders
            # erzwingt damit den MANUAL-Modus (der Fader ist die Tempo-Quelle).
            try:
                from src.core.engine.bpm_manager import get_bpm_manager
                get_bpm_manager().set_manual_bpm(30.0 + (v / 255.0) * 270.0)
            except Exception:
                pass
        elif self.mode == SliderMode.TEMPO_BUS:
            # Tempo-Sync Phase 5: BPM eines benannten Bus (30..300), unabhaengig
            # vom globalen Leader. "" = aktiver/Default-Bus.
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().resolve(self.tempo_bus_id)
                if bus is not None:
                    bus.set_bpm(30.0 + (v / 255.0) * 270.0)
            except Exception:
                pass
        elif self.mode == SliderMode.SPEED:
            # Geschwindigkeit ALLER laufenden zeitbasierten Effekte 0.1..4.0x
            # (Chaser, Sequence, Carousel, RGB-Matrix, EFX). Der Master multipliziert
            # die jeweilige Basisrate.
            try:
                from src.core.engine.function_manager import get_function_manager
                from src.core.engine.chaser import Chaser
                from src.core.engine.sequence import Sequence
                from src.core.engine.carousel import Carousel
                from src.core.engine.rgb_matrix import RgbMatrixInstance
                from src.core.engine.efx import EfxInstance
                timed = (Chaser, Sequence, Carousel, RgbMatrixInstance, EfxInstance)
                mult = 0.1 + (v / 255.0) * 3.9
                for f in get_function_manager().all():
                    if isinstance(f, timed) and f.is_running:
                        f.speed = mult
            except Exception:
                pass
        elif self.mode == SliderMode.EFFECT_INTENSITY:
            # Helligkeits-Master eines Effekts ODER einer Effekt-Gruppe
            # (function_ids). Leer -> aktiver Effekt.
            lvl = v / 255.0
            for f in self._effect_targets():
                f.intensity = lvl
        elif self.mode == SliderMode.EFFECT_SPEED:
            # Tempo-Master eines Effekts/einer Gruppe (0.1..4.0x).
            spd = 0.1 + (v / 255.0) * 3.9
            for f in self._effect_targets():
                f.speed = spd
        elif self.mode == SliderMode.EFFECT_PARAM:
            # Phase 6: beliebiger Effekt-Parameter live. Fader 0..255 → Wertebereich
            # der ParamSpec (im Effekt). Leere Bindung = aktiver Effekt.
            try:
                from src.core.engine import effect_live
                targets = self._all_target_fids() or [self._resolved_effect_fid()]
                for fid in targets:
                    # Phase E: je Effekt darf ein eigener Parameter gesteuert werden;
                    # fehlt ein Eintrag, gilt der Default-param_key des Faders.
                    key = self.param_keys_per_id.get(fid, self.param_key) if fid is not None else self.param_key
                    effect_live.set_param_normalized(key, v / 255.0, fid)
            except Exception:
                pass
        elif self.mode == SliderMode.PROGRAMMER:
            attr = self.programmer_attr or "intensity"
            try:
                if self.programmer_scope == "group" and self.programmer_group:
                    fids = self._group_fids(state, self.programmer_group)
                    if not fids:                       # Gruppe leer/fehlt -> alle
                        fids = [f.fid for f in state.get_patched_fixtures()]
                elif self.programmer_scope == "selected":
                    fids = list(state.get_selected_fids())
                    if not fids:                       # Fallback: nichts gewaehlt -> alle
                        fids = [f.fid for f in state.get_patched_fixtures()]
                else:
                    fids = [f.fid for f in state.get_patched_fixtures()]
                pv = self._programmer_mapped(v)   # LAS-Speed: 0..255 → [min,max]
                for fid in fids:
                    state.set_programmer_value(fid, attr, pv)
            except Exception:
                pass
        elif self.mode == SliderMode.LEVEL:
            # universes ist ein dict mit 1-basierten Keys — Universe bei Bedarf
            # anlegen, damit der Fader auch ohne gepatchte Fixture funktioniert
            # (analog SimpleDesk). Frueher: "< len(...)" -> KeyError: 0 -> Crash.
            u = state.universes.get(self.dmx_universe)
            if u is None:
                u = state.output_manager.add_universe(self.dmx_universe)
                state.universes[self.dmx_universe] = u
            u.set_channel(self.dmx_channel, v)
        elif self.mode == SliderMode.PLAYBACK and self.playback_slot is not None:
            slot = self.playback_slot
            executors = state.playback_engine.executors
            if 0 <= slot < len(executors):
                executors[slot].fader_value = v / 255.0
        elif self.mode == SliderMode.SUBMASTER:
            # Zuweisbarer Submaster: eigener Slot pro Fader (id(self)), optional auf
            # bestimmte Geraete/Gruppen beschraenkt (Reichweite). fids=None ->
            # globaler Submaster (wirkt auf alles, bisheriges Verhalten).
            try:
                fids = self._submaster_target_fids(state)
                state.output_manager.set_submaster(id(self), v / 255.0, fids)
            except Exception:
                pass
        elif self.mode == SliderMode.GROUP_DIMMER:
            # F-25: multiplikativer Gruppen-Dimmer über set_group_dimmer().
            try:
                fids = self._group_fids(state, self.programmer_group)
                state.set_group_dimmer(fids, v / 255.0)
            except Exception:
                pass
        elif self.mode == SliderMode.FEATURE_DIMMER:
            # F-26b: per-Slot Feature-Dimmer ueber set_feature_dimmer (Render 4b²).
            # Dimmt die gewaehlte Feature-Gruppe (feature_attr) einer festen Gruppe;
            # leeres/"Intensity" feature_attr -> Default = Helligkeit.
            try:
                fids = self._group_fids(state, self.programmer_group)
                feats = ({self.feature_attr}
                         if self.feature_attr and self.feature_attr != "Intensity"
                         else None)
                state.set_feature_dimmer(id(self), fids, feats, v / 255.0)
            except Exception:
                pass

    @staticmethod
    def _group_fids(state, group_name: str) -> list[int]:
        """Fids einer FESTEN Fixture-Gruppe (Name) in Raster-Reihenfolge (To-Do #4).
        Delegiert an die zentrale Auflösung in app_state (dedupliziert)."""
        try:
            return state.group_fids_by_name(group_name)
        except Exception:
            return []

    @staticmethod
    def _available_feature_groups(group_name: str) -> list[str]:
        """F-26b: die in den Fixtures der gewaehlten Gruppe tatsaechlich vorhandenen
        classify_attr-Feature-Gruppen (Capabilities), in sinnvoller Reihenfolge,
        Intensity immer zuerst. Ohne Gruppe / ohne Treffer -> Standardliste. Qt-frei."""
        _ORDER = ["Intensity", "Color", "Position", "Gobo", "Beam", "Effect"]
        try:
            from src.core.app_state import get_state
            from src.core.attr_groups import classify_attr
            st = get_state()
            fids = st.group_fids_by_name(group_name) if group_name else []
            present = set()
            for fid in fids:
                entry = st._fix_index.get(fid)
                if not entry:
                    continue
                _fx, chans = entry
                for ch in chans:
                    attr = (getattr(ch, "attribute", "") or "").lower()
                    if attr:
                        present.add(classify_attr(attr))
            avail = [g for g in _ORDER if g in present]
            if avail:
                return avail if "Intensity" in avail else (["Intensity"] + avail)
        except Exception:
            pass
        return list(_ORDER)

    def _submaster_target_fids(self, state):
        """Reichweite eines Submaster-Faders -> Ziel-fids oder None (= global/alle).
        'all' -> None (wirkt auf alles, bisheriges Verhalten); 'group' -> fids der
        festen Gruppe; 'selected' -> aktuelle Programmer-Auswahl (Snapshot). Leere
        Aufloesung -> [] (Fader ohne Wirkung, statt versehentlich alles zu dimmen)."""
        scope = self.programmer_scope or "all"
        if scope == "group" and self.programmer_group:
            return self._group_fids(state, self.programmer_group)
        if scope == "selected":
            try:
                return list(state.get_selected_fids())
            except Exception:
                return []
        return None

    def _resolved_effect_fid(self):
        """Einzel-Ziel-fid für Effekt-Modi: feste function_id, sonst der Live-Edit-Slot
        (von einem Effekt-Pad gesetzt), sonst None (= aktiver Effekt)."""
        if self.function_id is not None:
            return self.function_id
        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                fid = effect_live.get_edit_target(self.edit_slot)
                if fid is not None:
                    return fid
            except Exception:
                pass
        return None

    def _effect_target(self):
        """Einzel-Zielfunktion fuer die EFFECT_*-Modi: feste Bindung ueber
        function_id / Live-Edit-Slot, sonst der gerade aktive Effekt."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            fid = self._resolved_effect_fid()
            if fid is not None:
                return fm.get(fid)
            return fm.active_function()
        except Exception:
            return None

    def _effect_targets(self) -> list:
        """Alle Zielfunktionen: function_ids (Gruppen-Submaster) ODER der eine
        function_id / der aktive Effekt. Nicht gefundene IDs werden uebersprungen."""
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            # VCB-20: function_id UND function_ids zusammenfuehren (wie _all_target_fids),
            # statt function_id zu verwerfen, sobald function_ids gesetzt ist.
            ids = self._all_target_fids()
            if ids:
                return [f for f in (fm.get(i) for i in ids) if f is not None]
        except Exception:
            return []
        f = self._effect_target()
        return [f] if f is not None else []

    def _all_target_fids(self) -> list[int]:
        """Phase E: alle gekoppelten Effekt-IDs (function_id + function_ids),
        function_id zuerst, dedupliziert. Leer = keine feste Bindung
        (-> der Aufrufer faellt auf den aktiven/Edit-Slot-Effekt zurueck)."""
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

    def _autostart_targets(self):
        """Nur wenn ``effect_autostart`` aktiv ist: der Fader steuert zusaetzlich
        An/Aus der Ziel-Effekte. Wert > 0 startet sie (falls noch nicht laufend),
        Wert == 0 stoppt sie wirklich. Ohne festes Ziel (function_id/-ids leer ->
        „aktiver Effekt") wird nichts erzwungen. Bei effect_autostart == False
        bleibt der Effekt unberuehrt und der Fader regelt nur."""
        if not self.effect_autostart:
            return
        _fid = self._resolved_effect_fid()
        # VCB-20: function_id + function_ids zusammenfuehren; nur wenn beide leer
        # sind, auf den aufgeloesten (aktiven/Edit-Slot-)Effekt zurueckfallen.
        ids = self._all_target_fids() or ([_fid] if _fid is not None else [])
        if not ids:
            return
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
        except Exception:
            return
        on = self._effective_value() > 0
        for fid in ids:
            if fid is None:
                continue
            try:
                fid = int(fid)
                if on:
                    if not fm.is_running(fid):
                        fm.start(fid)
                elif fm.is_running(fid):
                    fm.stop(fid)
            except Exception:
                pass

    # ── MIDI ─────────────────────────────────────────────────────────────────

    # Toleranz (0–255) für den Pickup-„Treffer".  ~2 MIDI-Schritte.
    _PICKUP_TOLERANCE = 4

    def arm_pickup(self):
        """Aktiviert Soft-Takeover für diesen Fader (falls global eingeschaltet):
        der nächste MIDI-Zugriff wirkt erst, wenn der physische Fader den aktuellen
        VC-Wert durchfährt. Wird bei jedem Bank-/Seitenwechsel aufgerufen."""
        if VCSlider.soft_takeover:
            self._pickup_armed = True
            self._last_cc = None
            self.update()

    def handle_midi(self, msg) -> bool:
        if self.midi_cc < 0 or msg.msg_type != "cc":
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        if msg.data1 != self.midi_cc:
            return False
        iv = round(msg.data2 / 127.0 * 255)

        # Ohne Soft-Takeover (oder nicht „armiert"): direkt übernehmen.
        if not VCSlider.soft_takeover or not self._pickup_armed:
            self._last_cc = iv
            self.value = iv
            return True

        # Soft-Takeover: erst übernehmen, wenn der physische Fader den aktuellen
        # VC-Wert erreicht/durchfährt — sonst MIDI ignorieren (kein Sprung).
        prev = self._last_cc
        self._last_cc = iv
        cur = self._value
        caught = abs(iv - cur) <= self._PICKUP_TOLERANCE
        if not caught and prev is not None:
            caught = (prev <= cur <= iv) or (iv <= cur <= prev)
        if caught:
            self._pickup_armed = False
            self.value = iv            # ab jetzt normal mitlaufen
        else:
            self.update()              # nur den Pickup-Hinweis (Pfeil) auffrischen
        return True

    # ── MIDI Teach (siehe VCWidget) — Fader bindet nur CC ──────────────────────

    def supports_midi_teach(self) -> bool:
        return True

    def _midi_teach_kinds(self):
        return ("cc",)

    def current_midi_binding(self):
        if self.midi_cc is None or self.midi_cc < 0:
            return None
        return ("cc", self.midi_ch, self.midi_cc)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_cc = -1
            return
        if msg_type == "cc":
            self.midi_cc = data1
            self.midi_ch = channel or 0

    # ── Track geometry ────────────────────────────────────────────────────────

    def _track_rect(self) -> QRect:
        m = 20
        return QRect(self.width() // 2 - 6, m, 12, self.height() - m * 2)

    def _handle_y(self) -> int:
        tr = self._track_rect()
        ratio = 1.0 - self._value / 255.0
        return int(tr.y() + ratio * tr.height())

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = event.position().toPoint().y()
            self._drag_start_val = self._value
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag_y is not None:
            dy = self._drag_y - event.position().toPoint().y()
            tr = self._track_rect()
            # VCB-15: _track_rect()-Hoehe = height - 40; bei einem auf <=40 px
            # geschrumpften Fader wird sie 0/negativ -> ZeroDivisionError beim Ziehen.
            th = tr.height()
            if th > 0:
                delta = int(dy / th * 255)
                self.value = self._drag_start_val + delta
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._drag_y = None
        event.accept()

    def wheelEvent(self, event):
        if self._edit_mode:
            return
        steps = event.angleDelta().y() // 120
        self.value = self._value + steps * 5

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        tr = self._track_rect()
        # Track background
        p.fillRect(tr, QColor("#333355"))

        # Fill from bottom to handle
        hy = self._handle_y()
        fill = QRect(tr.x(), hy, tr.width(), tr.bottom() - hy)
        grad = QLinearGradient(0, fill.bottom(), 0, fill.top())
        grad.setColorAt(0.0, QColor("#003366"))
        grad.setColorAt(1.0, QColor("#0088ff"))
        p.fillRect(fill, grad)

        # Handle knob — VC3D-02: plastischer Griff (Woelbung + Bevel + Griff-Rille)
        # statt flachem fillRect, konsistent mit dem 3D-Look der VC-Buttons.
        paint_slider_handle(p, QRect(tr.x() - 8, hy - 4, tr.width() + 16, 8), QColor("#aaccff"))

        # Soft-Takeover-Hinweis: Fader „armiert" und wartet, bis der physische
        # Fader den VC-Wert (hy) durchfährt. Ziel-Linie + Geist-Position + Pfeil.
        if self._pickup_armed:
            p.setPen(QPen(QColor("#ffb000"), 1, Qt.PenStyle.DashLine))
            p.drawLine(tr.x() - 6, hy, tr.right() + 6, hy)   # Ziel = aktueller VC-Wert
            arrow = ""
            if self._last_cc is not None:
                gy = int(tr.y() + (1.0 - self._last_cc / 255.0) * tr.height())
                p.fillRect(tr.x() - 4, gy - 1, tr.width() + 8, 3, QColor("#ffb000"))
                arrow = "▲" if self._last_cc < self._value else "▼"
            p.setPen(QColor("#ffb000"))
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(QRect(0, 16, self.width(), 14),
                       Qt.AlignmentFlag.AlignCenter, f"⊘{arrow}")

        # Label at bottom
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 8))
        label_rect = QRect(0, self.height() - 18, self.width(), 18)
        p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.caption)

        # Value — zeigt den TATSÄCHLICHEN Ausgabewert (Range/Invert angewandt),
        # damit eine gesetzte Leitplanke direkt ablesbar ist.
        p.setFont(QFont("Segoe UI", 7))
        val_rect = QRect(0, 2, self.width(), 14)
        pct = int(self._effective_value() / 255 * 100)
        p.drawText(val_rect, Qt.AlignmentFlag.AlignCenter, f"{pct}%")

        # Leitplanken-Indikator oben links: ⇅ wenn invertiert / ▯ wenn Teilbereich.
        if self.invert or self.range_min > 0 or self.range_max < 255:
            p.setPen(QColor("#ffcc55"))
            p.setFont(QFont("Segoe UI", 7))
            mark = "⇅" if self.invert else "▯"
            p.drawText(QRect(2, 0, 12, 12), Qt.AlignmentFlag.AlignCenter, mark)

        # MIDI-Bindung-Indikator oben rechts (cyan dot)
        if self.midi_cc >= 0:
            p.fillRect(self.width() - 8, 0, 8, 8, QColor("#00aaff"))
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        _old_mode = self.mode      # fuer Submaster-Slot-Aufraeumen bei Moduswechsel
        _old_group = self.programmer_group   # VCB-34: alte Gruppe vor Form-Overwrite
        dlg = QDialog(self)
        dlg.setWindowTitle("Fader Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        mode_cb = QComboBox()
        for m, lbl in SLIDER_MODE_LABELS:
            mode_cb.addItem(lbl, m)          # Label sichtbar, Modus-Wert als Data
        for i in range(mode_cb.count()):
            if mode_cb.itemData(i) == self.mode:
                mode_cb.setCurrentIndex(i)
                break
        form.addRow("Modus:", mode_cb)

        # Parameter-Key fuer EFFECT_PARAM — Auswahl aus den Parametern des
        # gebundenen Effekts (list_params: Label + Key) statt blindem Freitext.
        # Editierbar, damit Power-User auch ohne aktiven Effekt einen Key tippen
        # koennen; der gespeicherte Key bleibt immer erhalten.
        param_key_combo = QComboBox()
        param_key_combo.setEditable(True)
        _pk_keys: list[str] = []
        try:
            from src.core.engine import effect_live
            _fid = self.function_id if self.function_id is not None else (self.function_ids[0] if self.function_ids else None)
            for _spec in effect_live.list_params(_fid):
                _key = getattr(_spec, "key", None)
                if not _key:
                    continue
                _lbl = getattr(_spec, "label", _key)
                param_key_combo.addItem(f"{_lbl}  ({_key})", _key)
                _pk_keys.append(_key)
        except Exception:
            pass
        if self.param_key and self.param_key not in _pk_keys:
            param_key_combo.addItem(self.param_key, self.param_key)
            _pk_keys.append(self.param_key)
        # aktuellen Key vorwaehlen (per Data; sonst als Freitext setzen)
        _pk_idx = next((i for i in range(param_key_combo.count())
                        if param_key_combo.itemData(i) == self.param_key), -1)
        if _pk_idx >= 0:
            param_key_combo.setCurrentIndex(_pk_idx)
        else:
            param_key_combo.setCurrentText(self.param_key)
        param_key_combo.setToolTip("Effekt-Parameter (nur Modus Effekt-Parameter). "
                                   "Liste = Parameter des gebundenen Effekts; eigener Key tippbar.")
        form.addRow("Parameter (Effekt-Parameter):", param_key_combo)

        # ── Aufklappbare „Steuert"-Liste (ersetzt die fruehere Gekoppelte-Effekte-
        # Tabelle): listet die gesteuerten Effekte/Funktionen nach NAMEN, je Zeile
        # mit Parameter-Combo, auswaehl-/loeschbar + „+"-Hinzufuegen. Bei den
        # EFFECT-Modi ist sie maßgeblich fuer die ID-Liste UND die je-Effekt-Parameter.
        from .target_list_editor import TargetListEditor
        target_editor = TargetListEditor(with_params=True, title="Steuert")
        target_editor.set_targets(self._all_target_fids(), dict(self.param_keys_per_id))
        target_editor.setToolTip("Effekte/Funktionen, die dieser Fader steuert — je Zeile "
                                 "den Parameter wählen, mit ✕ entfernen, „+“ hinzufügen. "
                                 "Bei Effekt-Modi maßgeblich (überschreibt das Slot-Feld).")
        form.addRow("Steuert:", target_editor)

        # FDR-01 / To-Do #4: Reichweite im Programmer-Modus.
        scope_cb = QComboBox()
        scope_cb.addItem("Alle Geräte", "all")
        scope_cb.addItem("Nur Auswahl", "selected")
        scope_cb.addItem("Feste Gruppe", "group")
        _scope_idx = {"selected": 1, "group": 2}.get(self.programmer_scope, 0)
        scope_cb.setCurrentIndex(_scope_idx)
        scope_cb.setToolTip("Modus Programmer/Submaster: auf welche Fixtures der Fader "
                            "wirkt (alle gepatchten, die aktuelle Auswahl, oder eine fest "
                            "gewählte Gruppe — unabhängig von der Live-Auswahl). Beim "
                            "Submaster = 'Alle Geräte' ist der bisherige globale Submaster.")
        form.addRow("Reichweite (Programmer/Submaster):", scope_cb)

        # Feste Gruppe (nur scope == "group"): Auswahl aus den vorhandenen Gruppen.
        group_cb = QComboBox()
        group_cb.setEditable(True)
        group_cb.addItem("")
        try:
            from sqlalchemy import select
            from src.core.database.models import FixtureGroup
            from src.core.app_state import get_state as _gs
            with _gs()._session() as _s:
                for _g in _s.execute(select(FixtureGroup.name)).scalars().all():
                    group_cb.addItem(_g)
        except Exception:
            pass
        group_cb.setCurrentText(self.programmer_group or "")
        group_cb.setToolTip("Fixture-Gruppe für Reichweite = 'Feste Gruppe' "
                            "(Programmer/Submaster) bzw. für 'GroupDimmer'/'FeatureDimmer'.")
        form.addRow("Feste Gruppe:", group_cb)

        # UXT-01: Ziel-Attribut für den PROGRAMMER-Modus. Ohne dieses Feld war der
        # Modus faktisch auf "intensity" festgenagelt (ein Fader auf z. B.
        # gobo_rotation war per GUI unbaubar → der LAS-Speed-Fader blieb
        # unerreichbar). Editierbare Combo, befüllt aus den bekannten Attributen
        # (attr_groups.ATTR_LABELS, Label + roher Key); Freitext für Power-User.
        prog_attr_combo = QComboBox()
        prog_attr_combo.setEditable(True)
        _pa_keys: list[str] = []
        try:
            from src.core.attr_groups import ATTR_LABELS
            for _a in sorted(ATTR_LABELS):
                prog_attr_combo.addItem(f"{ATTR_LABELS[_a]}  ({_a})", _a)
                _pa_keys.append(_a)
        except Exception:
            pass
        _cur_attr = self.programmer_attr or "intensity"
        if _cur_attr not in _pa_keys:
            prog_attr_combo.addItem(_cur_attr, _cur_attr)
            _pa_keys.append(_cur_attr)
        _pa_idx = next((i for i in range(prog_attr_combo.count())
                        if prog_attr_combo.itemData(i) == _cur_attr), -1)
        if _pa_idx >= 0:
            prog_attr_combo.setCurrentIndex(_pa_idx)
        else:
            prog_attr_combo.setCurrentText(_cur_attr)
        prog_attr_combo.setToolTip("Welches Programmer-Attribut dieser Fader setzt "
                                   "(Modus Programmer-Attribut). Liste = bekannte "
                                   "Attribute; eigener Name tippbar. Beispiel "
                                   "Laser-Tempo: gobo_rotation mit Wert 192–223.")
        form.addRow("Attribut (Programmer):", prog_attr_combo)

        # LAS-Speed: Wert-Teilband für den PROGRAMMER-Modus (0..100% → [min,max]).
        prog_min_spin = QSpinBox()
        prog_min_spin.setRange(0, 255)
        prog_min_spin.setValue(int(self.programmer_min))
        prog_min_spin.setToolTip("Kanalwert bei Fader 0 %. Für Laser-Speed = "
                                 "Anfang des Dynamik-Bereichs (z. B. 192).")
        form.addRow("Wert bei 0 % (Programmer):", prog_min_spin)
        prog_max_spin = QSpinBox()
        prog_max_spin.setRange(0, 255)
        prog_max_spin.setValue(int(self.programmer_max))
        prog_max_spin.setToolTip("Kanalwert bei Fader 100 %. Für Laser-Speed = "
                                 "Ende des Dynamik-Bereichs (z. B. 223).")
        form.addRow("Wert bei 100 % (Programmer):", prog_max_spin)

        # F-26b: Feature-Auswahl fuer den FEATURE_DIMMER-Modus — aus den Capabilities
        # der gewaehlten Gruppe (vorhandene classify_attr-Feature-Gruppen) befuellt,
        # Fallback Standardliste. Nicht-editierbare ComboBox -> keine Tippfehler.
        feature_attr_cb = QComboBox()
        for _fg in self._available_feature_groups(self.programmer_group):
            feature_attr_cb.addItem(_fg, _fg)
        _fa_idx = feature_attr_cb.findData(self.feature_attr or "Intensity")
        if _fa_idx >= 0:
            feature_attr_cb.setCurrentIndex(_fa_idx)
        feature_attr_cb.setToolTip("Welche Feature-Gruppe der Feature-Dimmer skaliert "
                                   "(Intensity = Helligkeit) — aus den Faehigkeiten der Gruppe.")
        form.addRow("Feature (Feature-Dimmer):", feature_attr_cb)

        # Live-Edit-Slot: bei EFFECT-Modi ohne feste Funktions-ID den Effekt aus
        # diesem Slot bearbeiten (von einem Effekt-Pad gesetzt).
        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext, z. B. MH/MX). EFFECT-Modi ohne "
                                  "feste ID bearbeiten den Effekt aus diesem Slot statt den "
                                  "global aktiven.")
        form.addRow("Live-Edit-Slot (EFFECT):", edit_slot_edit)

        # Tempo-Sync Phase 5: Ziel-Bus (nur Modus Tempo-Bus). "" = aktiver/Default-Bus.
        bus_cb = QComboBox()
        for _bid, _blbl in (("", "(aktiver/Default-Bus)"), ("A", "Bus A"),
                            ("B", "Bus B"), ("C", "Bus C"), ("D", "Bus D")):
            bus_cb.addItem(_blbl, _bid)
        for i in range(bus_cb.count()):
            if bus_cb.itemData(i) == self.tempo_bus_id:
                bus_cb.setCurrentIndex(i)
                break
        bus_cb.setToolTip("Welcher Tempo-Bus vom Fader gesetzt wird (Modus Tempo-Bus).")
        form.addRow("Tempo-Bus:", bus_cb)

        autostart_cb = QCheckBox("bei 0 wirklich stoppen (sonst nur runterregeln)")
        autostart_cb.setChecked(self.effect_autostart)
        autostart_cb.setToolTip(
            "Nur EFFECT-Modi (Intensity/Speed/Param):\n"
            "An  = Fader steuert An/Aus — Wert > 0 startet den Ziel-Effekt,\n"
            "      Wert 0 stoppt ihn wirklich.\n"
            "Aus = Fader regelt nur; den Effekt separat per Taste starten.")
        form.addRow("Effekt An/Aus (EFFECT-Modi):", autostart_cb)

        # ── Wert-Leitplanken (gelten für ALLE Modi) ──
        invert_cb = QCheckBox("Fader invertieren (oben = klein)")
        invert_cb.setChecked(self.invert)
        invert_cb.setToolTip("Dreht die Wirkrichtung um: ganz oben = range_min, "
                             "ganz unten = range_max.")
        form.addRow("Invertieren:", invert_cb)
        rmin = QSpinBox()
        rmin.setRange(0, 255)
        rmin.setValue(self.range_min)
        rmin.setToolTip("Unterer Ausgabewert (Leitplanke), 0–255. Der Fader regelt "
                        "nie darunter — z. B. ein Dimmer der nie ganz aus geht.")
        form.addRow("Wert min:", rmin)
        rmax = QSpinBox()
        rmax.setRange(0, 255)
        rmax.setValue(self.range_max)
        rmax.setToolTip("Oberer Ausgabewert (Leitplanke), 0–255. Der Fader regelt "
                        "nie darüber — z. B. ein Speed-Fader der bei 70% deckelt.")
        form.addRow("Wert max:", rmax)

        univ = QLineEdit(str(self.dmx_universe))
        form.addRow("DMX-Universe (Level-Modus):", univ)
        ch = QLineEdit(str(self.dmx_channel))
        form.addRow("DMX-Kanal (Level-Modus):", ch)
        if self.function_ids:
            slot_text = ", ".join(str(i) for i in self.function_ids)
        elif self.function_id is not None:
            slot_text = str(self.function_id)
        else:
            slot_text = ""
        slot = QLineEdit(slot_text)
        # Roh-Slot/ID-Feld -> unter „Erweitert" (David: Effekte per Name via „Steuert"
        # waehlen, nicht per Slot-Zahl). Bei Playback/Submaster ist es der einzige
        # Eingang und wird automatisch aufgeklappt (siehe _update_slider_fields).
        from src.ui.widgets.collapsible_section import CollapsibleSection
        from PySide6.QtWidgets import QWidget as _QWidget, QVBoxLayout as _QVBoxLayout
        _adv_inner = _QWidget()
        _adv_lay = _QVBoxLayout(_adv_inner)
        _adv_lay.setContentsMargins(0, 0, 0, 0)
        _adv_lay.addWidget(QLabel("Slot/Funktions-ID (Playback/Effekt):"))
        _adv_lay.addWidget(slot)
        _adv_lay.addWidget(QLabel("↳ Effekt-Modi: leer = aktiver Effekt · mehrere IDs mit Komma = Gruppe"))
        adv_section = CollapsibleSection("Erweitert (Slot / Roh-ID)", _adv_inner,
                                         collapsed=True, prefs_key="vc_slider_advanced")
        form.addRow(adv_section)

        # DQ-2: dediziertes Playback-Slot-Feld (eigener Eingang statt function_id-
        # Zweckentfremdung). Nur im PLAYBACK-Modus sichtbar (siehe Sichtbarkeit unten).
        playback_slot_spin = QSpinBox()
        playback_slot_spin.setRange(-1, 999)
        playback_slot_spin.setValue(self.playback_slot if self.playback_slot is not None else -1)
        playback_slot_spin.setSpecialValueText("nicht gesetzt")
        playback_slot_spin.setToolTip("Executor-Slot-Index (0-basiert) fuer den Playback-Modus.")
        form.addRow("Playback Executor-Slot:", playback_slot_spin)

        # ── Kontextabhängige Feld-Sichtbarkeit ──
        # Zeigt je Modus nur die passenden Felder; Beschriftung/Modus + Leitplanken
        # (Invert/Min/Max) bleiben immer sichtbar.
        _EFFECT_MODES = (SliderMode.EFFECT_INTENSITY, SliderMode.EFFECT_SPEED,
                         SliderMode.EFFECT_PARAM)

        def _update_slider_fields():
            m = mode_cb.currentData() or self.mode
            eff = m in _EFFECT_MODES
            vis = {
                param_key_combo: m == SliderMode.EFFECT_PARAM,
                scope_cb:        m in (SliderMode.PROGRAMMER, SliderMode.SUBMASTER),
                prog_attr_combo: m == SliderMode.PROGRAMMER,
                prog_min_spin:   m == SliderMode.PROGRAMMER,
                prog_max_spin:   m == SliderMode.PROGRAMMER,
                group_cb:        m in (SliderMode.PROGRAMMER, SliderMode.GROUP_DIMMER,
                                       SliderMode.SUBMASTER, SliderMode.FEATURE_DIMMER),
                feature_attr_cb: m == SliderMode.FEATURE_DIMMER,
                edit_slot_edit:  eff,
                autostart_cb:    eff,
                univ:            m == SliderMode.LEVEL,
                ch:              m == SliderMode.LEVEL,
                adv_section:        eff,
                playback_slot_spin: m == SliderMode.PLAYBACK,
                bus_cb:             m == SliderMode.TEMPO_BUS,
                target_editor:      eff,
            }
            for widget, show in vis.items():
                form.setRowVisible(widget, bool(show))

        mode_cb.currentIndexChanged.connect(lambda _i: _update_slider_fields())
        _update_slider_fields()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        form.addRow(QLabel("── MIDI CC Bindung ──"))

        midi_cc_spin = QSpinBox()
        midi_cc_spin.setRange(-1, 127)
        midi_cc_spin.setValue(self.midi_cc)
        midi_cc_spin.setSpecialValueText("keine")
        form.addRow("CC-Nummer (-1=keine):", midi_cc_spin)

        midi_ch_spin = QSpinBox()
        midi_ch_spin.setRange(0, 16)
        midi_ch_spin.setValue(self.midi_ch)
        midi_ch_spin.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", midi_ch_spin)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.mode = mode_cb.currentData() or self.mode
            try:
                self.dmx_universe = int(univ.text())
            except ValueError:
                pass
            try:
                self.dmx_channel = int(ch.text())
            except ValueError:
                pass
            ids = []
            for part in slot.text().replace(";", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except ValueError:
                    pass
            # Bei EFFECT-Modi ist die „Steuert"-Liste maßgeblich (IDs + je-Effekt-
            # Parameter); sonst zaehlt das Slot-Feld (Playback-Slot etc.).
            # WICHTIG: param_keys_per_id nur bei BEFUELLTEM Editor ersetzen — sonst
            # (Editor leer / Funktionen nicht geladen) die vorhandenen Parameter
            # behalten und nur auf die noch gueltigen IDs beschraenken (kein Wipen).
            if self.mode in _EFFECT_MODES:
                _eids = target_editor.ids()
                if _eids:
                    ids = _eids
                    self.param_keys_per_id = target_editor.param_keys()
                else:
                    _keep = set(ids)
                    self.param_keys_per_id = {k: v for k, v in self.param_keys_per_id.items()
                                              if k in _keep}
            self.function_ids = ids
            self.function_id = ids[0] if ids else None
            # DQ-2: Playback-Executor-Slot aus dem dedizierten Feld (>=0), sonst None.
            _ps = playback_slot_spin.value()
            self.playback_slot = _ps if _ps >= 0 else None
            _pk_text = param_key_combo.currentText().strip()
            _pk_hit = param_key_combo.findText(_pk_text)
            if _pk_hit >= 0 and param_key_combo.itemData(_pk_hit):
                self.param_key = param_key_combo.itemData(_pk_hit)
            else:
                self.param_key = _pk_text or self.param_key
            self.edit_slot = edit_slot_edit.text().strip()
            self.tempo_bus_id = bus_cb.currentData() or ""
            self.programmer_scope = scope_cb.currentData() or "all"
            self.programmer_group = group_cb.currentText().strip()
            # UXT-01: Ziel-Attribut zurücklesen — Auswahl liefert den rohen Key
            # per itemData, Freitext bleibt wie getippt (leer → alten Wert halten).
            _pa_text = prog_attr_combo.currentText().strip()
            _pa_hit = prog_attr_combo.findText(_pa_text)
            if _pa_hit >= 0 and prog_attr_combo.itemData(_pa_hit):
                self.programmer_attr = prog_attr_combo.itemData(_pa_hit)
            else:
                self.programmer_attr = _pa_text or self.programmer_attr
            self.programmer_min = prog_min_spin.value()
            self.programmer_max = prog_max_spin.value()
            self.feature_attr = feature_attr_cb.currentData() or "Intensity"   # F-26b
            self.effect_autostart = autostart_cb.isChecked()
            self.invert = invert_cb.isChecked()
            self.range_min = rmin.value()
            self.range_max = rmax.value()
            self.midi_cc = midi_cc_spin.value()
            self.midi_ch = midi_ch_spin.value()
            self.update()
            self._post_dialog_mode_sync(_old_mode, _old_group)

    def _reset_group_dimmer(self, group_name: str):
        """Setzt die Fixture-Dimmer einer (alten) Gruppe auf 1.0 zurueck — sonst
        bleibt sie als Geist gedimmt, weil set_group_dimmer pro-fid in
        state.fixture_dimmers schreibt (VCB-19/VCB-34). Tolerant bei fehlender
        Gruppe/State."""
        if not group_name:
            return
        try:
            from src.core.app_state import get_state
            _st = get_state()
            _st.set_group_dimmer(self._group_fids(_st, group_name), 1.0)
        except Exception:
            pass

    def _post_dialog_mode_sync(self, _old_mode, _old_group):
        """Nach dem Properties-Dialog die Submaster-/Gruppen-Dimmer-Slots sofort
        synchronisieren (nicht erst beim naechsten Ziehen). Ausgelagert aus
        _open_properties, damit der Retarget-Pfad (VCB-34) ohne modalen Dialog
        testbar ist.

        - neuer/geaenderter Submaster -> Slot mit aktueller Reichweite setzen;
          weg vom Submaster -> alten Slot raeumen (sonst Geister-Dimmer).
        - GROUP_DIMMER: bei Retarget A->B (beide GROUP_DIMMER, Gruppe gewechselt)
          die alte Gruppe A zuerst zuruecksetzen (VCB-34), dann B anwenden;
          weg vom GROUP_DIMMER -> die (alte) Gruppe zuruecksetzen (VCB-19).
        """
        # ZWEI unabhaengige Phasen statt einer elif-Kette: "alten Modus aufraeumen"
        # und "neuen Modus sofort anwenden" schliessen sich NICHT aus. Die fruehere
        # elif-Kette liess z. B. bei GROUP_DIMMER->SUBMASTER die alte Gruppe als
        # Geister-Dimmer stehen (Zweig 1 beendete die Kette) und wandte bei
        # SUBMASTER->GROUP_DIMMER den neuen Modus nicht sofort an (Zweig 2 endete).
        #
        # Phase 1: Alt-Modus aufraeumen (nur wenn verlassen bzw. Gruppe gewechselt).
        if _old_mode == SliderMode.SUBMASTER and self.mode != SliderMode.SUBMASTER:
            _clear_submaster_slot(id(self))
        if _old_mode == SliderMode.GROUP_DIMMER and (
                self.mode != SliderMode.GROUP_DIMMER
                or (_old_group and _old_group != self.programmer_group)):
            self._reset_group_dimmer(_old_group)         # VCB-19 / VCB-34
        if (_old_mode == SliderMode.FEATURE_DIMMER
                and self.mode != SliderMode.FEATURE_DIMMER):
            _clear_feature_dimmer_slot(id(self))         # F-26b: weg -> Slot raeumen
        # Phase 2: Neu-Modus sofort anwenden (nicht erst beim naechsten Ziehen).
        if self.mode in (SliderMode.SUBMASTER, SliderMode.GROUP_DIMMER,
                         SliderMode.FEATURE_DIMMER):
            self._apply()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["mode"] = self.mode
        d["function_id"] = self.function_id
        d["function_ids"] = list(self.function_ids)
        d["playback_slot"] = self.playback_slot      # DQ-2
        d["dmx_channel"] = self.dmx_channel
        d["dmx_universe"] = self.dmx_universe
        d["programmer_attr"] = self.programmer_attr
        d["programmer_scope"] = self.programmer_scope
        d["programmer_min"] = self.programmer_min
        d["programmer_max"] = self.programmer_max
        d["programmer_group"] = self.programmer_group
        d["feature_attr"] = self.feature_attr      # F-26b

        d["param_key"] = self.param_key
        d["param_keys_per_id"] = {str(k): v for k, v in self.param_keys_per_id.items()}
        d["edit_slot"] = self.edit_slot
        d["tempo_bus_id"] = self.tempo_bus_id
        d["effect_autostart"] = self.effect_autostart
        d["invert"] = self.invert
        d["range_min"] = self.range_min
        d["range_max"] = self.range_max
        d["value"] = self._value
        d["midi_cc"] = self.midi_cc
        d["midi_ch"] = self.midi_ch
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        # VCI-05: unbekannten Modus nicht still schlucken (sonst wirkungsloses Widget),
        # sondern melden und auf LEVEL zurueckfallen.
        _mode = d.get("mode", SliderMode.LEVEL)
        if _mode not in _VALID_SLIDER_MODES:
            print(f"[VCSlider] WARN: unbekannter Modus {_mode!r} -> LEVEL")
            _mode = SliderMode.LEVEL
        self.mode = _mode
        self.function_id = d.get("function_id")
        self.function_ids = [int(i) for i in d.get("function_ids", []) if str(i).strip().lstrip("-").isdigit()]
        # DQ-2: dediziertes playback_slot-Feld. Alt-Shows speicherten den Executor-
        # Slot im PLAYBACK-Modus in function_id -> migrieren, wenn playback_slot fehlt.
        _ps = d.get("playback_slot")
        if _ps is None and self.mode == SliderMode.PLAYBACK:
            _ps = d.get("function_id")
        try:
            self.playback_slot = int(_ps) if _ps is not None else None
        except (TypeError, ValueError):
            self.playback_slot = None
        self.dmx_channel = d.get("dmx_channel", 1)
        self.dmx_universe = d.get("dmx_universe", 1)
        self.programmer_attr = d.get("programmer_attr", "intensity")
        self.programmer_scope = d.get("programmer_scope", "all")
        self.programmer_min = int(d.get("programmer_min", 0))
        self.programmer_max = int(d.get("programmer_max", 255))
        self.programmer_group = d.get("programmer_group", "")
        self.feature_attr = d.get("feature_attr", "Intensity") or "Intensity"   # F-26b
        self.param_key = d.get("param_key", "speed")
        self.param_keys_per_id = {}
        for k, v in (d.get("param_keys_per_id") or {}).items():
            try:
                self.param_keys_per_id[int(k)] = str(v)
            except (TypeError, ValueError):
                pass
        self.edit_slot = d.get("edit_slot", "")
        self.tempo_bus_id = d.get("tempo_bus_id", "") or ""
        self.effect_autostart = bool(d.get("effect_autostart", False))
        self.invert = bool(d.get("invert", False))
        # VCB-27: JSON-null (Key vorhanden, Wert null) -> d.get(default) liefert None
        # -> int(None) crasht. range_min: 0 ist zugleich der Default, `or 0` harmlos.
        self.range_min = int(d.get("range_min") or 0)
        # VCB-33: range_max=0 ist eine GUELTIGE Konfiguration (Fader kappt/mutet die
        # Ausgabe; _effective_value erlaubt min==max). `or 255` wuerde die bewusste 0
        # als „fehlt" behandeln und auf 255 hochsetzen -> Ausgabe nach Reload statt
        # stummem Fader. Nur echtes None/Fehlen faellt auf 255 zurueck.
        _rm = d.get("range_max")
        self.range_max = int(_rm if _rm is not None else 255)
        # VCB-23: Direktzuweisung umging den @value.setter-Clamp -> Ratio>1.0/undef.
        # DMX bei Out-of-Range. Hier klemmen (0..255, int).
        self._value = max(0, min(255, int(d.get("value", 0) or 0)))
        self.midi_cc = d.get("midi_cc", -1)
        self.midi_ch = d.get("midi_ch", 0)
        # VCB-32: Die Direktzuweisung an self._value (oben) umgeht den @value.setter,
        # der _apply() ruft. Modi mit persistentem App-State (GROUP_DIMMER schreibt
        # fixture_dimmers, SUBMASTER einen Output-Slot) muessen ihren geladenen Wert
        # beim Show-Laden aktiv setzen — sonst kommt die Show zu hell hoch, bis der
        # Nutzer den Fader bewegt (fixture_dimmers wird bei load/reset geleert, VCB-05).
        if self.mode in (SliderMode.GROUP_DIMMER, SliderMode.SUBMASTER,
                         SliderMode.FEATURE_DIMMER):
            try:
                self._apply()
            except Exception:
                pass

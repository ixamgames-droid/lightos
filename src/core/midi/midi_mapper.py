"""MIDI mapper with learn mode, inbound actions and outbound LED feedback."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from .midi_manager import (MidiMessage, geraet_passt, get_midi_manager,
                           stabiler_portname, fader_wert)

# Action types (legacy-compatible)
ACTION_EXECUTOR_GO = "executor_go"
ACTION_EXECUTOR_BACK = "executor_back"
ACTION_EXECUTOR_FLASH = "executor_flash"
ACTION_EXECUTOR_FADER = "executor_fader"
ACTION_PROGRAMMER_VAL = "programmer_value"
ACTION_GRAND_MASTER = "grand_master"
ACTION_PAGE_SELECT = "page_select"
ACTION_PAGE_NEXT = "page_next"
ACTION_PAGE_PREV = "page_prev"
ACTION_FUNCTION = "function"      # target_id "function:<id>" -> Scene/Chaser/etc.
# Phase 6: dieselben Effekt-Parameter/Aktionen wie die virtuelle Konsole steuern.
# param-Form: "<key>" (aktiver Effekt) oder "<key>@<function_id>" (fester Effekt).
ACTION_EFFECT_PARAM = "effect_param"    # continuous -> effect_live.set_param_normalized
ACTION_EFFECT_ACTION = "effect_action"  # button     -> effect_live.do_action
ACTION_NONE = "none"

# ── MIDI-14: Motorfader ──────────────────────────────────────────────────────
#: ``MidiOutFeedback.message_type`` einer Motorfader-Rueckmeldung.
FEEDBACK_MOTOR = "pitchbend"
#: Solange vom Fader Werte kommen (die Hand bewegt ihn) und diese Zeit danach,
#: sendet LightOS nichts an seinen Motor — er arbeitete sonst gegen die Hand.
MOTOR_HAND_RUHE_S = 0.35
#: Was in dieser Zeit NACH einer eigenen Sendung vom selben Fader zurueckkommt,
#: ist der Bericht des Pults ueber die Motorfahrt und keine Eingabe. Ohne diese
#: Sperre durchliefe ein Executor-Fader, der von 0 auf 100 % springt (Seiten-
#: wechsel), am Ausgang alle Zwischenstellungen, die der Motor meldet.
MOTOR_ECHO_FENSTER_S = 0.25
#: Ab dieser Aenderung der Stellung (0..1) wird ein Motorfader nachgefuehrt —
#: feiner als die 1 % der LED-Rueckmeldung, damit eine Ueberblendung nicht ruckt.
MOTOR_SCHRITT = 0.002
#: Ziele, deren Stand sich zuruecklesen laesst. Bei allen anderen stufenlosen
#: Zielen (Programmer-Wert, Effekt-Parameter) kennt nur der Fader selbst seine
#: Stellung — dort wird nichts aus einem geratenen Zustand nachgefuehrt.
_MOTOR_LESBAR = (ACTION_EXECUTOR_FADER, ACTION_GRAND_MASTER)

# ── MIDI-15: Beruehrungs-Note ────────────────────────────────────────────────
#: Mackie Control: der Beruehrungssensor von Fader n (Pitchbend auf Kanal n,
#: 1..9, 9 = Master) meldet sich als Note 104..112 auf MIDI-Kanal 1 —
#: Anschlag > 0 = beruehrt, 0 (oder Note-Off) = losgelassen.
TOUCH_KANAL = 1
TOUCH_NOTE_FADER_1 = 104


def mackie_touch_note(fader_kanal: int) -> int | None:
    """Die Beruehrungs-Note zum Pitchbend-Kanal eines Mackie-Faders, oder
    ``None`` ausserhalb von 1..9 (dort kennt das Protokoll keine)."""
    k = int(fader_kanal)
    return TOUCH_NOTE_FADER_1 + k - 1 if 1 <= k <= 9 else None


def _parse_effect_param(param: str) -> tuple[str, int | None]:
    """'<key>[@<fid>]' -> (key, fid|None)."""
    key, _, fid = str(param or "").partition("@")
    fid = fid.strip()
    return key.strip(), (int(fid) if fid.lstrip("-").isdigit() else None)

BUTTON_TOGGLE = "toggle"
BUTTON_FLASH = "flash"
BUTTON_CONTINUOUS = "continuous"
# Portname, unter dem per UDP empfangene MSC-Befehle im Monitor erscheinen.
MSC_UDP_PORT_NAME = "MSC/UDP"
# MIDI-2: reine Druck-Aktion. Jeder Druck loest genau einmal aus, Loslassen tut
# nichts. Fuer GO/BACK der einzige zulaessige Modus — frueher war ``toggle`` die
# Vorgabe, und jeder ZWEITE GO-Druck schaltete den Toggle aus und loeste BACK
# aus (im Flash-Modus schon das Loslassen).
BUTTON_PRESS = "press"

# Aktionen, die nur auf das Druecken reagieren — unabhaengig vom gespeicherten
# Modus (Altbestand mit toggle/flash wird beim Laden normalisiert).
_PRESS_ONLY_ACTIONS = (ACTION_EXECUTOR_GO, ACTION_EXECUTOR_BACK)


def _clamp_7bit(value: int) -> int:
    return max(0, min(127, int(value)))


def normalize_button_mode(action: str, mode: str) -> str:
    """GO/BACK sind immer Druck-Aktionen; alle anderen Modi bleiben wie sie sind.

    Umgekehrt ist ``press`` nur fuer GO/BACK gueltig: wird ein GO-Mapping auf
    ein anderes Ziel umgestellt (Flash, Funktion ...), faellt der Modus auf die
    Vorgabe des neuen Ziels zurueck — sonst wuerde ein Flash beim Loslassen nie
    geloest und eine Funktion nie gestoppt.
    """
    if action in _PRESS_ONLY_ACTIONS:
        return BUTTON_PRESS
    if mode == BUTTON_PRESS:
        return _infer_button_mode(action)
    return mode


_normalize_button_mode = normalize_button_mode


def _infer_button_mode(action: str) -> str:
    if action in _PRESS_ONLY_ACTIONS:
        return BUTTON_PRESS
    if action in (ACTION_EXECUTOR_FADER, ACTION_PROGRAMMER_VAL, ACTION_GRAND_MASTER,
                  ACTION_EFFECT_PARAM):
        return BUTTON_CONTINUOUS
    if action in (ACTION_EXECUTOR_FLASH, ACTION_EFFECT_ACTION):
        return BUTTON_FLASH   # Effekt-Aktion: einmal pro Tastendruck feuern
    return BUTTON_TOGGLE


def _target_from_action(action: str, param: str) -> str:
    if action == ACTION_NONE:
        return ""
    if param:
        return f"{action}:{param}"
    return action


def _action_from_target(target: str) -> tuple[str, str]:
    target = str(target or "").strip()
    if not target:
        return ACTION_NONE, ""
    if ":" not in target:
        return target, ""
    action, param = target.split(":", 1)
    return action.strip(), param.strip()


def _msg_type_from_binding(binding_type: str) -> str:
    if binding_type == "pitchbend":             # MIDI-10
        return "pitchbend"
    return "cc" if binding_type == "cc" else "note_on"


def _binding_type_from_msg_type(msg_type: str) -> str:
    """Flaches Feld ``msg_type`` (note_on/cc/pitchbend) -> Typ der Bindung.
    EINE Stelle statt dreier ``"cc" if … else "note"``, die Pitchbend zu einer
    Note gemacht haetten (MIDI-10)."""
    if msg_type == "pitchbend":
        return "pitchbend"
    return "cc" if msg_type == "cc" else "note"


# --- Konflikt-Erkennung beim MIDI-Learn (STAB-12, Option B) -----------------
# Nicht-behaviorale Warnung: eine Note/CC kann gleichzeitig ein globales
# MidiMapper-Mapping UND ein VC-Widget-Binding treffen (beide haengen am selben
# Bus, kein Konsumierungs-Protokoll). Damit der Mapper beim Learn cross-Ebene
# warnen kann, OHNE UI-Code zu importieren (Layering: core kennt UI nicht),
# registriert die VC-Canvas hier einen Provider, der ihre aktuellen Widget-
# Bindungen liefert. Descriptor je Bindung: (label, msg_type, channel, data1).

_vc_binding_providers: list[Callable[[], list]] = []


def register_vc_binding_provider(provider: Callable[[], list]) -> None:
    """VC-Canvas meldet einen Provider an, der ihre MIDI-Widget-Bindungen liefert."""
    if provider not in _vc_binding_providers:
        _vc_binding_providers.append(provider)


def unregister_vc_binding_provider(provider: Callable[[], list]) -> None:
    try:
        _vc_binding_providers.remove(provider)
    except ValueError:
        pass


def _iter_vc_bindings() -> list[tuple]:
    """Alle aktuell registrierten VC-Widget-Bindungen einsammeln (robust)."""
    out: list[tuple] = []
    for provider in list(_vc_binding_providers):
        try:
            for item in (provider() or []):
                out.append(tuple(item))
        except Exception:
            pass
    return out


def _binding_family(msg_type: str) -> str:
    """note_on/note_off/note -> 'note', cc -> 'cc', pitchbend -> 'pitchbend'
    (Match-Familie)."""
    t = str(msg_type)
    if t == "pitchbend":
        return "pitchbend"
    return "cc" if t == "cc" else "note"


def _bindings_overlap(type_a, ch_a, d1_a, type_b, ch_b, d1_b) -> bool:
    """True, wenn zwei Bindungen auf DIESELBE eingehende Nachricht feuern wuerden.

    Gleiche data1, gleiche Familie (note vs cc), ueberlappender Kanal
    (0 = alle Kanaele). Deckt sich mit MidiInBinding.matches /
    midi_binding_matches (note_on bindet auch note_off).

    MIDI-10: ein Pitchbend-Fader ist sein Kanal — ``data1`` gehoert dort zum
    Wert und zaehlt nicht."""
    fam_a, fam_b = _binding_family(type_a), _binding_family(type_b)
    if fam_a != fam_b:
        return False
    if fam_a != "pitchbend":
        try:
            if int(d1_a) != int(d1_b):
                return False
        except (TypeError, ValueError):
            return False
    ca, cb = int(ch_a or 0), int(ch_b or 0)
    if ca != 0 and cb != 0 and ca != cb:
        return False
    return True


def _offene_eingaenge() -> list[str]:
    """Offene Eingaenge des Managers — fuer das Ordinal gleicher Geraete
    (MIDI-3). Ohne Manager/Methode (Tests, Fakes) eine leere Liste."""
    try:
        fn = getattr(get_midi_manager(), "offene_eingaenge", None)
        return list(fn()) if callable(fn) else []
    except Exception:
        return []


@dataclass
class MidiInBinding:
    """Incoming MIDI trigger definition."""

    device: str = ""
    channel: int = 1
    trigger_id: int = 0
    message_type: str = "note"  # note, cc oder pitchbend (MIDI-10)

    def matches(self, msg: MidiMessage, geschwister=None) -> bool:
        # MIDI-3: ueber den Geraetenamen, nicht ueber die ALSA-Nummer.
        # ``geschwister`` = Geraetenamen aller Mappings (CDX-58: zwei
        # baugleiche Pulte mit Alt-Nummern bleiben getrennt).
        if self.device and not geraet_passt(self.device, msg.port_name,
                                            _offene_eingaenge(), geschwister):
            return False
        if self.channel != 0 and self.channel != msg.channel:
            return False
        if self.message_type == "pitchbend":
            # MIDI-10: je Fader ein Kanal; ``data1`` sind die unteren 7 Bit des
            # Werts und aendern sich mit jeder Bewegung.
            return msg.msg_type == "pitchbend"
        if self.trigger_id != msg.data1:
            return False
        if self.message_type == "cc":
            return msg.msg_type == "cc"
        if self.message_type == "note":
            return msg.msg_type in ("note_on", "note_off")
        return msg.msg_type == self.message_type

    @classmethod
    def from_dict(cls, data: dict) -> "MidiInBinding":
        if not isinstance(data, dict):
            return cls()
        return cls(
            device=str(data.get("device", "")),
            channel=int(data.get("channel", 1)),
            trigger_id=int(data.get("trigger_id", 0)),
            message_type=str(data.get("message_type", "note")),
        )

    @classmethod
    def from_message(cls, msg: MidiMessage) -> "MidiInBinding":
        pitchbend = msg.msg_type == "pitchbend"
        return cls(
            device=stabiler_portname(msg.port_name, _offene_eingaenge()),
            channel=msg.channel,
            # MIDI-10: bei Pitchbend ist data1 Teil des Werts, nicht der Kennung.
            trigger_id=0 if pitchbend else msg.data1,
            message_type=_binding_type_from_msg_type(msg.msg_type),
        )

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "channel": int(self.channel),
            "trigger_id": int(self.trigger_id),
            "message_type": self.message_type,
        }


@dataclass
class MidiOutFeedback:
    """Outgoing MIDI feedback for LED/controller state."""

    device: str = ""
    channel: int = 1
    trigger_id: int = -1
    message_type: str = "note"  # note or cc
    state_off: int = 0
    state_on: int = 127
    brightness: int | None = None
    aux_channel: int | None = None
    #: MIDI-15 (nur Motorfader): Note des Beruehrungssensors auf
    #: ``TOUCH_KANAL``; ``None`` = der Fader hat keinen / wird nicht ausgewertet.
    touch_note: int | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "MidiOutFeedback | None":
        if not isinstance(data, dict):
            return None
        brightness = data.get("brightness")
        aux_channel = data.get("aux_channel")
        touch_note = data.get("touch_note")
        return cls(
            device=str(data.get("device", "")),
            channel=int(data.get("channel", 1)),
            trigger_id=int(data.get("trigger_id", -1)),
            message_type=str(data.get("message_type", "note")),
            state_off=_clamp_7bit(int(data.get("state_off", 0))),
            state_on=_clamp_7bit(int(data.get("state_on", 127))),
            brightness=None if brightness is None else _clamp_7bit(int(brightness)),
            aux_channel=None if aux_channel is None else int(aux_channel),
            touch_note=None if touch_note is None else _clamp_7bit(int(touch_note)),
        )

    def to_dict(self) -> dict:
        daten = {
            "device": self.device,
            "channel": int(self.channel),
            "trigger_id": int(self.trigger_id),
            "message_type": self.message_type,
            "state_off": int(self.state_off),
            "state_on": int(self.state_on),
            "brightness": self.brightness,
            "aux_channel": self.aux_channel,
        }
        # MIDI-15: nur schreiben, wenn gesetzt — gespeicherte Rueckmeldungen
        # ohne Beruehrungs-Note bleiben Zeichen fuer Zeichen gleich.
        if self.touch_note is not None:
            daten["touch_note"] = int(self.touch_note)
        return daten


def ist_motorfader(mapping) -> bool:
    """MIDI-14: fuehrt dieses Mapping einen Motorfader nach? Das tut es, wenn
    seine Rueckmeldung ``pitchbend`` heisst UND es selbst ein Pitchbend-Fader
    ist — die Rueckmeldung geht auf demselben Kanal an denselben Fader."""
    fb = getattr(mapping, "midi_out", None)
    return (fb is not None and fb.message_type == FEEDBACK_MOTOR
            and getattr(mapping, "msg_type", "") == "pitchbend")


def motor_rueckmeldung(mapping, geraet: str = "", touch: bool = True) -> "MidiOutFeedback":
    """MIDI-14: die Rueckmeldung, die den Motorfader dieses Mappings nachfuehrt
    — derselbe Kanal wie der Fader; ``geraet`` = Ausgang des Pults (leer = der
    gemeinsame Ausgang). MIDI-15: mit ``touch`` wird die Beruehrungs-Note nach
    Mackie-Belegung eingetragen (Kanal 1..9)."""
    return MidiOutFeedback(
        device=str(geraet or ""), channel=int(mapping.channel), trigger_id=-1,
        message_type=FEEDBACK_MOTOR,
        touch_note=mackie_touch_note(mapping.channel) if touch else None)


@dataclass
class MidiMapping:
    """Mapping object with modern config shape plus legacy flat fields."""

    name: str = "Mapping"
    msg_type: str = "note_on"  # legacy
    channel: int = 1  # legacy
    data1: int = 0  # legacy
    action: str = ACTION_NONE  # legacy
    param: str = ""  # legacy
    port_filter: str = ""  # legacy
    target_id: str = ""
    button_mode: str = ""
    midi_in: MidiInBinding = field(default_factory=MidiInBinding)
    midi_out: MidiOutFeedback | None = None
    mapping_id: str = field(default_factory=lambda: uuid4().hex)
    continuous_min: float = 0.0
    continuous_max: float = 1.0

    def __post_init__(self):
        if isinstance(self.midi_in, dict):
            self.midi_in = MidiInBinding.from_dict(self.midi_in)
        if isinstance(self.midi_out, dict):
            self.midi_out = MidiOutFeedback.from_dict(self.midi_out)

        if not self.target_id:
            self.target_id = _target_from_action(self.action, self.param)
        else:
            self.action, self.param = _action_from_target(self.target_id)

        if not self.button_mode:
            self.button_mode = _infer_button_mode(self.action)
        # MIDI-2-Migration: gespeicherte GO/BACK-Mappings mit toggle/flash
        # (alte Vorgabe) werden hier auf Druck normalisiert — gilt fuer
        # Konstruktor, from_config_dict und das flache Legacy-Format.
        self.button_mode = _normalize_button_mode(self.action, self.button_mode)

        # Legacy -> structured sync (kept for editor compatibility).
        legacy_binding_type = _binding_type_from_msg_type(self.msg_type)
        self.midi_in = MidiInBinding(
            device=self.port_filter,
            channel=int(self.channel),
            trigger_id=int(self.data1),
            message_type=legacy_binding_type,
        )

        # MIDI-10: ein Pitchbend-Fader hat keine Nummer. ``data1`` (0) als
        # Rueckmelde-Note zu nehmen, schaltete am Mackie-Pult die LED von Note 0.
        if (self.midi_out and self.midi_out.trigger_id < 0
                and self.msg_type != "pitchbend"):
            self.midi_out.trigger_id = int(self.data1)

    @classmethod
    def from_config_dict(cls, data: dict) -> "MidiMapping":
        midi_in = MidiInBinding.from_dict(data.get("midi_in", {}))
        midi_out = MidiOutFeedback.from_dict(data.get("midi_out"))
        target = str(data.get("target", ""))
        action, param = _action_from_target(target)
        msg_type = _msg_type_from_binding(midi_in.message_type)
        return cls(
            name=str(data.get("name", "Mapping")),
            msg_type=msg_type,
            channel=int(midi_in.channel),
            data1=int(midi_in.trigger_id),
            action=action,
            param=param,
            port_filter=str(midi_in.device),
            target_id=target,
            button_mode=str(data.get("button_mode", _infer_button_mode(action))),
            midi_in=midi_in,
            midi_out=midi_out,
            mapping_id=str(data.get("id") or uuid4().hex),
            continuous_min=float(data.get("continuous_min", 0.0)),
            continuous_max=float(data.get("continuous_max", 1.0)),
        )

    def to_config_dict(self) -> dict:
        return {
            "id": self.mapping_id,
            "name": self.name,
            "target": self.target_id or _target_from_action(self.action, self.param),
            "midi_in": self.midi_in.to_dict(),
            "button_mode": self.button_mode or _infer_button_mode(self.action),
            "midi_out": self.midi_out.to_dict() if self.midi_out else None,
            "continuous_min": float(self.continuous_min),
            "continuous_max": float(self.continuous_max),
        }

    def set_from_learn_message(self, msg: MidiMessage):
        self.msg_type = _msg_type_from_binding(
            _binding_type_from_msg_type(msg.msg_type))
        self.channel = int(msg.channel)
        # MIDI-10: Pitchbend hat keine Nummer (data1 = untere Bits des Werts).
        self.data1 = 0 if msg.msg_type == "pitchbend" else int(msg.data1)
        self.midi_in = MidiInBinding.from_message(msg)
        self.port_filter = self.midi_in.device
        if (self.midi_out and self.midi_out.trigger_id < 0
                and self.msg_type != "pitchbend"):
            self.midi_out.trigger_id = self.data1


class MidiMapper:
    """Bidirectional MIDI mapping engine (inbound + outbound feedback)."""

    # MIDI-10 (Lernen): als Klassen-Vorgabe, damit auch ein ohne __init__
    # gebautes Objekt (Tests) sie hat. Siehe start_learn.
    _learn_pitchbend = False
    _learn_note: MidiMessage | None = None
    # MIDI-14: ebenfalls als Klassen-Vorgabe (Objekte ohne __init__ in Tests).
    _uhr = staticmethod(time.monotonic)

    def __init__(self, app_state):
        self._state = app_state
        self._mappings: list[MidiMapping] = []
        self._learn_mode = False
        self._learn_callback = None
        self._state_callbacks: list[Callable[[str, dict], None]] = []
        # UI-Hook fuer Learn-Konflikt-Warnungen (Option B, rein additiv).
        self._conflict_callbacks: list[Callable[[dict], None]] = []
        self._toggle_states: dict[str, bool] = {}
        # MIDI-4: _on_midi laeuft im MIDI-Empfangsthread, add/replace/remove
        # und das Feedback-Polling in anderen Threads.
        self._toggle_lock = threading.Lock()
        self._feedback_state_cache: dict[str, float] = {}
        self._feedback_output_cache: dict[str, int] = {}
        self._feedback_last_send_ts: dict[str, float] = {}
        # MIDI-14: je Motorfader (mapping_id) — wann zuletzt die Hand einen
        # Wert schickte, wann und was LightOS zuletzt an den Motor sandte, und
        # was nach der Hand-Ruhe noch nachzutragen ist. Geschrieben aus dem
        # MIDI-Empfangsthread UND der Rueckmelde-Schleife.
        self._motor_lock = threading.Lock()
        self._motor_hand_ts: dict[str, float] = {}
        self._motor_send_ts: dict[str, float] = {}
        self._motor_wert: dict[str, int] = {}
        self._motor_offen: dict[str, tuple[MidiMapping, float]] = {}
        # MIDI-15: mapping_id der Motorfader, die gerade beruehrt werden, und
        # die Stellung (0..1), die jeder Fader zuletzt selbst gemeldet hat.
        self._motor_beruehrt: set[str] = set()
        self._motor_hand_wert: dict[str, float] = {}
        self._feedback_queue: queue.Queue[tuple[MidiMapping, float]] = queue.Queue(maxsize=2048)
        self._feedback_running = True
        self._last_state_poll_ts = 0.0
        self._feedback_thread = threading.Thread(
            target=self._feedback_loop, daemon=True, name="MidiFeedbackEngine"
        )
        self._feedback_thread.start()

        midi = get_midi_manager()
        midi.subscribe(self._on_midi)
        self._hook_state_sources()

    # Mapping management -------------------------------------------------

    def add_mapping(self, mapping: MidiMapping):
        if not mapping.mapping_id:
            mapping.mapping_id = uuid4().hex
        if mapping.button_mode == BUTTON_TOGGLE:
            with self._toggle_lock:
                self._toggle_states.setdefault(mapping.mapping_id, False)
        self._mappings.append(mapping)
        self._emit_mapping_state(mapping, self._read_mapping_state(mapping))

    def remove_mapping(self, idx: int):
        if 0 <= idx < len(self._mappings):
            mapping = self._mappings.pop(idx)
            with self._toggle_lock:
                self._toggle_states.pop(mapping.mapping_id, None)
            self._feedback_state_cache.pop(mapping.mapping_id, None)
            self._motor_vergessen(mapping.mapping_id)

    def get_mappings(self) -> list[MidiMapping]:
        return list(self._mappings)

    def replace_mappings(self, mappings: list[MidiMapping]):
        self._mappings = list(mappings)
        with self._toggle_lock:
            self._toggle_states = {
                m.mapping_id: False for m in self._mappings
                if m.button_mode == BUTTON_TOGGLE}
        self._feedback_state_cache = {}
        self._motor_vergessen()
        for mapping in self._mappings:
            self._emit_mapping_state(mapping, self._read_mapping_state(mapping))

    # Learn mode ---------------------------------------------------------

    def start_learn(self, callback, *, pitchbend: bool = False):
        """Wait for the next note/cc message and return it to callback(msg).

        MIDI-10: mit ``pitchbend=True`` lernt der Aufrufer auch Pitchbend-Fader
        (Mackie Control, X-Touch). Deren Beruehrungssensor schickt VOR der
        ersten Bewegung eine Note; damit nicht die statt des Faders gelernt
        wird, zaehlt eine Note dann erst beim Loslassen — kommt vorher ein
        Pitchbend, gewinnt der Fader. Ohne den Schalter bleibt alles wie
        bisher: Pitchbend wird uebergangen, die erste Note zaehlt sofort
        (so wollen es die Aufrufer, die nur Tasten binden)."""
        self._learn_note = None
        self._learn_pitchbend = bool(pitchbend)
        self._learn_mode = True
        self._learn_callback = callback

    def stop_learn(self):
        self._learn_mode = False
        self._learn_callback = None
        self._learn_note = None

    def _lern_auswahl(self, msg: MidiMessage):
        """Die Nachricht, die das Lernen beendet — oder ``None`` (weiter warten)."""
        art = msg.msg_type
        if not self._learn_pitchbend:
            return msg if art in ("note_on", "note_off", "cc") else None
        if art in ("pitchbend", "cc"):
            return msg
        if art not in ("note_on", "note_off"):
            return None
        wartend = self._learn_note
        if art == "note_on" and msg.data2 > 0:
            if wartend is not None:
                return wartend          # zweite Taste, oder Geraet ohne Note-Off
            self._learn_note = msg      # Taste oder Beruehrung? Abwarten.
            return None
        # Loslassen: die gehaltene Note gilt; ohne gehaltene wie bisher.
        return wartend if wartend is not None else msg

    # Learn-Konflikt-Warnung (STAB-12, Option B) -------------------------

    def subscribe_conflict(self, callback: Callable[[dict], None]) -> None:
        """UI-Hook: callback(payload) bei erkanntem Learn-Konflikt (optional)."""
        if callback not in self._conflict_callbacks:
            self._conflict_callbacks.append(callback)

    def find_binding_conflicts(self, msg_type, channel, data1,
                               *, exclude_mapping_id=None) -> list[dict]:
        """Zu einer eingehenden Note/CC-Bindung ALLE bereits belegten Bindungen
        liefern, die auf DIESELBE Nachricht feuern wuerden: globale Mapper-
        Mappings UND VC-Widget-Bindungen (ueber registrierte Provider).

        Rein informativ (Option B) — aendert das Dispatch-Verhalten NICHT."""
        conflicts: list[dict] = []
        # 1) Globale Mapper-Mappings.
        for m in self._mappings:
            if exclude_mapping_id and m.mapping_id == exclude_mapping_id:
                continue
            b = m.midi_in
            if _bindings_overlap(msg_type, channel, data1,
                                 b.message_type, b.channel, b.trigger_id):
                conflicts.append({
                    "source": "global",
                    "label": m.name or m.target_id or m.action or "Mapping",
                    "msg_type": b.message_type,
                    "channel": int(b.channel),
                    "data1": int(b.trigger_id),
                })
        # 2) VC-Widget-Bindungen (ueber Provider von der VC-Canvas).
        for item in _iter_vc_bindings():
            try:
                label, b_type, b_ch, b_d1 = item
            except (ValueError, TypeError):
                continue
            if _bindings_overlap(msg_type, channel, data1, b_type, b_ch, b_d1):
                conflicts.append({
                    "source": "vc",
                    "label": str(label),
                    "msg_type": str(b_type),
                    "channel": int(b_ch or 0),
                    "data1": int(b_d1),
                })
        return conflicts

    def check_and_warn_conflicts(self, msg_type, channel, data1,
                                 *, learned_label="Learn",
                                 exclude_mapping_id=None) -> list[dict]:
        """Konflikte suchen und (falls vorhanden) warnen: print + optionaler
        UI-Callback. Gibt die gefundenen Konflikte zurueck."""
        conflicts = self.find_binding_conflicts(
            msg_type, channel, data1, exclude_mapping_id=exclude_mapping_id)
        if not conflicts:
            return conflicts
        fam = _binding_family(msg_type)
        ident = f"{'CC' if fam == 'cc' else 'Note'} {int(data1)} (CH{int(channel or 0)})"
        for c in conflicts:
            print(f"[midi_mapper] Konflikt-Warnung ({learned_label}): {ident} ist "
                  f"bereits an {c['source']}:{c['label']} gebunden — beide feuern "
                  f"gleichzeitig.")
        payload = {
            "learned": learned_label,
            "msg_type": msg_type,
            "channel": int(channel or 0),
            "data1": int(data1),
            "conflicts": conflicts,
        }
        for cb in list(self._conflict_callbacks):
            try:
                cb(payload)
            except Exception:
                pass
        return conflicts

    # Inbound engine -----------------------------------------------------

    def _on_midi(self, msg: MidiMessage):
        if msg.msg_type == "msc":
            # MIDI-5/NET-14: MSC ist kein lernbares Mapping, sondern ein fester
            # Befehlssatz (Cue-Liste -> Executor). Auch im Learn-Modus nicht
            # verschlucken.
            self.handle_msc(msg.msc)
            return
        self._motor_beruehrung(msg)         # MIDI-15, auch waehrend des Lernens
        if self._learn_mode and self._learn_callback:
            gelernt = self._lern_auswahl(msg)
            if gelernt is not None:
                callback = self._learn_callback
                self._learn_mode = False
                self._learn_callback = None
                self._learn_note = None
                # Konflikt-Check VOR dem Anwenden der Bindung: so zaehlt die
                # gerade gelernte Zeile sich nicht selbst mit (Option B).
                try:
                    self.check_and_warn_conflicts(
                        gelernt.msg_type, gelernt.channel, gelernt.data1,
                        learned_label="Mapper-Learn")
                except Exception:
                    pass
                callback(gelernt)
            return

        # MIDI-4: jede Zeile einzeln absichern — eine kaputte Zeile darf die
        # anderen Zeilen derselben Note nicht abbrechen. Schnappschuss der
        # Liste, weil die UI sie parallel ersetzen kann.
        mappings = list(self._mappings)
        geraete = {m.midi_in.device for m in mappings
                   if getattr(m.midi_in, "device", "")}
        for mapping in mappings:
            try:
                if not mapping.midi_in.matches(msg, geraete):
                    continue
                self._handle_inbound_mapping(mapping, msg)
            except Exception as e:
                try:
                    from src.core.diagnose_log import melde_still
                    melde_still("midi.mapping", e,
                                text=f"Mapping {mapping.name or mapping.action}")
                except Exception:
                    pass

    # ── MIDI Show Control (MIDI-5 / NET-14) ──────────────────────────────────

    def _msc_executor(self, cue_list: str):
        """Cue-Liste -> Executor der aktuellen Page: Nummer = Slot, sonst
        Name (Executor-Beschriftung oder Name der gebundenen Cueliste).
        Leere Liste = Executor 1."""
        pe = self._state.playback_engine
        if pe is None:
            return None
        key = (cue_list or "").strip()
        if not key:
            key = "1"
        try:
            slot = int(float(key))
        except ValueError:
            slot = None
        if slot is not None:
            if slot < 1:
                return None
            try:
                return pe.get_executor(slot)
            except (IndexError, ValueError):
                return None
        name = key.casefold()
        for ex in list(pe.executors):
            stack_name = getattr(getattr(ex, "stack", None), "name", "") or ""
            if (str(ex.label).casefold() == name
                    or str(stack_name).casefold() == name):
                return ex
        return None

    def _msc_set(self, cmd) -> bool:
        """SET -> Executor-Fader. Die Lesart der Datenbytes bestimmt
        ``MscSettings.set_layout``:

        - ``grandma``: Byte 0 = Executor (ab 0), Byte 1 = Seite (ab 1) ->
          Executor-Seite von LightOS; Wert = grob (Prozent) + fein/128.
        - ``standard``: 14-bit-Regler n -> Executor n+1 der aktuellen Seite,
          Wert 14 bit.

        Einen Executor, den es nicht gibt, nicht still schlucken: gedrosselte
        Meldung (je Ziel einmal), sonst sucht man am Pult ohne Anhaltspunkt."""
        from . import msc as _msc
        from src.core.diagnose_log import melde_still
        pe = self._state.playback_engine
        if pe is None or cmd.control is None:
            return False
        seiten = getattr(pe, "pages", None)
        if _msc.get_settings().set_layout == _msc.SET_GRANDMA:
            gma = _msc.set_grandma(getattr(cmd, "set_data", ()) or ())
            if gma is None:
                return False
            slot, seite, wert = gma
            n_seiten = len(seiten) if seiten is not None else 1
            if not 1 <= seite <= n_seiten:
                melde_still("midi.msc.set", text=(
                    f"SET (grandMA): Seite {seite} gibt es nicht "
                    f"(1..{n_seiten}) — Executor {slot} nicht gesetzt. Sendet "
                    "das Pult 14-Bit-Regler, die SET-Belegung auf "
                    "'Standard' stellen."))
                return False
            n_slots = len(seiten[seite - 1]) if seiten is not None else len(pe.executors)
            if not 1 <= slot <= n_slots:
                melde_still("midi.msc.set", text=(
                    f"SET (grandMA): Executor {slot} auf Seite {seite} gibt es "
                    f"nicht (1..{n_slots})"))
                return False
            ex = (seiten[seite - 1][slot - 1] if seiten is not None
                  else pe.get_executor(slot))
        else:
            slot = int(cmd.control) + 1
            n_slots = len(pe.executors)
            if not 1 <= slot <= n_slots:
                melde_still("midi.msc.set", text=(
                    f"SET (Standard): Regler {int(cmd.control)} -> Executor "
                    f"{slot} gibt es nicht (1..{n_slots}). Sendet eine grandMA, "
                    "die SET-Belegung auf 'grandMA (Executor, Seite)' stellen."))
                return False
            ex = pe.get_executor(slot)
            wert = max(0.0, min(1.0, (cmd.value or 0) / 16383.0))
        ex.fader_value = wert
        return True

    def subscribe_msc(self, callback) -> None:
        """Beobachter fuer MSC-Befehle, die NICHT ueber einen MIDI-Eingang
        kommen (GMA-MSC per UDP) — sonst fehlen sie im MIDI-Monitor. Der
        Callback bekommt eine ``MidiMessage`` (Port ``MSC/UDP``) und laeuft im
        Empfangsthread."""
        if not hasattr(self, "_msc_listeners"):
            self._msc_listeners = []
        if callback not in self._msc_listeners:
            self._msc_listeners.append(callback)

    def unsubscribe_msc(self, callback) -> None:
        try:
            getattr(self, "_msc_listeners", []).remove(callback)
        except ValueError:
            pass

    def _on_msc_udp(self, cmd) -> bool:
        """NET-14: per UDP empfangenen Befehl ausfuehren UND den Beobachtern
        (MIDI-Monitor) zeigen."""
        ok = self.handle_msc(cmd)
        if cmd is not None:
            msg = MidiMessage(MSC_UDP_PORT_NAME, 0, "msc", cmd.command, 0, msc=cmd)
            for cb in list(getattr(self, "_msc_listeners", ())):
                try:
                    cb(msg)
                except Exception as e:
                    from src.core.diagnose_log import melde_still
                    melde_still("midi.msc", e, text="Monitor")
        return ok

    def handle_msc(self, cmd) -> bool:
        """Fuehrt ein ``MscCommand`` aus. True, wenn etwas ausgeloest wurde."""
        from . import msc as _msc
        if cmd is None:
            return False
        try:
            c = cmd.command
            if c in (_msc.GO, _msc.TIMED_GO, _msc.RESUME, _msc.LOAD):
                ex = self._msc_executor(cmd.cue_list)
                if ex is None or ex.stack is None:
                    return False
                if c == _msc.LOAD:
                    return False      # Vorladen kennt LightOS nicht
                if cmd.cue:
                    ex.stack.go_to(float(cmd.cue))
                else:
                    ex.press_btn("go")
                return True
            if c in (_msc.STOP, _msc.GO_OFF):
                if not (cmd.cue_list or "").strip():
                    # MSC-Spezifikation: ohne Cue-Liste gilt der Befehl fuer
                    # ALLE laufenden Listen (nicht nur Executor 1).
                    pe = self._state.playback_engine
                    if pe is None:
                        return False
                    pe.stop_all()
                    return True
                ex = self._msc_executor(cmd.cue_list)
                if ex is None or ex.stack is None:
                    return False
                ex.press_btn("stop")
                return True
            if c == _msc.SET:
                return self._msc_set(cmd)
            if c == _msc.FIRE:
                # Makro n -> Funktion (Szene/Chaser) mit ID n starten.
                fm = getattr(self._state, "function_manager", None)
                if fm is None or cmd.macro is None:
                    return False
                fm.start(int(cmd.macro))
                return True
            if c == _msc.ALL_OFF:
                pe = self._state.playback_engine
                if pe is None:
                    return False
                pe.stop_all()
                return True
        except Exception as e:
            from src.core.diagnose_log import melde_still
            melde_still("midi.msc", e, text=getattr(cmd, "name", ""))
        return False

    def _handle_inbound_mapping(self, mapping: MidiMapping, msg: MidiMessage):
        mode = _normalize_button_mode(
            mapping.action,
            (mapping.button_mode or _infer_button_mode(mapping.action)).lower())
        if mode == BUTTON_CONTINUOUS:
            if self._motor_eingang(mapping, msg):
                return                      # MIDI-14: Bericht der Motorfahrt
            value = fader_wert(msg)         # MIDI-10: Pitchbend mit 14 Bit
            self._execute_continuous(mapping, value)
            self._emit_mapping_state(mapping, value)
            return

        # Ein Fader (CC oder Pitchbend) an einer Tasten-Aktion: obere Haelfte
        # = gedrueckt. data2 ist bei Pitchbend das obere Byte, die Schwelle 64
        # liegt also auch dort in der Mitte.
        als_fader = msg.msg_type in ("cc", "pitchbend")
        is_pressed = (
            (msg.msg_type == "note_on" and msg.data2 > 0)
            or (als_fader and msg.data2 >= 64)
        )
        is_released = (
            msg.msg_type == "note_off"
            or (msg.msg_type == "note_on" and msg.data2 == 0)
            or (als_fader and msg.data2 < 64)
        )

        if mode == BUTTON_PRESS:
            # Nur der Druck zaehlt; Loslassen (Note-Off/Velocity 0/CC < 64)
            # tut nichts. Die LED folgt dem echten Zustand (Poll).
            if is_pressed:
                self._execute_binary(mapping, True)
                self._emit_mapping_state(mapping, self._read_mapping_state(mapping))
            return

        if mode == BUTTON_FLASH:
            if is_pressed:
                self._execute_binary(mapping, True)
                self._emit_mapping_state(mapping, 1.0)
            elif is_released:
                self._execute_binary(mapping, False)
                self._emit_mapping_state(mapping, 0.0)
            return

        # Toggle mode
        if not is_pressed:
            return
        with self._toggle_lock:
            new_state = not self._toggle_states.get(mapping.mapping_id, False)
            self._toggle_states[mapping.mapping_id] = new_state
        self._execute_binary(mapping, new_state)
        self._emit_mapping_state(mapping, 1.0 if new_state else 0.0)

    def _execute_binary(self, mapping: MidiMapping, state_on: bool):
        pe = self._state.playback_engine
        action = mapping.action

        if action == ACTION_EXECUTOR_GO and pe:
            # MIDI-2: GO loest NIE BACK aus. Frueher rief ``state_on=False``
            # (zweiter Toggle-Druck bzw. Flash-Loslassen) ``press_btn(1)``.
            if state_on:
                slot = int(mapping.param or "1")
                pe.get_executor(slot).press_btn(0)
            return

        if action == ACTION_EXECUTOR_BACK and pe and state_on:
            slot = int(mapping.param or "1")
            pe.get_executor(slot).press_btn(1)
            return

        if action == ACTION_EXECUTOR_FLASH and pe:
            slot = int(mapping.param or "1")
            ex = pe.get_executor(slot)
            if state_on:
                ex.press_btn(2)
            else:
                ex.release_btn(2)
            return

        if action == ACTION_PAGE_SELECT and pe and state_on:
            try:
                page = int(mapping.param) - 1
                pe.set_page(page)
            except (TypeError, ValueError):
                pass
            return

        if action == ACTION_PAGE_NEXT and pe and state_on:
            pe.set_page(pe.current_page + 1)
            return

        if action == ACTION_PAGE_PREV and pe and state_on:
            pe.set_page(pe.current_page - 1)
            return

        if action == ACTION_FUNCTION or (
            action == ACTION_NONE
            and (mapping.target_id or "").strip().startswith("function:")
        ):
            # Scene/Chaser/etc. ueber Funktions-ID starten/stoppen. Akzeptiert
            # sowohl param ("function:<id>" -> action="function") als auch das
            # Legacy-target_id mit action="none".
            try:
                fid = int(mapping.param or mapping.target_id.split(":", 1)[1])
                fm = self._state.function_manager
                if state_on:
                    fm.start(fid)
                else:
                    fm.stop(fid)
            except Exception as e:
                from src.core.diagnose_log import melde_still   # STAB-30
                melde_still("midi.funktion", e,
                            text=f"Mapping {mapping.target_id or mapping.param}")
            return

        if action == ACTION_EFFECT_ACTION:
            # Phase 6: Effekt-Aktion (add_color/next_color/toggle_freeze/…) auf Press.
            if state_on:
                key, fid = _parse_effect_param(mapping.param)
                try:
                    from src.core.engine import effect_live
                    effect_live.do_action(key, fid)
                except Exception:
                    pass
            return

    def _programmer_targets(self, attribute: str):
        """FM-9-Rest: Ziele fuer ``ACTION_PROGRAMMER_VAL`` — ``(fids, {fid: {head}})``.

        **Zwei Dinge waren hier kaputt, das zweite ist das groebere:**

        1. Der Regler kannte die **Kopf**-Auswahl nicht — „Kopf 2" gewaehlt, und
           trotzdem bewegten sich alle vier Koepfe (wie beim XY-Pad, FM-9/A5).
        2. Er kannte die Auswahl **ueberhaupt nicht**: geschrieben wurde stur auf
           ``get_patched_fixtures()``, also auf JEDES gepatchte Geraet. Ein mit
           „Programmer Attribut" beschrifteter Fader, der 30 Geraete anfasst
           obwohl zwei gewaehlt sind, ist auf keinem Lichtpult das erwartete
           Verhalten.

        Die Reichweite folgt jetzt dem im Projekt etablierten Muster von
        ``VCXYPad._resolve_fids``: **Auswahl, sonst alle gepatchten.** Der
        Alt-Fall „nichts gewaehlt" bleibt damit byte-identisch — wer den Fader
        bisher als globalen Attribut-Regler benutzt hat, merkt keinen Unterschied,
        solange er nichts selektiert.

        ★ Validiert wird gegen die Kopfzahl **dieses Attributs**
        (``head_counter_for_attr``), nicht gegen Farb- oder Bewegungskoepfe: eine
        ``HYDRABEAM 4000 RGBW [19-Kanal]`` hat 4 Pan, 4 Tilt, 5 Intensity und 1
        Farbbank. Mit der falschen Zaehlung entstuende entweder ein ``attr#N``
        ohne Kanal (Kopf faellt auf seinen Default) oder die Einschraenkung fiele
        weg — beides stumm.
        """
        st = self._state
        # FM-41/FM-51: „nichts gewaehlt -> alle" nur, wenn WIRKLICH nichts
        # gewaehlt ist — der zentrale Helfer liefert bei reiner Weiss-Auswahl
        # ``[]`` (sonst fuehre der Fader das ganze Rig).
        ziel = getattr(st, "auswahl_ziel_fids", None)
        try:
            if callable(ziel):
                fids = list(ziel() or [])
            else:
                fids = list(st.get_selected_fids())
        except Exception:
            fids = []
        if fids:
            try:
                from src.core.app_state import head_counter_for_attr
                from src.core.group_cells import head_restrictions
                heads = st.validate_head_restrictions(
                    head_restrictions(st.get_selected_cells()),
                    count_heads=head_counter_for_attr(attribute)) or {}
            except Exception:
                heads = {}
            return fids, heads
        if callable(ziel):
            try:
                return list(ziel(rueckfall="alle") or []), {}
            except Exception:
                pass
        try:
            patched = st.get_patched_fixtures()
        except Exception:
            patched = []
        return [f.fid for f in patched if getattr(f, "fid", None) is not None], {}

    def _execute_continuous(self, mapping: MidiMapping, normalized_value: float):
        value = max(0.0, min(1.0, float(normalized_value)))
        scaled = mapping.continuous_min + (mapping.continuous_max - mapping.continuous_min) * value
        pe = self._state.playback_engine
        action = mapping.action

        if action == ACTION_EXECUTOR_FADER and pe:
            slot = int(mapping.param or "1")
            ex = pe.get_executor(slot)
            ex.fader_value = max(0.0, min(1.0, scaled))
            return

        if action == ACTION_PROGRAMMER_VAL:
            attr = mapping.param
            raw = int(max(0.0, min(1.0, scaled)) * 255)
            fids, heads = self._programmer_targets(attr)
            for fid in fids:
                # Kein Eintrag = geraeteweit (FM-17: head=None), byte-identisch
                # zum Bestand. „Kopf 1" ist seit der Kopf-Karte etwas anderes.
                for head in (sorted(heads[fid]) if heads.get(fid) else (None,)):
                    self._state.set_programmer_value(fid, attr, raw, head=head)
            return

        if action == ACTION_GRAND_MASTER:
            val = max(0.0, min(1.0, scaled))
            self._state.output_manager.set_grand_master(val)
            if pe:
                for ex in pe.executors:
                    if ex.fader_function == "master":
                        ex.fader_value = val
            return

        if action == ACTION_EFFECT_PARAM:
            # Phase 6: beliebiger Effekt-Parameter live (gleicher Dispatcher wie die VC).
            key, fid = _parse_effect_param(mapping.param)
            try:
                from src.core.engine import effect_live
                effect_live.set_param_normalized(key, max(0.0, min(1.0, normalized_value)), fid)
            except Exception:
                pass
            return

    # Outbound feedback engine ------------------------------------------

    def subscribe_state(self, callback: Callable[[str, dict], None]):
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)

    def _emit_mapping_state(self, mapping: MidiMapping, value: float):
        payload = {
            "mapping_id": mapping.mapping_id,
            "target": mapping.target_id,
            "value": float(value),
            "is_on": bool(value >= 0.5),
        }
        for callback in list(self._state_callbacks):
            try:
                callback("mapping_state_changed", payload)
            except Exception:
                pass
        if mapping.midi_out:
            try:
                self._feedback_queue.put_nowait((mapping, float(value)))
            except queue.Full:
                pass

    def _feedback_loop(self):
        midi = get_midi_manager()
        while self._feedback_running:
            now = time.monotonic()
            if now - self._last_state_poll_ts >= 0.1:
                self._last_state_poll_ts = now
                self._poll_feedback_states()
            self._motor_nachtrag(midi)      # MIDI-14: nach der Hand-Ruhe

            try:
                mapping, value = self._feedback_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if mapping.midi_out is None:
                continue
            fb = mapping.midi_out
            if ist_motorfader(mapping):
                self._motor_melden(midi, mapping, value)    # MIDI-14
                continue
            if mapping.msg_type == "pitchbend" and fb.trigger_id < 0:
                # MIDI-10: keine Rueckmeldung ohne ausdruecklich gesetztes Ziel
                # — der Rueckfall auf ``data1`` waere hier Note/CC 0.
                continue
            ch = int(fb.channel or mapping.channel or 1)
            trigger = int(fb.trigger_id if fb.trigger_id >= 0 else mapping.data1)
            msg_type = fb.message_type or "note"

            # ★ MIDI-FB-PORT. Frueher wurde hier der GETEILTE Ausgang auf
            # ``fb.device`` umgeschaltet (``open_output``) — pro Nachricht,
            # sobald er nicht schon passte. Das nahm dem Benutzer die Auswahl
            # in der MIDI-Ansicht unter den Fingern weg, ohne dass die Anzeige
            # das mitbekam, und liess bei Mappings auf ZWEI Geraete den Ausgang
            # bei jeder Nachricht hin- und herspringen. Jetzt nennt die Nachricht
            # ihr Ziel; umgeschaltet wird gar nichts mehr.
            geraet = str(fb.device or "").strip()

            if (mapping.button_mode or "") == BUTTON_CONTINUOUS:
                out_val = _clamp_7bit(round(value * 127.0))
            else:
                out_val = fb.state_on if value >= 0.5 else fb.state_off

            if fb.brightness is not None:
                out_val = _clamp_7bit(min(out_val, fb.brightness))

            dedupe_key = f"{mapping.mapping_id}:{msg_type}:{ch}:{trigger}"
            prev_val = self._feedback_output_cache.get(dedupe_key)
            prev_ts = self._feedback_last_send_ts.get(dedupe_key, 0.0)
            if prev_val == out_val and (time.monotonic() - prev_ts) < 0.05:
                continue
            self._feedback_output_cache[dedupe_key] = out_val
            self._feedback_last_send_ts[dedupe_key] = time.monotonic()

            try:
                self._sende(midi, geraet, msg_type, ch, trigger, out_val)
            except Exception:
                pass

            if fb.aux_channel is not None:
                # Zweiter MIDI-Kanal auf DEMSELBEN Geraet — also derselbe Port.
                try:
                    self._sende(midi, geraet, "cc", int(fb.aux_channel),
                                trigger, out_val)
                except Exception:
                    pass

    # ── MIDI-14: Motorfader ──────────────────────────────────────────────────

    def _motor_eingang(self, mapping: MidiMapping, msg: MidiMessage) -> bool:
        """Eingang von einem Motorfader einordnen. ``True`` = das ist der
        Bericht des Pults ueber eine Fahrt, die LightOS selbst ausgeloest hat
        — nicht ausfuehren. Sonst merkt sich der Mapper die Hand."""
        if not ist_motorfader(mapping) or msg.msg_type != "pitchbend":
            return False
        jetzt = self._uhr()
        with self._motor_lock:
            if mapping.mapping_id in self._motor_beruehrt:
                # MIDI-15: der Sensor sagt, die Hand liegt auf dem Fader — was
                # jetzt kommt, ist nie der Bericht einer Motorfahrt.
                self._motor_hand_ts[mapping.mapping_id] = jetzt
                self._motor_hand_wert[mapping.mapping_id] = fader_wert(msg)
                return False
            gesendet = self._motor_send_ts.get(mapping.mapping_id)
            if gesendet is not None and (jetzt - gesendet) < MOTOR_ECHO_FENSTER_S:
                return True
            self._motor_hand_ts[mapping.mapping_id] = jetzt
            self._motor_hand_wert[mapping.mapping_id] = fader_wert(msg)
        return False

    def _motor_beruehrung(self, msg: MidiMessage) -> None:
        """MIDI-15: Beruehrungs-Note eines Motorfaders auswerten.

        Beruehrt: nichts geht mehr an seinen Motor (``_motor_melden`` merkt
        den Auftrag nur). Losgelassen: die Stellung wird sofort nachgetragen —
        ohne die Wartezeit aus MIDI-14, denn der Sensor weiss es genau.
        Die Note laeuft danach ganz normal weiter durch die Mappings."""
        if msg.msg_type not in ("note_on", "note_off") or msg.channel != TOUCH_KANAL:
            return
        beruehrt = msg.msg_type == "note_on" and msg.data2 > 0
        mappings = list(self._mappings)
        geraete = {m.midi_in.device for m in mappings
                   if getattr(m.midi_in, "device", "")}
        for mapping in mappings:
            if not ist_motorfader(mapping) or mapping.midi_out.touch_note != msg.data1:
                continue
            geraet = mapping.midi_in.device
            if geraet and not geraet_passt(geraet, msg.port_name,
                                           _offene_eingaenge(), geraete):
                continue                    # dieselbe Note von einem anderen Pult
            mid = mapping.mapping_id
            with self._motor_lock:
                if beruehrt:
                    self._motor_beruehrt.add(mid)
                    continue
                war = mid in self._motor_beruehrt
                self._motor_beruehrt.discard(mid)
                if war:
                    # sofort nachtragen: die Hand ist weg, keine Wartezeit
                    self._motor_hand_ts.pop(mid, None)
                    self._motor_wert.pop(mid, None)     # auch wenn der Wert gleich ist
                    if mapping.action in _MOTOR_LESBAR:
                        # der Wert zaehlt nicht: gesendet wird der echte Stand
                        self._motor_offen.setdefault(mid, (mapping, 0.0))
                    elif mid in self._motor_hand_wert:
                        # Ziel ohne lesbaren Stand: nur, was der Fader selbst
                        # gemeldet hat — nie eine geratene Stellung
                        self._motor_offen[mid] = (mapping, self._motor_hand_wert[mid])

    def _motor_stellung(self, mapping: MidiMapping, vorgabe: float) -> float:
        """Wohin der Fader gehoert (0..1). Bei einem lesbaren Ziel der echte
        Stand, zurueckgerechnet durch ``continuous_min``/``continuous_max``
        (der Fader steht bei 0..1, das Ziel bei min..max); sonst die Vorgabe —
        die letzte Stellung, die der Fader selbst gemeldet hat."""
        if mapping.action not in _MOTOR_LESBAR:
            return max(0.0, min(1.0, float(vorgabe)))
        stand = self._read_mapping_state(mapping)
        spanne = float(mapping.continuous_max) - float(mapping.continuous_min)
        if abs(spanne) > 1e-9:
            stand = (stand - float(mapping.continuous_min)) / spanne
        return max(0.0, min(1.0, float(stand)))

    def _motor_melden(self, midi, mapping: MidiMapping, value: float) -> bool:
        """Einen Motorfader nachfuehren — aber nicht, solange die Hand ihn
        bewegt: dann wird der Auftrag gemerkt und nach ``MOTOR_HAND_RUHE_S``
        nachgetragen (``_motor_nachtrag``). ``True`` = gesendet."""
        jetzt = self._uhr()
        mid = mapping.mapping_id
        with self._motor_lock:
            hand = self._motor_hand_ts.get(mid)
            if (mid in self._motor_beruehrt             # MIDI-15
                    or (hand is not None and (jetzt - hand) < MOTOR_HAND_RUHE_S)):
                self._motor_offen[mid] = (mapping, float(value))
                return False
            self._motor_offen.pop(mid, None)
        return self._motor_senden(midi, mapping, value, jetzt)

    def _motor_nachtrag(self, midi) -> int:
        """Gemerkte Auftraege senden, sobald die Hand lange genug ruht. Das
        Pult bekommt damit auch die Stellung zurueck, die der Bediener selbst
        eingestellt hat — Mackie-Pulte fahren den Fader nach dem Loslassen auf
        den zuletzt GESENDETEN Wert."""
        jetzt = self._uhr()
        faellig = []
        with self._motor_lock:
            for mid, (mapping, value) in list(self._motor_offen.items()):
                if mid in self._motor_beruehrt:         # MIDI-15: erst loslassen
                    continue
                hand = self._motor_hand_ts.get(mid)
                if hand is None or (jetzt - hand) >= MOTOR_HAND_RUHE_S:
                    faellig.append((mapping, value))
                    self._motor_offen.pop(mid, None)
        return sum(1 for mapping, value in faellig
                   if self._motor_senden(midi, mapping, value, jetzt))

    def _motor_senden(self, midi, mapping: MidiMapping, value: float,
                      jetzt: float) -> bool:
        fb = mapping.midi_out
        if fb is None:
            return False
        mid = mapping.mapping_id
        wert = int(round(self._motor_stellung(mapping, value) * 16383.0))
        with self._motor_lock:
            hand = self._motor_hand_ts.get(mid, float("-inf"))
            zuletzt = self._motor_send_ts.get(mid, float("-inf"))
            if self._motor_wert.get(mid) == wert and hand <= zuletzt:
                return False        # steht schon dort, und niemand hat ihn bewegt
            # VOR dem Senden merken: was das Pult gleich zurueckmeldet, soll
            # schon als Echo gelten.
            self._motor_wert[mid] = wert
            self._motor_send_ts[mid] = jetzt
        ch = int(fb.channel or mapping.channel or 1)
        geraet = str(fb.device or "").strip()
        try:
            if geraet:
                midi.send_pitchbend_to(geraet, ch, wert)
            else:
                midi.send_pitchbend(ch, wert)
        except Exception:
            return False
        return True

    def _motor_vergessen(self, mapping_id: str | None = None) -> None:
        """Zustand eines Motorfaders verwerfen (Mapping entfernt/ersetzt)."""
        with self._motor_lock:
            for tabelle in (self._motor_hand_ts, self._motor_send_ts,
                            self._motor_wert, self._motor_offen):
                if mapping_id is None:
                    tabelle.clear()
                else:
                    tabelle.pop(mapping_id, None)
            if mapping_id is None:
                self._motor_beruehrt.clear()
                self._motor_hand_wert.clear()
            else:
                self._motor_beruehrt.discard(mapping_id)
                self._motor_hand_wert.pop(mapping_id, None)

    @staticmethod
    def _sende(midi, geraet: str, msg_type: str, ch: int, trigger: int,
               wert: int) -> None:
        """Feedback rausschicken — portadressiert, wenn das Mapping ein Geraet
        nennt, sonst ueber den gemeinsamen Ausgang.

        Ohne ``fb.device`` gibt es kein Ziel zu adressieren; dann ist der
        geteilte Ausgang genau die richtige Wahl und bleibt es auch.
        """
        if msg_type == "cc":
            if geraet:
                midi.send_cc_to(geraet, ch, trigger, wert)
            else:
                midi.send_cc(ch, trigger, wert)
        else:
            if geraet:
                midi.send_note_to(geraet, ch, trigger, wert)
            else:
                midi.send_note(ch, trigger, wert)

    def _hook_state_sources(self):
        # Grand Master changes (UI slider, command line, MIDI, etc.)
        try:
            self._state.output_manager.subscribe_grand_master(self._on_grand_master_change)
        except Exception:
            pass

    def _on_grand_master_change(self, value: float):
        for mapping in self._mappings:
            if mapping.action == ACTION_GRAND_MASTER and mapping.midi_out:
                self._emit_mapping_state(mapping, max(0.0, min(1.0, float(value))))

    def _poll_feedback_states(self):
        for mapping in self._mappings:
            if not mapping.midi_out:
                continue
            if ist_motorfader(mapping):
                # MIDI-14: nur wo sich der Stand zuruecklesen laesst — sonst
                # fuehre der Fader auf einen geratenen Zustand (0) zurueck.
                if mapping.action not in _MOTOR_LESBAR:
                    continue
                value = self._motor_stellung(mapping, 0.0)
                prev = self._feedback_state_cache.get(mapping.mapping_id)
                if prev is None or abs(prev - value) >= MOTOR_SCHRITT:
                    self._feedback_state_cache[mapping.mapping_id] = value
                    self._emit_mapping_state(mapping, value)
                continue
            value = self._read_mapping_state(mapping)
            prev = self._feedback_state_cache.get(mapping.mapping_id)
            if prev is None or abs(prev - value) > 0.01:
                self._feedback_state_cache[mapping.mapping_id] = value
                self._emit_mapping_state(mapping, value)

    def _read_mapping_state(self, mapping: MidiMapping) -> float:
        pe = self._state.playback_engine
        action = mapping.action

        if action == ACTION_GRAND_MASTER:
            try:
                return float(self._state.output_manager.grand_master)
            except Exception:
                return 0.0

        if action == ACTION_EXECUTOR_FADER and pe:
            try:
                slot = int(mapping.param or "1")
                return float(pe.get_executor(slot).fader_value)
            except Exception:
                return 0.0

        if action == ACTION_EXECUTOR_FLASH and pe:
            try:
                slot = int(mapping.param or "1")
                return 1.0 if pe.get_executor(slot)._flash_active else 0.0
            except Exception:
                return 0.0

        if action == ACTION_EXECUTOR_GO and pe:
            try:
                slot = int(mapping.param or "1")
                ex = pe.get_executor(slot)
                return 1.0 if ex.stack is not None and bool(ex.get_output()) else 0.0
            except Exception:
                return 0.0

        if action == ACTION_PAGE_SELECT and pe:
            try:
                page = int(mapping.param) - 1
                return 1.0 if pe.current_page == page else 0.0
            except Exception:
                return 0.0

        target = (mapping.target_id or "").strip()
        if target.startswith("function:"):
            try:
                fid = int(target.split(":", 1)[1])
                return 1.0 if self._state.function_manager.is_running(fid) else 0.0
            except Exception:
                return 0.0

        with self._toggle_lock:
            an = self._toggle_states.get(mapping.mapping_id, False)
        return 1.0 if an else 0.0

    # Persistence --------------------------------------------------------

    def save(self, path: str) -> bool:
        """Schreibt die Mappings. ``True`` = geschrieben (QA-50).

        Vorher konnte ein Schreibfehler bis in den Aufrufer durchschlagen oder
        — je nach Aufrufer — unbemerkt bleiben; jetzt ist die Antwort eindeutig
        und die UI kann sie melden.
        """
        try:
            data = [mapping.to_config_dict() for mapping in self._mappings]
            # XPLAT-44: der App-Datenordner existiert nicht zwingend schon.
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[midi_mapper] save error: {e}")
            return False

    def load(self, path: str) -> bool:
        """Laedt die Mappings. ``True`` = geladen, ``False`` = nichts geaendert.

        ★ QA-50: Hier stand ``except Exception: pass``. Bei einer kaputten oder
        fehlenden Datei passierte damit **gar nichts** — ``replace_mappings``
        wurde nie erreicht, die bestehende (beim Start: leere) Liste blieb
        stehen, und die Oberflaeche meldete trotzdem „✓ Mappings geladen".

        **Der Schaden entsteht erst danach:** das naechste „Speichern" schreibt
        die leere Liste ueber die Datei, die noch alle Mappings enthielt. Ein
        Lesefehler wird so zu einem Schreibverlust — und niemand hat je einen
        Fehler gesehen.
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            loaded: list[MidiMapping] = []
            for item in data:
                if isinstance(item, dict) and "midi_in" in item:
                    loaded.append(MidiMapping.from_config_dict(item))
                elif isinstance(item, dict):
                    loaded.append(MidiMapping(**item))
            self.replace_mappings(loaded)
            return True
        except FileNotFoundError:
            # Kein Fehler, sondern der Normalfall beim ersten Start — aber auch
            # kein „geladen": der Aufrufer soll nicht behaupten, es gaebe
            # Mappings.
            return False
        except Exception as e:
            print(f"[midi_mapper] load error: {e}")
            return False

    def apply_msc_udp(self) -> bool:
        """NET-14: GMA-MSC-UDP-Empfaenger gemaess ``msc.get_settings()``
        (neu) starten oder stoppen. True = laeuft danach."""
        from . import msc as _msc
        st = _msc.get_settings()
        rx = getattr(self, "_msc_udp", None)
        if rx is not None and (not st.udp_enabled or rx.host != st.udp_host
                               or rx.port != int(st.udp_port)):
            rx.stop()
            rx = None
            self._msc_udp = None
        if not st.udp_enabled:
            return False
        if rx is None:
            rx = _msc.GmaMscReceiver(self._on_msc_udp, st.udp_host, st.udp_port)
            if not rx.start():
                return False
            self._msc_udp = rx
        return True

    def close(self):
        self._feedback_running = False
        try:
            self._feedback_thread.join(timeout=0.5)
        except Exception:
            pass
        rx = getattr(self, "_msc_udp", None)
        if rx is not None:
            rx.stop()
            self._msc_udp = None


_mapper_instance: MidiMapper | None = None


def get_midi_mapper(app_state=None) -> MidiMapper | None:
    global _mapper_instance
    if _mapper_instance is None and app_state is not None:
        _mapper_instance = MidiMapper(app_state)
        # MIDI-5/NET-14: gespeicherte MSC-Einstellungen beim Start anwenden.
        try:
            from . import msc as _msc
            _msc.load_settings()
            _mapper_instance.apply_msc_udp()
        except Exception as e:
            from src.core.diagnose_log import melde_still
            melde_still("midi.msc", e, text="Start")
    return _mapper_instance

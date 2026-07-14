"""MIDI mapper with learn mode, inbound actions and outbound LED feedback."""
from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from .midi_manager import MidiMessage, get_midi_manager

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


def _parse_effect_param(param: str) -> tuple[str, int | None]:
    """'<key>[@<fid>]' -> (key, fid|None)."""
    key, _, fid = str(param or "").partition("@")
    fid = fid.strip()
    return key.strip(), (int(fid) if fid.lstrip("-").isdigit() else None)

BUTTON_TOGGLE = "toggle"
BUTTON_FLASH = "flash"
BUTTON_CONTINUOUS = "continuous"


def _clamp_7bit(value: int) -> int:
    return max(0, min(127, int(value)))


def _infer_button_mode(action: str) -> str:
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
    return "cc" if binding_type == "cc" else "note_on"


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
    """note_on/note_off/note -> 'note', cc -> 'cc' (Match-Familie)."""
    return "cc" if str(msg_type) == "cc" else "note"


def _bindings_overlap(type_a, ch_a, d1_a, type_b, ch_b, d1_b) -> bool:
    """True, wenn zwei Bindungen auf DIESELBE eingehende Nachricht feuern wuerden.

    Gleiche data1, gleiche Familie (note vs cc), ueberlappender Kanal
    (0 = alle Kanaele). Deckt sich mit MidiInBinding.matches /
    midi_binding_matches (note_on bindet auch note_off)."""
    try:
        if int(d1_a) != int(d1_b):
            return False
    except (TypeError, ValueError):
        return False
    if _binding_family(type_a) != _binding_family(type_b):
        return False
    ca, cb = int(ch_a or 0), int(ch_b or 0)
    if ca != 0 and cb != 0 and ca != cb:
        return False
    return True


@dataclass
class MidiInBinding:
    """Incoming MIDI trigger definition."""

    device: str = ""
    channel: int = 1
    trigger_id: int = 0
    message_type: str = "note"  # note or cc

    def matches(self, msg: MidiMessage) -> bool:
        if self.device and self.device not in msg.port_name:
            return False
        if self.channel != 0 and self.channel != msg.channel:
            return False
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
        return cls(
            device=msg.port_name,
            channel=msg.channel,
            trigger_id=msg.data1,
            message_type="cc" if msg.msg_type == "cc" else "note",
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

    @classmethod
    def from_dict(cls, data: dict | None) -> "MidiOutFeedback | None":
        if not isinstance(data, dict):
            return None
        brightness = data.get("brightness")
        aux_channel = data.get("aux_channel")
        return cls(
            device=str(data.get("device", "")),
            channel=int(data.get("channel", 1)),
            trigger_id=int(data.get("trigger_id", -1)),
            message_type=str(data.get("message_type", "note")),
            state_off=_clamp_7bit(int(data.get("state_off", 0))),
            state_on=_clamp_7bit(int(data.get("state_on", 127))),
            brightness=None if brightness is None else _clamp_7bit(int(brightness)),
            aux_channel=None if aux_channel is None else int(aux_channel),
        )

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "channel": int(self.channel),
            "trigger_id": int(self.trigger_id),
            "message_type": self.message_type,
            "state_off": int(self.state_off),
            "state_on": int(self.state_on),
            "brightness": self.brightness,
            "aux_channel": self.aux_channel,
        }


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

        # Legacy -> structured sync (kept for editor compatibility).
        legacy_binding_type = "cc" if self.msg_type == "cc" else "note"
        self.midi_in = MidiInBinding(
            device=self.port_filter,
            channel=int(self.channel),
            trigger_id=int(self.data1),
            message_type=legacy_binding_type,
        )

        if self.midi_out and self.midi_out.trigger_id < 0:
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
        self.msg_type = "cc" if msg.msg_type == "cc" else "note_on"
        self.channel = int(msg.channel)
        self.data1 = int(msg.data1)
        self.port_filter = msg.port_name
        self.midi_in = MidiInBinding.from_message(msg)
        if self.midi_out and self.midi_out.trigger_id < 0:
            self.midi_out.trigger_id = msg.data1


class MidiMapper:
    """Bidirectional MIDI mapping engine (inbound + outbound feedback)."""

    def __init__(self, app_state):
        self._state = app_state
        self._mappings: list[MidiMapping] = []
        self._learn_mode = False
        self._learn_callback = None
        self._state_callbacks: list[Callable[[str, dict], None]] = []
        # UI-Hook fuer Learn-Konflikt-Warnungen (Option B, rein additiv).
        self._conflict_callbacks: list[Callable[[dict], None]] = []
        self._toggle_states: dict[str, bool] = {}
        self._feedback_state_cache: dict[str, float] = {}
        self._feedback_output_cache: dict[str, int] = {}
        self._feedback_last_send_ts: dict[str, float] = {}
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
            self._toggle_states.setdefault(mapping.mapping_id, False)
        self._mappings.append(mapping)
        self._emit_mapping_state(mapping, self._read_mapping_state(mapping))

    def remove_mapping(self, idx: int):
        if 0 <= idx < len(self._mappings):
            mapping = self._mappings.pop(idx)
            self._toggle_states.pop(mapping.mapping_id, None)
            self._feedback_state_cache.pop(mapping.mapping_id, None)

    def get_mappings(self) -> list[MidiMapping]:
        return list(self._mappings)

    def replace_mappings(self, mappings: list[MidiMapping]):
        self._mappings = list(mappings)
        self._toggle_states = {}
        self._feedback_state_cache = {}
        for mapping in self._mappings:
            if mapping.button_mode == BUTTON_TOGGLE:
                self._toggle_states[mapping.mapping_id] = False
            self._emit_mapping_state(mapping, self._read_mapping_state(mapping))

    # Learn mode ---------------------------------------------------------

    def start_learn(self, callback):
        """Wait for the next note/cc message and return it to callback(msg)."""
        self._learn_mode = True
        self._learn_callback = callback

    def stop_learn(self):
        self._learn_mode = False
        self._learn_callback = None

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
        if self._learn_mode and self._learn_callback:
            if msg.msg_type in ("note_on", "note_off", "cc"):
                callback = self._learn_callback
                self._learn_mode = False
                self._learn_callback = None
                # Konflikt-Check VOR dem Anwenden der Bindung: so zaehlt die
                # gerade gelernte Zeile sich nicht selbst mit (Option B).
                try:
                    self.check_and_warn_conflicts(
                        msg.msg_type, msg.channel, msg.data1,
                        learned_label="Mapper-Learn")
                except Exception:
                    pass
                callback(msg)
            return

        for mapping in self._mappings:
            if not mapping.midi_in.matches(msg):
                continue
            self._handle_inbound_mapping(mapping, msg)

    def _handle_inbound_mapping(self, mapping: MidiMapping, msg: MidiMessage):
        mode = (mapping.button_mode or _infer_button_mode(mapping.action)).lower()
        if mode == BUTTON_CONTINUOUS:
            value = msg.data2 / 127.0
            self._execute_continuous(mapping, value)
            self._emit_mapping_state(mapping, value)
            return

        is_pressed = (
            (msg.msg_type == "note_on" and msg.data2 > 0)
            or (msg.msg_type == "cc" and msg.data2 >= 64)
        )
        is_released = (
            msg.msg_type == "note_off"
            or (msg.msg_type == "note_on" and msg.data2 == 0)
            or (msg.msg_type == "cc" and msg.data2 < 64)
        )

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
        cur = self._toggle_states.get(mapping.mapping_id, False)
        new_state = not cur
        self._toggle_states[mapping.mapping_id] = new_state
        self._execute_binary(mapping, new_state)
        self._emit_mapping_state(mapping, 1.0 if new_state else 0.0)

    def _execute_binary(self, mapping: MidiMapping, state_on: bool):
        pe = self._state.playback_engine
        action = mapping.action

        if action == ACTION_EXECUTOR_GO and pe:
            slot = int(mapping.param or "1")
            if state_on:
                pe.get_executor(slot).press_btn(0)
            else:
                pe.get_executor(slot).press_btn(1)
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
            except Exception:
                pass
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
            for fixture in self._state.get_patched_fixtures():
                self._state.set_programmer_value(fixture.fid, attr, raw)
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

            try:
                mapping, value = self._feedback_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if mapping.midi_out is None:
                continue
            fb = mapping.midi_out
            ch = int(fb.channel or mapping.channel or 1)
            trigger = int(fb.trigger_id if fb.trigger_id >= 0 else mapping.data1)
            msg_type = fb.message_type or "note"

            if fb.device:
                try:
                    cur_name = ""
                    if hasattr(midi, "current_output_name"):
                        cur_name = str(midi.current_output_name() or "")
                    if cur_name != fb.device:
                        midi.open_output(fb.device)
                except Exception:
                    pass

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
                if msg_type == "cc":
                    midi.send_cc(ch, trigger, out_val)
                else:
                    midi.send_note(ch, trigger, out_val)
            except Exception:
                pass

            if fb.aux_channel is not None:
                try:
                    midi.send_cc(int(fb.aux_channel), trigger, out_val)
                except Exception:
                    pass

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

        return 1.0 if self._toggle_states.get(mapping.mapping_id, False) else 0.0

    # Persistence --------------------------------------------------------

    def save(self, path: str):
        data = [mapping.to_config_dict() for mapping in self._mappings]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, path: str):
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
        except Exception:
            pass

    def close(self):
        self._feedback_running = False
        try:
            self._feedback_thread.join(timeout=0.5)
        except Exception:
            pass


_mapper_instance: MidiMapper | None = None


def get_midi_mapper(app_state=None) -> MidiMapper | None:
    global _mapper_instance
    if _mapper_instance is None and app_state is not None:
        _mapper_instance = MidiMapper(app_state)
    return _mapper_instance

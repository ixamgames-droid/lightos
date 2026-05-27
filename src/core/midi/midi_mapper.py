"""MIDI-Mapper — Bindet MIDI-Events an LightOS-Aktionen."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from .midi_manager import MidiMessage, get_midi_manager

# Aktions-Typen
ACTION_EXECUTOR_GO    = "executor_go"
ACTION_EXECUTOR_BACK  = "executor_back"
ACTION_EXECUTOR_FLASH = "executor_flash"
ACTION_EXECUTOR_FADER = "executor_fader"  # CC → Fader-Wert
ACTION_PROGRAMMER_VAL = "programmer_value"  # CC → Attribut-Wert
ACTION_GRAND_MASTER   = "grand_master"
ACTION_PAGE_SELECT    = "page_select"   # param = page-Nummer (1-10)
ACTION_PAGE_NEXT      = "page_next"
ACTION_PAGE_PREV      = "page_prev"
ACTION_NONE           = "none"


@dataclass
class MidiMapping:
    name: str
    msg_type: str      # "cc", "note_on"
    channel: int       # 1–16 (0 = alle)
    data1: int         # CC-Nummer / Note (0–127)
    action: str        # ACTION_*
    param: str         # z.B. "5" für Executor 5, "intensity" für Attribut
    port_filter: str   # "" = alle Ports


class MidiMapper:
    def __init__(self, app_state):
        self._state = app_state
        self._mappings: list[MidiMapping] = []
        self._learn_mode = False
        self._learn_callback = None
        midi = get_midi_manager()
        midi.subscribe(self._on_midi)

    # ── Mapping-Verwaltung ────────────────────────────────────────────────────

    def add_mapping(self, mapping: MidiMapping):
        self._mappings.append(mapping)

    def remove_mapping(self, idx: int):
        if 0 <= idx < len(self._mappings):
            self._mappings.pop(idx)

    def get_mappings(self) -> list[MidiMapping]:
        return list(self._mappings)

    # ── MIDI-Learn ────────────────────────────────────────────────────────────

    def start_learn(self, callback):
        """Wartet auf nächste MIDI-Message und ruft callback(msg) auf."""
        self._learn_mode = True
        self._learn_callback = callback

    def stop_learn(self):
        self._learn_mode = False
        self._learn_callback = None

    # ── Empfang + Aktion ──────────────────────────────────────────────────────

    def _on_midi(self, msg: MidiMessage):
        if self._learn_mode and self._learn_callback:
            self._learn_callback(msg)
            self._learn_mode = False
            self._learn_callback = None
            return

        for m in self._mappings:
            if m.msg_type != msg.msg_type:
                continue
            if m.channel != 0 and m.channel != msg.channel:
                continue
            if m.data1 != msg.data1:
                continue
            if m.port_filter and m.port_filter not in msg.port_name:
                continue
            self._execute(m, msg)

    def _execute(self, m: MidiMapping, msg: MidiMessage):
        pe = self._state.playback_engine
        if m.action == ACTION_EXECUTOR_GO and pe:
            slot = int(m.param)
            pe.get_executor(slot).press_btn(0)

        elif m.action == ACTION_EXECUTOR_BACK and pe:
            slot = int(m.param)
            pe.get_executor(slot).press_btn(1)

        elif m.action == ACTION_EXECUTOR_FLASH and pe:
            slot = int(m.param)
            ex = pe.get_executor(slot)
            if msg.msg_type == "note_on" and msg.data2 > 0:
                ex.press_btn(2)
            else:
                ex.release_btn(2)

        elif m.action == ACTION_EXECUTOR_FADER and pe:
            slot = int(m.param)
            ex = pe.get_executor(slot)
            ex.fader_value = msg.data2 / 127.0

        elif m.action == ACTION_PROGRAMMER_VAL:
            # Attribut auf alle ausgewählten Fixtures setzen
            attr = m.param
            value = int(msg.data2 / 127.0 * 255)
            for f in self._state.get_patched_fixtures():
                self._state.set_programmer_value(f.fid, attr, value)

        elif m.action == ACTION_GRAND_MASTER:
            if pe:
                val = msg.data2 / 127.0
                # Direkt auf OutputManager Grand Master
                try:
                    self._state.output_manager.set_grand_master(val)
                except Exception:
                    pass
                for ex in pe.executors:
                    if ex.fader_function == "master":
                        ex.fader_value = val

        elif m.action == ACTION_PAGE_SELECT and pe:
            # Nur bei note_on triggern (nicht release)
            if msg.msg_type == "note_on" and msg.data2 == 0:
                return
            try:
                page = int(m.param) - 1   # 1-basiert in mapping, 0-basiert intern
                pe.set_page(page)
            except (ValueError, TypeError):
                pass

        elif m.action == ACTION_PAGE_NEXT and pe:
            if msg.msg_type == "note_on" and msg.data2 == 0:
                return
            pe.set_page(pe.current_page + 1)

        elif m.action == ACTION_PAGE_PREV and pe:
            if msg.msg_type == "note_on" and msg.data2 == 0:
                return
            pe.set_page(pe.current_page - 1)

    # ── Persistenz ────────────────────────────────────────────────────────────

    def save(self, path: str):
        data = [asdict(m) for m in self._mappings]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._mappings = [MidiMapping(**d) for d in data]
        except Exception:
            pass

"""Input-Profile - Sammlung von Mappings fuer ein konkretes Geraet."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional
import json
import os
from src.core.paths import app_data_dir
from src.core.midi.midi_mapper import MidiMapping

PROFILES_DIR = os.path.join(app_data_dir(), "input_profiles")


@dataclass
class InputProfile:
    name: str
    device_hint: str = ""           # z.B. "APC mini", "X-Touch" - matched gegen port_filter
    mappings: list = None           # list[MidiMapping]
    description: str = ""

    def __post_init__(self):
        if self.mappings is None:
            self.mappings = []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "device_hint": self.device_hint,
            "description": self.description,
            "mappings": [asdict(m) for m in self.mappings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InputProfile":
        p = cls(name=d.get("name", "Profil"))
        p.device_hint = d.get("device_hint", "")
        p.description = d.get("description", "")
        try:
            p.mappings = [MidiMapping(**m) for m in d.get("mappings", [])]
        except Exception as e:
            print(f"[InputProfile] from_dict mapping error: {e}")
            p.mappings = []
        return p

    def save(self) -> str:
        try:
            os.makedirs(PROFILES_DIR, exist_ok=True)
        except Exception as e:
            print(f"[InputProfile] mkdir error: {e}")
        path = os.path.join(PROFILES_DIR, f"{self.name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[InputProfile] save error: {e}")
        return path

    @classmethod
    def load(cls, name: str) -> Optional["InputProfile"]:
        path = os.path.join(PROFILES_DIR, f"{name}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            print(f"[InputProfile] load error: {e}")
            return None


def list_profiles() -> list:
    if not os.path.exists(PROFILES_DIR):
        return []
    try:
        return sorted([
            f[:-5] for f in os.listdir(PROFILES_DIR)
            if f.endswith(".json")
        ])
    except Exception as e:
        print(f"[InputProfile] list error: {e}")
        return []


def delete_profile(name: str) -> bool:
    path = os.path.join(PROFILES_DIR, f"{name}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            print(f"[InputProfile] delete error: {e}")
            return False
    return False


def create_default_apc_mini_profile() -> InputProfile:
    """Default APC mini - 33 Mappings."""
    from src.core.midi.midi_mapper import (
        ACTION_EXECUTOR_GO, ACTION_EXECUTOR_BACK, ACTION_EXECUTOR_FLASH,
        ACTION_EXECUTOR_FADER, ACTION_GRAND_MASTER, ACTION_PAGE_SELECT
    )
    p = InputProfile(
        name="APC mini Default",
        device_hint="APC",
        description="Akai APC mini: 8 Faders + 64 Grid + 8 Side + 9 Master",
    )
    PORT = "APC"
    # 8 Faders
    for i in range(8):
        p.mappings.append(MidiMapping(
            name=f"APC Fader {i+1}", msg_type="cc", channel=0,
            data1=48+i, action=ACTION_EXECUTOR_FADER, param=str(i+1), port_filter=PORT))
    # Master fader
    p.mappings.append(MidiMapping(
        name="APC Master Fader", msg_type="cc", channel=0,
        data1=56, action=ACTION_GRAND_MASTER, param="", port_filter=PORT))
    # Grid bottom row -> GO
    for i in range(8):
        p.mappings.append(MidiMapping(
            name=f"APC Grid Btm {i+1} GO", msg_type="note_on", channel=0,
            data1=i, action=ACTION_EXECUTOR_GO, param=str(i+1), port_filter=PORT))
    # Grid row 2 -> Flash
    for i in range(8):
        p.mappings.append(MidiMapping(
            name=f"APC Grid Row2 {i+1} Flash", msg_type="note_on", channel=0,
            data1=8+i, action=ACTION_EXECUTOR_FLASH, param=str(i+1), port_filter=PORT))
    # Track buttons -> BACK
    for i in range(8):
        p.mappings.append(MidiMapping(
            name=f"APC Track {i+1} BACK", msg_type="note_on", channel=0,
            data1=64+i, action=ACTION_EXECUTOR_BACK, param=str(i+1), port_filter=PORT))
    # Side buttons -> Page select
    for i in range(8):
        p.mappings.append(MidiMapping(
            name=f"APC Side {i+1} Page {i+1}", msg_type="note_on", channel=0,
            data1=82+i, action=ACTION_PAGE_SELECT, param=str(i+1), port_filter=PORT))
    return p

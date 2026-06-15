"""Controller-Bibliothek — Profile für MIDI-/DMX-Controller, Pulte & Interfaces.

Pendant zur Fixture Library, aber für Eingabegeräte: jedes Profil beschreibt
ein Gerät (Hersteller, Modell, Anschlussart, Bedienelemente mit MIDI-Notes/CCs,
LED-Feedback, Quelle/Lizenz). Die Profile liegen als einzelne JSON-Dateien in

- ``data/controller_library/``                 (mitgelieferte Builtins)
- ``%APPDATA%/LightOS/controller_library/``    (Nutzer-Importe, z. B. QLC+ .qxi)

und werden beim ersten Zugriff gemergt geladen (Nutzer-Profile mit gleicher id
überschreiben Builtins NICHT — sie bekommen einen ``-2``-Suffix; bestehende
Daten werden nie kaputt überschrieben).

Rechtliches: MIDI-Implementierungen (Note-/CC-Nummern) sind Faktendaten und
nicht urheberrechtlich schutzfähig; die mitgelieferten Einträge sind aus
öffentlich zugänglichen Herstellerprotokollen bzw. dem bestehenden LightOS-
Code (APC mini) zusammengetragen — Quelle steht in jedem Profil. Importierte
QLC+-Inputprofile stammen aus dem QLC+-Projekt (Apache-2.0, Quellenangabe im
Profil). Details: data/controller_library/README.md
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

_BUILTIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "data", "controller_library",
)
_USER_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "LightOS", "controller_library",
)

SCHEMA_VERSION = 1

DEVICE_TYPES = (
    "midi_grid_controller",   # Pad-Matrix (APC, Launchpad)
    "midi_fader_controller",  # Fader/Knob-Boxen (nanoKONTROL, X-Touch)
    "midi_keyboard",
    "dmx_interface",          # USB-DMX (Enttec & Co.)
    "network_node",           # Art-Net/sACN-Nodes
    "console",                # Hardware-Lichtpulte
    "keyboard_macro",         # Tastatur/Makro-Boards (Keyboard-Mapping)
    "other",
)


@dataclass
class ControllerControl:
    """Ein Bedienelement(-Block): Pads, Fader, Encoder, Tasten…"""
    name: str = ""
    # "note" | "cc" | "pitchbend" | "fader" | "encoder" | "key" | "other"
    type: str = "note"
    channel: int = 0                  # 0-basiert; -1 = beliebig
    range: list = field(default_factory=lambda: [0, 0])  # [erste, letzte] Nummer
    layout: str = ""                  # Freitext ("8x8, Note 0 unten links")

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "channel": self.channel,
                "range": list(self.range), "layout": self.layout}

    @classmethod
    def from_dict(cls, d: dict) -> "ControllerControl":
        rng = d.get("range", [0, 0])
        if not (isinstance(rng, (list, tuple)) and len(rng) == 2):
            rng = [0, 0]
        return cls(name=str(d.get("name", "")),
                   type=str(d.get("type", "note")),
                   channel=int(d.get("channel", 0)),
                   range=[int(rng[0]), int(rng[1])],
                   layout=str(d.get("layout", "")))

    @property
    def count(self) -> int:
        return max(0, int(self.range[1]) - int(self.range[0]) + 1)


@dataclass
class ControllerProfile:
    id: str = ""
    manufacturer: str = ""
    model: str = ""
    device_type: str = "other"
    connections: list = field(default_factory=list)   # ["USB-MIDI", "DMX-USB", …]
    buttons: int = 0
    faders: int = 0
    encoders: int = 0
    pad_matrix: list | None = None                    # [cols, rows] oder None
    banks: str = ""                                   # Banks/Pages (Freitext)
    controls: list = field(default_factory=list)      # list[ControllerControl]
    led_feedback: dict = field(default_factory=dict)  # {"type": …, "notes": …}
    features: list = field(default_factory=list)      # Besonderheiten
    source: str = ""                                  # Herkunft der Daten
    license: str = ""                                 # Lizenz/Rechtliches
    imported_at: str = ""                             # ISO-Datum
    # Schlüssel in controller_templates.CONTROLLERS → "VC-Vorlage einfügen"
    vc_template: str = ""
    # "apc_mini_default" → fertiges MIDI-Mapping-Profil (input/profile.py)
    mapping_template: str = ""

    @property
    def label(self) -> str:
        return f"{self.manufacturer} {self.model}".strip() or self.id

    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "id": self.id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "device_type": self.device_type,
            "connections": list(self.connections),
            "buttons": self.buttons,
            "faders": self.faders,
            "encoders": self.encoders,
            "pad_matrix": list(self.pad_matrix) if self.pad_matrix else None,
            "banks": self.banks,
            "controls": [c.to_dict() for c in self.controls],
            "led_feedback": dict(self.led_feedback),
            "features": list(self.features),
            "source": self.source,
            "license": self.license,
            "imported_at": self.imported_at,
            "vc_template": self.vc_template,
            "mapping_template": self.mapping_template,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ControllerProfile":
        pm = d.get("pad_matrix")
        if not (isinstance(pm, (list, tuple)) and len(pm) == 2):
            pm = None
        return cls(
            id=str(d.get("id", "")),
            manufacturer=str(d.get("manufacturer", "")),
            model=str(d.get("model", "")),
            device_type=str(d.get("device_type", "other")),
            connections=[str(c) for c in d.get("connections", [])],
            buttons=int(d.get("buttons", 0)),
            faders=int(d.get("faders", 0)),
            encoders=int(d.get("encoders", 0)),
            pad_matrix=[int(pm[0]), int(pm[1])] if pm else None,
            banks=str(d.get("banks", "")),
            controls=[ControllerControl.from_dict(c)
                      for c in d.get("controls", []) if isinstance(c, dict)],
            led_feedback=dict(d.get("led_feedback", {}) or {}),
            features=[str(f) for f in d.get("features", [])],
            source=str(d.get("source", "")),
            license=str(d.get("license", "")),
            imported_at=str(d.get("imported_at", "")),
            vc_template=str(d.get("vc_template", "")),
            mapping_template=str(d.get("mapping_template", "")),
        )


class ControllerLibrary:
    """Lädt und verwaltet alle Controller-Profile (Builtins + Nutzer)."""

    def __init__(self):
        self._profiles: list[ControllerProfile] = []
        self._loaded = False

    # ── Laden ────────────────────────────────────────────────────────────────

    @staticmethod
    def builtin_dir() -> str:
        return _BUILTIN_DIR

    @staticmethod
    def user_dir() -> str:
        return _USER_DIR

    def _load_dir(self, path: str, builtin: bool):
        if not os.path.isdir(path):
            return
        for fname in sorted(os.listdir(path)):
            if not fname.lower().endswith(".json"):
                continue
            fpath = os.path.join(path, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                p = ControllerProfile.from_dict(data)
                if not p.id:
                    p.id = os.path.splitext(fname)[0]
                # Duplikate: gleiche id wird NICHT überschrieben — der spätere
                # Eintrag (Nutzer-Import) bekommt einen Suffix.
                if self.find(p.id) is not None:
                    base = p.id
                    n = 2
                    while self.find(f"{base}-{n}") is not None:
                        n += 1
                    p.id = f"{base}-{n}"
                self._profiles.append(p)
            except Exception as e:
                print(f"[controller_library] {fname}: {e}")

    def ensure_loaded(self):
        if self._loaded:
            return
        self._load_dir(_BUILTIN_DIR, builtin=True)
        self._load_dir(_USER_DIR, builtin=False)
        self._loaded = True

    def reload(self):
        self._profiles.clear()
        self._loaded = False
        self.ensure_loaded()

    # ── Zugriff ──────────────────────────────────────────────────────────────

    def all(self) -> list[ControllerProfile]:
        self.ensure_loaded()
        return list(self._profiles)

    def find(self, profile_id: str) -> ControllerProfile | None:
        for p in self._profiles:
            if p.id == profile_id:
                return p
        return None

    def by_type(self, device_type: str) -> list[ControllerProfile]:
        return [p for p in self.all() if p.device_type == device_type]

    # ── Import ───────────────────────────────────────────────────────────────

    def add_user_profile(self, profile: ControllerProfile) -> str:
        """Speichert ein (importiertes) Profil ins Nutzer-Verzeichnis und nimmt
        es in die geladene Liste auf. Gibt den Dateipfad zurück."""
        self.ensure_loaded()
        if self.find(profile.id) is not None:
            base = profile.id or "controller"
            n = 2
            while self.find(f"{base}-{n}") is not None:
                n += 1
            profile.id = f"{base}-{n}"
        os.makedirs(_USER_DIR, exist_ok=True)
        path = os.path.join(_USER_DIR, f"{profile.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
        self._profiles.append(profile)
        return path


_library: ControllerLibrary | None = None


def get_controller_library() -> ControllerLibrary:
    global _library
    if _library is None:
        _library = ControllerLibrary()
    return _library

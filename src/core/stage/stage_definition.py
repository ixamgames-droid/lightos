"""Stage-Geometry-Persistenz fuer den 3D-Visualizer.

Format passt zur HTML/Three.js-Seite (stage_scene.html):
  Stage-Element = { id, type, position{x,y,z}, size{x,y,z}, rotation, color }

Diese Klassen halten die kanonische Definition einer Buehne (Plattformen,
Truss, Waende, LED-Walls, Stuetzen, Audience-Areas, DJ-Booths usw.) und
serialisieren sie als JSON in %APPDATA%/LightOS/stages/<name>.json.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


SUPPORTED_TYPES = (
    "platform",
    "truss_h",
    "truss_v",
    "wall",
    "led_wall",
    "speaker",
    "audience",
    "dj_booth",
    "support",   # Alias fuer truss_v
    "truss",     # Alias fuer truss_h
)


@dataclass
class StageElement:
    """Ein einzelnes Buehnen-Element (Plattform, Truss, Wand etc.)."""

    id: str = ""
    type: str = "platform"
    # Position (Mittelpunkt)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    # Groesse (Breite, Hoehe, Tiefe)
    w: float = 4.0
    h: float = 0.4
    d: float = 4.0
    rotation: float = 0.0   # Y-Rotation in Radiant
    color: str = "#2a2a3a"
    name: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = "el_" + uuid.uuid4().hex[:8]
        # Type-Aliase normalisieren (HTML-Blueprint kennt truss_h/truss_v)
        if self.type == "truss":
            self.type = "truss_h"
        elif self.type == "support":
            self.type = "truss_v"

    # --- JSON fuer die HTML/Three.js-Seite -----------------------------------
    def to_js_dict(self) -> dict:
        """Format wie es loadStageJson() in stage_scene.html erwartet."""
        return {
            "id": self.id,
            "type": self.type,
            "position": {"x": float(self.x), "y": float(self.y), "z": float(self.z)},
            "size": {"x": float(self.w), "y": float(self.h), "z": float(self.d)},
            "rotation": float(self.rotation),
            "color": self.color,
            "name": self.name,
        }

    @classmethod
    def from_js_dict(cls, d: dict) -> "StageElement":
        pos = d.get("position") or {}
        size = d.get("size") or {}
        return cls(
            id=d.get("id", ""),
            type=d.get("type", "platform"),
            x=float(pos.get("x", d.get("x", 0.0))),
            y=float(pos.get("y", d.get("y", 0.0))),
            z=float(pos.get("z", d.get("z", 0.0))),
            w=float(size.get("x", d.get("w", 4.0))),
            h=float(size.get("y", d.get("h", 0.4))),
            d=float(size.get("z", d.get("d", 4.0))),
            rotation=float(d.get("rotation", 0.0)),
            color=d.get("color", "#2a2a3a"),
            name=d.get("name", ""),
        )


@dataclass
class StageDefinition:
    """Eine komplette Buehnen-Definition (Sammlung von Elementen)."""

    name: str = "Neue Buehne"
    elements: list[StageElement] = field(default_factory=list)

    # --- mutation ------------------------------------------------------------
    def add(self, type: str, **kwargs) -> StageElement:
        el = StageElement(type=type, **kwargs)
        self.elements.append(el)
        return el

    def remove(self, element_id: str) -> bool:
        before = len(self.elements)
        self.elements = [e for e in self.elements if e.id != element_id]
        return len(self.elements) != before

    def get(self, element_id: str) -> Optional[StageElement]:
        for e in self.elements:
            if e.id == element_id:
                return e
        return None

    def update(self, element_id: str, **kwargs) -> bool:
        el = self.get(element_id)
        if not el:
            return False
        for k, v in kwargs.items():
            if hasattr(el, k):
                setattr(el, k, v)
        return True

    # --- JSON / Persistenz ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "elements": [asdict(e) for e in self.elements],
        }

    def to_js_dict(self) -> dict:
        """Format fuer loadStageJson()."""
        return {
            "name": self.name,
            "objects": [e.to_js_dict() for e in self.elements],
            "fixtures": [],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageDefinition":
        sd = cls(name=d.get("name", "Buehne"))
        # Native format
        for el_data in d.get("elements", []) or []:
            sd.elements.append(StageElement(**el_data))
        # JS format (objects)
        for el_data in d.get("objects", []) or []:
            sd.elements.append(StageElement.from_js_dict(el_data))
        return sd


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------

def stages_dir() -> str:
    base_root = os.environ.get("APPDATA") or os.path.expanduser("~")
    base = os.path.join(base_root, "LightOS", "stages")
    os.makedirs(base, exist_ok=True)
    return base


def _safe_filename(name: str) -> str:
    keep = "-_ " + "".join(chr(c) for c in range(0x30, 0x3A))
    out = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return out or "stage"


def list_stages() -> list[str]:
    d = stages_dir()
    if not os.path.isdir(d):
        return []
    return sorted(
        f[:-5] for f in os.listdir(d) if f.lower().endswith(".json")
    )


def load_stage(name: str) -> Optional[StageDefinition]:
    path = os.path.join(stages_dir(), f"{_safe_filename(name)}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return StageDefinition.from_dict(json.load(f))
    except Exception as e:
        print(f"[stage] load error: {e}")
        return None


def save_stage(stage: StageDefinition) -> Optional[str]:
    path = os.path.join(stages_dir(), f"{_safe_filename(stage.name)}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stage.to_dict(), f, indent=2, ensure_ascii=False)
        return path
    except Exception as e:
        print(f"[stage] save error: {e}")
        return None


def delete_stage(name: str) -> bool:
    path = os.path.join(stages_dir(), f"{_safe_filename(name)}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            print(f"[stage] delete error: {e}")
    return False


# ---------------------------------------------------------------------------
# Default-Buehnen
# ---------------------------------------------------------------------------

def get_default_simple() -> StageDefinition:
    s = StageDefinition(name="Simple")
    s.add("platform", x=0, y=0.2, z=0, w=12, h=0.4, d=8, color="#2a2520", name="Stage")
    return s


def get_default_theatre() -> StageDefinition:
    s = StageDefinition(name="Theater")
    s.add("platform", x=0, y=0.25, z=0, w=16, h=0.5, d=10,
          color="#2a1a0e", name="Buehne")
    s.add("wall", x=0, y=6, z=-5, w=20, h=12, d=0.2,
          color="#1a1429", name="Hintergrund")
    s.add("wall", x=-10, y=6, z=5, w=2, h=12, d=0.4,
          color="#1a0808", name="Proszenium L")
    s.add("wall", x=10, y=6, z=5, w=2, h=12, d=0.4,
          color="#1a0808", name="Proszenium R")
    s.add("truss_h", x=0, y=9, z=0, w=15, h=0.18, d=0.18,
          color="#666666", name="Mittel-Truss")
    s.add("truss_h", x=-7, y=9, z=0, w=15, h=0.18, d=0.18,
          color="#666666", name="Links-Truss")
    s.add("truss_h", x=7, y=9, z=0, w=15, h=0.18, d=0.18,
          color="#666666", name="Rechts-Truss")
    return s


def get_default_rock() -> StageDefinition:
    s = StageDefinition(name="Rock Concert")
    s.add("platform", x=0, y=0.3, z=0, w=22, h=0.6, d=14,
          color="#111111", name="Mainstage")
    # Truss-Rahmen
    s.add("truss_h", x=0, y=9, z=-6, w=24, h=0.25, d=0.25,
          color="#666666", name="Truss hinten")
    s.add("truss_h", x=0, y=9, z=6, w=24, h=0.25, d=0.25,
          color="#666666", name="Truss vorne")
    # Seitliche Stuetzen
    for x in (-12, 12):
        for z in (-6, 6):
            s.add("truss_v", x=x, y=4.5, z=z, w=0.3, h=9, d=0.3,
                  color="#666666", name=f"Stuetze {x}/{z}")
    # LED-Wall
    s.add("led_wall", x=0, y=4, z=-5.9, w=20, h=6, d=0.15,
          color="#080820", name="LED Wand")
    # Speakers
    for x in (-11, 11):
        for i in range(3):
            s.add("speaker", x=x, y=0.6 + i * 1.25, z=5,
                  w=1.4, h=1.2, d=1.4,
                  color="#202020", name=f"Speaker {x}/{i}")
    # Audience
    s.add("audience", x=0, y=0.05, z=10, w=24, h=0.1, d=10,
          color="#0c0c10", name="Publikum")
    return s


DEFAULT_PRESETS: dict[str, "callable"] = {
    "simple": get_default_simple,
    "theatre": get_default_theatre,
    "rock": get_default_rock,
}


def get_default(name: str) -> StageDefinition:
    fn = DEFAULT_PRESETS.get((name or "simple").lower())
    return fn() if fn else get_default_simple()

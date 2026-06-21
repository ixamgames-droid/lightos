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
from typing import Callable, Optional


SUPPORTED_TYPES = (
    "platform",
    "floor",     # beweglicher Boden/Deck (grosse flache Flaeche)
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

# --- Andock-Klassifikation (Fixtures rasten an Buehnen-Elemente ein) ----------
# HANG: Strahler haengt UNTEN am Element (Trusses).
# TOP:  Strahler steht OBEN drauf (Plattform, Boden, Speaker, ...).
# Andere Typen (Waende, LED-Walls) ziehen keine Strahler an.
DOCK_HANG_TYPES = frozenset({"truss_h", "truss_v"})
DOCK_TOP_TYPES = frozenset({"platform", "floor", "dj_booth", "speaker", "audience"})
# Laenge des gedachten Clamps unter einer Trasse bzw. Sockel-Versatz auf Flaechen.
DOCK_HANG_OFFSET = 0.25
DOCK_TOP_OFFSET = 0.30


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

    # --- Geometrie-Helfer (Andocken) -----------------------------------------
    def contains_xz(self, px: float, pz: float, margin: float = 0.0) -> bool:
        """True, wenn der Punkt (px, pz) in der (gedrehten) Grundflaeche liegt.

        Beruecksichtigt die Y-Rotation: Punkt ins lokale Koordinatensystem
        des Elements zuruecktransformieren und gegen die halbe Breite/Tiefe
        pruefen. `margin` weitet die Flaeche fuer touch-tolerantes Andocken.
        """
        import math
        dx = px - self.x
        dz = pz - self.z
        c = math.cos(-self.rotation)
        s = math.sin(-self.rotation)
        local_x = dx * c - dz * s
        local_z = dx * s + dz * c
        return (abs(local_x) <= self.w / 2.0 + margin and
                abs(local_z) <= self.d / 2.0 + margin)

    @property
    def top_y(self) -> float:
        """Oberkante des Elements (fuer Raycast-Sortierung von oben)."""
        return self.y + self.h / 2.0

    def dock_y(self) -> Optional[float]:
        """Montagehoehe fuer einen daran angedockten Strahler, oder None."""
        if self.type in DOCK_HANG_TYPES:
            return self.y - self.h / 2.0 - DOCK_HANG_OFFSET
        if self.type in DOCK_TOP_TYPES:
            return self.y + self.h / 2.0 + DOCK_TOP_OFFSET
        return None


@dataclass
class StageDefinition:
    """Eine komplette Buehnen-Definition (Sammlung von Elementen)."""

    name: str = "Neue Bühne"
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

    # --- Andocken ------------------------------------------------------------
    def dock_target_for(self, px: float, pz: float, margin: float = 0.0
                        ) -> Optional[dict]:
        """Findet das Buehnen-Element, an das ein Strahler bei (px, pz) andockt.

        Spiegelt das JS-Verhalten (vertikaler Raycast von oben): unter allen
        andockbaren Elementen, deren Grundflaeche den Punkt enthaelt, wird das
        mit der hoechsten Oberkante gewaehlt (das ein Strahl von oben zuerst
        traefe). Trusses -> Strahler haengt unten dran ('hang'), Plattform/
        Boden -> oben drauf ('top'). Waende/LED-Walls docken nicht an.

        Rueckgabe: {"id", "kind", "y"} oder None.
        """
        best: Optional[StageElement] = None
        for el in self.elements:
            if el.type not in DOCK_HANG_TYPES and el.type not in DOCK_TOP_TYPES:
                continue
            if not el.contains_xz(px, pz, margin):
                continue
            if best is None or el.top_y > best.top_y:
                best = el
        if best is None:
            return None
        y = best.dock_y()
        if y is None:
            return None
        kind = "hang" if best.type in DOCK_HANG_TYPES else "top"
        return {"id": best.id, "kind": kind, "y": float(y)}

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
        sd = cls(name=d.get("name", "Bühne"))
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
# Default-Buehne
# ---------------------------------------------------------------------------

# Der Visualizer startet bewusst mit einer LEEREN Buehne: keine vorgerenderte
# Kulisse (frueher theatre/rock), nur das fixe Welt-Grid als Referenz im
# Hintergrund. Der User baut seine eigene Buehne/Trassen selbst auf.

def get_default_simple() -> StageDefinition:
    """Leere Buehne (keine Elemente) — Default fuer den Visualizer."""
    return StageDefinition(name="Leer")


# Rueckwaerts-kompatibler Alias-Name.
def get_default_empty() -> StageDefinition:
    return get_default_simple()


DEFAULT_PRESETS: dict[str, Callable[[], StageDefinition]] = {
    "simple": get_default_simple,
    "empty": get_default_simple,
}


def get_default(name: str) -> StageDefinition:
    # Unbekannte/alte Preset-Keys (z.B. "theatre"/"rock" aus Alt-Shows) fallen
    # bewusst auf die leere Buehne zurueck.
    fn = DEFAULT_PRESETS.get((name or "simple").lower())
    return fn() if fn else get_default_simple()

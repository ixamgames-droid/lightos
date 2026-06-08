"""Palette System — Color, Position, Beam preset values."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PaletteType(str, Enum):
    COLOR    = "Color"
    POSITION = "Position"
    BEAM     = "Beam"
    EFFECT   = "Effect"
    ALL      = "All"


@dataclass
class Palette:
    """A named set of attribute values applicable to any fixture."""
    name: str
    type: PaletteType = PaletteType.COLOR
    # Generic values — applied by attribute key (e.g. color_r, pan, zoom)
    values: dict[str, int] = field(default_factory=dict)
    # Per-fixture overrides (fid → {attr: val}) — empty means use generic values
    fixture_values: dict[int, dict[str, int]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    ATTR_GROUPS = {
        PaletteType.COLOR:    {"color_r", "color_g", "color_b", "color_w",
                               "color_a", "color_uv", "cmy_c", "cmy_m", "cmy_y",
                               "color_wheel"},
        PaletteType.POSITION: {"pan", "tilt", "pan_fine", "tilt_fine"},
        PaletteType.BEAM:     {"zoom", "focus", "iris", "shutter", "gobo_wheel",
                               "gobo_rotation", "prism", "frost"},
        PaletteType.EFFECT:   {"speed", "macro"},
        PaletteType.ALL:      None,   # includes everything
    }

    def get_values_for_fixture(self, fid: int) -> dict[str, int]:
        """Returns merged values: generic + per-fixture override."""
        base = dict(self.values)
        if fid in self.fixture_values:
            base.update(self.fixture_values[fid])
        return base

    def apply_to_programmer(self, fixture_ids: list[int] | None = None):
        """Push palette values into the programmer."""
        from src.core.app_state import get_state
        state = get_state()
        if fixture_ids:
            targets = fixture_ids
        else:
            # PatchedFixture sind ORM-Objekte mit .fid (nicht dicts)
            targets = []
            for f in state.get_patched_fixtures():
                fid = getattr(f, "fid", None)
                if fid is None and isinstance(f, dict):
                    fid = f.get("id") or f.get("fid")
                if fid is not None:
                    targets.append(fid)
        for fid in targets:
            vals = self.get_values_for_fixture(fid)
            for attr, val in vals.items():
                state.set_programmer_value(fid, attr, val)

    def record_from_programmer(self, fixture_ids: list[int] | None = None):
        """Capture current programmer state into this palette."""
        from src.core.app_state import get_state
        state = get_state()
        allowed = self.ATTR_GROUPS.get(self.type)
        targets = fixture_ids or list(state.programmer.keys())
        generic_accum: dict[str, list[int]] = {}
        for fid in targets:
            prog = state.programmer.get(fid, {})
            fx_vals = {}
            for attr, val in prog.items():
                if allowed is None or attr in allowed:
                    fx_vals[attr] = val
                    generic_accum.setdefault(attr, []).append(val)
            if fx_vals:
                self.fixture_values[fid] = fx_vals
        # Build generic (averaged) values
        self.values = {attr: int(sum(vals) / len(vals))
                       for attr, vals in generic_accum.items()}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "values": self.values,
            "fixture_values": {str(k): v for k, v in self.fixture_values.items()},
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Palette":
        p = cls(
            name=d["name"],
            type=PaletteType(d.get("type", "Color")),
            values=d.get("values", {}),
            tags=d.get("tags", []),
        )
        p.fixture_values = {int(k): v for k, v in d.get("fixture_values", {}).items()}
        return p


class PaletteManager:
    """Holds all palettes, organized by type."""

    def __init__(self):
        self._palettes: list[Palette] = []
        self._load_defaults()

    def _load_defaults(self):
        colors = [
            ("Rot",     {"color_r": 255, "color_g": 0,   "color_b": 0}),
            ("Grün",    {"color_r": 0,   "color_g": 255, "color_b": 0}),
            ("Blau",    {"color_r": 0,   "color_g": 0,   "color_b": 255}),
            ("Weiß",    {"color_r": 255, "color_g": 255, "color_b": 255}),
            ("Cyan",    {"color_r": 0,   "color_g": 255, "color_b": 255}),
            ("Magenta", {"color_r": 255, "color_g": 0,   "color_b": 255}),
            ("Gelb",    {"color_r": 255, "color_g": 255, "color_b": 0}),
            ("Orange",  {"color_r": 255, "color_g": 128, "color_b": 0}),
        ]
        for name, vals in colors:
            p = Palette(name=name, type=PaletteType.COLOR, values=vals)
            self._palettes.append(p)

        positions = [
            ("Center",    {"pan": 128, "tilt": 128}),
            ("Links",     {"pan": 64,  "tilt": 128}),
            ("Rechts",    {"pan": 192, "tilt": 128}),
            ("Oben",      {"pan": 128, "tilt": 64}),
            ("Unten",     {"pan": 128, "tilt": 192}),
            ("Links/Oben",{"pan": 64,  "tilt": 64}),
            ("Rechts/U.", {"pan": 192, "tilt": 192}),
        ]
        for name, vals in positions:
            p = Palette(name=name, type=PaletteType.POSITION, values=vals)
            self._palettes.append(p)

    def add(self, palette: Palette):
        self._palettes.append(palette)
        # Zentrale Benachrichtigung: neue Palette erscheint sofort in allen
        # Paletten-Ansichten (eingebettet + Sub-Tab) ohne manuelles Neuladen.
        # _load_defaults()/from_dict() umgehen add() (direktes append) → kein Spam.
        self._notify_palettes_changed()

    def remove(self, palette: Palette):
        self._palettes.remove(palette)
        self._notify_palettes_changed()

    @staticmethod
    def _notify_palettes_changed(data=None):
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.PALETTE_CHANGED, data)
        except Exception:
            pass

    def get_by_type(self, ptype: PaletteType) -> list[Palette]:
        if ptype == PaletteType.ALL:
            return list(self._palettes)
        return [p for p in self._palettes if p.type == ptype]

    def get_all(self) -> list[Palette]:
        return list(self._palettes)

    def find(self, name: str) -> Palette | None:
        for p in self._palettes:
            if p.name == name:
                return p
        return None

    def to_dict(self) -> dict:
        return {"palettes": [p.to_dict() for p in self._palettes]}

    def from_dict(self, d: dict):
        self._palettes.clear()
        for pd in d.get("palettes", []):
            self._palettes.append(Palette.from_dict(pd))


_manager: PaletteManager | None = None


def get_palette_manager() -> PaletteManager:
    global _manager
    if _manager is None:
        _manager = PaletteManager()
    return _manager

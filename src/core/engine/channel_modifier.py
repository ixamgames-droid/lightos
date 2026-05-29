"""Channel-Modifier: wandelt DMX-Eingangswerte (0-255) durch eine Curve in Output-Werte."""
from enum import Enum
from dataclasses import dataclass, field
import math


class CurveType(Enum):
    LINEAR   = "Linear"      # f(x) = x (default, kein Effekt)
    INVERSE  = "Inverse"     # f(x) = 255 - x
    SCURVE   = "S-Curve"     # f(x) = smoothstep(x/255) * 255
    GAMMA22  = "Gamma 2.2"   # f(x) = (x/255)^2.2 * 255 (perceptual brightness)
    GAMMA045 = "Gamma 0.45"  # f(x) = (x/255)^0.45 * 255 (inverse perceptual)
    SQUARED  = "Squared"     # f(x) = (x/255)^2 * 255
    SQRT     = "Square Root" # f(x) = sqrt(x/255) * 255
    CUSTOM   = "Custom"      # Liste von 256 Werten (lookup table)


@dataclass
class ChannelModifier:
    universe: int            # 1-32
    address: int             # 1-512 (absolute DMX-Adresse)
    name: str = ""
    curve: CurveType = CurveType.LINEAR
    custom_lut: list = field(default_factory=list)  # 256 Werte fuer CUSTOM
    range_min: int = 0       # Output auf [range_min, range_max] skalieren (0/255 = kein Effekt)
    range_max: int = 255

    def apply(self, value: int) -> int:
        value = max(0, min(255, int(value)))
        # 1) Curve anwenden -> out (0-255)
        if self.curve == CurveType.LINEAR:
            out = value
        elif self.curve == CurveType.CUSTOM and len(self.custom_lut) == 256:
            try:
                out = max(0, min(255, int(self.custom_lut[value])))
            except Exception:
                out = value
        else:
            x = value / 255.0
            if self.curve == CurveType.INVERSE:
                y = 1.0 - x
            elif self.curve == CurveType.SCURVE:
                y = x * x * (3.0 - 2.0 * x)
            elif self.curve == CurveType.GAMMA22:
                y = x ** 2.2
            elif self.curve == CurveType.GAMMA045:
                y = x ** 0.45
            elif self.curve == CurveType.SQUARED:
                y = x * x
            elif self.curve == CurveType.SQRT:
                y = math.sqrt(x)
            else:
                y = x
            out = max(0, min(255, int(y * 255)))
        # 2) Auf Sub-Range skalieren (Range-Lock)
        lo = max(0, min(255, int(self.range_min)))
        hi = max(0, min(255, int(self.range_max)))
        if lo != 0 or hi != 255:
            out = lo + int(round((out / 255.0) * (hi - lo)))
            out = max(0, min(255, out))
        return out


class ChannelModifierManager:
    """Singleton: alle Modifier zentral verwaltet."""

    def __init__(self):
        # {(universe, address): ChannelModifier}
        self._modifiers: dict = {}

    def add(self, mod: ChannelModifier):
        self._modifiers[(mod.universe, mod.address)] = mod

    def remove(self, universe: int, address: int):
        self._modifiers.pop((universe, address), None)

    def get(self, universe: int, address: int):
        return self._modifiers.get((universe, address))

    def all(self) -> list:
        return list(self._modifiers.values())

    def clear(self):
        self._modifiers.clear()

    def apply_to_universe(self, universe: int, data: bytes) -> bytes:
        """Wandelt data (512 Bytes) durch alle Modifier dieses Universe."""
        if not self._modifiers:
            return data
        ba = bytearray(data)
        for (u, addr), mod in self._modifiers.items():
            if u != universe:
                continue
            if 1 <= addr <= 512:
                idx = addr - 1
                if idx < len(ba):
                    try:
                        ba[idx] = mod.apply(ba[idx])
                    except Exception:
                        pass
        return bytes(ba)

    def save(self, path: str):
        import json
        data = []
        for m in self._modifiers.values():
            data.append({
                "universe": m.universe,
                "address": m.address,
                "name": m.name,
                "curve": m.curve.value,
                "custom_lut": m.custom_lut,
                "range_min": m.range_min,
                "range_max": m.range_max,
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        import json
        import os
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self._modifiers.clear()
        for d in data:
            try:
                m = ChannelModifier(
                    universe=int(d["universe"]),
                    address=int(d["address"]),
                    name=d.get("name", ""),
                    curve=CurveType(d.get("curve", "Linear")),
                    custom_lut=d.get("custom_lut", []),
                    range_min=int(d.get("range_min", 0)),
                    range_max=int(d.get("range_max", 255)),
                )
                self.add(m)
            except Exception:
                continue


_mgr = None


def get_modifier_manager() -> ChannelModifierManager:
    global _mgr
    if _mgr is None:
        _mgr = ChannelModifierManager()
    return _mgr

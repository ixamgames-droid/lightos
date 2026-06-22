"""Mapped Channel Change — eine Funktion, die einen Positions-Kanal (Pan/Tilt/X-Y)
auf einen beliebigen Ziel-Kanal abbildet ("gemappter Channel-Change").

Idee: Statt einen Wert fest zu setzen, FOLGT der Ziel-Kanal live der aktuellen
Position. Beispiel: „je höher der Moving Head (Tilt), desto röter" — Tilt 0..255
wird auf ``color_r`` 40..255 abgebildet. Oder: Tilt-Mitte → Strobe-Rate hoch.

Eine ``MappedChannelChange`` hält
  * ``fids``   – die Geräte, auf die sie wirkt (Moving Heads / Spiders),
  * ``rules``  – eine Liste ``MappedRule`` (Quelle → Ziel-Kanal, Range, Kurve).

Sie läuft als echte ``Function`` im 44-Hz-Render-Pfad (``write()`` pro Frame),
liest den AKTUELLEN Quellwert aus dem committeten Live-Universe (so folgt sie
egal ob die Position von Hand, per EFX-Bewegung oder per VC-Slider gesetzt wird)
und schreibt den gemappten Ausgangswert ins Scratch — der Programmer überschreibt
diese Kanäle dann NICHT mehr (sie gelten als funktions-getrieben, ``func_driven``).

VC-Bindung braucht KEINEN neuen Widget-Typ: die Quelle (z. B. Tilt) legt man als
normalen VCSlider im ``Programmer``-Modus auf ``tilt``; aktiviert/deaktiviert wird
die Regel per VCButton ``Funktion an/aus`` (FUNCTION_TOGGLE) auf diese Funktion.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dmx.universe import Universe
    from src.core.database.models import PatchedFixture

from .function import Function, FunctionType
from .fade_curve import eval_named, CURVE_NAMES


# Quell-Modi (Eingang). "xy" kombiniert Pan+Tilt zur radialen Auslenkung aus der
# Feldmitte (128,128) — „je weiter der Strahl von der Mitte zeigt, desto mehr".
SOURCE_TILT = "tilt"
SOURCE_PAN = "pan"
SOURCE_XY = "xy"
SOURCE_MODES = (SOURCE_TILT, SOURCE_PAN, SOURCE_XY)

# Mapping-Modi (Ausgang).
MODE_VALUE = "value"        # ein Kanal von out_min..out_max (z. B. Rot dunkel→hell, Strobe-Rate)
MODE_GRADIENT = "gradient"  # Farbverlauf zwischen color_a und color_b (RGB(W)/Farbrad)


def _clamp255(v) -> int:
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return 0
    return 0 if v < 0 else 255 if v > 255 else v


def _norm(value: float, in_min: int, in_max: int, invert: bool) -> float:
    """DMX-Eingang (0..255) → Fortschritt 0..1 über den Eingangs-Bereich."""
    lo, hi = (in_min, in_max) if in_max >= in_min else (in_max, in_min)
    t = 0.0 if hi <= lo else (value - lo) / (hi - lo)
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return 1.0 - t if invert else t


def _lerp_rgb(a, b, t: float) -> tuple[int, int, int]:
    return (_clamp255(a[0] + (b[0] - a[0]) * t),
            _clamp255(a[1] + (b[1] - a[1]) * t),
            _clamp255(a[2] + (b[2] - a[2]) * t))


@dataclass
class MappedRule:
    """Eine Abbildungs-Regel: Quelle (Position) → Ziel-Kanal.

    ``curve`` formt den Übergang (Namen aus ``fade_curve.CURVE_NAMES``): "linear"/
    "scurve"/"ease_*" = fließend, "snap" = harter Sprung am Ende.
    ``per_head``: bei Mehrkopf-Geräten (Spider mit 2 Tilts/Farb-Bänken) jeden Kopf
    aus SEINER eigenen Quell-Position mappen (Kopf 1 anders als Kopf 2).
    """
    source: str = SOURCE_TILT
    target: str = "color_r"
    mode: str = MODE_VALUE
    in_min: int = 0
    in_max: int = 255
    out_min: int = 0
    out_max: int = 255
    color_a: tuple[int, int, int] = (0, 0, 0)
    color_b: tuple[int, int, int] = (255, 0, 0)
    curve: str = "linear"
    invert: bool = False
    per_head: bool = False

    def evaluate(self, src_value: float) -> dict:
        """Bildet einen Quellwert (0..255) auf das Ergebnis ab.

        Rückgabe: ``{"value": int}`` (MODE_VALUE) oder ``{"rgb": (r,g,b)}``
        (MODE_GRADIENT). Wird AUCH von der UI-Live-Vorschau genutzt → kein Drift
        zwischen Vorschau und echtem Render.
        """
        t = _norm(src_value, self.in_min, self.in_max, self.invert)
        s = eval_named(self.curve, t)
        if self.mode == MODE_GRADIENT:
            return {"rgb": _lerp_rgb(self.color_a, self.color_b, s)}
        out = self.out_min + s * (self.out_max - self.out_min)
        return {"value": _clamp255(out)}

    # ── Serialisierung ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
            "in_min": int(self.in_min),
            "in_max": int(self.in_max),
            "out_min": int(self.out_min),
            "out_max": int(self.out_max),
            "color_a": [int(c) for c in self.color_a],
            "color_b": [int(c) for c in self.color_b],
            "curve": self.curve,
            "invert": bool(self.invert),
            "per_head": bool(self.per_head),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MappedRule":
        def _rgb(key, default):
            v = d.get(key)
            if not v:
                return default
            try:
                return (int(v[0]), int(v[1]), int(v[2]))
            except (TypeError, ValueError, IndexError):
                return default
        src = str(d.get("source", SOURCE_TILT))
        mode = str(d.get("mode", MODE_VALUE))
        curve = str(d.get("curve", "linear"))
        return cls(
            source=src if src in SOURCE_MODES else SOURCE_TILT,
            target=str(d.get("target", "color_r")),
            mode=mode if mode in (MODE_VALUE, MODE_GRADIENT) else MODE_VALUE,
            in_min=_clamp255(d.get("in_min", 0)),
            in_max=_clamp255(d.get("in_max", 255)),
            out_min=_clamp255(d.get("out_min", 0)),
            out_max=_clamp255(d.get("out_max", 255)),
            color_a=_rgb("color_a", (0, 0, 0)),
            color_b=_rgb("color_b", (255, 0, 0)),
            curve=curve if curve in CURVE_NAMES else "linear",
            invert=bool(d.get("invert", False)),
            per_head=bool(d.get("per_head", False)),
        )


def _find_fixture(patch_cache, fid):
    for fx in patch_cache or ():
        if getattr(fx, "fid", None) == fid:
            return fx
    return None


def _nth_addr(fx, chans, attr: str, head: int):
    """DMX-Adresse (1..512) des ``head``-ten Vorkommens von ``attr`` (0-basiert)."""
    cnt = 0
    for ch in chans:
        if (getattr(ch, "attribute", "") or "") == attr:
            if cnt == head:
                a = fx.address + ch.channel_number - 1
                return a if 1 <= a <= 512 else None
            cnt += 1
    return None


class MappedChannelChange(Function):
    """Bildet eine Live-Position (Pan/Tilt/X-Y) auf beliebige Ziel-Kanäle ab.

    Eigener ``FunctionType`` (KEIN geteilter EFX-Tag) → saubere Persistenz ohne
    die motion/layers/pattern-Diskriminator-Falle.
    """

    function_type = FunctionType.MappedChannelChange

    def __init__(self, name: str = "Kanal-Mapping", fid: int | None = None):
        super().__init__(name, fid)
        self.fids: list[int] = []
        self.rules: list[MappedRule] = []

    # ── Quellwert lesen ───────────────────────────────────────────────────────

    def _read_attr(self, state, fx, chans, attr: str, head: int):
        """Aktueller Wert des Quell-Kanals: bevorzugt das committete Live-Universe
        (enthält Hand-Eingabe via _flush, EFX-Output via Commit und VC), Fallback
        auf den Programmer-Wert (z. B. headless ohne Output-Thread)."""
        addr = _nth_addr(fx, chans, attr, head)
        if addr is not None:
            univ = getattr(state, "universes", {}).get(fx.universe)
            if univ is not None:
                try:
                    return univ.get_channel(addr)
                except Exception:
                    pass
        try:
            return state.get_programmer_value(fx.fid, attr, head=head)
        except Exception:
            return None

    def _read_source(self, state, fx, chans, source: str, head: int) -> float:
        if source == SOURCE_XY:
            pv = self._read_attr(state, fx, chans, "pan", head)
            tv = self._read_attr(state, fx, chans, "tilt", head)
            dx = (pv if pv is not None else 128) - 128.0
            dy = (tv if tv is not None else 128) - 128.0
            return min(255.0, math.hypot(dx, dy) / math.hypot(127.0, 127.0) * 255.0)
        v = self._read_attr(state, fx, chans, source, head)
        return 0.0 if v is None else float(v)

    @staticmethod
    def _target_heads(rule: MappedRule, chans) -> list[int]:
        base = rule.target if rule.mode == MODE_VALUE else "color_r"
        n = sum(1 for ch in chans if (getattr(ch, "attribute", "") or "") == base)
        return list(range(n)) if n >= 1 else [0]

    # ── Per-frame ─────────────────────────────────────────────────────────────

    def write(self, universes: dict[int, "Universe"],
              patch_cache: list["PatchedFixture"],
              dt: float,
              function_registry=None):
        if not self._running or not self.fids or not self.rules:
            return
        try:
            from src.core.app_state import get_state, get_channels_for_patched
            from src.core.color_utils import (color_attrs_for_fixture,
                                              adapt_color_payload)
        except Exception:
            return
        state = get_state()
        for fid in self.fids:
            fx = _find_fixture(patch_cache, fid)
            if fx is None:
                continue
            universe = universes.get(fx.universe)
            if universe is None:
                continue
            chans = get_channels_for_patched(fx)
            attr_set = {str(a) for ch in chans if (a := getattr(ch, "attribute", None))}
            attrs: dict[str, int] = {}
            for rule in self.rules:
                heads = self._target_heads(rule, chans) if rule.per_head else [0]
                for h in heads:
                    src = self._read_source(state, fx, chans, rule.source, h)
                    res = rule.evaluate(src)
                    if "value" in res:
                        key = rule.target if h == 0 else f"{rule.target}#{h}"
                        attrs[key] = res["value"]
                    else:
                        payload = color_attrs_for_fixture(chans, res["rgb"])
                        payload = adapt_color_payload(attr_set, payload)
                        for k, v in payload.items():
                            attrs[k if h == 0 else f"{k}#{h}"] = v
            if not attrs:
                continue
            # Vorkommens-bewusst schreiben (gleiche #N-Logik wie efx.py).
            seen: dict[str, int] = {}
            for ch in chans:
                a = getattr(ch, "attribute", "") or ""
                head = seen.get(a, 0)
                seen[a] = head + 1
                key = a if head == 0 else f"{a}#{head}"
                if key in attrs:
                    val = attrs[key]
                elif head == 0 and a in attrs:
                    val = attrs[a]
                else:
                    continue
                addr = fx.address + ch.channel_number - 1
                if 1 <= addr <= 512:
                    universe.set_channel(addr, _clamp255(val))

    # ── Live-Programming (VC/MIDI) ────────────────────────────────────────────

    def list_params(self) -> list:
        from .rgb_matrix_meta import ParamSpec
        return [
            ParamSpec("intensity", "Intensität", "float", 1.0, 0.0, 1.0, 0.01,
                      "Per-Effekt-Master (0..1)"),
        ]

    def get_param(self, key: str):
        if key == "intensity":
            return self.intensity
        return None

    def set_param(self, key: str, value) -> bool:
        if key == "intensity":
            self.intensity = max(0.0, min(1.0, float(value)))
            return True
        return False

    # ── Serialisierung ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "mapped": True,    # Klarheits-Diskriminator (Typ ist ohnehin eindeutig)
            "fids": [int(f) for f in self.fids],
            "rules": [r.to_dict() for r in self.rules],
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MappedChannelChange":
        m = cls(name=d.get("name", "Kanal-Mapping"), fid=d.get("id"))
        m.fids = [int(x) for x in d.get("fids", []) if x is not None]
        m.rules = [MappedRule.from_dict(r) for r in d.get("rules", [])
                   if isinstance(r, dict)]
        return m

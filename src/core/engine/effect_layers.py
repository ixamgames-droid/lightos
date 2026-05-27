"""Effect-Layer-System - modular zusammensetzbare Math-Layer.

Jeder Layer transformiert einen Eingangswert in einen Ausgangswert.
Layer werden in einer Liste hintereinander angewandt.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math
import random


class LayerType(Enum):
    CONSTANT  = "Constant"    # f(t,i) = value
    SIN       = "Sin"         # f(t,i) = amp * sin(2pi * freq * t + phase) + offset
    COS       = "Cos"
    TRIANGLE  = "Triangle"
    SAW       = "Saw"
    SQUARE    = "Square"
    RANDOM    = "Random"      # zufallswert pro Tick
    RAMP      = "Ramp"        # linear von start nach end
    PHASE_OFFSET = "PhaseOffset"  # verschiebt Phase pro Fixture-Index
    MULTIPLY  = "Multiply"    # f(in) = in * factor
    ADD       = "Add"         # f(in) = in + offset
    CLAMP     = "Clamp"       # f(in) = max(min(in, max), min)
    MAP       = "Map"         # f(in) = map(in, in_min, in_max, out_min, out_max)


@dataclass
class EffectLayer:
    """Ein Layer in der Effect-Pipeline."""
    type: LayerType = LayerType.CONSTANT
    amplitude: float = 1.0
    frequency: float = 1.0      # Hz
    phase: float = 0.0          # 0..1 (= 0..2pi)
    offset: float = 0.0
    value: float = 0.0
    min_val: float = 0.0
    max_val: float = 1.0
    fixture_phase_step: float = 0.0   # rad pro Fixture-Index

    def process(self, prev: float, t: float, fixture_index: int = 0) -> float:
        """Wandelt vorigen Wert mit dieser Schicht."""
        try:
            if self.type == LayerType.CONSTANT:
                return self.value

            # Phase pro Fixture verschieben
            phase_rad = self.phase * 2 * math.pi + fixture_index * self.fixture_phase_step

            if self.type == LayerType.SIN:
                return prev + self.amplitude * math.sin(
                    2 * math.pi * self.frequency * t + phase_rad
                ) + self.offset
            if self.type == LayerType.COS:
                return prev + self.amplitude * math.cos(
                    2 * math.pi * self.frequency * t + phase_rad
                ) + self.offset
            if self.type == LayerType.TRIANGLE:
                cyc = (self.frequency * t + phase_rad / (2 * math.pi)) % 1.0
                v = 4 * cyc - 1 if cyc < 0.5 else 3 - 4 * cyc
                return prev + self.amplitude * v + self.offset
            if self.type == LayerType.SAW:
                cyc = (self.frequency * t + phase_rad / (2 * math.pi)) % 1.0
                return prev + self.amplitude * (2 * cyc - 1) + self.offset
            if self.type == LayerType.SQUARE:
                cyc = (self.frequency * t + phase_rad / (2 * math.pi)) % 1.0
                return prev + self.amplitude * (1 if cyc < 0.5 else -1) + self.offset
            if self.type == LayerType.RANDOM:
                return prev + random.uniform(-self.amplitude, self.amplitude) + self.offset
            if self.type == LayerType.RAMP:
                ramp_phase = (self.frequency * t) % 1.0
                return prev + self.min_val + (self.max_val - self.min_val) * ramp_phase
            if self.type == LayerType.PHASE_OFFSET:
                return prev  # Phasen werden in folgenden Layern angewandt
            if self.type == LayerType.MULTIPLY:
                return prev * self.amplitude
            if self.type == LayerType.ADD:
                return prev + self.offset
            if self.type == LayerType.CLAMP:
                return max(self.min_val, min(self.max_val, prev))
            if self.type == LayerType.MAP:
                # in [in_min,in_max] -> out [out_min,out_max]
                in_min, in_max = self.min_val, self.max_val
                out_min, out_max = self.offset, self.value
                if in_max - in_min == 0:
                    return out_min
                t_norm = (prev - in_min) / (in_max - in_min)
                return out_min + t_norm * (out_max - out_min)
        except Exception as exc:
            print(f"[EffectLayer] process error ({self.type}): {exc}")
        return prev

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "amplitude": self.amplitude,
            "frequency": self.frequency,
            "phase": self.phase,
            "offset": self.offset,
            "value": self.value,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "fixture_phase_step": self.fixture_phase_step,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EffectLayer":
        try:
            lt = LayerType(d.get("type", "Constant"))
        except ValueError:
            lt = LayerType.CONSTANT
        return cls(
            type=lt,
            amplitude=d.get("amplitude", 1.0),
            frequency=d.get("frequency", 1.0),
            phase=d.get("phase", 0.0),
            offset=d.get("offset", 0.0),
            value=d.get("value", 0.0),
            min_val=d.get("min_val", 0.0),
            max_val=d.get("max_val", 1.0),
            fixture_phase_step=d.get("fixture_phase_step", 0.0),
        )

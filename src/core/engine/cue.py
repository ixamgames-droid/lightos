"""Cue-Datenmodell."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Cue:
    number: float                          # 1.0, 2.0, 2.5 ...
    label: str = ""
    fade_in: float = 2.0                   # Sekunden
    fade_out: float = 0.0
    delay_in: float = 0.0
    delay_out: float = 0.0
    follow: float | None = None            # Auto-Follow nach N Sekunden
    # F-5: Fade-Verlauf dieser Cue (scurve/linear/ease_in/ease_out/snap).
    # "scurve" = historischer Standard (Smoothstep) → Alt-Shows faden unverändert.
    fade_curve: str = "scurve"
    # {fid: {attribute: value}}
    values: dict[int, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self):
        self.number = round(float(self.number), 3)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "label": self.label,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "delay_in": self.delay_in,
            "delay_out": self.delay_out,
            "follow": self.follow,
            "fade_curve": self.fade_curve,
            "values": {str(k): v for k, v in self.values.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cue":
        c = cls(
            number=d["number"],
            label=d.get("label", ""),
            fade_in=d.get("fade_in", 2.0),
            fade_out=d.get("fade_out", 0.0),
            delay_in=d.get("delay_in", 0.0),
            delay_out=d.get("delay_out", 0.0),
            follow=d.get("follow"),
            fade_curve=d.get("fade_curve", "scurve"),
        )
        c.values = {int(k): v for k, v in d.get("values", {}).items()}
        return c

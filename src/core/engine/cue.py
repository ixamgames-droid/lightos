"""Cue-Datenmodell."""
from __future__ import annotations
from dataclasses import dataclass, field


def _coerce_values(raw) -> dict[int, dict[str, int]]:
    """{fid: {attr: int}} defensiv aus rohen (ggf. hand-editierten) Daten."""
    out: dict[int, dict[str, int]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            fid = int(k)
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            out[fid] = v
    return out


def _coerce_attr_delays(raw) -> dict[int, dict[str, float]]:
    """F-6: {fid: {attr: float_sekunden}} defensiv — kaputte Einträge werden
    übersprungen statt eine Exception zu werfen (sonst ginge beim Laden die ganze
    Cuelisten-Sektion verloren)."""
    out: dict[int, dict[str, float]] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            fid = int(k)
        except (TypeError, ValueError):
            continue
        if not isinstance(v, dict):
            continue
        inner: dict[str, float] = {}
        for a, dl in v.items():
            try:
                inner[str(a)] = float(dl)
            except (TypeError, ValueError):
                continue
        if inner:
            out[fid] = inner
    return out


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
    # F-16: optionale Referenz auf eine andere Cueliste (Index in state.cue_stacks),
    # die beim Erreichen dieser Cue mitläuft ("Sequence-in-Sequence"). None = aus.
    #   sub_stack_mode "merge" = Sub-Cueliste läuft nebenher und wird in den Output
    #   gemischt (LTP). Alt-Shows haben den Schlüssel nicht → None → unverändert.
    sub_stack_ref: int | None = None
    sub_stack_mode: str = "merge"
    # {fid: {attribute: value}}
    values: dict[int, dict[str, int]] = field(default_factory=dict)
    # F-6: optionale PRO-ATTRIBUT-Verzögerung (Sekunden) ZUSÄTZLICH zum Cue-Delay,
    #   beim Hinein-Faden (GO/Vorwärts). {fid: {attribute: extra_delay_sekunden}}
    #   — leer = bisheriges Verhalten.
    attr_delays: dict[int, dict[str, float]] = field(default_factory=dict)
    # ENG-01: dieselbe Pro-Attribut-Verzögerung für den AUSWÄRTS-Fade (BACK / Fade-Out).
    #   Symmetrisch zu den Cue-Delays delay_in/delay_out: ``attr_delays`` gilt beim
    #   GO (Basis delay_in), ``attr_delays_out`` beim BACK (Basis delay_out).
    #   Leer = wie bisher (BACK nutzt dann nur die Cue-Delay-Basis).
    attr_delays_out: dict[int, dict[str, float]] = field(default_factory=dict)

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
            "sub_stack_ref": self.sub_stack_ref,
            "sub_stack_mode": self.sub_stack_mode,
            "values": {str(k): v for k, v in self.values.items()},
            "attr_delays": {
                str(k): {a: float(d) for a, d in v.items()}
                for k, v in self.attr_delays.items()
            },
            "attr_delays_out": {
                str(k): {a: float(d) for a, d in v.items()}
                for k, v in self.attr_delays_out.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Cue":
        # F-16: defensiv gegen hand-editierte Shows (z. B. "2" statt 2, Tippfehler).
        ref = d.get("sub_stack_ref")
        try:
            ref = int(ref) if ref is not None else None
        except (TypeError, ValueError):
            ref = None
        mode = d.get("sub_stack_mode", "merge")
        if mode not in ("merge", "sequential"):
            mode = "merge"
        c = cls(
            number=d["number"],
            label=d.get("label", ""),
            fade_in=d.get("fade_in", 2.0),
            fade_out=d.get("fade_out", 0.0),
            delay_in=d.get("delay_in", 0.0),
            delay_out=d.get("delay_out", 0.0),
            follow=d.get("follow"),
            fade_curve=d.get("fade_curve", "scurve"),
            sub_stack_ref=ref,
            sub_stack_mode=mode,
        )
        c.values = _coerce_values(d.get("values"))
        c.attr_delays = _coerce_attr_delays(d.get("attr_delays"))
        c.attr_delays_out = _coerce_attr_delays(d.get("attr_delays_out"))
        return c

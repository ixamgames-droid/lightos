"""Controller-Vorlage fuer die Virtual Console (APC mini / APC mini mk2).

Liefert eine fertige Widget-Liste (``to_dict``-Dicts), die auf den ``VCCanvas``
gelegt werden kann: ein beschriftetes Abbild des MIDI-Controllers (8x8-Pad-
Raster + Fader-Reihe, bereits auf die richtigen Notes/CCs gemappt). Reiner
Daten-Builder (kein Engine-Zugriff); den Pads/Fadern weist man danach im
Eigenschaften-Dialog/Rechtsklick Funktionen zu.

* :func:`controller_template` — baut das Panel fuer ``kind`` aus :data:`CONTROLLERS`.
"""
from __future__ import annotations

from .vc_button import VCButton, ButtonAction
from .vc_slider import VCSlider, SliderMode
from .vc_label import VCLabel

# ── Physische Layouts der unterstuetzten Controller ─────────────────────────────
# grid: 8x8 Pads = Notes 0..63 (Note 0 unten links). track: 8 Tasten unter dem
# Grid. scene: 8 Tasten rechts (Seiten). fader_cc: 9 Fader-CCs.
CONTROLLERS = {
    "apc_mini": {
        "label": "Akai APC mini (Original)",
        "track": list(range(64, 72)),     # 64..71
        "scene": list(range(82, 90)),     # 82..89
        "fader_cc": list(range(48, 57)),  # 48..56
    },
    "apc_mini_mk2": {
        "label": "Akai APC mini mk2",
        "track": list(range(100, 108)),   # 100..107
        "scene": list(range(112, 120)),   # 112..119
        "fader_cc": list(range(48, 57)),  # 48..56
    },
}

_PAD = 54
_GAP = 6
_STEP = _PAD + _GAP


def _pad_pos(note: int, x0: int, y0: int) -> tuple[int, int]:
    """Note 0..63 -> (x, y); Note 0 unten links, 56 oben links."""
    row, col = note // 8, note % 8
    return x0 + col * _STEP, y0 + (7 - row) * _STEP


def _btn_dict(caption, x, y, w, h, bank, **extra) -> dict:
    b = VCButton(caption)
    b.bank = bank
    b.setGeometry(x, y, w, h)
    for k, v in extra.items():
        setattr(b, k, v)
    return b.to_dict()


def _slider_dict(caption, x, y, w, h, bank, **extra) -> dict:
    s = VCSlider(caption)
    s.bank = bank
    s.setGeometry(x, y, w, h)
    for k, v in extra.items():
        setattr(s, k, v)
    return s.to_dict()


def _label_dict(caption, x, y, w, h, bank) -> dict:
    lab = VCLabel(caption)
    lab.bank = bank
    lab.setGeometry(x, y, w, h)
    return lab.to_dict()


def controller_template(kind: str = "apc_mini", x0: int = 20, y0: int = 70,
                        bank: int = -1) -> list[dict]:
    """Beschriftetes Abbild eines MIDI-Controllers als VC-Widgets.

    Erzeugt 64 Platzhalter-Pads (Note-Nummer als Beschriftung, bereits auf die
    richtige MIDI-Note gemappt) + 9 Fader (auf CC gemappt) + Beschriftungen fuer
    Track-/Scene-Tasten. Den Pads/Fadern weist man dann nur noch Funktionen zu.
    """
    spec = CONTROLLERS.get(kind, CONTROLLERS["apc_mini"])
    out: list[dict] = []
    out.append(_label_dict(f"Controller-Vorlage: {spec['label']}  -  Pads mit Note-Nummer "
                           "(Rechtsklick -> Funktion/Farbe zuweisen)", x0, y0 - 24, 900, 20, bank))
    # 8x8 Grid-Platzhalter
    for note in range(64):
        x, y = _pad_pos(note, x0, y0)
        out.append(_btn_dict(f"{note}", x, y, _PAD, _PAD, bank,
                             action=ButtonAction.TOGGLE, pad_style="solid",
                             midi_type="note_on", midi_ch=0, midi_data1=note))
    grid_bottom = y0 + 8 * _STEP
    # Track-Tasten (Beschriftung) unter dem Grid
    for i, note in enumerate(spec["track"]):
        out.append(_btn_dict(f"Trk {note}", x0 + i * (_PAD + 8), grid_bottom + 4, _PAD, 24, bank,
                             action=ButtonAction.TOGGLE, pad_style="solid",
                             midi_type="note_on", midi_ch=0, midi_data1=note))
    # Fader-Reihe (CC) unter den Track-Tasten
    y_fad = grid_bottom + 34
    for i, cc in enumerate(spec["fader_cc"]):
        out.append(_slider_dict(f"F{i + 1} CC{cc}", x0 + i * _STEP + 2, y_fad, 50, 140, bank,
                                mode=SliderMode.LEVEL, midi_cc=cc, midi_ch=0))
    # Scene-Tasten-Legende rechts (Seitenwahl)
    for i, note in enumerate(spec["scene"]):
        out.append(_label_dict(f"Scene {i + 1}  (Note {note})  -> Seite {i + 1}",
                               x0 + 8 * _STEP + 16, y0 + i * 24, 220, 20, bank))
    return out

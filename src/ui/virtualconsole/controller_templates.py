"""Controller-Vorlagen + Bausteine fuer die Virtual Console.

Liefert fertige Widget-Listen (als ``to_dict``-Dicts), die direkt auf den
``VCCanvas`` gelegt werden koennen (``VCView._insert_widgets``):

* :func:`controller_template` — bildet ein MIDI-Panel (APC mini / APC mini mk2)
  als beschriftetes 8x8-Raster + Fader-Reihe nach, mit bereits korrekt gesetzten
  MIDI-Notes/CCs. So sieht man auf der virtuellen Konsole, **wo welche Hardware-
  Taste liegt** und muss den Pads nur noch Funktionen zuweisen (Rechtsklick).

* :func:`color_chase_kit` — ein wiederverwendbarer **Live-Color-Chase-Baustein**
  (Farb-Pads im Modus „Farbe hinzufuegen" + Start/Clear/Farbe±-Tasten + Speed-/
  Uebergang-Fader), alles auf eine COLORFADE-Funktion gebunden. Damit baut man
  einen Color-Chase live aus angewaehlten Farben zusammen.

Die Bausteine sind reine Daten-Builder (kein Engine-Zugriff). Den COLORFADE-Effekt
fuer das Kit legt der Aufrufer an und uebergibt dessen ``function_id``.
"""
from __future__ import annotations

from .vc_button import VCButton, ButtonAction
from .vc_color import VCColor, ColorTarget
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


def _color_dict(caption, x, y, w, h, bank, **extra) -> dict:
    c = VCColor(caption)
    c.bank = bank
    c.setGeometry(x, y, w, h)
    for k, v in extra.items():
        setattr(c, k, v)
    return c.to_dict()


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


def color_chase_kit(function_id: int, x0: int = 20, y0: int = 70, bank: int = -1,
                    palette: list[tuple] | None = None) -> list[dict]:
    """Wiederverwendbarer Live-Color-Chase-Baustein als VC-Widgets.

    ``function_id`` ist die ID einer COLORFADE-RGB-Matrix (vom Aufrufer angelegt).
    Farb-Pads haengen ihre Farbe live an die Color-Sequence an; Start/Clear steuern
    den Chase; zwei Fader regeln Tempo (Speed) und Uebergang (hold).
    """
    if palette is None:
        palette = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                   ("Grün", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                   ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0),
                   ("Pink", 255, 0, 120, 0), ("Türkis", 0, 220, 180, 0),
                   ("Weiß", 255, 255, 255, 255)]
    out: list[dict] = []
    out.append(_label_dict("Color-Chase-Baukasten: 1) Clear  2) Farben antippen  3) Start  "
                           "-  Fader = Speed / Übergang", x0, y0 - 24, 760, 20, bank))
    # Farb-Pads (Farbe hinzufuegen) — bis zu 2 Reihen
    for i, (nm, r, g, b, w) in enumerate(palette):
        row, col = divmod(i, 8)
        x, y = x0 + col * _STEP, y0 + row * _STEP
        out.append(_color_dict(nm, x, y, _PAD, _PAD, bank,
                               color_r=r, color_g=g, color_b=b, color_w=w,
                               with_intensity=False, target=ColorTarget.EFFECT_ADD,
                               function_id=function_id,
                               midi_type="note_on", midi_ch=0, midi_data1=-1))
    # Steuer-Tasten unter den Farben
    rows = (len(palette) + 7) // 8
    ctl_y = y0 + rows * _STEP + 6
    out.append(_btn_dict("Start", x0, ctl_y, _PAD, _PAD, bank,
                         action=ButtonAction.FUNCTION_TOGGLE, function_id=function_id,
                         pad_style="pulse", midi_type="note_on", midi_ch=0, midi_data1=-1))
    for i, (cap, key) in enumerate([("Clear", "clear_colors"), ("Farbe -", "prev_color"),
                                    ("Farbe +", "next_color")]):
        out.append(_btn_dict(cap, x0 + (i + 1) * _STEP, ctl_y, _PAD, _PAD, bank,
                             action=ButtonAction.EFFECT_ACTION, effect_action_key=key,
                             function_id=function_id, pad_style="solid",
                             midi_type="note_on", midi_ch=0, midi_data1=-1))
    # Fader: Speed + Uebergang
    fad_y = ctl_y + _STEP + 6
    out.append(_slider_dict("Speed", x0, fad_y, 50, 140, bank,
                            mode=SliderMode.EFFECT_SPEED, function_id=function_id,
                            _value=70, midi_cc=-1, midi_ch=0))
    out.append(_slider_dict("Übergang", x0 + _STEP, fad_y, 50, 140, bank,
                            mode=SliderMode.EFFECT_PARAM, function_id=function_id,
                            param_key="hold", _value=64, midi_cc=-1, midi_ch=0))
    return out


def color_chase_kit_in_rect(function_id: int, x: int, y: int, w: int, h: int,
                            bank: int = -1, palette: list[tuple] | None = None) -> list[dict]:
    """Wie :func:`color_chase_kit`, aber **fuellt ein aufgezogenes Rechteck**.

    Wird vom Canvas-Editor benutzt: der Nutzer zieht einen Bereich auf, hier wird
    ein passend skalierter Live-Color-Chase hineingelegt (Farb-Pads + Steuer-Tasten
    + Speed/Uebergang-Fader). ``function_id`` = ID der COLORFADE-Funktion.
    """
    if palette is None:
        palette = [("Rot", 255, 0, 0, 0), ("Orange", 255, 90, 0, 0), ("Gelb", 255, 220, 0, 0),
                   ("Grün", 0, 255, 0, 0), ("Cyan", 0, 255, 255, 0), ("Blau", 0, 0, 255, 0),
                   ("Violett", 140, 0, 255, 0), ("Magenta", 255, 0, 255, 0)]
    gap = 6
    w = max(240, int(w))
    h = max(220, int(h))
    cols = max(3, min(8, (w - gap) // (48 + gap)))
    pad = max(40, min(64, (w - (cols + 1) * gap) // cols))
    out: list[dict] = []
    out.append(_label_dict("Color-Chase: Clear -> Farben antippen -> Start", x, y, w, 18, bank))
    cy = y + 22
    # Farb-Pads (Farbe hinzufuegen), zeilenweise im Rechteck
    n = min(len(palette), cols * 2)        # max 2 Reihen Farben
    for i in range(n):
        row, col = divmod(i, cols)
        nm, r, g, b, ww = palette[i]
        out.append(_color_dict(nm, x + gap + col * (pad + gap), cy + row * (pad + gap),
                               pad, pad, bank, color_r=r, color_g=g, color_b=b, color_w=ww,
                               with_intensity=False, target=ColorTarget.EFFECT_ADD,
                               function_id=function_id,
                               midi_type="note_on", midi_ch=0, midi_data1=-1))
    rows = (n + cols - 1) // cols
    cy += rows * (pad + gap) + 4
    # Steuer-Tasten
    ctl = [("Start", ButtonAction.FUNCTION_TOGGLE, None), ("Clear", ButtonAction.EFFECT_ACTION, "clear_colors"),
           ("Farbe -", ButtonAction.EFFECT_ACTION, "prev_color"), ("Farbe +", ButtonAction.EFFECT_ACTION, "next_color")]
    for i, (cap, act, key) in enumerate(ctl[:cols]):
        extra = dict(action=act, function_id=function_id, pad_style="solid",
                     midi_type="note_on", midi_ch=0, midi_data1=-1)
        if key:
            extra["effect_action_key"] = key
        elif act == ButtonAction.FUNCTION_TOGGLE:
            extra["pad_style"] = "pulse"
        out.append(_btn_dict(cap, x + gap + i * (pad + gap), cy, pad, pad, bank, **extra))
    cy += pad + 6
    # Fader (Speed + Uebergang), Hoehe an Rest des Rechtecks angepasst
    fad_h = max(90, min(150, (y + h) - cy - 6))
    out.append(_slider_dict("Speed", x + gap, cy, 50, fad_h, bank,
                            mode=SliderMode.EFFECT_SPEED, function_id=function_id,
                            _value=70, midi_cc=-1, midi_ch=0))
    out.append(_slider_dict("Übergang", x + gap + 60, cy, 50, fad_h, bank,
                            mode=SliderMode.EFFECT_PARAM, function_id=function_id,
                            param_key="hold", _value=64, midi_cc=-1, midi_ch=0))
    return out

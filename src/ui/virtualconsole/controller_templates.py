"""Controller-Vorlagen fuer die Virtual Console (APC mini / mk2, Mackie Control).

Liefert eine fertige Widget-Liste (``to_dict``-Dicts), die auf den ``VCCanvas``
gelegt werden kann: ein beschriftetes Abbild des MIDI-Controllers (8x8-Pad-
Raster + Fader-Reihe, bereits auf die richtigen Notes/CCs gemappt). Reiner
Daten-Builder (kein Engine-Zugriff); den Pads/Fadern weist man danach im
Eigenschaften-Dialog/Rechtsklick Funktionen zu.

* :func:`controller_template` — baut das Panel fuer ``kind`` aus :data:`CONTROLLERS`.
* :func:`mackie_template` — MIDI-18: Motorpult im Mackie-Control-Modus (MCU,
  X-Touch, iCON …): 8 Kanalzuege + Master, Fader mit Motor, Tasten mit LED.
* :func:`vorlage_bauen` / :func:`vorlage_name` — fuer den Controller-Browser
  (``ControllerProfile.vc_template``).
"""
from __future__ import annotations

from .vc_button import VCButton, ButtonAction
from .vc_slider import VCSlider, SliderMode
from .vc_label import VCLabel
from .vc_encoder import VCEncoder, EncoderMidiMode

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


# ── MIDI-18: Motorpult im Mackie-Control-Modus ──────────────────────────────────
# Belegung (Logic-Control-Doku, Ardour): Fader n = Pitchbend auf Kanal n (1..8),
# Master = Kanal 9; Tasten und V-Pots auf Kanal 1. Tasten von oben nach unten
# wie am X-Touch/MCU: REC, SOLO, MUTE, SELECT.
MACKIE_TASTEN = (("REC", 0), ("SOLO", 8), ("MUTE", 16), ("SELECT", 24))
MACKIE_VPOT_CC = 16          # V-Pot n = CC 16+n-1, relativ mit Vorzeichenbit
MACKIE_KANAL = 1             # Tasten, V-Pots, Beruehrung
MACKIE_MASTER_KANAL = 9

_ZUG = 84                    # Breite eines Kanalzugs
_ZUG_W = 72


def _encoder_dict(caption, x, y, w, h, bank, **extra) -> dict:
    e = VCEncoder(caption)
    e.bank = bank
    e.setGeometry(x, y, w, h)
    for k, v in extra.items():
        setattr(e, k, v)
    return e.to_dict()


def mackie_template(x0: int = 20, y0: int = 50, bank: int = -1) -> list[dict]:
    """Motorpult (Mackie Control) als VC-Widgets.

    Je Kanalzug n (1..8): V-Pot als relativer Encoder (CC 16+n-1, Kanal 1,
    Vorzeichenbit), vier Tasten (Note auf Kanal 1, LED-Rueckmeldung an) und
    ein Fader (Pitchbend Kanal n, Motor nachfuehren, Modus Level). Dazu der
    Master-Fader (Pitchbend Kanal 9) als Grand Master. Funktionen weist man
    danach zu; die Tasten leuchten erst mit Funktion dauerhaft (ohne: nur
    solange gedrueckt).
    """
    out: list[dict] = []
    out.append(_label_dict("Motorpult (Mackie Control): Fader folgen dem Pult und "
                           "fahren mit. Rechtsklick → Funktion zuweisen",
                           x0, y0 - 30, 8 * _ZUG + 90, 22, bank))
    y_tasten = y0 + 96
    y_fader = y_tasten + len(MACKIE_TASTEN) * 32 + 6
    for i in range(8):
        n = i + 1
        x = x0 + i * _ZUG
        out.append(_encoder_dict(f"V-Pot {n}", x, y0, _ZUG_W, 90, bank,
                                 midi_mode=EncoderMidiMode.RELATIVE_SIGN,
                                 midi_cc=MACKIE_VPOT_CC + i, midi_ch=MACKIE_KANAL))
        for j, (name, erste) in enumerate(MACKIE_TASTEN):
            out.append(_btn_dict(f"{name} {n}", x, y_tasten + j * 32, _ZUG_W, 28, bank,
                                 action=ButtonAction.TOGGLE, pad_style="solid",
                                 midi_type="note_on", midi_ch=MACKIE_KANAL,
                                 midi_data1=erste + i, midi_led=True))
        out.append(_slider_dict(f"Fader {n}", x + 6, y_fader, 60, 220, bank,
                                mode=SliderMode.LEVEL, midi_type="pitchbend",
                                midi_cc=0, midi_ch=n, midi_motor=True))
    x_master = x0 + 8 * _ZUG + 16
    out.append(_label_dict("Master", x_master, y_fader - 26, 72, 22, bank))
    out.append(_slider_dict("Master", x_master + 6, y_fader, 60, 220, bank,
                            mode=SliderMode.GRANDMASTER, midi_type="pitchbend",
                            midi_cc=0, midi_ch=MACKIE_MASTER_KANAL, midi_motor=True))
    return out


# ── Zugang fuer den Controller-Browser ──────────────────────────────────────────
_VORLAGEN_NAMEN = {k: v["label"] for k, v in CONTROLLERS.items()}
_VORLAGEN_NAMEN["mackie_control"] = "Motorpult (Mackie Control)"


def vorlage_name(kind: str) -> str:
    """Anzeigename der Vorlage, ``""`` wenn es sie nicht gibt."""
    return _VORLAGEN_NAMEN.get(str(kind or ""), "")


def vorlage_bauen(kind: str, bank: int = -1) -> list[dict]:
    """Widget-Liste fuer ``kind``; leer, wenn es die Vorlage nicht gibt (kein
    stiller Rueckfall auf den APC wie bei :func:`controller_template`)."""
    if kind == "mackie_control":
        return mackie_template(bank=bank)
    if kind in CONTROLLERS:
        return controller_template(kind, bank=bank)
    return []

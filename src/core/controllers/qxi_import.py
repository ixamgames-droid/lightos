"""QLC+-Inputprofil (.qxi) → LightOS-Controller-Profil (Konverter-Kern).

Wird vom CLI-Wrapper ``tools/import_qlc_input_profile.py`` UND vom
Controller-Browser (UI, „QLC+ .qxi importieren…") genutzt.

Die .qxi-Dateien stammen aus dem QLC+-Projekt (Apache-2.0) — entweder aus einer
QLC+-Installation (Ordner `InputProfiles/`) oder aus dem GitHub-Repository
(`resources/inputprofiles/`). Quelle und Lizenz werden im importierten Profil
vermerkt. Importiert wird nach %APPDATA%/LightOS/controller_library/ — die
mitgelieferten Builtins bleiben unangetastet (gleiche id → Suffix).

Kanal-Dekodierung: QLC+ kodiert MIDI in eine flache Kanalnummer
(Seite = MIDI-Kanal × 4096; innerhalb der Seite: 0–127 = CC, 128–255 = Note,
256–383 = Note-Aftertouch, 384–511 = Program Change, 512 = Channel-Aftertouch,
513 = Pitch-Wheel). Unbekannte Nummern werden als type="other" mit der
Original-Nummer im layout-Feld übernommen (nichts geht verloren).
"""
from __future__ import annotations

import datetime
import os
import xml.etree.ElementTree as ET

from .controller_library import (ControllerControl, ControllerProfile,
                                 get_controller_library)

_NS = "{http://www.qlcplus.org/InputProfile}"

_PAGE = 4096
_OFF_CC = 0
_OFF_NOTE = 128
_OFF_NOTE_AT = 256
_OFF_PROG = 384
_OFF_CH_AT = 512
_OFF_PITCH = 513


def _decode_channel(number: int) -> tuple[str, int, int, str]:
    """(typ, midi_kanal, nummer, hinweis) aus einer QLC+-Kanalnummer."""
    midi_ch = number // _PAGE
    off = number % _PAGE
    if _OFF_CC <= off < _OFF_NOTE:
        return ("cc", midi_ch, off - _OFF_CC, "")
    if _OFF_NOTE <= off < _OFF_NOTE_AT:
        return ("note", midi_ch, off - _OFF_NOTE, "")
    if _OFF_NOTE_AT <= off < _OFF_PROG:
        return ("other", midi_ch, off - _OFF_NOTE_AT, "Note-Aftertouch")
    if _OFF_PROG <= off < _OFF_CH_AT:
        return ("other", midi_ch, off - _OFF_PROG, "Program Change")
    if off == _OFF_CH_AT:
        return ("other", midi_ch, 0, "Channel-Aftertouch")
    if off == _OFF_PITCH:
        return ("pitchbend", midi_ch, 0, "")
    return ("other", midi_ch, off, f"QLC+-Kanal {number}")


def _find(elem, tag):
    """Element mit und ohne Namespace suchen (alte .qxi haben keinen)."""
    found = elem.find(f"{_NS}{tag}")
    return found if found is not None else elem.find(tag)


def _findall(elem, tag):
    found = elem.findall(f"{_NS}{tag}")
    return found if found else elem.findall(tag)


def convert_qxi(path: str) -> ControllerProfile:
    tree = ET.parse(path)
    root = tree.getroot()

    manu_el = _find(root, "Manufacturer")
    manufacturer = (manu_el.text or "").strip() if manu_el is not None else ""
    model_el = _find(root, "Model")
    model = ((model_el.text or "").strip() if model_el is not None else "") \
        or os.path.basename(path)

    controls: list[ControllerControl] = []
    n_buttons = n_faders = n_encoders = 0
    for ch in _findall(root, "Channel"):
        try:
            number = int(ch.get("Number", "0"))
        except ValueError:
            continue
        name_el = _find(ch, "Name")
        type_el = _find(ch, "Type")
        name = (name_el.text or "").strip() if name_el is not None else ""
        qtype = (type_el.text or "").strip() if type_el is not None else ""
        mtype, midi_ch, num, hint = _decode_channel(number)
        ql = qtype.lower()
        if ql == "button":
            n_buttons += 1
        elif ql in ("slider", "knob"):
            n_faders += 1
        elif ql == "encoder":
            n_encoders += 1
        layout_bits = [b for b in (qtype, hint) if b]
        controls.append(ControllerControl(
            name=name or f"{qtype or mtype} {num}",
            type=mtype, channel=midi_ch, range=[num, num],
            layout=" · ".join(layout_bits)))

    base_id = "qlc_" + "".join(
        c.lower() if c.isalnum() else "_"
        for c in f"{manufacturer}_{model}").strip("_")
    return ControllerProfile(
        id=base_id,
        manufacturer=manufacturer,
        model=model,
        device_type=("midi_grid_controller" if n_buttons >= 32
                     else "midi_fader_controller"),
        connections=["USB-MIDI"],
        buttons=n_buttons,
        faders=n_faders,
        encoders=n_encoders,
        controls=controls,
        source=f"QLC+-Inputprofil '{os.path.basename(path)}' (QLC+-Projekt)",
        license="Apache-2.0 (QLC+, https://github.com/mcallegari/qlcplus)",
        imported_at=datetime.date.today().isoformat(),
    )


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in argv
    if not args:
        print(__doc__)
        return 1
    lib = get_controller_library()
    for path in args:
        if not os.path.isfile(path):
            print(f"FEHLER: Datei nicht gefunden: {path}")
            continue
        try:
            profile = convert_qxi(path)
        except Exception as e:
            print(f"FEHLER beim Konvertieren von {path}: {e}")
            continue
        print(f"{path} → {profile.label}: {profile.buttons} Tasten, "
              f"{profile.faders} Fader/Knobs, {profile.encoders} Encoder, "
              f"{len(profile.controls)} Controls")
        if dry:
            continue
        out = lib.add_user_profile(profile)
        print(f"  gespeichert: {out}")
    return 0

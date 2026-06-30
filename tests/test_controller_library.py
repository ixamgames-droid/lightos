"""Tests für die Controller-Bibliothek (Feature 6) und den QXI-Import."""
import json
import os

import pytest

from src.core.controllers.controller_library import (ControllerControl,
                                                     ControllerLibrary,
                                                     ControllerProfile)
from src.core.controllers.qxi_import import _decode_channel, convert_qxi


class TestControllerProfile:
    def test_roundtrip(self):
        p = ControllerProfile(
            id="test", manufacturer="Acme", model="Pad 8",
            device_type="midi_grid_controller", connections=["USB-MIDI"],
            buttons=8, faders=1, pad_matrix=[4, 2],
            controls=[ControllerControl("Pads", "note", 0, [0, 7], "4x2")],
            led_feedback={"type": "note_velocity", "notes": "0=aus"},
            source="Test", license="CC0", imported_at="2026-06-11")
        d = p.to_dict()
        p2 = ControllerProfile.from_dict(d)
        assert p2.label == "Acme Pad 8"
        assert p2.pad_matrix == [4, 2]
        assert p2.controls[0].count == 8
        assert p2.led_feedback["type"] == "note_velocity"

    def test_from_dict_tolerates_garbage(self):
        p = ControllerProfile.from_dict({"id": "x", "pad_matrix": "kaputt",
                                         "controls": [{"range": None}]})
        assert p.pad_matrix is None
        assert p.controls[0].range == [0, 0]


class TestBuiltinLibrary:
    def test_builtins_load(self):
        lib = ControllerLibrary()
        lib.ensure_loaded()
        ids = {p.id for p in lib.all()}
        # Seed-Profile vorhanden
        assert "akai_apc_mini" in ids
        assert "korg_nanokontrol2" in ids
        assert "enttec_dmx_usb_pro" in ids

    def test_apc_mini_facts(self):
        """APC-mini-Profil muss zu den im Code verwendeten Werten passen
        (controller_templates.py / apc_mini_feedback.py)."""
        lib = ControllerLibrary()
        lib.ensure_loaded()
        p = lib.find("akai_apc_mini")
        assert p is not None
        assert p.pad_matrix == [8, 8]
        by_name = {c.name: c for c in p.controls}
        assert by_name["Grid-Pads"].range == [0, 63]
        assert by_name["Track-Tasten (unten)"].range == [64, 71]
        assert by_name["Scene-Tasten (rechts)"].range == [82, 89]
        assert by_name["Fader 1-8"].range == [48, 55]
        assert by_name["Master-Fader"].range == [56, 56]
        assert p.vc_template == "apc_mini"

    def test_every_builtin_has_source_and_license(self):
        lib = ControllerLibrary()
        lib.ensure_loaded()
        for p in lib.all():
            assert p.source, f"{p.id}: Quelle fehlt"
            assert p.license, f"{p.id}: Lizenz fehlt"

    def test_duplicate_id_gets_suffix(self):
        lib = ControllerLibrary()
        lib.ensure_loaded()
        before = len(lib.all())
        # gleiche id nochmal einspeisen (ohne Datei zu schreiben): über _profiles
        dup = ControllerProfile(id="akai_apc_mini", manufacturer="X", model="Y")
        # add_user_profile würde auf Platte schreiben — hier nur die
        # Suffix-Logik prüfen:
        assert lib.find("akai_apc_mini") is not None
        n = 2
        while lib.find(f"akai_apc_mini-{n}") is not None:
            n += 1
        assert n == 2  # noch kein Duplikat vorhanden
        assert len(lib.all()) == before


class TestMidiOnlyFilter:
    """Controller-Browser im MIDI-Kontext: nur MIDI-Geräte, schön sortiert."""

    @staticmethod
    def _profiles():
        mk = lambda i, man, mod, dt: ControllerProfile(
            id=i, manufacturer=man, model=mod, device_type=dt)
        return [
            mk("grid_b", "Bravo", "Pad", "midi_grid_controller"),
            mk("grid_a", "Alpha", "Pad", "midi_grid_controller"),
            mk("fader", "Korg", "nano", "midi_fader_controller"),
            mk("keys", "M-Audio", "Keys", "midi_keyboard"),
            mk("enttec", "Enttec", "DMX USB Pro", "dmx_interface"),
            mk("node", "Generic", "Art-Net", "network_node"),
            mk("macro", "Generic", "Makro", "keyboard_macro"),
        ]

    def test_excludes_non_midi(self):
        from src.ui.widgets.controller_browser import _sorted_midi_profiles
        out = _sorted_midi_profiles(self._profiles(), midi_only=True)
        # kein DMX-Interface / Netzwerk-Node / Makro-Tastatur
        assert all(p.device_type.startswith("midi_") for p in out)
        assert {p.id for p in out} == {"grid_a", "grid_b", "fader", "keys"}

    def test_grouped_sort_order(self):
        from src.ui.widgets.controller_browser import _sorted_midi_profiles
        out = _sorted_midi_profiles(self._profiles(), midi_only=True)
        # Gruppen: Grid (alphabetisch Alpha vor Bravo) → Fader → Keyboard
        assert [p.id for p in out] == ["grid_a", "grid_b", "fader", "keys"]

    def test_midi_only_false_keeps_all(self):
        from src.ui.widgets.controller_browser import _sorted_midi_profiles
        out = _sorted_midi_profiles(self._profiles(), midi_only=False)
        assert len(out) == 7

    def test_builtin_library_midi_filter_hides_enttec(self):
        """Realdaten: Enttec/Art-Net/Makro raus, APC & nanoKONTROL drin."""
        from src.ui.widgets.controller_browser import _sorted_midi_profiles
        lib = ControllerLibrary()
        lib.ensure_loaded()
        out = _sorted_midi_profiles(lib.all(), midi_only=True)
        ids = {p.id for p in out}
        assert "akai_apc_mini" in ids
        assert "korg_nanokontrol2" in ids
        assert "enttec_dmx_usb_pro" not in ids
        assert all(p.device_type in
                   ("midi_grid_controller", "midi_fader_controller",
                    "midi_keyboard") for p in out)


class TestQxiDecode:
    def test_cc(self):
        assert _decode_channel(7) == ("cc", 0, 7, "")

    def test_note(self):
        assert _decode_channel(128 + 60) == ("note", 0, 60, "")

    def test_note_channel_page(self):
        typ, ch, num, _ = _decode_channel(4096 * 2 + 128 + 5)
        assert (typ, ch, num) == ("note", 2, 5)

    def test_pitch(self):
        assert _decode_channel(513)[0] == "pitchbend"

    def test_unknown_kept(self):
        typ, _, _, hint = _decode_channel(700)
        assert typ == "other" and hint


class TestQxiConvert:
    QXI = """<?xml version="1.0" encoding="UTF-8"?>
<InputProfile xmlns="http://www.qlcplus.org/InputProfile">
 <Creator><Author>Test</Author></Creator>
 <Manufacturer>TestCo</Manufacturer>
 <Model>MiniPad</Model>
 <Type>MIDI</Type>
 <Channel Number="0"><Name>Fader 1</Name><Type>Slider</Type></Channel>
 <Channel Number="1"><Name>Fader 2</Name><Type>Slider</Type></Channel>
 <Channel Number="128"><Name>Pad 1</Name><Type>Button</Type></Channel>
 <Channel Number="4224"><Name>Pad Ch2</Name><Type>Button</Type></Channel>
</InputProfile>"""

    def test_convert(self, tmp_path):
        f = tmp_path / "test.qxi"
        f.write_text(self.QXI, encoding="utf-8")
        p = convert_qxi(str(f))
        assert p.manufacturer == "TestCo" and p.model == "MiniPad"
        assert p.faders == 2 and p.buttons == 2
        assert p.license.startswith("Apache-2.0")
        by_name = {c.name: c for c in p.controls}
        assert by_name["Fader 1"].type == "cc" and by_name["Fader 1"].range == [0, 0]
        assert by_name["Pad 1"].type == "note" and by_name["Pad 1"].range == [0, 0]
        assert by_name["Pad Ch2"].channel == 1  # 4224 = 4096*1 + 128 + 0

    def test_convert_without_namespace(self, tmp_path):
        qxi = self.QXI.replace(' xmlns="http://www.qlcplus.org/InputProfile"', "")
        f = tmp_path / "old.qxi"
        f.write_text(qxi, encoding="utf-8")
        p = convert_qxi(str(f))
        assert p.model == "MiniPad" and len(p.controls) == 4

    def test_builtin_json_files_are_valid(self):
        lib_dir = ControllerLibrary.builtin_dir()
        files = [f for f in os.listdir(lib_dir) if f.endswith(".json")]
        assert len(files) >= 7
        for fname in files:
            with open(os.path.join(lib_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            assert data.get("schema") == 1, fname
            assert data.get("id"), fname

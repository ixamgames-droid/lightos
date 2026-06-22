"""Welle 3 / Cluster M: Snap-Editor + SnapLibrary-Mutations-API.

Nicht-Matrix-Snaps bekommen ein Bearbeiten-Overlay (Liste der programmierten
Kanaele). Werte aendern/entfernen laeuft ueber neue SnapLibrary-Setter, geklemmt.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.snap_library import get_snap_library, SnapLibrary


def _app():
    return QApplication.instance() or QApplication([])


def test_library_mutation_api():
    lib = SnapLibrary()
    snap = lib.add_snap("S1", "", {1: {"intensity": 255, "color_r": 128}, 2: {"dimmer": 100}})
    assert lib.set_snap_value(snap.id, 1, "intensity", 200)
    assert snap.values[1]["intensity"] == 200
    lib.set_snap_value(snap.id, 1, "color_r", 999)      # klemmt auf 255
    assert snap.values[1]["color_r"] == 255
    assert lib.remove_snap_attr(snap.id, 2, "dimmer")
    assert 2 not in snap.values                          # leeres Gerät entfernt
    assert lib.remove_snap_attr(snap.id, 2, "dimmer") is False   # schon weg
    lib.set_snap_values(snap.id, {3: {"intensity": 300}})        # normalisiert+klemmt
    assert snap.values == {3: {"intensity": 255}}
    assert lib.set_snap_value(99999, 1, "x", 1) is False         # unbekannter Snap


def test_snap_editor_loads_edits_removes():
    _app()
    from src.ui.views.snap_editor import SnapEditor
    lib = get_snap_library()
    snap = lib.add_snap("S2", "", {1: {"intensity": 255, "color_r": 128}, 2: {"dimmer": 100}})
    ed = SnapEditor(snap)
    assert ed.total_rows() == 3           # 3 programmierte Kanäle (1:2 + 2:1)
    ed._on_value(1, "intensity", 77)
    assert lib.get(snap.id).values[1]["intensity"] == 77
    ed._remove(2, "dimmer")
    assert 2 not in lib.get(snap.id).values
    assert ed.total_rows() == 2           # neu geladen ohne die entfernte Zeile


# ── Snap nachträglich erweitern (David 2026-06-22) ─────────────────────────────
# Geräte/Kanäle nach dem Speichern hinzufügen (nach Typ gruppiert, kompatibel
# gefiltert, Werte vom gleichen Typ übernommen) + Kanal-Drilldown beim Speichern.

from PySide6.QtCore import Qt

from src.ui.views import snap_editor as SE
from src.ui.views.snap_file_panel import ChannelSelectDialog
from src.core.attr_groups import attr_label


class _Ch:
    """Minimaler FixtureChannel-Stand-in."""
    def __init__(self, attribute):
        self.attribute = attribute


def test_base_attr_strips_head_and_lowercases():
    assert SE.base_attr("color_r#1") == "color_r"
    assert SE.base_attr("PAN") == "pan"
    assert SE.base_attr("") == ""


def test_fixture_caps_ignores_raw_and_empty():
    assert SE.fixture_caps([_Ch("color_r"), _Ch("raw"), _Ch(""), _Ch("PAN")]) \
        == {"color_r", "pan"}


def test_fixture_channel_keys_multihead_suffixes():
    chans = [_Ch("tilt"), _Ch("color_r"), _Ch("color_g"), _Ch("color_r"),
             _Ch("tilt"), _Ch("raw"), _Ch("")]
    assert SE.fixture_channel_keys(chans) == \
        ["tilt", "color_r", "color_g", "color_r#1", "tilt#1"]


def test_snap_controlled_attrs_and_groups():
    values = {1: {"color_r": 255, "dimmer": 100}, 2: {"pan": 10, "tilt": 20}}
    assert SE.snap_controlled_attrs(values) == {"color_r", "dimmer", "pan", "tilt"}
    assert SE.snap_controlled_groups(values) == {"Color", "Intensity", "Position"}


def test_is_compatible_movement_excludes_par():
    par = {"color_r", "color_g", "color_b", "dimmer", "shutter"}
    mover = {"color_r", "color_g", "color_b", "dimmer", "pan", "tilt"}
    groups = {"Color", "Position"}
    assert not SE.is_compatible(par, groups)
    assert SE.is_compatible(mover, groups)


def test_is_compatible_color_snap_includes_par():
    par = {"color_r", "color_g", "color_b", "dimmer", "shutter"}
    assert SE.is_compatible(par, {"Color"})
    assert SE.is_compatible(par, {"Color", "Intensity"})


def test_is_compatible_empty_snap_accepts_all():
    assert SE.is_compatible({"dimmer"}, set())


def test_values_for_new_device_copies_template_only_supported():
    template = {"color_r": 255, "color_g": 128, "color_w": 10, "pan": 50}
    caps = {"color_r", "color_g", "color_w"}        # kein pan
    out = SE.values_for_new_device(template, caps,
                                   {"color_r", "color_g", "color_w", "pan"})
    assert out == {"color_r": 255, "color_g": 128, "color_w": 10}


def test_values_for_new_device_fallback_zero_for_supported_controlled():
    caps = {"color_r", "color_g", "dimmer"}
    out = SE.values_for_new_device(None, caps, {"color_r", "color_g", "color_b"})
    assert out == {"color_r": 0, "color_g": 0}


def test_addable_channels_missing_only_sorted():
    type_caps = {"color_r", "color_g", "color_b", "color_w", "dimmer", "shutter"}
    present_on_all = {"color_r", "color_g", "color_b", "dimmer"}
    assert SE.addable_channels(type_caps, present_on_all) == ["color_w", "shutter"]


def test_fixture_type_key_and_label():
    class FX:
        fixture_profile_id = 7
        mode_name = "8ch"
        channel_count = 8
        manufacturer_name = "Acme"
        fixture_name = "PAR"
        label = "PAR 1"
    fx = FX()
    assert SE.fixture_type_key(fx) == (7, "8ch", 8)
    assert SE.fixture_type_label(fx) == "Acme PAR · 8ch"


def test_attr_label_friendly_and_multihead():
    assert attr_label("color_r") == "Rot"
    assert attr_label("color_r#1") == "Rot (Kopf 2)"
    assert attr_label("shutter") == "Shutter"
    assert attr_label("unknown_x") == "unknown_x"


def test_dialog_uncheck_single_channel_within_group():
    _app()
    prog = {1: {"dimmer": 200, "shutter": 255}}   # beide Intensity
    dlg = ChannelSelectDialog(prog)
    dlg._attr_checks["shutter"].setChecked(False)
    assert dlg.filter_programmer(prog) == {1: {"dimmer": 200}}


def test_dialog_rgb_subset_without_white():
    _app()
    prog = {1: {"color_r": 255, "color_g": 128, "color_b": 64, "color_w": 10}}
    dlg = ChannelSelectDialog(prog)
    dlg._attr_checks["color_w"].setChecked(False)
    assert dlg.filter_programmer(prog) \
        == {1: {"color_r": 255, "color_g": 128, "color_b": 64}}


def test_dialog_group_uncheck_overrides_channel():
    _app()
    prog = {1: {"dimmer": 200, "shutter": 255}}
    dlg = ChannelSelectDialog(prog)
    dlg._checks["Intensity"].setChecked(False)
    assert dlg.filter_programmer(prog) == {}


def test_dialog_default_keeps_everything():
    _app()
    prog = {1: {"color_r": 255, "dimmer": 100}, 2: {"pan": 5}}
    dlg = ChannelSelectDialog(prog)
    assert dlg.filter_programmer(prog) == prog


def test_add_device_dialog_returns_checked_fids():
    _app()
    cand = [("Acme PAR · 8ch", [(1, "PAR 1", ""), (2, "PAR 2", "")])]
    dlg = SE._AddDeviceDialog(cand)
    item, fid = dlg._fid_items[0]
    item.setCheckState(0, Qt.CheckState.Checked)
    assert dlg.selected_fids() == [1]


def test_add_channel_dialog_returns_attrs_and_value():
    _app()
    dlg = SE._AddChannelDialog("Acme PAR", ["color_w", "shutter"], 3)
    dlg._checks["shutter"].setChecked(True)
    dlg._value.setValue(255)
    assert dlg.selected_attrs() == ["shutter"]
    assert dlg.value() == 255


# ── Integration gegen die echte Fixture-DB ─────────────────────────────────────
# Treibt _add_device/_add_channel mit echten gepatchten Geräten (get_channels_for_
# patched) über Fake-Dialoge — prüft Kompatibilitäts-Filter + Werte-Übernahme real.

import unittest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as _fdb_engine
from src.core.database.models import PatchedFixture, FixtureProfile
from src.core.show.show_file import reset_show
from src.core.engine.snap_library import get_snap_library
from src.ui.views.snap_editor import SnapEditor
from PySide6.QtWidgets import QDialog
import src.ui.views.snap_editor as _SEmod


def _pid(short: str) -> int:
    with Session(_fdb_engine()) as s:
        return int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == short)).scalar_one())


class _FakeAddDevice:
    captured = None
    chosen: list = []

    def __init__(self, candidates_by_type, parent=None):
        type(self).captured = candidates_by_type

    def exec(self):
        return QDialog.DialogCode.Accepted

    def selected_fids(self):
        return list(type(self).chosen)

    @classmethod
    def offered_fids(cls):
        return {fid for _label, devs in (cls.captured or []) for fid, _, _ in devs}


class _FakeAddChannel:
    addable_seen: list = []
    attrs: list = []
    val = 0

    def __init__(self, type_label, addable, n_devices, parent=None):
        type(self).addable_seen = list(addable)

    def exec(self):
        return QDialog.DialogCode.Accepted

    def selected_attrs(self):
        return list(type(self).attrs)

    def value(self):
        return type(self).val


class SnapEditorRealFixtureTest(unittest.TestCase):

    def setUp(self):
        _app()
        reset_show()
        self.state = get_state()
        par, mh = _pid("ZQ01424"), _pid("SPIDER14")
        self.state.add_fixture(PatchedFixture(
            fid=1, label="PAR 1", fixture_profile_id=par, mode_name="8-Kanal RGBW",
            universe=1, address=1, channel_count=8, manufacturer_name="Generic",
            fixture_name="Stage Light ZQ01424", fixture_type="par"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=2, label="PAR 2", fixture_profile_id=par, mode_name="8-Kanal RGBW",
            universe=1, address=20, channel_count=8, manufacturer_name="Generic",
            fixture_name="Stage Light ZQ01424", fixture_type="par"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=3, label="MH 1", fixture_profile_id=mh, mode_name="14-Kanal",
            universe=1, address=40, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.state.add_fixture(PatchedFixture(
            fid=4, label="MH 2", fixture_profile_id=mh, mode_name="14-Kanal",
            universe=1, address=60, channel_count=14, manufacturer_name="U King",
            fixture_name="Spider 14ch", fixture_type="moving_head"), undoable=False)
        self.lib = get_snap_library()
        self._orig_add_dev = _SEmod._AddDeviceDialog
        self._orig_add_chan = _SEmod._AddChannelDialog

    def tearDown(self):
        _SEmod._AddDeviceDialog = self._orig_add_dev
        _SEmod._AddChannelDialog = self._orig_add_chan
        reset_show()

    def test_color_snap_offers_par_and_mh_and_copies_values(self):
        snap = self.lib.add_snap("C", "", {1: {"color_r": 255, "color_g": 100, "color_b": 50}})
        ed = SnapEditor(snap)
        _FakeAddDevice.chosen = [2]
        _SEmod._AddDeviceDialog = _FakeAddDevice
        ed._add_device()
        # Farb-Snap: PAR2 (fid2) und beide MH (3,4) sind kompatibel, fid1 ist drin.
        self.assertEqual(_FakeAddDevice.offered_fids(), {2, 3, 4})
        # PAR2 hat die RGB-Werte von PAR1 übernommen (W war nicht im Vorbild).
        self.assertEqual(snap.values[2], {"color_r": 255, "color_g": 100, "color_b": 50})

    def test_movement_snap_excludes_par(self):
        # Spider hat Tilt (Position-Gruppe), aber KEIN Pan -> Tilt für realistische Daten.
        snap = self.lib.add_snap("M", "", {3: {"tilt": 64, "color_r": 255}})
        ed = SnapEditor(snap)
        _FakeAddDevice.chosen = [4]
        _SEmod._AddDeviceDialog = _FakeAddDevice
        ed._add_device()
        # Bewegungs-Snap (Position+Color): nur der andere Mover ist kompatibel, keine PARs.
        self.assertEqual(_FakeAddDevice.offered_fids(), {4})
        self.assertEqual(snap.values[4], {"tilt": 64, "color_r": 255})

    def test_add_channel_fills_missing_on_all_of_type(self):
        snap = self.lib.add_snap("K", "", {1: {"color_r": 255}, 2: {"color_r": 200}})
        ed = SnapEditor(snap)
        tkey = _SEmod.fixture_type_key(self.state.get_patched_fixtures()[0])
        _SEmod._AddChannelDialog = _FakeAddChannel
        _FakeAddChannel.val = 180
        # Erst sehen, was nachtragbar ist, dann den ersten Kandidaten wählen.
        captured = {}

        class _Cap(_FakeAddChannel):
            def __init__(self, type_label, addable, n_devices, parent=None):
                captured["addable"] = list(addable)
                _FakeAddChannel.attrs = [addable[0]] if addable else []
                super().__init__(type_label, addable, n_devices, parent)
        _SEmod._AddChannelDialog = _Cap
        ed._add_channel(tkey, [1, 2])
        added = captured["addable"][0]
        self.assertIn("color_w", captured["addable"])     # RGBW-Profil bietet Weiß an
        self.assertEqual(snap.values[1][added], 180)
        self.assertEqual(snap.values[2][added], 180)
        self.assertEqual(snap.values[1]["color_r"], 255)  # Bestand bleibt erhalten

    def test_add_channel_offers_second_head_of_spider(self):
        # Spider hat color_r DOPPELT (Bank 1/2). Snap hat nur Kopf 0 (color_r) ->
        # color_r#1 (zweiter Bank) muss nachtragbar sein.
        snap = self.lib.add_snap("S", "", {3: {"color_r": 255}})
        ed = SnapEditor(snap)
        tkey = _SEmod.fixture_type_key(
            [f for f in self.state.get_patched_fixtures() if f.fid == 3][0])
        captured = {}

        class _Cap(_FakeAddChannel):
            def __init__(self, type_label, addable, n_devices, parent=None):
                captured["addable"] = list(addable)
                _FakeAddChannel.attrs = ["color_r#1"] if "color_r#1" in addable else []
                super().__init__(type_label, addable, n_devices, parent)
        _SEmod._AddChannelDialog = _Cap
        _FakeAddChannel.val = 120
        ed._add_channel(tkey, [3])
        self.assertIn("color_r#1", captured["addable"])     # zweiter Kopf angeboten
        self.assertEqual(snap.values[3]["color_r#1"], 120)
        self.assertEqual(snap.values[3]["color_r"], 255)    # Bestand erhalten

    def test_resolve_multihead_distinct_dmx(self):
        # color_r und color_r#1 müssen auf VERSCHIEDENE Kanäle/DMX auflösen.
        snap = self.lib.add_snap("R", "", {3: {"color_r": 255, "color_r#1": 100}})
        ed = SnapEditor(snap)
        fx = [f for f in self.state.get_patched_fixtures() if f.fid == 3][0]
        _, _, dmx0 = ed._resolve(fx, "color_r")
        _, _, dmx1 = ed._resolve(fx, "color_r#1")
        self.assertIsNotNone(dmx0)
        self.assertIsNotNone(dmx1)
        self.assertNotEqual(dmx0, dmx1)
        self.assertGreater(dmx1, dmx0)   # Bank 2 liegt hinter Bank 1


if __name__ == "__main__":
    unittest.main()

"""LAS-03-Rest: Laser-Muster über Snaps/Szenen abrufbar — Verifikations-Pins.

Die Verdrahtung existiert seit LAS-01 implizit (laser_* in ATTR_GROUPS →
Snap-Save-Dialog; resolve_attr_channels → Szenen). Diese Tests nageln den
End-to-End-Vertrag fest, damit ihn niemand still bricht:

1. classify_attr sortiert Laser-Attribute (inkl. ``attr#N``-Kopf-Keys) in
   Gruppen ein → der Snap-Save-Dialog bietet sie an.
2. ChannelSelectDialog.filter_programmer übernimmt Laser-Werte (inkl. Kopf-
   Keys) und respektiert Gruppen-Abwahl.
3. SnapLibrary persistiert Kopf-Keys roh (to_dict/from_dict) — der Apply-Pfad
   schreibt sie 1:1 zurück (Programmer-Key-Konvention).
4. programmer_to_scene_values löst Laser-Attribute vorkommens-bewusst auf die
   richtigen Kanal-Nummern auf (Gruppe A/B des L2600).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.attr_groups import classify_attr


def _app():
    return QApplication.instance() or QApplication([])


# Ein realistischer Laser-Programmer-Stand (L2600, Gruppe A + B).
_LASER_PROG = {
    7: {"shutter": 255, "laser_bank": 32, "gobo_wheel": 42,
        "gobo_wheel#1": 77, "laser_x": 64, "laser_color_change": 16},
}


# ---------------------------------------------------- 1) Klassifikation -----

def test_laser_attrs_have_snap_groups():
    # Pin: Laser-Attribute liegen in bekannten Gruppen (Snap-Dialog bietet sie
    # an); Kopf-Keys klassifizieren wie ihr Basis-Attribut.
    assert classify_attr("laser_x") == "Effect"
    assert classify_attr("laser_bank") == "Effect"
    assert classify_attr("laser_draw_mode") == "Effect"
    assert classify_attr("gobo_wheel") == "Gobo"
    assert classify_attr("shutter") == "Intensity"
    assert classify_attr("gobo_wheel#1") == classify_attr("gobo_wheel")
    assert classify_attr("laser_x#1") == classify_attr("laser_x")


# ---------------------------------------------------- 2) Snap-Save-Dialog ---

def test_snap_dialog_captures_laser_attrs():
    _app()
    from src.ui.views.snap_file_panel import ChannelSelectDialog
    dlg = ChannelSelectDialog(_LASER_PROG)
    out = dlg.filter_programmer(_LASER_PROG)
    # Default: alles angehakt -> ALLE Laser-Werte inkl. Kopf-Key ueberleben.
    assert out == _LASER_PROG


def test_snap_dialog_group_deselect_drops_laser_effects():
    _app()
    from src.ui.views.snap_file_panel import ChannelSelectDialog
    dlg = ChannelSelectDialog(_LASER_PROG)
    assert "Effect" in dlg._checks          # Gruppe wird angeboten
    dlg._checks["Effect"].setChecked(False)
    out = dlg.filter_programmer(_LASER_PROG)
    kept = set(out.get(7, {}))
    # Effect-Attribute weg, Gobo/Intensity bleiben (inkl. Kopf-Key).
    assert "laser_bank" not in kept and "laser_x" not in kept
    assert "laser_color_change" not in kept
    assert {"shutter", "gobo_wheel", "gobo_wheel#1"} <= kept


# ---------------------------------------------------- 3) Snap-Persistenz ----

def test_snap_library_roundtrips_head_keys():
    from src.core.engine.snap_library import SnapLibrary
    lib = SnapLibrary()
    snap = lib.add_snap("Laser Kreis", "", dict(_LASER_PROG))
    data = lib.to_dict()
    lib2 = SnapLibrary()
    lib2.from_dict(data)
    back = lib2.get(snap.id)
    assert back is not None
    # Kopf-Keys ueberleben roh — der Apply-Pfad (snap_file_panel._apply_snap)
    # schreibt sie 1:1 als Programmer-Keys zurueck (gleiche Konvention).
    assert back.values[7]["gobo_wheel#1"] == 77
    assert back.values[7]["laser_bank"] == 32


# ---------------------------------------------------- 4) Szenen-Bruecke -----

class _Rng:
    def __init__(self, lo, hi, name):
        self.range_from, self.range_to, self.name = lo, hi, name


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.ranges = []
        self.name = attr


class _FX:
    def __init__(self, fid, chans):
        self.fid = fid
        self._chans = chans


def test_scene_conversion_resolves_laser_heads(monkeypatch):
    _app()
    import src.ui.views.programmer_view as pv
    # L2600-Kurzform: gobo_wheel als Ch3 (Kopf 0) und Ch6 (Kopf 1).
    fx = _FX(7, [_Ch("shutter", 1), _Ch("laser_bank", 2), _Ch("gobo_wheel", 3),
                 _Ch("laser_x", 4), _Ch("shutter", 5), _Ch("gobo_wheel", 6)])
    monkeypatch.setattr(pv, "get_channels_for_patched", lambda f: f._chans)
    vals = pv.programmer_to_scene_values(
        {7: {"gobo_wheel": 42, "gobo_wheel#1": 77, "laser_bank": 32}}, [fx])
    as_map = {(fid, ch): v for fid, ch, v in vals}
    assert as_map[(7, 3)] == 42     # Kopf 0 -> 1. Vorkommen (Ch3)
    assert as_map[(7, 6)] == 77     # Kopf 1 -> 2. Vorkommen (Ch6)
    assert as_map[(7, 2)] == 32     # laser_bank -> Ch2
    assert len(vals) == 3

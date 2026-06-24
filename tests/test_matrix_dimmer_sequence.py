"""ENG-08 — Dimmerwert-Sequenz fuer den Dimmer-Chase.

Prueft das Pendant zur ColorSequence:
- ``DimmerSequence``-Datenmodell (add/remove/toggle/set_level/move/enabled_levels/
  selected/next/prev/to_list/from_list, Klemmen 0..255).
- Render: ein Dimmer-Chase mit ``dimmer_cycle`` schaltet pro Runde durch die
  expliziten Stufen (statt fester Min/Max-Bereich).
- ``_dimmer_output`` reicht die Stufen im Cycle-Modus DIREKT durch (kein
  Min/Max-Remap), bleibt sonst beim bisherigen Verhalten.
- Serialisierung (to_dict/apply_dict) inkl. Default fuer Alt-Shows ohne Key.
- View-Integration: Checkbox + Editor in der Farben-Gruppe (analog UI-12).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.rgb_matrix import (RgbMatrixInstance, RgbAlgorithm,
                                         MatrixStyle, DimmerSequence)


# ── Datenmodell ───────────────────────────────────────────────────────────────

def test_dimmer_sequence_basics():
    ds = DimmerSequence([255, 50, 100])
    assert len(ds) == 3
    assert ds.all_levels() == [255, 50, 100]
    assert ds.enabled_levels() == [255, 50, 100]
    assert ds.selected() == 255          # active_index 0
    assert ds.next() == 1 and ds.selected() == 50
    assert ds.prev() == 0 and ds.selected() == 255


def test_dimmer_sequence_clamp_and_edit():
    ds = DimmerSequence([10])
    ds.set_level(0, 999)
    assert ds.level_at(0) == 255         # geklemmt auf 255
    ds.add(-5)
    assert ds.level_at(1) == 0           # geklemmt auf 0
    ds.add(128)
    assert ds.all_levels() == [255, 0, 128]
    ds.move(0, 2)
    assert ds.all_levels() == [0, 128, 255]


def test_dimmer_sequence_toggle_skips_inactive():
    ds = DimmerSequence([255, 50, 100])
    ds.toggle(1)                          # 50 deaktivieren
    assert ds.enabled_levels() == [255, 100]
    ds.set_enabled(1, True)
    assert ds.enabled_levels() == [255, 50, 100]


def test_dimmer_sequence_enabled_fallback():
    ds = DimmerSequence([200])
    ds.toggle(0)                          # alle aus -> Fallback erste Stufe
    assert ds.enabled_levels() == [200]
    assert DimmerSequence([]).enabled_levels() == [255]


def test_dimmer_sequence_remove_keeps_active_valid():
    ds = DimmerSequence([10, 20, 30])
    ds.active_index = 2
    ds.remove(2)
    assert ds.active_index == 1
    assert ds.all_levels() == [10, 20]


def test_dimmer_sequence_roundtrip():
    ds = DimmerSequence([255, 50, 100])
    ds.toggle(1)
    data = ds.to_list()
    assert data == [{"level": 255, "on": True},
                    {"level": 50, "on": False},
                    {"level": 100, "on": True}]
    assert DimmerSequence.from_list(data).to_list() == data


# ── Render: pro Runde explizite Stufe ─────────────────────────────────────────

def _dimmer_chase(levels, **params):
    m = RgbMatrixInstance(cols=4, rows=1)
    m.algorithm = RgbAlgorithm.CHASE
    m.style = MatrixStyle.DIMMER
    m.dimmer_levels = DimmerSequence(levels)
    m.params.update(dict(dimmer_cycle=True, axis="H", movement="normal",
                         runner_width=1, after_fade=0.0))
    m.params.update(params)
    return m


def _peak(m, p):
    return max(max(px) for px in m._render(p))


def test_dimmer_cycle_advances_per_round():
    """length_hint=4 (4 Spalten, Achse H) -> rnd = int(p)//4 wechselt die Stufe."""
    m = _dimmer_chase([255, 50, 100])
    assert _peak(m, 0.0) == 255
    assert _peak(m, 4.0) == 50
    assert _peak(m, 8.0) == 100
    assert _peak(m, 12.0) == 255          # wrap


def test_dimmer_interval_slows_cycling():
    """dimmer_interval=2 -> Stufe wechselt erst alle 2 Durchlaeufe."""
    m = _dimmer_chase([255, 50], dimmer_interval=2)
    assert _peak(m, 0.0) == 255
    assert _peak(m, 4.0) == 255           # noch dieselbe Stufe
    assert _peak(m, 8.0) == 50            # erst nach 2 Runden gewechselt


def test_dimmer_cycle_skips_inactive_levels():
    m = _dimmer_chase([255, 50, 100])
    m.dimmer_levels.toggle(1)             # 50 aus -> nur [255, 100]
    assert _peak(m, 0.0) == 255
    assert _peak(m, 4.0) == 100
    assert _peak(m, 8.0) == 255


# ── _dimmer_output: Cycle = direkt, sonst Min/Max-Remap ───────────────────────

def test_dimmer_output_passthrough_in_cycle_mode():
    m = _dimmer_chase([255])
    m.intensity_min, m.intensity_max = 0, 100   # darf im Cycle-Modus NICHT skalieren
    assert m._dimmer_output((255, 255, 255)) == 255
    assert m._dimmer_output((50, 50, 50)) == 50


def test_dimmer_output_uses_range_without_cycle():
    m = _dimmer_chase([255])
    m.params["dimmer_cycle"] = False
    m.intensity_min, m.intensity_max = 0, 100
    assert m._dimmer_output((255, 255, 255)) == 100   # auf max gemappt
    assert m._dimmer_output((0, 0, 0)) == 0


# ── Serialisierung ────────────────────────────────────────────────────────────

def test_instance_serialization_roundtrip():
    m = RgbMatrixInstance(cols=4, rows=1)
    m.dimmer_levels = DimmerSequence([255, 50, 100])
    m.dimmer_levels.toggle(2)
    m.dimmer_levels.active_index = 1
    d = m.to_dict()
    assert d["dimmer_sequence"] == [{"level": 255, "on": True},
                                    {"level": 50, "on": True},
                                    {"level": 100, "on": False}]
    assert d["dimmer_active"] == 1
    m2 = RgbMatrixInstance.from_dict(d)
    assert m2.dimmer_levels.to_list() == d["dimmer_sequence"]
    assert m2.dimmer_levels.active_index == 1


def test_old_show_without_key_gets_default():
    """Alt-Shows ohne dimmer_sequence-Key bekommen den Standard (kein Crash)."""
    m = RgbMatrixInstance(cols=4, rows=1)
    m.apply_dict({"algorithm": "Chase", "style": "Dimmer"})  # kein dimmer_sequence
    assert len(m.dimmer_levels) >= 1
    assert m.dimmer_levels.all_levels() == [255, 128, 64]


def test_set_param_dimmer_sequence():
    m = RgbMatrixInstance(cols=4, rows=1)
    assert m.set_param("dimmer_sequence", [{"level": 200, "on": True},
                                           {"level": 10, "on": False}])
    assert m.dimmer_levels.to_list() == [{"level": 200, "on": True},
                                         {"level": 10, "on": False}]
    assert m.get_param("dimmer_sequence") is m.dimmer_levels

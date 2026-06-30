"""#5: Param-Key-Disambiguierung gegen Bleed beim Algorithmus-Wechsel.

Frueher teilten sich mehrere Algorithmen denselben params-Key mit
unterschiedlicher Bedeutung -> ein Wert blutete beim Algo-Wechsel durch:
  - runner_count : CHASE „Läufer" vs PINWHEEL „Segmente"
  - spread       : WAVE „Breite" vs RAINBOW „Farbzyklen"
  - movement     : CHASE/WIPE (normal/bounce…) vs RAINBOW (linear/radial…)
  - hold         : FILL „Halte-Schritte" (0..20) vs COLORFADE „Anteil" (0..0.95)
  - fade         : RADAR/RAIN „Schweif" vs FILL „Fade pro Fixture"

Jetzt hat jeder dieser Faelle einen EIGENEN Key. Die Renderer lesen den neuen
Key mit Fallback auf den alten (Alt-Shows / direkte VC-params), und apply_dict
migriert den alten Key beim Laden auf den neuen.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.engine.rgb_matrix_meta import ALGO_META


def _keys(algo):
    return {s.key for s in ALGO_META[algo].params}


# ── 1) Meta: jeder Algorithmus exponiert SEINEN eigenen Key (nicht den alten) ──

def test_meta_keys_are_disambiguated():
    assert "segment_count" in _keys(RgbAlgorithm.PINWHEEL)
    assert "runner_count" not in _keys(RgbAlgorithm.PINWHEEL)

    rk = _keys(RgbAlgorithm.RAINBOW)
    assert {"hue_spread", "rainbow_movement"} <= rk
    assert "spread" not in rk and "movement" not in rk

    assert "crossfade_hold" in _keys(RgbAlgorithm.COLORFADE)
    assert "hold" not in _keys(RgbAlgorithm.COLORFADE)

    fk = _keys(RgbAlgorithm.FILL)
    assert "fixture_fade" in fk
    assert "fade" not in fk
    # FILL behaelt seinen eigenen „hold" (Halte-Schritte) — NICHT umbenannt.
    assert "hold" in fk

    # Gegenprobe: die alten Eigentuemer behalten ihren Key.
    assert "runner_count" in _keys(RgbAlgorithm.CHASE)
    assert "spread" in _keys(RgbAlgorithm.WAVE)
    assert "movement" in _keys(RgbAlgorithm.CHASE)
    assert "fade" in _keys(RgbAlgorithm.RADAR)


# ── 2) apply_dict migriert den alten Key beim Laden auf den neuen ──────────────

def _roundtrip(algo, old_params):
    src = RgbMatrixInstance(name="s", cols=4, rows=2, algorithm=algo)
    d = src.to_dict()
    d["params"] = dict(old_params)
    dst = RgbMatrixInstance(name="d", cols=4, rows=2)
    dst.apply_dict(d)
    return dst


def test_apply_dict_migrates_old_keys():
    m = _roundtrip(RgbAlgorithm.PINWHEEL, {"runner_count": 5})
    assert m.params.get("segment_count") == 5
    assert "runner_count" not in m.params

    m = _roundtrip(RgbAlgorithm.RAINBOW, {"spread": 4.0, "movement": "radial"})
    assert m.params.get("hue_spread") == 4.0
    assert m.params.get("rainbow_movement") == "radial"
    assert "spread" not in m.params and "movement" not in m.params

    m = _roundtrip(RgbAlgorithm.COLORFADE, {"hold": 0.5})
    assert m.params.get("crossfade_hold") == 0.5
    assert "hold" not in m.params

    m = _roundtrip(RgbAlgorithm.FILL, {"fade": 0.8, "hold": 3.0})
    assert m.params.get("fixture_fade") == 0.8
    assert "fade" not in m.params
    assert m.params.get("hold") == 3.0   # FILL-hold bleibt unangetastet


def test_apply_dict_keeps_new_key_when_present():
    # Neuer Key vorhanden -> alter wird NICHT drueberkopiert.
    m = _roundtrip(RgbAlgorithm.PINWHEEL,
                   {"segment_count": 7, "runner_count": 2})
    assert m.params.get("segment_count") == 7


# ── 3) Engine-Fallback: alter Key direkt in params (ohne apply_dict) rendert ──
#     identisch zum neuen Key (Back-compat fuer direkt gesetzte VC-/API-params).

def _render(algo, params, p=3.0):
    m = RgbMatrixInstance(name="t", cols=6, rows=4, algorithm=algo)
    m.params.update(params)
    return m._render(p)


def test_engine_reads_old_key_via_fallback():
    for algo, old, new in [
        (RgbAlgorithm.PINWHEEL, {"runner_count": 4}, {"segment_count": 4}),
        (RgbAlgorithm.RAINBOW, {"spread": 3.0}, {"hue_spread": 3.0}),
        (RgbAlgorithm.RAINBOW, {"movement": "radial"}, {"rainbow_movement": "radial"}),
        (RgbAlgorithm.COLORFADE, {"hold": 0.5}, {"crossfade_hold": 0.5}),
        (RgbAlgorithm.FILL, {"fade": 0.9}, {"fixture_fade": 0.9}),
    ]:
        assert _render(algo, old) == _render(algo, new), f"Fallback != neu fuer {algo} {old}"


def test_new_key_actually_changes_render():
    # Sanity: der Wert wirkt ueberhaupt (sonst waere die Gleichheit oben trivial).
    base = _render(RgbAlgorithm.PINWHEEL, {"segment_count": 1})
    many = _render(RgbAlgorithm.PINWHEEL, {"segment_count": 6})
    assert base != many


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))

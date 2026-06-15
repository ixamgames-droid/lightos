"""Tests für EFX-Custom-Paths (efx_path.py) und die EFX-Live-API.

Abdeckung:
- EfxPath: Sampling (linear/spline, offen/geschlossen), Bogenlängen-Konstanz
- EfxPathLibrary: add/replace/remove, eindeutige Namen, Serialisierung
- EfxInstance: Custom-Path-_calc, Loop/One-Shot, to_dict/from_dict-Roundtrip,
  eingebettete Pfad-Kopie (Show bleibt ohne Bibliothek abspielbar)
- Live-API: list_params/set_param/do_action + effect_live-Dispatcher
"""
import math

import pytest

from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance
from src.core.engine.efx_path import EfxPath, EfxPathLibrary, get_efx_path_library


SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]


@pytest.fixture(autouse=True)
def _clean_library():
    lib = get_efx_path_library()
    lib.from_dict({})
    yield
    lib.from_dict({})


# ── EfxPath ───────────────────────────────────────────────────────────────────

class TestEfxPathSampling:
    def test_empty_path_centers(self):
        p = EfxPath("leer")
        assert p.sample(0.0) == (0.5, 0.5)

    def test_single_point(self):
        p = EfxPath("punkt", [(0.3, 0.7)])
        assert p.sample(0.99) == (0.3, 0.7)

    def test_linear_closed_returns_to_start(self):
        p = EfxPath("quadrat", SQUARE, "linear", closed=True)
        x0, y0 = p.sample(0.0)
        x1, y1 = p.sample(1.0)
        assert math.isclose(x0, x1, abs_tol=1e-6)
        assert math.isclose(y0, y1, abs_tol=1e-6)

    def test_linear_open_ends_at_last_point(self):
        p = EfxPath("linie", [(0.0, 0.0), (1.0, 1.0)], "linear", closed=False)
        assert p.sample(0.0) == pytest.approx((0.0, 0.0))
        assert p.sample(1.0) == pytest.approx((1.0, 1.0))
        assert p.sample(0.5) == pytest.approx((0.5, 0.5))

    def test_arc_length_constant_speed(self):
        # Ungleiche Segmentlängen: 0→0.9 (lang), 0.9→1.0 (kurz). Bei
        # Bogenlängen-Parametrisierung liegt t=0.45 bei x=0.45·Gesamtlänge.
        p = EfxPath("ungleich", [(0.0, 0.5), (0.9, 0.5), (1.0, 0.5)],
                    "linear", closed=False)
        x, _ = p.sample(0.45)
        assert x == pytest.approx(0.45, abs=0.01)

    def test_spline_passes_through_control_points(self):
        p = EfxPath("spline", SQUARE, "spline", closed=True)
        x, y = p.sample(0.0)
        assert (x, y) == pytest.approx(SQUARE[0], abs=1e-6)

    def test_spline_differs_from_linear(self):
        lin = EfxPath("a", SQUARE, "linear", closed=True)
        spl = EfxPath("b", SQUARE, "spline", closed=True)
        # Zwischen den Punkten weicht der Spline von der Geraden ab.
        diffs = [abs(lin.sample(t)[1] - spl.sample(t)[1])
                 for t in (0.1, 0.35, 0.6, 0.85)]
        assert max(diffs) > 0.01

    def test_invalidate_after_edit(self):
        p = EfxPath("edit", [(0.0, 0.0), (1.0, 0.0)], "linear", closed=False)
        assert p.sample(1.0) == pytest.approx((1.0, 0.0))
        p.points.append((1.0, 1.0))
        p.invalidate()
        assert p.sample(1.0) == pytest.approx((1.0, 1.0))

    def test_sample_clamps_t(self):
        p = EfxPath("clamp", [(0.0, 0.0), (1.0, 1.0)], "linear", closed=False)
        assert p.sample(-0.5) == pytest.approx((0.0, 0.0))
        assert p.sample(1.5) == pytest.approx((1.0, 1.0))


class TestEfxPathLibrary:
    def test_add_and_find(self):
        lib = EfxPathLibrary()
        p = lib.add(EfxPath("Test", SQUARE))
        assert lib.find(p.id) is p
        assert lib.find_by_name("Test") is p

    def test_same_id_replaces(self):
        lib = EfxPathLibrary()
        p = lib.add(EfxPath("Test", SQUARE))
        p2 = EfxPath("Test geändert", SQUARE, path_id=p.id)
        lib.add(p2)
        assert len(lib.all()) == 1
        assert lib.find(p.id).name == "Test geändert"

    def test_duplicate_name_gets_unique(self):
        lib = EfxPathLibrary()
        lib.add(EfxPath("Pfad", SQUARE))
        p2 = lib.add(EfxPath("Pfad", SQUARE))
        assert p2.name != "Pfad"

    def test_remove(self):
        lib = EfxPathLibrary()
        p = lib.add(EfxPath("Test", SQUARE))
        assert lib.remove(p.id) is True
        assert lib.find(p.id) is None
        assert lib.remove("gibtsnicht") is False

    def test_roundtrip(self):
        lib = EfxPathLibrary()
        lib.add(EfxPath("A", SQUARE, "spline", closed=False))
        data = lib.to_dict()
        lib2 = EfxPathLibrary()
        lib2.from_dict(data)
        p = lib2.find_by_name("A")
        assert p is not None
        assert p.mode == "spline" and p.closed is False
        assert p.points == [(pytest.approx(x), pytest.approx(y)) for x, y in SQUARE]


# ── EfxInstance + Custom Path ─────────────────────────────────────────────────

class TestEfxInstanceCustomPath:
    def test_set_custom_path_switches_algorithm(self):
        e = EfxInstance("Test")
        p = EfxPath("Quadrat", SQUARE)
        e.set_custom_path(p)
        assert e.algorithm == EfxAlgorithm.CUSTOM
        assert e.path_id == p.id
        assert e.path_data is not None

    def test_calc_maps_through_width_height_offset(self):
        e = EfxInstance("Test")
        p = EfxPath("Mitte", [(0.5, 0.5), (1.0, 0.5)], "linear", closed=False)
        e.set_custom_path(p)
        e.width = 100.0
        e.height = 100.0
        e.x_offset = 128.0
        e.y_offset = 128.0
        pan, tilt = e._calc(0.0)  # Punkt (0.5, 0.5) → Zentrum
        assert pan == pytest.approx(128.0)
        assert tilt == pytest.approx(128.0)
        pan, tilt = e._calc(1.0)  # Punkt (1.0, 0.5) → Zentrum + halbe Breite
        assert pan == pytest.approx(178.0)
        assert tilt == pytest.approx(128.0)

    def test_calc_without_path_stays_center(self):
        e = EfxInstance("Test")
        e.algorithm = EfxAlgorithm.CUSTOM
        pan, tilt = e._calc(0.3)
        assert pan == pytest.approx(e.x_offset)
        assert tilt == pytest.approx(e.y_offset)

    def test_embedded_copy_survives_library_removal(self):
        lib = get_efx_path_library()
        p = lib.add(EfxPath("Quadrat", SQUARE))
        e = EfxInstance("Test")
        e.set_custom_path(p)
        d = e.to_dict()
        lib.remove(p.id)
        e2 = EfxInstance.from_dict(d)
        rp = e2._resolve_path()
        assert rp is not None and rp.name == "Quadrat"

    def test_library_edit_wins_over_embedded(self):
        lib = get_efx_path_library()
        p = lib.add(EfxPath("Quadrat", SQUARE))
        e = EfxInstance("Test")
        e.set_custom_path(p)
        # Bibliothekspfad wird ersetzt (gleiche id, andere Punkte)
        lib.add(EfxPath("Quadrat neu", [(0.0, 0.0), (1.0, 1.0)], path_id=p.id))
        rp = e._resolve_path()
        assert rp is not None and rp.name == "Quadrat neu"

    def test_roundtrip_keeps_loop_and_path(self):
        e = EfxInstance("Test")
        e.set_custom_path(EfxPath("Quadrat", SQUARE, "spline", closed=False))
        e.loop = False
        e2 = EfxInstance.from_dict(e.to_dict())
        assert e2.loop is False
        assert e2.algorithm == EfxAlgorithm.CUSTOM
        assert e2.path_data is not None
        assert e2.path_data["mode"] == "spline"


class TestEfxLoopOneShot:
    def _advance_total(self, e, seconds, dt=0.05):
        steps = int(seconds / dt)
        for _ in range(steps):
            e._advance(dt)

    def test_one_shot_forward_clamps_at_end(self):
        e = EfxInstance("Test")
        e.loop = False
        e.speed_hz = 1.0
        e.start()
        self._advance_total(e, 3.0)
        assert e._phase == 1.0
        e.stop()

    def test_one_shot_backward_clamps_at_zero(self):
        e = EfxInstance("Test")
        e.loop = False
        e.direction = "backward"
        e.speed_hz = 1.0
        e.start()
        assert e._phase == 1.0  # Start am Ende
        self._advance_total(e, 3.0)
        assert e._phase == 0.0
        e.stop()

    def test_one_shot_bounce_runs_once_and_holds(self):
        e = EfxInstance("Test")
        e.loop = False
        e.direction = "bounce"
        e.speed_hz = 1.0
        e.start()
        self._advance_total(e, 5.0)
        assert e._phase == 0.0
        assert e._bounce_dir == 0.0  # angehalten
        e.stop()

    def test_loop_keeps_running(self):
        e = EfxInstance("Test")
        e.loop = True
        e.speed_hz = 1.0
        e.start()
        self._advance_total(e, 2.55)
        assert 0.0 < e._phase < 1.0
        e.stop()

    def test_restart_action_resets_phase(self):
        e = EfxInstance("Test")
        e.loop = False
        e.start()
        self._advance_total(e, 3.0)
        assert e._phase == 1.0
        assert e.do_action("restart") is True
        assert e._phase == 0.0
        e.stop()


# ── Live-API (VC/MIDI) ───────────────────────────────────────────────────────

class TestEfxLiveApi:
    def test_list_params_keys(self):
        e = EfxInstance("Test")
        keys = {s.key for s in e.list_params()}
        assert {"speed", "intensity", "size", "spread", "direction",
                "loop", "algorithm"} <= keys

    def test_path_param_listed_when_library_has_paths(self):
        get_efx_path_library().add(EfxPath("Quadrat", SQUARE))
        e = EfxInstance("Test")
        keys = {s.key for s in e.list_params()}
        assert "path" in keys

    def test_set_param_speed_clamped(self):
        e = EfxInstance("Test")
        assert e.set_param("speed", 99.0) is True
        assert e.speed_hz == 10.0

    def test_set_param_size_sets_both(self):
        e = EfxInstance("Test")
        e.set_param("size", 60.0)
        assert e.width == 60.0 and e.height == 60.0

    def test_set_param_path_by_name(self):
        p = get_efx_path_library().add(EfxPath("Quadrat", SQUARE))
        e = EfxInstance("Test")
        assert e.set_param("path", "Quadrat") is True
        assert e.path_id == p.id
        assert e.algorithm == EfxAlgorithm.CUSTOM

    def test_cycle_paths(self):
        lib = get_efx_path_library()
        p1 = lib.add(EfxPath("A", SQUARE))
        p2 = lib.add(EfxPath("B", SQUARE))
        e = EfxInstance("Test")
        assert e.do_action("next_path") is True
        assert e.path_id == p1.id
        assert e.do_action("next_path") is True
        assert e.path_id == p2.id
        assert e.do_action("prev_path") is True
        assert e.path_id == p1.id

    def test_cycle_algorithm(self):
        e = EfxInstance("Test")
        first = e.algorithm
        assert e.do_action("next_algorithm") is True
        assert e.algorithm != first
        assert e.do_action("prev_algorithm") is True
        assert e.algorithm == first

    def test_toggle_actions(self):
        e = EfxInstance("Test")
        assert e.do_action("toggle_loop") and e.loop is False
        assert e.do_action("toggle_mirror") and e.mirror is True
        assert e.do_action("toggle_open_beam") and e.open_beam is True
        assert e.do_action("toggle_bounce") and e.direction == "bounce"
        assert e.do_action("reverse_direction") and e.direction == "backward"

    def test_list_actions_pairs(self):
        e = EfxInstance("Test")
        actions = dict(e.list_actions())
        assert "restart" in actions and "next_path" in actions

    def test_effect_live_dispatcher(self):
        from src.core.engine import effect_live
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        e = EfxInstance("LiveTest")
        fm.add(e)
        try:
            assert effect_live.set_param_normalized("speed", 1.0, function_id=e.id)
            assert e.speed_hz == pytest.approx(10.0)
            assert effect_live.do_action("toggle_loop", function_id=e.id)
            assert e.loop is False
            keys = {s.key for s in effect_live.list_params(function_id=e.id)}
            assert "loop" in keys
            actions = dict(effect_live.list_actions(function_id=e.id))
            assert "restart" in actions
        finally:
            fm.remove(e.id)


# ── Show-Persistenz ──────────────────────────────────────────────────────────

class TestShowPersistence:
    def test_efx_paths_roundtrip_via_dicts(self):
        lib = get_efx_path_library()
        lib.add(EfxPath("ShowPfad", SQUARE, "spline"))
        data = lib.to_dict()
        lib.from_dict({})
        assert lib.find_by_name("ShowPfad") is None
        lib.from_dict(data)
        assert lib.find_by_name("ShowPfad") is not None

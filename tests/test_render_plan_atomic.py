"""STAB-15: Der Patch-Render-Plan muss ATOMAR getauscht werden.

_rebuild_render_plan tauscht mehrere Plan-Felder (_fix_index, _default_frame,
_commit_spans, _patched_set, _laser_estop_addrs) — waehrend der 44-Hz-Render-
Thread (_render_frame) sie liest. Frueher geschah der Tausch feldweise: der
Renderer konnte eine HALB getauschte Kombination sehen (neuer _fix_index +
alte _commit_spans) -> 1-Frame-Glitch/Crash beim Umpatchen.

Diese Tests fahren genau die Rennbedingung: ein Thread ruft _rebuild_render_plan
wiederholt (mit ZWEI unterschiedlichen Patches, damit sich die Plan-Felder real
unterscheiden), waehrend der Haupt-Thread die Plan-Felder liest — einmal als
konsistenter Snapshot (darf nie halb getauscht sein) und einmal ueber den echten
_render_frame (darf nie crashen).
"""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 1

    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _FM:
    """Fake-FunctionManager ohne Nebenwirkung (nur damit _render_frame laeuft)."""
    def tick(self, universes, patch_cache, dt):
        return None


# Zwei klar unterscheidbare Patches: Fixture an Adresse 10 vs. an Adresse 100.
# Der Kanal sitzt jeweils auf channel_number 1 -> Live-Adresse == fx.address.
_FX_A = _Fx(1, 1, 10)
_FX_B = _Fx(2, 1, 100)
_CONFIGS = {
    1: {"addr": 10, "spans": [(10, 1)], "patched": frozenset({10})},
    2: {"addr": 100, "spans": [(100, 1)], "patched": frozenset({100})},
}


def _make_state():
    st = AppState.__new__(AppState)        # ohne __init__ (keine DB/Threads)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_FX_A]
    import types as _ty
    st._prog_lock = threading.RLock()
    st._plan_lock = threading.RLock()      # STAB-15: explizit (kein Lazy-Race)
    st.output_manager = _ty.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


class RenderPlanAtomicTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: [_Ch("intensity", 1, 0)]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_snapshot_never_half_swapped(self):
        """Ein konsistenter Snapshot (unter _plan_lock) darf nie eine gemischte
        Feld-Kombination zeigen: fix_index, _commit_spans und _patched_set muessen
        IMMER zum selben Patch gehoeren."""
        st = _make_state()
        st._rebuild_render_plan()
        errors = []
        stop = threading.Event()

        def rebuilder():
            fxs = [_FX_A, _FX_B]
            i = 0
            while not stop.is_set():
                st._patch_cache = [fxs[i % 2]]
                i += 1
                try:
                    st._rebuild_render_plan()
                except Exception as exc:       # pragma: no cover - Fehlerpfad
                    errors.append(f"rebuild: {exc!r}")
                    return

        t = threading.Thread(target=rebuilder)
        t.start()
        try:
            for _ in range(6000):
                with st._get_plan_lock():
                    fids = tuple(st._fix_index.keys())
                    spans = st._commit_spans.get(1)
                    patched = st._patched_set.get(1)
                    default = st._default_frame.get(1)
                # Genau ein Fixture -> genau eine erwartete Konfiguration.
                if len(fids) != 1:
                    errors.append(f"fix_index nicht 1 Fixture: {fids}")
                    break
                cfg = _CONFIGS[fids[0]]
                if spans != cfg["spans"] or patched != cfg["patched"]:
                    errors.append(
                        f"halb getauscht: fid={fids[0]} spans={spans} "
                        f"patched={patched} (erwartet {cfg})")
                    break
                # _default_frame muss zum selben Patch passen (512 Byte, Adresse
                # gesetzt/plausibel) — nie None waehrend gepatcht.
                if default is None or len(default) != 512:
                    errors.append(f"default_frame inkonsistent: {default!r}")
                    break
        finally:
            stop.set()
            t.join(timeout=5)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_render_frame_during_rebuild_no_crash(self):
        """Der echte Renderer darf waehrend eines nebenlaeufigen Umpatchens nie
        crashen (kein KeyError/Index aus einer halb getauschten Kombination)."""
        st = _make_state()
        st._rebuild_render_plan()
        errors = []
        stop = threading.Event()

        def rebuilder():
            fxs = [_FX_A, _FX_B]
            i = 0
            while not stop.is_set():
                st._patch_cache = [fxs[i % 2]]
                i += 1
                try:
                    st._rebuild_render_plan()
                except Exception as exc:       # pragma: no cover - Fehlerpfad
                    errors.append(f"rebuild: {exc!r}")
                    return

        t = threading.Thread(target=rebuilder)
        t.start()
        try:
            for _ in range(3000):
                try:
                    st._render_frame(0.02)
                except Exception as exc:
                    errors.append(f"render: {exc!r}")
                    break
        finally:
            stop.set()
            t.join(timeout=5)
        self.assertEqual(errors, [], "\n".join(errors))


if __name__ == "__main__":
    unittest.main()

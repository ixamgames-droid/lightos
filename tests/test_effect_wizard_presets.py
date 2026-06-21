"""B1 / T-4 + EA-02: neue Effekt-Assistent-Presets (Wipe/Comet/Random-Strobe/VU)
und Farb-Zwischenstufen-Interpolation."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attr, channel_number):
        self.attribute = attr
        self.channel_number = channel_number
        self.ranges = []


class _Fx:
    def __init__(self, fid):
        self.fid = fid
        self.universe = 1
        self.address = 1
        self.label = f"FX {fid}"


# PAR mit RGB+W+Dimmer.
_PAR_CHANS = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
              _Ch("color_w", 4), _Ch("intensity", 5)]
_FIDS = [1, 2, 3]


class _Page0:
    def __init__(self, key):
        self._key = key

    def selected_key(self):
        return self._key


class _Page1:
    def selected_fids(self):
        return list(_FIDS)


class _Page2:
    def selected_colors(self):
        return [(255, 0, 0), (0, 0, 255)]

    def expanded_colors(self):
        return self.selected_colors()


class _Spin:
    def __init__(self, v):
        self._v = v

    def value(self):
        return self._v


class _Chk:
    def isChecked(self):
        return False


class _Page3:
    def __init__(self):
        self.name = type("N", (), {"text": lambda self: "T"})()
        self.hold = _Spin(0.2)
        self.fade = _Spin(0.05)
        self.beat = _Chk()


def _run_preset(key):
    import src.core.app_state as app_state
    import src.core.engine.function_manager as fm_mod
    from src.core.engine.function_manager import FunctionManager
    from src.ui.widgets.effect_wizard import EffectWizard

    fm = FunctionManager()
    fixtures = [_Fx(f) for f in _FIDS]
    fake_state = type("S", (), {
        "get_patched_fixtures": lambda self: list(fixtures),
        "get_selected_fids": lambda self: [],
    })()
    orig_state, orig_gcp, orig_fm = (app_state.get_state,
                                     app_state.get_channels_for_patched, fm_mod._manager)
    app_state.get_state = lambda: fake_state
    app_state.get_channels_for_patched = lambda fx: _PAR_CHANS
    fm_mod._manager = fm
    try:
        wiz = EffectWizard()
        wiz.page = lambda i: [_Page0(key), _Page1(), _Page2(), _Page3()][i]
        wiz._generate()
        return fm, wiz.created_function
    finally:
        app_state.get_state = orig_state
        app_state.get_channels_for_patched = orig_gcp
        fm_mod._manager = orig_fm
        try:
            wiz.deleteLater()
        except Exception:
            pass


class NewPresetsTest(unittest.TestCase):
    def test_presets_registered(self):
        from src.ui.widgets.effect_wizard import PRESETS
        keys = {p[0] for p in PRESETS}
        for k in ("wipe", "comet", "random_strobe", "vu"):
            self.assertIn(k, keys)

    def test_wipe_cumulative_fill(self):
        fm, ch = _run_preset("wipe")
        self.assertEqual(len(ch.steps), len(_FIDS))   # eine Stufe je Lampe
        first = fm.get(ch.steps[0].function_id)
        last = fm.get(ch.steps[-1].function_id)
        first_fids = {sv.fixture_id for sv in first.values}
        last_fids = {sv.fixture_id for sv in last.values}
        self.assertEqual(first_fids, {1})             # erste Stufe nur Lampe 1
        self.assertEqual(last_fids, set(_FIDS))        # letzte Stufe alle

    def test_comet_head_full_tail_dimmer(self):
        fm, ch = _run_preset("comet")
        self.assertEqual(len(ch.steps), len(_FIDS))
        # Im 3. Schritt (Kopf an Lampe 3) ist Lampe 3 voll, Lampe 2 gedimmt.
        s = fm.get(ch.steps[2].function_id)
        inten = {sv.fixture_id: sv.value for sv in s.values if sv.channel == 5}
        self.assertEqual(inten.get(3), 255)
        self.assertTrue(0 < inten.get(2, 0) < 255)

    def test_random_strobe_random_order(self):
        from src.core.engine.function import RunOrder
        fm, ch = _run_preset("random_strobe")
        self.assertEqual(len(ch.steps), len(_FIDS))
        self.assertEqual(ch.run_order, RunOrder.Random)

    def test_vu_bounces_up_and_down(self):
        fm, ch = _run_preset("vu")
        # levels = 1,2,3,2,1 -> 2n-1 Schritte
        self.assertEqual(len(ch.steps), 2 * len(_FIDS) - 1)


class ColorInterpolationTest(unittest.TestCase):
    def _page(self):
        from src.ui.widgets.effect_wizard import _ColorPage
        return _ColorPage()

    def test_off_returns_selected(self):
        page = self._page()
        for b in page.swatch_btns[:2]:
            b.setChecked(True)
        self.assertEqual(page.expanded_colors(), page.selected_colors())

    def test_interpolation_expands_with_wrap(self):
        page = self._page()
        # genau 2 Farben anwählen
        for b in page.swatch_btns:
            b.setChecked(False)
        page.swatch_btns[0].setChecked(True)   # Rot
        page.swatch_btns[3].setChecked(True)   # Grün
        page._interp_chk.setChecked(True)
        page._interp_spin.setValue(4)
        exp = page.expanded_colors()
        # 2 Farben * (1 + 4 Zwischen) = 10 (mit Wrap last->first)
        self.assertEqual(len(exp), 10)
        self.assertEqual(exp[0], page.swatch_btns[0].rgb)   # beginnt mit Rot


if __name__ == "__main__":
    unittest.main()

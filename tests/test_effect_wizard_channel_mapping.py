"""Regressions-Beweis: der Effekt-Assistent (EffectWizard._generate) muss die
DMX-Kanal-Zuordnung PRO Fixture berechnen.

Frueherer Bug: Die Map {attr: channel_number} wurde EINMAL aus dem ersten
gepatchten Geraet gebaut und fuer alle Geraete verwendet. Bei gemischten Typen
(PAR an Kanal 1-3 RGB, Moving Head mit Pan=1/Tilt=2 und color_r/g/b weiter
hinten) landete color_r=Ch1 dann auf dem Pan-Kanal des Moving Heads — er
bewegte sich statt die Farbe zu wechseln.

Dieser Test patcht einen PAR und einen Moving Head, erzeugt einen "color_chase"
ueber den Wizard und prueft, dass der MH KEINE Werte auf Pan/Tilt bekommt,
sondern auf seinen echten color_r/g/b-Kanaelen.

Verifiziert per Revert-Gedanke: mit der alten (festen) Map auf channel_number
1/2/3 wuerde der MH Werte auf Ch1/Ch2 (= Pan/Tilt) erhalten -> Test rot.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Ch:
    def __init__(self, attr, channel_number):
        self.attribute = attr
        self.channel_number = channel_number
        self.ranges = []


class _Fx:
    def __init__(self, fid, universe=1, address=1):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.label = f"FX {fid}"


# PAR: RGB an Ch1-3, Dimmer an Ch4.
_PAR_CHANS = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
              _Ch("intensity", 4)]
# Moving Head: Pan=1, Tilt=2, Intensity=3, color_r/g/b an 6/7/8.
_MH_CHANS = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3),
             _Ch("shutter", 4), _Ch("color_wheel", 5),
             _Ch("color_r", 6), _Ch("color_g", 7), _Ch("color_b", 8)]

PAR_FID, MH_FID = 101, 202
_CHANS_BY_FID = {PAR_FID: _PAR_CHANS, MH_FID: _MH_CHANS}


class _Page0:
    def selected_key(self):
        return "color_chase"


class _Page1:
    def selected_fids(self):
        return [PAR_FID, MH_FID]


class _Page2:
    def selected_colors(self):
        return [(255, 0, 0), (0, 255, 0), (0, 0, 255)]


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
        self.name = type("N", (), {"text": lambda self: "Test-Chase"})()
        self.hold = _Spin(0.5)
        self.fade = _Spin(0.2)
        self.beat = _Chk()


class EffectWizardChannelMappingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def _build_chaser(self):
        """Treibt EffectWizard._generate() headless mit gestubbten Pages und
        gestubbtem app_state und liefert (function_manager, created_chaser)."""
        import src.core.app_state as app_state
        from src.core.engine.function_manager import FunctionManager
        from src.ui.widgets.effect_wizard import EffectWizard

        fm = FunctionManager()
        fixtures = [_Fx(PAR_FID), _Fx(MH_FID)]

        fake_state = type("S", (), {
            "get_patched_fixtures": lambda self: list(fixtures),
            "get_selected_fids": lambda self: [],
        })()

        orig_state = app_state.get_state
        orig_gcp = app_state.get_channels_for_patched
        # FunctionManager-Singleton fuer den Lauf umbiegen.
        import src.core.engine.function_manager as fm_mod
        orig_fm = fm_mod._manager
        app_state.get_state = lambda: fake_state
        app_state.get_channels_for_patched = lambda fx: _CHANS_BY_FID[fx.fid]
        fm_mod._manager = fm
        try:
            wiz = EffectWizard()
            # Pages durch leichtgewichtige Stubs ersetzen (kein echtes QWizard-
            # Page-Treiben noetig; _generate liest nur ueber self.page(i)).
            stubs = [_Page0(), _Page1(), _Page2(), _Page3()]
            wiz.page = lambda i: stubs[i]
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

    def test_moving_head_color_not_on_pan_tilt(self):
        fm, chaser = self._build_chaser()
        self.assertIsNotNone(chaser)
        self.assertTrue(chaser.steps)

        mh_pan_tilt_seen = False
        mh_color_seen = False
        par_color_seen = False

        for step in chaser.steps:
            scene = fm.get(step.function_id)
            if scene is None:
                continue
            for sv in scene.values:
                if sv.fixture_id == MH_FID:
                    # Pan=Ch1, Tilt=Ch2 duerfen vom Farb-Chase NICHT gesetzt
                    # werden (nur color_r/g/b an Ch6/7/8 + intensity an Ch3).
                    if sv.channel in (1, 2) and sv.value != 0:
                        mh_pan_tilt_seen = True
                    if sv.channel in (6, 7, 8) and sv.value != 0:
                        mh_color_seen = True
                elif sv.fixture_id == PAR_FID:
                    if sv.channel in (1, 2, 3) and sv.value != 0:
                        par_color_seen = True

        self.assertFalse(mh_pan_tilt_seen,
                         "Moving Head darf vom Farb-Chase keine Pan/Tilt-Werte "
                         "bekommen (Bug: feste Kanal-Map aus dem ersten Fixture)")
        self.assertTrue(mh_color_seen,
                        "Moving Head muss Farbe auf seinen echten "
                        "color_r/g/b-Kanaelen (Ch6/7/8) erhalten")
        self.assertTrue(par_color_seen,
                        "PAR muss Farbe auf Ch1-3 erhalten")

    def test_mapping_per_fixture_exact_values(self):
        """Genauerer Beweis: im roten Schritt steht 255 auf MH-Ch6 (color_r),
        nichts auf Ch1 (pan); beim PAR 255 auf Ch1 (color_r)."""
        fm, chaser = self._build_chaser()
        # Erster Farb-Schritt = Rot (255,0,0).
        first = fm.get(chaser.steps[0].function_id)
        mh = {sv.channel: sv.value for sv in first.values if sv.fixture_id == MH_FID}
        par = {sv.channel: sv.value for sv in first.values if sv.fixture_id == PAR_FID}
        # MH: color_r (Ch6)=255, color_g/b (Ch7/8)=0, intensity (Ch3)=255.
        self.assertEqual(mh.get(6), 255)
        self.assertEqual(mh.get(7), 0)
        self.assertEqual(mh.get(8), 0)
        # Pan/Tilt (Ch1/2) duerfen gar nicht vorkommen.
        self.assertNotIn(1, mh)
        self.assertNotIn(2, mh)
        # PAR: color_r (Ch1)=255.
        self.assertEqual(par.get(1), 255)
        self.assertEqual(par.get(2), 0)


if __name__ == "__main__":
    unittest.main()

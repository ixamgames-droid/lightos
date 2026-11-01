"""UI-77: 'Pan-Mitte/Tilt-Mitte (DMX)' nimmt Kommazahlen.

Die Rechnung (``aim.py``, ``einmessen.py``, 3D) arbeitet seit jeher mit
Kommazahlen, aber der Patch-Dialog bot nur ein ganzzahliges Feld an, und
``update_fixture`` sowie Show-Datei (Speichern UND Laden) rundeten per ``int()``
ab. Ein am Rig gemessener Wert wie 167,5 kam nie an: 167,5 -> 167.

Dieser Test geht den ganzen Weg: Dialog (deutsches Komma) -> ``update_fixture``
-> Show-Datei speichern/laden -> Zielen (``aim_kw``). Alt-Shows mit ganzen
Zahlen laden unveraendert.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


class _Basis(unittest.TestCase):
    def setUp(self):
        _app()
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        from src.core.database.models import PatchedFixture
        ensure_builtins()
        reset_show()
        self.addCleanup(reset_show)
        self.state = get_state()
        self.state.add_fixture(PatchedFixture(
            fid=1, label="MH", fixture_profile_id=1, mode_name="m", universe=1,
            address=1, channel_count=16, fixture_type="moving_head"))

    def _f(self):
        return next(x for x in self.state.get_patched_fixtures() if x.fid == 1)


class DialogNimmtKommaTest(_Basis):

    def _dialog(self):
        import src.ui.views.patch_view as PV
        d = PV.PatchFixtureEditDialog(self.state, self._f())
        self.addCleanup(d.deleteLater)
        return d

    def test_167_komma_5_kommt_im_dialog_an(self):
        d = self._dialog()
        for spin in (d._spin_pan_zero, d._spin_tilt_zero):
            spin.lineEdit().selectAll()
            spin.lineEdit().insert("167,5")          # deutsches Komma, wie am Rig getippt
            spin.interpretText()
        d._on_accept()
        self.assertEqual(d.result_updates["pan_zero_dmx"], 167.5,
                         "Pan-Mitte 167,5 wird im Dialog abgeschnitten")
        self.assertEqual(d.result_updates["tilt_zero_dmx"], 167.5)

    def test_punkt_wird_wie_komma_gelesen(self):
        # Review: das deutsche Feld verwarf einen getippten Punkt STILL —
        # "167.5" wurde 167,00, also genau die Abrundung, die UI-77 beheben soll.
        from PySide6.QtTest import QTest
        d = self._dialog()
        for txt, soll in (("167.5", 167.5), ("167,25", 167.25)):
            sp = d._spin_pan_zero
            sp.lineEdit().selectAll()
            QTest.keyClicks(sp.lineEdit(), txt)       # echte Tastendruecke
            sp.interpretText()
            self.assertEqual(sp.value(), soll, txt)

    def test_testshow_traegt_die_gemessene_mitte(self):
        # Review: tools/build_spot90_testshow.py misst 167.5, schrieb aber
        # int(PAN_ZERO) = 167 in den Patch, waehrend seine Szenen mit 167.5 zielen.
        src = (ROOT / "tools" / "build_spot90_testshow.py").read_text(encoding="utf-8")
        self.assertNotIn("int(PAN_ZERO)", src)
        self.assertNotIn("int(TILT_ZERO)", src)

    def test_dialog_zeigt_gespeicherte_kommazahl(self):
        self.state.update_fixture(1, pan_zero_dmx=167.5, tilt_zero_dmx=127.25)
        d = self._dialog()
        self.assertEqual(d._spin_pan_zero.value(), 167.5)
        self.assertEqual(d._spin_tilt_zero.value(), 127.25)
        self.assertIn("167,5", d._spin_pan_zero.text())   # Komma, nicht Punkt

    def test_ganze_zahl_und_null_bleiben(self):
        self.state.update_fixture(1, pan_zero_dmx=0, tilt_zero_dmx=128)
        d = self._dialog()
        d._on_accept()
        self.assertEqual(d.result_updates["pan_zero_dmx"], 0.0)   # echte 0 bleibt 0
        self.assertEqual(d.result_updates["tilt_zero_dmx"], 128.0)


class SpeichernLadenTest(_Basis):

    def test_update_fixture_behaelt_die_kommazahl(self):
        self.assertTrue(self.state.update_fixture(1, pan_zero_dmx=167.5, tilt_zero_dmx=141.25))
        self.assertEqual((self._f().pan_zero_dmx, self._f().tilt_zero_dmx), (167.5, 141.25))

    def test_show_datei_rundreise(self):
        from src.core.show.show_file import save_show, load_show
        self.state.update_fixture(1, pan_zero_dmx=167.5, tilt_zero_dmx=141.25)
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "ui77.lshow")
            save_show(pfad)
            self.state.update_fixture(1, pan_zero_dmx=128, tilt_zero_dmx=128)
            ok, msg = load_show(pfad)
            self.assertTrue(ok, msg)
        f = self._f()
        self.assertEqual((f.pan_zero_dmx, f.tilt_zero_dmx), (167.5, 141.25),
                         "167,5 kommt nach Speichern/Laden nicht zurueck")

    def test_dict_rundreise_und_alte_ganzzahl(self):
        from src.core.show.show_file import _fixture_to_dict, _patched_fixture_from_data
        f = self._f()
        f.pan_zero_dmx, f.tilt_zero_dmx = 167.5, 99.75
        d = _fixture_to_dict(f)
        self.assertEqual((d["pan_zero_dmx"], d["tilt_zero_dmx"]), (167.5, 99.75))
        g = _patched_fixture_from_data(dict(d), 1)
        self.assertEqual((g.pan_zero_dmx, g.tilt_zero_dmx), (167.5, 99.75))
        alt = dict(d, pan_zero_dmx=120, tilt_zero_dmx=130)          # Alt-Show: int
        g = _patched_fixture_from_data(alt, 1)
        self.assertEqual((g.pan_zero_dmx, g.tilt_zero_dmx), (120, 130))
        ohne = {k: v for k, v in d.items() if not k.endswith("_zero_dmx")}
        g = _patched_fixture_from_data(ohne, 1)                    # ganz ohne Feld
        self.assertEqual((g.pan_zero_dmx, g.tilt_zero_dmx), (128, 128))

    def test_kaputte_werte(self):
        from src.core.show.show_file import _to_dmx_mitte
        for kaputt in (None, "abc", float("nan"), float("inf")):
            self.assertEqual(_to_dmx_mitte(kaputt), 128.0, kaputt)
        self.assertEqual(_to_dmx_mitte("167.5"), 167.5)
        self.assertEqual(_to_dmx_mitte(1000), 255.0)               # begrenzt
        self.assertEqual(_to_dmx_mitte(-3), 0.0)


class ZielenNutztKommazahlTest(_Basis):

    def test_aim_kw_mit_167_5(self):
        from src.core.stage.einmessen import aim_kw
        self.state.update_fixture(1, pan_zero_dmx=167.5, tilt_zero_dmx=141.25,
                                  aim_offset_pan=0.5)
        kw = aim_kw(self._f())
        self.assertEqual((kw["pan_zero_dmx"], kw["tilt_zero_dmx"]), (168.0, 141.25))


if __name__ == "__main__":
    unittest.main()

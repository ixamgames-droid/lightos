"""VCG-02: Tastenbild als Momentaufnahme aus der 3D-Ansicht.

Geprueft ohne echte WebGL-Seite (die steht in
``test_vcg02_momentaufnahme_scene.py``): Zuschnitt/Skalierung als reine
Funktion, der Dialog-Weg mit einer gestellten 3D-Ansicht bis in den
Asset-Cache, die Meldung ohne offenes 3D-Fenster und der Rundlauf
Show speichern/laden.
"""
import base64
import os
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from src.core.show import vc_assets
from src.ui.virtualconsole import vc_momentaufnahme as mom
from src.ui.virtualconsole.vc_gallery_dialog import VCGalleryDialog

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


GRUEN = QColor(0, 200, 0)
ROT = QColor(200, 0, 0)


def _streifenbild(w, h, rand):
    """Mitte gruen, links/rechts je ``rand`` px rot."""
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(GRUEN)
    p = QPainter(img)
    p.fillRect(0, 0, rand, h, ROT)
    p.fillRect(w - rand, 0, rand, h, ROT)
    p.end()
    return img


def _data_url(img):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode()


class _Seite:
    def __init__(self, antwort):
        self.antwort = antwort
        self.js = []

    def runJavaScript(self, js, cb):
        self.js.append(js)
        cb(self.antwort)


class _Gestellte3DAnsicht(QWidget):
    """Steht fuer die QWebEngineView der 3D-Szene (Kennzeichen wie
    ``load_stage_html``)."""

    def __init__(self, antwort):
        super().__init__()
        self._lightos_3d_szene = True
        self._seite = _Seite(antwort)
        self.resize(800, 400)

    def page(self):
        return self._seite


class ZuschnittTest(unittest.TestCase):
    def test_mitte_im_seitenverhaeltnis(self):
        aus = mom.zuschneiden(_streifenbild(400, 200, 100), 1.0)
        self.assertEqual((aus.width(), aus.height()), (200, 200))
        for x in (0, 100, 199):
            self.assertEqual(aus.pixelColor(x, 100).name(), GRUEN.name(),
                             f"Rand bei x={x} nicht weggeschnitten")

    def test_zu_hoch_wird_oben_unten_gekappt(self):
        aus = mom.zuschneiden(_streifenbild(100, 400, 1), 2.0)
        self.assertEqual((aus.width(), aus.height()), (100, 50))

    def test_verkleinert_auf_max_px_ohne_zu_vergroessern(self):
        gross = mom.zuschneiden(_streifenbild(1600, 800, 10), 2.0)
        self.assertEqual((gross.width(), gross.height()), (mom.MAX_PX, mom.MAX_PX // 2))
        klein = mom.zuschneiden(_streifenbild(60, 30, 1), 2.0)
        self.assertEqual((klein.width(), klein.height()), (60, 30))

    def test_unsinniges_seitenverhaeltnis_faellt_auf_quadrat(self):
        for sv in (0, -1, None, float("nan"), float("inf")):
            aus = mom.zuschneiden(_streifenbild(300, 100, 1), sv)
            self.assertEqual((aus.width(), aus.height()), (100, 100), sv)

    def test_leeres_bild_und_kaputte_data_url(self):
        self.assertTrue(mom.zuschneiden(QImage(), 1.0).isNull())
        for kaputt in ("", None, "data:image/png;base64,@@@", "keine-url"):
            self.assertIsNone(mom.als_tastenbild(kaputt, 1.0), kaputt)


class DialogAufnahmeTest(unittest.TestCase):
    def setUp(self):
        vc_assets.set_cache_dir_for_test(tempfile.mkdtemp(prefix="vcg02_"))
        self.meldungen = []

    def tearDown(self):
        dlg = getattr(self, "dlg", None)
        if dlg is not None:
            dlg._stop_movies()
        vc_assets.set_cache_dir_for_test(None)

    def _dialog(self):
        # Die Taste am Test festhalten: stirbt sie, nimmt sie den Dialog mit.
        self.taste = QWidget()
        self.taste.resize(160, 80)           # Taste 2:1
        dlg = VCGalleryDialog(self.taste)
        dlg._melden = self.meldungen.append
        self.dlg = dlg
        return dlg

    def test_ohne_3d_fenster_verstaendliche_meldung(self):
        dlg = self._dialog()
        self.assertIsNone(mom.finde_3d_ansicht())
        dlg._aus_3d_aufnehmen()
        self.assertEqual(self.meldungen, [mom.MELDUNG_KEIN_3D])
        self.assertIn("3D-Visualizer öffnen", mom.MELDUNG_KEIN_3D)
        self.assertIsNone(dlg.selected_key)

    def test_unsichtbare_ansicht_zaehlt_nicht(self):
        ansicht = _Gestellte3DAnsicht(_data_url(_streifenbild(800, 400, 10)))
        ansicht.hide()
        self.assertIsNone(mom.finde_3d_ansicht())

    def test_aufnahme_setzt_zugeschnittenes_png_als_key(self):
        ansicht = _Gestellte3DAnsicht(_data_url(_streifenbild(800, 400, 100)))
        ansicht.show()
        dlg = self._dialog()
        dlg._aus_3d_aufnehmen()
        self.assertEqual(self.meldungen, [])
        self.assertIn("momentaufnahme", ansicht.page().js[0])
        key = dlg.selected_key
        self.assertTrue(vc_assets.is_valid_key(key), key)
        self.assertTrue(key.endswith(".png"))
        bild = QImage(vc_assets.resolve(key))
        self.assertFalse(bild.isNull())
        # 800x400 -> Taste 2:1 -> ganzes Bild, dann auf 256x128 verkleinert
        self.assertEqual((bild.width(), bild.height()), (256, 128))
        self.assertEqual(dlg.result(), VCGalleryDialog.DialogCode.Accepted)

    def test_leere_antwort_meldet_und_setzt_nichts(self):
        ansicht = _Gestellte3DAnsicht("")
        ansicht.show()
        dlg = self._dialog()
        dlg._aus_3d_aufnehmen()
        self.assertEqual(self.meldungen, [mom.MELDUNG_FEHLGESCHLAGEN])
        self.assertIsNone(dlg.selected_key)
        self.assertTrue(dlg._btn_aufnahme.isEnabled())

    def test_spaete_antwort_nach_schliessen_wird_verworfen(self):
        dlg = self._dialog()
        dlg.reject()
        dlg._aufnahme_fertig(_data_url(_streifenbild(80, 40, 1)))
        self.assertIsNone(dlg.selected_key)
        self.assertEqual(self.meldungen, [])


class KennzeichenTest(unittest.TestCase):
    """Die Suche haengt am Kennzeichen aus ``load_stage_html`` — der
    Szenentest setzt es selbst, also hier eigens: faellt die Zeile weg,
    findet der Dialog nie eine 3D-Ansicht."""

    def test_load_stage_html_kennzeichnet_die_ansicht(self):
        import src.ui.visualizer.visualizer_window as VW

        class _FakeView:
            def __init__(self):
                self.geladen = []

            def load(self, url):
                self.geladen.append(url)

        v = _FakeView()
        VW.load_stage_html(v)
        self.assertTrue(v.geladen)
        self.assertIs(getattr(v, "_lightos_3d_szene", False), True)


class ShowRundlaufTest(unittest.TestCase):
    """Das aufgenommene Bild reist in der .lshow mit und kommt auf einem
    anderen Rechner (frischer Cache) wieder."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vcg02_show_")
        vc_assets.set_cache_dir_for_test(os.path.join(self._tmp, "cache1"))

    def tearDown(self):
        vc_assets.set_cache_dir_for_test(None)

    def test_speichern_laden_bild_bleibt(self):
        from src.core.app_state import get_state
        from src.core.show import show_file
        from src.ui.virtualconsole.vc_button import VCButton

        key = mom.als_tastenbild(_data_url(_streifenbild(400, 200, 50)), 2.0)
        self.assertTrue(vc_assets.is_valid_key(key))
        daten = vc_assets.bytes_for(key)
        taste = VCButton()
        taste.set_bg_image(key)
        state = get_state()
        state._vc_layout = {"pages": [{"widgets": [taste.to_dict()]}]}

        pfad = os.path.join(self._tmp, "vcg02.lshow")
        show_file.save_show(pfad)
        with zipfile.ZipFile(pfad) as zf:
            self.assertIn(vc_assets.zip_name(key), zf.namelist())

        vc_assets.set_cache_dir_for_test(os.path.join(self._tmp, "cache2"))
        self.assertEqual(vc_assets.resolve(key), "")
        ok, msg = show_file.load_show(pfad)
        self.assertTrue(ok, msg)
        self.assertEqual(vc_assets.bytes_for(key), daten)
        geladen = VCButton()
        geladen.apply_dict(state._vc_layout["pages"][0]["widgets"][0])
        self.assertEqual(geladen.bg_image, key)


if __name__ == "__main__":
    unittest.main()

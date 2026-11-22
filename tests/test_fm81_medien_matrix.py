"""FM-81 — Medien auf die Matrix: Bild und animiertes GIF als Matrix-Art.

Testmedien werden im Test mit QImage/QImageWriter erzeugt (kleine PNG/GIF),
der Medien-Ordner ist ein Wegwerf-Ordner. Erwartete Pixel sind von HAND aus
dem Testbild abgeleitet.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage                         # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

import pytest                                                    # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets          # noqa: E402

from src.core.engine import matrix_media as MM                    # noqa: E402
from src.core.engine.rgb_matrix import (RgbAlgorithm,             # noqa: E402
                                        RgbMatrixInstance)

R, G, B, W, K = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0)


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _bild(zeilen) -> QImage:
    """QImage aus einer Liste von Zeilen mit RGB-Tupeln."""
    h, w = len(zeilen), len(zeilen[0])
    img = QImage(w, h, QImage.Format.Format_RGB32)
    for y, zeile in enumerate(zeilen):
        for x, c in enumerate(zeile):
            img.setPixelColor(x, y, QColor(*c))
    return img


def _warte(bedingung, timeout=5.0):
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


class _Basis(unittest.TestCase):

    def setUp(self):
        _app()
        self.ordner = tempfile.mkdtemp(prefix="lightos_fm81_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)
        MM.set_media_dir_for_test(os.path.join(self.ordner, "medien"))
        self.addCleanup(MM.set_media_dir_for_test, None)

    def _png(self, name, zeilen) -> str:
        pfad = os.path.join(MM.media_dir(), name)
        self.assertTrue(_bild(zeilen).save(pfad, "PNG"))
        return name

    def _matrix(self, cols, rows, **params) -> RgbMatrixInstance:
        m = RgbMatrixInstance("Medien", cols=cols, rows=rows,
                              fixture_grid=list(range(1, cols * rows + 1)),
                              algorithm=RgbAlgorithm.MEDIA)
        m.matrix_speed = 1.0
        m.params.update(params)
        return m

    def _render_fertig(self, m, phase=0.0):
        """Rendert, bis die Hintergrund-Dekodierung fertig ist."""
        _warte(lambda: (m._render(phase), not MM.bilder(
            m.params.get("media_path", ""), m.cols, m.rows,
            m.params.get("media_fit", "fit"),
            m.params.get("media_rotation", "0")).laedt)[1])
        return m._render(phase)


class BildTest(_Basis):

    BILD = [[R, G, B],
            [W, K, R]]          # 3 breit, 2 hoch

    def test_bild_landet_pixelgenau_im_raster(self):
        rel = self._png("a.png", self.BILD)
        m = self._matrix(3, 2, media_path=rel)
        self.assertEqual(self._render_fertig(m), [R, G, B, W, K, R])
        self.assertEqual(m.medien_meldung, "")

    def test_drehung_90_auf_hochkant_gruppe(self):
        """3x2-Bild um 90° im Uhrzeigersinn -> 2 breit, 3 hoch: die alte
        linke Spalte (R oben, W unten) wird von unten nach oben gelesen zur
        oberen Zeile (W,R), die mittlere zu (K,G), die rechte zu (R,B)."""
        rel = self._png("a.png", self.BILD)
        m = self._matrix(2, 3, media_path=rel, media_rotation="90")
        self.assertEqual(self._render_fertig(m), [W, R, K, G, R, B])

    def test_drehung_180(self):
        rel = self._png("a.png", self.BILD)
        m = self._matrix(3, 2, media_path=rel, media_rotation="180")
        self.assertEqual(self._render_fertig(m), [R, K, W, B, G, R])

    def test_einpassen_fuellen_strecken(self):
        # 2x1-Bild (R,B) auf ein 2x2-Raster
        rel = self._png("b.png", [[R, B]])
        einp = self._render_fertig(self._matrix(2, 2, media_path=rel, media_fit="fit"))
        # einpassen: Bild 2x1 in der Mitte -> bei 2 Zeilen oben (y=0), unten schwarz
        self.assertEqual(einp, [R, B, K, K])
        streck = self._render_fertig(self._matrix(2, 2, media_path=rel, media_fit="stretch"))
        self.assertEqual(streck, [R, B, R, B])
        fuell = self._render_fertig(self._matrix(2, 2, media_path=rel, media_fit="fill"))
        self.assertNotIn(K, fuell, "Füllen lässt keinen schwarzen Rand")

    def test_helligkeit_skaliert_nur_die_farbe(self):
        rel = self._png("a.png", self.BILD)
        m = self._matrix(3, 2, media_path=rel, media_brightness=0.5)
        px = self._render_fertig(m)
        self.assertEqual(px[0], (127, 0, 0))
        self.assertFalse(m.drive_intensity, "Farbe zieht den Dimmer nicht automatisch mit")

    def test_fehlende_datei_klare_meldung_kein_absturz(self):
        m = self._matrix(2, 2, media_path="gibtsnicht.png")
        self.assertEqual(m._render(0.0), [K] * 4)
        self.assertIn("Medium fehlt", m.medien_meldung)
        self.assertIn("gibtsnicht.png", m.medien_meldung)

    def test_pfad_darf_medienordner_nicht_verlassen(self):
        self.assertIsNone(MM.resolve("../geheim.png"))

    def test_video_ehrlich_abgelehnt(self):
        pfad = os.path.join(MM.media_dir(), "clip.mp4")
        with open(pfad, "wb") as f:
            f.write(b"\0" * 16)
        m = self._matrix(2, 2, media_path="clip.mp4")
        self._render_fertig(m)
        self.assertIn("Video", m.medien_meldung)

    def test_import_kopiert_in_den_medienordner_relativ(self):
        quelle = os.path.join(self.ordner, "draussen.png")
        _bild(self.BILD).save(quelle, "PNG")
        rel = MM.import_file(quelle)
        self.assertEqual(rel, "draussen.png")
        self.assertTrue(os.path.isfile(os.path.join(MM.media_dir(), rel)))


class GifTest(_Basis):

    def _folge_von_hand(self, name, farben):
        """Mehrbild-GIF ohne Qt-Schreiber: kleine GIF89a-Datei von Hand."""
        import struct
        pal = b"".join(bytes(c) for c in farben) + b"\0\0\0" * (4 - len(farben))
        out = bytearray(b"GIF89a" + struct.pack("<HHBBB", 2, 2, 0xF1, 0, 0) + pal)
        out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"
        for i, _c in enumerate(farben):
            out += b"\x21\xf9\x04\x00" + struct.pack("<H", 10) + b"\x00\x00"  # 100 ms
            out += b"\x2c" + struct.pack("<HHHHB", 0, 0, 2, 2, 0)
            # LZW, Mindestcodegroesse 2: Clear(4), 4x Index i, End(5)
            bits, n = 0, 0
            for code in [4, i, i, i, i, 5]:
                bits |= code << n
                n += 3
            daten = bits.to_bytes((n + 7) // 8, "little")
            out += b"\x02" + bytes([len(daten)]) + daten + b"\x00"
        out += b"\x3b"
        with open(os.path.join(MM.media_dir(), name), "wb") as f:
            f.write(bytes(out))
        return name

    def test_gif_bildwechsel_mit_tempo_und_schleife(self):
        rel = self._folge_von_hand("anim.gif", [R, G, B])
        m = self._matrix(2, 2, media_path=rel)
        self.assertEqual(self._render_fertig(m, 0.0), [R] * 4)
        erg = MM.bilder(rel, 2, 2)
        self.assertEqual(len(erg.folge.bilder), 3)
        self.assertAlmostEqual(erg.folge.gesamt, 0.3, places=3)
        self.assertEqual(m._render(0.15)[0], G)      # 2. Bild nach 100 ms
        self.assertEqual(m._render(0.25)[0], B)
        self.assertEqual(m._render(0.35)[0], R)      # Schleife
        # Tempo 2: doppelt so schnell -> bei 0.075 s schon Bild 2
        m.params["media_tempo"] = 2.0
        self.assertEqual(m._render(0.075)[0], G)
        # Schleife aus: am Ende bleibt das letzte Bild stehen
        m.params["media_tempo"] = 1.0
        m.params["media_loop"] = False
        self.assertEqual(m._render(5.0)[0], B)

    def test_schritte_regler_aendert_medienzeit_nicht(self):
        rel = self._folge_von_hand("anim.gif", [R, G])
        m = self._matrix(2, 2, media_path=rel)
        self._render_fertig(m)
        m.matrix_speed = 4.0
        # Phase 0.6 bei 4 Schritten/s = 0.15 s -> Bild 2
        self.assertEqual(m._render(0.6)[0], G)


class ShowTest(_Basis):

    def test_speichern_laden_behaelt_medium_pfad(self):
        from src.core.app_state import get_state
        from src.core.show.show_file import load_show, reset_show, save_show
        reset_show()
        self.addCleanup(reset_show)
        state = get_state()
        rel = self._png("a.png", BildTest.BILD)
        m = self._matrix(3, 2, media_path=rel, media_rotation="180",
                         media_fit="stretch", media_tempo=1.5)
        state.function_manager.add(m)
        pfad = os.path.join(self.ordner, "medien.lshow")
        save_show(pfad)
        reset_show()
        ok, msg = load_show(pfad)
        self.assertTrue(ok, msg)
        neu = [f for f in state.function_manager.all() if f.name == "Medien"]
        self.assertEqual(len(neu), 1)
        n = neu[0]
        self.assertEqual(n.algorithm, RgbAlgorithm.MEDIA)
        self.assertEqual(n.params["media_path"], "a.png")
        self.assertEqual(n.params["media_rotation"], "180")
        self.assertEqual(n.params["media_fit"], "stretch")
        self.assertEqual(self._render_fertig(n), [R, K, W, B, G, R])
        # Das Medium steckt NICHT in der Show-Datei
        import zipfile
        if zipfile.is_zipfile(pfad):
            with zipfile.ZipFile(pfad) as zf:
                self.assertFalse([e for e in zf.namelist() if e.endswith(".png")])

    def test_alt_show_ohne_medien_felder_laedt(self):
        alt = {"name": "Alt", "algorithm": "Chase", "cols": 2, "rows": 1,
               "fixture_grid": [1, 2], "params": {}}
        m = RgbMatrixInstance.from_dict(alt)
        self.assertEqual(m.algorithm, RgbAlgorithm.CHASE)
        self.assertEqual(m.medien_meldung, "")


class EditorTest(_Basis):

    def test_editor_zeigt_medien_knopf_und_setzt_pfad(self):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        from src.core.show.show_file import reset_show
        reset_show()
        self.addCleanup(reset_show)
        v = RgbMatrixView()
        self.addCleanup(v.deleteLater)
        m = self._matrix(3, 2)
        v._current = m
        v._load_ui(m)
        self.assertIsNotNone(getattr(v, "_medien_knopf", None))
        quelle = os.path.join(self.ordner, "x.png")
        _bild(BildTest.BILD).save(quelle, "PNG")
        rel = v.medium_setzen(quelle)
        self.assertEqual(m.params["media_path"], rel)
        self.assertTrue(_warte(lambda: m._render(0.0) == [R, G, B, W, K, R]))
        # Pruef-Nachbesserung: die Statuszeile bleibt nicht auf „wird geladen"
        # stehen, sondern zieht nach, sobald der Hintergrund fertig ist.
        def _status_fertig():
            QApplication.processEvents()
            return "1 Bild" in v._medien_status.text()
        self.assertTrue(_warte(_status_fertig), v._medien_status.text())


class CacheTest(_Basis):

    def test_alte_bildfolgen_werden_verworfen(self):
        """Pruef-Nachbesserung: jede Drehung/Rastergroesse ist ein eigener
        Schluessel — der Cache haelt trotzdem hoechstens MAX_CACHE Folgen."""
        rel = self._png("a.png", BildTest.BILD)
        for n in range(MM.MAX_CACHE + 4):
            erg = MM.vorbereiten(rel, 2 + n, 2, "stretch", "0", warten=5.0)
            self.assertIsNotNone(erg.folge, erg.meldung)
        self.assertLessEqual(len(MM._cache), MM.MAX_CACHE)


if __name__ == "__main__":
    unittest.main()

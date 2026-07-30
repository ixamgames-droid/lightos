"""GDS-6: Der Galerie-Generator schrieb bei jedem Lauf Binärdateien um, die sich
inhaltlich gar nicht geändert hatten.

Der Docstring versprach eine deterministische Ausgabe — und **auf einem Rechner
stimmt das auch**: zwei Läufe in getrennten Prozessen liefern hier byte-identische
GIFs. Verschieden werden sie **zwischen Umgebungen**. Gemessen am 2026-07-31:
sechs der zehn committeten GIFs (`beam_sweep`, `color_wheel`, `gobo_spin`,
`rainbow_scroll`, `sparkle`, `vu_meter`, auf dem alten Windows-ARM-Rechner
erzeugt) sind gegenüber der frischen Ausgabe **Frame für Frame pixelgleich, aber
anders kodiert** — die adaptive Palette des GIF-Writers hängt an der
Pillow-Version.

Folge: jeder Generator-Lauf churnt alle sechs im Diff, und man sieht nicht mehr,
was sich wirklich geändert hat (bei GDS-3 mussten sie von Hand zurückgesetzt
werden). Eine feste Palette würde das nicht lösen — auch der Rest des Writers
kann sich zwischen Versionen ändern. Der Riegel sitzt deshalb beim Schreiben:
**verglichen werden Pixel, nicht Bytes.**
"""
import io
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

from PIL import Image                                   # noqa: E402

import gen_vc_gallery as G                              # noqa: E402


def _gif_bytes(farben, optimize):
    """Winziges GIF aus Vollton-Frames — `optimize` aendert die KODIERUNG,
    nicht die Pixel."""
    frames = [Image.new("RGBA", (8, 8), f) for f in farben]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   loop=0, duration=80, disposal=2, optimize=optimize)
    return buf.getvalue()


class PixelVergleichTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="gds6-")
        self.pfad = os.path.join(self.dir, "probe.gif")

    def test_gleiche_pixel_andere_kodierung_gilt_als_gleich(self):
        """★ Der Kern: genau diese Lage haben die sechs committeten GIFs."""
        a = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=True)
        b = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=False)
        self.assertNotEqual(a, b, "Testaufbau kaputt: die Bytes muessen sich "
                                  "unterscheiden, sonst prueft der Test nichts")
        with open(self.pfad, "wb") as fh:
            fh.write(b)
        self.assertTrue(G._pixels_equal(a, self.pfad))

    def test_andere_pixel_gelten_als_verschieden(self):
        a = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=True)
        with open(self.pfad, "wb") as fh:
            fh.write(_gif_bytes([(255, 0, 0, 255), (0, 200, 255, 255)], True))
        self.assertFalse(G._pixels_equal(a, self.pfad))

    def test_andere_frame_zahl_gilt_als_verschieden(self):
        a = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=True)
        with open(self.pfad, "wb") as fh:
            fh.write(_gif_bytes([(255, 0, 0, 255)], True))
        self.assertFalse(G._pixels_equal(a, self.pfad))

    def test_fehlende_datei_gilt_als_verschieden(self):
        a = _gif_bytes([(255, 0, 0, 255)], optimize=True)
        self.assertFalse(G._pixels_equal(a, self.pfad))

    def test_kaputte_datei_wird_neu_geschrieben_statt_zu_werfen(self):
        with open(self.pfad, "wb") as fh:
            fh.write(b"kein GIF")
        a = _gif_bytes([(255, 0, 0, 255)], optimize=True)
        self.assertFalse(G._pixels_equal(a, self.pfad))
        self.assertTrue(G._write_if_changed(a, self.pfad))


class SchreibRiegelTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="gds6-")
        self.pfad = os.path.join(self.dir, "probe.gif")

    def test_datei_bleibt_unangetastet_wenn_die_pixel_stimmen(self):
        alt = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=False)
        with open(self.pfad, "wb") as fh:
            fh.write(alt)
        vorher = os.stat(self.pfad).st_mtime_ns
        neu = _gif_bytes([(255, 0, 0, 255), (0, 128, 255, 255)], optimize=True)
        self.assertFalse(G._write_if_changed(neu, self.pfad))
        self.assertEqual(os.stat(self.pfad).st_mtime_ns, vorher,
                         "die Datei darf nicht einmal neu geschrieben werden")
        with open(self.pfad, "rb") as fh:
            self.assertEqual(fh.read(), alt, "Bytes muessen unveraendert bleiben")

    def test_echte_aenderung_wird_geschrieben(self):
        with open(self.pfad, "wb") as fh:
            fh.write(_gif_bytes([(255, 0, 0, 255)], True))
        neu = _gif_bytes([(0, 255, 0, 255)], True)
        self.assertTrue(G._write_if_changed(neu, self.pfad))
        with open(self.pfad, "rb") as fh:
            self.assertEqual(fh.read(), neu)


class BestandsGalerieTest(unittest.TestCase):
    """Die committete Galerie ist der eigentliche Streitfall."""

    def test_committete_gifs_gelten_als_unveraendert(self):
        """Ein frisch kodiertes GIF mit denselben Pixeln wie die committete
        Datei darf sie nicht ersetzen — sonst churnt der naechste Lauf wieder."""
        pfad = os.path.join(REPO, "assets", "vc_gallery", "beam_sweep.gif")
        if not os.path.exists(pfad):
            self.skipTest("Galerie nicht im Checkout")
        from PIL import ImageSequence
        with Image.open(pfad) as bild:
            frames = [f.convert("RGBA").copy() for f in ImageSequence.Iterator(bild)]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True,
                       append_images=frames[1:], loop=0, duration=83,
                       disposal=2, optimize=True)
        self.assertTrue(G._pixels_equal(buf.getvalue(), pfad))


if __name__ == "__main__":
    unittest.main()

"""TOOL-21: der „unveraendert"-Vergleich der Anleitungsbilder zaehlt je Farbkanal.

``tools/anleitungsbilder/runner.py`` laesst ein vorhandenes Bild liegen, wenn das
neu gerenderte sich nur unmerklich unterscheidet (sonst aenderte jeder Lauf alle
Bilder im git-Diff). Der Vergleich wandelte die Differenz aber erst in
Graustufen und hielt DANN gegen die Schwelle 48:

    Helligkeit = 0,299 R + 0,587 G + 0,114 B

Eine Aenderung nur im Blau-Kanal kommt damit selbst beim vollen Sprung
0 -> 255 auf 29 — unter der Schwelle. Rot bleibt bis 162 darunter, Gruen bis
82. Ein Bild, in dem ein Feld von Schwarz auf Blau wechselt (eine Taste, eine
Farbkachel, ein Strahl), galt als unveraendert: die alte Datei blieb liegen,
die Anleitung zeigte den alten Zustand. Herkunft: Codex-Review #853.

Jetzt zaehlt der groesste der drei Kanalabstaende. Die Toleranz, fuer die es den
Vergleich gibt (einzelne anders glimmende Pixel, kleine Abweichungen je Kanal),
bleibt.
"""
import io
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

GROESSE = (400, 300)
GRUND = (30, 33, 40)
FELD = (100, 80, 300, 220)          # 200 x 140 = 23 % der Flaeche


def _bild(feld_farbe, grund=GRUND):
    from PIL import Image
    im = Image.new("RGB", GROESSE, grund)
    im.paste(feld_farbe, FELD)
    return im


def _png(im) -> bytes:
    puffer = io.BytesIO()
    im.save(puffer, "PNG")
    return puffer.getvalue()


class BildvergleichJeKanalTest(unittest.TestCase):

    def setUp(self):
        from anleitungsbilder import runner
        self.runner = runner
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _datei(self, name: str, daten: bytes) -> str:
        pfad = os.path.join(self._tmp.name, name)
        with open(pfad, "wb") as f:
            f.write(daten)
        return pfad

    # ── PNG ──────────────────────────────────────────────────────────────────

    def test_reiner_farbwechsel_je_kanal_ist_eine_aenderung(self):
        """Ein Viertel des Bildes wechselt die Farbe — in jedem Kanal einzeln."""
        alt = self._datei("alt.png", _png(_bild((0, 0, 0))))
        for name, farbe in (("Blau voll", (0, 0, 255)),
                            ("Blau halb", (0, 0, 128)),
                            ("Rot 150", (150, 0, 0)),
                            ("Gruen 80", (0, 80, 0))):
            with self.subTest(name):
                self.assertFalse(
                    self.runner.fast_gleich(alt, _png(_bild(farbe))),
                    f"{name}: Feld wechselt von Schwarz auf {farbe}, gilt aber "
                    f"als unveraendert")

    def test_farbwechsel_zwischen_zwei_farben(self):
        """Blau -> Violett aendert nur Rot um 150: sichtbar, frueher uebersehen."""
        alt = self._datei("alt.png", _png(_bild((0, 0, 255))))
        self.assertFalse(self.runner.fast_gleich(alt, _png(_bild((150, 0, 255)))))

    def test_kleine_abweichung_je_kanal_bleibt_unveraendert(self):
        """Wofuer es die Schwelle gibt: jeder Kanal weicht hoechstens um 48 ab."""
        alt = self._datei("alt.png", _png(_bild((100, 100, 100))))
        self.assertTrue(self.runner.fast_gleich(alt, _png(_bild((148, 52, 148)))))
        # ... ein Schritt darueber in EINEM Kanal ist eine Aenderung.
        self.assertFalse(self.runner.fast_gleich(alt, _png(_bild((149, 100, 100)))))
        self.assertFalse(self.runner.fast_gleich(alt, _png(_bild((100, 100, 149)))))

    def test_einzelne_pixel_bleiben_unveraendert(self):
        """Der gemessene Anlass der Toleranz: ein paar anders glimmende Pixel."""
        basis = _bild((0, 0, 0))
        alt = self._datei("alt.png", _png(basis))
        neu = basis.copy()
        for x in range(10):                      # 10 von 120000 < 0,05 %
            neu.putpixel((5 + x, 5), (0, 0, 255))
        self.assertTrue(self.runner.fast_gleich(alt, _png(neu)))
        for x in range(80):                      # 80 von 120000 > 0,05 %
            neu.putpixel((5 + x, 7), (0, 0, 255))
        self.assertFalse(self.runner.fast_gleich(alt, _png(neu)))

    def test_gleiches_bild_bleibt_gleich(self):
        daten = _png(_bild((0, 0, 255)))
        alt = self._datei("alt.png", daten)
        self.assertTrue(self.runner.fast_gleich(alt, daten))
        self.assertTrue(self.runner.ist_gleich(alt, daten))

    # ── GIF ──────────────────────────────────────────────────────────────────

    def _gif(self, farben) -> bytes:
        return self.runner.gif_bytes([_bild(f) for f in farben], [800] * len(farben))

    def test_gif_farbwechsel_in_einem_frame_ist_eine_aenderung(self):
        alt = self._datei("alt.gif", self._gif([(0, 0, 0), (255, 0, 0), (0, 0, 0)]))
        self.assertTrue(self.runner.gif_fast_gleich(
            alt, self._gif([(0, 0, 0), (255, 0, 0), (0, 0, 0)])))
        # Nur der LETZTE Frame aendert sich, und nur im Blau-Kanal.
        neu = self._gif([(0, 0, 0), (255, 0, 0), (0, 0, 255)])
        frames = self.runner.gif_frames(neu)
        self.assertEqual(frames[2][0].getpixel((200, 150)), (0, 0, 255))   # Vorbedingung
        self.assertFalse(self.runner.gif_fast_gleich(alt, neu),
                         "Frame 3 wechselt von Schwarz auf Blau, GIF gilt aber "
                         "als unveraendert")
        self.assertFalse(self.runner.ist_gleich(alt, neu))

    def test_gif_rot_150_ist_eine_aenderung(self):
        alt = self._datei("alt.gif", self._gif([(0, 0, 0), (0, 0, 0)]))
        self.assertFalse(self.runner.gif_fast_gleich(
            alt, self._gif([(0, 0, 0), (150, 0, 0)])))

    # ── Die Rechnung selbst ──────────────────────────────────────────────────

    def test_abweichende_pixel_zaehlt_den_groessten_kanal(self):
        a = _bild((0, 0, 0))
        flaeche = (FELD[2] - FELD[0]) * (FELD[3] - FELD[1])
        for farbe, erwartet in (((0, 0, 49), flaeche), ((0, 0, 48), 0),
                                ((49, 0, 0), flaeche), ((0, 49, 0), flaeche),
                                ((48, 48, 48), 0), ((20, 20, 49), flaeche)):
            with self.subTest(farbe=farbe):
                self.assertEqual(
                    self.runner.abweichende_pixel(a, _bild(farbe), 48), erwartet)


if __name__ == "__main__":
    unittest.main()

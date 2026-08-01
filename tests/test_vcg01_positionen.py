"""VCG-01: die Lichtkegel-Piktogramme zeigen wirklich, was ihr Name sagt.

David wollte „Lichtkegel-Gruppen, die Moving-Head-Positionen anzeigen". Ein
Taster „Mover auf Mitte" soll also auch wie „Mover auf Mitte" aussehen.

Diese Tests prüfen deshalb die **Bedeutung**, nicht die Mechanik. Dass eine
Datei existiert und im Manifest steht, sagt nichts darüber, ob das Bild die
richtige Formation zeigt — ein vertauschter Eintrag in der Zeichner-Tabelle
(``pos_links`` zeigt auf ``d_pos_rechts``) käme durch jeden Existenz-Test
glatt durch. Gemessen wird stattdessen am fertigen, committeten PNG:

* **Richtung** — der Schwerpunkt des Lichts am BODEN liegt links, rechts oder
  mittig, je nach Name.
* **Streuung** — Fächer streut mehr als Parallel, Parallel mehr als Mitte,
  Mitte mehr als Schmal. Genau diese Rangfolge macht die Piktogramme
  unterscheidbar; die ersten Entwürfe fielen hier durch (Fächer war von
  Parallel auf 64 px nicht zu trennen und wurde bewusst überzeichnet).
* **„Ins Publikum" trifft den Boden NICHT** — das ist die ganze Aussage des
  Bildes.
* **Helligkeit auf Tastergröße** — die GDS-3-Lehre: ein Bild kann technisch
  fehlerfrei und auf der Button-Face trotzdem tot sein. Damals lag das kranke
  GIF bei ~26/255 Mittel. Diese Untergrenze wird hier festgenagelt, damit
  niemand die Kegel später „dezenter" macht und sie damit unsichtbar.

Gelesen wird die ausgelieferte Datei, nicht frisch gerendert: geprüft gehört
das, was die App wirklich anzeigt.
"""
from __future__ import annotations

import os
import statistics
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.show import vc_gallery                                # noqa: E402

try:
    from PIL import Image
except Exception:                                                   # pragma: no cover
    Image = None

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.path.join(_ROOT, "assets", "vc_gallery")

STATISCH = ("pos_mitte", "pos_faecher", "pos_parallel", "pos_kreuz",
            "pos_links", "pos_rechts", "pos_schmal", "pos_publikum")
ANIMIERT = ("pos_sweep", "pos_faecher_atmen")

_HELL = 90          # ab hier gilt ein Pixel als beleuchtet
_BODEN = (0.80, 0.95)
_MITTE = (0.45, 0.72)


def _grau(name):
    return Image.open(os.path.join(_DIR, name + ".png")).convert("L")


def _leuchtende_x(bild, von, bis):
    """Normierte x-Positionen aller hellen Pixel im waagerechten Band."""
    w, h = bild.size
    px = bild.load()
    return [x / w for y in range(int(h * von), int(h * bis))
            for x in range(w) if px[x, y] > _HELL]


class ManifestTest(unittest.TestCase):
    def test_alle_positionen_sind_im_manifest(self):
        nach_name = {e["name"]: e for e in vc_gallery.entries()}
        for n in STATISCH + ANIMIERT:
            self.assertIn(n, nach_name, f"{n} fehlt in der Galerie")
            self.assertEqual(nach_name[n]["category"], "positionen")

    def test_dateien_liegen_wirklich_da(self):
        for e in vc_gallery.entries():
            if e.get("category") == "positionen":
                self.assertTrue(os.path.exists(os.path.join(_DIR, e["file"])),
                                f"{e['file']} fehlt auf der Platte")

    def test_kategorie_hat_einen_deutschen_reitertitel(self):
        from src.ui.virtualconsole.vc_gallery_dialog import _KAT_TITEL
        self.assertEqual(_KAT_TITEL.get("positionen"), "Positionen")


@unittest.skipIf(Image is None, "Pillow nicht verfuegbar")
class FormationTest(unittest.TestCase):
    """Zeigt das Bild dorthin, wo der Name es verspricht?"""

    def _schwerpunkt(self, name):
        xs = _leuchtende_x(_grau(name), *_BODEN)
        self.assertTrue(xs, f"{name}: am Boden kommt gar kein Licht an")
        return sum(xs) / len(xs)

    def test_links_beleuchtet_die_linke_haelfte(self):
        self.assertLess(self._schwerpunkt("pos_links"), 0.35)

    def test_rechts_beleuchtet_die_rechte_haelfte(self):
        self.assertGreater(self._schwerpunkt("pos_rechts"), 0.65)

    def test_links_und_rechts_sind_spiegelbilder(self):
        # Faellt auf, wenn jemand eine der beiden Zielreihen anfasst und die
        # andere vergisst — dann kippt die Symmetrie, ohne dass ein
        # Einzeltest rot wird.
        l, r = self._schwerpunkt("pos_links"), self._schwerpunkt("pos_rechts")
        self.assertAlmostEqual(l, 1.0 - r, delta=0.03)

    def test_symmetrische_formationen_liegen_mittig(self):
        for n in ("pos_mitte", "pos_faecher", "pos_parallel", "pos_kreuz",
                  "pos_schmal"):
            with self.subTest(n=n):
                self.assertAlmostEqual(self._schwerpunkt(n), 0.5, delta=0.06)

    def test_streuung_trennt_die_formationen(self):
        """Fächer > Parallel > Mitte > Schmal — sonst sehen sie gleich aus.

        Auf 64 px ist die Streuung das einzige Merkmal, das diese vier
        unterscheidet. Die erste Fassung erfüllte die Rangfolge NICHT
        (Fächer 0.33 gegen Parallel 0.23 war zu knapp, auf dem Taster nicht
        mehr trennbar) und wurde deshalb überzeichnet.
        """
        def streuung(n):
            return statistics.pstdev(_leuchtende_x(_grau(n), *_BODEN))

        f, p = streuung("pos_faecher"), streuung("pos_parallel")
        m, s = streuung("pos_mitte"), streuung("pos_schmal")
        self.assertGreater(f, p * 1.25, "Faecher streut nicht deutlich mehr als Parallel")
        self.assertGreater(p, m * 1.5, "Parallel streut nicht deutlich mehr als Mitte")
        self.assertGreater(m, s, "Mitte streut nicht mehr als Schmal")

    def test_publikum_trifft_den_boden_nicht(self):
        """Das ist die komplette Aussage des Bildes — nichts landet am Boden."""
        bild = _grau("pos_publikum")
        self.assertEqual(_leuchtende_x(bild, *_BODEN), [],
                         "Ins Publikum darf am Boden nichts beleuchten")
        self.assertGreater(len(_leuchtende_x(bild, *_MITTE)), 4000,
                           "ohne Blend-Flare in Bildmitte fehlt die Aussage")

    def test_jede_formation_ist_ein_eigenes_bild(self):
        """Zwei Namen auf denselben Zeichner zeigen zu lassen ist ein
        Tippfehler in der Registry-Tabelle, den man im Dialog kaum bemerkt."""
        gesehen = {}
        for n in STATISCH:
            roh = _grau(n).tobytes()
            self.assertNotIn(roh, gesehen,
                             f"{n} ist pixelgleich mit {gesehen.get(roh)}")
            gesehen[roh] = n


@unittest.skipIf(Image is None, "Pillow nicht verfuegbar")
class LesbarkeitTest(unittest.TestCase):
    """GDS-3: technisch fehlerfrei und auf der Button-Face trotzdem tot."""

    def test_auf_tastergroesse_bleibt_genug_licht_uebrig(self):
        for n in STATISCH:
            with self.subTest(n=n):
                klein = _grau(n).resize((64, 64), Image.LANCZOS).tobytes()
                mittel = sum(klein) / len(klein)
                anteil = sum(1 for v in klein if v > 60) / len(klein)
                # Untergrenzen mit Luft unter dem gemessenen Minimum
                # (pos_schmal: 31 bzw. 0.17) und ueber der GDS-3-Todeszone (26).
                self.assertGreater(mittel, 28,
                                   f"{n} ist auf 64 px zu dunkel ({mittel:.0f}/255)")
                self.assertGreater(anteil, 0.14,
                                   f"{n} hat auf 64 px zu wenig helle Flaeche")


@unittest.skipIf(Image is None, "Pillow nicht verfuegbar")
class AnimationTest(unittest.TestCase):
    def test_sweep_bewegt_sich_wirklich(self):
        """Ein GIF, dessen Frames alle gleich aussehen, ist ein teures PNG."""
        gif = Image.open(os.path.join(_DIR, "pos_sweep.gif"))
        schwer = []
        for k in (0, 5, 10, 15):
            gif.seek(k)
            xs = _leuchtende_x(gif.convert("L"), *_BODEN)
            if xs:
                schwer.append(sum(xs) / len(xs))
        self.assertGreater(max(schwer) - min(schwer), 0.15,
                           "der Sweep wandert kaum — auf dem Taster steht er still")

    def test_faecher_atmen_beginnt_geschlossen(self):
        """Frame 0 ist auch das Vorschaubild (GDS-3). Beginnt die Animation in
        der Mitte ihres Hubs, wirkt sie im Dialog beliebig."""
        gif = Image.open(os.path.join(_DIR, "pos_faecher_atmen.gif"))
        gif.seek(0)
        zu = statistics.pstdev(_leuchtende_x(gif.convert("L"), *_BODEN))
        gif.seek(10)
        auf = statistics.pstdev(_leuchtende_x(gif.convert("L"), *_BODEN))
        self.assertLess(zu, auf * 0.6,
                        "Frame 0 zeigt den Faecher nicht geschlossen")


if __name__ == "__main__":
    unittest.main()

"""DEMO-9: Die 2D-Bühne beschriftet Geräte mit ihrem Namen.

Befund (Demo-Show im Sandkasten): die Geräteliste nannte die Geräte „Wash 1",
„Spot 2", „LED-Leiste", die 2D-Bühne darunter „MH 9", „MH 12", „PARBAR 13" —
Typ-Kürzel + Gerätenummer. Das lag nicht am Demo-Bau, sondern an der Ansicht
(``live_view``: Steckbrief-Label = fid, Zeichner setzt das Kürzel davor) und
galt damit für JEDE Show.

Geprüft wird:

* ``buehnen_beschriftung``/``buehnen_beschriftungen``: Name aus dem Patch
  (Leerraum bereinigt, lange Namen gekürzt, eine Endnummer bleibt stehen),
  ohne Namen oder bei doppeltem Namen die Nummer;
* ``buehnen_label_waehlen``: ein Name, der nicht neben den Nachbarn passt,
  fällt auf Kürzel + Nummer zurück;
* ``FixtureRenderer.draw``: ein Name steht ohne Typ-Kürzel da, eine Nummer
  behält es (alte Aufrufer unverändert);
* die ganze Fläche (``StageCanvas``): freistehende Geräte zeigen ihren Namen,
  ein Gerät ohne Namen „MH <Nr>", dicht stehende Geräte (LOD 1) die Nummer;
* die Demo-Generatoren vergeben Funktionsnamen mit Umlaut („Laser Farbe grün",
  „MH Grün", „MH Weiß") statt ihrer ASCII-Schlüssel.
"""
from __future__ import annotations

import ast
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets

import src.ui.views.live_view as LV

_app = QApplication.instance() or QApplication([])
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _keine_widget_reste():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _fixture(fid, label, fixture_type="moving_head"):
    return SimpleNamespace(fid=fid, universe=1, address=fid * 20 + 1, label=label,
                           fixture_type=fixture_type, channel_count=8,
                           pan_range_deg=540, tilt_range_deg=270,
                           pan_zero_dmx=128, tilt_zero_dmx=128,
                           aim_offset_pan=0.0, aim_offset_tilt=0.0)


class _TextMerker(QPainter):
    """QPainter, der jeden gezeichneten Text mitschreibt."""

    def __init__(self, dev):
        super().__init__(dev)
        self.texte: list[str] = []

    def drawText(self, *args):          # noqa: N802 (Qt-Name)
        if args and isinstance(args[-1], str):
            self.texte.append(args[-1])
        return super().drawText(*args)


class BeschriftungTest(unittest.TestCase):

    def test_name_aus_dem_patch(self):
        self.assertEqual(LV.buehnen_beschriftung(_fixture(9, "Wash 1")), ("Wash 1", True))
        self.assertEqual(LV.buehnen_beschriftung(_fixture(13, "LED-Leiste")),
                         ("LED-Leiste", True))

    def test_leerraum_wird_bereinigt(self):
        self.assertEqual(LV.buehnen_beschriftung(_fixture(2, "  Spot \n 2 ")),
                         ("Spot 2", True))

    def test_ohne_namen_bleibt_die_nummer(self):
        for leer in ("", "   ", None):
            self.assertEqual(LV.buehnen_beschriftung(_fixture(7, leer)), ("7", False))

    def test_langer_name_wird_gekuerzt(self):
        name, ist_name = LV.buehnen_beschriftung(_fixture(1, "MH Live Beam 230 Spot links"))
        self.assertTrue(ist_name)
        self.assertEqual(len(name), LV.BUEHNEN_NAME_MAX)
        self.assertTrue(name.endswith("…"))
        self.assertTrue(name.startswith("MH Live Beam"))

    def test_langer_name_behaelt_die_endnummer(self):
        # Gegenpruefung: „<Profilname> <i>" (fixture_browser) wurde hinten
        # gekuerzt — die Nummer fiel weg, vier Geraete hiessen gleich.
        texte = [LV.buehnen_beschriftung(_fixture(i, f"Stairville MH-X50+ {i}"))
                 for i in (1, 2, 3, 4)]
        for i, (name, ist_name) in zip((1, 2, 3, 4), texte):
            self.assertTrue(ist_name)
            self.assertLessEqual(len(name), LV.BUEHNEN_NAME_MAX)
            self.assertTrue(name.endswith(f" {i}"), name)
            self.assertIn("…", name)
        self.assertEqual(len({t for t, _ in texte}), 4)
        self.assertEqual(LV.buehnen_beschriftung(_fixture(7, "Eurolite LED PAR-64 RGBA 12"))[0],
                         "Eurolite LED… 12")

    def test_doppelte_namen_fallen_auf_die_nummer_zurueck(self):
        # „Mit Offset kopieren" uebernimmt den Namen unveraendert.
        fx = [_fixture(5, "PAR"), _fixture(6, "PAR"), _fixture(7, " PAR "),
              _fixture(8, "Wash 1")]
        erg = LV.buehnen_beschriftungen(fx)
        self.assertEqual(erg, {5: ("5", False), 6: ("6", False), 7: ("7", False),
                               8: ("Wash 1", True)})

    def test_nach_dem_kuerzen_gleiche_namen_sind_doppelt(self):
        fx = [_fixture(1, "MH Live Beam 230 Spot links"),
              _fixture(2, "MH Live Beam 230 Spot rechts")]
        self.assertEqual(LV.buehnen_beschriftungen(fx), {1: ("1", False), 2: ("2", False)})


class LabelWahlTest(unittest.TestCase):
    """Gegenpruefung: ein Name, der breiter ist als der Abstand zum Nachbarn,
    lief bei LOD 0 (ab 48 px) in den Namen daneben (TextDontClip)."""

    SB = {"label": "Moving Head 12", "ist_name": True, "fid_text": "12",
          "name_breite": 80.0}

    def test_name_passt(self):
        self.assertEqual(LV.buehnen_label_waehlen(self.SB, 0, 200.0),
                         ("Moving Head 12", True))

    def test_name_zu_breit_faellt_auf_die_nummer(self):
        self.assertEqual(LV.buehnen_label_waehlen(self.SB, 0, 60.0), ("12", False))
        self.assertEqual(LV.buehnen_label_waehlen(self.SB, 0, 80.0), ("12", False))

    def test_lod1_immer_nummer(self):
        self.assertEqual(LV.buehnen_label_waehlen(self.SB, 1, 1e9), ("12", False))

    def test_ohne_namen_unveraendert(self):
        sb = {"label": "12", "ist_name": False, "fid_text": "12", "name_breite": 0.0}
        self.assertEqual(LV.buehnen_label_waehlen(sb, 0, 50.0), ("12", False))


class ZeichnerTest(unittest.TestCase):

    def _texte(self, label, *, ist_name=None, lod=0, typ="moving_head"):
        img = QImage(240, 140, QImage.Format.Format_ARGB32)
        img.fill(QColor("#0d1117"))
        p = _TextMerker(img)
        kw = {} if ist_name is None else {"ist_name": ist_name}
        try:
            LV.FixtureRenderer.draw(p, typ, 120, 60, 30, QColor("#ff8800"), 0, label,
                                    zoom=1.0, lod=lod, **kw)
        finally:
            p.end()                     # nie einen aktiven Painter liegen lassen
        return p.texte

    def test_name_ohne_typ_kuerzel(self):
        self.assertEqual(self._texte("Wash 1", ist_name=True), ["Wash 1"])
        self.assertEqual(self._texte("LED-Leiste", ist_name=True, typ="par_bar"),
                         ["LED-Leiste"])

    def test_nummer_behaelt_das_kuerzel(self):
        self.assertEqual(self._texte("9", ist_name=False), ["MH 9"])
        self.assertEqual(self._texte("13", typ="par_bar"), ["PARBAR 13"])  # alter Aufruf

    def test_lod1_zeigt_nur_das_label(self):
        self.assertEqual(self._texte("9", ist_name=False, lod=1), ["9"])


class FlaecheTest(unittest.TestCase):
    """Die ganze 2D-Fläche: was steht unter den Geräten?"""

    def _zeichne(self, fixtures, positionen):
        c = LV.StageCanvas()
        self.addCleanup(c.deleteLater)
        c.zoom = 1.0
        c._positions = dict(positionen)
        gezeichnet = {}

        # Nur mitschreiben, nicht zeichnen: was der Zeichner daraus macht,
        # prueft ZeichnerTest.
        def merken(painter, typ, x, y, size, color, intensity, label, **kw):
            gezeichnet[(round(x), round(y))] = (label, kw.get("ist_name", False),
                                                kw.get("lod", 0))

        with mock.patch.object(c._state, "get_patched_fixtures", return_value=fixtures), \
                mock.patch.object(LV, "get_channels_for_patched", return_value=[]), \
                mock.patch.object(LV.FixtureRenderer, "draw", staticmethod(merken)):
            c._steckbriefe.clear()
            c._compute_label_gaps()
            c.resize(1200, 800)
            c.grab()
        return {fid: gezeichnet.get((round(x), round(y)))
                for fid, (x, y) in positionen.items()}

    def test_freistehende_geraete_zeigen_ihren_namen(self):
        fx = [_fixture(9, "Wash 1"), _fixture(11, "Spot 1"),
              _fixture(13, "LED-Leiste", "par_bar"), _fixture(14, "")]
        pos = {9: (300.0, 250.0), 11: (600.0, 220.0), 13: (450.0, 600.0),
               14: (900.0, 250.0)}
        erg = self._zeichne(fx, pos)
        self.assertEqual(erg[9], ("Wash 1", True, 0))
        self.assertEqual(erg[11], ("Spot 1", True, 0))
        self.assertEqual(erg[13], ("LED-Leiste", True, 0))
        # ohne Namen: Nummer, der Zeichner setzt das Typ-Kuerzel davor
        self.assertEqual(erg[14], ("14", False, 0))

    def test_dicht_stehende_geraete_zeigen_die_nummer(self):
        fx = [_fixture(1, "Wash links"), _fixture(2, "Wash rechts")]
        # 30 px Abstand -> LOD 1 (22 <= gap < 48)
        erg = self._zeichne(fx, {1: (400.0, 300.0), 2: (430.0, 300.0)})
        self.assertEqual(erg[1], ("1", False, 1))
        self.assertEqual(erg[2], ("2", False, 1))

    def test_kopien_mit_gleichem_namen_zeigen_die_nummer(self):
        fx = [_fixture(5, "PAR", "par"), _fixture(6, "PAR", "par"),
              _fixture(7, "PAR", "par"), _fixture(8, "Wash 1")]
        pos = {5: (200.0, 200.0), 6: (450.0, 200.0), 7: (700.0, 200.0),
               8: (950.0, 200.0)}
        erg = self._zeichne(fx, pos)
        self.assertEqual(erg[5], ("5", False, 0))
        self.assertEqual(erg[6], ("6", False, 0))
        self.assertEqual(erg[7], ("7", False, 0))
        self.assertEqual(erg[8], ("Wash 1", True, 0))

    def test_breiter_name_bei_engem_abstand_zeigt_kuerzel_und_nummer(self):
        fx = [_fixture(11, "Moving Head 11"), _fixture(12, "Moving Head 12")]
        # 55 px: LOD 0, aber „Moving Head 11" ist rund 80 px breit
        erg = self._zeichne(fx, {11: (400.0, 300.0), 12: (455.0, 300.0)})
        self.assertEqual(erg[11], ("11", False, 0))
        self.assertEqual(erg[12], ("12", False, 0))
        # weit genug auseinander: der Name
        erg = self._zeichne(fx, {11: (300.0, 300.0), 12: (600.0, 300.0)})
        self.assertEqual(erg[11], ("Moving Head 11", True, 0))


def _quelle(generator: str) -> str:
    """Quelltext eines Generators — gelesen, nicht gestartet (das Bauen und
    Laden pruefen test_showcase_club / test_demo8_demoshows)."""
    with open(os.path.join(_REPO, "tools", generator), encoding="utf-8") as f:
        return f.read()


class GeneratorNamenTest(unittest.TestCase):

    def _modul_konstanten(self, generator):
        baum = ast.parse(_quelle(generator))
        werte = {}
        for knoten in baum.body:
            if (isinstance(knoten, ast.Assign) and len(knoten.targets) == 1
                    and isinstance(knoten.targets[0], ast.Name)):
                try:
                    werte[knoten.targets[0].id] = ast.literal_eval(knoten.value)
                except ValueError:
                    pass
        return werte

    def _schleifen_namen(self, generator, vorlage, schluessel_konst, namen_konst):
        k = self._modul_konstanten(generator)
        quelle = _quelle(generator)
        self.assertIn(vorlage, quelle, f"{generator}: Namensbildung nicht gefunden")
        namen = k[namen_konst]
        return {s: namen.get(s, s) for s in k[schluessel_konst]}

    def test_laser_farben_mit_umlaut(self):
        for gen in ("build_showcase_club.py", "build_buehnen_show_2026.py"):
            namen = self._schleifen_namen(
                gen, 'b.scene(f"Laser Farbe {LASER_FARBNAME.get(farbe, farbe)}")',
                "LASER_FARBE", "LASER_FARBNAME")
            self.assertEqual(namen["gruen"], "grün", gen)
            for anzeige in namen.values():
                self.assertNotIn("ue", anzeige, gen)

    def test_mega_arena_mh_farben_mit_umlaut(self):
        k = self._modul_konstanten("build_mega_arena_2026.py")
        quelle = _quelle("build_mega_arena_2026.py")
        self.assertIn('f"MH {MH_FARBNAME.get(nm, nm.capitalize())}"', quelle)
        namen = {nm: k["MH_FARBNAME"].get(nm, nm.capitalize()) for nm in k["MHCOL"]}
        self.assertEqual(namen["gruen"], "Grün")
        self.assertEqual(namen["weiss"], "Weiß")


if __name__ == "__main__":
    unittest.main()

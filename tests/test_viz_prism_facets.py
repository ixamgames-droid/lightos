"""VIZ-PRISMA-3D, Python-Haelfte: DMX-Wert -> Range -> Facettenzahl.

Die Zuordnung wird bewusst HIER aufgeloest und nicht in JS (dieselbe Regel wie
bei VIZ-GOBO-3D): die Ranges leben im Profil, also darf es nur EINE Stelle
geben, die sie liest. Nach JS wandert die fertige Zahl.

Der wichtigste Fall in dieser Datei ist die ZWEISPRACHIGKEIT: die eingebauten
Profile schreiben deutsch ("6-fach Prisma"), die importierten QXF-Profile
englisch ("3 Facet Prism"). Ausgezaehlt ueber die Library sind 93 % der
Prisma-Ranges englisch benannt oder nennen gar keine Zahl — ein Muster fuer nur
eine Sprache haette die stillschweigend als "kein Prisma" behandelt.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.visualizer.visualizer_service import (
    _prism_facets, PRISM_FACETTEN_FALLBACK)


def _range(von, bis, name):
    return SimpleNamespace(range_from=von, range_to=bis, name=name)


def _kanal(attribut, ranges=()):
    return SimpleNamespace(attribute=attribut, ranges=list(ranges))


class PrismFacetsTest(unittest.TestCase):
    def test_geraet_ohne_prisma_kanal_bekommt_keinen_schluessel(self):
        """``None`` heisst "hat gar kein Prisma" — dann steht nichts im Payload
        und JS laesst den Strahl in Ruhe. Ein erfundener Default waere hier
        dieselbe Falle wie der erfundene 128er-Zoom (VIZ-MH-OPTICS)."""
        kanaele = [_kanal("dimmer"), _kanal("gobo_wheel")]
        self.assertIsNone(_prism_facets({"dimmer": 255}, kanaele))

    def test_ohne_kanalliste_keine_aussage(self):
        self.assertIsNone(_prism_facets({"prism": 200}, None))

    def test_kanal_da_aber_kein_wert_im_batch(self):
        """Der Service schickt differentiell — fehlt `prism` im Batch, gibt es
        nichts zu melden (nicht etwa "aus")."""
        kanaele = [_kanal("prism", [_range(0, 10, "Aus")])]
        self.assertIsNone(_prism_facets({"dimmer": 255}, kanaele))

    def test_deutsche_schreibweise(self):
        kanaele = [_kanal("prism", [
            _range(0, 19, "Aus"),
            _range(20, 75, "6-fach Prisma (Index/Rot)"),
            _range(76, 127, "8-fach Prisma (Index/Rot)"),
        ])]
        self.assertEqual(_prism_facets({"prism": 50}, kanaele), 6)
        self.assertEqual(_prism_facets({"prism": 100}, kanaele), 8)

    def test_englische_schreibweise_der_qxf_profile(self):
        """93 % der Library kommt so daher — ohne diesen Zweig waere das
        Feature fuer fast alle importierten Geraete unsichtbar."""
        kanaele = [_kanal("prism", [
            _range(0, 9, "Open"),
            _range(10, 100, "3 Facet Prism"),
            _range(101, 200, "8-facet prism"),
            _range(201, 255, "4 Facet Prism Insertion"),
        ])]
        self.assertEqual(_prism_facets({"prism": 50}, kanaele), 3)
        self.assertEqual(_prism_facets({"prism": 150}, kanaele), 8)
        self.assertEqual(_prism_facets({"prism": 220}, kanaele), 4)

    def test_aus_ranges_quer_durch_die_library(self):
        for name in ("Aus", "Off", "Open", "offen", "kein Prisma",
                     "No Prism", "None", "Blank"):
            kanaele = [_kanal("prism", [_range(0, 255, name)])]
            self.assertEqual(_prism_facets({"prism": 128}, kanaele), 0,
                             f"{name!r} muss als AUS gelten")

    def test_range_ohne_zahl_bekommt_den_ausgezaehlten_fallback(self):
        """Der haeufigste Fall der ganzen Library: die Range sagt nur "Prism".
        Dann gilt 3 — nicht geraten, sondern die haeufigste Angabe unter den
        Profilen, die ueberhaupt eine machen (25 von 49)."""
        kanaele = [_kanal("prism", [_range(0, 9, "Open"),
                                    _range(10, 255, "Prism")])]
        self.assertEqual(_prism_facets({"prism": 128}, kanaele),
                         PRISM_FACETTEN_FALLBACK)

    def test_makro_nummern_werden_nicht_als_facetten_gelesen(self):
        """"Prisma-Makros 1–16" nennt eine MAKRO-Nummer, keine Facettenzahl.
        16 Kegel je Geraet waeren ein echter Renderschaden — und gemeint ist
        ohnehin etwas anderes."""
        kanaele = [_kanal("prism", [_range(0, 255, "Prisma-Makros 1–16")])]
        self.assertEqual(_prism_facets({"prism": 200}, kanaele),
                         PRISM_FACETTEN_FALLBACK)

    def test_prism_rotation_zaehlt_nicht_als_prisma_kanal(self):
        """Die Drehung sagt nichts ueber die Facettenzahl. Wer sie mitliest,
        holt sich die Zahl aus dem falschen Kanal."""
        kanaele = [_kanal("prism_rotation", [_range(0, 255, "8 Facet Rotation")])]
        self.assertIsNone(_prism_facets({"prism_rotation": 200}, kanaele))

    def test_ohne_passende_range_entscheidet_der_wert(self):
        """Kein Range-Treffer (oder gar keine Ranges): Default 0 = aus ist in
        der Library einhellig, alles darueber heisst "steckt drin"."""
        kanaele = [_kanal("prism", [])]
        self.assertEqual(_prism_facets({"prism": 0}, kanaele), 0)
        self.assertEqual(_prism_facets({"prism": 200}, kanaele),
                         PRISM_FACETTEN_FALLBACK)

    def test_unsinniger_wert_wirft_nicht(self):
        kanaele = [_kanal("prism", [_range(0, 255, "Prism")])]
        self.assertIsNone(_prism_facets({"prism": None}, kanaele))
        self.assertIsNone(_prism_facets({"prism": "abc"}, kanaele))


class PrismPayloadTest(unittest.TestCase):
    """Die Zahl muss auch wirklich im Payload landen — und die Drehung roh
    daneben, weil es dort keine Profil-Zuordnung aufzuloesen gibt."""

    def _payload(self, attrs, kanaele):
        from src.ui.visualizer.visualizer_service import _build_fixture_payload
        fix = SimpleNamespace(id=1, fid=1, name="MH", fixture_type="moving_head",
                              universe=1, address=1, channels=list(kanaele))
        return _build_fixture_payload(fix, attrs, kanaele)

    def test_prisma_und_drehung_im_payload(self):
        kanaele = [_kanal("prism", [_range(0, 9, "Open"),
                                    _range(10, 255, "8 Facet Prism")]),
                   _kanal("prism_rotation", [])]
        p = self._payload({"prism": 128, "prism_rotation": 64}, kanaele)
        self.assertEqual(p.get("prism"), 8)
        self.assertEqual(p.get("prism_rotation"), 64)

    def test_ohne_prisma_kanal_steht_nichts_drin(self):
        p = self._payload({"dimmer": 255}, [_kanal("dimmer")])
        self.assertNotIn("prism", p)
        self.assertNotIn("prism_rotation", p)


if __name__ == "__main__":
    unittest.main()

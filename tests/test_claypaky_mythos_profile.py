"""FM-15 — Clay Paky Mythos (Beam/Spot-Hybrid, Standard 30ch).

Chart DOPPELT verifiziert und maschinell gegenuebergestellt:

* Clay-Paky-Handbuch „MYTHOS C61391" (Kanaltabelle Standard/Vector plus die
  Wertebereiche je Kanal),
* QLC+-Definition ``Clay_Paky/Clay-Paky-Mythos.qxf``.

Beide nennen fuer den Standard-Modus **dieselben 30 Kanaele in derselben
Reihenfolge**. Die Reihenfolge unten ist aus dieser Gegenueberstellung
abgeschrieben — sie ist der eigentliche Pruefgegenstand, denn ein verrutschtes
Chart erzeugt spaeter Programmier-Fehler, die niemand mehr dem Profil zuordnet.

**Warum das Geraet:** Die Library kannte bisher kein Profil mit DREI getrennten
Farbraedern. Und sie belegt die FM-15-Feature-Liste weiter — mit einer Ausnahme,
die hier ausdruecklich festgehalten wird: **eine Iris hat der Mythos nicht.**
Das war meine Ausgangsannahme bei der Geraetewahl, und die Kanaltabelle hat sie
widerlegt; ein erfundener Iris-Kanal waere genau die Sorte Fehler, gegen die die
Doppelverifikation existiert.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from _fixture_quelle import frische_library                        # noqa: E402
from src.core.database.models import (ChannelRange, FixtureChannel,  # noqa: E402
                                      FixtureMode, FixtureProfile)

# (Kanalnummer, Name im Handbuch, erwartetes LightOS-Attribut)
_CHART = [
    (1,  "CYAN COLOUR WHEEL",        "cmy_c"),
    (2,  "MAGENTA COLOUR WHEEL",     "cmy_m"),
    (3,  "YELLOW COLOUR WHEEL",      "cmy_y"),
    (4,  "COLOUR 1",                 "color_wheel"),
    (5,  "COLOUR 2",                 "raw"),
    (6,  "COLOUR 3",                 "raw"),
    (7,  "STOPPER / STROBE",         "shutter"),
    (8,  "DIMMER",                   "intensity"),
    (9,  "DIMMER FINE",              "raw"),
    (10, "STATIC GOBO CHANGE",       "gobo_wheel"),
    (11, "ANIMATION DISK INSERTION", "animation"),
    (12, "ANIMATION DISK ROTATION",  "raw"),
    (13, "ROTATING GOBO SELECT",     "gobo_wheel2"),
    (14, "GOBO ROTATION",            "gobo_rotation"),
    (15, "FINE GOBO ROTATION",       "raw"),
    (16, "PRISMS INSERTION",         "prism"),
    (17, "PRISMS ROTATION",          "prism_rotation"),
    (18, "FROST",                    "frost"),
    (19, "ZOOM",                     "zoom"),
    (20, "FOCUS",                    "focus"),
    (21, "FOCUS FINE",               "raw"),
    (22, "BEAM MODE",                "macro"),
    (23, "PAN",                      "pan"),
    (24, "FINE PAN",                 "pan_fine"),
    (25, "TILT",                     "tilt"),
    (26, "FINE TILT",                "tilt_fine"),
    (27, "FUNCTION",                 "raw"),
    (28, "RESET",                    "reset"),
    (29, "LAMP CONTROL",             "lamp"),
    (30, "MACRO EFFECTS",            "raw"),
]


class MythosProfileTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # ★ Frisch aus dem QUELLTEXT geseedet. Vorher las dieser Test die
        # abgelegte fixtures.db und war damit blind: die Mutation
        # „Zoomkanal zoom -> raw" liess ihn 12/12 gruen. Begruendung und
        # Messung in tests/_fixture_quelle.py.
        cls._eng = frische_library(cls)

    def setUp(self):
        self.s = Session(self._eng)
        self.addCleanup(self.s.close)
        self.profil = self.s.execute(select(FixtureProfile).where(
            FixtureProfile.short_name == "MYTHOS")).scalars().first()
        self.assertIsNotNone(self.profil, "Builtin MYTHOS fehlt")
        self.modus = self.s.execute(select(FixtureMode).where(
            FixtureMode.fixture_id == self.profil.id)).scalars().first()

    def _kanaele(self):
        return self.s.execute(
            select(FixtureChannel).where(FixtureChannel.mode_id == self.modus.id)
            .order_by(FixtureChannel.channel_number)).scalars().all()

    def _bereiche(self, kanalnummer: int):
        ch = self._kanaele()[kanalnummer - 1]
        return self.s.execute(select(ChannelRange).where(
            ChannelRange.channel_id == ch.id)
            .order_by(ChannelRange.range_from)).scalars().all()

    # ── Chart ────────────────────────────────────────────────────────────────

    def test_standard_modus_hat_dreissig_kanaele(self):
        self.assertEqual(self.modus.name, "30-Kanal (Standard)")
        self.assertEqual(self.modus.channel_count, 30)
        self.assertEqual(len(self._kanaele()), 30)

    def test_jeder_kanal_traegt_das_attribut_aus_dem_chart(self):
        kanaele = self._kanaele()
        for nummer, handbuch, attribut in _CHART:
            with self.subTest(kanal=nummer, handbuch=handbuch):
                ch = kanaele[nummer - 1]
                self.assertEqual(ch.channel_number, nummer)
                self.assertEqual(
                    ch.attribute, attribut,
                    f"Kanal {nummer} ({handbuch}) muss {attribut!r} sein")

    def test_geraet_ist_ein_moving_head_ohne_zweite_farbbank(self):
        """Single-Head: kein ``color_r`` -> keine Fehl-Erkennung als Spider
        (die Klasse haengt an der Zahl der Farbbaenke, s. is_spider_fixture)."""
        self.assertEqual(self.profil.fixture_type, "moving_head")
        self.assertNotIn("color_r", [c.attribute for c in self._kanaele()])

    def test_genau_ein_kanonisches_farbrad(self):
        """Drei Raeder im Geraet, aber nur EINES traegt die Farb-Aussage.

        Zwei ``color_wheel``-Kanaele waeren eine stille Zweitquelle fuer „welche
        Farbe hat das Geraet" — Programmer und Visualizer lesen das erste.
        """
        attrs = [c.attribute for c in self._kanaele()]
        self.assertEqual(attrs.count("color_wheel"), 1)

    def test_keine_iris(self):
        """Ausdruecklich festgehalten: die Kanaltabelle des Handbuchs hat keine.

        Der Test verhindert, dass jemand sie spaeter „nachtraegt", weil die
        Geraeteklasse eine vermuten laesst.
        """
        self.assertNotIn("iris", [c.attribute for c in self._kanaele()])

    # ── Safety-Defaults ──────────────────────────────────────────────────────

    def test_dimmer_startet_dunkel(self):
        self.assertEqual(self._kanaele()[7].default_value, 0)

    def test_shutter_default_liegt_in_einem_offenen_band(self):
        """Nicht „irgendein Wert, den ich fuer offen halte": der Default muss in
        einem Bereich liegen, den das Handbuch als „Licht AN" fuehrt."""
        default = self._kanaele()[6].default_value
        offen = [(r.range_from, r.range_to) for r in self._bereiche(7)
                 if (r.kind or "") == "open"]
        self.assertTrue(offen, "Vorbedingung: es gibt offene Baender")
        self.assertTrue(any(von <= default <= bis for von, bis in offen),
                        f"Shutter-Default {default} liegt in keinem offenen Band {offen}")

    def test_lampe_und_reset_starten_ohne_funktion(self):
        """0 darf NICHT die Lampe ausschalten — „Lampe AUS" beginnt laut
        Handbuch erst bei 26, 0-25 ist der Leerbereich."""
        for nummer in (28, 29):        # Reset, Lampensteuerung
            with self.subTest(kanal=nummer):
                self.assertEqual(self._kanaele()[nummer - 1].default_value, 0)
        leer = [r for r in self._bereiche(29)
                if r.range_from == 0 and r.range_to >= 25]
        self.assertTrue(leer, "0 muss im Leerbereich der Lampensteuerung liegen")

    def test_pan_tilt_starten_mittig(self):
        for nummer in (23, 25):
            with self.subTest(kanal=nummer):
                self.assertEqual(self._kanaele()[nummer - 1].default_value, 128)

    # ── Wertebereiche gegen das Handbuch ─────────────────────────────────────

    def test_shutter_baender_stimmen_mit_dem_handbuch(self):
        erwartet = [(0, 3, "closed"), (4, 103, "strobe"), (104, 107, "open"),
                    (108, 207, "strobe"), (208, 212, "open"),
                    (213, 225, "strobe"), (226, 238, "strobe"),
                    (239, 251, "strobe"), (252, 255, "open")]
        ist = [(r.range_from, r.range_to, r.kind or "") for r in self._bereiche(7)]
        self.assertEqual(ist, erwartet)

    def test_prisma_hat_zwei_prismen_und_eine_aus_stellung(self):
        ist = [(r.range_from, r.range_to, r.kind or "") for r in self._bereiche(16)]
        self.assertEqual(ist, [(0, 10, "open"), (11, 132, "prism"),
                               (133, 255, "prism")])

    def test_farbrad_1_beginnt_offen(self):
        erste = self._bereiche(4)[0]
        self.assertEqual((erste.range_from, erste.range_to, erste.kind),
                         (0, 0, "open"))


if __name__ == "__main__":
    unittest.main()

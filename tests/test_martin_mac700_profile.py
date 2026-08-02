"""FM-15 — Martin MAC 700 Profile (CMY-Spot, 16-bit Basic 23ch).

Chart DOPPELT verifiziert und maschinell gegenuebergestellt:

* Martin-Handbuch „MAC 700 Profile", Anhang **DMX protocol** (Spalte „16-bit
  Basic Mode" plus die Wertebereiche je Kanal),
* QLC+-Definition ``Martin/Martin-MAC-700-Profile.qxf``, Modus
  ``16-bit Basic``.

Beide nennen **dieselben 23 Kanaele in derselben Reihenfolge**, 23/23. Die
Reihenfolge unten ist aus dieser Gegenueberstellung abgeschrieben — sie ist der
eigentliche Pruefgegenstand, denn ein verrutschtes Chart erzeugt spaeter
Programmier-Fehler, die niemand mehr dem Profil zuordnet.

**Warum GERADE dieses Geraet — gemessen, nicht ausgesucht:** ueber alle Builtins
ausgezaehlt, welches Attribut der FM-15-Feature-Liste (zoom/focus/frost/iris/
prism/prism_rotation/gobo_rotation/gobo_wheel/animation) noch **kein** eingebautes
Geraet benutzt. Ergebnis: genau eines, **`iris`** — 0 Nennungen. Der Regler
existierte im Programmer und in der Simple-Desk-Farbtabelle, konnte aber an
keinem eingebauten Geraet etwas bewirken. Der MAC 700 Profile fuehrt laut
Martin-Datenblatt eine **„Motorized iris"** und traegt sie auf Kanal 15.

Die vorige Runde (Clay Paky Mythos) hatte dieselbe Luecke schliessen wollen und
scheiterte daran, dass der Mythos real gar keine Iris hat. Deshalb steht hier
ausdruecklich ein Test, der die Iris am ECHTEN Kanal festnagelt — und einer, der
belegt, dass sie damit auch wirklich die letzte Luecke war.

**Bewusst kein Framing-Shutter-Geraet** (z. B. MAC Viper): das braeuchte neues
Vokabular (vier Blenden mit je Position und Winkel) und gehoert in eine eigene
Runde. Diese hier schliesst genau eine Luecke.

**Gewaehlt ist der 16-bit-BASIC-Modus (23ch).** Der Extended-Modus (31ch) fuegt
ausschliesslich Fine-Kanaele hinzu — als Builtin waeren das acht weitere
`raw`-Regler ohne eigene Wirkung.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

from sqlalchemy import create_engine                                # noqa: E402

from src.core.attr_groups import ATTR_GROUPS                        # noqa: E402
from src.core.database import fixture_db as fdb                     # noqa: E402
from src.core.database.models import (Base, ChannelRange,           # noqa: E402
                                      FixtureChannel, FixtureMode,
                                      FixtureProfile)

# (Kanalnummer, Name im Handbuch / QLC+, erwartetes LightOS-Attribut)
_CHART = [
    (1,  "Shutter, strobe, reset, lamp",   "shutter"),
    (2,  "Dimmer (MSB)",                   "intensity"),
    (3,  "Cyan (MSB)",                     "cmy_c"),
    (4,  "Magenta (MSB)",                  "cmy_m"),
    (5,  "Yellow (MSB)",                   "cmy_y"),
    (6,  "Color wheel (MSB)",              "color_wheel"),
    (7,  "Gobo wheel 1 (rotating)",        "gobo_wheel"),
    (8,  "Rotating gobo: indexing, speed", "gobo_rotation"),
    (9,  "Rotating gobo, fine indexing",   "raw"),
    (10, "Gobo wheel 2 (static)",          "gobo_wheel2"),
    (11, "Gobo/color macros, random CMY",  "macro"),
    (12, "Gobo animation wheel",           "animation"),
    (13, "Gobo animation wheel rotation",  "raw"),
    (14, "Prism",                          "prism"),
    (15, "Iris (MSB)",                     "iris"),
    (16, "Focus (MSB)",                    "focus"),
    (17, "Zoom (MSB)",                     "zoom"),
    (18, "Pan (MSB)",                      "pan"),
    (19, "Pan, fine (LSB)",                "pan_fine"),
    (20, "Tilt (MSB)",                     "tilt"),
    (21, "Tilt, fine (LSB)",               "tilt_fine"),
    (22, "Pan/tilt speed",                 "speed"),
    (23, "Effects speed",                  "effect_speed"),
]


class Mac700ProfileTest(unittest.TestCase):
    """★ Baut die Library FRISCH im Arbeitsspeicher, statt die abgelegte
    ``fixtures.db`` zu lesen.

    Das ist keine Kosmetik. Die erste Fassung dieses Tests las die persistente
    DB — und blieb bei **jeder** Mutation gruen: Iris-Kanal entfernt, Default
    auf geschlossen, Luecke in der Bereichstabelle, Shutter-Default auf 0,
    Zoom/Fokus vertauscht. Grund: ``ensure_builtins`` legt ein Builtin nur an,
    wenn sein ``short_name`` **fehlt**; steht es schon in der Datei, wird die
    Quelle nie wieder angesehen. Der Test prueft dann den Stand von gestern.

    Gegen eine leere DB (also in der CI) waere er echt gewesen — auf jedem
    Entwicklerrechner, der das Profil einmal geschrieben hat, nicht mehr. Ein
    Gate, das nur auf fremder Hardware greift, ist genau dort blind, wo man es
    braucht: beim Aendern.
    """

    def setUp(self):
        motor = create_engine("sqlite://")       # eigene, leere In-Memory-DB
        Base.metadata.create_all(motor)
        self.s = Session(motor)
        self.addCleanup(self.s.close)
        fdb._add_martin_mac700_profile(
            self.s, fdb._get_or_create_mfr(self.s, "Martin", "MARTIN"))
        self.s.flush()
        self.profil = self.s.execute(select(FixtureProfile).where(
            FixtureProfile.short_name == "MAC700P")).scalars().first()
        self.assertIsNotNone(self.profil, "Builtin MAC700P fehlt")
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

    def test_basic_modus_hat_dreiundzwanzig_kanaele(self):
        self.assertEqual(self.modus.name, "23-Kanal (16-bit Basic)")
        self.assertEqual(self.modus.channel_count, 23)
        self.assertEqual(len(self._kanaele()), 23)

    def test_jeder_kanal_traegt_das_attribut_aus_dem_chart(self):
        kanaele = self._kanaele()
        for nummer, handbuch, attribut in _CHART:
            with self.subTest(kanal=nummer, handbuch=handbuch):
                ch = kanaele[nummer - 1]
                self.assertEqual(ch.channel_number, nummer)
                self.assertEqual(
                    ch.attribute, attribut,
                    f"Kanal {nummer} ({handbuch}) muss {attribut!r} sein")

    # ── Die Iris — der Grund fuer dieses Geraet ──────────────────────────────

    def test_die_iris_sitzt_auf_kanal_fuenfzehn(self):
        kanaele = self._kanaele()
        iris = [c for c in kanaele if c.attribute == "iris"]
        self.assertEqual(len(iris), 1, "genau EIN Iris-Kanal erwartet")
        self.assertEqual(iris[0].channel_number, 15,
                         "Handbuch und QLC+ nennen beide Kanal 15 (Basic)")

    def test_iris_default_ist_offen(self):
        """Ein Geraet, das mit halb geschlossener Iris hochkommt, sieht kaputt
        aus — und zwar auf eine Art, die niemand beim Profil sucht.

        Geprueft wird nicht der Zahlenwert, sondern dass er in einem als
        ``open`` DEKLARIERTEN Band liegt. Sonst prueft der Test meine Meinung
        statt das Profil.
        """
        ch = self._kanaele()[14]
        self.assertEqual(ch.attribute, "iris")
        baender = [b for b in self._bereiche(15) if b.kind == "open"]
        self.assertTrue(baender, "kein als offen deklariertes Iris-Band")
        self.assertTrue(
            any(b.range_from <= ch.default_value <= b.range_to for b in baender),
            f"Iris-Default {ch.default_value} liegt in keinem offenen Band")

    def test_iris_ist_im_programmer_erreichbar(self):
        """Ein Kanal mit einem Attribut, das keine Gruppe kennt, taucht im
        Programmer nicht auf — das Geraet haette die Iris dann nur auf dem
        Papier."""
        gruppen = [g for g, attrs in ATTR_GROUPS.items() if "iris" in attrs]
        self.assertEqual(gruppen, ["Beam"],
                         f"'iris' gehoert in genau eine Gruppe, ist aber in {gruppen}")

    def test_schliesst_die_letzte_fm15_luecke(self):
        """Gegenprobe zur Geraetewahl: NACH dieser Runde darf kein Attribut der
        FM-15-Liste mehr ohne Builtin dastehen.

        Gemessen an der GANZEN frisch geseedeten Library, nicht an diesem einen
        Profil — sonst belegt der Test nur, dass ich eine Iris eingebaut habe,
        nicht dass sie die fehlende war. (Der MAC 700 hat selbst weder Frost
        noch Prisma-Rotation; die kommen von anderen Builtins.)
        """
        motor = create_engine("sqlite://")
        Base.metadata.create_all(motor)
        with Session(motor) as voll:
            fdb._seed(voll)
            voll.flush()
            vorhanden = set(voll.execute(
                select(FixtureChannel.attribute).distinct()).scalars().all())
        gesucht = {"zoom", "focus", "frost", "iris", "prism", "prism_rotation",
                   "gobo_rotation", "gobo_wheel", "animation"}
        fehlen = sorted(gesucht - vorhanden)
        self.assertEqual(fehlen, [],
                         f"FM-15-Attribute weiterhin ohne Builtin: {fehlen}")

    # ── Klasse, Routing, Safety ─────────────────────────────────────────────

    def test_geraet_ist_ein_moving_head_ohne_zweite_farbbank(self):
        """Single-Head: kein ``color_r`` -> keine Fehl-Erkennung als Spider
        (die Klasse haengt an der Zahl der Farbbaenke, s. is_spider_fixture)."""
        self.assertEqual(self.profil.fixture_type, "moving_head")
        attrs = [c.attribute for c in self._kanaele()]
        self.assertNotIn("color_r", attrs)
        self.assertEqual(attrs.count("pan"), 1)
        self.assertEqual(attrs.count("tilt"), 1)

    def test_genau_ein_kanonisches_farbrad(self):
        attrs = [c.attribute for c in self._kanaele()]
        self.assertEqual(attrs.count("color_wheel"), 1)

    def test_shutter_default_liegt_im_offenen_band_und_nicht_bei_null(self):
        """0-19 faehrt die Lampe nach 10 s in den 400-W-Modus — ein Default
        dort waere ein Geraet, das von selbst dunkler wird."""
        ch = self._kanaele()[0]
        self.assertEqual(ch.attribute, "shutter")
        self.assertGreater(ch.default_value, 19)
        offen = [b for b in self._bereiche(1) if b.kind == "open"]
        self.assertTrue(
            any(b.range_from <= ch.default_value <= b.range_to for b in offen),
            f"Shutter-Default {ch.default_value} liegt in keinem offenen Band")

    def test_dimmer_startet_dunkel(self):
        ch = self._kanaele()[1]
        self.assertEqual(ch.attribute, "intensity")
        self.assertEqual(ch.default_value, 0)

    def test_lampe_aus_liegt_nicht_auf_dem_default(self):
        """Der Shutter-Kanal traegt auch Lampe-AUS (248-255). Ein Default in
        dessen Naehe waere ein Geraet, das beim Patchen die Lampe loescht."""
        ch = self._kanaele()[0]
        self.assertLess(ch.default_value, 248)

    def test_name_und_kind_eines_bandes_widersprechen_sich_nicht(self):
        """Ein Band, das „Geschlossen" heisst und als ``open`` deklariert ist,
        ist ein stiller Widerspruch: Menschen lesen den Namen, der Code liest
        ``kind``.

        Aufgefallen ist die Luecke beim Mutationstest — den Default-Test
        taeuscht so eine Falschdeklaration nicht, weil der Default ohnehin in
        einem echten offenen Band liegt. Genau deshalb steht sie hier.
        """
        zu = ("geschlossen", "closed", "licht aus", "lampe aus")
        auf = ("offen", "open", "licht an")
        for nummer, handbuch, _a in _CHART:
            for b in self._bereiche(nummer):
                name = b.name.lower()
                nennt_zu = any(w in name for w in zu)
                nennt_auf = any(w in name for w in auf)
                # „Offen → geschlossen" ist ein VERLAUF und nennt beides zu
                # Recht. Nur die eindeutigen Faelle sind pruefbar.
                if nennt_zu == nennt_auf:
                    continue
                with self.subTest(kanal=nummer, band=b.name):
                    erwartet_nicht = "open" if nennt_zu else "closed"
                    self.assertNotEqual(
                        b.kind, erwartet_nicht,
                        f"Kanal {nummer} ({handbuch}): Band {b.name!r} "
                        f"widerspricht seiner Deklaration {b.kind!r}")

    def test_bereiche_sind_lueckenlos_und_ueberschneidungsfrei(self):
        """Ein verrutschtes Band ist der Fehler, den man am Geraet sieht und im
        Profil nicht sucht. Geprueft fuer alle Kanaele MIT Bereichstabelle."""
        for nummer, handbuch, _a in _CHART:
            baender = self._bereiche(nummer)
            if not baender:
                continue
            with self.subTest(kanal=nummer, handbuch=handbuch):
                self.assertEqual(baender[0].range_from, 0)
                self.assertEqual(baender[-1].range_to, 255)
                for a, b in zip(baender, baender[1:]):
                    self.assertEqual(
                        b.range_from, a.range_to + 1,
                        f"Luecke/Ueberschneidung bei {a.range_to}->{b.range_from}")


if __name__ == "__main__":
    unittest.main()

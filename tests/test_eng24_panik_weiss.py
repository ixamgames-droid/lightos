"""ENG-24: „Alles Weiss" liess Amber, UV und das Farbrad stehen.

„Alles Weiss" ist eine **Rettungsfunktion**. Wenn sie scheitert, dann in dem
Moment, in dem niemand mehr Zeit hat nachzusehen — und sie scheiterte auf die
unguenstigste Art: hell, aber nicht weiss.

**Gemessen vor dem Fix** ueber die echte Bibliothek: **11 Modi** tragen
``color_a`` und/oder ``color_uv`` (PAR4, PAR5, MEGAPAR+, CQ6136 ×2, ADJ5PXHEX
×3 u. a.). ``white_attrs_for_fixture`` lieferte dort nur
``color_r/g/b/w`` — Amber und UV kamen im Ergebnis **gar nicht vor** und
behielten damit ihren Vorwert.

★ ``color_attrs_for_fixture`` ist daran unschuldig: es beantwortet „welche
Kanaele machen weiss?". Ein OVERRIDE muss aber auch die Kanaele bestimmen, die
er auf **0** will — sonst ist er kein Override, sondern ein Zuschlag auf einen
unbekannten Zustand.

★★★ **Der Farbrad-Teil hat den eigenen ersten Entwurf gestoppt.** Ein Geraet mit
RGB *und* Farbrad (gemessen: **17 Modi**) erreicht den Rad-Zweig von
``color_attrs_for_fixture`` nie — er steht hinter dem RGB-Zweig. Ihn hier
mitzubenutzen lag nahe und waere falsch gewesen: er beantwortet *„welcher Slot
kommt der Wunschfarbe am naechsten?"*, hier gilt aber *„welcher Slot legt das Rad
AUS DEM WEG?"*. Gemessen mit der ersten Fassung: DOTZ TPAR und DOTZ MATRIX haben
keinen weiss benannten Slot, also gewann der naechstgelegene bunte — die
Panik-Funktion haette die Lampen auf **Blau** gestellt. Richtig ist
``open_value_of_channel`` (``kind == "open"``), dieselbe Funktion und dieselbe
Haltung wie bei der Shutter-Regel; sie trifft „Manuelle RGB-Steuerung",
„Aus" bzw. „Offen (RGBW-Mischung aktiv)".
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Alle ``color*``-Attribute, die die Bibliothek heute kennt. Waechst sie, muss
#: entschieden werden: additiver Emitter (auf 0) oder Ortsangabe (Offen-Slot)?
BEKANNTE_FARBATTRIBUTE = {"color_r", "color_g", "color_b", "color_w",
                          "color_a", "color_uv", "color_wheel"}
RAD_ATTRIBUTE = {"color_wheel", "colour_wheel", "color"}


class _Basis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def _kanaele(self, kurz, moduswahl=max):
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import (FixtureChannel, FixtureMode,
                                              FixtureProfile)
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels)
                         .selectinload(FixtureChannel.ranges))
                .where(FixtureProfile.short_name == kurz)).scalars().first()
            self.assertIsNotNone(p, f"Vorbedingung: {kurz} steht in der Bibliothek")
            m = moduswahl(p.modes, key=lambda x: x.channel_count)
            return [SimpleNamespace(
                        attribute=c.attribute, channel_number=c.channel_number,
                        name=c.name, highlight_value=c.highlight_value,
                        ranges=[SimpleNamespace(range_from=r.range_from,
                                                range_to=r.range_to,
                                                name=r.name,
                                                kind=getattr(r, "kind", None))
                                for r in (c.ranges or [])])
                    for c in sorted(m.channels, key=lambda c: c.channel_number)]

    def _weiss(self, chans):
        from src.core.all_white import white_attrs_for_fixture
        from src.core.app_state import open_value_of_channel
        return white_attrs_for_fixture(chans, open_value_of_channel)

    def _slotname(self, chans, attr, wert):
        ch = next(c for c in chans if c.attribute == attr)
        return next((r.name for r in ch.ranges
                     if r.range_from <= wert <= r.range_to), None)


class JederFarbkanalWirdBestimmtTest(_Basis):

    def test_amber_und_uv_gehen_auf_null(self):
        """★★★ Der Kern. Vorher kamen beide im Ergebnis gar nicht vor."""
        for kurz in ("MEGAPAR+", "CQ6136", "ADJ5PXHEX"):
            with self.subTest(geraet=kurz):
                chans = self._kanaele(kurz)
                vorhanden = {c.attribute for c in chans}
                self.assertTrue({"color_a", "color_uv"} <= vorhanden,
                                "Vorbedingung: das Geraet hat Amber und UV")
                out = self._weiss(chans)
                self.assertEqual(out.get("color_a"), 0)
                self.assertEqual(out.get("color_uv"), 0)

    def test_kein_farb_emitter_bleibt_unbestimmt(self):
        """★★ Die allgemeine Fassung: was auch immer an Farb-Emittern am Geraet
        haengt, der Override muss es NENNEN. „Nicht genannt" heisst „behaelt
        seinen Vorwert" — und einen unbekannten Vorwert darf eine Panik-Funktion
        nicht stehen lassen."""
        for kurz in ("PAR4", "PAR5", "MEGAPAR+", "CQ6136", "ADJ5PXHEX",
                     "ZQ06121", "MACAURA"):
            with self.subTest(geraet=kurz):
                chans = self._kanaele(kurz)
                out = self._weiss(chans)
                offen = [c.attribute for c in chans
                         if (c.attribute or "").startswith("color")
                         and c.attribute not in RAD_ATTRIBUTE
                         and c.attribute not in out]
                self.assertEqual(offen, [], f"unbestimmt geblieben: {offen}")

    def test_die_weissen_kanaele_tragen_das_weiss(self):
        """Gegenprobe: nicht ALLES auf 0 — es soll ja hell und weiss werden."""
        chans = self._kanaele("MEGAPAR+")
        out = self._weiss(chans)
        self.assertEqual(out.get("color_w"), 255,
                         "bei RGBW traegt der Weiss-Kanal das Weiss")
        self.assertTrue(any(v == 255 for v in out.values()))


class DasFarbradWirdAusDemWegGefahrenTest(_Basis):

    def test_der_offene_slot_wird_gewaehlt(self):
        """★★ Und zwar der, der das Rad AUS DEM WEG legt — nicht der, der einer
        weissen Wunschfarbe am naechsten kommt."""
        for kurz, erwarteter_slot in (("FPQWH12X", "Aus"),
                                      ("DOTZTPAR", "Manuelle RGB-Steuerung"),
                                      ("MACAURA", "Offen (RGBW-Mischung aktiv)")):
            with self.subTest(geraet=kurz):
                chans = self._kanaele(kurz)
                out = self._weiss(chans)
                wert = out.get("color_wheel")
                self.assertIsNotNone(wert, "das Rad wurde nicht angefasst")
                self.assertEqual(self._slotname(chans, "color_wheel", wert),
                                 erwarteter_slot)

    def test_es_wird_NICHT_der_naechstgelegene_bunte_slot(self):
        """★★★ Der Fehler, den der erste Entwurf gemacht hat, als Test
        festgehalten. DOTZ TPAR hat keinen weiss benannten Slot; wer die
        Naechste-Farbe-Regel benutzt, landet auf **Blau** und die
        Panik-Funktion faerbt die Lampen ein."""
        chans = self._kanaele("DOTZTPAR")
        wert = self._weiss(chans).get("color_wheel")
        name = (self._slotname(chans, "color_wheel", wert) or "").lower()
        for bunt in ("blau", "rot", "gruen", "grün", "gelb", "cyan", "magenta"):
            self.assertNotIn(bunt, name,
                             f"das Panik-Weiss stellt das Rad auf {name!r}")

    def test_ohne_belegte_slots_bleibt_das_rad_in_ruhe_oder_geht_auf_aus(self):
        """Der ADJ 5PX HEX hat einen „Farb-Makro"-Kanal ganz OHNE Slots. Dann
        entscheidet ``highlight_value`` — wie beim Shutter. Was hier NICHT
        passieren darf, ist ein geratener bunter Slot."""
        chans = self._kanaele("ADJ5PXHEX")
        wert = self._weiss(chans).get("color_wheel")
        self.assertIn(wert, (None, 0),
                      "auf einem Makro-Kanal ohne Slots wurde ein Wert geraten")

    def test_ein_geraet_MIT_rad_und_OHNE_rgb_bleibt_unveraendert(self):
        """★★ Die wichtigste Gegenprobe: dort ist das Rad die EINZIGE
        Farbquelle, und die bestehende Naechste-Farbe-Regel ist genau richtig.
        Dieser Fix darf sie nicht anfassen."""
        chans = self._kanaele("MH16")
        vorhanden = {c.attribute for c in chans}
        self.assertNotIn("color_r", vorhanden, "Vorbedingung: kein RGB")
        self.assertIn("color_wheel", vorhanden, "Vorbedingung: ein Rad")
        wert = self._weiss(chans).get("color_wheel")
        name = (self._slotname(chans, "color_wheel", wert) or "").lower()
        self.assertTrue("weiß" in name or "weiss" in name or "offen" in name,
                        f"der Rad-Zweig waehlt nicht mehr weiss: {name!r}")


class DerOffenSlotWirdWIRKLICHGesuchtTest(unittest.TestCase):
    """★★★ Von der Mutationsprobe erzwungen — und sie hatte recht.

    Bei ALLEN Raedern der heutigen Bibliothek beginnt der offene Slot bei 0.
    Deshalb bestanden die Tests oben auch die Mutation „setze das Rad einfach
    auf 0": 0 faellt dort zufaellig in denselben Slot. Der Test konnte „die
    Regel sucht den offenen Slot" und „die Regel schreibt eine 0" nicht
    unterscheiden — ein Bestehen, das nichts belegt.

    Der Beleg braucht ein Geraet, bei dem der offene Slot NICHT bei 0 liegt.
    Ein solches gibt es heute nicht, also wird es hier gebaut: die Regel muss
    unabhaengig von der zufaelligen Slot-Anordnung der aktuellen Bibliothek
    gelten.
    """

    def _weiss(self, chans):
        from src.core.all_white import white_attrs_for_fixture
        from src.core.app_state import open_value_of_channel
        return white_attrs_for_fixture(chans, open_value_of_channel)

    def _rad(self, ranges, attribut="color_wheel"):
        return SimpleNamespace(
            attribute=attribut, channel_number=4, name="Farbrad",
            highlight_value=None,
            ranges=[SimpleNamespace(range_from=a, range_to=b, name=n, kind=k)
                    for a, b, n, k in ranges])

    def _rgb(self):
        return [SimpleNamespace(attribute=a, channel_number=i + 1, name=a,
                                highlight_value=None, ranges=[])
                for i, a in enumerate(("color_r", "color_g", "color_b"))]

    def test_der_offene_slot_wird_getroffen_auch_wenn_er_hinten_liegt(self):
        rad = self._rad([(0, 9, "Rot", "color"),
                         (10, 19, "Blau", "color"),
                         (200, 210, "Offen", "open")])
        wert = self._weiss(self._rgb() + [rad]).get("color_wheel")
        self.assertEqual(wert, 205,
                         "der offene Slot wird nicht gesucht — 0 waere hier "
                         "'Rot', und das Panik-Weiss faerbt die Lampe ein")

    def test_ohne_offenen_slot_und_ohne_highlight_bleibt_das_rad_in_ruhe(self):
        """Dieselbe Haltung wie bei der Shutter-Regel: kein Beleg, kein Wert."""
        rad = self._rad([(0, 127, "Rot", "color"), (128, 255, "Blau", "color")])
        self.assertIsNone(self._weiss(self._rgb() + [rad]).get("color_wheel"),
                          "es wurde ein Slot geraten")

    def test_das_rad_wird_NIE_als_emitter_genullt(self):
        """★★ Die zweite Mutation, die zuerst ueberlebt hat: zaehlte das Rad als
        Farb-Emitter, ginge es auf 0 — bei diesem Geraet also auf 'Rot'."""
        rad = self._rad([(0, 9, "Rot", "color"), (200, 210, "Offen", "open")])
        wert = self._weiss(self._rgb() + [rad]).get("color_wheel")
        self.assertNotEqual(wert, 0, "das Rad wurde wie ein Pegel behandelt")

    def test_auch_die_alten_schreibweisen_des_rad_attributs(self):
        for attribut in ("colour_wheel", "color"):
            with self.subTest(attribut=attribut):
                rad = self._rad([(0, 9, "Rot", "color"),
                                 (200, 210, "Offen", "open")], attribut)
                out = self._weiss(self._rgb() + [rad])
                self.assertEqual(out.get(attribut), 205)


class DieAnnahmenSindFestgenageltTest(_Basis):
    """★ Waechter statt Vermutung."""

    def test_die_bibliothek_kennt_genau_diese_farbattribute(self):
        """★★ Kommt ein neues ``color*``-Attribut dazu, muss jemand
        entscheiden: additiver Emitter (auf 0) oder Ortsangabe (Offen-Slot)?
        Dieser Test faellt dann rot, damit die Entscheidung nicht still
        uebergangen wird — statt dass ein neuer Kanal unbemerkt auf 0 geht."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureMode, FixtureProfile
        gefunden = set()
        with Session(self._eng) as s:
            for p in s.execute(
                    select(FixtureProfile)
                    .options(selectinload(FixtureProfile.modes)
                             .selectinload(FixtureMode.channels))).scalars():
                for m in p.modes:
                    for c in m.channels:
                        a = c.attribute or ""
                        if a.startswith("color"):
                            gefunden.add(a)
        self.assertEqual(gefunden, BEKANNTE_FARBATTRIBUTE,
                         "neues Farb-Attribut: Emitter (auf 0) oder Ortsangabe "
                         "(Offen-Slot)? Siehe _KEINE_EMITTER in all_white.py")

    def test_es_gibt_wirklich_geraete_mit_rgb_UND_rad(self):
        """Belegt die Praemisse des Rad-Zweigs. Faellt das weg, ist der Zweig
        toter Code und gehoert geprueft, nicht behalten."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureMode, FixtureProfile
        n = 0
        with Session(self._eng) as s:
            for p in s.execute(
                    select(FixtureProfile)
                    .options(selectinload(FixtureProfile.modes)
                             .selectinload(FixtureMode.channels))).scalars():
                for m in p.modes:
                    attrs = {(c.attribute or "") for c in m.channels}
                    if {"color_r", "color_g", "color_b"} <= attrs and (attrs & RAD_ATTRIBUTE):
                        n += 1
        self.assertGreater(n, 5, "kaum Geraete mit RGB und Rad — Annahme pruefen")


if __name__ == "__main__":
    unittest.main()

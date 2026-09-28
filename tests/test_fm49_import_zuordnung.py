"""FM-49: der QLC+-Import ordnet Kanaele ohne Preset nicht mehr falsch zu.

QLC+-Kanaele ohne Channel-Preset tragen nur eine grobe <Group>. Gemessen am
2026-09-29 an 64 092 importierten Kanaelen: Farbkanaele in „Intensity" wurden
Dimmer, „Gobo/Prism Rotation" in „Speed" eine Geschwindigkeit, „Frost" in
„Effect" ein Makro, Laser/Blades in „Beam" ein Zoom (1239 Kanaele, 181 Profile).

Die XML-Zeilen unten sind woertlich aus den QLC+-Definitionen
(mcallegari/qlcplus, resources/fixtures) der genannten Geraete.
"""
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.core.database import fixture_db as F
from src.core.database.models import (FixtureChannel, FixtureMode, FixtureProfile,
                                      Manufacturer, create_all_idempotent)
from src.core.database.qxf_import import (QXF_NS, _resolve_attribute,
                                          attribut_korrigieren, bibliothek_reparieren)


def _kanal(xml: str):
    """Eine <Channel>-Zeile aus einer .qxf im QLC+-Namensraum parsen."""
    return ET.fromstring(xml.replace("<Channel ", f'<Channel xmlns="{QXF_NS}" ', 1))


class EchteQxfZeilenTest(unittest.TestCase):
    """Je Klasse eine echte Zeile: vorher falsch, jetzt richtig."""

    def test_farbkanal_in_gruppe_intensity(self):
        # American DJ Hyper Gem LED
        el = _kanal('<Channel Name="Red 1"><Group Byte="0">Intensity</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "color_r")
        # Chauvet Geyser P6
        el = _kanal('<Channel Name="Amber"><Group Byte="0">Intensity</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "color_a")

    def test_rotation_in_gruppe_speed(self):
        # American DJ Boom Box Fx2
        el = _kanal('<Channel Name="Gobo Rotation"><Group Byte="0">Speed</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "gobo_rotation")
        # Ayrton Mistral
        el = _kanal('<Channel Name="Prism Rotation"><Group Byte="0">Speed</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "prism_rotation")

    def test_frost_in_gruppe_effect(self):
        # American DJ Focus Spot 5Z
        el = _kanal('<Channel Name="Frost 1"><Group Byte="0">Effect</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "frost")

    def test_laser_und_blades_in_gruppe_beam_sind_kein_zoom(self):
        # American DJ Galaxian 3D
        el = _kanal('<Channel Name="Red Laser"><Group Byte="0">Beam</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "raw")
        # ADB Warp M
        el = _kanal('<Channel Name="Shutter A Rotation/Index Coarse">'
                    '<Group Byte="0">Beam</Group></Channel>')
        self.assertEqual(_resolve_attribute(el), "raw")

    def test_was_stimmte_bleibt(self):
        for xml, soll in (
            ('<Channel Name="Dimmer"><Group Byte="0">Intensity</Group></Channel>', "intensity"),
            ('<Channel Name="Zoom"><Group Byte="0">Beam</Group></Channel>', "zoom"),
            ('<Channel Name="Beam Angle"><Group Byte="0">Beam</Group></Channel>', "zoom"),
            ('<Channel Name="Pan/Tilt Speed"><Group Byte="0">Speed</Group></Channel>', "speed"),
            ('<Channel Name="Red" Preset="IntensityRed"/>', "color_r"),
        ):
            with self.subTest(xml=xml):
                self.assertEqual(_resolve_attribute(_kanal(xml)), soll)


class RegelGrenzenTest(unittest.TestCase):
    """Sammelkanaele mit Farbwort im Namen werden NICHT geraten."""

    def test_sammel_und_steuerkanaele_bleiben(self):
        for name in ("Red | Step Time", "Cyan/Random CMY", "Yellow color fading",
                     "Red Laser", "Red/Green", "Red fine", "Master Dimmer"):
            with self.subTest(name=name):
                self.assertEqual(attribut_korrigieren("intensity", name), "intensity")

    def test_speed_mit_mehreren_funktionen_bleibt(self):
        self.assertEqual(attribut_korrigieren(
            "speed", "Effect speed/Color/Gobo selection/Gobo rotation/Prism"), "speed")

    def test_frost_sammelkanal_bleibt_makro(self):
        self.assertEqual(attribut_korrigieren("macro", "Zoom, Frost, UV Filter"), "macro")

    def test_beam_namen_werden_ihr_attribut(self):
        self.assertEqual(attribut_korrigieren("zoom", "Focus"), "focus")
        self.assertEqual(attribut_korrigieren("zoom", "Diffusion"), "frost")
        self.assertEqual(attribut_korrigieren("zoom", "Blade 1A"), "raw")

    def test_lime_ist_keine_helligkeit(self):
        self.assertEqual(attribut_korrigieren("intensity", "Lime"), "raw")


class BibliothekReparaturTest(unittest.TestCase):
    """Die schon importierte Bibliothek wird einmal nachgezogen — nur Attribute."""

    def setUp(self):
        fd, self.pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.pfad)
        self.eng = create_engine(f"sqlite:///{self.pfad}")
        self.addCleanup(self.eng.dispose)
        create_all_idempotent(self.eng)
        with Session(self.eng) as s:
            mfr = Manufacturer(name="TestCo")
            s.add(mfr)
            for quelle, kurz in (("qlcplus", "IMP"), ("builtin", "EIG")):
                p = FixtureProfile(name=kurz, short_name=kurz, fixture_type="par",
                                   manufacturer=mfr, source=quelle)
                m = FixtureMode(name="4ch", channel_count=4)
                for i, (n, a) in enumerate((("Dimmer", "intensity"), ("Red 1", "intensity"),
                                            ("Gobo Rotation", "speed"), ("Frost", "macro")), 1):
                    m.channels.append(FixtureChannel(channel_number=i, name=n, attribute=a))
                p.modes.append(m)
                s.add(p)
            s.commit()

    def _attrs(self, kurz):
        with Session(self.eng) as s:
            return s.execute(text(
                "select c.attribute from channels c join fixture_modes m on m.id=c.mode_id "
                "join fixtures f on f.id=m.fixture_id where f.short_name=:k "
                "order by c.channel_number"), {"k": kurz}).scalars().all()

    def test_nur_importierte_profile_nur_attribute(self):
        with Session(self.eng) as s:
            liste = bibliothek_reparieren(s)
            s.commit()
        self.assertEqual(len(liste), 3)
        self.assertEqual(self._attrs("IMP"), ["intensity", "color_r", "gobo_rotation", "frost"])
        self.assertEqual(self._attrs("EIG"), ["intensity", "intensity", "speed", "macro"],
                         "eingebaute Profile fasst die Import-Regel nicht an")

    def test_laeuft_einmal_je_regel_version(self):
        with Session(self.eng) as s:
            self.assertTrue(F._qlc_korrektur(s))
            s.commit()
        self.assertEqual(len(F.LETZTE_QLC_KORREKTUR), 3)
        with Session(self.eng) as s:
            self.assertFalse(F._qlc_korrektur(s), "Version gestempelt -> kein zweiter Lauf")
            v = s.execute(text("select version from qlc_korrektur")).scalar()
        self.assertEqual(v, F.QLC_KORREKTUR_VERSION)

    def test_zweiter_lauf_findet_nichts(self):
        with Session(self.eng) as s:
            bibliothek_reparieren(s)
            s.commit()
        with Session(self.eng) as s:
            self.assertEqual(bibliothek_reparieren(s), [])


if __name__ == "__main__":
    unittest.main()

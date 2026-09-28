"""FM-50: installierte eingebaute Profile werden an die Code-Fassung angeglichen.

Gemessen am 2026-09-28: die installierte Bibliothek des Betreibers lag 7 Modi
hinter dem Code — ``ensure_builtins`` trug nur FEHLENDE Profile nach. Der
ZQ01424 hatte keine Strobe-Bereiche (dort schrieb „Auf" 255 = Strobe schnell),
der 102-Kanal-Modus der Stairville MB5x5 fehlte ganz.

Geprueft an einer kuenstlich GEALTERTEN Kopie einer frisch gebauten Bibliothek
— eigene Engine, die globale bleibt unberuehrt.
"""
import os
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from src.core.database import fixture_db as F
from src.core.database.models import (ChannelRange, FixtureChannel, FixtureMode,
                                      FixtureProfile, Manufacturer, create_all_idempotent)


def _profil(s, kurz):
    return s.execute(select(FixtureProfile)
                     .options(selectinload(FixtureProfile.modes)
                              .selectinload(FixtureMode.channels)
                              .selectinload(FixtureChannel.ranges))
                     .where(FixtureProfile.short_name == kurz)).scalars().first()


class AbgleichTest(unittest.TestCase):

    def setUp(self):
        fd, self.pfad = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.remove, self.pfad)
        self.eng = create_engine(f"sqlite:///{self.pfad}")
        self.addCleanup(self.eng.dispose)
        create_all_idempotent(self.eng)
        with Session(self.eng) as s:
            F._seed(s)
            s.flush()
            F._ensure_builtins_in(s)
            s.commit()

    def _altern(self):
        """Wie eine Installation aus einer frueheren Version."""
        with Session(self.eng) as s:
            zq = _profil(s, "ZQ01424")
            strobe = next(c for m in zq.modes if m.name == "8-Kanal RGBW"
                          for c in m.channels if c.attribute == "shutter")
            strobe.ranges.clear()                                   # Bereiche weg
            mb = _profil(s, "STAIRMB5X5")
            weg = next(m for m in mb.modes if m.name.startswith("102-Kanal"))
            mb.modes.remove(weg)                                    # Modus weg
            hex_ = _profil(s, "ADJ5PXHEX")
            ch = sorted(hex_.modes[0].channels, key=lambda c: c.channel_number)[-1]
            ch.attribute = "raw" if ch.attribute != "raw" else "speed"   # strukturell anders
            # ein importiertes Profil mit „falschen" Bereichen — darf NIE angefasst werden
            mfr = s.execute(select(Manufacturer)).scalars().first()
            imp = FixtureProfile(name="Import X", short_name="IMPX", fixture_type="par",
                                 manufacturer=mfr, source="qlcplus")
            m = FixtureMode(name="3ch", channel_count=1)
            c = FixtureChannel(channel_number=1, name="Strobe", attribute="shutter")
            m.channels.append(c)
            imp.modes.append(m)
            s.add(imp)
            s.commit()

    def test_repariert_was_sicher_ist_und_meldet_den_rest(self):
        self._altern()
        with Session(self.eng) as s:
            geaendert = F._builtins_abgleichen(s)
            s.commit()
        self.assertTrue(geaendert)
        bericht = F.LETZTER_ABGLEICH
        self.assertIn("ZQ01424 [8-Kanal RGBW]", bericht["angeglichen"])
        self.assertTrue(any(x.startswith("STAIRMB5X5 [102-Kanal") for x in bericht["ergaenzt"]))
        self.assertTrue(any(x.startswith("ADJ5PXHEX") for x in bericht["strukturell"]))
        with Session(self.eng) as s:
            zq = _profil(s, "ZQ01424")
            strobe = next(c for m in zq.modes if m.name == "8-Kanal RGBW"
                          for c in m.channels if c.attribute == "shutter")
            self.assertTrue(strobe.ranges, "Strobe-Bereiche wieder da")
            self.assertTrue(any(m.name.startswith("102-Kanal") for m in _profil(s, "STAIRMB5X5").modes))
            hex_ = _profil(s, "ADJ5PXHEX")
            letzte = sorted(hex_.modes[0].channels, key=lambda c: c.channel_number)[-1]
            self.assertIn(letzte.attribute, ("raw", "speed"), "strukturell: NICHT still geaendert")
            imp = _profil(s, "IMPX")
            self.assertEqual(imp.modes[0].channels[0].ranges, [], "Import unberuehrt")

    def test_aktuelle_bibliothek_bleibt_unveraendert(self):
        with Session(self.eng) as s:
            self.assertFalse(F._builtins_abgleichen(s))
        self.assertEqual(F.LETZTER_ABGLEICH,
                         {"ergaenzt": [], "angeglichen": [], "strukturell": []})

    def test_zweiter_abgleich_findet_nichts_mehr(self):
        self._altern()
        with Session(self.eng) as s:
            F._builtins_abgleichen(s)
            s.commit()
        with Session(self.eng) as s:
            self.assertFalse(F._builtins_abgleichen(s))
        self.assertEqual(F.LETZTER_ABGLEICH["angeglichen"], [])
        self.assertEqual(F.LETZTER_ABGLEICH["ergaenzt"], [])

    def test_stempel(self):
        with Session(self.eng) as s:
            self.assertEqual(F._stand_lesen(s), "")
            F._stand_schreiben(s, "abc")
            s.commit()
        with Session(self.eng) as s:
            self.assertEqual(F._stand_lesen(s), "abc")
        self.assertEqual(len(F._code_stand()), 16)


if __name__ == "__main__":
    unittest.main()

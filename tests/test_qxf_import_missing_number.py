"""QXF-Import: ein FEHLENDES Mode-``Number`` darf nicht mit dem echten 1. Kanal
kollidieren (CDX-03, FIMP-02-Rest).

``int(ch_ref.get("Number", "0")) + 1`` liess ein komplett fehlendes
``Number``-Attribut still per Default "0" → num=1 durchrutschen. ``int("0")`` ist
parsebar, also griff der bestehende ``except (ValueError, TypeError)`` (der nur
NON-numerische Strings faengt) NICHT — der Kanal ohne Number bekam dieselbe
``channel_number`` wie der legitime 1. Kanal (``Number="0"``). Beim nach
``channel_number`` sortierten Auslesen verschob sich die DMX-Belegung still.

Fix (CDX-03 + Review): ``Number`` OHNE Default holen und in ZWEI Durchlaeufen
aufloesen — zuerst alle explizit nummerierten Kanaele, dann die Number-losen auf die
jeweils naechste WIRKLICH freie Nummer. So teilen sich nie zwei Kanaele dieselbe
``channel_number`` UND ein Number-loser Ref verdraengt nie einen explizit
nummerierten (auch nicht, wenn er im Dokument zuerst steht). Non-numerische Number
bleibt ein sichtbar gemeldeter Skip.
"""
import os
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database.models import Base, FixtureMode, FixtureChannel
from src.core.database.qxf_import import import_qxf_file, QXF_NS


# Mode: legitimer 1. Kanal mit Number="0" (→ channel_number 1), daneben ein
# Kanal OHNE Number-Attribut. Frueher landeten BEIDE auf channel_number 1.
_QXF_MISSING = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>MissingNumberSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Mode Name="bank">
  <Channel Number="0">Red</Channel>
  <Channel>Green</Channel>
 </Mode>
</FixtureDefinition>
"""


class MissingNumberDoesNotCollideTest(unittest.TestCase):
    def _import(self, xml_text):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        fd, path = tempfile.mkstemp(suffix=".qxf")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml_text)
            with Session(engine) as s:
                ok = import_qxf_file(path, s, {})
                self.assertTrue(ok)
                s.commit()
                mode = s.execute(select(FixtureMode)).scalar_one()
                chs = s.execute(
                    select(FixtureChannel)
                    .where(FixtureChannel.mode_id == mode.id)
                    .order_by(FixtureChannel.channel_number)
                ).scalars().all()
                return [(c.channel_number, c.name, c.attribute) for c in chs]
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def test_no_two_channels_share_a_number(self):
        chs = self._import(_QXF_MISSING)
        numbers = [n for (n, _, _) in chs]
        # Kernaussage CDX-03: KEINE zwei Kanaele teilen sich dieselbe
        # channel_number, obwohl ein Ref das Number-Attribut nicht hatte.
        self.assertEqual(len(numbers), len(set(numbers)),
                         f"channel_number-Kollision: {chs}")

    def test_missing_number_does_not_displace_explicit(self):
        # CDX-03 (Review): Der Number-lose Kanal wird NICHT gedroppt, sondern auf die
        # naechste freie Nummer gelegt — verdraengt aber den explizit nummerierten
        # Kanal 1 nie.
        chs = self._import(_QXF_MISSING)
        by_num = {n: (name, attr) for (n, name, attr) in chs}
        self.assertEqual(by_num[1], ("Red", "color_r"))   # explizit, bleibt auf 1
        self.assertEqual(by_num[2][0], "Green")           # Number-los -> naechste frei (2)

    def test_missing_number_FIRST_still_does_not_displace(self):
        # Der eigentliche Review-Fall: der Number-lose Kanal steht ZUERST im Dokument,
        # der explizit nummerierte (Number="0") danach. Trotzdem darf der explizite
        # Kanal 1 nicht verdraengt werden (Pass 1 platziert ihn vor den Number-losen).
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>MissingFirstSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Foo" Preset="IntensityMasterDimmer"/>
 <Channel Name="Dimmer" Preset="IntensityDimmer"/>
 <Mode Name="bank">
  <Channel>Foo</Channel>
  <Channel Number="0">Dimmer</Channel>
 </Mode>
</FixtureDefinition>
"""
        chs = self._import(xml)
        by_num = {n: name for (n, name, _) in chs}
        numbers = [n for (n, _, _) in chs]
        self.assertEqual(len(numbers), len(set(numbers)))   # keine Kollision
        self.assertEqual(by_num[1], "Dimmer")               # explizit gewinnt Kanal 1
        self.assertEqual(by_num[2], "Foo")                  # Number-los -> 2, nicht verdraengend

    def test_empty_number_treated_as_missing(self):
        # A3D-34: ein LEERES Number-Attribut (Number="") ist morally „keine Angabe".
        # Frueher lief es in int("") -> ValueError -> der Kanal wurde still GEDROPPT.
        # Jetzt wird es wie fehlend behandelt -> Pass 2 legt es auf die naechste
        # freie Nummer (2), der Kanal bleibt also erhalten.
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>EmptyNumberSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Mode Name="bank">
  <Channel Number="0">Red</Channel>
  <Channel Number="">Green</Channel>
 </Mode>
</FixtureDefinition>
"""
        chs = self._import(xml)
        by_num = {n: name for (n, name, _) in chs}
        numbers = [n for (n, _, _) in chs]
        self.assertEqual(len(chs), 2, f"leerer Number-Kanal wurde gedroppt: {chs}")
        self.assertEqual(len(numbers), len(set(numbers)))   # keine Kollision
        self.assertEqual(by_num[1], "Red")                  # explizit bleibt Kanal 1
        self.assertEqual(by_num[2], "Green")                # leer -> naechste frei (2)

    def test_negative_number_rejected(self):
        # A3D-34: eine negative Number (Number="-1" -> int("-1")+1 == 0, "-2" -> -1)
        # ergaebe eine ungueltige channel_number <= 0 und rutschte frueher still
        # durch. Jetzt wird der Kanal sichtbar verworfen; NIE eine Nummer <= 0
        # gepatcht. Der legitime Kanal 1 bleibt erhalten.
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>NegativeNumberSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Mode Name="bank">
  <Channel Number="0">Red</Channel>
  <Channel Number="-1">Green</Channel>
 </Mode>
</FixtureDefinition>
"""
        chs = self._import(xml)
        numbers = [n for (n, _, _) in chs]
        self.assertTrue(all(n >= 1 for n in numbers),
                        f"channel_number <= 0 gepatcht: {chs}")
        # der negative Kanal wird verworfen -> nur der legitime Kanal 1 bleibt
        self.assertEqual(numbers, [1], f"negativer Kanal nicht verworfen: {chs}")


if __name__ == "__main__":
    unittest.main()

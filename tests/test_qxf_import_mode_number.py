"""QXF-Import: ein kaputtes Mode-``Number`` darf keine zwei Kanaele kollidieren.

Reproduziert FIMP-02 (docs/FIXTURE_IMPORT_AUDIT_2026-07-13.md): faellt das
``Number``-Attribut eines Mode-Channels weg oder ist es nicht parsebar, fiel die
Kanalnummer frueher hart auf ``len(ch_refs)`` zurueck. Ein defekter Ref neben dem
legitim letzten Kanal bekam damit DIESELBE ``channel_number`` -> beim nach
``channel_number`` sortierten Auslesen verschob sich die DMX-Belegung still.

Fix: defekte Refs werden uebersprungen (und gemeldet), nie auf einen
kollidierenden Default gezwungen -> alle ``channel_number`` bleiben eindeutig.
"""
import os
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database.models import Base, FixtureMode, FixtureChannel
from src.core.database.qxf_import import import_qxf_file, QXF_NS


# Mode: Red ohne Number (Default "0"->1), Green mit kaputtem Number="xx",
# Blue mit Number="2"->3. Frueher: Green faellt auf len(ch_refs)==3 -> Kollision
# mit Blue (beide channel_number==3).
_QXF_BROKEN = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>BrokenNumberSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Channel Name="Blue" Preset="IntensityBlue"/>
 <Mode Name="bank">
  <Channel>Red</Channel>
  <Channel Number="xx">Green</Channel>
  <Channel Number="2">Blue</Channel>
 </Mode>
</FixtureDefinition>
"""

# Gegenprobe: voll gueltiger Mode -> Verhalten unveraendert, alle Kanaele da.
_QXF_VALID = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>ValidNumberSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Channel Name="Blue" Preset="IntensityBlue"/>
 <Mode Name="bank">
  <Channel Number="0">Red</Channel>
  <Channel Number="1">Green</Channel>
  <Channel Number="2">Blue</Channel>
 </Mode>
</FixtureDefinition>
"""


class _QxfImportBase(unittest.TestCase):
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


class BrokenNumberIsSkippedTest(_QxfImportBase):
    def test_no_two_channels_share_a_number(self):
        chs = self._import(_QXF_BROKEN)
        numbers = [n for (n, _, _) in chs]
        # Kernaussage: keine zwei Kanaele teilen sich dieselbe channel_number.
        self.assertEqual(len(numbers), len(set(numbers)),
                         f"channel_number-Kollision: {chs}")

    def test_broken_channel_is_dropped_valid_ones_survive(self):
        chs = self._import(_QXF_BROKEN)
        by_num = {n: (name, attr) for (n, name, attr) in chs}
        # Der defekte Green-Ref wird sauber ausgelassen (kein Kanal fuer ihn).
        self.assertNotIn("Green", [name for (name, _) in by_num.values()])
        # Die gueltigen Refs bleiben unveraendert an ihren 1-basierten Nummern.
        self.assertEqual(by_num[1], ("Red", "color_r"))
        self.assertEqual(by_num[3], ("Blue", "color_b"))


class ValidModeUnchangedTest(_QxfImportBase):
    def test_valid_mode_maps_exactly_as_before(self):
        chs = self._import(_QXF_VALID)
        self.assertEqual(chs, [
            (1, "Red", "color_r"),
            (2, "Green", "color_g"),
            (3, "Blue", "color_b"),
        ])


if __name__ == "__main__":
    unittest.main()

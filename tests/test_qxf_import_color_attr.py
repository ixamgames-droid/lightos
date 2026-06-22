"""QXF-Import: farb-benannte Kanaele duerfen nie als ``raw`` landen.

Reproduziert den realen Speider-Defekt (U-King-Spider, QLC+-Import): ein Mode
referenziert ``Red``/``Green``/``Blue``/``White``, aber die ``<Channel>``-
Definitionen passen nicht 1:1 zu den Mode-Referenznamen -> ``channel_defs.get``
liefert ``None`` -> frueher hart ``"raw"``. Folge: die erste RGBW-Bank galt
nicht als Farbe, fiel im Programmer in den "Weitere"-Tab und renderte nicht.

Der Namens-Fallback (``_attr_from_name``) rettet ``color_r/g/b/w``. Gegenprobe:
ein per Preset bewusst auf ``raw`` gesetztes Fine-Farbbyte (``IntensityRedFine``)
darf NICHT zu ``color_r`` umgedeutet werden (sonst Doppel-Mapping / kaputter
Footprint).
"""
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.core.database.models import Base, FixtureMode, FixtureChannel
from src.core.database.qxf_import import (
    _attr_from_name, _resolve_attribute, import_qxf_file, QXF_NS,
)


class AttrFromNameTest(unittest.TestCase):
    def test_color_words(self):
        self.assertEqual(_attr_from_name("Red"), "color_r")
        self.assertEqual(_attr_from_name("Green"), "color_g")
        self.assertEqual(_attr_from_name("grün"), "color_g")
        self.assertEqual(_attr_from_name("Blue"), "color_b")
        self.assertEqual(_attr_from_name("White 2"), "color_w")
        self.assertEqual(_attr_from_name("Amber"), "color_a")

    def test_unknown_and_empty_are_raw(self):
        self.assertEqual(_attr_from_name("Frobnicate"), "raw")
        self.assertEqual(_attr_from_name(""), "raw")
        self.assertEqual(_attr_from_name(None), "raw")

    def test_resolve_attribute_name_fallback_preserved(self):
        # <Channel> ohne Preset/Group -> Namens-Heuristik (Stufe 3) wie bisher.
        el = ET.Element(f"{{{QXF_NS}}}Channel", {"Name": "Green"})
        self.assertEqual(_resolve_attribute(el), "color_g")


_QXF = f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Manufacturer>TestCo</Manufacturer>
 <Model>ColorRawSpider</Model>
 <Type>Moving Head</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Red Fine" Preset="IntensityRedFine"/>
 <Mode Name="bank">
  <Channel Number="0">Red</Channel>
  <Channel Number="1">Green</Channel>
  <Channel Number="2">Blue</Channel>
  <Channel Number="3">White</Channel>
  <Channel Number="4">Red Fine</Channel>
 </Mode>
</FixtureDefinition>
"""


class ImportRecoversColorAttrTest(unittest.TestCase):
    def setUp(self):
        # Eigene In-Memory-DB pro Test -> keine Beruehrung der echten fixtures.db.
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        fd, self.path = tempfile.mkstemp(suffix=".qxf")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_QXF)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _channels(self):
        with Session(self.engine) as s:
            ok = import_qxf_file(self.path, s, {})
            self.assertTrue(ok)
            s.commit()
            mode = s.execute(select(FixtureMode)).scalar_one()
            chs = s.execute(
                select(FixtureChannel)
                .where(FixtureChannel.mode_id == mode.id)
                .order_by(FixtureChannel.channel_number)
            ).scalars().all()
            return {c.channel_number: (c.name, c.attribute) for c in chs}

    def test_missing_defs_recovered_from_name(self):
        chs = self._channels()
        # CH1 hat eine Definition (Preset) -> color_r wie gehabt.
        self.assertEqual(chs[1], ("Red", "color_r"))
        # CH2-4 referenzieren Namen OHNE <Channel>-Definition (channel_defs.get
        # == None) -> frueher hart "raw"; jetzt aus dem Namen gerettet.
        self.assertEqual(chs[2], ("Green", "color_g"))
        self.assertEqual(chs[3], ("Blue", "color_b"))
        self.assertEqual(chs[4], ("White", "color_w"))

    def test_preset_raw_not_overridden_by_name(self):
        chs = self._channels()
        # "Red Fine" ist per Preset bewusst raw -> bleibt raw (kein color_r),
        # obwohl der Name "Red" enthaelt.
        self.assertEqual(chs[5], ("Red Fine", "raw"))


if __name__ == "__main__":
    unittest.main()

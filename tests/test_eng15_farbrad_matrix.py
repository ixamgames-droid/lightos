"""ENG-15: ein Matrix-Effekt auf einem FARBRAD-Geraet.

★★★ Der Backlog-Eintrag beschrieb den falschen Mechanismus, und das Nachmessen
war die eigentliche Arbeit. Behauptet war: „jeder DUNKLE Pixel dreht das Rad auf
GRUEN statt dunkel zu bleiben", belegt mit ``DMX color [3, 27, 27, 3]``.

Gemessen am laufenden Code war es **anders und schlimmer**: das Farbrad wurde
ueberhaupt nicht angefasst. Der Zweig dafuer war TOTER CODE.

* ``color_attrs_for_fixture`` gibt ``{getattr(color_ch, "attribute"): wert}``
  zurueck — den Namen des GERAETE-Attributs. ``rgb_matrix.write`` las
  ``.get("color")``.
* Gemessen tragen **alle 2171 Farbrad-Modi** der echten Bibliothek das Attribut
  ``color_wheel``; ``color`` kommt in **5125 Modi null-mal** vor (in der
  eingebauten Saat ebenso: 27x ``color_wheel``, 0x ``color``).
* Dieselbe Verwechslung ein zweites Mal in der Kanalmaske: ``attr == "color"``.

Und weil dem Geraet die Farbkanaele fehlen, blieb auch die HELLIGKEIT auf der
Strecke: der Dimmer stand bei ``drive_intensity`` unbedingt auf 255. Ein Raster
``[weiss, schwarz, dunkel, weiss]`` schrieb an allen vier Zellen denselben
Wert — die Animation war am Geraet gar nicht zu sehen.
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _Universe:
    def __init__(self):
        self.ch: dict[int, int] = {}

    def set_channel(self, addr, val):
        self.ch[addr] = val


class FarbradMatrixTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from _fixture_quelle import frische_library
        cls._eng = frische_library(cls)

    def _kanaele(self, kurz):
        """Kanaele MIT ihren Ranges — ohne die kann kein Farbrad antworten.

        (Eigener Aufbaufehler beim ersten Messen: die Ranges fehlten, und
        ``color_attrs_for_fixture`` lieferte deshalb `{}` — das sah aus wie ein
        Befund und war der Testaufbau.)
        """
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import (FixtureProfile, FixtureMode,
                                              FixtureChannel)
        with Session(self._eng) as s:
            p = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels)
                         .selectinload(FixtureChannel.ranges))
                .where(FixtureProfile.short_name == kurz)).scalars().first()
            m = max(p.modes, key=lambda x: x.channel_count)
            return [SimpleNamespace(
                        attribute=c.attribute,
                        channel_number=c.channel_number,
                        ranges=[SimpleNamespace(range_from=r.range_from,
                                                range_to=r.range_to,
                                                name=r.name,
                                                kind=getattr(r, "kind", None))
                                for r in (c.ranges or [])])
                    for c in sorted(m.channels, key=lambda c: c.channel_number)]

    def _frame(self, chans, pixel, drive=True, style=None):
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle
        alt = AS.get_channels_for_patched
        AS.get_channels_for_patched = lambda f: chans
        self.addCleanup(lambda: setattr(AS, "get_channels_for_patched", alt))
        mx = RgbMatrixInstance(name="T")
        mx.cols, mx.rows = len(pixel), 1
        mx.style = style or MatrixStyle.RGB
        mx.fixture_grid = [1] * len(pixel)
        mx.drive_intensity = drive
        mx._running = True
        mx._render = lambda p: list(pixel)
        u = _Universe()
        mx.write({1: u}, [SimpleNamespace(fid=1, universe=1, address=1,
                                          fixture_type="moving_head")], 0.02)
        return u.ch

    def _adressen(self, chans, attribut):
        return [c.channel_number for c in chans if c.attribute == attribut]

    # ── Der Kern ────────────────────────────────────────────────────────────
    def test_das_farbrad_wird_ueberhaupt_gefahren(self):
        """★★ Vorher: gar nicht. Der Zweig las `.get("color")`, die Bibliothek
        liefert `color_wheel` — der Wert war immer None."""
        chans = self._kanaele("MH16")
        rad = self._adressen(chans, "color_wheel")
        self.assertTrue(rad, "Vorbedingung: das Geraet hat ein Farbrad")
        d = self._frame(chans, [(255, 255, 255)])
        self.assertIn(rad[0], d, "das Farbrad wurde nicht angefasst")

    def test_ein_schwarzer_pixel_schliesst_den_dimmer(self):
        """★★★ Die Abnahme aus dem Backlog-Eintrag, woertlich: „ein schwarzer
        Pixel am Farbrad-Geraet schliesst den Dimmer statt einen Farbslot zu
        waehlen (am DMX gemessen)"."""
        chans = self._kanaele("MH16")
        rad = self._adressen(chans, "color_wheel")[0]
        dim = [c.channel_number for c in chans
               if c.attribute in ("intensity", "dimmer", "master")][0]
        d = self._frame(chans, [(0, 0, 0)])
        self.assertEqual(d.get(dim), 0, "Dimmer muss zu sein")
        self.assertNotIn(rad, d,
                         "und das Rad bewegt sich nicht: Schwarz ist keine "
                         "Farbe, die auf einem Rad vorkommt")

    def test_die_helligkeit_folgt_dem_pixel(self):
        """Ohne Farbkanaele traegt der Dimmer die Helligkeit — es gibt sonst
        nichts, was sie tragen koennte. Vorher stand er unbedingt auf 255, die
        Animation war am Geraet nicht zu sehen."""
        chans = self._kanaele("MH16")
        dim = [c.channel_number for c in chans
               if c.attribute in ("intensity", "dimmer", "master")][0]
        for pixel, erwartet in (((255, 255, 255), 255),
                                ((42, 42, 42), 42),
                                ((0, 255, 0), 255),
                                ((0, 0, 0), 0)):
            with self.subTest(pixel=pixel):
                self.assertEqual(self._frame(chans, [pixel]).get(dim), erwartet)

    def test_der_slot_wird_nicht_mit_dem_master_skaliert(self):
        """Ein Slot ist eine ORTSANGABE auf dem Rad, kein Pegel — ihn zu
        skalieren waere eine andere FARBE, nicht dieselbe dunkler."""
        chans = self._kanaele("MH16")
        rad = self._adressen(chans, "color_wheel")[0]
        hell = self._frame(chans, [(0, 255, 0)])
        import src.core.app_state as AS
        from src.core.engine.rgb_matrix import RgbMatrixInstance, MatrixStyle
        AS.get_channels_for_patched = lambda f: chans
        mx = RgbMatrixInstance(name="T")
        mx.cols, mx.rows = 1, 1
        mx.style = MatrixStyle.RGB
        mx.fixture_grid = [1]
        mx.drive_intensity = True
        mx.intensity = 0.25
        mx._running = True
        mx._render = lambda p: [(0, 255, 0)]
        u = _Universe()
        mx.write({1: u}, [SimpleNamespace(fid=1, universe=1, address=1,
                                          fixture_type="moving_head")], 0.02)
        self.assertEqual(u.ch.get(rad), hell.get(rad),
                         "der Slot darf sich mit dem Master nicht verschieben")

    # ── Die Gegenproben ─────────────────────────────────────────────────────
    def test_rgb_geraete_bleiben_unveraendert(self):
        """★ Die wichtigste Gegenprobe: bei einem Geraet MIT Farbkanaelen
        traegt die FARBE die Helligkeit, der Dimmer soll nur oeffnen. Wuerde er
        hier dem Pixel folgen, waere es Doppel-Dimmen."""
        chans = self._kanaele("ZQ06121")
        dim = [c.channel_number for c in chans
               if c.attribute in ("intensity", "dimmer", "master")][0]
        rot = [c.channel_number for c in chans if c.attribute == "color_r"][0]
        for pixel, farbe in (((255, 255, 255), 255), ((42, 42, 42), 42),
                             ((0, 0, 0), 0)):
            with self.subTest(pixel=pixel):
                d = self._frame(chans, [pixel])
                self.assertEqual(d.get(dim), 255, "Dimmer oeffnet nur")
                self.assertEqual(d.get(rot), farbe, "die Farbe traegt die Helligkeit")

    def test_dimmer_und_shutter_stil_unveraendert(self):
        from src.core.engine.rgb_matrix import MatrixStyle
        chans = self._kanaele("ZQ06121")
        d = self._frame(chans, [(42, 42, 42)], style=MatrixStyle.DIMMER)
        self.assertEqual(d.get(1), 42, "DIMMER-Stil rechnet weiterhin selbst")
        d = self._frame(chans, [(42, 42, 42)], style=MatrixStyle.SHUTTER)
        self.assertIsNone(d.get(1), "SHUTTER laesst den Dimmer in Ruhe")

    def test_ohne_drive_intensity_bleibt_der_dimmer_unberuehrt(self):
        """Der Nutzer hat dann gesagt, die Matrix soll den Dimmer NICHT
        treiben — auch nicht, um Schwarz darzustellen."""
        chans = self._kanaele("MH16")
        dim = [c.channel_number for c in chans
               if c.attribute in ("intensity", "dimmer", "master")][0]
        d = self._frame(chans, [(0, 0, 0)], drive=False)
        self.assertNotIn(dim, d)

    # ── Der Beleg fuer die Namensfrage ──────────────────────────────────────
    def test_die_bibliothek_kennt_nur_color_wheel(self):
        """★ Der Grund, warum der Zweig toter Code war — als Test festgehalten,
        damit ein spaeterer „Aufraeumer" ihn nicht wieder auf `"color"` kuerzt."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session, selectinload
        from src.core.database.models import FixtureProfile, FixtureMode
        n_wheel = n_color = 0
        with Session(self._eng) as s:
            for p in s.execute(
                    select(FixtureProfile)
                    .options(selectinload(FixtureProfile.modes)
                             .selectinload(FixtureMode.channels))).scalars():
                for m in p.modes:
                    attrs = {(c.attribute or "") for c in m.channels}
                    n_wheel += 1 if "color_wheel" in attrs else 0
                    n_color += 1 if "color" in attrs else 0
        self.assertGreater(n_wheel, 0, "es gibt Farbrad-Modi")
        self.assertEqual(n_color, 0,
                         "das Attribut heisst ueberall `color_wheel` — wer hier "
                         "auf `\"color\"` prueft, prueft auf nichts")

    def test_der_schluessel_ist_das_geraete_attribut(self):
        """Gegenstueck dazu auf der Erzeuger-Seite."""
        from src.core.color_utils import color_attrs_for_fixture
        chans = self._kanaele("MH16")
        payload = color_attrs_for_fixture(chans, (255, 255, 255))
        self.assertIn("color_wheel", payload)
        self.assertNotIn("color", payload)


if __name__ == "__main__":
    unittest.main()

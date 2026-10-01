"""ENG-27 — „offen" nur mit Beleg: der ``highlight_value`` zaehlt nicht, wenn
er in einem Bereich ``closed``/``strobe`` liegt.

``open_value_of_channel`` lieferte nach dem ``open``-Bereich ungeprueft den
``highlight_value``. Weil der in der Bibliothek NOT NULL ist (gemessen 0 von
66 247 Kanaelen ohne Wert), war der Sentinel-Zweig „ohne Beleg in Ruhe lassen"
fuer echte Kanaele unerreichbar. Drei Aufrufer hingen daran:

* ``all_white`` Shutter — ein importierter Shutter ohne ``open``-Bereich, dessen
  ``highlight_value`` im Strobe-Bereich liegt, haette die Panik-Funktion das
  Geraet blitzen lassen; im ``closed``-Bereich haette sie es abgedunkelt,
* ``all_white`` Farbrad (ENG-24) — dieselbe Regel,
* EFX ``open_beam`` — erbte zusaetzlich den Vorgabewert 255 von
  ``open_value_for``, an vielen Shuttern „schnelles Blitzen".

Gegenprobe: auf der frisch geseedeten Bibliothek aendert die neue Regel an
KEINEM Shutter- oder Rad-Kanal den Wert (gemessen 0 von 57 bzw. 0 von 33) —
sie trifft nur importierte Profile.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import src.core.app_state as A
from src.core.all_white import white_attrs_for_fixture
from src.core.app_state import open_value_of_channel, shutter_bereich_art, \
    ist_strobe_kanal_ohne_bereiche
from src.core.dmx.universe import Universe
from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance
from _fixture_quelle import frische_library     # FIXTEST-FRESH

KEIN = -1


class _Range:
    def __init__(self, lo, hi, kind="", name=""):
        self.range_from, self.range_to, self.kind, self.name = lo, hi, kind, name


class _Ch:
    def __init__(self, attr, num, highlight=255, ranges=None, name=""):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0
        self.highlight_value = highlight
        self.ranges = ranges or []
        self.name = name


def _shutter(hv, num=4):
    """Shutter OHNE ``open``-Bereich: 0..9 zu, 10..255 Strobe langsam->schnell."""
    return _Ch("shutter", num, hv, [_Range(0, 9, "closed", "Zu"),
                                    _Range(10, 255, "strobe", "Strobe")], "Shutter")


class SentinelIstErreichbar(unittest.TestCase):

    def test_highlight_im_strobe_bereich_ist_kein_beleg(self):
        self.assertEqual(open_value_of_channel(_shutter(200), KEIN), KEIN)

    def test_highlight_im_closed_bereich_ist_kein_beleg(self):
        self.assertEqual(open_value_of_channel(_shutter(5), KEIN), KEIN)

    def test_open_bereich_bleibt_der_erste_beleg(self):
        ch = _Ch("shutter", 4, 200, [_Range(0, 9, "closed"), _Range(10, 19, "open"),
                                     _Range(20, 255, "strobe")])
        self.assertEqual(open_value_of_channel(ch, KEIN), 14)

    def test_highlight_ausserhalb_aller_bereiche_bleibt_beleg(self):
        ch = _Ch("shutter", 4, 250, [_Range(0, 9, "closed"), _Range(10, 199, "strobe")])
        self.assertEqual(open_value_of_channel(ch, KEIN), 250)

    def test_highlight_in_bereich_ohne_art_bleibt_beleg(self):
        ch = _Ch("color_wheel", 5, 12, [_Range(0, 9, "", "Weiss"), _Range(10, 19, "", "Rot")])
        self.assertEqual(open_value_of_channel(ch, KEIN), 12)

    def test_kanal_ohne_bereiche_unveraendert(self):
        self.assertEqual(open_value_of_channel(_Ch("shutter", 4, 0, name="Dimmer/Shutter"), KEIN), 0)
        self.assertEqual(open_value_of_channel(_Ch("color_wheel", 5, 0, name="Farb-Makro"), KEIN), 0)

    def test_ohne_kanal_der_fallback(self):
        self.assertEqual(open_value_of_channel(None, KEIN), KEIN)


class AllesWeissLaesstDenShutterInRuhe(unittest.TestCase):

    def test_strobe_highlight_wird_nicht_gesetzt(self):
        kanaele = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
                   _Ch("color_b", 5), _shutter(200, num=4)]
        out = white_attrs_for_fixture(kanaele, open_value_of_channel)
        self.assertNotIn("shutter", out, "Panik-Weiss haette das Geraet blitzen lassen")
        self.assertEqual(out.get("intensity"), 255)

    def test_farbrad_mit_highlight_im_closed_bereich(self):
        rad = _Ch("color_wheel", 6, 3, [_Range(0, 7, "closed", "Blackout"),
                                         _Range(8, 255, "", "Farben")])
        out = white_attrs_for_fixture([_Ch("intensity", 1), rad], open_value_of_channel)
        self.assertNotIn("color_wheel", out)


class EfxSichtbarkeitBlitztNicht(unittest.TestCase):
    """``open_beam`` setzt den Shutter nur mit Beleg — kein 255-Vorgabewert."""

    def setUp(self):
        self._orig = A.get_channels_for_patched

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _lauf(self, shutter):
        kanaele = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3), shutter]
        A.get_channels_for_patched = lambda fx: kanaele

        class _Fx:
            fid, universe, address = 1, 1, 10
            fixture_profile_id, mode_name, channel_count = 1, "m", 4
            invert_pan = invert_tilt = swap_pan_tilt = False

        uni = Universe(1)
        uni.set_channel(13, 42)            # Shutter-Vorwert (Adresse 10 + 3)
        efx = EfxInstance(name="eng27")
        efx.algorithm = EfxAlgorithm.CIRCLE
        efx.fixtures = [EfxFixture(fid=1)]
        efx.open_beam = True
        efx._running = True
        efx.write({1: uni}, [_Fx()], dt=0.5)
        return uni

    def test_ohne_beleg_bleibt_der_shutter_stehen(self):
        uni = self._lauf(_shutter(200))
        self.assertEqual(uni.get_channel(12), 255, "Dimmer voll wie bisher")
        self.assertEqual(uni.get_channel(13), 42, "Shutter ohne Beleg geoeffnet (Blitzen)")

    def test_mit_open_bereich_wie_bisher(self):
        uni = self._lauf(_Ch("shutter", 4, 0, [_Range(0, 7, "open")]))
        self.assertEqual(uni.get_channel(13), 3)


def _alte_regel(ch, fallback):
    """``open_value_of_channel`` VOR ENG-27 — nur fuer die Gegenprobe."""
    if ch is None:
        return fallback
    shutter = (ch.attribute or "") in ("shutter", "strobe")
    for rng in ch.ranges or ():
        art = shutter_bereich_art(rng) if shutter else (rng.kind or "").lower()
        if art == "open":
            return max(0, min(255, (int(rng.range_from) + int(rng.range_to)) // 2))
    if shutter and ist_strobe_kanal_ohne_bereiche(ch):
        return 0
    return int(ch.highlight_value) if ch.highlight_value is not None else fallback


class GegenprobeMitgelieferteBibliothek(unittest.TestCase):
    """Keine mitgelieferte Geraetedefinition aendert ihren „offen"-Wert."""

    def test_shutter_und_rad_unveraendert(self):
        from src.core.database.models import FixtureChannel
        motor = frische_library(self)
        with Session(motor) as s:
            kanaele = s.execute(select(FixtureChannel).options(
                selectinload(FixtureChannel.ranges))).scalars().all()
            gezaehlt = {"shutter": 0, "rad": 0}
            abweichend = []
            for ch in kanaele:
                if ch.attribute in ("shutter", "strobe"):
                    gezaehlt["shutter"] += 1
                elif ch.attribute in ("color_wheel", "colour_wheel", "color"):
                    gezaehlt["rad"] += 1
                else:
                    continue
                if open_value_of_channel(ch, KEIN) != _alte_regel(ch, KEIN):
                    abweichend.append((ch.mode_id, ch.channel_number, ch.name))
        self.assertGreater(gezaehlt["shutter"], 20, gezaehlt)   # Vorbedingung
        self.assertGreater(gezaehlt["rad"], 10, gezaehlt)
        self.assertEqual(abweichend, [])


if __name__ == "__main__":
    unittest.main()

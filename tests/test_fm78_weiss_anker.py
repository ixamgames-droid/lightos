"""FM-78: ``weiss_setzen`` (FM-41) verankert die uebrigen Weiss-Segmente auf
ihrem WIRKSAMEN Vorwert — dem gespiegelten Basiswert (``color_w``) bzw. ihrem
Standardwert —, nicht auf 0. Gleiche Antwort wie ``dimmer_key_setzen`` seit
FM-62. Ohne den Fix gingen die anderen Weiss-Segmente beim Regeln eines
Segments ungefragt dunkel.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as AS                       # noqa: E402


def _ch(attr, nr, default=0):
    return N(attribute=attr, channel_number=nr, default_value=default,
             highlight_value=255, ranges=[], name=attr, segment=None)


def _geraet(w_defaults=(0, 0, 0)):
    """Vier RGB-Koepfe, drei eigene Weiss-Segmente (CH13..CH15)."""
    k, nr = [], 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            k.append(_ch(a, nr))
            nr += 1
    for d in w_defaults:
        k.append(_ch("color_w", nr, d))
        nr += 1
    return k


class WeissAnkerVorwertTest(unittest.TestCase):

    def setUp(self):
        alt = AS.get_channels_for_patched
        self.addCleanup(setattr, AS, "get_channels_for_patched", alt)
        self.kanaele = _geraet()
        AS.get_channels_for_patched = lambda fx: self.kanaele
        fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
               fixture_profile_id=1, mode_name="m", head_mode="auto",
               channel_count=len(self.kanaele))
        self.st = AS.AppState.__new__(AS.AppState)
        self.st._patch_cache = [fx]
        self.st.programmer = {}
        self.st.set_programmer_value = (
            lambda fid, k, v: self.st.programmer.setdefault(fid, {})
            .__setitem__(k, int(v)))

    def _weiss_dmx(self):
        """Wie ``_flush_programmer_to_dmx``: Vorkommens-Schluessel, Rueckfall
        auf den Basis-Schluessel (Spiegel), sonst ``default_value``."""
        werte = {nr: v for nr, _k, v in AS.resolve_attr_channels(
            self.kanaele, self.st.programmer.get(1, {}))}
        std = {c.channel_number: c.default_value for c in self.kanaele}
        return [werte.get(nr, std[nr]) for nr in (13, 14, 15)]

    def test_segmente_vorhanden(self):
        self.assertEqual(self.st.weiss_programmer_key(1, 0), "color_w")
        self.assertIsNotNone(self.st.weiss_programmer_key(1, 2))

    def test_gespiegelter_basiswert_bleibt(self):
        self.st.set_programmer_value(1, "color_w", 128)
        self.assertEqual(self._weiss_dmx(), [128, 128, 128], "Spiegel vorher")
        self.assertTrue(self.st.weiss_setzen(1, 0, 255))
        self.assertEqual(self._weiss_dmx(), [255, 128, 128],
                         "uebrige Segmente behalten ihren wirksamen Wert")

    def test_anderes_segment_mit_basiswert(self):
        self.st.set_programmer_value(1, "color_w", 90)
        self.assertTrue(self.st.weiss_setzen(1, 1, 255))
        self.assertEqual(self._weiss_dmx(), [90, 255, 90])

    def test_ohne_basiswert_der_standardwert(self):
        self.kanaele = _geraet(w_defaults=(0, 200, 50))
        self.assertEqual(self._weiss_dmx(), [0, 200, 50], "vorher")
        self.assertTrue(self.st.weiss_setzen(1, 0, 255))
        self.assertEqual(self._weiss_dmx(), [255, 200, 50])

    def test_ohne_basiswert_standardwert_auch_fuer_basis(self):
        self.kanaele = _geraet(w_defaults=(70, 0, 0))
        self.assertTrue(self.st.weiss_setzen(1, 2, 255))
        self.assertEqual(self._weiss_dmx(), [70, 0, 255])

    def test_ohne_alles_weiter_0(self):
        self.assertTrue(self.st.weiss_setzen(1, 1, 255))
        self.assertEqual(self._weiss_dmx(), [0, 255, 0])

    def test_eigener_wert_bleibt_unangetastet(self):
        self.st.set_programmer_value(1, "color_w", 128)
        k2 = self.st.weiss_programmer_key(1, 2)
        self.st.set_programmer_value(1, k2, 33)
        self.assertTrue(self.st.weiss_setzen(1, 0, 255))
        self.assertEqual(self._weiss_dmx(), [255, 128, 33])


if __name__ == "__main__":
    unittest.main()

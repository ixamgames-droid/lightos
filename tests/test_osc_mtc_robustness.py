"""OSC-04 + MTC-02 (aus AUD-08): Robustheit von OSC-Blackout-Coercion und der
MTC-Quarter-Frame-Vollstaendigkeitspruefung."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.osc.osc_server import OscServer
from src.core.timecode.mtc_reader import MTCReader


class OscBlackoutCoercionTest(unittest.TestCase):
    """OSC-04: /blackout darf bei STRING-Args nicht invertieren (bool('0')==True)."""

    def test_string_off_tokens_are_false(self):
        for tok in ("0", "off", "false", "no", "", " Off ", "FALSE"):
            self.assertFalse(OscServer._as_on(tok), f"{tok!r} sollte AUS sein")

    def test_string_on_tokens_are_true(self):
        for tok in ("1", "on", "true", "yes", "go"):
            self.assertTrue(OscServer._as_on(tok), f"{tok!r} sollte AN sein")

    def test_typed_numeric_args(self):
        # Getypte OSC-int/float (TouchOSC/Lemur): 0/0.0 aus, 1/1.0 an, Schwelle 0.5.
        self.assertFalse(OscServer._as_on(0))
        self.assertFalse(OscServer._as_on(0.0))
        self.assertFalse(OscServer._as_on(0.4))
        self.assertTrue(OscServer._as_on(1))
        self.assertTrue(OscServer._as_on(1.0))
        self.assertTrue(OscServer._as_on(0.6))
        self.assertFalse(OscServer._as_on(False))
        self.assertTrue(OscServer._as_on(True))


class MtcCompletenessGateTest(unittest.TestCase):
    """MTC-02: nur ein vollstaendiger 0..7-Quarter-Frame-Satz feuert; ein
    unvollstaendiger (Mid-Stream-Attach / verlorenes Piece) wird verworfen, damit
    kein Frame aus gemischten alten+neuen Nibbles entsteht."""

    def _qf(self, reader, piece, value=0):
        reader._handle_quarter_frame((piece << 4) | (value & 0x0F))

    def test_incomplete_group_does_not_fire(self):
        r = MTCReader()
        fired = []
        r.subscribe(lambda h, m, s, f: fired.append((h, m, s, f)))
        for p in (3, 4, 5, 6, 7):          # Mid-Stream-Attach: piece 0..2 fehlen
            self._qf(r, p)
        self.assertEqual(fired, [])

    def test_missing_middle_piece_does_not_fire(self):
        r = MTCReader()
        fired = []
        r.subscribe(lambda h, m, s, f: fired.append((h, m, s, f)))
        for p in (0, 1, 2, 4, 5, 6, 7):    # piece 3 verloren
            self._qf(r, p)
        self.assertEqual(fired, [])

    def test_full_group_fires_once_with_decoded_time(self):
        r = MTCReader()
        fired = []
        r.subscribe(lambda h, m, s, f: fired.append((h, m, s, f)))
        # Vollstaendiger Satz 0..7: setze Sekunden = 10 (buf[2] low nibble=10),
        # alles andere 0. seconds = buf[2] | ((buf[3]&0x03)<<4) = 10.
        vals = {0: 0, 1: 0, 2: 10, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}
        for p in range(8):
            self._qf(r, p, vals[p])
        self.assertEqual(len(fired), 1)
        h, m, s, f = fired[0]
        self.assertEqual(s, 10)            # Sekunden korrekt dekodiert

    def test_recovers_after_incomplete_then_complete(self):
        r = MTCReader()
        fired = []
        r.subscribe(lambda h, m, s, f: fired.append((h, m, s, f)))
        for p in (5, 6, 7):                # unvollstaendig -> kein Feuern
            self._qf(r, p)
        for p in range(8):                 # danach voller Satz -> genau ein Feuern
            self._qf(r, p)
        self.assertEqual(len(fired), 1)


if __name__ == "__main__":
    unittest.main()

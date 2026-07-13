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


class MtcFrameWrapTest(unittest.TestCase):
    """MTC-01: die +2-Frame-Korrektur darf die Frame-Nr nicht ueber fps treiben —
    Ueberlauf muss sauber in Sekunden/Minuten/Stunden getragen werden, sodass immer
    0 <= frame < fps gilt (inkl. Drop-Frame 29.97)."""

    def _send_full_frame(self, reader, h, m, s, f, fps_code):
        """Sende einen vollstaendigen 0..7-Quarter-Frame-Satz fuer h:m:s:f."""
        pieces = [
            f & 0x0F,                                   # 0: frames LS
            (f >> 4) & 0x01,                            # 1: frames MS (1 bit)
            s & 0x0F,                                   # 2: seconds LS
            (s >> 4) & 0x03,                            # 3: seconds MS
            m & 0x0F,                                   # 4: minutes LS
            (m >> 4) & 0x03,                            # 5: minutes MS
            h & 0x0F,                                   # 6: hours LS
            ((h >> 4) & 0x01) | ((fps_code & 0x03) << 1),  # 7: hours MS + fps code
        ]
        for piece, value in enumerate(pieces):
            reader._handle_quarter_frame((piece << 4) | (value & 0x0F))

    def _fire_and_get(self, h, m, s, f, fps_code):
        r = MTCReader()
        fired = []
        r.subscribe(lambda *a: fired.append(a))
        self._send_full_frame(r, h, m, s, f, fps_code)
        self.assertEqual(len(fired), 1, "voller Satz sollte genau einmal feuern")
        return r, fired[0]

    def test_frame_wrap_30fps(self):
        # 30 fps (code 3), frame 29 -> +2 = 31 muss auf f=1, s+1 wrappen.
        r, (h, m, s, f) = self._fire_and_get(0, 0, 0, 29, 3)
        self.assertTrue(0 <= f < r.fps(), f"frame {f} nicht in [0,{r.fps()})")
        self.assertEqual((h, m, s, f), (0, 0, 1, 1))

    def test_frame_wrap_carries_minute_hour_25fps(self):
        # 25 fps (code 1), 01:59:59:24 -> +2 traegt bis in die Stunde.
        r, (h, m, s, f) = self._fire_and_get(1, 59, 59, 24, 1)
        self.assertTrue(0 <= f < r.fps())
        self.assertEqual((h, m, s, f), (2, 0, 0, 1))

    def test_no_wrap_when_in_range(self):
        # 30 fps, frame 10 -> +2 = 12, kein Carry.
        r, (h, m, s, f) = self._fire_and_get(0, 0, 0, 10, 3)
        self.assertEqual((h, m, s, f), (0, 0, 0, 12))
        self.assertTrue(0 <= f < r.fps())

    def test_dropframe_skips_frames_0_1_on_minute(self):
        # 29.97 Drop-Frame (code 2): Carry auf ss=00 einer Nicht-10er-Minute ->
        # Frame 0/1 existieren nicht, muss auf 2/3 gehoben werden.
        r, (h, m, s, f) = self._fire_and_get(0, 4, 59, 29, 2)
        self.assertEqual((h, m, s), (0, 5, 0))
        self.assertEqual(f, 3)             # 29+2=31 -> f=1 -> Drop -> 3
        self.assertTrue(0 <= f < 30)

    def test_dropframe_keeps_frames_on_tenth_minute(self):
        # Auf jeder 10. Minute werden Frame 0/1 NICHT gedroppt.
        r, (h, m, s, f) = self._fire_and_get(0, 9, 59, 29, 2)
        self.assertEqual((h, m, s, f), (0, 10, 0, 1))

    def test_all_fps_codes_stay_in_range(self):
        # Fuer jeden fps-Code bleibt eine grenznahe Frame-Nr nach +2 im Bereich.
        for code, fps in ((0, 24), (1, 25), (2, 30), (3, 30)):
            r, (h, m, s, f) = self._fire_and_get(0, 0, 0, fps - 1, code)
            self.assertTrue(0 <= f < fps, f"code {code}: frame {f} out of range")


if __name__ == "__main__":
    unittest.main()

"""MTC-03: time()/format() lesen den (h, m, s, f)-Satz konsistent unter dem
Lock, den der Writer nutzt — kein Torn-Read fuer Poll-Consumer (ein Reader darf
nie h/m vom alten und s/f vom neuen Frame mischen)."""
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.timecode.mtc_reader import MTCReader


def _send_full_frame_sysex(reader, h, m, s, f, fps_code=1):
    """Setze h:m:s:f atomar via MTC Full-Frame SysEx (F0 7F cc 01 01 hh mm ss ff F7).
    Der SysEx-Pfad uebernimmt die Werte unveraendert (keine +2-Korrektur)."""
    hh_byte = ((fps_code & 0x03) << 5) | (h & 0x1F)
    msg = [0xF0, 0x7F, 0x7F, 0x01, 0x01, hh_byte, m, s, f, 0xF7]
    reader._on_raw((msg, 0.0))


class MtcConsistentReadTest(unittest.TestCase):
    """(a) Korrektheit: nach einem gesetzten Frame liefern time()/format() genau
    diesen Wert."""

    def test_time_and_format_reflect_set_frame(self):
        r = MTCReader()
        _send_full_frame_sysex(r, 1, 2, 3, 4)
        self.assertEqual(r.time(), (1, 2, 3, 4))
        self.assertEqual(r.format(), "01:02:03:04")

    def test_time_and_format_reflect_updated_frame(self):
        r = MTCReader()
        _send_full_frame_sysex(r, 1, 2, 3, 4)
        _send_full_frame_sysex(r, 11, 22, 33, 20)
        self.assertEqual(r.time(), (11, 22, 33, 20))
        self.assertEqual(r.format(), "11:22:33:20")

    def test_quarter_frame_path_still_consistent(self):
        # Vollstaendiger 0..7-Quarter-Frame-Satz: seconds=10, Rest 0. Der QF-Pfad
        # addiert +2 Frames (adj_frames), Rest bleibt 0.
        r = MTCReader()
        vals = {0: 0, 1: 0, 2: 10, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}
        for p in range(8):
            r._handle_quarter_frame((p << 4) | vals[p])
        h, m, s, f = r.time()
        self.assertEqual((h, m, s), (0, 0, 10))
        self.assertEqual(f, 2)              # 0 + 2 (Frame-Korrektur)
        self.assertEqual(r.format(), "00:00:10:02")


class MtcConcurrentReadSmokeTest(unittest.TestCase):
    """(b) Nebenlaeufigkeits-Smoke: waehrend ein Writer-Thread in Schleife zwischen
    zwei Vollframes wechselt, darf ein Reader-Thread nie ein gemischtes h:m:s:f
    sehen, das keinem gesetzten Frame entspricht."""

    def test_reader_never_sees_torn_frame(self):
        r = MTCReader()
        # Zwei Frames, die sich in ALLEN vier Komponenten unterscheiden — ein
        # Torn-Read (Mix aus beiden) landet zwangslaeufig ausserhalb dieser Menge.
        frame_a = (1, 2, 3, 4)
        frame_b = (11, 22, 33, 20)
        valid = {frame_a, frame_b}
        # Ein neutraler Startframe (0,0,0,0) ist ebenfalls gueltig (vor erstem Write).
        valid.add((0, 0, 0, 0))

        stop = threading.Event()
        errors = []

        def writer():
            i = 0
            while not stop.is_set():
                h, m, s, f = frame_a if (i & 1) else frame_b
                _send_full_frame_sysex(r, h, m, s, f)
                i += 1

        def reader():
            while not stop.is_set():
                t = r.time()
                if t not in valid:
                    errors.append(("time", t))
                    return
                # format() muss zum selben konsistenten Satz passen
                fs = r.format()
                h, m, s, f = t
                # (format kann einen neueren Frame sehen — pruefe nur, dass er
                # selbst ein gueltiger, nicht gemischter Frame ist)
                parts = tuple(int(x) for x in fs.split(":"))
                if parts not in valid:
                    errors.append(("format", parts))
                    return

        writers = [threading.Thread(target=writer) for _ in range(2)]
        readers = [threading.Thread(target=reader) for _ in range(3)]
        for t in writers + readers:
            t.start()
        # Kurzer Lauf reicht fuer viele tausend Wechsel.
        threading.Event().wait(0.5)
        stop.set()
        for t in writers + readers:
            t.join(timeout=2.0)

        self.assertEqual(errors, [], f"Torn-Read erkannt: {errors[:5]}")


if __name__ == "__main__":
    unittest.main()

"""F-15 (Tier 0): tag_reader liest BPM aus eingebetteten ID3v2-/MP4-Tags.

Die Test-Dateien werden byte-genau synthetisiert (kein echtes Audio nötig)."""
import os
import struct
import tempfile
import unittest

from src.core.audio.tag_reader import read_tag_bpm


def _syncsafe(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _id3v23_tbpm(bpm_text: str) -> bytes:
    body = b"\x00" + bpm_text.encode("latin-1")          # encoding 0 + Zahl
    frame = b"TBPM" + struct.pack(">I", len(body)) + b"\x00\x00" + body
    return b"ID3" + bytes([3, 0]) + b"\x00" + _syncsafe(len(frame)) + frame


def _atom(typ: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + typ + payload


def _mp4_tmpo(value: int) -> bytes:
    data = _atom(b"data", b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00"
                 + struct.pack(">H", value))
    tmpo = _atom(b"tmpo", data)
    ilst = _atom(b"ilst", tmpo)
    meta = _atom(b"meta", b"\x00\x00\x00\x00" + ilst)    # Full-Box
    udta = _atom(b"udta", meta)
    moov = _atom(b"moov", udta)
    ftyp = _atom(b"ftyp", b"M4A \x00\x00\x00\x00")
    return ftyp + moov


def _write(suffix: str, data: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


class TagReaderTest(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _mk(self, suffix, data):
        p = _write(suffix, data)
        self._paths.append(p)
        return p

    def test_id3v23_tbpm(self):
        p = self._mk(".mp3", _id3v23_tbpm("128") + b"\xff\xfb\x00" * 4)
        self.assertEqual(read_tag_bpm(p), 128.0)

    def test_id3_decimal_bpm(self):
        p = self._mk(".mp3", _id3v23_tbpm("174.5"))
        self.assertAlmostEqual(read_tag_bpm(p), 174.5)

    def test_mp4_tmpo(self):
        p = self._mk(".m4a", _mp4_tmpo(140))
        self.assertEqual(read_tag_bpm(p), 140.0)

    def test_mp3_without_tag_is_zero(self):
        p = self._mk(".mp3", b"\xff\xfb\x90\x00" * 16)   # nur „Audio", kein ID3
        self.assertEqual(read_tag_bpm(p), 0.0)

    def test_unknown_extension_is_zero(self):
        p = self._mk(".wav", _id3v23_tbpm("128"))        # .wav -> nicht zuständig
        self.assertEqual(read_tag_bpm(p), 0.0)

    def test_mp4_without_moov_is_zero(self):
        p = self._mk(".m4a", _atom(b"ftyp", b"M4A \x00") + b"\x00" * 32)
        self.assertEqual(read_tag_bpm(p), 0.0)

    def test_nonexistent_file_is_zero(self):
        self.assertEqual(read_tag_bpm("does/not/exist.mp3"), 0.0)

    def test_garbage_is_zero(self):
        p = self._mk(".mp3", b"\x00\x01\x02\x03random junk bytes")
        self.assertEqual(read_tag_bpm(p), 0.0)


if __name__ == "__main__":
    unittest.main()

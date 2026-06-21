"""F-15 (Tier 2): offline_analysis.analyze_bpm auf synthetischen Klick-Tracks.

Erzeugt einen Bass-Klick alle 60/BPM Sekunden und prüft die Schätzung ±2 BPM,
inkl. Oktav-Faltung (64-BPM-Klick → 128, „64 wird nicht für 128 zurückgegeben")."""
import os
import tempfile
import unittest
import wave

from src.core.audio import offline_analysis as oa


def _click_wav(path: str, bpm: float, sr: int = 44100, dur: float = 8.0):
    import numpy as np
    n = int(sr * dur)
    x = np.zeros(n, dtype=np.float32)
    period = int(sr * 60.0 / bpm)
    blen = int(sr * 0.05)                                  # 50 ms Bass-Burst
    t = np.arange(blen)
    burst = (np.sin(2 * np.pi * 60.0 * t / sr).astype(np.float32)
             * np.linspace(1.0, 0.0, blen).astype(np.float32) * 0.8)
    for start in range(0, n - blen, period):
        x[start:start + blen] += burst
    pcm = np.clip(x, -1, 1)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


@unittest.skipUnless(oa.HAS_NUMPY, "numpy nicht verfügbar")
class AnalyzeBpmTest(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _wav(self, bpm):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        self._paths.append(path)
        _click_wav(path, bpm)
        return path

    def test_detects_128(self):
        self.assertAlmostEqual(oa.estimate_bpm_from_file(self._wav(128)), 128, delta=2)

    def test_detects_150(self):
        self.assertAlmostEqual(oa.estimate_bpm_from_file(self._wav(150)), 150, delta=2)

    def test_octave_fold_64_becomes_128(self):
        # 64-BPM-Klick wird in den Dance-Bereich gefaltet -> ~128, NICHT 64.
        bpm = oa.estimate_bpm_from_file(self._wav(64))
        self.assertGreater(bpm, 90)
        self.assertAlmostEqual(bpm, 128, delta=3)

    def test_non_wav_is_zero(self):
        self.assertEqual(oa.estimate_bpm_from_file("x.mp3"), 0.0)

    def test_bad_path_is_zero(self):
        self.assertEqual(oa.estimate_bpm_from_file("nope/missing.wav"), 0.0)

    def test_too_short_is_zero(self):
        import numpy as np
        self.assertEqual(oa.analyze_bpm(np.zeros(100, dtype=np.float32), 44100), 0.0)

    def test_silence_is_zero(self):
        import numpy as np
        self.assertEqual(oa.analyze_bpm(np.zeros(44100 * 3, dtype=np.float32), 44100), 0.0)


class NoSamplesTest(unittest.TestCase):
    def test_none_samples(self):
        self.assertEqual(oa.analyze_bpm(None, 44100), 0.0)


if __name__ == "__main__":
    unittest.main()

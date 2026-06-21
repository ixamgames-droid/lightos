"""Beat-Detector mit Bass-Band-Energy + Adaptive Threshold."""
from __future__ import annotations
import numpy as np
import time
import threading
from collections import deque

SAMPLE_RATE = 44100


class BeatDetector:
    """
    Erkennt Beats aus Audio-Chunks:
    1. FFT auf Chunk
    2. Energie im Bass-Band (40-180 Hz)
    3. Vergleich mit gleitendem Mittelwert
    4. Bei Schwellenueberschreitung + Mindest-Abstand: Beat
    5. Berechnet BPM aus den letzten Beat-Intervallen
    """
    def __init__(self):
        self.sensitivity: float = 1.3   # 1.0=immer, 2.0=streng (Faktor ueber Durchschnitt)
        self.band_low_hz: int = 40
        self.band_high_hz: int = 180
        self.min_beat_interval: float = 0.25  # max 240 BPM
        self.silence_reset_s: float = 3.0     # nach so langer Stille den BPM-Lock verwerfen

        # WP-2: BPM-Aufbereitung (Oktav-Faltung + Glaettung) fuer die oeffentliche BPM
        self.min_bpm: int = 60          # untere Grenze der Ziel-Range (Oktav-Faltung)
        self.max_bpm: int = 200         # obere Grenze der Ziel-Range
        self.smoothing: float = 0.3     # EMA-Glaettung 0..1 (hoeher = traeger)

        self._energy_history = deque(maxlen=43)  # ~1 sec @ 1024 samples / 44100
        self._beat_times = deque(maxlen=16)
        self._last_beat_time: float = 0.0
        self._beat_callbacks: list = []
        self._lock = threading.Lock()
        self._latest_bands = np.zeros(8)  # 8-band spectrum for visualization

        # WP-2: geglaetteter BPM-Wert + Verlauf der gefalteten Schaetzungen (fuer Confidence)
        self._bpm_smoothed: float = 0.0
        self._bpm_estimates = deque(maxlen=8)  # Verlauf der gefalteten BPM-Schaetzungen (fuer Confidence)

    def subscribe(self, cb):
        """Callback wird bei jedem erkannten Beat aufgerufen (kein arg)."""
        if cb not in self._beat_callbacks:
            self._beat_callbacks.append(cb)

    def unsubscribe(self, cb):
        if cb in self._beat_callbacks:
            self._beat_callbacks.remove(cb)

    def set_sensitivity(self, value: float):
        """0.5 - 3.0. Niedriger = empfindlicher (mehr Beats), hoeher = strenger."""
        self.sensitivity = max(0.5, min(3.0, value))

    def set_smoothing(self, value: float):
        """0.0 - 1.0. Hoeher = traegere/stabilere BPM (staerkere EMA-Glaettung)."""
        self.smoothing = max(0.0, min(1.0, float(value)))

    def set_bounds(self, min_bpm, max_bpm):
        """Ziel-Range fuer die Oktav-Faltung. Vertauscht falls verkehrt, je 20..400."""
        lo = int(min_bpm)
        hi = int(max_bpm)
        if lo > hi:
            lo, hi = hi, lo
        self.min_bpm = max(20, min(400, lo))
        self.max_bpm = max(20, min(400, hi))

    def get_bpm(self) -> float:
        """Aufbereitete BPM: Oktav-Faltung in [min_bpm, max_bpm] + EMA-Glaettung."""
        raw = self.get_raw_bpm()
        if raw <= 0:
            return 0.0
        # Oktav-Faltung in die Ziel-Range, mit Kontinuitaet zum bisherigen Wert
        # (verhindert Oktav-Springen bei Half/Double-Time-Passagen).
        folded = self._fold_octave(raw)
        with self._lock:
            self._bpm_estimates.append(folded)
            if self._bpm_smoothed <= 0:
                self._bpm_smoothed = folded
            else:
                self._bpm_smoothed = ((1.0 - self.smoothing) * self._bpm_smoothed
                                      + self.smoothing * folded)
            result = self._bpm_smoothed
        return max(float(self.min_bpm), min(float(self.max_bpm), result))

    def _fold_octave(self, raw: float) -> float:
        """Faltet ``raw`` in [min_bpm, max_bpm]; existiert bereits ein
        geglaetteter Wert, wird die Oktave gewaehlt, die ihm am naechsten ist
        (Kontinuitaet statt Hin-und-Her-Springen bei Half/Double-Time)."""
        base = raw
        for _ in range(6):
            if base < self.min_bpm:
                base *= 2.0
            elif base > self.max_bpm:
                base /= 2.0
            else:
                break
        smoothed = self._bpm_smoothed
        if smoothed > 0:
            best, best_d = base, abs(base - smoothed)
            c = base
            for _ in range(3):
                c /= 2.0
                if c < self.min_bpm:
                    break
                if abs(c - smoothed) < best_d:
                    best, best_d = c, abs(c - smoothed)
            c = base
            for _ in range(3):
                c *= 2.0
                if c > self.max_bpm:
                    break
                if abs(c - smoothed) < best_d:
                    best, best_d = c, abs(c - smoothed)
            base = best
        return base

    def get_raw_bpm(self) -> float:
        """Rohe BPM aus den letzten Beat-Intervallen — robust via Median +
        Ausreisser-Verwerfung ueber ein kurzes, aktuelles Fenster.

        Reagiert schneller auf Tempowechsel als ein flacher Mittelwert ueber
        die ganze History und ignoriert verpasste/doppelte Onsets (deren
        Intervalle weit vom Median liegen). Weit geklemmt 20..400 BPM."""
        with self._lock:
            if len(self._beat_times) < 2:
                return 0.0
            times = list(self._beat_times)[-9:]   # kurzes, aktuelles Fenster
        intervals = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        intervals = [iv for iv in intervals if iv > 0.01]
        if not intervals:
            return 0.0
        s = sorted(intervals)
        n = len(s)
        median = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
        if median <= 0:
            return 0.0
        # nur Intervalle nahe am Median mitteln (±35 %) → Ausreisser raus
        inliers = [iv for iv in intervals if abs(iv - median) <= 0.35 * median]
        use = inliers or intervals
        avg = sum(use) / len(use)
        if avg < 0.01:
            return 0.0
        return max(20.0, min(400.0, 60.0 / avg))

    def get_confidence(self) -> float:
        """Stabilitaet der gefalteten BPM-Schaetzungen als Wert 0..1.

        Basiert bewusst auf den (oktav-gefalteten) Schaetzungen, NICHT auf der
        rohen Onset-Intervall-Varianz: Onsets sind keine Viertel-Beats, daher
        unterschaetzt die naive Varianz die Stabilitaet bei sauberer Musik.
        """
        with self._lock:
            estimates = list(self._bpm_estimates)
        if len(estimates) < 3:
            return 0.0
        mean = sum(estimates) / len(estimates)
        if mean <= 0:
            return 0.0
        var = sum((e - mean) ** 2 for e in estimates) / len(estimates)
        std = var ** 0.5
        return max(0.0, min(1.0, 1.0 - std / mean))

    def reset(self):
        """Beim Wechsel der Audio-Quelle: gesamten BPM-Zustand verwerfen."""
        with self._lock:
            self._beat_times.clear()
            self._energy_history.clear()
            self._bpm_smoothed = 0.0
            self._bpm_estimates.clear()

    def get_spectrum(self) -> np.ndarray:
        """8-Band Spektrum fuer Visualisierung."""
        with self._lock:
            return self._latest_bands.copy()

    def get_volume_level(self) -> float:
        """Aktueller Pegel 0..1."""
        with self._lock:
            return float(np.mean(self._latest_bands))

    def process_chunk(self, audio: np.ndarray):
        """Callback fuer AudioCapture - verarbeitet einen Chunk."""
        try:
            if len(audio) < 64:
                return

            # FFT
            window = np.hanning(len(audio))
            spectrum = np.abs(np.fft.rfft(audio * window))
            freqs = np.fft.rfftfreq(len(audio), 1.0 / SAMPLE_RATE)

            # Bass-Band Energie
            bass_mask = (freqs >= self.band_low_hz) & (freqs <= self.band_high_hz)
            bass_energy = float(np.sum(spectrum[bass_mask] ** 2))

            # 8-Band Spektrum (log-spaced) fuer Visualisierung
            band_edges = np.logspace(np.log10(40), np.log10(16000), 9)
            bands = np.zeros(8)
            for i in range(8):
                mask = (freqs >= band_edges[i]) & (freqs < band_edges[i + 1])
                if mask.any():
                    bands[i] = np.sqrt(np.mean(spectrum[mask] ** 2))
            # Normalize bands
            max_b = bands.max() if bands.max() > 0 else 1
            bands_normalized = np.clip(bands / max(max_b, 1e-3), 0, 1)

            with self._lock:
                self._latest_bands = bands_normalized

            # Adaptive Threshold
            self._energy_history.append(bass_energy)
            if len(self._energy_history) < 10:
                return
            avg_energy = float(np.mean(self._energy_history))
            threshold = avg_energy * self.sensitivity

            now = time.monotonic()
            # Stille-Re-Lock: nach laengerer Stille (kein Beat mehr) den
            # BPM-Zustand verwerfen, damit get_bpm nicht ewig die alte BPM
            # haelt und der naechste Einsatz frisch (ohne veraltete Intervalle,
            # die pre/post-Stille mischen) einrastet.
            if (self._beat_times and self._last_beat_time > 0
                    and now - self._last_beat_time > self.silence_reset_s):
                with self._lock:
                    self._beat_times.clear()
                    self._bpm_smoothed = 0.0
                    self._bpm_estimates.clear()

            if (bass_energy > threshold and
                    bass_energy > 0.01 and  # minimum absolute threshold
                    now - self._last_beat_time > self.min_beat_interval):

                self._last_beat_time = now
                with self._lock:
                    self._beat_times.append(now)

                # Notify subscribers
                for cb in list(self._beat_callbacks):
                    try:
                        cb()
                    except Exception as e:
                        print(f"[BeatDetector] callback error: {e}")

        except Exception as e:
            print(f"[BeatDetector] process error: {e}")


_detector: BeatDetector | None = None


def get_beat_detector() -> BeatDetector:
    global _detector
    if _detector is None:
        _detector = BeatDetector()
    return _detector

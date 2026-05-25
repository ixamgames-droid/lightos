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

        self._energy_history = deque(maxlen=43)  # ~1 sec @ 1024 samples / 44100
        self._beat_times = deque(maxlen=16)
        self._last_beat_time: float = 0.0
        self._beat_callbacks: list = []
        self._lock = threading.Lock()
        self._latest_bands = np.zeros(8)  # 8-band spectrum for visualization

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

    def get_bpm(self) -> float:
        """Aktuelle BPM-Schaetzung."""
        with self._lock:
            if len(self._beat_times) < 2:
                return 0.0
            intervals = [self._beat_times[i + 1] - self._beat_times[i]
                         for i in range(len(self._beat_times) - 1)]
            if not intervals:
                return 0.0
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval < 0.01:
                return 0.0
            bpm = 60.0 / avg_interval
            return max(20, min(300, bpm))

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

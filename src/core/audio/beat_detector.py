"""Live-Beat-Detektor: Spectral Flux + Autokorrelation, Beats aus dem Sample-Zaehler.

Verfahren (Details: onset_flux.py, tempo_tracker.py):
1. DC-Blocker/Hochpass 30 Hz -> Hann 1024 / Hop 512, unabhaengig von Chunkgroesse und Abtastrate.
2. Adaptives Whitening je Bin (2 s) -> Spectral Flux je log-Band, bandweise normiert (Onset-Huellkurve).
3. 6-s-Ring -> unbiased ACF + 4-fach-Kamm (Max-Filter an den Oberwellen) + Sub-Oktav-Strafe
   + Log-Normal-Prior 120 BPM -> Parabel (Details und Grenzfall Backbeat: tempo_tracker.py).
4. Konfidenz = Periodizitaet x Onset-Kontrast; Zustand no_signal / searching / locked, Totband 4 %,
   Haltezeiten 1 s (Oktave 3 s), Stille dreistufig 0,5 / 2 / 10 s.
5. Comb-Phasenfit (32 Phasen, 4 s) -> Beat-Vorhersage als Sample-Position; Callbacks nur im Zustand locked.
6. Alle Zeiten aus dem Sample-Zaehler (kein time.monotonic fuer Beats) -> Burst/Jitter der Chunks egal.

Messbank (synthetische Signale, 30 s, alt -> neu): Brumm mit Bassband-SNR 0 dB 104,5 BPM / 27 von
64 Treffern / 76 Fehlalarme -> 127,6 BPM / 56 von 64 / 0; Klick 140 halbiert (70,2) -> 140,0;
Chunks in 8er-Salven 15 von 64 -> 56 von 64 (wie Idealfall); ab dem Einrasten alle Beats
getroffen; Phasenfehler mittel -2..+11 ms, max 47 ms (Tempowechsel); CPU 0,41 ms je 1024er-Chunk
(alt 0,22). Reine Kicks/Klicks 60..200 BPM ohne Oktavfehler. Preis: Einrasten dauert nach
Start/Quellenwechsel ~3,8 s (Autokorrelation braucht ein gefuelltes Fenster), vorher werden
keine Beats gemeldet. Grenze: Kick jeder Beat + Snare 2/4 ab ~150 BPM rastet auf die halbe
Oktave (Bank 08l; x2 / Tempo-Bereich korrigieren, s. tempo_tracker.py).

Threads: ``process_chunk`` laeuft auf dem Capture-Thread; Getter lesen einen unveraenderlichen
``DetectorSnapshot`` (per Referenz veroeffentlicht), Setter arbeiten unter einem kleinen Lock.
Beat-Callbacks werden ausserhalb des Locks gerufen.
"""
from __future__ import annotations
import threading
import time
from collections import deque

import numpy as np

from src.core.audio.onset_flux import HighPass, FluxStream, WIN, HOP  # noqa: F401 (WIN/HOP re-export)
from src.core.audio.tempo_tracker import TempoTracker, DetectorSnapshot

SAMPLE_RATE = 44100


class BeatDetector:
    """Erkennt Tempo und Beats aus Audio-Chunks (siehe Modulkopf).

    Alte Schnittstelle bleibt: ``subscribe/unsubscribe``, ``get_bpm/get_raw_bpm/get_confidence``
    (reine Getter), ``get_spectrum``, ``get_volume_level``, ``reset``, ``set_bounds``,
    ``process_chunk``. ``set_sensitivity/set_smoothing`` speichern nur noch das Attribut
    (einmaliger Hinweis); ``band_low_hz/band_high_hz/min_beat_interval/silence_reset_s``
    sind wirkungslose Attribute fuer Altleser.
    Neu: ``snapshot()``, ``resync_phase()``, ``set_tempo_hint()``, ``set_octave_preference()``,
    ``set_beat_latency_ms()``, ``last_beat_time``.
    """
    SILENCE_DBFS = -72.0        # Stille-Gate auf dem 300-ms-Maximum des Chunk-RMS
    HUM_N = 8192                # FFT-Laenge der Brumm-Analyse (5,4 Hz bei 44,1 kHz)

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self._lock = threading.Lock()
        self._beat_callbacks: list = []
        # --- Alt-Attribute (Leser: bpm_settings, genre_presets, Bench; Tab „Audio Input" entfiel in BPM-10) ---
        self.sensitivity: float = 1.3
        self.smoothing: float = 0.3
        self.band_low_hz: int = 40
        self.band_high_hz: int = 180
        self.min_beat_interval: float = 0.25
        self.silence_reset_s: float = TempoTracker.SIL_RELEASE_S
        self.min_bpm: int = 60
        self.max_bpm: int = 200
        self._deprecated_printed: set = set()
        # --- neu ---
        self.beat_latency_ms: int = 0
        self.last_beat_time: float = 0.0    # Sekunden aus dem Sample-Zaehler
        self.sr = int(sample_rate)
        self._hp = HighPass(self.sr, 30.0)
        self._flux = FluxStream(self.sr, mode="whitened")
        self._tracker = TempoTracker(self.sr, self.min_bpm, self.max_bpm)
        self._hum_window = np.hanning(self.HUM_N).astype(np.float32)
        self._hum_freqs = np.fft.rfftfreq(self.HUM_N, 1.0 / self.sr)
        self._hum_band = (self._hum_freqs >= 30) & (self._hum_freqs <= 300)
        edges = np.logspace(np.log10(40), np.log10(min(16000, self.sr / 2)), 9)
        f = self._flux.freqs
        self._spec_idx = [(int(np.searchsorted(f, a)), int(np.searchsorted(f, b))) for a, b in zip(edges[:-1], edges[1:])]
        self._reset_state()
        self._publish()

    # ------------------------------------------------------------ Zustand
    def _reset_state(self):
        self._hp.reset()
        self._flux.reset()
        self._tracker.reset()
        self.sample_pos = 0
        self.last_beat_time = 0.0
        # Diagnose
        self._rms_dbfs = -100.0
        self._peak_dbfs = -100.0
        self._rms_ring = deque(maxlen=430)          # ~10 s bei 1024er Chunks
        self._rms_300: deque = deque()              # (n_samples, dbfs) der letzten 300 ms
        self._rms_300_n = 0
        self._clip_ring: deque = deque()            # (n_samples, clips, dc_sum) der letzten 1 s
        self._clip_n = 0
        self._clip_1s = 0
        self._dc_offset = 0.0
        self._hum_buf = np.zeros(self.HUM_N, np.float32)
        self._hum_fill = 0
        self._hum_hist: deque = deque(maxlen=5)
        self._hum_ratio = 0.0
        self._hum_hz = 0
        self._silent_s = 0.0
        self._signal_s = 0.0
        self._t_last_chunk = None
        self._t_start = None
        self._intervals: deque = deque(maxlen=43)
        self._expected_dt = 0.0
        self._jitter_ms = 0.0
        self._backlog_ms = 0.0

    def reset(self):
        """Beim Wechsel der Audio-Quelle: gesamten Zustand verwerfen (Tempo-Hinweis bleibt)."""
        with self._lock:
            self._reset_state()
            self._publish()

    # ------------------------------------------------------------ Callbacks
    def subscribe(self, cb):
        """Callback wird bei jedem Beat gerufen (kein arg) — nur im Zustand ``locked``."""
        with self._lock:
            if cb not in self._beat_callbacks:
                self._beat_callbacks.append(cb)

    def unsubscribe(self, cb):
        with self._lock:
            if cb in self._beat_callbacks:
                self._beat_callbacks.remove(cb)

    # ------------------------------------------------------------ Getter (rein)
    def snapshot(self) -> DetectorSnapshot:
        return self._snap

    def get_bpm(self) -> float:
        """Gerastetes Tempo (Totband/Hysterese); 0 vor dem ersten Lock / nach Stille."""
        return self._snap.bpm

    def get_raw_bpm(self) -> float:
        """Roh-Schaetzung der letzten Tempo-Analyse (Parabel), in [min_bpm, max_bpm] gefaltet."""
        return self._snap.bpm_raw

    def get_confidence(self) -> float:
        """Kalibrierte Konfidenz 0..1 (Periodizitaet x Onset-Kontrast)."""
        return self._snap.confidence

    def get_spectrum(self) -> np.ndarray:
        """8-Band Spektrum (log-Baender 40 Hz..16 kHz, auf Maximum normiert) fuer die Anzeige."""
        mag = self._flux.last_magnitude
        bands = np.zeros(8)
        for i, (a, b) in enumerate(self._spec_idx):
            if b > a:
                bands[i] = float(np.sqrt(np.mean(mag[a:b] ** 2)))
        mx = bands.max()
        return np.clip(bands / max(mx, 1e-3), 0.0, 1.0) if mx > 0 else bands

    def get_volume_level(self) -> float:
        """Pegel 0..1 aus dem RMS: (dBFS + 60) / 60 geklemmt."""
        return float(np.clip((self._snap.level_rms_dbfs + 60.0) / 60.0, 0.0, 1.0))

    # ------------------------------------------------------------ Setter
    def set_bounds(self, min_bpm, max_bpm):
        """Faltbereich fuer die Oktave (kein Klemmen des Ergebnisses). Vertauscht falls
        verkehrt, je 20..400."""
        lo, hi = int(min_bpm), int(max_bpm)
        if lo > hi:
            lo, hi = hi, lo
        lo = max(20, min(400, lo))
        hi = max(20, min(400, hi))
        with self._lock:
            self.min_bpm, self.max_bpm = lo, hi
            self._tracker.set_bounds(float(lo), float(max(hi, lo + 1)))
            self._publish()

    def _deprecated(self, name: str):
        if name not in self._deprecated_printed:
            self._deprecated_printed.add(name)
            print(f"[BeatDetector] {name}: veraltet, ohne Wirkung (Erkennung ist selbstkalibrierend)")

    def set_sensitivity(self, value: float):
        """Veraltet: wirkungslos, Wert bleibt lesbar (Altleser)."""
        self.sensitivity = max(0.5, min(3.0, float(value)))
        self._deprecated("set_sensitivity")

    def set_smoothing(self, value: float):
        """Veraltet: wirkungslos, Wert bleibt lesbar (Altleser)."""
        self.smoothing = max(0.0, min(1.0, float(value)))
        self._deprecated("set_smoothing")

    def set_tempo_hint(self, bpm):
        """Suche um ``bpm`` einschraenken (Prior sigma 0,15 Oktaven) und die Oktave der
        Rastung sofort zum Hinweis falten; None = frei."""
        with self._lock:
            self._tracker.set_tempo_hint(float(bpm) if bpm else None)
            self._publish()

    def set_octave_preference(self, step: int):
        """Rastung x2 (step > 0) bzw. x0,5 (step < 0) innerhalb der Grenzen."""
        with self._lock:
            self._tracker.set_octave_preference(int(step))
            self._publish()

    def set_beat_latency_ms(self, ms: int):
        """Positiv = Beat-Callback frueher (Vorhersage laeuft der Wiedergabe voraus)."""
        with self._lock:
            self.beat_latency_ms = int(ms)
            self._publish()

    def resync_phase(self):
        """Beat-Raster auf 'jetzt' (1. TAP)."""
        with self._lock:
            self._tracker.resync_phase(self.sample_pos)
            self._publish()

    def _inject_tempo(self, bpm: float):
        """Test-Hook: Detektor in den Zustand ``locked`` mit Tempo ``bpm`` versetzen, ohne
        Audio (ersetzt das fruehere Fuellen von ``_beat_times``). Roh = ``bpm`` wie geliefert,
        ``get_bpm()`` = in die Grenzen gefaltet, Konfidenz 1."""
        with self._lock:
            self._tracker.inject_tempo(float(bpm), self.sample_pos)
            self._publish()

    # ------------------------------------------------------------ Verarbeitung (Capture-Thread)
    def process_chunk(self, audio: np.ndarray):
        """Callback fuer AudioCapture — beliebige Chunk-Laenge, float32 mono."""
        try:
            x = np.asarray(audio, dtype=np.float32)
            if x.ndim > 1:
                x = x.mean(axis=1)
            if x.size == 0:
                return
            fire = 0
            with self._lock:
                self._diagnostics(x)
                y = self._hp.process(x)
                flux = self._flux.push(y)
                self.sample_pos += int(x.size)
                tr = self._tracker
                est = tr.push(flux, self._silent_s, self._signal_s)
                lat = self.beat_latency_ms / 1000.0 * self.sr
                while fire < 2 and tr.beat_due(self.sample_pos, lat):
                    fire += 1
                if fire:
                    self.last_beat_time = tr.last_beat_time
                if est or tr.changed:
                    self._publish()
                cbs = list(self._beat_callbacks) if fire else ()
            for _ in range(fire):
                for cb in cbs:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[BeatDetector] callback error: {e}")
        except Exception as e:
            print(f"[BeatDetector] process error: {e}")

    def _diagnostics(self, x: np.ndarray):
        n = int(x.size)
        dt = n / self.sr
        now = time.monotonic()
        if self._t_start is None:
            self._t_start = now
        if self._t_last_chunk is not None:
            self._intervals.append(now - self._t_last_chunk)
        self._t_last_chunk = now
        self._expected_dt = dt
        self._backlog_ms = max(0.0, (now - self._t_start) - self.sample_pos / self.sr) * 1000.0
        xd = x.astype(np.float64)
        rms = float(np.sqrt(np.dot(xd, xd) / n))
        self._rms_dbfs = 20.0 * np.log10(rms) if rms > 1e-5 else -100.0
        ax = np.abs(x)
        peak = float(ax.max())
        self._peak_dbfs = 20.0 * np.log10(peak) if peak > 1e-5 else -100.0
        self._rms_ring.append(self._rms_dbfs)
        # Clip + DC ueber 1 s
        self._clip_ring.append((n, int(np.count_nonzero(ax >= 0.99)), float(xd.sum())))
        self._clip_n += n
        while self._clip_n - self._clip_ring[0][0] >= self.sr and len(self._clip_ring) > 1:
            self._clip_n -= self._clip_ring.popleft()[0]
        self._clip_1s = sum(c for _, c, _ in self._clip_ring)
        self._dc_offset = sum(d for _, _, d in self._clip_ring) / max(1, self._clip_n)
        # Brumm: 8192er FFT, 50 vs 60 Hz, Schmalbandigkeit, Minimum ueber 5 Bloecke
        k = min(n, self.HUM_N - self._hum_fill)
        self._hum_buf[self._hum_fill:self._hum_fill + k] = x[:k]
        self._hum_fill += k
        if self._hum_fill >= self.HUM_N:
            self._hum_fill = 0
            self._hum_analyze()
        # Stille-Zaehler auf dem 300-ms-Maximum des RMS
        self._rms_300.append((n, self._rms_dbfs))
        self._rms_300_n += n
        while self._rms_300_n - self._rms_300[0][0] >= 0.3 * self.sr and len(self._rms_300) > 1:
            self._rms_300_n -= self._rms_300.popleft()[0]
        if max(v for _, v in self._rms_300) < self.SILENCE_DBFS:
            self._silent_s += dt
        else:
            self._silent_s = 0.0
            self._signal_s += dt

    def _hum_analyze(self):
        mag2 = np.abs(np.fft.rfft(self._hum_buf * self._hum_window)) ** 2
        band = float(mag2[self._hum_band].sum()) + 1e-12
        best, best_hz = 0.0, 0
        for f0 in (50, 60):
            e_n, e_w = 0.0, 0.0
            for h in (1, 2, 3):
                c = int(round(f0 * h * self.HUM_N / self.sr))
                e_n += float(mag2[c - 1:c + 2].sum())
                e_w += float(mag2[c - 6:c + 7].sum())
            narrow = e_n / (e_w + 1e-12)          # Brumm ~1, Kick mit Pitch-Drop breit -> klein
            val = (e_n / band) * float(np.clip((narrow - 0.5) / 0.4, 0.0, 1.0))
            if val > best:
                best, best_hz = val, f0
        self._hum_hist.append(min(1.0, best))
        self._hum_ratio = float(min(self._hum_hist))   # Brumm ist stationaer: Minimum ueber ~0,9 s
        self._hum_hz = best_hz if self._hum_ratio >= 0.05 else 0

    # ------------------------------------------------------------ Snapshot
    def _publish(self):
        tr = self._tracker
        tr.changed = False
        if len(self._intervals) >= 4:
            iv = np.fromiter(self._intervals, dtype=np.float64)
            self._jitter_ms = float(np.percentile(np.abs(iv - self._expected_dt), 95) * 1000.0)
        noise = float(np.percentile(np.fromiter(self._rms_ring, dtype=np.float64), 5)) if self._rms_ring else -100.0
        self._snap = DetectorSnapshot(
            sample_pos=int(self.sample_pos), sample_rate=self.sr, state=tr.state,
            hold_stage=int(tr.hold_stage), bpm=float(tr.bpm), bpm_raw=float(tr.bpm_raw),
            confidence=float(tr.conf), alt_bpm=float(tr.alt_bpm), alt_score=float(tr.alt_score),
            tempo_hint=tr.tempo_hint, next_beat_sample=int(tr.next_beat_sample),
            beat_latency_ms=int(self.beat_latency_ms), window_s=float(tr.MEM_S),
            window_filled_s=float(min(tr.MEM_S, tr.frames_filled / tr.fps)),
            signal_s=float(self._signal_s), level_rms_dbfs=float(self._rms_dbfs),
            peak_dbfs=float(self._peak_dbfs), clip_1s=int(self._clip_1s),
            noise_floor_dbfs=noise, hum_ratio=float(self._hum_ratio), hum_hz=int(self._hum_hz),
            dc_offset=float(self._dc_offset), backlog_ms=float(self._backlog_ms),
            jitter_ms=float(self._jitter_ms), onset_contrast=float(tr.onset_contrast),
            phase_ok=bool(tr.phase_ok))


_detector: BeatDetector | None = None


def get_beat_detector() -> BeatDetector:
    global _detector
    if _detector is None:
        _detector = BeatDetector()
    return _detector

"""Onset-Huellkurve per Spectral Flux — streambar (Live) und als Batch (Offline).

Zwei Betriebsarten derselben Kette Hann(win) / Hop hop / |rfft|:

* ``mode="log1p"`` — log-komprimierte Magnitude, halbweg-gleichgerichtete
  1. Differenz, Summe ueber alle Bins. Das ist **mathematisch identisch** zu
  ``onset_envelope`` (frueher in ``offline_timeline``): frameweises Streaming
  liefert bitgleich dieselben Werte wie der Batch, unabhaengig davon, wie die
  Samples in Chunks zerlegt ankommen.
* ``mode="whitened"`` — adaptives Whitening (Stowell/Plumbley: jeder Bin wird
  auf sein eigenes, langsam abklingendes Maximum normiert), danach Flux je
  log-Band, jedes Band auf seinen eigenen laufenden Mittelwert normiert und nur
  der Ueberschuss ueber diesen Mittelwert gezaehlt. Dadurch zaehlt ein Bass-Onset
  in einem sonst ruhigen Band genauso viel wie ein breitbandiger Klick, und
  stationaeres Rauschen/Brummen (Flux konstant ueber die Zeit) traegt fast nichts
  bei. Das ist die Live-Kette des ``BeatDetector``.
  Nebenbei (BPM-12) im selben FFT-Durchlauf eine **Bass-Huellkurve**: halbweg-
  gleichgerichteter Flux der *linearen* Roh-Magnitude nur ~30..200 Hz, ohne Whitening
  und ohne Bandnormierung — die Staerke der Bass-Onsets bleibt vergleichbar (Kick vs.
  Bassnote), das braucht der Oktav-Entscheider im ``TempoTracker``. Dazu eine
  **Hochband-Huellkurve**: Summe der bandnormierten Flux-Anteile der Baender ab ~800 Hz
  (Klick-Anteil einer Kick, Snare, Hats — eine reine Bassnote traegt dort nichts).

Dazu ``HighPass`` (1-Pol-DC-Blocker/Hochpass 30 Hz, blockweise vektorisiert).
"""
from __future__ import annotations

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:                       # pragma: no cover - numpy fehlt nur im System-Py
    np = None
    HAS_NUMPY = False

WIN = 1024
HOP = 512


# ── Batch (Offline-Referenz) ──────────────────────────────────────────────────

def onset_envelope(samples, sr: int, hop: int = HOP, win: int = WIN):
    """Onset-Strength via **Spectral Flux** ueber das ganze Spektrum (log-Magnitude).

    Robuster ueber Genres als das reine Bass-Band (``compute_novelty``): erfasst auch
    Snare/HiHat/Synth-Onsets, nicht nur den Kick. → (onset float32-Array, fps).

    Referenz-Implementierung fuer ``FluxStream(mode="log1p")`` — beide muessen
    bitgleich bleiben (Test ``test_stream_equals_batch``)."""
    if not HAS_NUMPY or samples is None or sr <= 0:
        return None, 0.0
    x = np.asarray(samples, dtype=np.float32)
    if x.size < win + hop:
        return None, 0.0
    n_frames = 1 + (len(x) - win) // hop
    if n_frames < 4:
        return None, 0.0
    window = np.hanning(win).astype(np.float32)
    prev = None
    env = np.empty(n_frames, dtype=np.float32)
    # Blockweise (Speicher schonen bei langen Songs) statt eine n_frames×win-Matrix.
    for i in range(n_frames):
        seg = x[i * hop:i * hop + win] * window
        mag = np.log1p(np.abs(np.fft.rfft(seg)).astype(np.float32))
        if prev is None:
            env[i] = 0.0
        else:
            diff = mag - prev
            diff[diff < 0] = 0.0
            env[i] = float(diff.sum())
        prev = mag
    fps = sr / float(hop)
    return env, fps


# ── Hochpass ──────────────────────────────────────────────────────────────────

class HighPass:
    """1-Pol-DC-Blocker/Hochpass: y[n] = x[n] - x[n-1] + R*y[n-1], R = 1 - 2*pi*fc/sr.

    Vektorisiert ueber cumsum in Bloecken (R**n darf nicht unterlaufen)."""
    BLOCK = 2048

    def __init__(self, sr: int, fc_hz: float = 30.0):
        self.R = 1.0 - 2.0 * np.pi * float(fc_hz) / float(sr)
        n = np.arange(1, self.BLOCK + 1, dtype=np.float64)
        self._Rn = self.R ** n
        self._inv_Rn = 1.0 / self._Rn
        self.reset()

    def reset(self):
        self.x1 = 0.0
        self.y1 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        """x: float32 1-D → gefiltertes float32-Array gleicher Laenge."""
        xd = x.astype(np.float64)
        out = np.empty(xd.size, np.float32)
        for s in range(0, xd.size, self.BLOCK):
            blk = xd[s:s + self.BLOCK]
            n = blk.size
            u = np.empty(n, np.float64)
            u[0] = blk[0] - self.x1
            if n > 1:
                u[1:] = blk[1:] - blk[:-1]
            y = self._Rn[:n] * (self.y1 + np.cumsum(u * self._inv_Rn[:n]))
            self.y1 = float(y[-1])
            self.x1 = float(blk[-1])
            out[s:s + n] = y
        return out


# ── Streaming-Flux ────────────────────────────────────────────────────────────

class FluxStream:
    """Streambarer Spectral Flux; ``push()`` nimmt beliebig grosse Chunks.

    mode="log1p":    bitgleich zu ``onset_envelope`` (Offline-Referenz).
    mode="whitened": Live-Kette (Whitening + bandnormierter Flux), s. Modulkopf.

    Nach jedem ``push`` haelt ``last_magnitude`` das Roh-Magnitudenspektrum des
    zuletzt vollstaendigen Frames (fuer die 8-Band-Anzeige)."""
    RELAX_S = 2.0            # Whitening: Halbwertszeit des Bin-Maximums
    WHITE_FLOOR = 0.1        # Whitening: Floor relativ zum lautesten Bin
    BAND_NORM_S = 1.5        # Bandnormierung: Zeitkonstante des laufenden Mittels
    BAND_CAP = 20.0          # Obergrenze je Band (Verhaeltnis zum Mittel), gegen Ausreisser
    N_BANDS = 12             # log-Baender ab 30 Hz
    LOW_HZ = 30.0
    BASS_LO_HZ = 30.0        # Bass-Huellkurve (BPM-12): Bins 30..200 Hz (bei 44,1 kHz/1024: 43..172 Hz)
    BASS_HI_HZ = 200.0
    HI_LO_HZ = 800.0         # Hochband-Huellkurve (BPM-12): log-Baender ab 815 Hz (6 von 12)

    def __init__(self, sr: int, win: int = WIN, hop: int = HOP, mode: str = "whitened"):
        if mode not in ("log1p", "whitened"):
            raise ValueError(mode)
        self.sr = int(sr)
        self.win = int(win)
        self.hop = int(hop)
        self.mode = mode
        self.fps = self.sr / float(self.hop)
        self.window = np.hanning(self.win).astype(np.float32)
        nb = self.win // 2 + 1
        self.freqs = np.fft.rfftfreq(self.win, 1.0 / self.sr)
        # Band-Grenzen (Bin-Indizes) fuer reduceat; erstes Band beginnt bei LOW_HZ
        edges_hz = np.geomspace(self.LOW_HZ, self.sr / 2.0, self.N_BANDS + 1)
        idx = np.searchsorted(self.freqs, edges_hz).astype(np.intp)
        idx[-1] = nb
        idx = np.unique(idx)
        self._band_starts = idx[:-1]
        self._n_bands = int(self._band_starts.size)
        self._lo_bin = int(idx[0])
        self._bass_lo = int(np.searchsorted(self.freqs, self.BASS_LO_HZ))
        self._bass_hi = max(self._bass_lo + 1, int(np.searchsorted(self.freqs, self.BASS_HI_HZ, side="right")))
        self._hi_band0 = min(self._n_bands - 1, int(np.searchsorted(self.freqs[self._band_starts], self.HI_LO_HZ)))
        self.relax = np.float32(np.exp(np.log(0.5) * self.hop / (self.RELAX_S * self.sr)))
        self._bn_alpha = np.float32(self.hop / (self.BAND_NORM_S * self.sr))
        self._nb = nb
        self.reset()

    def reset(self):
        nb = self._nb
        self.tail = np.zeros(0, np.float32)
        self.prev = None
        self.psp = np.full(nb, 1e-4, np.float32)
        self.band_mean = np.zeros(self._n_bands, np.float32)
        self._bn_n = 0
        self.last_magnitude = np.zeros(nb, np.float32)
        self.frames = 0
        self._bass_prev = None
        self.bass = np.zeros(0, np.float32)     # Bass-Flux der Frames des letzten push (nur whitened)
        self.hi = np.zeros(0, np.float32)       # Hochband-Flux derselben Frames (nur whitened)
        self._hi_val = 0.0

    # ---------------------------------------------------------------- Kern
    def push(self, x: np.ndarray) -> np.ndarray:
        """x: float32 1-D. Liefert die Flux-Werte aller in diesem Aufruf
        vollendeten Frames (float32, evtl. leer)."""
        buf = np.concatenate([self.tail, x]) if self.tail.size else x
        n_new = 0 if buf.size < self.win else 1 + (buf.size - self.win) // self.hop
        if n_new <= 0:
            self.tail = buf
            self.bass = np.zeros(0, np.float32)
            self.hi = np.zeros(0, np.float32)
            return np.zeros(0, np.float32)
        out = np.empty(n_new, np.float32)
        if self.mode == "log1p":
            for i in range(n_new):
                out[i] = self._frame_log1p(buf[i * self.hop:i * self.hop + self.win])
        else:
            bass = np.empty(n_new, np.float32)
            hi = np.empty(n_new, np.float32)
            for i in range(n_new):
                out[i] = self._frame_whitened(buf[i * self.hop:i * self.hop + self.win])
                bass[i] = self._bass_val
                hi[i] = self._hi_val
            self.bass = bass
            self.hi = hi
        self.tail = buf[n_new * self.hop:]
        self.frames += n_new
        return out

    def _frame_log1p(self, seg: np.ndarray) -> float:
        mag = np.log1p(np.abs(np.fft.rfft(seg * self.window)).astype(np.float32))
        if self.prev is None:
            self.prev = mag
            return 0.0
        diff = mag - self.prev
        diff[diff < 0] = 0.0
        self.prev = mag
        return float(diff.sum())

    def _frame_whitened(self, seg: np.ndarray) -> float:
        mag = np.abs(np.fft.rfft(seg * self.window)).astype(np.float32)
        self.last_magnitude = mag
        # Bass-Flux (BPM-12) aus derselben FFT: lineare Magnitude, nur 30..200 Hz
        mb = mag[self._bass_lo:self._bass_hi]
        if self._bass_prev is None:
            self._bass_val = 0.0
        else:
            self._bass_val = float(np.maximum(mb - self._bass_prev, 0.0).sum())
        self._bass_prev = mb
        # adaptives Whitening: Bin / (eigenes abklingendes Maximum, Floor relativ zum lautesten)
        psp = np.maximum(mag, self.psp * self.relax)
        self.psp = psp
        floor = np.float32(self.WHITE_FLOOR) * np.float32(psp.max() + 1e-9)
        m = mag / np.maximum(psp, floor)
        if self.prev is None:
            self.prev = m
            self._hi_val = 0.0
            return 0.0
        d = m - self.prev
        self.prev = m
        np.maximum(d, 0.0, out=d)
        # Flux je log-Band, jedes Band auf sein laufendes Mittel normiert,
        # nur der Ueberschuss zaehlt (stationaeres Rauschen/Brummen -> ~0)
        bf = np.add.reduceat(d[self._lo_bin:], self._band_starts - self._lo_bin)
        bm = self.band_mean
        # Warmlauf: erst echtes laufendes Mittel (1/n), dann EMA — sonst dominieren die
        # ersten Frames mit riesigen Verhaeltnissen den Ring sekundenlang
        self._bn_n += 1
        alpha = max(self._bn_alpha, np.float32(1.0 / self._bn_n))
        bm += alpha * (bf - bm)
        ratio = bf / (bm + np.float32(1e-6)) - np.float32(1.0)
        np.clip(ratio, 0.0, self.BAND_CAP, out=ratio)
        self._hi_val = float(ratio[self._hi_band0:].sum())
        return float(ratio.sum())

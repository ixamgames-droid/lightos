"""Pegelmeter fuer den Audio-Capture (BPM-10, S5) — reines numpy, kein Qt.

``LevelMeter.on_chunk(samples)`` haengt als Abonnent am ``AudioCapture`` und
veroeffentlicht nach JEDEM Chunk einen neuen, unveraenderlichen
``CaptureSnapshot`` per Referenzwechsel (eine Attributzuweisung ist in CPython
atomar). Leser (50-ms-Timer der UI) holen ``snapshot()`` ohne Lock und sehen
immer einen in sich stimmigen Satz Werte.

dBFS-Bezug: 0 dBFS = Sample-Betrag 1,0; RMS in dBFS = 20·log10(RMS). Ein
Vollsinus (Amplitude 1,0) hat damit −3,01 dBFS RMS und 0 dBFS Spitze; Stille
liegt am Boden ``BODEN_DBFS`` (−120).

Fenster in AUDIO-Zeit (Samples/Samplerate), damit Tests deterministisch sind:
RMS ueber 300 ms und 1 s, Clip-Zaehler ueber 1 s, Peak-Hold faellt mit
``PEAK_HOLD_ABFALL_DB_S`` je Sekunde Audio. ``chunk_ms_p95`` misst dagegen die
WANDUHR (Ankunftsabstaende der Chunks, Uhr injizierbar) — Jitter/Aussetzer des
Treibers.

``netz_linie`` (BPM-11, S6) misst, wie SCHARF die Energie um 50/60 Hz samt
zwei Oberwellen auf der Netzfrequenz liegt: Leistung in ±``NETZ_LINIE_HZ``
um k·50 bzw. k·60 Hz geteilt durch die Leistung in ±``NETZ_UMGEBUNG_HZ``,
aus einem ``NETZ_FENSTER_S`` langen, auf ~2,8 kHz dezimierten Fenster
(Aufloesung 0,25 Hz). Netzbrumm ist eine Linie genau auf 50/60 Hz (≈1,0);
ein gehaltener Bass-Ton liegt fast nie dort (G1 49,0 · G#1 51,9 · A#1 58,3 ·
B1 61,7 Hz → ≤0,07), eine Kick ist breitbandig (≤0,22). Die Statusregel BRUMM
braucht beides: ``hum_ratio`` des Detektors UND diese Linie.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

# ── Konstanten (EIN Block; Anzeige und spaetere Statusregeln lesen nur hier) ──
ZIEL_LO_DBFS = -30.0          # gruene Zielzone unten (RMS)
ZIEL_HI_DBFS = -6.0           # gruene Zielzone oben (RMS)
GRAU_UNTER_DBFS = -45.0       # darunter: zu leise fuer die Erkennung (grau)
ROT_UEBER_DBFS = -3.0         # darueber: zu heiss (rot)
CLIP_CHUNKS_PRO_S = 3         # so viele Chunks mit Clip-Samples in 1 s = CLIP
CLIP_SAMPLE_DBFS = -0.1       # ein Sample ab hier zaehlt als Clip
PEAK_HOLD_ABFALL_DB_S = 20.0  # Peak-Hold faellt so viele dB je Sekunde
ANZEIGE_MIN_DBFS = -60.0      # Skala der Anzeige (Widget)
BODEN_DBFS = -120.0           # Stille / kein Signal
FENSTER_KURZ_S = 0.3
FENSTER_LANG_S = 1.0
JITTER_ABSTAENDE = 64         # so viele Ankunftsabstaende gehen in p95 ein
NETZ_FENSTER_S = 4.0          # Fensterlaenge der Netzlinien-Messung (Aufloesung 1/4 s = 0,25 Hz)
NETZ_ALLE_S = 1.0             # so oft (Audio-Zeit) wird die Netzlinie neu gerechnet (CPU-Budget)
NETZ_DEZIMATION = 16          # 44,1 kHz -> 2,76 kHz (Blocksumme, Nullstellen auf fs/16-Vielfachen)
NETZ_LINIE_HZ = 0.5           # Linienbreite um k·50/60 Hz (Hann-Hauptkeule bei 4 s)
NETZ_UMGEBUNG_HZ = 4.0        # Vergleichsband um k·50/60 Hz

_CLIP_LIN = 10.0 ** (CLIP_SAMPLE_DBFS / 20.0)
_BODEN_LIN = 10.0 ** (BODEN_DBFS / 20.0)


def dbfs(lin: float) -> float:
    """Linearer Betrag (RMS oder Spitze) -> dBFS, unten bei ``BODEN_DBFS`` begrenzt."""
    if lin <= _BODEN_LIN:
        return BODEN_DBFS
    return 20.0 * math.log10(lin)


@dataclass(frozen=True, slots=True)
class CaptureSnapshot:
    """Unveraenderlicher Pegel-/Capture-Zustand. ``running``/``device``/
    ``source_mode`` setzt ``AudioCapture.snapshot()``; der LevelMeter allein
    liefert sie leer."""
    rms_dbfs_300ms: float = BODEN_DBFS
    rms_dbfs_1s: float = BODEN_DBFS
    peak_dbfs: float = BODEN_DBFS          # Spitze des letzten Chunks
    peak_hold_dbfs: float = BODEN_DBFS     # gehaltene Spitze, faellt 20 dB/s
    clip_samples_1s: int = 0               # Samples >= −0,1 dBFS in der letzten Sekunde
    clip_chunks_1s: int = 0                # Chunks mit mindestens einem Clip-Sample
    dc_offset: float = 0.0                 # Mittelwert ueber 1 s (linear, −1..+1)
    chunk_ms_p95: float = 0.0              # p95 der Chunk-Ankunftsabstaende (Wanduhr)
    sample_rate: int = 44100
    chunks: int = 0                        # verarbeitete Chunks seit reset()
    netz_linie: float = 0.0                # 0..1 Schaerfe der 50/60-Hz-Linie (s. Moduldoku); 0 = unbekannt
    netz_hz: int = 0                       # 50 | 60 (staerkere Linie), 0 = noch nicht gemessen
    running: bool = False
    device: str | None = None
    source_mode: str | None = None

    @property
    def clipping(self) -> bool:
        """CLIP: mindestens ``CLIP_CHUNKS_PRO_S`` Chunks mit Clip-Samples in 1 s."""
        return self.clip_chunks_1s >= CLIP_CHUNKS_PRO_S

    @property
    def has_signal(self) -> bool:
        return self.chunks > 0 and self.rms_dbfs_300ms > BODEN_DBFS


EMPTY_SNAPSHOT = CaptureSnapshot()


class LevelMeter:
    """Capture-Abonnent: misst Pegel je Chunk, veroeffentlicht ``CaptureSnapshot``.

    Schreiber ist genau EIN Thread (der Capture-Thread); ``snapshot()`` darf
    aus jedem Thread ohne Lock gelesen werden.
    """

    def __init__(self, sample_rate: int = 44100, clock=None):
        self.sample_rate = int(sample_rate)
        self._clock = clock if clock is not None else time.perf_counter
        self._snap = CaptureSnapshot(sample_rate=self.sample_rate)
        self.reset()

    def reset(self) -> None:
        """Fenster leeren (Quellen-/Geraetewechsel). Der Snapshot wird ersetzt."""
        # je Chunk: (n, Quadratsumme, Summe, Clip-Samples)
        self._chunks: deque = deque()
        self._n_lang = 0
        self._kurz: deque = deque()
        self._n_kurz = 0
        self._abst: deque = deque(maxlen=JITTER_ABSTAENDE)
        self._t_last: float | None = None
        self._hold = 0.0                     # linear
        self._count = 0
        fs = self.sample_rate / NETZ_DEZIMATION
        self._netz_w = int(NETZ_FENSTER_S * fs)
        self._netz_ring = np.zeros(self._netz_w, dtype=np.float32)   # dezimiert, Ringpuffer
        self._netz_pos = 0
        self._netz_n = 0
        self._netz_rest = np.zeros(0, dtype=np.float32)
        self._netz_win = np.hanning(self._netz_w)
        self._netz_seit = 0                  # Roh-Samples seit der letzten Messung
        self._netz = (0.0, 0)
        self._snap = CaptureSnapshot(sample_rate=self.sample_rate)

    def snapshot(self) -> CaptureSnapshot:
        return self._snap

    def on_chunk(self, samples) -> None:
        now = self._clock()
        x = samples if isinstance(samples, np.ndarray) else np.asarray(samples, dtype=np.float32)
        if x.ndim > 1:
            x = x.mean(axis=1)
        n = int(x.shape[0])
        if n == 0:
            return
        if self._t_last is not None:
            self._abst.append((now - self._t_last) * 1000.0)
        self._t_last = now

        sq = float(np.dot(x, x))
        sm = float(x.sum())
        hi = float(x.max())
        lo = float(x.min())
        peak = hi if hi >= -lo else -lo
        clips = int(np.count_nonzero(np.abs(x) >= _CLIP_LIN)) if peak >= _CLIP_LIN else 0

        sr = self.sample_rate
        entry = (n, sq, sm, clips)
        self._chunks.append(entry)
        self._n_lang += n
        lang_max = int(sr * FENSTER_LANG_S)
        while self._n_lang - self._chunks[0][0] >= lang_max:
            self._n_lang -= self._chunks.popleft()[0]
        self._kurz.append(entry)
        self._n_kurz += n
        kurz_max = int(sr * FENSTER_KURZ_S)
        while self._n_kurz - self._kurz[0][0] >= kurz_max:
            self._n_kurz -= self._kurz.popleft()[0]

        sq_l = sm_l = 0.0
        clip_s = clip_c = 0
        for cn, csq, csm, ccl in self._chunks:
            sq_l += csq
            sm_l += csm
            if ccl:
                clip_s += ccl
                clip_c += 1
        sq_k = 0.0
        for e in self._kurz:
            sq_k += e[1]

        # Peak-Hold: faellt in Audio-Zeit (dieser Chunk dauert n/sr Sekunden)
        if self._hold > 0.0:
            self._hold *= 10.0 ** (-PEAK_HOLD_ABFALL_DB_S * (n / sr) / 20.0)
        if peak > self._hold:
            self._hold = peak

        if self._abst:
            srt = sorted(self._abst)
            p95 = srt[min(len(srt) - 1, int(math.ceil(0.95 * len(srt))) - 1)]
        else:
            p95 = 0.0
        self._netz_chunk(x)
        self._count += 1
        self._snap = CaptureSnapshot(
            dbfs(math.sqrt(sq_k / self._n_kurz)),
            dbfs(math.sqrt(sq_l / self._n_lang)),
            dbfs(peak),
            dbfs(self._hold),
            clip_s,
            clip_c,
            sm_l / self._n_lang,
            p95,
            sr,
            self._count,
            netz_linie=self._netz[0],
            netz_hz=self._netz[1],
        )

    # ── Netzlinie ────────────────────────────────────────────────────────────

    def _netz_chunk(self, x: np.ndarray) -> None:
        d = NETZ_DEZIMATION
        y = np.concatenate((self._netz_rest, x)) if self._netz_rest.shape[0] else x
        m = (y.shape[0] // d) * d
        self._netz_rest = y[m:].astype(np.float32, copy=True)
        if m:
            blk = y[:m].reshape(-1, d).sum(axis=1)       # Blocksumme: Skala egal (Verhaeltnis)
            w, k = self._netz_w, blk.shape[0]
            if k >= w:
                self._netz_ring[:] = blk[-w:]
                self._netz_pos = 0
            else:
                e = self._netz_pos + k
                if e <= w:
                    self._netz_ring[self._netz_pos:e] = blk
                else:
                    self._netz_ring[self._netz_pos:] = blk[:w - self._netz_pos]
                    self._netz_ring[:e - w] = blk[w - self._netz_pos:]
                self._netz_pos = e % w
            self._netz_n = min(w, self._netz_n + k)
        self._netz_seit += int(x.shape[0])
        if self._netz_n < self._netz_w or self._netz_seit < int(NETZ_ALLE_S * self.sample_rate):
            return
        self._netz_seit = 0
        y = np.roll(self._netz_ring, -self._netz_pos)
        self._netz = netz_linie(y, self.sample_rate / d, self._netz_win)


def netz_linie(y: np.ndarray, fs: float, fenster: np.ndarray | None = None) -> tuple[float, int]:
    """(Schaerfe 0..1, 50|60) der Netzlinie in ``y`` (Abtastrate ``fs``); (0, 0) bei Stille."""
    n = int(y.shape[0])
    if n < 16:
        return 0.0, 0
    nfft = 1 << max(12, int(math.ceil(math.log2(n))))
    win = fenster if fenster is not None and fenster.shape[0] == n else np.hanning(n)
    p = np.abs(np.fft.rfft((y - y.mean()) * win, nfft)) ** 2
    df = fs / nfft
    best, best_hz = 0.0, 0
    for f0 in (50, 60):
        linie = umgebung = 0.0
        for k in (1, 2, 3):
            c = k * f0
            lo, hi = int(math.ceil((c - NETZ_LINIE_HZ) / df)), int(math.floor((c + NETZ_LINIE_HZ) / df))
            ulo, uhi = int(math.ceil((c - NETZ_UMGEBUNG_HZ) / df)), int(math.floor((c + NETZ_UMGEBUNG_HZ) / df))
            linie += float(p[lo:hi + 1].sum())
            umgebung += float(p[ulo:uhi + 1].sum())
        if umgebung > 1e-18 and linie / umgebung > best:
            best, best_hz = linie / umgebung, f0
    return best, best_hz

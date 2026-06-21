"""F-15 (Tier 2, optional): Offline-BPM-Schätzung aus WAV — reines numpy, kein extra-Dep.

Bewusst KLEIN gehalten und ausschließlich **opt-in** (vom Nutzer angestoßen, nie auf dem
Import-/Lade-/Render-Pfad). Deckt nur ``.wav`` ab (stdlib ``wave`` + numpy); komprimierte
Formate (MP3/M4A) bleiben hier WontFix — dafür gibt es keinen stdlib-Decoder (``audioop``
ist in Python 3.14 entfernt) und die Memory-Notiz „Offline-Analyse bewusst weggelassen"
gilt für echte Inhalts-Analyse. Für MP3/M4A liefert das eingebettete Tag (``tag_reader``)
die BPM. Ohne numpy degradiert alles sauber zu 0.0/None.

Algorithmus: Bass-Band-Energie (40–180 Hz, wie der Live-``beat_detector``) → Onset-Novelty
(halbweg-gleichgerichtete erste Differenz) → Autokorrelation → Tempo-Peak 60–200 BPM mit
Parabel-Verfeinerung und Oktav-Faltung in den Dance-Bereich (≥90 BPM).
"""
from __future__ import annotations
import os

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:                       # pragma: no cover - numpy fehlt nur im System-Py
    np = None
    HAS_NUMPY = False


def decode_wav_mono(path: str):
    """``.wav`` → (mono float32 ndarray in [-1,1], samplerate) oder (None, 0).

    Nutzt stdlib ``wave`` (PCM 8/16/32-bit) + numpy; KEIN ``audioop`` (in 3.14 entfernt)."""
    if not HAS_NUMPY:
        return None, 0
    import wave
    try:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            sw = w.getsampwidth()
            sr = w.getframerate()
            raw = w.readframes(w.getnframes())
    except Exception:
        return None, 0
    if not raw or sr <= 0:
        return None, 0
    if sw == 2:
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sw == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        return None, 0
    if nch > 1:
        usable = (a.size // nch) * nch
        a = a[:usable].reshape(-1, nch).mean(axis=1)
    return a, sr


def analyze_bpm(samples, sr: int, hop: int = 512, win: int = 1024) -> float:
    """BPM aus einem mono float32-Signal schätzen (oder 0.0). Wirft nie."""
    if not HAS_NUMPY or samples is None or sr <= 0:
        return 0.0
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size < sr or x.size < win + hop:        # < ~1 s ist zu kurz
            return 0.0
        n_frames = 1 + (len(x) - win) // hop
        if n_frames < 8:
            return 0.0
        freqs = np.fft.rfftfreq(win, 1.0 / sr)
        band = (freqs >= 40.0) & (freqs <= 180.0)
        window = np.hanning(win).astype(np.float32)
        env = np.empty(n_frames, dtype=np.float32)
        for i in range(n_frames):
            seg = x[i * hop:i * hop + win] * window
            spec = np.abs(np.fft.rfft(seg))
            env[i] = float(spec[band].sum())
        nov = np.diff(env)
        nov[nov < 0] = 0.0
        if not np.any(nov > 0):
            return 0.0
        nov = nov - nov.mean()
        ac = np.correlate(nov, nov, mode="full")[len(nov) - 1:]
        fps = sr / float(hop)                         # Frames pro Sekunde
        min_lag = max(1, int(fps * 60.0 / 200.0))     # 200 BPM
        max_lag = min(len(ac) - 1, int(fps * 60.0 / 60.0))   # 60 BPM
        if max_lag <= min_lag:
            return 0.0
        seg = ac[min_lag:max_lag + 1]
        if not np.any(seg > 0):
            return 0.0
        peak = min_lag + int(np.argmax(seg))
        shift = 0.0
        if 0 < peak < len(ac) - 1:                    # Parabel-Verfeinerung
            a0, b0, c0 = ac[peak - 1], ac[peak], ac[peak + 1]
            denom = (a0 - 2 * b0 + c0)
            if denom != 0:
                shift = 0.5 * (a0 - c0) / denom
        lag = peak + shift
        if lag <= 0:
            return 0.0
        bpm = 60.0 * fps / lag
        while bpm < 90.0 and bpm * 2.0 <= 200.0:      # Oktav-Faltung (Dance ≥ 90)
            bpm *= 2.0
        while bpm > 200.0:
            bpm /= 2.0
        return round(float(bpm), 1)
    except Exception:
        return 0.0


def estimate_bpm_from_file(path: str) -> float:
    """Opt-in: BPM aus einer ``.wav``-Datei (oder 0.0 bei anderem Format / ohne numpy)."""
    if not HAS_NUMPY:
        return 0.0
    if os.path.splitext(path)[1].lower() != ".wav":
        return 0.0
    samples, sr = decode_wav_mono(path)
    if samples is None or sr <= 0:
        return 0.0
    return analyze_bpm(samples, sr)

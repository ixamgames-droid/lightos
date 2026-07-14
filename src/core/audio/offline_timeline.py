"""Offline-Analyse eines KOMPLETTEN Liedes in eine zeitgestuetzte BPM-Kurve.

Erweitert die globale Einzel-BPM-Schaetzung (``offline_analysis``) um zwei Dinge,
die der „BPM-Generator"-Tab braucht:

1. **Dekodierung beliebiger Formate** (MP3/M4A/FLAC/OGG/WAV) ueber Qt's
   ``QAudioDecoder`` — dieselben Codecs wie der eingebaute Player, **keine neue
   Abhaengigkeit**. ``.wav`` laeuft weiter ueber den stdlib-Pfad.
2. **Zeitverlauf statt EINER BPM:** ein gleitendes Analyse-Fenster ueber die
   global einmal berechnete Onset-Novelty liefert je Fenster ``(Zeit, BPM,
   Konfidenz)`` — die „BPM-Chase"/Timeline.

Bewusst **opt-in** (nur vom Generator-Tab angestossen, nie auf dem Import-/Lade-/
Render-Pfad). Ohne numpy degradiert alles sauber zu leeren Ergebnissen.

Algorithmus pro Fenster: Bass-Band-Energie (40-180 Hz) → Onset-Novelty
(halbweg-gleichgerichtete 1. Differenz) → Autokorrelation → Tempo-Peak mit
Parabel-Verfeinerung; Konfidenz = Prominenz des Peaks gegen den Rest. Zwischen
Fenstern haelt eine Oktav-Kontinuitaet die Kurve glatt (kein Half/Double-Springen).
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:                       # pragma: no cover - numpy fehlt nur im System-Py
    np = None
    HAS_NUMPY = False


# ── Datenmodell ───────────────────────────────────────────────────────────────

@dataclass
class BpmSegment:
    """Ein Analyse-Fenster: BPM (mit Konfidenz) zur Zeit ``t_ms`` (Fenstermitte)."""
    t_ms: int
    bpm: float
    confidence: float = 0.0


@dataclass
class BpmTimeline:
    """Zeitgestuetzte BPM-Kurve eines Liedes + optionales echtes Beatgrid.

    ``segments`` = BPM-Kurve (fuer Anzeige + ``bpm_at``). ``beats_ms`` =
    phasen-genaue Beat-Zeitpunkte (das Beatgrid), ``downbeats_ms`` deren
    Taktanfaenge. ``engine`` = welcher Analyzer es erzeugt hat."""
    segments: list = field(default_factory=list)   # list[BpmSegment], sortiert nach t_ms
    duration_ms: int = 0
    step_ms: int = 0
    window_ms: int = 0
    beats_ms: list = field(default_factory=list)       # echtes Beatgrid (alle Beats)
    downbeats_ms: list = field(default_factory=list)   # Taktanfaenge (Teilmenge)
    engine: str = "builtin"
    beats_per_bar: int = 4
    sections: list = field(default_factory=list)       # Songstruktur: [[t_ms, label, energy], ...]

    def has_grid(self) -> bool:
        return bool(self.beats_ms)

    # ── Abfrage ──
    def bpm_at(self, ms: float) -> float:
        """BPM am naechstgelegenen Segment zur Position ``ms`` (0 falls leer)."""
        seg = self._nearest(ms)
        return seg.bpm if seg else 0.0

    def confidence_at(self, ms: float) -> float:
        seg = self._nearest(ms)
        return seg.confidence if seg else 0.0

    def _nearest(self, ms: float):
        if not self.segments:
            return None
        best = self.segments[0]
        best_d = abs(best.t_ms - ms)
        for s in self.segments:
            d = abs(s.t_ms - ms)
            if d < best_d:
                best, best_d = s, d
            elif s.t_ms > ms and d > best_d:
                break   # Segmente sind sortiert → ab hier nur groesser
        return best

    def summary(self) -> dict:
        """Kennzahlen fuer die UI: Anzahl, Mittel/Median/Min/Max-BPM, Stabilitaet."""
        vals = [s.bpm for s in self.segments if s.bpm > 0]
        if not vals:
            return {"count": 0, "avg": 0.0, "median": 0.0, "min": 0.0,
                    "max": 0.0, "stable": True, "duration_ms": self.duration_ms}
        sv = sorted(vals)
        n = len(sv)
        median = sv[n // 2] if n % 2 else 0.5 * (sv[n // 2 - 1] + sv[n // 2])
        return {
            "count": len(self.segments),
            "avg": round(sum(vals) / len(vals), 1),
            "median": round(median, 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "stable": (max(vals) - min(vals)) <= 4.0,
            "duration_ms": self.duration_ms,
            "beats": len(self.beats_ms),
            "engine": self.engine,
        }

    # ── Beatgrid-Abfrage (fuer phasen-genaue Wiedergabe + Editor) ──
    def nearest_beat(self, ms: float):
        """Index + Zeit des naechstgelegenen Beats (oder (None, None))."""
        if not self.beats_ms:
            return None, None
        import bisect
        i = bisect.bisect_left(self.beats_ms, ms)
        cands = []
        if i < len(self.beats_ms):
            cands.append(i)
        if i > 0:
            cands.append(i - 1)
        best = min(cands, key=lambda j: abs(self.beats_ms[j] - ms))
        return best, self.beats_ms[best]

    def beat_phase_at(self, ms: float):
        """(bar_index, beat_in_bar, phase01) an Position ``ms`` aus dem Beatgrid.

        ``phase01`` = Bruchteil bis zum naechsten Beat. Gibt None, wenn kein Grid."""
        if not self.beats_ms:
            return None
        import bisect
        b = self.beats_ms
        i = bisect.bisect_right(b, ms) - 1
        if i < 0:
            i = 0
        nxt = b[i + 1] if i + 1 < len(b) else (b[i] + (b[i] - b[i - 1] if i > 0 else 500))
        span = max(1, nxt - b[i])
        phase01 = max(0.0, min(1.0, (ms - b[i]) / span))
        bpb = max(1, self.beats_per_bar)
        # Beat-Nummer relativ zum naechsten vorausgehenden Downbeat
        if self.downbeats_ms:
            db_i = bisect.bisect_right(self.downbeats_ms, b[i]) - 1
            bar_index = max(0, db_i)
            # Beats seit diesem Downbeat zaehlen
            db_ms = self.downbeats_ms[max(0, db_i)]
            beat_in_bar = sum(1 for x in b if db_ms <= x <= b[i]) - 1
            beat_in_bar = max(0, beat_in_bar) % bpb
        else:
            bar_index = i // bpb
            beat_in_bar = i % bpb
        return bar_index, beat_in_bar, phase01

    # ── Serialisierung (kompakt) ──
    def to_dict(self) -> dict:
        d = {
            "v": 2,
            "engine": self.engine,
            "beats_per_bar": int(self.beats_per_bar),
            "duration_ms": int(self.duration_ms),
            "step_ms": int(self.step_ms),
            "window_ms": int(self.window_ms),
            "segments": [[int(s.t_ms), round(float(s.bpm), 1),
                          round(float(s.confidence), 3)] for s in self.segments],
        }
        if self.beats_ms:
            d["beats_ms"] = [int(x) for x in self.beats_ms]
        if self.downbeats_ms:
            d["downbeats_ms"] = [int(x) for x in self.downbeats_ms]
        if self.sections:
            d["sections"] = [[int(s[0]), str(s[1]), round(float(s[2]), 3)]
                             for s in self.sections]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BpmTimeline":
        if not isinstance(d, dict):
            return cls()
        segs = []
        for row in (d.get("segments") or []):
            try:
                t_ms = int(row[0])
                bpm = float(row[1])
                conf = float(row[2]) if len(row) > 2 else 0.0
            except (TypeError, ValueError, IndexError):
                continue
            segs.append(BpmSegment(t_ms=t_ms, bpm=bpm, confidence=conf))
        segs.sort(key=lambda s: s.t_ms)

        def _int_list(key):
            out = []
            for x in (d.get(key) or []):
                try:
                    out.append(int(x))
                except (TypeError, ValueError):
                    pass
            out.sort()
            return out

        secs = []
        for row in (d.get("sections") or []):
            try:
                secs.append([int(row[0]), str(row[1]),
                             float(row[2]) if len(row) > 2 else 0.0])
            except (TypeError, ValueError, IndexError):
                continue

        beats = _int_list("beats_ms")
        downs = _int_list("downbeats_ms")
        # Invariante downbeats ⊆ beats erzwingen: ein korrupter/veralteter Cache
        # kann Downbeats enthalten, die in keinem Beat vorkommen (unabhaengig
        # sortiert). ``beat_phase_at`` zaehlt dann falsche Beats seit dem Downbeat
        # → falsches ``beat_in_bar``. Darum auf die Schnittmenge mit ``beats``
        # reduzieren; ueberlebt bei vorhandenen Beats gar kein Downbeat, sauber
        # verwerfen (Fallback ``i // bpb`` liefert dann konsistente Bars).
        if downs and beats:
            beat_set = set(beats)
            downs = [x for x in downs if x in beat_set]
        elif downs and not beats:
            # Downbeats ohne jedes Beatgrid sind sinnlos → verwerfen.
            downs = []

        return cls(
            segments=segs,
            duration_ms=int(d.get("duration_ms", 0) or 0),
            step_ms=int(d.get("step_ms", 0) or 0),
            window_ms=int(d.get("window_ms", 0) or 0),
            beats_ms=beats,
            downbeats_ms=downs,
            engine=str(d.get("engine", "builtin") or "builtin"),
            beats_per_bar=int(d.get("beats_per_bar", 4) or 4),
            sections=secs,
        )

    def is_empty(self) -> bool:
        return not self.segments and not self.beats_ms


# ── Novelty + Tempo pro Fenster ───────────────────────────────────────────────

def compute_novelty(samples, sr: int, hop: int = 512, win: int = 1024):
    """Onset-Novelty (Bass-Band) ueber das ganze Signal → (nov-Array, fps).

    Wird EINMAL global berechnet und vom Timeline-Schieber in Fenster zerschnitten
    (FFT nicht pro Fenster neu)."""
    if not HAS_NUMPY or samples is None or sr <= 0:
        return None, 0.0
    x = np.asarray(samples, dtype=np.float32)
    if x.size < win + hop:
        return None, 0.0
    n_frames = 1 + (len(x) - win) // hop
    if n_frames < 4:
        return None, 0.0
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
    fps = sr / float(hop)
    return nov, fps


def tempo_from_novelty(nov, fps: float, min_bpm: float = 60.0,
                       max_bpm: float = 200.0, prior_center: float = 120.0):
    """Tempo + Konfidenz aus einem Novelty-Ausschnitt (Autokorrelation).

    ``prior_center`` = Zentrum des log-normalen Tempo-Priors (Genre-abhaengig:
    z.B. 150 fuer Hardstyle, 174 fuer DnB) → loest Oktav-Mehrdeutigkeit.
    Returns (bpm, confidence) — bpm im Bereich [min_bpm, max_bpm] oder 0.0."""
    if not HAS_NUMPY or nov is None or len(nov) < 4 or fps <= 0:
        return 0.0, 0.0
    try:
        n = nov - nov.mean()
        ac = np.correlate(n, n, mode="full")[len(n) - 1:]
        if ac.size < 2 or ac[0] <= 0:
            return 0.0, 0.0
        min_lag = max(1, int(fps * 60.0 / max_bpm))
        max_lag = min(len(ac) - 1, int(fps * 60.0 / min_bpm))
        if max_lag <= min_lag:
            return 0.0, 0.0
        seg = ac[min_lag:max_lag + 1]
        if not np.any(seg > 0):
            return 0.0, 0.0
        # Tempo-Prior (log-normal um ~120 BPM): bricht Oktav-Mehrdeutigkeiten
        # (z.B. 64 vs 128) so auf, wie ein Mensch den Grundschlag waehlt — und
        # konsistent mit der Dance-Bias (>=90) des bestehenden Analyzers.
        lags = np.arange(min_lag, max_lag + 1).astype(np.float64)
        cand_bpm = 60.0 * fps / lags
        prior = np.exp(-0.5 * (np.log2(cand_bpm / max(1.0, prior_center)) / 0.9) ** 2)
        seg_w = seg * prior
        peak = int(np.argmax(seg_w))
        peak_val = float(seg_w[peak])
        if peak_val <= 0:
            return 0.0, 0.0
        abs_peak = min_lag + peak
        shift = 0.0
        if 0 < abs_peak < len(ac) - 1:            # Parabel-Verfeinerung (rohe ac)
            a0, b0, c0 = ac[abs_peak - 1], ac[abs_peak], ac[abs_peak + 1]
            denom = (a0 - 2 * b0 + c0)
            if denom != 0:
                shift = 0.5 * (a0 - c0) / denom
        lag = abs_peak + shift
        if lag <= 0:
            return 0.0, 0.0
        bpm = 60.0 * fps / lag
        # Konfidenz = Prominenz des Peaks gegen den Rest (Nachbarschaft unterdrueckt).
        supp = seg_w.copy()
        lo = max(0, peak - 3)
        hi = min(len(seg_w), peak + 4)
        supp[lo:hi] = 0.0
        second = float(supp.max()) if supp.size else 0.0
        conf = max(0.0, min(1.0, 1.0 - second / peak_val))
        return float(bpm), conf
    except Exception:
        return 0.0, 0.0


def analyze_timeline(samples, sr: int, window_s: float = 8.0, step_s: float = 2.0,
                     min_bpm: float = 60.0, max_bpm: float = 200.0,
                     hop: int = 512, win: int = 1024) -> BpmTimeline:
    """Ganzes mono-Signal → BpmTimeline (gleitendes Fenster ueber die Novelty)."""
    nov, fps = compute_novelty(samples, sr, hop, win)
    if nov is None or fps <= 0:
        return BpmTimeline()
    total = len(nov)
    wf = max(8, int(window_s * fps))
    sf = max(1, int(step_s * fps))
    segments = []
    start = 0
    while start < total:
        end = min(start + wf, total)
        if end - start < max(8, wf // 3):     # zu kurzer Rest am Songende
            break
        # Ehrlicher Pro-Fenster-Wert: KEIN Oktav-Snap auf den Vorwert, sonst
        # wuerden echte Tempowechsel (z.B. 110→150) faelschlich gehalvet.
        bpm, conf = tempo_from_novelty(nov[start:end], fps, min_bpm, max_bpm)
        if bpm > 0:
            center = start + (end - start) / 2.0
            t_ms = int(center / fps * 1000.0)
            segments.append(BpmSegment(t_ms=t_ms, bpm=round(bpm, 1),
                                       confidence=round(conf, 3)))
        start += sf
    return BpmTimeline(
        segments=segments,
        duration_ms=int(total / fps * 1000.0),
        step_ms=int(step_s * 1000),
        window_ms=int(window_s * 1000),
    )


# ── Multiband-Onset (Spectral Flux) + echtes Beatgrid ─────────────────────────

def onset_envelope(samples, sr: int, hop: int = 512, win: int = 1024):
    """Onset-Strength via **Spectral Flux** ueber das ganze Spektrum (log-Magnitude).

    Robuster ueber Genres als das reine Bass-Band (`compute_novelty`): erfasst auch
    Snare/HiHat/Synth-Onsets, nicht nur den Kick. → (onset float32-Array, fps)."""
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


def _fit_beatgrid(onset, fps: float, bpm: float, beats_per_bar: int = 4):
    """Phasen-genaues Beatgrid aus Onset-Strength + Tempo (frames).

    1) globale Phase per Comb-Kreuzkorrelation (Pulszug @ Periode vs. Onset),
    2) Beats setzen + jeden Beat auf den staerksten Onset im ±Periode/8-Fenster
       snappen (faengt Mikro-Timing/leichten Drift),
    3) Downbeat-Phase = der beats_per_bar-Versatz mit max. Onset-Energie.
    Returns (beats_frames:list[int], downbeats_frames:list[int])."""
    if not HAS_NUMPY or onset is None or len(onset) < 4 or bpm <= 0 or fps <= 0:
        return [], []
    o = np.asarray(onset, dtype=np.float64)
    if o.max() > 0:
        o = o / o.max()
    N = len(o)
    period = 60.0 * fps / bpm
    if period < 2 or period >= N:
        return [], []
    # 1) beste globale Phase
    best_phase, best_score = 0.0, -1.0
    for ph in np.linspace(0.0, period, 32, endpoint=False):
        idx = np.round(np.arange(ph, N, period)).astype(int)
        idx = idx[idx < N]
        if idx.size == 0:
            continue
        sc = float(o[idx].sum())
        if sc > best_score:
            best_score, best_phase = sc, ph
    # 2) Beats setzen + auf Onset snappen
    w = max(1, int(round(period / 8)))
    beats = []
    for b in np.arange(best_phase, N, period):
        c = int(round(b))
        lo, hi = max(0, c - w), min(N, c + w + 1)
        if hi > lo:
            c = lo + int(np.argmax(o[lo:hi]))
        if not beats or c > beats[-1]:
            beats.append(c)
    # 3) Downbeat-Versatz: welcher der beats_per_bar Offsets traegt die meiste Energie?
    bpb = max(1, int(beats_per_bar))
    best_off, best_e = 0, -1.0
    if beats:
        for off in range(bpb):
            e = sum(o[beats[k]] for k in range(off, len(beats), bpb))
            if e > best_e:
                best_e, best_off = e, off
    downbeats = [beats[k] for k in range(best_off, len(beats), bpb)]
    return beats, downbeats


def analyze_builtin(samples, sr: int, window_s: float = 8.0, step_s: float = 2.0,
                    min_bpm: float = 60.0, max_bpm: float = 200.0,
                    beats_per_bar: int = 4, prior_center: float = 120.0) -> "BpmTimeline":
    """Eingebaute Engine: Multiband-Onset → BPM-Kurve (Fenster) + echtes Beatgrid.

    Nutzt EINE Onset-Strength-Kurve fuer beides; Tempo fuer das Grid = Median der
    Fenster-BPMs (stabiler Anker; Drift faengt der Onset-Snap je Beat)."""
    onset, fps = onset_envelope(samples, sr, hop=512, win=1024)
    if onset is None or fps <= 0:
        return BpmTimeline(engine="builtin", beats_per_bar=beats_per_bar)
    total = len(onset)
    wf = max(8, int(window_s * fps))
    sf = max(1, int(step_s * fps))
    segments = []
    start = 0
    while start < total:
        end = min(start + wf, total)
        if end - start < max(8, wf // 3):
            break
        bpm, conf = tempo_from_novelty(onset[start:end], fps, min_bpm, max_bpm, prior_center)
        if bpm > 0:
            center = start + (end - start) / 2.0
            segments.append(BpmSegment(t_ms=int(center / fps * 1000.0),
                                       bpm=round(bpm, 1), confidence=round(conf, 3)))
        start += sf
    # Anker-BPM fuers Grid = Median der Fenster-BPMs (robust).
    vals = sorted(s.bpm for s in segments if s.bpm > 0)
    anchor = vals[len(vals) // 2] if vals else 0.0
    beats_f, downs_f = _fit_beatgrid(onset, fps, anchor, beats_per_bar) if anchor > 0 else ([], [])
    beats_ms = [int(c / fps * 1000.0) for c in beats_f]
    downs_ms = [int(c / fps * 1000.0) for c in downs_f]
    return BpmTimeline(
        segments=segments,
        duration_ms=int(total / fps * 1000.0),
        step_ms=int(step_s * 1000),
        window_ms=int(window_s * 1000),
        beats_ms=beats_ms,
        downbeats_ms=downs_ms,
        engine="builtin",
        beats_per_bar=beats_per_bar,
    )


def detect_meter(beats_ms, downbeats_ms) -> int:
    """Schaetzt die Taktart (Schlaege pro Takt) aus den Downbeat-Abstaenden —
    Median der Beat-Anzahl zwischen aufeinanderfolgenden Downbeats. Am genauesten
    mit echten Downbeats (Beat This!); fuer heuristische Downbeats (builtin/librosa,
    die 4 annehmen) kommt erwartungsgemaess 4 heraus. Fallback 4."""
    import bisect
    beats = list(beats_ms or [])
    downs = sorted(downbeats_ms or [])
    if len(beats) < 2 or len(downs) < 2:
        return 4
    counts = []
    for k in range(len(downs) - 1):
        i = bisect.bisect_left(beats, downs[k])
        j = bisect.bisect_left(beats, downs[k + 1])
        c = j - i
        if 1 <= c <= 12:
            counts.append(c)
    if not counts:
        return 4
    counts.sort()
    med = counts[len(counts) // 2]
    return int(med) if 1 <= med <= 12 else 4


def waveform_peaks(samples, n_buckets: int = 1400) -> list:
    """Downsampled Peak-Huellkurve (abs-Maximum je Bucket, normiert 0..1) fuer die
    Wellenform-Anzeige hinter dem Beatgrid. Leere Liste ohne numpy/Samples."""
    if not HAS_NUMPY or samples is None:
        return []
    x = np.abs(np.asarray(samples, dtype=np.float32))
    if x.size == 0:
        return []
    n = int(min(n_buckets, x.size))
    if n < 1:
        return []
    edges = (np.arange(n + 1) * (x.size / n)).astype(np.int64)
    peaks = []
    for i in range(n):
        a = edges[i]
        b = max(a + 1, edges[i + 1])
        peaks.append(float(x[a:b].max()))
    m = max(peaks) or 1.0
    return [round(p / m, 4) for p in peaks]


def detect_sections(beats_ms, downbeats_ms, peaks, duration_ms,
                    phrase_bars: int = 8) -> list:
    """Grobe Songstruktur aus der Energie pro Takt (Wellenform-Peaks): markiert an
    Phrasen-Grenzen (alle ``phrase_bars`` Takte) Abschnitte wie Intro/Build/Drop/
    Breakdown/Hook. Heuristisch (nicht perfekt), aber zeigt die Struktur fuers
    Show-Bauen. Returns [[t_ms, label, energy0..1], ...]."""
    downs = sorted(int(x) for x in (downbeats_ms or []))
    if len(downs) < 4 or not peaks or duration_ms <= 0:
        return []
    n = len(peaks)

    def _energy(a_ms, b_ms):
        ia = max(0, int(n * a_ms / duration_ms))
        ib = min(n, max(ia + 1, int(n * b_ms / duration_ms)))
        seg = peaks[ia:ib]
        return (sum(seg) / len(seg)) if seg else 0.0

    bar_e = [_energy(downs[k], downs[k + 1]) for k in range(len(downs) - 1)]
    if not bar_e:
        return []
    mx = max(bar_e) or 1.0
    bar_e = [e / mx for e in bar_e]

    sections = []
    prev_e = None
    for k in range(0, len(bar_e), phrase_bars):
        chunk = bar_e[k:k + phrase_bars]
        e = sum(chunk) / len(chunk)
        if k == 0:
            label = "Intro" if e < 0.5 else "Start"
        else:
            d = e - (prev_e if prev_e is not None else e)
            if d >= 0.22:
                label = "Drop"
            elif d <= -0.22:
                label = "Breakdown"
            elif e >= 0.65:
                label = "Hook"
            elif e < 0.32:
                label = "Ruhig"
            else:
                label = "Build" if d > 0.05 else "Teil"
        sections.append([downs[k], label, round(e, 3)])
        prev_e = e
    if bar_e[-1] < 0.4 and len(downs) >= 2:
        sections.append([downs[-1], "Outro", round(bar_e[-1], 3)])
    return sections


def segments_from_beats(beats_ms, step_s: float = 2.0) -> list:
    """BPM-Kurve (BpmSegments) aus einem Beatgrid ableiten — fuer Engines, die nur
    Beats liefern, und nach Grid-Edits (½×/2×) im Editor. Gleitendes Mittel."""
    if not beats_ms or len(beats_ms) < 2:
        return []
    segs = []
    win = 4
    step_ms = max(1, int(step_s * 1000))
    last_t = -step_ms
    for i in range(len(beats_ms) - 1):
        j0 = max(0, i - win // 2)
        j1 = min(len(beats_ms) - 1, i + win // 2)
        ivs = [beats_ms[k + 1] - beats_ms[k] for k in range(j0, j1)]
        ivs = [iv for iv in ivs if iv > 0]
        if not ivs:
            continue
        bpm = 60000.0 / (sum(ivs) / len(ivs))
        t = beats_ms[i]
        if t - last_t >= step_ms:
            segs.append(BpmSegment(t_ms=t, bpm=round(bpm, 1), confidence=0.0))
            last_t = t
    return segs


# ── Dekodierung beliebiger Formate (Qt) + WAV-Fallback ────────────────────────

AUDIO_EXTS = (".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".wav")


def decode_audio_mono(path: str, target_sr: int = 44100):
    """Beliebige Audiodatei → (mono float32 ndarray in [-1,1], samplerate).

    ``.wav`` via stdlib; alles andere via ``QAudioDecoder`` (Qt-Codecs). Gibt
    (None, 0) zurueck, wenn numpy/Qt fehlt oder das Dekodieren scheitert."""
    if not HAS_NUMPY or not path:
        return None, 0
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        try:
            from src.core.audio.offline_analysis import decode_wav_mono
            return decode_wav_mono(path)
        except Exception:
            return None, 0
    return _decode_via_qt(path, target_sr)


def _decode_via_qt(path: str, target_sr: int = 44100):
    """MP3/M4A/FLAC/… → mono float32 ueber QAudioDecoder (synchron via QEventLoop).

    Braucht eine laufende QCoreApplication (in der App vorhanden). Nutzt die vom
    Backend gelieferten Buffer-Formate (Int16/Int32/UInt8/Float) und mischt auf
    mono. Faengt jeden Fehler ab → (None, 0)."""
    try:
        from PySide6.QtCore import QUrl, QEventLoop, QTimer
        from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
        from PySide6.QtWidgets import QApplication
    except Exception:
        return None, 0
    if QApplication.instance() is None:
        # Ohne laufende Qt-App keine Decoder-Events → sauber abbrechen.
        return None, 0

    dec = QAudioDecoder()
    want = QAudioFormat()
    want.setSampleRate(int(target_sr))
    want.setChannelCount(1)
    try:
        want.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    except Exception:
        pass
    try:
        dec.setAudioFormat(want)
    except Exception:
        pass

    chunks: list = []
    sr_holder = {"sr": 0}
    loop = QEventLoop()

    def _read_ready():
        try:
            while dec.bufferAvailable():
                buf = dec.read()
                arr, sr = _buffer_to_mono(buf)
                if arr is not None and arr.size:
                    chunks.append(arr)
                    if sr > 0:
                        sr_holder["sr"] = sr
        except Exception:
            pass

    def _finish(*_):
        loop.quit()

    try:
        dec.bufferReady.connect(_read_ready)
        dec.finished.connect(_finish)
        # error-Signal heisst je nach Qt-Version unterschiedlich.
        for sig in ("errorOccurred", "error"):
            s = getattr(dec, sig, None)
            if s is not None:
                try:
                    s.connect(_finish)
                    break
                except Exception:
                    continue
        dec.setSource(QUrl.fromLocalFile(path))
        # Sicherheitstimeout (kein Haengen bei kaputten Dateien).
        QTimer.singleShot(120000, loop.quit)
        dec.start()
        loop.exec()
        _read_ready()   # evtl. letzte Buffer
    except Exception:
        return None, 0
    finally:
        try:
            dec.stop()
        except Exception:
            pass

    if not chunks:
        return None, 0
    data = np.concatenate(chunks).astype(np.float32)
    sr = sr_holder["sr"] or target_sr
    return data, sr


def _buffer_to_mono(buf):
    """QAudioBuffer → (mono float32 ndarray in [-1,1], samplerate)."""
    if not HAS_NUMPY:
        return None, 0
    try:
        fmt = buf.format()
        ch = max(1, int(fmt.channelCount()))
        sr = int(fmt.sampleRate())
        nbytes = int(buf.byteCount())
        ptr = buf.constData()
        try:
            ptr.setsize(nbytes)
        except Exception:
            pass
        raw = bytes(ptr)
        if not raw:
            return None, sr
        from PySide6.QtMultimedia import QAudioFormat
        sf = fmt.sampleFormat()
        SF = QAudioFormat.SampleFormat
        if sf == SF.Int16:
            a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif sf == SF.Int32:
            a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif sf == SF.UInt8:
            a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif sf == SF.Float:
            a = np.frombuffer(raw, dtype="<f4").astype(np.float32)
        else:
            return None, sr
        if ch > 1:
            usable = (a.size // ch) * ch
            a = a[:usable].reshape(-1, ch).mean(axis=1)
        return a, sr
    except Exception:
        return None, 0


def analyze_file_timeline(path: str, window_s: float = 8.0, step_s: float = 2.0,
                          min_bpm: float = 60.0, max_bpm: float = 200.0) -> BpmTimeline:
    """Komfort: Datei dekodieren + Timeline analysieren (opt-in, kann blockieren)."""
    samples, sr = decode_audio_mono(path)
    if samples is None or sr <= 0:
        return BpmTimeline()
    return analyze_timeline(samples, sr, window_s, step_s, min_bpm, max_bpm)

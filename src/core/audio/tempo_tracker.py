"""Tempo-Tracker fuer die Live-Beat-Erkennung: Onset-Huellkurve -> Tempo, Phase, Beats.

Bekommt vom ``BeatDetector`` die Onset-Huellkurve frameweise (Hop 512) und haelt sie in
einem Ringpuffer (6 s). Alle ``EST_EVERY_FRAMES`` Frames (~93 ms):

1. **Tempo:** Autokorrelation via FFT, **unbiased** (ac[l] / (M - l)), 4-fach-Kamm mit
   Max-Filter +-1 Lag an den Oberwellen (Ellis 2007 / aubio), Log-Normal-Prior
   (120 BPM, sigma 0,9 Oktaven; mit Tempo-Hinweis sigma 0,15), Parabel-Verfeinerung auf
   der rohen ACF. Kandidatenraum min/2 .. 2*max, Ergebnis in [min, max] gefaltet.
2. **Konfidenz:** normierte Periodizitaet r = ac[P]/ac[0] x Onset-Kontrast-Gate
   (max/mean der Huellkurve im 4-s-Fenster) — kalibriert 0..1.
3. **Zustandsautomat:** no_signal / searching / locked; Lock ab gefuelltem Mindestfenster,
   Konfidenz >= 0,35 und drei stabilen Roh-Schaetzungen; Totband 4 % mit EMA-
   Feinnachfuehrung; ausserhalb: Kandidat muss HOLD_S (Oktave: OCT_HOLD_S) konsistent
   bleiben; Stille dreistufig (haelt / friert ein / laesst los).
4. **Phase:** Comb-Suche (32 Phasen, 4-s-Fenster, vektorisiert) + Parabel, Kontinuitaet
   ueber halbe Fehlerkorrektur; naechster Beat als Sample-Position vorhergesagt.
5. **Beat-Emission:** ``beat_due(sample_pos)`` — nur in ``locked`` / hold_stage 0,
   Mindestabstand 0,5 Periode, Latenz-Offset.

Der Tracker kennt keine Uhr — alles rechnet auf Frames und Samples (deterministisch,
unabhaengig von Chunkgroesse und Ankunftszeit). Die Diagnosefelder des Snapshots
(Pegel, Brumm, Jitter, ...) liefert der ``BeatDetector``.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from src.core.audio.onset_flux import WIN, HOP


@dataclass(frozen=True)
class DetectorSnapshot:
    """Unveraenderlicher Zustandsabzug — wird per Referenz veroeffentlicht (Poll aus Qt)."""
    sample_pos: int
    sample_rate: int
    state: str              # no_signal | searching | locked
    hold_stage: int         # 0 aktiv, 1 haelt (Stille), 2 eingefroren, 3 losgelassen
    bpm: float
    bpm_raw: float
    confidence: float
    alt_bpm: float
    alt_score: float
    tempo_hint: float | None
    next_beat_sample: int
    beat_latency_ms: int
    window_s: float
    window_filled_s: float
    signal_s: float
    level_rms_dbfs: float
    peak_dbfs: float
    clip_1s: int
    noise_floor_dbfs: float
    hum_ratio: float
    hum_hz: int
    dc_offset: float
    backlog_ms: float
    jitter_ms: float
    onset_contrast: float
    phase_ok: bool = True   # False: Beat-Raster widerspricht den juengsten Onsets -> Beats stumm


class TempoTracker:
    # ---- Parameter (Herkunft: bpm_arbeit/entwuerfe/dsp_prototyp.md, Abschnitt 1/2) ----
    MEM_S = 6.0             # Ringpuffer Onset-Huellkurve
    MIN_WINDOW_S = 3.5      # Mindestfuellung fuer den ersten Lock
    MIN_EST_S = 2.0         # darunter keine Schaetzung
    PRIOR_BPM = 120.0
    PRIOR_SIGMA = 0.9       # Oktaven (Ellis 2007)
    HINT_SIGMA = 0.15       # Oktaven, bei set_tempo_hint
    DEADBAND = 0.04
    HOLD_S = 1.0            # Widerspruch-Haltezeit fuer Tempowechsel
    OCT_HOLD_S = 3.0        # Haltezeit fuer Oktavsprung
    LOCK_CONF = 0.35
    UNLOCK_CONF = 0.15
    UNLOCK_S = 2.0
    STABLE_N = 3            # Roh-Schaetzungen, die fuer den Lock innerhalb DEADBAND liegen muessen
    SIL_HOLD_S = 0.5
    SIL_FREEZE_S = 2.0
    SIL_RELEASE_S = 10.0
    EST_EVERY_FRAMES = 8    # Schaetzung alle 8 Hops (~93 ms bei 44,1 kHz)
    PHASE_STEPS = 32
    PHASE_WIN_S = 4.0
    CONTRAST_LO = 2.5       # Onset-Kontrast max/mean: darunter Konfidenz 0 ...
    CONTRAST_HI = 7.0       # ... ab hier volles Gate
    R_LO = 0.15             # Periodizitaet r: darunter 0 ...
    R_HI = 0.60             # ... ab hier 1
    AGREE_WIN_S = 1.5       # Fenster fuer den Abgleich Raster <-> juengste Onsets
    AGREE_MIN = 0.4         # Raster-Score / bester Phasen-Score: darunter zaehlt ein Widerspruch
    AGREE_N = 3             # so viele Widersprueche in Folge -> Beats stumm, Schaetzfenster kurz
    SHORT_S = 3.0           # verkuerztes ACF-Fenster bei Widerspruch (schnellerer Tempowechsel)

    def __init__(self, sample_rate: int, min_bpm: float = 60.0, max_bpm: float = 200.0):
        self.sr = int(sample_rate)
        self.fps = self.sr / float(HOP)
        self.N = int(round(self.MEM_S * self.fps))
        self.min_bpm = float(min_bpm)
        self.max_bpm = float(max_bpm)
        self.tempo_hint: float | None = None
        self._lags_setup()
        self._phase_grid = np.arange(self.PHASE_STEPS, dtype=np.float64) / self.PHASE_STEPS
        self.reset()

    # ------------------------------------------------------------ Setup
    def set_bounds(self, min_bpm: float, max_bpm: float):
        self.min_bpm, self.max_bpm = float(min_bpm), float(max_bpm)
        self._lags_setup()
        if self.bpm > 0:
            self.bpm = self._fold(self.bpm)
            self._set_period(self.bpm)

    def _lags_setup(self):
        lo_lag = max(2, int(self.fps * 60.0 / (self.max_bpm * 2.0)))    # bis 2x max (Oktav-Alternative)
        hi_lag = min(self.N - 2, int(self.fps * 60.0 / (self.min_bpm / 2.0)) + 1)
        self.lags = np.arange(lo_lag, max(lo_lag + 1, hi_lag + 1))
        self.cand = 60.0 * self.fps / self.lags
        self._prior_update()

    def _prior_update(self):
        if self.tempo_hint:
            c, s = float(self.tempo_hint), self.HINT_SIGMA
        else:
            c, s = self.PRIOR_BPM, self.PRIOR_SIGMA
        self.pri = np.exp(-0.5 * (np.log2(self.cand / c) / s) ** 2)

    def reset(self):
        self.env = np.zeros(self.N, np.float32)
        self.frames_total = 0
        self.frames_filled = 0
        self.frames_since_est = 0
        self.state = "no_signal"
        self.hold_stage = 3
        self.bpm = 0.0
        self.bpm_raw = 0.0
        self.conf = 0.0
        self.alt_bpm = 0.0
        self.alt_score = 0.0
        self.onset_contrast = 0.0
        self._cand_bpm = 0.0
        self._cand_since = 0.0
        self._stable: list[float] = []
        self._unlock_s = 0.0
        self.silent_s = 0.0
        self.signal_s = 0.0
        self.period_samples = 0.0
        self.next_beat_sample = 0
        self.last_beat_sample = -(10 ** 12)
        self.last_beat_time = 0.0
        self.phase_ok = True
        self._disagree = 0
        self.changed = True     # Zustand seit dem letzten Snapshot veraendert

    # ------------------------------------------------------------ Eingang
    def push(self, flux: np.ndarray, silent_s: float, signal_s: float) -> bool:
        """Neue Flux-Werte (ein Wert je Frame) anhaengen. Liefert True, wenn eine
        Schaetzung gelaufen ist (Snapshot-Anlass)."""
        k = int(flux.size)
        self.silent_s = float(silent_s)
        self.signal_s = float(signal_s)
        if k <= 0:
            return False
        if k >= self.N:
            self.env[:] = flux[-self.N:]
        else:
            self.env[:-k] = self.env[k:]
            self.env[-k:] = flux
        self.frames_total += k
        self.frames_filled = min(self.N, self.frames_filled + k)
        self.frames_since_est += k
        if self.frames_since_est >= self.EST_EVERY_FRAMES:
            self.frames_since_est = 0
            self._update_state()
            return True
        return False

    # ------------------------------------------------------------ Tempo
    def _estimate(self):
        """-> (bpm_roh, conf, alt_bpm, alt_score, lag) oder Nullen."""
        M = int(self.frames_filled)
        if not self.phase_ok:
            M = min(M, int(self.SHORT_S * self.fps))    # Widerspruch: kurzes Gedaechtnis
        if M < self.MIN_EST_S * self.fps:
            return 0.0, 0.0, 0.0, 0.0, 0
        e = self.env[-M:].astype(np.float64)
        e -= e.mean()
        nfft = 1 << int(np.ceil(np.log2(2 * M)))
        F = np.fft.rfft(e, nfft)
        ac = np.fft.irfft(F * np.conj(F), nfft)[:M]
        if ac[0] <= 1e-12:
            return 0.0, 0.0, 0.0, 0.0, 0
        ac = ac / (M - np.arange(M))            # unbiased
        r0 = ac[0]
        nl = int(np.searchsorted(self.lags, M - 1))     # Lags < M-1
        if nl < 2:
            return 0.0, 0.0, 0.0, 0.0, 0
        L = self.lags[:nl]
        pri = self.pri[:nl]
        # Max-Filter +-1 Lag: ganzzahlige Vielfache des gerundeten Lags verfehlen sonst
        # die scharfen ACF-Spitzen der wahren Vielfachen (z. B. 29,7 -> 59,4 statt 60)
        acm = np.empty(M)
        acm[0] = ac[0]
        acm[-1] = ac[-1]
        np.maximum(ac[:-2], ac[1:-1], out=acm[1:-1])
        np.maximum(acm[1:-1], ac[2:], out=acm[1:-1])
        sc = ac[L].copy()
        for h in (2, 3, 4):
            idx = L * h
            m = idx < M
            sc[m] += acm[idx[m]] / h
        np.maximum(sc, 0.0, out=sc)
        sc *= pri
        k = int(np.argmax(sc))
        if sc[k] <= 0:
            return 0.0, 0.0, 0.0, 0.0, 0
        a = int(L[k])
        sh = 0.0
        if 0 < a < M - 1:
            y0, y1, y2 = ac[a - 1], ac[a], ac[a + 1]
            den = y0 - 2 * y1 + y2
            if den != 0:
                sh = float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5))
        bpm = 60.0 * self.fps / (a + sh)
        # Konfidenz: Periodizitaet x Onset-Kontrast
        r = float(np.clip(acm[a] / r0, 0.0, 1.0))
        conf_r = float(np.clip((r - self.R_LO) / (self.R_HI - self.R_LO), 0.0, 1.0))
        contrast = self._contrast()
        gate = float(np.clip((contrast - self.CONTRAST_LO) / (self.CONTRAST_HI - self.CONTRAST_LO), 0.0, 1.0))
        conf = conf_r * gate
        # Oktav-Alternative (Score relativ zum Sieger)
        alt_bpm, alt_score = 0.0, 0.0
        for fac in (2.0, 0.5):
            lag_alt = int(round(a / fac))
            j = int(np.searchsorted(L, lag_alt))
            if 0 <= j < nl and abs(int(L[j]) - lag_alt) <= 1:
                s = float(sc[j] / sc[k])
                if s > alt_score:
                    alt_score, alt_bpm = s, bpm * fac
        return bpm, conf, alt_bpm, alt_score, a

    def _contrast(self) -> float:
        M = min(int(self.frames_filled), int(self.PHASE_WIN_S * self.fps))
        if M <= 0:
            return 0.0
        w = self.env[-M:]
        mean = float(w.mean())
        return float(w.max()) / (mean + 1e-9) if mean > 0 else 0.0

    def _fold(self, bpm: float) -> float:
        if bpm <= 0:
            return 0.0
        for _ in range(8):
            if bpm < self.min_bpm:
                bpm *= 2.0
            elif bpm > self.max_bpm:
                bpm /= 2.0
            else:
                break
        return bpm

    def _set_period(self, bpm: float):
        self.period_samples = 60.0 / bpm * self.sr if bpm > 0 else 0.0

    # ------------------------------------------------------------ Zustand
    def _update_state(self):
        self.changed = True
        est_dt = self.EST_EVERY_FRAMES / self.fps
        # --- Stille dreistufig
        if self.silent_s >= self.SIL_RELEASE_S:
            if self.state != "no_signal":
                self.env[:] = 0.0
                self.frames_filled = 0
            self.state, self.hold_stage = "no_signal", 3
            self.bpm, self.bpm_raw, self.conf = 0.0, 0.0, 0.0
            self.alt_bpm, self.alt_score = 0.0, 0.0
            self.next_beat_sample = 0
            self._stable.clear()
            self._cand_bpm, self._cand_since = 0.0, 0.0
            return
        if self.silent_s >= self.SIL_FREEZE_S:
            self.hold_stage = 2
            self.conf = 0.0
            self.next_beat_sample = 0
            return
        if self.silent_s >= self.SIL_HOLD_S:
            self.hold_stage = 1
            self.conf = 0.0
            self.next_beat_sample = 0
            return
        if self.state == "no_signal" and self.signal_s > 0:
            self.state = "searching"
        self.hold_stage = 0
        raw, conf, alt_bpm, alt_score, lag = self._estimate()
        self.bpm_raw = self._fold(raw)
        self.alt_bpm, self.alt_score = self._fold(alt_bpm), alt_score
        self.onset_contrast = self._contrast()
        min_frames = self.MIN_WINDOW_S * self.fps
        self.conf = conf if self.frames_filled >= min_frames else conf * (self.frames_filled / min_frames)
        if raw <= 0:
            return
        # --- Suche -> Lock
        if self.state != "locked":
            self._stable.append(self.bpm_raw)
            del self._stable[:-self.STABLE_N]
            if (self.frames_filled >= min_frames and self.conf >= self.LOCK_CONF
                    and len(self._stable) >= self.STABLE_N
                    and max(self._stable) - min(self._stable) <= self.DEADBAND * self.bpm_raw):
                self.state = "locked"
                self.bpm = self.bpm_raw
                self._set_period(self.bpm)
                self._fit_phase(force=True)
            return
        # --- eingerastet: Hysterese nach unten
        if self.conf < self.UNLOCK_CONF:
            self._unlock_s += est_dt
            if self._unlock_s >= self.UNLOCK_S:
                self.state = "searching"
                self._unlock_s = 0.0
                self.next_beat_sample = 0
                self._stable.clear()
                return
        else:
            self._unlock_s = 0.0
        dev = abs(self.bpm_raw - self.bpm) / self.bpm
        if dev <= self.DEADBAND:
            self.bpm = 0.9 * self.bpm + 0.1 * self.bpm_raw      # Feinnachfuehrung im Totband
            self._set_period(self.bpm)
            self._cand_bpm, self._cand_since = 0.0, 0.0
        else:
            is_oct = any(abs(self.bpm_raw - self.bpm * f) / (self.bpm * f) <= self.DEADBAND
                         for f in (2.0, 0.5))
            if self._cand_bpm and abs(self.bpm_raw - self._cand_bpm) / self._cand_bpm <= self.DEADBAND:
                self._cand_since += est_dt
            else:
                self._cand_bpm, self._cand_since = self.bpm_raw, est_dt
            need = self.OCT_HOLD_S if is_oct else self.HOLD_S
            if self._cand_since >= need and self.conf >= self.LOCK_CONF:
                self.bpm = self.bpm_raw
                self._set_period(self.bpm)
                self._cand_bpm, self._cand_since = 0.0, 0.0
                self._fit_phase(force=True)
                return
        self._fit_phase()

    # ------------------------------------------------------------ Phase
    def _last_frame_sample(self) -> float:
        """Sample-Position der Mitte des letzten Frames (dort liegt der Onset, dessen
        Flux in env[-1] steht)."""
        return (self.frames_total - 1) * HOP + WIN / 2.0

    def _fit_phase(self, force: bool = False):
        if self.period_samples <= 0:
            return
        P = self.period_samples / HOP                       # Periode in Frames
        M = min(int(self.frames_filled), int(self.PHASE_WIN_S * self.fps))
        n_beats = int(M / P)
        if n_beats < 2:
            return
        env = self.env[-M:]
        # Comb-Suche vektorisiert: (PHASE_STEPS x n_beats) Indizes, ein Fancy-Index
        phis = self._phase_grid * P
        idx = (M - 1) - phis[:, None] - np.arange(n_beats, dtype=np.float64)[None, :] * P
        ii = np.floor(idx + 0.5).astype(np.intp)
        valid = ii >= 0
        ii[~valid] = 0
        scores = (env[ii] * valid).sum(axis=1)
        s = int(np.argmax(scores))
        # Parabel ueber die Nachbar-Phasen (zyklisch) gegen die Rasterung von P/32
        y0, y1, y2 = scores[(s - 1) % self.PHASE_STEPS], scores[s], scores[(s + 1) % self.PHASE_STEPS]
        den = y0 - 2 * y1 + y2
        sh = float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5)) if den != 0 else 0.0
        best_phi = (s + sh) * P / self.PHASE_STEPS
        last_beat = self._last_frame_sample() - best_phi * HOP
        if force:
            self.phase_ok, self._disagree = True, 0
        else:
            self._check_agreement(P)
        return self._apply_phase(last_beat, force)

    def _check_agreement(self, P: float):
        """Passt das vorhergesagte Raster zu den Onsets der letzten AGREE_WIN_S Sekunden?
        Score des Rasters (Max-Filter +-2 Frames) gegen den besten Phasen-Score im selben
        Fenster; AGREE_N Widersprueche in Folge schalten die Beats stumm."""
        M2 = min(int(self.frames_filled), int(self.AGREE_WIN_S * self.fps))
        n2 = int(M2 / P)
        if n2 < 2 or self.next_beat_sample <= 0:
            return
        env = self.env[-M2:]
        ks = np.arange(n2, dtype=np.float64)[None, :] * P
        idx = (M2 - 1) - (self._phase_grid * P)[:, None] - ks
        ii = np.floor(idx + 0.5).astype(np.intp)
        valid = ii >= 0
        ii[~valid] = 0
        best = float((env[ii] * valid).sum(axis=1).max())
        # Raster: juengster vorhergesagter Beat, als Frames vom letzten Frame aus
        last_pred = self.next_beat_sample - self.period_samples
        phi = ((self._last_frame_sample() - last_pred) / HOP) % P
        gi = np.floor((M2 - 1) - phi - ks[0] + 0.5).astype(np.intp)
        gi = gi[gi >= 2]
        if gi.size == 0:
            return
        score = 0.0
        for d in (-2, -1, 0, 1, 2):
            score = np.maximum(score, env[np.clip(gi + d, 0, M2 - 1)])
        score = float(np.sum(score))
        if best > 0 and score / best < self.AGREE_MIN:
            self._disagree += 1
            if self._disagree >= self.AGREE_N and self.phase_ok:
                self.phase_ok = False
                self.changed = True
        else:
            self._disagree = 0
            if not self.phase_ok:
                self.phase_ok = True
                self.changed = True

    def _apply_phase(self, last_beat: float, force: bool):
        P = self.period_samples
        pos = self.frames_total * HOP        # bis hierher liegen Frames vor
        if force or self.next_beat_sample <= 0:
            nb = last_beat
            while nb <= pos or nb < self.last_beat_sample + 0.5 * P:
                nb += P
            self.next_beat_sample = int(round(nb))
            return
        # Kontinuitaet: Vorhersage sanft zur Messung ziehen (halber Fehler, um +-P/2 gefaltet).
        # Rutscht der naechste Beat dabei knapp in die Vergangenheit, bleibt er stehen und
        # feuert im naechsten Chunk (mit seiner eigenen Zeit) — sonst fehlt er ganz.
        pred_last = self.next_beat_sample - P
        err = (last_beat - pred_last + P / 2.0) % P - P / 2.0
        nb = self.next_beat_sample + 0.5 * err
        while nb < pos - 0.5 * P or nb < self.last_beat_sample + 0.5 * P:
            nb += P
        self.next_beat_sample = int(round(nb))

    # ------------------------------------------------------------ Beats
    def beat_due(self, sample_pos: int, latency_samples: float) -> bool:
        """Nach jedem Chunk aufrufen; True = Beat feuern (Zeit in ``last_beat_time``)."""
        if self.state != "locked" or self.hold_stage != 0 or self.next_beat_sample <= 0:
            return False
        if sample_pos + latency_samples < self.next_beat_sample:
            return False
        P = self.period_samples
        if not self.phase_ok:
            # Raster widerspricht den Onsets: weiterzaehlen, aber nicht feuern
            self.next_beat_sample += int(round(P))
            return False
        if self.next_beat_sample - self.last_beat_sample < 0.5 * P:
            # Doppel-Beat-Schutz: Mindestabstand halbe Periode
            self.next_beat_sample += int(round(P))
            return False
        self.last_beat_sample = self.next_beat_sample
        self.last_beat_time = self.next_beat_sample / self.sr
        self.next_beat_sample += int(round(P))
        self.changed = True
        return True

    # ------------------------------------------------------------ Eingriffe (Qt-Thread, unter Lock des Detektors)
    def resync_phase(self, sample_pos: int):
        """Beat-Raster auf 'jetzt': naechster Beat = jetzt + Periode."""
        if self.period_samples <= 0:
            return
        self.last_beat_sample = int(sample_pos)
        self.last_beat_time = sample_pos / self.sr
        self.next_beat_sample = int(sample_pos + self.period_samples)
        self.changed = True

    def set_tempo_hint(self, bpm: float | None):
        self.tempo_hint = float(bpm) if bpm else None
        self._prior_update()
        if bpm and self.bpm > 0:
            b = self.bpm
            while b < bpm / 1.4:
                b *= 2.0
            while b > bpm * 1.4:
                b /= 2.0
            b = self._fold(b)
            if b != self.bpm:
                self.bpm = b
                self._set_period(b)
                self._cand_bpm, self._cand_since = 0.0, 0.0
                self._fit_phase(force=True)
        self.changed = True

    def set_octave_preference(self, step: int):
        if self.bpm <= 0:
            return
        b = self.bpm * (2.0 if step > 0 else 0.5)
        if self.min_bpm <= b <= self.max_bpm:
            self.bpm = b
            self._set_period(b)
            self._cand_bpm, self._cand_since = 0.0, 0.0
            self._fit_phase(force=True)
            self.changed = True

    def inject_tempo(self, bpm: float, sample_pos: int):
        """Test-Hook: Zustand 'locked' mit gegebenem Tempo setzen, als haette die
        Schaetzung es geliefert (Roh ungefaltet, Rastung gefaltet, Konfidenz 1)."""
        self.state, self.hold_stage = "locked", 0
        self.bpm_raw = float(bpm)
        self.bpm = self._fold(float(bpm))
        self.conf = 1.0
        self._set_period(self.bpm)
        self.next_beat_sample = int(sample_pos + self.period_samples)
        self.changed = True

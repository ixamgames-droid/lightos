"""Tempo-Tracker fuer die Live-Beat-Erkennung: Onset-Huellkurve -> Tempo, Phase, Beats.

Bekommt vom ``BeatDetector`` die Onset-Huellkurve frameweise (Hop 512) und haelt sie in
einem Ringpuffer (6 s). Alle ``EST_EVERY_FRAMES`` Frames (~93 ms):

1. **Tempo:** Huellkurve gaussisch geglaettet (1 Frame), Autokorrelation via FFT,
   **unbiased** (ac[l] / (M - l)), 4-fach-Kamm mit Max-Filter an den Oberwellen (+-1 Lag,
   ab der 3. +-2; Ellis 2007 / aubio), Sub-Oktav-Strafe (Spitze beim halben Lag fast so hoch
   wie die eigene -> Kandidat ist die halbe Oktave eines Pulszugs), Log-Normal-Prior
   (120 BPM, sigma 0,9 Oktaven; mit Tempo-Hinweis sigma 0,15), Parabel-Verfeinerung auf
   der rohen ACF. Kandidatenraum min/2 .. 2*max, Ergebnis in [min, max] gefaltet (knapp
   ausserhalb: geklemmt). **Oktav-Entscheider Bass (BPM-12):** waehlt der Kamm die langsame
   Oktave und ist x2 plausibel, prueft eine zweite Huellkurve (Bass-Flux 30..200 Hz, eigener
   Ring), ob zwischen den Beats *dieselben* Bass-Onsets liegen (Kick-Lage + ACF-Gleichartigkeit)
   -> Backbeat (Kick jeder Beat + Snare 2/4) rastet auf das volle Tempo; Offbeat-Bass und
   Bass/Hats auf Achteln bleiben. Grenze: Two-Step (Kick nur auf 1 und 3) und Halftime
   bleiben auf der halben Oktave — Alternative im Snapshot, x2 / Tempo-Bereich korrigieren.
2. **Konfidenz:** normierte Periodizitaet r = ac[P]/ac[0] x Onset-Kontrast-Gate
   (max/mean der Huellkurve im 4-s-Fenster) — kalibriert 0..1.
3. **Zustandsautomat:** no_signal / searching / locked; Lock ab gefuelltem Mindestfenster,
   Konfidenz >= 0,35 und drei stabilen Roh-Schaetzungen; Totband 4 % mit EMA-
   Feinnachfuehrung; ausserhalb: Kandidat muss HOLD_S (Oktave: OCT_HOLD_S) konsistent
   bleiben; Stille dreistufig (haelt / friert ein / laesst los) — eingerastet beginnt
   „haelt" fruehestens nach 1,25 Beat-Perioden (Klick 60 BPM = 1 s Luecke je Beat).
4. **Phase:** Comb-Suche (32 Phasen, bei langen Perioden 1 Frame je Schritt; 4-s-Fenster,
   vektorisiert) + Parabel, Kontinuitaet
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
    SUB_OCT_PENALTY = 1.0   # Kamm: Sub-Oktav-Strafe (s. _estimate), 0 = aus
    SUB_OCT_TAU = 0.7       # ... nur der Anteil von acm[Lag/2] ueber TAU x acm[Lag] zaehlt
    EST_SMOOTH = True       # Huellkurve vor der ACF gaussisch glaetten (SMOOTH_SIGMA Frames)
    SMOOTH_SIGMA = 1.0      # Frames (~12 ms); Spitzen zwischen zwei Lags verlieren sonst ACF-Hoehe
    HARM_WIDE = True        # Max-Filter +-2 an den Oberwellen 3 und 4
    DEADBAND = 0.04
    HOLD_S = 1.0            # Widerspruch-Haltezeit fuer Tempowechsel
    OCT_HOLD_S = 3.0        # Haltezeit fuer Oktavsprung
    LOCK_CONF = 0.35
    UNLOCK_CONF = 0.15
    UNLOCK_S = 2.0
    STABLE_N = 3            # Roh-Schaetzungen, die fuer den Lock innerhalb DEADBAND liegen muessen
    SIL_HOLD_S = 0.5
    SIL_HOLD_PERIODS = 1.25 # eingerastet: Halten fruehestens nach 1,25 Beat-Perioden (Klick 60 BPM = 1 s Luecke)
    SIL_FREEZE_S = 2.0
    SIL_RELEASE_S = 10.0
    EST_EVERY_FRAMES = 8    # Schaetzung alle 8 Hops (~93 ms bei 44,1 kHz)
    PHASE_STEPS = 32
    PHASE_WIN_S = 4.0
    CONTRAST_LO = 3.0       # Onset-Kontrast max/mean: darunter Konfidenz 0 ...
    CONTRAST_HI = 7.5       # ... ab hier volles Gate (Brumm allein 3,7; Kick+Rauschen -30 dB 11,8)
    SPARSE_LO = 3.0         # zweites, mildes Gate max/median: Brumm-Modulation ~5, Beats >> 10
    SPARSE_HI = 7.0
    R_LO = 0.15             # Periodizitaet r: darunter 0 ...
    R_HI = 0.60             # ... ab hier 1
    AGREE_WIN_S = 1.5       # Fenster fuer den Abgleich Raster <-> juengste Onsets
    AGREE_MIN = 0.4         # Raster-Score / bester Phasen-Score: darunter zaehlt ein Widerspruch
    AGREE_N = 3             # so viele Widersprueche in Folge -> Beats stumm, Schaetzfenster kurz
    SHORT_S = 3.0           # verkuerztes ACF-Fenster bei Widerspruch (schnellerer Tempowechsel)
    # ---- Bass-Oktav-Entscheider (BPM-12). Greift nur, wenn die Flux-Wahl die LANGSAME Oktave ist,
    # x2 in den Grenzen liegt und kein Tempo-Hinweis gesetzt ist. Messherkunft: Messbank
    # bpm_bench (08l/08p Backbeat 150..200 soll x2; 03_kick_bass_hats_90, 08n_offbeat_bass_80..100,
    # 08m_dauerbass, 08o_halftime_140 und Zusatzmessungen lauter Offbeat-Bass 0,9..2,5, Two-Step,
    # Brumm/Rauschen sollen bleiben), Werte min..max je Pruefung nach 4 s.
    BASS_OCT = True         # Schalter (Tests/Bank)
    BASS_ALT_MIN = 0.45     # Flux-Score der x2-Alternative: Backbeat 0,52..1,00; Kick/Klick allein <= 0,30 und
                            # Kick 90 + Brumm 0,29 (dort taeuscht die Bass-ACF) -> gar nicht erst pruefen
    BASS_CONTRAST_MIN = 6.0   # Bass-Flux max/mean: Backbeat >= 12,2; bassdominierter Brumm 3,9..6,7 (Sicherheitsgate)
    BASS_SIM_MIN = 0.6      # Gleichartigkeit ac_bass[L/2]/ac_bass[L]: Backbeat 0,63..1,35 (Reese bis 1,6);
    BASS_SIM_MAX = 1.5      # darunter Kick+Bass+Hats 90 0,23..0,32, Two-Step; darueber Brumm (1,6..6,0), Boom-Bap
    BASS_PHASE_MIN = 0.6    # Kick-Lage: Bass-Flux zwischen / auf den Flux-Beats: Backbeat 0,74..1,32; Kick+Bass+
    BASS_PHASE_MAX = 1.6    # Hats 90 0,13..0,21, Offbeat-Bass 0,27..0,30, Two-Step 5,0..7,2; Pluck-Offbeat 0,64..1,61
    BASS_HI_MIN = 0.17      # Klick-Lage (TRAGEND gegen Offbeat-Bass): Hochband-Flux zwischen / auf den Beats:
    BASS_HI_MAX = 1.0       # Backbeat 0,18..0,36 (Median >= 0,19); Pluck-/Offbeat-Bass 0,01..0,16 (Median <= 0,12),
                            # Achtel-Bass ohne Kick 0,01..0,05; ueber 1: Flux-Phase liegt auf dem Offbeat
    BASS_R_MIN = 0.3        # Bass-Periodizitaet ac_bass[L]/ac_bass[0]: Backbeat 0,45..1,00; Boom-Bap (Kick 1 + 3-und)
                            # 0,00..0,17, Breakbeat 0,00..0,04 — dort ist die Gleichartigkeit ein Quotient aus Rauschen
    BASS_PHASE_HOLD = (0.5, 1.8)    # Halten (Hysterese): weitere Grenzen, sobald x2 entschieden ist
    BASS_SIM_HOLD = (0.5, 1.7)
    BASS_HI_HOLD = (0.12, 1.0)
    BASS_DEBOUNCE_N = 3     # so viele widersprechende Pruefungen in Folge kippen die Entscheidung (~0,28 s)

    def __init__(self, sample_rate: int, min_bpm: float = 60.0, max_bpm: float = 200.0):
        self.sr = int(sample_rate)
        self.fps = self.sr / float(HOP)
        self.N = int(round(self.MEM_S * self.fps))
        self.min_bpm = float(min_bpm)
        self.max_bpm = float(max_bpm)
        self.tempo_hint: float | None = None
        self._lags_setup()
        self._grids: dict[int, np.ndarray] = {}
        r = int(np.ceil(2.0 * self.SMOOTH_SIGMA))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / self.SMOOTH_SIGMA) ** 2)
        self._smooth_k = k / k.sum()
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
        self.env_bass = np.zeros(self.N, np.float32)     # Bass-Huellkurve (BPM-12), gleicher Takt
        self.env_hi = np.zeros(self.N, np.float32)       # Hochband-Huellkurve (BPM-12), gleicher Takt
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
        self.bass_diag = None   # (x2-Score, Bass-Kontrast, Kick-Lage, Gleichartigkeit, Klick-Lage) der letzten Pruefung
        self.bass_dbl = False   # entprellte Entscheidung des Bass-Entscheiders (Hysterese)
        self._bass_run = 0      # Pruefungen in Folge, die der Entscheidung widersprechen
        self.oct_pref = 0       # Nutzer-Oktave (set_octave_preference): -1 / 0 / +1 ...
        self.changed = True     # Zustand seit dem letzten Snapshot veraendert

    # ------------------------------------------------------------ Eingang
    def push(self, flux: np.ndarray, silent_s: float, signal_s: float, bass: np.ndarray | None = None,
             hi: np.ndarray | None = None) -> bool:
        """Neue Flux-Werte (ein Wert je Frame) anhaengen; ``bass`` / ``hi`` = Bass- und
        Hochband-Flux derselben Frames (None: Nullen, Oktav-Entscheider enthaelt sich).
        Liefert True, wenn eine Schaetzung gelaufen ist (Snapshot-Anlass)."""
        k = int(flux.size)
        self.silent_s = float(silent_s)
        self.signal_s = float(signal_s)
        if k <= 0:
            return False
        if bass is None or int(bass.size) != k:
            bass = np.zeros(k, np.float32)
        if hi is None or int(hi.size) != k:
            hi = np.zeros(k, np.float32)
        if k >= self.N:
            self.env[:] = flux[-self.N:]
            self.env_bass[:] = bass[-self.N:]
            self.env_hi[:] = hi[-self.N:]
        else:
            self.env[:-k] = self.env[k:]
            self.env[-k:] = flux
            self.env_bass[:-k] = self.env_bass[k:]
            self.env_bass[-k:] = bass
            self.env_hi[:-k] = self.env_hi[k:]
            self.env_hi[-k:] = hi
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
        if self.EST_SMOOTH:
            # leichte Glaettung: eine Spitze, die zwischen zwei Lags faellt (195 BPM = 26,5 Frames),
            # verliert sonst ~1/3 ihrer ACF-Hoehe gegen die ganzzahlige Sub-Oktave (Kick 195 -> 97)
            e = np.convolve(e, self._smooth_k, mode="same")
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
        if self.HARM_WIDE:
            # Oberwellen h*round(L) liegen bis zu h/2 Frames neben h*L -> ab h=3 Max ueber +-2
            acm2 = acm.copy()
            np.maximum(acm2[1:-1], acm[:-2], out=acm2[1:-1])
            np.maximum(acm2[1:-1], acm[2:], out=acm2[1:-1])
        else:
            acm2 = acm
        # Kamm, normiert auf die im Fenster verfuegbaren Oberwellen: bei kurzem Fenster
        # (Aufwaermphase, SHORT_S) fehlen langsamen Kandidaten die 3./4. Oberwelle, der
        # doppelt so schnelle hat alle — unnormiert kippt Kick+Bass+Hats 90 beim Einrasten
        # auf 180 (Bank-Fall 03: 9,3 s Einrastzeit, 8 Fehlalarme)
        sc = acm[L].copy()
        wsum = np.ones(nl)
        for h in (2, 3, 4):
            idx = L * h
            m = idx < M
            sc[m] += (acm if h == 2 else acm2)[idx[m]] / h
            wsum[m] += 1.0 / h
        sc *= (1.0 + 1.0 / 2 + 1.0 / 3 + 1.0 / 4) / wsum
        # Sub-Oktav-Strafe: ist die Spitze beim HALBEN Lag fast so hoch wie die eigene, ist
        # der Kandidat die halbe Oktave eines schnelleren Pulses. Ohne sie ist der Kamm fuer
        # reine Pulszuege symmetrisch (alle Vielfachen gleich hoch) und allein der Prior
        # entscheidet — der kippt ab 120*sqrt(2) = 170 BPM zur halben Oktave (Kick 185 -> 92).
        # Nur der Ueberschuss ueber TAU x eigene Spitze zaehlt: Pulszug 0,94 (bestraft),
        # Hats auf Achteln 0,64 (Bank-Fall 03_kick_bass_hats_90: unter TAU, sonst kippt er beim
        # Einrasten auf 180) / Backbeat-Kick 0,75-0,78 (kaum) — die schnelle Oktave selbst
        # hat beim halben Lag nichts (ac ~ 0).
        own = np.maximum(acm[L], 0.0)
        half = np.maximum(acm[np.rint(L / 2.0).astype(np.intp)], 0.0)
        sc -= (self.SUB_OCT_PENALTY / (1.0 - self.SUB_OCT_TAU)) * np.maximum(half - self.SUB_OCT_TAU * own, 0.0)
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
        contrast, sparse = self._contrast(with_sparse=True)
        gate = float(np.clip((contrast - self.CONTRAST_LO) / (self.CONTRAST_HI - self.CONTRAST_LO), 0.0, 1.0))
        gate *= float(np.clip((sparse - self.SPARSE_LO) / (self.SPARSE_HI - self.SPARSE_LO), 0.0, 1.0))
        conf = conf_r * gate
        # Oktav-Alternative (Score relativ zum Sieger)
        alt_bpm, alt_score = 0.0, 0.0
        s_dbl = 0.0
        for fac in (2.0, 0.5):
            la = a / fac                                # Lag der Alternative (evtl. halbzahlig)
            j0 = int(np.searchsorted(L, la - 1.0))
            j1 = int(np.searchsorted(L, la + 1.0, side="right"))
            if j0 < j1:                                 # Max ueber +-1 Lag, sonst rutscht der
                s = float(sc[j0:j1].max() / sc[k])      # Wert bei scharfen Spitzen ins Tal
                if fac == 2.0:
                    s_dbl = s
                if s > alt_score:
                    alt_score, alt_bpm = s, bpm * fac
        if self._bass_says_double(M, a, bpm, s_dbl):
            # Bass-Huellkurve traegt die schnelle Oktave: Sieger x2, die Flux-Wahl wird Alternative
            return bpm * 2.0, conf, bpm, min(1.0, 1.0 / max(s_dbl, 1e-9)), a
        return bpm, conf, alt_bpm, alt_score, a

    def _bass_says_double(self, M: int, a: int, bpm: float, s_dbl: float) -> bool:
        """Oktav-Entscheider (BPM-12): Flux waehlte Lag ``a``, die x2-Alternative hat Score
        ``s_dbl``. True = zwischen den Flux-Beats liegen *Kicks* wie auf ihnen (Backbeat).

        Unterscheidet Backbeat (Kick auf jedem Beat, Snare 2/4 -> Flux-Periode 2 Beats) von
        Bass/Hats auf Achteln und Offbeat-Bass, die ebenfalls Bass-Onsets bei L/2 haben:
        1. Kick-Lage: Bass-Flux zwischen den Flux-Beats (Phase + L/2) muss aehnlich stark sein
           wie auf ihnen (Phase aus der Flux-Huellkurve, Max +-1 Frame).
        2. Gleichartigkeit: ac_bass[L/2] / ac_bass[L] im Fenster (Brumm-/Pulszug-Sicherung).
        3. Klick-Lage (tragend gegen Offbeat-Bass): Hochband-Flux (ab ~800 Hz) zwischen den
           Beats / auf den Beats — eine Kick bringt ihre Transiente mit, eine Bassnote nicht.
        Entprellt: die Entscheidung kippt erst nach BASS_DEBOUNCE_N widersprechenden Pruefungen
        in Folge, und das Halten nutzt weitere Grenzen als das Einschalten (Hysterese).
        Gates: Tempo-Hinweis entscheidet selbst; x2 muss in den Grenzen liegen; Flux-Score der
        x2-Alternative >= BASS_ALT_MIN; Bass-Kontrast >= BASS_CONTRAST_MIN (Brumm); Bass-Periodizitaet
        >= BASS_R_MIN (Boom-Bap/Breakbeat). Die Nutzer-Oktave (set_octave_preference) wird danach auf das Ergebnis
        angewandt, die Oktav-Hysterese (OCT_HOLD_S) gilt unveraendert."""
        self.bass_diag = None
        if not self.BASS_OCT or self.tempo_hint:    # Hinweis entscheidet selbst: Entscheidung verwerfen
            self.bass_dbl, self._bass_run = False, 0
            return False
        if a < 4 or self._fold(bpm) * 2.0 > self.max_bpm:
            return False                    # x2 nicht moeglich (Flux steht schon oben): Entscheidung bleibt
        raw = self._bass_raw(M, a, s_dbl)
        if raw != self.bass_dbl:
            self._bass_run += 1
            if self._bass_run >= self.BASS_DEBOUNCE_N:
                self.bass_dbl, self._bass_run = raw, 0
        else:
            self._bass_run = 0
        return self.bass_dbl

    def _bass_raw(self, M: int, a: int, s_dbl: float) -> bool:
        """Eine Pruefung ohne Entprellung (Grenzen je nach aktueller Entscheidung)."""
        if s_dbl < self.BASS_ALT_MIN:
            return False
        b = self.env_bass[-M:].astype(np.float64)
        mean_b = float(b.mean())
        if mean_b <= 1e-12:
            return False
        contrast = float(b.max()) / mean_b
        n = (M - 2) // a
        if n < 2 or contrast < self.BASS_CONTRAST_MIN:
            return False
        e = self.env[-M:]
        h = self.env_hi[-M:]
        # Max-Filter +-1 Frame (Onset kann zwischen zwei Frames liegen)
        em = np.maximum(np.maximum(e[:-2], e[1:-1]), e[2:])
        bm = np.maximum(np.maximum(b[:-2], b[1:-1]), b[2:])
        hm = np.maximum(np.maximum(h[:-2], h[1:-1]), h[2:])
        # Beat-Indizes relativ zum letzten gefilterten Frame (em hat Laenge M-2, Index i <-> Frame i+1)
        ph = np.arange(a)
        idx = (M - 3) - ph[:, None] - np.arange(n)[None, :] * a
        ok = idx >= 0
        idx[~ok] = 0
        j = int(np.argmax((em[idx] * ok).sum(axis=1)))
        on = idx[j][ok[j]]
        off = on - (a // 2) if a % 2 == 0 else on - (a + 1) // 2
        off = off[off >= 0]
        on_s = float(bm[on].sum())
        if on_s <= 1e-12:
            return False
        q_phase = float(bm[off].sum()) / on_s
        hi_on = float(hm[on].sum())
        q_hi = float(hm[off].sum()) / hi_on if hi_on > 1e-12 else 0.0
        # nur 6 Lags noetig -> Skalarprodukte statt FFT (unbiased wie in _estimate)
        b -= mean_b
        hl = int(round(a / 2.0))

        def ac_max(l0: int) -> float:
            return max(float(np.dot(b[:M - l], b[l:])) / (M - l) for l in (l0 - 1, l0, l0 + 1))
        pk_full = ac_max(a)
        if pk_full <= 1e-12:
            return False
        q_sim = ac_max(hl) / pk_full
        r_bass = pk_full / max(float(np.dot(b, b)) / M, 1e-12)
        self.bass_diag = (s_dbl, contrast, q_phase, q_sim, q_hi, r_bass)     # Diagnose (Messbank/Tests)
        if r_bass < self.BASS_R_MIN:        # Bass ohne Periode L (Boom-Bap, Breakbeat): q_sim waere Rauschen
            return False
        if self.bass_dbl:                   # halten: weitere Grenzen (Hysterese)
            return (self.BASS_PHASE_HOLD[0] <= q_phase <= self.BASS_PHASE_HOLD[1]
                    and self.BASS_SIM_HOLD[0] <= q_sim <= self.BASS_SIM_HOLD[1]
                    and self.BASS_HI_HOLD[0] <= q_hi <= self.BASS_HI_HOLD[1])
        return (self.BASS_PHASE_MIN <= q_phase <= self.BASS_PHASE_MAX
                and self.BASS_SIM_MIN <= q_sim <= self.BASS_SIM_MAX
                and self.BASS_HI_MIN <= q_hi <= self.BASS_HI_MAX)

    def _contrast(self, with_sparse: bool = False):
        """Onset-Kontrast im 4-s-Fenster: max/mean (und max/median als Sparsity-Mass)."""
        M = min(int(self.frames_filled), int(self.PHASE_WIN_S * self.fps))
        if M <= 0:
            return (0.0, 0.0) if with_sparse else 0.0
        w = self.env[-M:]
        mean = float(w.mean())
        mx = float(w.max())
        c = mx / (mean + 1e-9) if mean > 0 else 0.0
        if not with_sparse:
            return c
        med = float(np.median(w))
        return c, (mx / (med + 1e-6) if mean > 0 else 0.0)

    def _fold(self, bpm: float) -> float:
        if bpm <= 0:
            return 0.0
        # knapp ausserhalb (Parabel liefert 59,9 bei Klick 60 BPM, Grenze 60): klemmen statt
        # oktavieren — sonst meldet der Tracker 119,9 und rastet nach OCT_HOLD_S dort ein
        if self.min_bpm * (1.0 - self.DEADBAND) <= bpm < self.min_bpm:
            return self.min_bpm
        if self.max_bpm < bpm <= self.max_bpm * (1.0 + self.DEADBAND):
            return self.max_bpm
        for _ in range(8):
            if bpm < self.min_bpm:
                bpm *= 2.0
            elif bpm > self.max_bpm:
                bpm /= 2.0
            else:
                break
        return bpm

    def _with_pref(self, bpm: float) -> float:
        """Nutzer-Oktave (x2 / x0,5 je Stufe) anwenden, wenn das Ergebnis in den Grenzen bleibt."""
        if not self.oct_pref or bpm <= 0:
            return bpm
        b = bpm * (2.0 ** self.oct_pref)
        return b if self.min_bpm <= b <= self.max_bpm else bpm

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
                self.env_bass[:] = 0.0
                self.env_hi[:] = 0.0
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
        hold_s = self.SIL_HOLD_S
        if self.state == "locked" and self.bpm > 0:
            # sparsames Material (Klick 60 BPM: 1 s digitale Stille je Beat) sonst im Dauer-Halten
            hold_s = min(self.SIL_FREEZE_S, max(hold_s, self.SIL_HOLD_PERIODS * 60.0 / self.bpm))
        if self.silent_s >= hold_s:
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
        raw = self._with_pref(self.bpm_raw)     # Nutzer-Oktave auf die Roh-Schaetzung anwenden
        dev = abs(raw - self.bpm) / self.bpm
        if dev <= self.DEADBAND:
            self.bpm = 0.9 * self.bpm + 0.1 * raw               # Feinnachfuehrung im Totband
            self._set_period(self.bpm)
            self._cand_bpm, self._cand_since = 0.0, 0.0
        else:
            is_oct = any(abs(raw - self.bpm * f) / (self.bpm * f) <= self.DEADBAND
                         for f in (2.0, 0.5))
            if self._cand_bpm and abs(raw - self._cand_bpm) / self._cand_bpm <= self.DEADBAND:
                self._cand_since += est_dt
            else:
                self._cand_bpm, self._cand_since = raw, est_dt
            need = self.OCT_HOLD_S if is_oct else self.HOLD_S
            if self._cand_since >= need and self.conf >= self.LOCK_CONF:
                self.bpm = raw
                self._set_period(self.bpm)
                self._cand_bpm, self._cand_since = 0.0, 0.0
                self._fit_phase(force=True)
                return
        self._fit_phase()

    # ------------------------------------------------------------ Phase
    def _phase_grid(self, P: float) -> np.ndarray:
        """Phasenraster 0..1: PHASE_STEPS Schritte, bei langen Perioden hoechstens ein Frame
        je Schritt (60 BPM = 86 Frames: 32 Schritte waeren 2,7 Frames — eine 1-Frame-Spitze
        faellt dann zwischen die Raster, der Fit zieht das Beat-Raster um bis zu eine
        Periode weg)."""
        n = max(self.PHASE_STEPS, int(np.ceil(P)))
        g = self._grids.get(n)
        if g is None:
            g = self._grids[n] = np.arange(n, dtype=np.float64) / n
        return g

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
        # Comb-Suche vektorisiert: (Phasen x n_beats) Indizes, ein Fancy-Index
        grid = self._phase_grid(P)
        n_ph = int(grid.size)
        phis = grid * P
        idx = (M - 1) - phis[:, None] - np.arange(n_beats, dtype=np.float64)[None, :] * P
        ii = np.floor(idx + 0.5).astype(np.intp)
        valid = ii >= 0
        ii[~valid] = 0
        scores = (env[ii] * valid).sum(axis=1)
        s = int(np.argmax(scores))
        # Parabel ueber die Nachbar-Phasen (zyklisch) gegen die Rasterung von P/32
        y0, y1, y2 = scores[(s - 1) % n_ph], scores[s], scores[(s + 1) % n_ph]
        den = y0 - 2 * y1 + y2
        sh = float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5)) if den != 0 else 0.0
        best_phi = (s + sh) * P / n_ph
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
        idx = (M2 - 1) - (self._phase_grid(P) * P)[:, None] - ks
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
        self.oct_pref = 0           # der Hinweis entscheidet die Oktave
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
        """Rastung x2 (step > 0) / x0,5 (step < 0) innerhalb der Grenzen; die Wahl bleibt
        gegen die Oktav-Hysterese bestehen (Roh-Schaetzungen werden mitgefaltet), bis
        reset()/set_tempo_hint() sie aufheben."""
        if self.bpm <= 0 or step == 0:
            return
        step = 1 if step > 0 else -1
        b = self.bpm * (2.0 if step > 0 else 0.5)
        if self.min_bpm <= b <= self.max_bpm:
            self.oct_pref += step
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

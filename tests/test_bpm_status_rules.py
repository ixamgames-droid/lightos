"""BPM-11 (S6): Statuszeile Problem — Ursache — Abhilfe als reine Regeln.

Jede Situation als Snapshot-Fixture -> erwartete Schwere/Aktion + Schluesselwort;
Text nie leer; Hysterese 2 s an / 3 s aus (Uhr gestellt); Chips inkl. der
gemessenen Brumm-Faelle (hum_ratio mit dem echten BeatDetector, 2026-09-14).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.audio.level_meter import CaptureSnapshot
from src.core.audio.tempo_tracker import DetectorSnapshot
from src.ui import bpm_status_rules as R
from src.ui.bpm_status_rules import (
    ChipHysterese, MgrState, Os2lState, StatusHysterese, StatusLine, chips, ereignis_oktave,
    status_line,
)

# Gemessen (bpm_bench/signals.py, BeatDetector, Werte ab t > 3 s):
HUM_KICK_128_MAX = 0.000            # (i)
HUM_KICK_BASS_HATS_128_MAX = 0.000  # (ii)
HUM_KICK_BRUMM_SNR0_MIN = 0.517     # (iii) Kick −30 dB + Brumm 50 Hz −30 dBFS
HUM_KICK_BRUMM_SNR0_MED = 0.594
HUM_REINER_BRUMM = 0.994            # (iv)
NETZ = dict(netz_linie=0.99, netz_hz=50)   # scharfe 50-Hz-Linie (level_meter.netz_linie, Brumm ≥ 0,92)


def det(**kw) -> DetectorSnapshot:
    base = dict(sample_pos=0, sample_rate=44100, state="locked", hold_stage=0, bpm=128.0,
                bpm_raw=128.0, confidence=0.9, alt_bpm=64.0, alt_score=0.1, tempo_hint=None,
                next_beat_sample=0, beat_latency_ms=0, window_s=6.0, window_filled_s=6.0,
                signal_s=20.0, level_rms_dbfs=-18.0, peak_dbfs=-6.0, clip_1s=0,
                noise_floor_dbfs=-60.0, hum_ratio=0.0, hum_hz=0, dc_offset=0.0, backlog_ms=5.0,
                jitter_ms=2.0, onset_contrast=8.0)
    base.update(kw)
    return DetectorSnapshot(**base)


def cap(**kw) -> CaptureSnapshot:
    base = dict(rms_dbfs_300ms=-18.0, rms_dbfs_1s=-18.0, peak_dbfs=-6.0, peak_hold_dbfs=-6.0,
                chunk_ms_p95=24.0, chunks=500, running=True)
    base.update(kw)
    return CaptureSnapshot(**base)


PC = MgrState(kind="loopback", device_label="Built-in Audio", bpm=128.0)
IN = MgrState(kind="input", device_label="USB Audio CODEC", bpm=128.0)
_EV, _EV_BIS = ereignis_oktave(+1, 256.0, 60.0, 200.0, now=100.0)

# (id, cap, det, mgr, os2l, now, schwere, aktion, schluesselwort)
FAELLE = [
    ("ereignis_oktave", cap(), det(), replace(PC, ereignis=_EV, ereignis_bis=_EV_BIS), None, 101.0,
     "hinweis", "range", "Tempo-Bereich"),
    ("aufnahme", cap(), det(), replace(IN, aufnahme_s=12.0), None, 0, "hinweis", None, "12 / 30 s"),
    ("audio_fehlt", None, None, replace(IN, audio_available=False), None, 0, "problem", "source", "soundcard"),
    ("monitor_als_eingang", cap(running=False), None,
     replace(IN, capture_error="no soundcard with id Monitor of Built-in"), None, 0, "problem", "source", "Monitor"),
    ("capture_fehler", cap(running=False), None, replace(IN, capture_error="Aufnahme abgebrochen: device lost"),
     None, 0, "problem", "reconnect", "device lost"),
    ("capture_haengt", cap(running=False), None, replace(IN, capture_error="Vorheriger Audio-Thread haengt noch"),
     None, 0, "problem", "source", "Neustart"),
    ("capture_gestoppt", cap(running=False), det(), IN, None, 0, "problem", "reconnect", "erneut verbinden"),
    ("kein_signal", cap(rms_dbfs_300ms=-70.0, rms_dbfs_1s=-70.0), det(state="no_signal", hold_stage=3),
     IN, None, 0, "problem", "source", "−70 dBFS"),
    ("sink_fehlt", cap(), det(), replace(PC, sink_missing="alsa_output.usb"), None, 0, "hinweis", "source",
     "Standardausgabe"),
    ("clip", cap(clip_chunks_1s=5, clip_samples_1s=140, peak_hold_dbfs=0.0), det(), IN, None, 0,
     "problem", None, "Übersteuert"),
    ("brumm", cap(**NETZ), det(state="searching", hum_ratio=0.71, hum_hz=50), IN, None, 0, "problem", "record", "71 %"),
    ("leise", cap(rms_dbfs_300ms=-44.0, rms_dbfs_1s=-44.0), det(), IN, None, 0, "hinweis", None, "−44 dBFS"),
    ("jitter", cap(chunk_ms_p95=95.0), det(), IN, None, 0, "hinweis", "record", "95 ms"),
    ("dc", cap(dc_offset=0.05), det(), IN, None, 0, "hinweis", "record", "+0.050"),
    ("os2l_aus", None, None, MgrState(kind="os2l"), Os2lState(running=False), 0, "problem", "reconnect",
     "läuft nicht"),
    ("os2l_wartet", None, None, MgrState(kind="os2l"), Os2lState(running=True, port=1234), 0, "hinweis", None,
     "VirtualDJ"),
    ("os2l_ok", None, None, MgrState(kind="os2l"), Os2lState(running=True, last_bpm=126.0), 0, "ok", None,
     "126 BPM"),
    ("song_ohne_titel", None, None, MgrState(kind="song", song_available=False), None, 0, "hinweis", None,
     "kein analysierter Titel"),
    ("song_ok", None, None, MgrState(kind="song", song_available=True, bpm=124.0), None, 0, "ok", None, "124"),
    ("aus", None, None, MgrState(kind="off"), None, 0, "hinweis", "source", "Quelle wählen"),
    ("eingefroren", cap(), det(), replace(IN, locked=True), None, 0, "hinweis", "range", "Eingefroren"),
    ("manuell", cap(), det(bpm=127.8), replace(IN, manual=True, bpm=128.0), None, 0, "ok", None, "127.8"),
    ("manuell_aus", cap(), det(), replace(IN, manual=True, bpm=0.0), None, 0, "ok", None, "Tempo aus"),
    ("halbtempo", cap(), det(bpm=70.2, alt_bpm=140.4, alt_score=0.8), IN, None, 0, "hinweis", None, "×2"),
    ("pause", cap(rms_dbfs_300ms=-120.0, rms_dbfs_1s=-120.0), det(hold_stage=1), PC, None, 0, "ok", None,
     "gehalten"),
    ("kein_takt", cap(), det(state="searching", signal_s=18.0), IN, None, 0, "hinweis", "record",
     "kein stabiles Tempo"),
    ("sucht", cap(), det(state="searching", signal_s=3.0, window_filled_s=3.0), IN, None, 0, "hinweis", None,
     "Sucht"),
    ("kein_detektor", cap(), None, IN, None, 0, "hinweis", None, "Detektor"),
    ("ok", cap(), det(), PC, None, 0, "ok", None, "Eingerastet — 128 BPM aus PC-Audio"),
]


@pytest.mark.parametrize("key,c,d,m,o,now,schwere,aktion,wort", FAELLE, ids=[f[0] for f in FAELLE])
def test_situation(key, c, d, m, o, now, schwere, aktion, wort):
    line = status_line(c, d, m, o, now)
    assert line.key == key
    assert line.schwere == schwere
    assert line.aktion == aktion
    assert wort in line.text
    assert line.schwere in R.SCHWEREN and line.aktion in R.AKTIONEN


@pytest.mark.parametrize("fall", FAELLE, ids=[f[0] for f in FAELLE])
def test_text_nie_leer(fall):
    _k, c, d, m, o, now, *_ = fall
    line = status_line(c, d, m, o, now)
    assert line.problem.strip() and line.ursache.strip() and line.text.strip()


def test_mindestens_17_situationen_und_fallback_nie_leer():
    assert len({f[0] for f in FAELLE}) >= 17
    for m in (None, MgrState(kind="weird"), MgrState(kind="input")):
        for c in (None, cap()):
            for d in (None, det(), det(state="no_signal")):
                assert status_line(c, d, m, None, 0).text.strip()


def test_messwert_in_ursache():
    line = status_line(cap(rms_dbfs_300ms=-70.0), det(state="no_signal"), IN, None, 0)
    assert line.text == ("Kein Signal — Eingang »USB Audio CODEC« liefert −70 dBFS — "
                         "Kabel/Gerät prüfen oder anderen Eingang wählen")


def test_ereignis_laeuft_nach_3_s_ab():
    m = replace(PC, ereignis=_EV, ereignis_bis=_EV_BIS)
    assert status_line(cap(), det(), m, None, 102.9).key == "ereignis_oktave"
    assert status_line(cap(), det(), m, None, 103.1).key == "ok"


def test_ereignis_verdraengt_gehaltene_stoerung_sofort():
    h = StatusHysterese()
    h.update(_brumm(), 0.0)
    m = replace(PC, ereignis=_EV, ereignis_bis=_EV_BIS)
    assert h.update(status_line(cap(**NETZ), det(state="searching", hum_ratio=0.8), m, None, 101.0),
                    101.0).key == "ereignis_oktave"


def test_ereignis_aufnahme_nur_relativer_pfad():
    line, bis = R.ereignis_aufnahme("audio_diag/lightos_eingang_20260914-120000.wav", 30.0, False, 5.0)
    assert line.text == ("Aufnahme gespeichert — audio_diag/lightos_eingang_20260914-120000.wav — "
                         "Datei an Robin/Support schicken")
    assert bis == 5.0 + R.EREIGNIS_AUFNAHME_S
    ab, _ = R.ereignis_aufnahme("audio_diag/x.wav", 12.0, True, 0.0)
    assert "abgebrochen" in ab.problem and "12 s" in ab.ursache


def test_kein_signal_nennt_fehlenden_sink():
    m = replace(PC, sink_missing="alsa_output.usb")
    line = status_line(cap(rms_dbfs_300ms=-120.0), det(state="no_signal", hold_stage=3), m, None, 0)
    assert line.key == "kein_signal" and "Standardausgabe" in line.ursache


def test_reihenfolge_problem_vor_hinweis():
    # Clip + Brumm + Leise-Chip gleichzeitig -> Clip (vor Brumm) gewinnt
    line = status_line(cap(clip_chunks_1s=5), det(state="searching", hum_ratio=0.9), IN, None, 0)
    assert line.key == "clip"
    assert status_line(cap(chunk_ms_p95=99.0, **NETZ), det(state="searching", hum_ratio=0.9), IN, None, 0).key == "brumm"


def test_halbtempo_ausserhalb_bereich_aktion_range():
    m = replace(IN, max_bpm=130.0)
    line = status_line(cap(), det(bpm=70.2, alt_bpm=140.4, alt_score=0.8), m, None, 0)
    assert line.key == "halbtempo" and line.aktion == "range"


# ── Hysterese ────────────────────────────────────────────────────────────────

def _ok():
    return status_line(cap(), det(), PC, None, 0)


def _brumm():
    return status_line(cap(**NETZ), det(state="searching", hum_ratio=0.8, hum_hz=50), PC, None, 0)


def test_hysterese_2s_an_3s_aus():
    h = StatusHysterese(clock=lambda: 0.0)
    assert h.update(_ok(), 0.0).key == "ok"
    t = 10.0
    assert h.update(_brumm(), t).key == "ok"
    assert h.update(_brumm(), t + 1.9).key == "ok"
    assert h.update(_brumm(), t + 2.0).key == "brumm"
    assert h.update(_brumm(), t + 5.0).key == "brumm"
    t2 = t + 5.0
    assert h.update(_ok(), t2 + 0.05).key == "brumm"
    assert h.update(_ok(), t2 + 2.95).key == "brumm"
    assert h.update(_ok(), t2 + 3.0).key == "ok"


def test_hysterese_kurzes_flackern_zeigt_nichts():
    h = StatusHysterese()
    h.update(_ok(), 0.0)
    for i in range(20):                       # 1,5 s an, 0,5 s aus im Wechsel
        t = i * 2.0
        assert h.update(_brumm(), t).key == "ok"
        assert h.update(_brumm(), t + 1.5).key == "ok"
        assert h.update(_ok(), t + 1.6).key == "ok"


def test_hysterese_zustandszeilen_sofort_und_messwert_aktualisiert():
    h = StatusHysterese()
    h.update(status_line(cap(), det(state="searching", signal_s=3.0), PC, None, 0), 0.0)
    assert h.update(_ok(), 0.05).key == "ok"               # Sucht -> Eingerastet sofort
    err = status_line(cap(running=False), None, replace(PC, capture_error="Aufnahme abgebrochen: x"), None, 0)
    assert h.update(err, 0.1).key == "capture_fehler"        # Fehler sofort
    h2 = StatusHysterese()
    h2.update(_brumm(), 0.0)
    b2 = status_line(cap(**NETZ), det(state="searching", hum_ratio=0.55, hum_hz=50), PC, None, 0)
    assert "55 %" in h2.update(b2, 0.05).ursache


# ── Chips ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ratio,erwartet", [
    (HUM_KICK_128_MAX, False), (HUM_KICK_BASS_HATS_128_MAX, False),
    (HUM_KICK_BRUMM_SNR0_MIN, True), (HUM_KICK_BRUMM_SNR0_MED, True), (HUM_REINER_BRUMM, True),
], ids=["i_kick", "ii_kick_bass_hats", "iii_snr0_min", "iii_snr0_median", "iv_reiner_brumm"])
def test_brumm_chip_gemessene_faelle(ratio, erwartet):
    assert ("BRUMM" in chips(cap(**NETZ), det(state="searching", hum_ratio=ratio))) is erwartet
    assert R.BRUMM_RATIO > HUM_KICK_BASS_HATS_128_MAX and R.BRUMM_RATIO < HUM_KICK_BRUMM_SNR0_MIN


def test_chips_bedingungen():
    assert chips(None, None) == set()
    assert chips(cap(), det()) == set()
    assert chips(cap(clip_chunks_1s=3), None) == {"CLIP"}
    assert chips(cap(rms_dbfs_1s=-50.0), None) == {"LEISE"}
    assert chips(cap(rms_dbfs_1s=-80.0), None) == set()          # kein Signal ist nicht „leise"
    assert chips(cap(chunk_ms_p95=80.0), None) == {"JITTER"}
    assert chips(cap(), det(backlog_ms=300.0)) == {"JITTER"}
    assert chips(cap(dc_offset=-0.03), None) == {"DC"}
    assert chips(cap(clip_chunks_1s=4, dc_offset=0.1, **NETZ), det(state="searching", hum_ratio=0.6)) == {"CLIP", "DC", "BRUMM"}


def test_chip_hysterese_2s_an_3s_aus():
    h = ChipHysterese()
    assert h.update({"CLIP"}, 0.0) == set()
    assert h.update({"CLIP"}, 1.9) == set()
    assert h.update({"CLIP", "LEISE"}, 2.0) == {"CLIP"}      # CLIP 2 s an; LEISE neu
    assert h.update({"CLIP", "LEISE"}, 4.0) == {"CLIP", "LEISE"}
    assert h.update(set(), 6.9) == {"CLIP", "LEISE"}         # zuletzt 4,0 -> noch 2,9 s
    assert h.update(set(), 7.0) == set()                     # 3,0 s ohne -> weg
    assert h.update({"DC"}, 8.0) == set()
    assert h.update(set(), 8.5) == set()                      # zu kurz, nie sichtbar
    assert h.update({"DC"}, 9.0) == set()
    assert h.update({"DC"}, 10.9) == set()
    assert h.update({"DC"}, 11.0) == {"DC"}


def test_regeln_modul_ist_qt_frei():
    import src.ui.bpm_status_rules as mod
    text = open(mod.__file__, encoding="utf-8").read()
    assert "PySide6" not in text


# ── BRUMM: Grenzwerte und Bedingungen (Nachbesserung S6) ─────────────────────

@pytest.mark.parametrize("ratio,erwartet", [(0.39, False), (0.40, True)], ids=["0,39", "0,40"])
def test_brumm_grenze_hum_ratio_zeile_und_chip(ratio, erwartet):
    d = det(state="searching", signal_s=3.0, hum_ratio=ratio, hum_hz=50)
    assert (status_line(cap(**NETZ), d, IN, None, 0).key == "brumm") is erwartet
    assert ("BRUMM" in chips(cap(**NETZ), d)) is erwartet


@pytest.mark.parametrize("linie,erwartet", [(0.49, False), (0.50, True)], ids=["0,49", "0,50"])
def test_brumm_grenze_netz_linie_zeile_und_chip(linie, erwartet):
    d = det(state="searching", signal_s=3.0, hum_ratio=0.9, hum_hz=60)
    c = cap(netz_linie=linie, netz_hz=60)
    assert (status_line(c, d, IN, None, 0).key == "brumm") is erwartet
    assert ("BRUMM" in chips(c, d)) is erwartet


def test_brumm_nicht_wenn_eingerastet_oder_ohne_netzlinie():
    # F2: eingerastet -> Brumm stoert die Erkennung nicht, keine Meldung
    locked = det(state="locked", hum_ratio=0.99, hum_hz=60)
    assert status_line(cap(**NETZ), locked, IN, None, 0).key == "ok"
    assert "BRUMM" not in chips(cap(**NETZ), locked)
    # Breakdown: gehaltener Bass 58,3 Hz, Detektor sucht, hum_ratio hoch, aber keine Netzlinie
    bass = det(state="searching", signal_s=3.0, hum_ratio=0.997, hum_hz=60)
    assert status_line(cap(netz_linie=0.03, netz_hz=60), bass, IN, None, 0).key == "sucht"
    assert "BRUMM" not in chips(cap(netz_linie=0.03, netz_hz=60), bass)
    assert "BRUMM" not in chips(None, bass)


def test_brumm_text_nimmt_netzfrequenz_aus_der_linie():
    d = det(state="searching", hum_ratio=0.8, hum_hz=50)
    assert status_line(cap(netz_linie=0.95, netz_hz=60), d, IN, None, 0).problem == "Netzbrumm 60 Hz"


# ── Bank-Regression: echter BeatDetector + LevelMeter + Regeln + Hysterese ───

def _sig_kick(bpm: float, dauer: float, sr: int, f0: float = 60.0):
    import numpy as np
    n = int(0.30 * sr)
    t = np.arange(n) / sr
    ph = 2 * np.pi * np.cumsum(f0 + 30.0 * np.exp(-t / 0.03)) / sr
    k = 0.8 * np.sin(ph) * np.exp(-t / 0.09)
    k[:int(0.004 * sr)] += 0.4 * np.random.default_rng(2).standard_normal(int(0.004 * sr))
    buf = np.zeros(int(dauer * sr))
    b = 0.0
    while b < dauer:
        i = int(round(b * sr))
        m = min(n, buf.shape[0] - i)
        buf[i:i + m] += k[:m]
        b += 60.0 / bpm
    return buf


def _sig_bass(f: float, dauer: float, sr: int, amp: float = 0.35):
    import numpy as np
    t = np.arange(int(dauer * sr)) / sr
    return amp * (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)
                  + 0.2 * np.sin(6 * np.pi * f * t)) / 1.6


def _sig_brumm(dauer: float, sr: int, dbfs: float, f0: float = 50.0):
    import numpy as np
    t = np.arange(int(dauer * sr)) / sr
    a = 10.0 ** (dbfs / 20.0)
    return (a * np.sin(2 * np.pi * f0 * t) + 0.5 * a * np.sin(4 * np.pi * f0 * t + 0.7)
            + 0.25 * a * np.sin(6 * np.pi * f0 * t + 1.9))


def _pipeline(sig):
    """Wie die View: je Chunk Detektor + LevelMeter, dann Regeln + Hysterese (Audio-Uhr)."""
    import numpy as np
    from src.core.audio.beat_detector import BeatDetector
    from src.core.audio.level_meter import LevelMeter
    sr, ch = 44100, 1024
    clk = [0.0]
    d = BeatDetector(sr)
    lm = LevelMeter(sr, clock=lambda: clk[0])
    h, chh = StatusHysterese(clock=lambda: clk[0]), ChipHysterese()
    x = np.asarray(sig, dtype=np.float32)
    zeilen, sichtbar, hum = set(), set(), []
    for i in range(0, x.shape[0] - ch + 1, ch):
        blk = x[i:i + ch]
        d.process_chunk(blk)
        lm.on_chunk(blk)
        clk[0] += ch / sr
        cs, ds = replace(lm.snapshot(), running=True), d.snapshot()
        zeilen.add(h.update(status_line(cs, ds, IN, None, clk[0]), clk[0]).key)
        sichtbar |= chh.update(chips(cs, ds), clk[0])
        if clk[0] > 3.0:
            hum.append(ds.hum_ratio)
    return zeilen, sichtbar, hum


def test_bank_breakdown_bass_ohne_kick_ist_kein_brumm():
    import numpy as np
    sr = 44100
    for f in (49.0, 58.3, 61.7):
        sig = 0.8 * np.concatenate([_sig_kick(128, 8.0, sr), _sig_bass(f, 16.0, sr)])
        zeilen, sichtbar, hum = _pipeline(sig)
        assert max(hum) >= R.BRUMM_RATIO           # der Detektor allein wuerde Brumm melden
        assert "brumm" not in zeilen and "BRUMM" not in sichtbar, f


def test_bank_kick_allein_und_brumm_snr0():
    import numpy as np
    sr = 44100
    zeilen, sichtbar, hum = _pipeline(_sig_kick(128, 8.0, sr))
    assert max(hum) < R.BRUMM_RATIO and "brumm" not in zeilen and "BRUMM" not in sichtbar
    # Kick −30 dB + Brumm 50 Hz −30 dBFS (Bassband-SNR 0 dB): hum_ratio ueber der Schwelle;
    # der Detektor rastet trotzdem ein -> F2: keine Meldung
    kick = _sig_kick(128, 10.0, sr) * 10.0 ** (-30 / 20)
    zeilen, sichtbar, hum = _pipeline(kick + _sig_brumm(10.0, sr, -30.0))
    assert min(hum) >= R.BRUMM_RATIO
    # reiner Brumm (keine Musik, Detektor sucht): Zeile und Chip
    zeilen, sichtbar, hum = _pipeline(_sig_brumm(9.0, sr, -30.0))
    assert "brumm" in zeilen and "BRUMM" in sichtbar

"""BPM-09 (S4): TapHelper — TAP mit Doppelrolle.

1 Tipp = ``det.resync_phase()`` (Phase auf „jetzt", Tempo bleibt); jeder Tipp
ruft ``mgr.tap()``; ab dem 3. Tipp innerhalb 2 s zusaetzlich
``det.set_tempo_hint(<gemessenes Tempo>)``; nach 2 s Pause beginnt eine neue
Folge. Uhr wird gestellt (kein Schlafen). Der Topbar-TAP und der Tab-TAP
teilen sich denselben Helfer (``get_tap_helper``).
"""
from __future__ import annotations

from src.ui.bpm_tap_helper import TapHelper, get_tap_helper, TAP_WINDOW_S


class _Det:
    def __init__(self):
        self.resyncs = 0
        self.hints: list = []

    def resync_phase(self):
        self.resyncs += 1

    def set_tempo_hint(self, bpm):
        self.hints.append(bpm)


class _Mgr:
    def __init__(self):
        self.taps = 0

    def tap(self):
        self.taps += 1
        return 120.0 if self.taps >= 2 else 0.0


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _make():
    det, mgr, clk = _Det(), _Mgr(), _Clock()
    return TapHelper(mgr=mgr, det=det, clock=clk), det, mgr, clk


def test_ein_tipp_setzt_nur_die_phase():
    h, det, mgr, _ = _make()
    h.tap()
    assert det.resyncs == 1
    assert mgr.taps == 1                      # der Manager zaehlt jeden Tipp
    assert det.hints == []                    # noch kein Tempo-Hinweis
    assert h.count == 1 and h.measured_bpm() == 0.0


def test_vier_tipps_bei_120_bpm_geben_tap_x4_und_hint_120():
    h, det, mgr, clk = _make()
    for _ in range(4):
        h.tap()
        clk.t += 0.5                          # 120 BPM
    assert mgr.taps == 4
    assert det.resyncs == 1                   # nur der erste Tipp resynct
    assert len(det.hints) == 2                # ab dem 3. Tipp: 3. und 4.
    assert all(abs(x - 120.0) <= 1.0 for x in det.hints)
    assert abs(h.measured_bpm() - 120.0) <= 1.0


def test_pause_ueber_zwei_sekunden_beginnt_neue_folge():
    h, det, mgr, clk = _make()
    for _ in range(3):
        h.tap()
        clk.t += 0.5
    assert det.resyncs == 1 and len(det.hints) == 1
    clk.t += TAP_WINDOW_S + 0.1               # Pause -> Ruecksetzen
    h.tap()
    assert h.count == 1
    assert det.resyncs == 2                   # neue Folge: wieder Phase
    assert len(det.hints) == 1                # kein neuer Hinweis beim 1. Tipp


def test_ohne_detektor_wirkt_nur_der_manager():
    mgr, clk = _Mgr(), _Clock()
    h = TapHelper(mgr=mgr, det=None, clock=clk)
    h._det = None
    h._detector = lambda: None                # numpy fehlt o. ae.
    for _ in range(3):
        h.tap()
        clk.t += 0.5
    assert mgr.taps == 3


def test_get_tap_helper_ist_singleton():
    assert get_tap_helper() is get_tap_helper()

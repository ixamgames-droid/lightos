"""BPM-10 (S5): Pegelmeter-Widget — nur mit Fake-Snapshots, kein echtes Capture."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from src.core.audio.level_meter import CaptureSnapshot, LevelMeter
from src.ui.widgets import level_meter_widget as lmw
from src.ui.widgets.level_meter_widget import LevelMeterWidget

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class _Clock:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


def _snap_aus_sinus(amp: float, chunks: int = 40) -> CaptureSnapshot:
    m = LevelMeter(44100)
    for i in range(chunks):
        t = (np.arange(1024) + i * 1024) / 44100
        m.on_chunk((amp * np.sin(2 * np.pi * 441 * t)).astype(np.float32))
    return dataclasses.replace(m.snapshot(), running=True)


def _render(w):
    w.resize(260, 16)
    return w.grab().toImage()


def _pixel_bei(w, img, dbfs):
    r_w = w.width() - 34.0 - 5.0
    x = int(w._x(dbfs, 0.5, r_w))
    return img.pixelColor(x, w.height() // 2)


def test_minus_6_db_sinus_liegt_in_der_zielzone():
    snap = _snap_aus_sinus(10 ** (-6 / 20))
    assert -30 <= snap.rms_dbfs_300ms <= -6
    w = LevelMeterWidget()
    w.set_snapshot(snap)
    assert w.zone() == "ziel" and w.bar_color() == lmw.COL_GRUEN
    img = _render(w)
    assert _pixel_bei(w, img, -20.0) == lmw.COL_GRUEN          # Balken gruen gemalt
    assert not w.clip_visible()


def test_minus_50_dbfs_ist_grau():
    w = LevelMeterWidget()
    w.set_snapshot(CaptureSnapshot(rms_dbfs_300ms=-50.0, peak_hold_dbfs=-44.0, chunks=10, running=True))
    assert w.zone() == "grau" and w.bar_color() == lmw.COL_GRAU
    img = _render(w)
    assert _pixel_bei(w, img, -55.0) == lmw.COL_GRAU


@pytest.mark.parametrize("dbfs,erwartet", [(-40.0, "leise"), (-4.0, "heiss"), (-2.0, "rot")])
def test_zonen_grenzen(dbfs, erwartet):
    assert lmw.zone(dbfs) == erwartet


def test_clip_nach_vollaussteuerung_sichtbar_und_bleibt_1_s():
    clk = _Clock()
    w = LevelMeterWidget(clock=clk)
    m = LevelMeter(44100)
    voll = np.ones(1024, np.float32)
    zeiten = []
    for i in range(10):                          # 10 Chunks Vollaussteuerung = 232 ms
        m.on_chunk(voll)
        clk.t += 1024 / 44100
        w.set_snapshot(dataclasses.replace(m.snapshot(), running=True))
        if w.clip_visible():
            zeiten.append(i)
    assert zeiten and (zeiten[0] + 1) * 1024 / 44100 < 1.0     # CLIP innerhalb 1 s
    assert w.zone() == "rot"
    img = _render(w)
    assert img.pixelColor(w.width() - 2, 2) == lmw.COL_ROT      # CLIP-Feld (Rand, nicht Schrift)
    clk.t += 0.9
    w.set_snapshot(CaptureSnapshot(rms_dbfs_300ms=-20.0, chunks=99, running=True))
    assert w.clip_visible()                      # bleibt stehen
    clk.t += 0.2
    assert not w.clip_visible()


def test_gestoppt_oder_leer_zeigt_nichts():
    w = LevelMeterWidget()
    assert not w.active() and w.zone() == "grau"
    _render(w)
    w.set_snapshot(CaptureSnapshot(rms_dbfs_300ms=-10.0, clip_chunks_1s=5, chunks=3, running=False))
    assert not w.active() and not w.clip_visible()
    w.set_snapshot(None)
    _render(w)


def test_widget_ist_kein_bedienelement_und_greift_nicht_auf_capture_zu():
    import inspect
    from PySide6.QtCore import Qt
    w = LevelMeterWidget()
    assert w.focusPolicy() == Qt.FocusPolicy.NoFocus and w.toolTip()
    src = inspect.getsource(lmw)
    assert "get_audio_capture" not in src and "import capture" not in src

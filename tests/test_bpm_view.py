"""Smoke-/Funktionstest fuer den BPM-Manager-Tab (WP-5/6).

Headless (offscreen Qt). Die Prefs werden auf eine Temp-Datei umgelenkt, damit
der echte ``ui_prefs.json`` der App nicht angefasst wird.
"""
from __future__ import annotations
import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


def test_bpm_view_constructs_and_drives_backend(qapp, _isolated_prefs):
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode

    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    mgr = get_bpm_manager()

    # Grenzen-Spinboxen -> Manager (und gespiegelt in den Detektor)
    v._sp_min.setValue(110)
    v._sp_max.setValue(170)
    assert mgr.min_bpm == 110 and mgr.max_bpm == 170

    # Modus-Umschalter
    v._rb_manual.setChecked(True)
    assert mgr.mode == BpmMode.MANUAL
    v._rb_auto.setChecked(True)
    assert mgr.mode == BpmMode.AUTO

    # Lock-Toggle
    v._btn_lock.setChecked(True)
    assert mgr.is_locked is True
    v._btn_lock.setChecked(False)
    assert mgr.is_locked is False

    # Sensitivity/Smoothing -> Detektor
    v._sl_sens.setValue(200)
    v._sl_smooth.setValue(50)
    from src.core.audio.beat_detector import get_beat_detector
    det = get_beat_detector()
    assert det.sensitivity == 2.0 and det.smoothing == 0.5

    # Eingehender Beat aktualisiert die Takt-Anzeige ohne Crash
    v._beat_sig.emit(0)
    qapp.processEvents()
    v._beat_sig.emit(1)
    qapp.processEvents()

    # Persistenz: Einstellungen wurden gespeichert
    saved = _isolated_prefs.load_settings()
    assert saved["min_bpm"] == 110 and saved["max_bpm"] == 170

    v.hide()
    v.deleteLater()
    qapp.processEvents()
    # Nach Zerstoerung keine Geister-Callbacks mehr (Unsubscribe lief)
    mgr.set_mode(BpmMode.AUTO)


def test_bpm_source_kind_selector(qapp, _isolated_prefs):
    """Der user-friendly Quellen-Umschalter Live/Lied-Analyse/Manuell."""
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    from src.core.audio.media_player import get_media_player, Track

    mgr = get_bpm_manager()
    mgr.reset()
    mgr._audio_active = False
    mgr.set_locked(False)
    mgr.set_mode(BpmMode.AUTO)

    tl = {"v": 2, "duration_ms": 20000, "engine": "builtin", "beats_per_bar": 4,
          "segments": [[0, 128.0, 0.9]], "beats_ms": [0, 469, 938]}
    mp = get_media_player()
    mp.set_tracks([Track(path="song.mp3", title="Test Song", bpm_timeline=tl)])

    v = BpmManagerView()
    v.show()
    qapp.processEvents()

    # analysierter Song in der Auswahl
    assert v._cmb_song.itemData(0) == 0

    # Manuell → MANUAL
    v._rb_kind_manual.setChecked(True)
    qapp.processEvents()
    assert mgr.mode == BpmMode.MANUAL

    # Lied-Analyse → AUTO + Quelle "timeline" + statische BPM aus der Analyse
    v._rb_kind_song.setChecked(True)
    qapp.processEvents()
    assert mgr.mode == BpmMode.AUTO
    assert mgr.current_source == "timeline"
    assert abs(mgr.bpm - 128.0) < 1.0
    assert v._cmb_song.isEnabled()

    v.hide()
    v.deleteLater()
    qapp.processEvents()
    mp.set_tracks([])
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)

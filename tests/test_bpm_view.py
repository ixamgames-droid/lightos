"""Smoke-/Funktionstest fuer den BPM-Manager-Tab (WP-5/6).

Headless (offscreen Qt). Die Prefs werden auf eine Temp-Datei umgelenkt, damit
der echte ``ui_prefs.json`` der App nicht angefasst wird.
"""
from __future__ import annotations
import pytest

from PySide6.QtWidgets import QApplication


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen. `deleteLater()` allein stellt `DeferredDelete` nie zu — die Objekte
# ueberleben mitsamt Kindern, Signalen und (bei Views) Renderern. Segmentiert
# faellt das nicht auf, weil jede Datei allein laeuft; in einem Prozess mit
# genug angesammeltem Zustand ist es dieselbe Klasse Zeitzuender, die vor
# XPLAT-09 neun scheinbar gruene viz-Dateien zum Segfault brachte.
# Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py.
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    # QApplication lokal importieren: manche Dateien holen es nur INNERHALB
    # ihrer Tests, dann gibt es den Modulnamen hier nicht (3 Dateien liefen
    # genau darauf in einen NameError).
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture(autouse=True)
def _kein_echtes_capture(monkeypatch):
    """S2-Lehre: ein Quellenwechsel startet sonst den echten Capture (Exit 134)."""
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "start", lambda self: False)
    yield
    from src.core.engine.bpm_manager import get_bpm_manager
    get_bpm_manager().use_audio_source(False)


def test_bpm_view_constructs_and_drives_backend(qapp, _isolated_prefs):
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode

    v = BpmManagerView()
    v.show()
    qapp.processEvents()
    mgr = get_bpm_manager()

    # Grenzen-Spinboxen (Erweitert) -> Manager (und gespiegelt in den Detektor)
    v._sp_min.setValue(110)
    v._sp_max.setValue(170)
    assert mgr.min_bpm == 110 and mgr.max_bpm == 170

    # Modus-Umschalter Auto | Manuell (S4: QToolButtons statt Radios)
    v._btn_manual.setChecked(True)
    assert mgr.mode == BpmMode.MANUAL
    v._btn_auto.setChecked(True)
    assert mgr.mode == BpmMode.AUTO

    # Lock-Toggle („Tempo einfrieren" in Erweitert)
    v._btn_lock.setChecked(True)
    assert mgr.is_locked is True
    v._btn_lock.setChecked(False)
    assert mgr.is_locked is False

    # Beat-Latenz -> Detektor (S4, ersetzt Sensitivity/Smoothing)
    from src.core.audio.beat_detector import get_beat_detector
    det = get_beat_detector()
    v._sp_latency.setValue(-40)
    assert det.beat_latency_ms == -40
    v._sp_latency.setValue(0)

    # Eingehender Beat aktualisiert die Takt-Anzeige ohne Crash
    v._beat_sig.emit(0)
    qapp.processEvents()
    v._beat_sig.emit(1)
    qapp.processEvents()

    # Persistenz: entprellt (400 ms) — flush schreibt Ausstehendes sofort
    v.flush_pending_save()
    saved = _isolated_prefs.load_settings()
    assert saved["min_bpm"] == 110 and saved["max_bpm"] == 170
    assert saved["version"] == 3 and "sensitivity" not in saved

    v.hide()
    v.deleteLater()
    qapp.processEvents()
    # Nach Zerstoerung keine Geister-Callbacks mehr (Unsubscribe lief)
    mgr.set_mode(BpmMode.AUTO)


def test_bpm_source_kind_selector(qapp, _isolated_prefs):
    """Quelle-Combo „Lied-Analyse (Player)" + Auto | Manuell (S4): nimmt den
    aktuellen Player-Track, keine eigene Song-Auswahl mehr."""
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.ui.bpm_source_controller import SourceController
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

    v = BpmManagerView(source_controller=SourceController())
    v.show()
    qapp.processEvents()

    # Manuell → MANUAL
    v._btn_manual.setChecked(True)
    qapp.processEvents()
    assert mgr.mode == BpmMode.MANUAL

    # Auto + Quelle „Lied-Analyse" → AUTO + Quelle "timeline" + statische BPM aus der Analyse
    v._btn_auto.setChecked(True)
    v._cmb_source.setCurrentIndex(v._cmb_source.findData("song"))
    qapp.processEvents()
    assert mgr.mode == BpmMode.AUTO
    assert mgr.current_source == "timeline"
    assert abs(mgr.bpm - 128.0) < 1.0
    v.flush_pending_save()
    assert _isolated_prefs.load_settings()["source"] == "song"

    v.hide()
    v.deleteLater()
    qapp.processEvents()
    mp.set_tracks([])
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)

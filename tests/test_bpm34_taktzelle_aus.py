"""BPM-34: Nach Quelle „Aus" (``BPMManager.reset()``, seit BPM-33 Takt 0) darf keine
Taktzelle der BPM-Anzeige mehr auf dem letzten Schlag erleuchtet bleiben.

Vorher spiegelte ``BpmManagerView._on_bpm`` nur die BPM-Zahl; die Zellen wurden
ausschliesslich in ``_on_beat`` umgefaerbt und blieben nach dem Reset gruen.
Der Fix laeuft ueber den Signalpfad ``reset() -> _emit_bpm_change -> _on_bpm`` —
kein Polling.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets


@pytest.fixture(autouse=True)
def _kein_widget_leck():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


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
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "start", lambda self: False)
    yield
    from src.core.engine.bpm_manager import get_bpm_manager
    get_bpm_manager().use_audio_source(False)


def _aktive_zellen(v) -> list[int]:
    return [i for i, pl in enumerate(v._phase_lbls)
            if pl.styleSheet() == v._phase_style(True, i == 0)]


def _takt_ohne_timer(monkeypatch, mgr, bpm: float = 120.0):
    """Laufender Takt (> 0), ohne den echten Beat-Faden zu starten — die Beats
    speist der Test selbst ein."""
    monkeypatch.setattr(mgr, "_bpm", bpm)


def test_reset_loescht_erleuchtete_taktzelle(qapp, _isolated_prefs, monkeypatch):
    from src.ui.views.bpm_manager_view import BpmManagerView, _DOT_IDLE
    from src.core.engine.bpm_manager import get_bpm_manager

    mgr = get_bpm_manager()
    mgr.reset()                        # kein laufender Beat-Timer im Test
    v = BpmManagerView()
    try:
        v.show()
        qapp.processEvents()
        _takt_ohne_timer(monkeypatch, mgr)
        assert len(v._phase_lbls) >= 3

        v._beat_sig.emit(2)            # dritter Schlag: Zelle 3 gruen
        qapp.processEvents()
        assert _aktive_zellen(v) == [2]

        mgr.reset()                    # Quelle „Aus" (BPM-33) -> Takt 0
        qapp.processEvents()

        assert mgr.bpm == 0.0
        assert _aktive_zellen(v) == [], "Taktzelle leuchtet nach Takt 0 weiter"
        assert v._dot.styleSheet() == _DOT_IDLE
        assert v._phase_pos.text() == ""
    finally:
        v.hide()
        v.deleteLater()
        qapp.processEvents()
        mgr.reset()


def test_takt_groesser_null_laesst_zelle_stehen(qapp, _isolated_prefs, monkeypatch):
    """Gegenprobe: ein BPM-Wechsel > 0 loescht die Zelle NICHT (nur Takt 0)."""
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.core.engine.bpm_manager import get_bpm_manager

    mgr = get_bpm_manager()
    mgr.reset()                        # kein laufender Beat-Timer im Test
    v = BpmManagerView()
    try:
        v.show()
        qapp.processEvents()
        _takt_ohne_timer(monkeypatch, mgr)
        v._beat_sig.emit(1)
        qapp.processEvents()
        v._bpm_sig.emit(128.0)
        qapp.processEvents()
        assert _aktive_zellen(v) == [1]
    finally:
        v.hide()
        v.deleteLater()
        qapp.processEvents()
        mgr.reset()


def test_verspaeteter_beat_nach_reset_erleuchtet_keine_zelle(qapp, _isolated_prefs, monkeypatch):
    """Adversarial: ein Beat, den der Timer-/Audio-Faden KURZ VOR ``reset()``
    gesendet hat, steckt als Queued-Signal noch in der Ereignisschlange und kommt
    erst NACH dem Loeschen an. Er darf die Zelle nicht wieder erleuchten."""
    import threading
    from src.ui.views.bpm_manager_view import BpmManagerView, _DOT_IDLE
    from src.core.engine.bpm_manager import get_bpm_manager

    mgr = get_bpm_manager()
    mgr.reset()
    v = BpmManagerView()
    try:
        v.show()
        qapp.processEvents()
        _takt_ohne_timer(monkeypatch, mgr)
        t = threading.Thread(target=lambda: v._cb_beat(2))   # Beat aus fremdem Faden
        t.start()
        t.join()                       # Signal liegt jetzt queued in der Schlange
        mgr.reset()                    # Quelle „Aus" -> Takt 0, loescht direkt
        qapp.processEvents()           # erst jetzt kommt der alte Beat an

        assert _aktive_zellen(v) == [], "verspaeteter Beat erleuchtet die Zelle wieder"
        assert v._dot.styleSheet() == _DOT_IDLE
    finally:
        v.hide()
        v.deleteLater()
        qapp.processEvents()
        mgr.reset()


def test_audio_beat_ohne_takt_leuchtet_weiter(qapp, _isolated_prefs, monkeypatch):
    """Gegenprobe: im AUTO-Audio-Betrieb kommen Beats auch, bevor ein Takt erkannt
    ist (BPM 0). Diese Beats muessen die Zelle weiter erleuchten."""
    from src.ui.views.bpm_manager_view import BpmManagerView
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode

    mgr = get_bpm_manager()
    mgr.reset()
    v = BpmManagerView()
    try:
        v.show()
        qapp.processEvents()
        monkeypatch.setattr(mgr, "_audio_active", True)   # Detektor taktet, kein Capture
        monkeypatch.setattr(mgr, "_mode", BpmMode.AUTO)
        assert mgr.bpm == 0.0
        v._beat_sig.emit(1)
        qapp.processEvents()
        assert _aktive_zellen(v) == [1]
    finally:
        v.hide()
        v.deleteLater()
        qapp.processEvents()
        monkeypatch.undo()
        mgr.reset()

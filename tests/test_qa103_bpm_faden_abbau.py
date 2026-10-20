"""QA-103: der 'BPM-Beat'-Faden ist nach reset()/shutdown() wirklich zu Ende.

Befund: ``tests/test_bpm_view.py`` starb in der Linux-CI dreimal mit SIGSEGV.
Der faulthandler-Stack zeigte den Faden 'BPM-Beat' beim Garbage-Collecting in
``_emit_beat`` (erster ``function_manager``-Import im Prozess), WAEHREND der Mainthread im
Teardown Widgets abbaute -- obwohl der Test vorher ``mgr.reset()`` gerufen hatte.
``reset()`` meldete den Faden nur ab (``_running = False``), wartete aber nicht
auf ihn; ein Beat, der schon lief, lief zu Ende -- mitten in den Qt-Abbau.

Diese Tests machen das Fenster deterministisch: ein Beat-Callback blockiert,
waehrend reset()/shutdown() kommt. Vor dem Fix lebte der Faden danach weiter.
Eigene ``BPMManager``-Instanzen, nie das Singleton (shutdown() ist endgueltig).
"""
from __future__ import annotations

import threading
import time

from src.core.engine.bpm_manager import BPMManager


def _manager_mit_haengendem_beat(dauer: float = 0.3):
    """Manager, dessen erster Beat ``dauer`` Sekunden im Callback steckt."""
    mgr = BPMManager()
    im_beat = threading.Event()

    def langsamer_beat(_idx):
        im_beat.set()
        time.sleep(dauer)

    mgr.subscribe_beat(langsamer_beat)
    mgr.set_manual_bpm(120.0)
    assert im_beat.wait(2.0), "Beat-Faden hat nie gefeuert"
    faden = mgr._timer
    assert faden is not None and faden.is_alive()
    return mgr, faden


def test_reset_wartet_auf_laufenden_beat():
    mgr, faden = _manager_mit_haengendem_beat()
    mgr.reset()
    # Kern von QA-103: nach reset() laeuft kein Beat mehr parallel weiter.
    assert not faden.is_alive()
    assert mgr._timer is None and mgr._running is False


def test_shutdown_stoppt_und_startet_nicht_neu():
    mgr, faden = _manager_mit_haengendem_beat()
    assert mgr.shutdown() is True
    assert not faden.is_alive()
    # Eine spaete Quelle (Tap/OS2L/Datei) darf nach dem App-Ende keinen neuen
    # Faden mehr anwerfen.
    mgr.set_manual_bpm(128.0)
    assert mgr._timer is None and mgr._running is False


def test_reset_aus_dem_beat_faden_selbst_blockiert_nicht():
    """Ein Beat-Callback, der reset() ruft, darf nicht auf sich selbst warten."""
    mgr = BPMManager()
    fertig = threading.Event()

    def reset_im_beat(_idx):
        mgr.reset()
        fertig.set()

    mgr.subscribe_beat(reset_im_beat)
    t0 = time.perf_counter()
    mgr.set_manual_bpm(120.0)
    assert fertig.wait(2.0)
    assert time.perf_counter() - t0 < 0.9   # kein join-Timeout abgesessen
    mgr.shutdown()


def test_shutdown_ohne_faden_ist_harmlos():
    mgr = BPMManager()
    assert mgr.shutdown() is True
    assert mgr.shutdown() is True


def test_main_window_stoppt_bpm_faden_beim_beenden():
    """closeEvent ruft shutdown() VOR dem Output-/Audio-Abbau (Quelltext-Waechter:
    ein echtes MainWindow wuerde Show-DB und DMX-Ausgabe anfassen)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
    close = src[src.index("    def closeEvent(self, event):"):]
    i_bpm = close.index("_mgr.shutdown()")
    assert i_bpm < close.index("get_audio_capture().stop()")
    assert i_bpm < close.index("output_manager.stop(")


def test_freigeben_hebt_shutdown_auf():
    """Nach shutdown() (Fenster geschlossen) startet der interne Takt nicht mehr;
    freigeben() — vom naechsten Hauptfenster gerufen — erlaubt ihn wieder."""
    from src.core.engine.bpm_manager import BPMManager
    m = BPMManager()
    m.shutdown()
    m.set_bpm(120)
    assert not m._running
    m.freigeben()
    m.set_bpm(120)
    try:
        assert m._running
    finally:
        m.shutdown()

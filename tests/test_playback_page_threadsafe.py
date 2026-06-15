"""Regression (crash.log 2026-06-14): Ein Page-Wechsel aus einem Fremd-Thread
(MIDI-RX ruft PlaybackEngine.set_page) darf die Playback-UI NICHT direkt aus dem
Worker-Thread aktualisieren — frueher baute der MIDI-Thread die QTableWidget neu
auf -> Freeze + Access Violation. Jetzt marshallt ein Qt-Signal in den GUI-Thread.
"""
from __future__ import annotations
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_playbackview_has_page_signal():
    from src.ui.views.playback_view import PlaybackView
    # Das marshallende Signal existiert als echtes Qt-Signal der Klasse.
    assert isinstance(PlaybackView.__dict__.get("_page_changed"), Signal)


def test_page_change_from_worker_thread_updates_ui_without_crash():
    _app()
    from src.core.app_state import get_state
    from src.ui.views.playback_view import PlaybackView

    state = get_state()
    if state.playback_engine is None:
        state.start_playback()

    view = PlaybackView()
    app = QApplication.instance()

    # Page-Wechsel aus einem ECHTEN Fremd-Thread anstossen (wie MIDI-RX).
    pe = state.playback_engine
    err: list[BaseException] = []

    def worker():
        try:
            pe.set_page(2)
        except BaseException as e:   # pragma: no cover - darf nicht passieren
            err.append(e)

    t = threading.Thread(target=worker, name="FakeMidiRX")
    t.start()
    t.join(timeout=2.0)
    assert not err, f"set_page aus Fremd-Thread warf: {err}"

    # Das Signal ist gequeued -> erst processEvents liefert die UI-Aktualisierung.
    for _ in range(5):
        app.processEvents()

    assert view._page_buttons[2].isChecked(), \
        "Page-Button wurde nach Cross-Thread-Wechsel nicht (im GUI-Thread) aktualisiert"

    # zuruecksetzen, damit der globale Singleton-Zustand andere Tests nicht stoert
    pe.set_page(0)
    for _ in range(5):
        app.processEvents()

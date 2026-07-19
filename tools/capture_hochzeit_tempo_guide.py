"""Reproduzierbare Screenshots für die Hochzeit-Tempo-Anleitung.

Die Show wird nur im Arbeitsspeicher bedient. ``hochzeit.lshow`` wird nicht
erneut gespeichert oder verändert.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "windows"
os.environ["QT_SCALE_FACTOR"] = "0.5"
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
# STAB-CURSHOW (a): load_show schreibt in die Show-DB — isolierte Wegwerf-DB via
# _gen_env, damit der Capture-Lauf Davids echte data/current_show.db nicht anfasst.
# (QT_QPA_PLATFORM='windows' oben gewinnt gegen das offscreen-setdefault.)
import _gen_env  # noqa: F401
from _showpath import find_show

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox

from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.show.show_file import load_show
from src.ui.main_window import MainWindow
from src.ui.virtualconsole.vc_live_editor import VCLiveEditor
from src.ui.virtualconsole.vc_speedial import VCSpeedDial


SHOW = find_show("hochzeit.lshow")
OUT = ROOT / "docs" / "anleitung_hochzeit_tempo" / "img"


def settle(app: QApplication, ms: int = 200) -> None:
    app.processEvents()
    loop = [True]
    QTimer.singleShot(ms, lambda: loop.clear())
    while loop:
        app.processEvents()


def save_widget(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settle(QApplication.instance(), 250)
    if not widget.grab().save(str(OUT / name)):
        raise RuntimeError(f"Screenshot konnte nicht gespeichert werden: {name}")


def capture_speed_dialog(dial: VCSpeedDial, name: str) -> None:
    def capture_and_close() -> None:
        dialogs = [
            w for w in QApplication.topLevelWidgets()
            if isinstance(w, QDialog) and w.windowTitle() == "Speed Dial Einstellungen"
        ]
        if not dialogs:
            QTimer.singleShot(100, capture_and_close)
            return
        dialog = dialogs[0]
        dialog.adjustSize()
        save_widget(dialog, name)
        dialog.reject()

    QTimer.singleShot(250, capture_and_close)
    dial._open_properties()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    settle(app, 500)

    ok, msg = load_show(str(SHOW))
    if not ok:
        raise RuntimeError(msg)
    window.setWindowTitle(f"LightOS – Hochzeit-Show – {msg}")
    settle(app, 500)

    vc = window._vc_view
    window._switch_section(3)
    vc._canvas.set_active_bank(3)
    vc._btn_edit.setChecked(False)
    vc._btn_sidebar.setChecked(False)
    settle(app, 350)
    save_widget(window, "01_bank4_uebersicht.png")

    dials = {d.caption: d for d in vc._canvas.findChildren(VCSpeedDial)}
    for caption in ("Farb Wechsel", "An Aus"):
        if caption not in dials:
            raise RuntimeError(f"Speed-Dial fehlt: {caption}")

    vc._btn_edit.setChecked(True)
    settle(app, 250)
    capture_speed_dialog(dials["Farb Wechsel"], "02_speed_farbe_ziele.png")
    capture_speed_dialog(dials["An Aus"], "03_speed_dimmer_ziele.png")

    editor = VCLiveEditor(31, window)
    editor.adjustSize()
    editor.show()
    settle(app, 250)
    save_widget(editor, "04_effekt_tempo_bus_global.png")
    editor.close()

    window._switch_section(7)
    bpm_view = window._bpm_manager_view
    bpm_view._refresh_speeds()
    settle(app, 350)
    panel = next(
        box for box in bpm_view.findChildren(QGroupBox)
        if box.title().startswith("Tempo-Speeds")
    )
    save_widget(panel, "05_bpm_auto_sync.png")

    get_bpm_manager().set_manual_bpm(128.0)
    get_tempo_bus_manager().advance_frame(0.1)
    dials["Farb Wechsel"]._set_factor(1.0)
    dials["An Aus"]._set_factor(0.5)
    for dial in dials.values():
        dial._poll_live()

    window._switch_section(3)
    vc._canvas.set_active_bank(3)
    vc._btn_edit.setChecked(False)
    vc._btn_sidebar.setChecked(False)
    settle(app, 500)
    save_widget(window, "06_fertig_128_bpm.png")

    window.close()
    app.processEvents()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())

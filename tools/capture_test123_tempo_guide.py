"""Reproduzierbare Screenshots fuer die Test123-Tempo-Anleitung.

Die Show wird nur im Arbeitsspeicher angepasst. ``test123.lshow`` wird nicht
gespeichert oder veraendert.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox

from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.effect_live import set_param
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.show.show_file import load_show
from src.ui.main_window import MainWindow
from src.ui.virtualconsole.vc_live_editor import VCLiveEditor
from src.ui.virtualconsole.vc_speedial import VCSpeedDial


SHOW = ROOT / "shows" / "test123.lshow"
OUT = ROOT / "docs" / "anleitung_test123_tempo" / "img"


def settle(app: QApplication, ms: int = 200) -> None:
    app.processEvents()
    loop = [True]
    QTimer.singleShot(ms, lambda: loop.clear())
    while loop:
        app.processEvents()


def save_widget(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settle(QApplication.instance(), 250)
    pixmap = widget.grab()
    if not pixmap.save(str(OUT / name)):
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
    window.setWindowTitle(f"LightOS – Test123 Lightshow – {msg}")
    settle(app, 500)

    vc = window._vc_view
    window._switch_section(3)
    vc._canvas.set_active_bank(3)
    vc._btn_edit.setChecked(False)
    vc._btn_sidebar.setChecked(False)
    settle(app, 350)
    save_widget(window, "01_bank4_uebersicht.png")

    dials = {d.caption: d for d in vc._canvas.findChildren(VCSpeedDial)}
    for caption in ("Farb wechsel", "L R", "Schwingen"):
        if caption not in dials:
            raise RuntimeError(f"Speed-Dial fehlt: {caption}")

    vc._btn_edit.setChecked(True)
    settle(app, 250)
    capture_speed_dialog(dials["Farb wechsel"], "02_speed_farbe_ziele.png")
    capture_speed_dialog(dials["L R"], "03_speed_dimmer_ziele.png")
    capture_speed_dialog(dials["Schwingen"], "04_speed_bewegung_ziele.png")

    # Ein Effekt-Dialog zeigt den entscheidenden Schritt: Tempo-Bus = Global.
    editor = VCLiveEditor(6, window)
    _kind, bus_combo = editor._controls["tempo_bus_id"]
    bus_combo.setCurrentText("Global")
    editor._controls["speed"][1].setValue(1.0)
    editor._controls["tempo_multiplier"][1].setValue(1.0)
    editor._controls["phase_offset"][1].setValue(0.0)
    editor.adjustSize()
    editor.show()
    settle(app, 250)
    save_widget(editor, "05_effekt_tempo_bus_global.png")
    editor.close()

    # BPM-Panel mit aktivem Auto-Sync.
    window._switch_section(7)
    bpm_view = window._bpm_manager_view
    get_tempo_bus_manager().set_auto_sync(True)
    bpm_view._refresh_speeds()
    bpm_view._chk_auto_sync.setChecked(True)
    settle(app, 350)
    panel = next(
        box for box in bpm_view.findChildren(QGroupBox)
        if box.title().startswith("Tempo-Speeds")
    )
    save_widget(panel, "06_bpm_auto_sync.png")

    # Fertiges Beispiel nur im RAM: alle Ziel-Effekte Global, drei Faktoren.
    for fid in (6, 8, 7, 13, 3, 2, 4, 12, 5):
        set_param("tempo_bus_id", "Global", fid)
    get_bpm_manager().set_manual_bpm(128.0)
    get_tempo_bus_manager().advance_frame(0.1)
    dials["Farb wechsel"]._set_factor(1.0)
    dials["L R"]._set_factor(0.5)
    dials["Schwingen"]._set_factor(2.0)
    for dial in dials.values():
        dial._poll_live()

    window._switch_section(3)
    vc._canvas.set_active_bank(3)
    vc._btn_edit.setChecked(False)
    vc._btn_sidebar.setChecked(False)
    settle(app, 500)
    save_widget(window, "07_fertig_128_bpm.png")

    window.close()
    app.processEvents()
    # LightOS startet optionale Hintergrundhelfer. Fuer den einmaligen
    # Screenshot-Lauf nach dem sicheren Schliessen nicht auf deren Teardown warten.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproduzierbare Screenshots für die Hochzeit-Tempo-Anleitung (ARCHIVIERT).

Die Show wird nur im Arbeitsspeicher bedient. ``hochzeit.lshow`` wird nicht
erneut gespeichert oder verändert.

★ **Ausgemustert mit TOOL-5 (2026-10-02).** DOC-17 hat die Anleitung
``docs/anleitung_hochzeit_tempo/`` auf Tempo-Controller umgestellt und ihre
Bilder entfernt — sie ist seither bildlos. Dieses Werkzeug fotografierte das
ALTE Bedienkonzept (Speed-Dials „Farb Wechsel"/„An Aus" als Multiplikatoren)
und hat damit kein Ziel mehr. Es schreibt deshalb nicht mehr nach ``docs/``,
sondern in einen Wegwerf-Ordner (``LIGHTOS_CAPTURE_OUT`` oder Temp-Ordner).
Neue Anleitungsbilder entstehen ueber ``tools/anleitungsbilder.py``.

TOOL-4: fehlt der Show ein erwartetes Widget, nennt die Meldung die Show, das
fehlende Widget und die vorhandenen — statt eines nackten ``RuntimeError``.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# XPLAT-25: ein Capture braucht ein ECHT gerendertes Fenster — offscreen
# liefert bei QtWebEngine schwarze Bilder. Die native Plattform muss deshalb
# erzwungen werden (ein geerbtes QT_QPA_PLATFORM=offscreen soll NICHT gewinnen)
# — aber plattformrichtig: "windows" gibt es nur auf Windows, auf Linux heisst
# die native Plattform "xcb". Hart gesetzt starb das Werkzeug hier mit
# rc=134 (qt.qpa.plugin: Could not find the Qt platform plugin "windows").
os.environ["QT_QPA_PLATFORM"] = "windows" if os.name == "nt" else "xcb"
os.environ["QT_SCALE_FACTOR"] = "0.5"
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
# STAB-CURSHOW (a): load_show schreibt in die Show-DB — isolierte Wegwerf-DB via
# _gen_env (zieht _bootstrap mit), damit der Capture-Lauf die echte
# data/current_show.db nicht anfasst. (Die native Plattform oben gewinnt gegen
# ein geerbtes offscreen.) _bootstrap legt Repo-Root + tools/ auf sys.path.
import _bootstrap  # noqa: F401
from _showpath import find_show

ROOT = Path(_bootstrap.REPO_ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QGroupBox

from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.show.show_file import load_show
from src.ui.main_window import MainWindow
from src.ui.virtualconsole.vc_live_editor import VCLiveEditor
from src.ui.virtualconsole.vc_speedial import VCSpeedDial


SHOW_NAME = "hochzeit.lshow"
SHOW = find_show(SHOW_NAME, hint="private Show des Projektinhabers, nicht im Repo")
# TOOL-5: nicht mehr nach docs/ — die Anleitung ist seit DOC-17 bildlos.
OUT = Path(os.environ.get("LIGHTOS_CAPTURE_OUT")
           or Path(tempfile.gettempdir()) / "lightos_capture_hochzeit_tempo")
#: Speed-Dials (Bank 4) aus dem alten Multiplikator-Layout, die das Werkzeug fotografiert.
ERWARTETE_DIALS = ("Farb Wechsel", "An Aus")


def fehlende_dials_meldung(vorhanden, show=SHOW_NAME) -> str:
    """TOOL-4: Leerer Text, wenn alle erwarteten Dials da sind — sonst eine
    Meldung, die Show, fehlende und vorhandene Dials nennt."""
    fehlend = [c for c in ERWARTETE_DIALS if c not in vorhanden]
    if not fehlend:
        return ""
    da = ", ".join(sorted(f"'{c}'" for c in vorhanden)) or "keine"
    return (f"Show '{show}' passt nicht zu diesem (archivierten) Werkzeug: "
            f"Speed-Dial(s) fehlen: {', '.join(repr(c) for c in fehlend)}. "
            f"Vorhanden: {da}. Das Werkzeug erwartet das alte Multiplikator-Layout "
            f"(Bank 4); die Anleitung nutzt seit DOC-17 Tempo-Controller und keine Bilder.")


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
    meldung = fehlende_dials_meldung(dials)
    if meldung:
        window.close()
        raise SystemExit(meldung)

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
    bpm_view = window._tempo_bus_view   # BPM-08: Sub-Tab „Tempo-Buses"
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
    print(f"Bilder in {OUT}")
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())

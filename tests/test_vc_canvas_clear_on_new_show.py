"""VCL-04: VC-Canvas wird bei „Neue Show" / Laden einer Show OHNE VC-Widgets geleert.

Bug (Backlog VCL-04, live beobachtet + headless verifiziert): `reset_show()` setzt
`state._vc_layout = {}` und feuert SHOW_LOADED; der einzige Pfad, der den Canvas
leert, ist `main_window._on_show_loaded` -> `VCCanvas.from_dict()` (ruft intern
`_clear()`). Die alte Guard-Bedingung `if vc and vc.get("widgets")` war bei einem
LEEREN Dict falsy -> `from_dict()` lief nie -> die VC-Widgets der VORIGEN Show
ueberlebten „Neue Show" und das Laden einer Show ohne VC-Widgets dauerhaft.

Fix: `isinstance(vc, dict)` — jedes vorhandene Layout-Dict (auch leer) laeuft durch
`from_dict()`; nur fehlendes/kaputtes `_vc_layout` laesst den Canvas unangetastet.

Erster Test, der das echte `MainWindow` baut (inkl. Sync-Subscriptions) — der
Isolate-Runner kapselt die Datei in einen eigenen Prozess.
"""
import json
import os
import tempfile
import unittest
import uuid
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from src.core.show.show_file import load_show, reset_show
from src.ui.virtualconsole.vc_widget import VCWidget


def _app():
    return QApplication.instance() or QApplication([])


def _direct_children(canvas):
    return canvas.findChildren(
        VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)


class TestVcCanvasClearOnNewShow(unittest.TestCase):
    """Kompletter Zyklus in EINEM Test (MainWindow-Bau ist teuer; die Phasen
    bauen aufeinander auf wie im echten Bedienablauf)."""

    def test_new_show_and_empty_show_clear_vc_canvas(self):
        app = _app()
        from src.ui.main_window import MainWindow
        win = MainWindow()
        try:
            canvas = win._vc_view._canvas

            # ── Phase 1: „Neue Show" (exakter Handler-Pfad aus _new_show) ──
            canvas._add_widget("VCButton", QPoint(20, 20))
            canvas._add_widget("VCSlider", QPoint(120, 20))
            canvas._add_widget("VCMultiLiveEditor", QPoint(220, 20))
            self.assertEqual(len(_direct_children(canvas)), 3)

            reset_show()
            win._current_show_path = None
            app.processEvents()
            app.processEvents()          # deleteLater braucht Event-Loop-Durchlauf

            self.assertEqual(
                len(_direct_children(canvas)), 0,
                "VC-Widgets der vorigen Show ueberleben 'Neue Show' (VCL-04)")
            self.assertEqual(canvas.to_dict().get("widgets", []), [])

            # ── Phase 2: load_show() einer Show mit leerem virtual_console ──
            canvas._add_widget("VCMultiLiveEditor", QPoint(300, 200))
            self.assertEqual(len(_direct_children(canvas)), 1)

            show_path = os.path.join(
                tempfile.gettempdir(), f"vcl04_empty_{uuid.uuid4().hex}.lshow")
            with zipfile.ZipFile(show_path, "w") as zf:
                zf.writestr("show.json", json.dumps({
                    "version": 1, "name": "Leere Show", "patch": [],
                    "programmer": {}, "cue_stacks": [], "executors": [],
                    "virtual_console": {},
                }))
            try:
                ok, _msg = load_show(show_path)
                self.assertTrue(ok)
                app.processEvents()
                app.processEvents()
                self.assertEqual(
                    len(_direct_children(canvas)), 0,
                    "VC-Widgets ueberleben das Laden einer Show ohne VC-Widgets")
            finally:
                try:
                    os.remove(show_path)
                except OSError:
                    pass

            # ── Phase 3: kaputtes _vc_layout (kein dict) laesst Canvas stehen ──
            canvas._add_widget("VCButton", QPoint(40, 40))
            win._state._vc_layout = None      # defekte/fremde Show simulieren
            win._on_show_loaded("show_loaded", {})
            app.processEvents()
            self.assertEqual(
                len(_direct_children(canvas)), 1,
                "Nicht-dict _vc_layout darf den Canvas NICHT leeren (Guard)")
        finally:
            try:
                win.close()
                win.deleteLater()
            except Exception:
                pass
            app.processEvents()
            reset_show()                       # globalen State fuer Folge-Tests raeumen
            app.processEvents()


if __name__ == "__main__":
    unittest.main()

"""Show-Manager: Track-Panel-Refresh darf nicht am Layout-Aufräumen abstuerzen.

Regression (live gefunden 2026-07-09 im Feature-Verifikations-Sweep): Klick auf
'+ Neue Show' im Show-Manager warf
    AttributeError: 'NoneType' object has no attribute 'deleteLater'
Ursache: TrackLabelPanel.refresh() raeumte das Layout via
    self.layout().itemAt(i).widget().deleteLater()
ohne Guard — enthaelt das Layout ein Nicht-Widget-Item (Spacer/Stretch/Sub-Layout),
liefert .widget() None. Fix: gegen None guarden.

Bewusst NUR das leichte TrackLabelPanel getestet (nicht die ganze ShowManagerView):
deren Konstruktion zieht Timeline-/DB-Objekte nach, die beim GC-Teardown headless
sporadisch nativ segfaulten — das Panel deckt die gefixte Zeile praezise ab.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QVBoxLayout, QLabel

from src.ui.views.show_manager_view import TrackLabelPanel

_app = QApplication.instance() or QApplication([])


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
    # ihrer Tests, dann gibt es den Modulnamen hier nicht.
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class TrackPanelRefreshTest(unittest.TestCase):
    def test_refresh_tolerates_non_widget_layout_item(self):
        """Ein Nicht-Widget-Layout-Item (Stretch -> .widget() is None) darf
        refresh() nicht mehr crashen lassen. Vor dem Fix: AttributeError."""
        panel = TrackLabelPanel(SimpleNamespace(_current_show=None))
        try:
            lay = QVBoxLayout(panel)
            lay.addWidget(QLabel("track"))
            lay.addStretch(1)          # Nicht-Widget-Item
            panel.refresh()            # vor dem Fix: AttributeError deleteLater/None
        finally:
            panel.deleteLater()
            _app.processEvents()

    def test_refresh_on_empty_panel_is_noop(self):
        """Frisches Panel ohne Layout -> refresh() legt Layout an, kein Fehler."""
        panel = TrackLabelPanel(SimpleNamespace(_current_show=None))
        try:
            panel.refresh()
            self.assertIsNotNone(panel.layout())
        finally:
            panel.deleteLater()
            _app.processEvents()


if __name__ == "__main__":
    unittest.main()

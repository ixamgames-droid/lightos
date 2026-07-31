"""WURZEL-Fix (2026-06-24, analog efx): Der Programmer-eingebettete RGB-Matrix-
Editor (follow_selection) darf das ``fixture_grid`` der gespielten Matrix NICHT
im Hintergrund ueberschreiben.

Gleiches latentes Problem wie beim EFX-Bug (siehe test_efx_follow_no_clobber):
der eingebettete Follow-Editor hoert GLOBAL auf SELECTION_CHANGED und ruft
``_assign_from_selection``, das ``_current.fixture_grid`` (und ``_saved``) aus der
aktuellen Auswahl/Gruppe neu bildet — auch wenn der Editor gar nicht sichtbar ist
(Nutzer in der Virtual Console o.ae.). So konnte eine per VC-Button gespielte
RGB-Matrix ihr Grid im Hintergrund verlieren/aendern.

Fix: ``_sync_follow_selection`` wirkt nur, wenn die Editor-Seite sichtbar/aktiv
ist; ``showEvent`` holt den Sync beim Sichtbarwerden nach.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import src.core.app_state as A
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.ui.views.rgb_matrix_view import RgbMatrixView


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


class FollowNoBackgroundClobberTest(unittest.TestCase):
    def setUp(self):
        self._sel = []
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        # Auswahl/Gruppe deterministisch mocken (kein DB-/Gruppen-Pfad).
        st = A.get_state()
        st.get_selected_group_id = lambda: None
        st.get_selected_fids = lambda: list(self._sel)
        # Eingebetteter Follow-Editor — NICHT gezeigt.
        self.view = RgbMatrixView(follow_selection=True)
        self.m = self.fm.new_rgb_matrix(name="Matrix")
        self.m.algorithm = RgbAlgorithm.CHASE
        self.m.cols, self.m.rows = 3, 1
        self.m.fixture_grid = [10, 20, 30]      # im Matrix-Tab zugewiesen / gespielt
        # Editor zeigt genau diese Matrix (wie nach Auswahl im Programmer).
        self.view._saved = self.m
        self.view._current = self.m

    def tearDown(self):
        try:
            self.view.deleteLater()
        except Exception:
            pass
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                try:
                    self.fm.remove(f.id)
                except Exception:
                    pass

    def test_hidden_editor_keeps_grid_on_empty_selection(self):
        # Hintergrund-Selektionsevent (Nutzer ist in der VC, nichts ausgewaehlt):
        self._sel = []
        self.assertFalse(self.view.isVisible())
        self.view._sync_follow_selection()      # = der SELECTION_CHANGED-Handler
        self.assertEqual(self.m.fixture_grid, [10, 20, 30],
                         "Unsichtbarer Follow-Editor darf das Grid nicht aendern")

    def test_hidden_editor_keeps_grid_on_foreign_selection(self):
        # Auch eine fremde Auswahl (anderes Geraet) darf das Grid nicht aendern.
        self._sel = [99, 98]
        self.view._sync_follow_selection()
        self.assertEqual(self.m.fixture_grid, [10, 20, 30],
                         "Hintergrund-Auswahl darf das gespielte Grid nicht clobbern")

    def test_visible_editor_still_follows_selection(self):
        # Sichtbar/aktiv: Follow funktioniert weiterhin wie vorgesehen.
        self.view.show()
        self.assertTrue(self.view.isVisible())
        self._sel = [7, 8]
        self.view._sync_follow_selection()
        self.assertEqual(self.m.fixture_grid, [7, 8],
                         "Sichtbarer Follow-Editor folgt der Auswahl weiterhin")
        self.view.deleteLater()


if __name__ == "__main__":
    unittest.main()

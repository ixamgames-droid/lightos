"""Regression: einen LAUFENDEN Chaser live verkuerzen darf den Engine-Tick
NICHT abstuerzen lassen.

Vorbestehender latenter Bug (gefunden 2026-07-01): Loescht man im Chaser-Editor
(`_remove_step` -> ``steps.pop(row)``) einen Schritt, waehrend der Chaser laeuft,
konnte ``_step_idx >= len(steps)`` zurueckbleiben. Der naechste Engine-Tick griff
dann in ``write()`` (self.steps[self._step_idx]) bzw. ``_render_and_blend()``
out-of-range zu -> IndexError / Crash.

Fix: ``Chaser._clamp_step_idx()`` begrenzt ``_step_idx`` defensiv vor jedem
Step-Zugriff; ``ChaserEditor._remove_step`` clampt zusaetzlich direkt nach dem
Entfernen. Diese Tests decken beide Ebenen ab.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from src.core.engine.chaser import Chaser, ChaserStep


def _running_chaser(n: int, at: int | None = None) -> Chaser:
    """Chaser mit n Schritten, laufend, _step_idx auf dem letzten (oder ``at``)."""
    c = Chaser("clamp")
    for i in range(n):
        c.steps.append(ChaserStep(function_id=1000 + i, hold=1.0))
    c._running = True
    c._step_idx = (n - 1) if at is None else at
    return c


class ChaserStepIdxClampEngineTest(unittest.TestCase):
    """Engine-Ebene: der Sicherheitsnetz-Clamp in write()/_render_and_blend()."""

    def test_write_after_pop_no_indexerror(self):
        # Chaser steht auf dem letzten Schritt (idx 2), dann wird er verkuerzt.
        c = _running_chaser(3)          # idx = 2
        c.steps.pop()                   # len -> 2, idx 2 ist jetzt out-of-range
        # function_registry=None -> _render_and_blend kehrt frueh zurueck, der
        # Zugriff self.steps[self._step_idx] in write() bleibt und wuerde crashen.
        c.write({}, [], 0.05, function_registry=None)   # darf NICHT werfen
        self.assertEqual(c._step_idx, 1)                # auf neuen letzten geclampt
        self.assertLess(c._step_idx, len(c.steps))

    def test_render_and_blend_after_pop_no_indexerror(self):
        # Truthy function_registry -> _render_and_blend laeuft bis zum
        # Step-Zugriff (Zeile ~251); der Child-Lookup schlaegt fehl (None),
        # aber der IndexError-Pfad ist der interessante.
        c = _running_chaser(3)
        c.steps.pop()
        c.write({}, [], 0.05, function_registry={99999: object()})   # darf NICHT werfen
        self.assertLess(c._step_idx, len(c.steps))

    def test_multiple_pops_still_valid(self):
        c = _running_chaser(5)          # idx = 4
        for _ in range(3):              # len -> 2
            c.steps.pop()
        c.write({}, [], 0.05, function_registry=None)
        self.assertEqual(c._step_idx, 1)

    def test_clamp_helper_handles_empty(self):
        c = _running_chaser(2, at=1)
        c.steps.clear()
        c._clamp_step_idx()             # leer -> 0, kein Fehler
        self.assertEqual(c._step_idx, 0)

    def test_clamp_helper_handles_negative(self):
        c = _running_chaser(3, at=-2)
        c._clamp_step_idx()
        self.assertEqual(c._step_idx, 0)

    def test_clamp_leaves_valid_index_untouched(self):
        c = _running_chaser(4, at=2)
        c._clamp_step_idx()
        self.assertEqual(c._step_idx, 2)


class ChaserEditorRemoveStepClampTest(unittest.TestCase):
    """UI-Ebene: der eigentliche Reproduktionsweg ueber den Chaser-Editor."""

    def test_editor_remove_step_clamps_running_chaser(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.ui.views.chaser_editor import ChaserEditor

        c = _running_chaser(3)          # laufend, idx = 2 (letzter Schritt)
        ed = ChaserEditor(c)
        try:
            # Den letzten Schritt selektieren und loeschen (wie der Nutzer).
            ed._table.setCurrentCell(2, 0)
            ed._remove_step()

            self.assertEqual(len(c.steps), 2)
            self.assertLess(c._step_idx, len(c.steps))
            self.assertEqual(c._step_idx, 1)

            # Und der naechste Engine-Tick darf nicht mehr crashen.
            c.write({}, [], 0.05, function_registry=None)
            self.assertLess(c._step_idx, len(c.steps))
        finally:
            ed.setParent(None)
            ed.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()

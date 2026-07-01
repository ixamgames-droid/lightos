"""Regression: eine LAUFENDE Sequence live verkuerzen darf den Engine-Tick
NICHT abstuerzen lassen.

Vorbestehender latenter Bug (gefunden 2026-07-01, gleiche Form wie der Chaser-Bug
auf ``fix/chaser-stepidx-clamp``): Loescht man im Sequence-Editor
(`_delete_step` -> ``del steps[row]``) einen Schritt, waehrend die Sequence laeuft,
konnte ``_step_idx >= len(steps)`` zurueckbleiben. Der naechste Engine-Tick griff
dann in ``write()`` (``self.steps[self._step_idx]``) out-of-range zu -> IndexError /
Crash.

Fix: ``Sequence._clamp_step_idx()`` begrenzt ``_step_idx`` defensiv vor jedem
Step-Zugriff; ``SequenceEditor._delete_step`` clampt zusaetzlich direkt nach dem
Entfernen. Diese Tests decken beide Ebenen ab.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from src.core.engine.sequence import Sequence, SequenceStep


def _running_sequence(n: int, at: int | None = None) -> Sequence:
    """Sequence mit n Schritten, laufend, _step_idx auf dem letzten (oder ``at``)."""
    s = Sequence("clamp")
    for _ in range(n):
        s.steps.append(SequenceStep(values={}, fade_in=0.0, hold=1.0))
    s._running = True
    s._step_idx = (n - 1) if at is None else at
    return s


class SequenceStepIdxClampEngineTest(unittest.TestCase):
    """Engine-Ebene: der Sicherheitsnetz-Clamp in write()."""

    def test_write_after_pop_no_indexerror(self):
        # Sequence steht auf dem letzten Schritt (idx 2), dann wird sie verkuerzt.
        s = _running_sequence(3)        # idx = 2
        s.steps.pop()                   # len -> 2, idx 2 ist jetzt out-of-range
        s.write({}, [], 0.05)           # darf NICHT werfen
        self.assertEqual(s._step_idx, 1)                # auf neuen letzten geclampt
        self.assertLess(s._step_idx, len(s.steps))

    def test_multiple_pops_still_valid(self):
        s = _running_sequence(5)        # idx = 4
        for _ in range(3):              # len -> 2
            s.steps.pop()
        s.write({}, [], 0.05)
        self.assertEqual(s._step_idx, 1)

    def test_clamp_helper_handles_empty(self):
        s = _running_sequence(2, at=1)
        s.steps.clear()
        s._clamp_step_idx()             # leer -> 0, kein Fehler
        self.assertEqual(s._step_idx, 0)

    def test_write_when_all_steps_removed_is_noop(self):
        # Alle Schritte weg + noch laufend: write() darf nicht crashen. Der
        # ``not self.steps``-Guard kehrt frueh zurueck (kein Step-Zugriff); der
        # (dann veraltete) _step_idx wird beim naechsten nicht-leeren Tick durch
        # _clamp_step_idx() wieder gueltig gezogen.
        s = _running_sequence(3, at=2)
        s.steps.clear()
        s.write({}, [], 0.05)           # darf NICHT werfen
        # Schritt wieder anhaengen -> naechster Tick muss den Index heilen.
        s.steps.append(SequenceStep(values={}, fade_in=0.0, hold=1.0))
        s.write({}, [], 0.05)           # darf NICHT werfen
        self.assertEqual(s._step_idx, 0)
        self.assertLess(s._step_idx, len(s.steps))

    def test_clamp_helper_handles_negative(self):
        s = _running_sequence(3, at=-2)
        s._clamp_step_idx()
        self.assertEqual(s._step_idx, 0)

    def test_clamp_leaves_valid_index_untouched(self):
        s = _running_sequence(4, at=2)
        s._clamp_step_idx()
        self.assertEqual(s._step_idx, 2)


class SequenceEditorDeleteStepClampTest(unittest.TestCase):
    """UI-Ebene: der eigentliche Reproduktionsweg ueber den Sequence-Editor."""

    def test_editor_delete_step_clamps_running_sequence(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.ui.views.sequence_editor import SequenceEditor

        s = _running_sequence(3)        # laufend, idx = 2 (letzter Schritt)
        ed = SequenceEditor(s)
        try:
            # Den letzten Schritt selektieren und loeschen (wie der Nutzer).
            ed._tbl.selectRow(2)
            ed._delete_step()

            self.assertEqual(len(s.steps), 2)
            self.assertLess(s._step_idx, len(s.steps))
            self.assertEqual(s._step_idx, 1)

            # Und der naechste Engine-Tick darf nicht mehr crashen.
            s.write({}, [], 0.05)
            self.assertLess(s._step_idx, len(s.steps))
        finally:
            ed.setParent(None)
            ed.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()

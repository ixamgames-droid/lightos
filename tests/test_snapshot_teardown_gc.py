"""GC-Teardown-Regression (2026-07): SnapshotsView-Baum darf nie in der
ZYKLISCHEN GC landen bzw. von aussen gepinnt werden.

Hintergrund (deterministischer nativer Crash von tests/test_snapshot_ignore.py,
rc=0xC0000005): PySide6 6.11/Python 3.14 uebersteht es nicht, wenn die zyklische
GC den OWNER-Wrapper eines Widget-Baums dealloziert (die Qt-Eltern-Kaskade
loescht dann mitten in der GC C++-Objekte in beliebiger Reihenfolge -> Access
Violation, faulthandler zeigt "Garbage-collecting"). Drei Ursachen wurden
gefixt:

1. ``SnapshotButton._view`` war eine STARKE Ref auf die View ->
   view -> _buttons -> Button -> view = Zyklus -> Owner nur per GC abraeumbar.
   Jetzt weakref: der Baum stirbt per Refcount, die GC fasst ihn nie an.
2. ``SnapFilePanel``: Lambda-Slots an ``itemExpanded``/``itemCollapsed`` des
   Baums werden von der C++-Connection stark und GC-unsichtbar gehalten ->
   externer Wrapper-Pin. Jetzt gebundene Methoden (bindet PySide6 schwach).

BEWUSST ZURUECKGESTELLT (STAB-09-Sweep): ``sync.subscribe_widget`` haelt den
Callback weiterhin STARK im globalen Bus — die Call-Site-Lambdas fangen
``self``, das pinnt jedes abonnierende Widget. Dieses Leck ist zugleich eine
versehentliche SCHUTZSCHICHT: es haelt auch Views mit EIGENEN internen
Zyklen (Matrix-/Programmer-Views) aus der zyklischen GC heraus. Ein Umbau auf
schwach gehaltene Callbacks (erprobt, PR #142, wieder zurueckgenommen) laesst
deren Baeume in die GC fallen -> dieselbe Upstream-AV in 6 anderen
Testdateien. Reihenfolge daher: ERST alle View-Zyklen brechen (Sweep), DANN
subscribe_widget auf weakrefs umstellen; Canaries: test_matrix_dirty_save,
test_matrix_group_scope, test_matrix_meta_view,
test_programmer_editor_load_guard, test_rgb_matrix_style_visibility,
test_rgb_matrix_view_controls.
"""
import gc
import os
import unittest
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from src.core.sync import StateSync, SyncEvent

_app = QApplication.instance() or QApplication([])


class ViewTreeRefcountDeathTest(unittest.TestCase):
    """Der Owner-Wrapper (SnapshotsView) muss per REFCOUNT sterben — landet er
    in der zyklischen GC, ist der naechste Lauf ein potenzieller nativer Crash."""

    def test_view_dies_by_refcount_and_panel_is_not_pinned(self):
        from src.core.app_state import get_state
        from src.ui.views.snapshots_view import SnapshotsView
        get_state()                      # Singletons wie in der App anlegen
        gc.collect()                     # sauberer Ausgangszustand
        gc.disable()                     # zyklische GC AUS -> nur Refcount raeumt auf
        try:
            view = SnapshotsView()
            vref = weakref.ref(view)
            pref = weakref.ref(view._snap_file_panel)
            del view
            self.assertIsNone(
                vref(),
                "SnapshotsView haengt in einem Referenz-Zyklus (stirbt nicht per "
                "Refcount) -> Owner-Dealloc in der zyklischen GC = native-AV-Risiko")
        finally:
            gc.enable()
        # Der Panel-Wrapper darf einen harmlosen Selbst-Zyklus haben (Callback-
        # Anker), aber KEINEN externen Pin: nach der GC muss er weg sein.
        for _ in range(3):
            gc.collect()
        self.assertIsNone(
            pref(),
            "SnapFilePanel wird von aussen am Leben gehalten (Lambda-Slot oder "
            "Bus-Callback pinnt den Wrapper) -> Use-after-free-Risiko")


class SubscribeWidgetNoPinTest(unittest.TestCase):
    """Verhalten rund um den (bewusst noch starken) Callback-Halt des Bus.

    Der eigentliche No-Pin-Test (Widget wird trotz self-fangendem Lambda
    einsammelbar) kommt ERST mit dem STAB-09-Sweep zurueck — siehe
    Modul-Docstring, Abschnitt "BEWUSST ZURUECKGESTELLT"."""

    def test_callback_lives_as_long_as_widget(self):
        """Der schwach gehaltene Callback darf NICHT vorzeitig sterben: der
        Anker am Widget muss ihn genau bis zum Widget-Tod am Leben halten."""
        sync = StateSync()
        calls = []

        def _make():
            w = QWidget()
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, w,
                                  lambda *_: calls.append(1))
            return w

        w = _make()                      # Widget lebt, Helper-Frame ist weg
        gc.collect()                     # ein nicht verankertes Lambda waere jetzt tot
        sync.emit(SyncEvent.PATCH_CHANGED)
        self.assertEqual(len(calls), 1,
                         "Callback starb vor dem Widget (Anker fehlt/zu schwach)")
        del w


if __name__ == "__main__":
    unittest.main()

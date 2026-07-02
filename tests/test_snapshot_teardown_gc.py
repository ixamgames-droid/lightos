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
2. ``sync.subscribe_widget`` hielt den Callback stark im GLOBALEN Bus; die
   Call-Site-Lambdas fangen ``self`` -> Widget unsterblich, sein C++-Objekt
   stirbt aber ueber die Eltern-Kaskade -> lebender Wrapper auf freiem
   Speicher. Jetzt: Callback am Widget verankert, Guard haelt nur weakrefs.
3. ``SnapFilePanel``: Lambda-Slots an ``itemExpanded``/``itemCollapsed`` des
   Baums werden von der C++-Connection stark und GC-unsichtbar gehalten ->
   selber Pin. Jetzt gebundene Methoden (bindet PySide6 schwach).
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
    """subscribe_widget darf das Widget nicht ueber den Callback unsterblich
    machen — auch dann nicht, wenn das Lambda ``self`` faengt (Standard-Muster
    aller Call-Sites)."""

    def test_self_capturing_lambda_does_not_pin_widget(self):
        sync = StateSync()

        # WICHTIG fuers Test-Design: das Abo passiert in einem HELPER, dessen
        # Frame stirbt — genau wie bei den echten Call-Sites (Abo im __init__
        # des Widgets). Ein ``del w`` im selben Scope wuerde die Closure-ZELLE
        # des Lambdas leeren und die Pin-Kette kuenstlich brechen — der Test
        # wuerde dann auch den ungefixten Stand gruen durchwinken.
        def _make():
            w = QWidget()
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, w,
                                  lambda *_: w.objectName())
            return weakref.ref(w)

        wref = _make()
        for _ in range(3):
            gc.collect()
        self.assertIsNone(
            wref(),
            "subscribe_widget pinnt das Widget ueber den stark gehaltenen "
            "Callback (Bus -> Lambda -> self)")
        # Toter Subscriber wird beim naechsten Emit uebersprungen + entfernt.
        sync.emit(SyncEvent.PATCH_CHANGED)
        self.assertEqual(sync._subscribers.get(SyncEvent.PATCH_CHANGED, []), [],
                         "toter Subscriber wurde beim Emit nicht abgemeldet")

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

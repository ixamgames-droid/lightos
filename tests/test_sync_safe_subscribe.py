"""StateSync-Haertung (2026-06-10): widget-gebundene Subscriptions werden beim
Zerstoeren des Widgets automatisch abgemeldet, und tote Subscriber (PySide6
"already deleted"-RuntimeError) werden beim Emit selbst-heilend entfernt.

Hintergrund: crash.log zeigte Access Violations in Programmer-Refreshes —
eingebettete Views (EFX/Matrix/Palette/SnapFilePanel) werden bei jedem
Layout-Wechsel neu gebaut, die alten blieben aber im Event-Bus registriert.
"""
import gc
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.sync import StateSync, SyncEvent


class SubscribeWidgetTest(unittest.TestCase):
    def test_unsubscribes_on_widget_destroy(self):
        from PySide6.QtWidgets import QApplication, QWidget
        app = QApplication.instance() or QApplication([])
        sync = StateSync()
        calls = []
        w = QWidget()
        sync.subscribe_widget(SyncEvent.PATCH_CHANGED, w,
                              lambda *_: calls.append(1))
        sync.emit(SyncEvent.PATCH_CHANGED)
        self.assertEqual(len(calls), 1)
        # Widget zerstoeren -> destroyed-Signal -> auto-unsubscribe
        del w
        gc.collect()
        app.processEvents()
        sync.emit(SyncEvent.PATCH_CHANGED)
        self.assertEqual(len(calls), 1, "toter Subscriber wurde noch beliefert")

    def test_non_widget_behaves_like_subscribe(self):
        sync = StateSync()
        calls = []
        sync.subscribe_widget(SyncEvent.GROUP_CHANGED, object(),
                              lambda *_: calls.append(1))
        sync.emit(SyncEvent.GROUP_CHANGED)
        self.assertEqual(len(calls), 1)


class SelfHealingEmitTest(unittest.TestCase):
    def test_dead_subscriber_removed(self):
        sync = StateSync()
        calls = []

        def dead(*_):
            calls.append(1)
            raise RuntimeError(
                "Internal C++ object (QListWidget) already deleted.")

        sync.subscribe(SyncEvent.FUNCTION_CHANGED, dead)
        sync.emit(SyncEvent.FUNCTION_CHANGED)
        self.assertEqual(len(calls), 1)
        sync.emit(SyncEvent.FUNCTION_CHANGED)
        self.assertEqual(len(calls), 1, "toter Subscriber nicht entfernt")

    def test_other_runtime_errors_keep_subscriber(self):
        sync = StateSync()
        calls = []

        def flaky(*_):
            calls.append(1)
            raise RuntimeError("anderes, transientes Problem")

        sync.subscribe(SyncEvent.GROUP_CHANGED, flaky)
        sync.emit(SyncEvent.GROUP_CHANGED)
        sync.emit(SyncEvent.GROUP_CHANGED)
        self.assertEqual(len(calls), 2,
                         "Subscriber faelschlich entfernt (kein Zombie)")


if __name__ == "__main__":
    unittest.main()

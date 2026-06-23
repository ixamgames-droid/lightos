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


class WidgetValidityGuardTest(unittest.TestCase):
    """STAB-03: Selbst wenn das destroyed-Signal die Abmeldung NICHT rechtzeitig
    ausloest (Qt loescht das C++-Objekt vorher), darf der naechste Emit den
    Callback nicht in das tote Widget laufen lassen (sonst native Access
    Violation). Der Guard prueft die Gueltigkeit und ueberspringt + meldet ab."""

    def test_guard_skips_and_unsubscribes_when_invalid(self):
        import src.core.sync as sync_mod

        class _FakeWidget:        # schwach referenzierbar, aber kein destroyed-Signal
            pass

        sync = StateSync()
        calls = []
        state = {"valid": True}
        orig = sync_mod._qt_is_valid
        sync_mod._qt_is_valid = lambda _w: state["valid"]
        fake = _FakeWidget()                  # starke Ref halten (Weakref im Guard)
        try:
            # Fake ohne destroyed-Pfad -> NUR der Guard schuetzt.
            sync.subscribe_widget(SyncEvent.PATCH_CHANGED, fake,
                                  lambda *_: calls.append(1))
            sync.emit(SyncEvent.PATCH_CHANGED)                 # gueltig -> feuert
            self.assertEqual(len(calls), 1)
            state["valid"] = False                            # Widget "stirbt"
            sync.emit(SyncEvent.PATCH_CHANGED)                # Guard -> skip
            self.assertEqual(len(calls), 1,
                             "Callback feuerte auf totem Widget (Guard wirkungslos)")
            self.assertEqual(sync._subscribers[SyncEvent.PATCH_CHANGED], [],
                             "toter Subscriber wurde nicht abgemeldet")
        finally:
            sync_mod._qt_is_valid = orig

    def test_live_widget_still_fires(self):
        from PySide6.QtWidgets import QApplication, QWidget
        _ = QApplication.instance() or QApplication([])
        sync = StateSync()
        calls = []
        w = QWidget()
        sync.subscribe_widget(SyncEvent.FUNCTION_CHANGED, w,
                              lambda *_: calls.append(1))
        sync.emit(SyncEvent.FUNCTION_CHANGED)
        sync.emit(SyncEvent.FUNCTION_CHANGED)
        self.assertEqual(len(calls), 2, "lebendes Widget muss normal beliefert werden")


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

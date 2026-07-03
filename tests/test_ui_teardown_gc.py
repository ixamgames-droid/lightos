"""GC-Teardown-Regression STAB-10 (Repo-Sweep nach STAB-09).

Zwei Crash-/Leak-Klassen (PySide6 6.11 / Python 3.14, empirisch verifiziert):

1. **Starke Kind->Owner-Referenzen**: Shibokens Parent->Kind-Wrapper-Kante ist
   GC-sichtbar — ein Kind-Widget mit starker Ref auf seinen Top-Level-Owner
   zykelt den Owner selbst dann, wenn KEIN Python-Container das Kind hält
   (Layout genügt). Der Owner stirbt dann nur in der ZYKLISCHEN GC; dealloziert
   die den Owner-Wrapper, läuft die Qt-Eltern-Kaskade mitten in der GC ->
   native Access Violation (faulthandler: "Garbage-collecting").
   Gefixt via weakref: ``EfxPopoutDialog._view``, ``AttributeSlider._owner``,
   ``_AspectRow._parent`` (vc_drop_panel).

2. **Lambda-Slots**: die C++-Connection hält Lambdas (und functools.partial!)
   STARK und GC-unsichtbar — ein self-fangendes Lambda pinnt den Wrapper von
   aussen (Leak + Use-after-free-Fenster, wenn das C++-Objekt via Kaskade
   stirbt). Gefixt via Bound-Method-Slots (bindet PySide6 schwach) bzw.
   ``src.ui.weak_slots.weak_slot``/``weak_slot_fwd``.
"""
import gc
import os
import types
import unittest
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget, QPushButton

from src.ui.weak_slots import weak_slot, weak_slot_fwd

_app = QApplication.instance() or QApplication([])


def _collect(n=3):
    for _ in range(n):
        gc.collect()


class WeakSlotHelperTest(unittest.TestCase):
    """Verhalten der weak_slot-Adapter (Basis des ganzen Sweeps)."""

    class _Recv(QWidget):
        def __init__(self):
            super().__init__()
            self.calls = []

        def on_it(self, *args):
            self.calls.append(args)

    def test_weak_slot_discards_signal_args(self):
        r = self._Recv()
        slot = weak_slot(r.on_it, "a", 1)
        slot("sig1", "sig2")            # Signal-Args muessen verworfen werden
        self.assertEqual(r.calls, [("a", 1)])

    def test_weak_slot_fwd_forwards_signal_args(self):
        r = self._Recv()
        slot = weak_slot_fwd(r.on_it, "key")
        slot(42)                        # Signal-Arg NACH den gebundenen Args
        self.assertEqual(r.calls, [("key", 42)])

    def test_dead_receiver_is_silent_noop(self):
        r = self._Recv()
        slot = weak_slot(r.on_it)
        ref = weakref.ref(r)
        del r
        _collect()
        self.assertIsNone(ref(), "Receiver haette sterben muessen")
        slot()                          # darf weder rufen noch werfen

    def test_receiver_is_not_pinned(self):
        """Der Adapter selbst darf den Receiver nicht am Leben halten —
        Refcount-Tod trotz lebender Slot-Funktion (gc.disable-Probe)."""
        r = self._Recv()
        slot = weak_slot(r.on_it)       # noqa: F841 — lebt weiter
        ref = weakref.ref(r)
        gc.disable()
        try:
            del r
            self.assertIsNone(ref(), "weak_slot pinnt den Receiver")
        finally:
            gc.enable()

    def test_qt_builtin_method_receiver(self):
        """Qt-Builtin-Methoden haben kein __func__ — der Fallback loest ueber
        den Methodennamen am lebenden Objekt auf."""
        w = QWidget()
        slot = weak_slot(w.setWindowTitle, "titel")
        slot("ignoriertes-signal-arg")
        self.assertEqual(w.windowTitle(), "titel")

    def test_connected_lambda_would_pin_but_weak_slot_does_not(self):
        """Kontrolle am echten Signal: weak_slot an einer C++-Connection
        pinnt den Receiver nicht (das Lambda-Aequivalent tat es — STAB-09)."""
        outer = QWidget()
        btn = QPushButton(outer)

        r = self._Recv()
        btn.clicked.connect(weak_slot(r.on_it, "x"))
        ref = weakref.ref(r)
        gc.disable()
        try:
            del r
            self.assertIsNone(
                ref(), "Connection + weak_slot pinnt den Receiver (Refcount)")
        finally:
            gc.enable()


class EfxPopoutCycleTest(unittest.TestCase):
    """EfxView <-> EfxPopoutDialog: der Popout darf die View nicht zykeln —
    die View (Owner-Wrapper) muss per REFCOUNT sterben (gc.disable-Probe).
    Auf dem ungefixten Stand (starkes ``EfxPopoutDialog._view``) beisst der
    Test: die View ueberlebt den del und landet erst in der zyklischen GC."""

    def test_view_with_open_popout_dies_by_refcount(self):
        from src.core import sync as sync_mod
        from src.core.app_state import get_state
        get_state()                     # Singletons wie in der App anlegen

        # subscribe_widget-Anker sind bewusst GC-bare SELBST-Zyklen (STAB-09)
        # und wuerden den Refcount-Tod hier verdecken -> fuer die Probe die
        # Subscription unterbinden (der try/except im View faengt das ab).
        real_get_sync = sync_mod.get_sync

        def _no_sync():
            raise RuntimeError("sync-anker fuer refcount-probe deaktiviert")

        sync_mod.get_sync = _no_sync
        try:
            from src.ui.views.efx_view import EfxView, EfxPopoutDialog
            gc.collect()
            gc.disable()
            try:
                view = EfxView()
                popout = EfxPopoutDialog(view, parent=view)
                view._popout = popout   # wie in EfxView._open_popout
                vref = weakref.ref(view)
                del view, popout
                self.assertIsNone(
                    vref(),
                    "EfxView haengt in einem Referenz-Zyklus (Popout haelt die "
                    "View stark?) -> Owner-Dealloc in der zyklischen GC = "
                    "native-AV-Risiko (STAB-09/-10)")
            finally:
                gc.enable()
                _collect()
        finally:
            sync_mod.get_sync = real_get_sync

    def test_popout_slots_are_none_guarded_after_view_death(self):
        """Die Popout-Adapter muessen nach dem Tod der View stille No-Ops
        sein (Teardown-Fenster: Signale koennen noch feuern)."""
        from src.core import sync as sync_mod
        from src.core.app_state import get_state
        get_state()
        real_get_sync = sync_mod.get_sync

        def _no_sync():
            raise RuntimeError("sync-anker fuer refcount-probe deaktiviert")

        sync_mod.get_sync = _no_sync
        try:
            from src.ui.views.efx_view import EfxView, EfxPopoutDialog
            view = EfxView()
            popout = EfxPopoutDialog(view)   # OHNE Qt-Parent: ueberlebt die View
            del view
            _collect()
            self.assertIsNone(popout._view, "View-weakref muesste tot sein")
            # Darf nicht werfen (None-Guards):
            popout._on_geom_spin("width", 10)
            popout._on_relationship_changed("spread", 0.5)
            popout._on_mode_combo_changed(0)
            popout.sync_from_model()
            popout.sync_relationship()
        finally:
            sync_mod.get_sync = real_get_sync


class AttributeSliderOwnerBackrefTest(unittest.TestCase):
    """AttributeSlider._owner (ProgrammerView) war eine STARKE Kind->Owner-Ref.
    Shibokens Parent->Kind-Kante macht daraus einen GC-Zyklus um den Owner —
    auch OHNE Python-Container (Layout genuegt). Nach dem weakref-Fix muss der
    Owner per Refcount sterben; auf dem ungefixten Stand beisst der Test."""

    class _OwnerStub(QWidget):
        # Duck-Typing wie ProgrammerView (AttributeSlider prueft per hasattr)
        def group_mode(self):
            return "linked"

        def active_fixture_index(self):
            return 0

    def test_slider_does_not_cycle_owner(self):
        from src.core.app_state import get_state
        from src.ui.views.programmer_view import AttributeSlider

        channel = types.SimpleNamespace(
            name="Dimmer", attribute="intensity", default_value=0)
        gc.collect()
        gc.disable()
        try:
            owner = self._OwnerStub()
            slider = AttributeSlider(channel, [], get_state(),
                                     owner=owner, parent=owner)
            self.assertIs(slider._owner, owner)   # weakref liefert den Owner
            oref = weakref.ref(owner)
            del owner, slider
            self.assertIsNone(
                oref(),
                "AttributeSlider._owner zykelt den Owner (starke Ref?) -> "
                "Owner-Dealloc in der zyklischen GC = native-AV-Risiko")
        finally:
            gc.enable()
            _collect()

    def test_slider_owner_none_after_owner_death(self):
        """Nach dem Tod des Owners liefert die Property None (Guards greifen)."""
        from src.core.app_state import get_state
        from src.ui.views.programmer_view import AttributeSlider

        channel = types.SimpleNamespace(
            name="Dimmer", attribute="intensity", default_value=0)
        owner = self._OwnerStub()
        slider = AttributeSlider(channel, [], get_state(), owner=owner)
        del owner
        _collect()
        self.assertIsNone(slider._owner)
        # Owner-abhaengige Pfade muessen auf Linked-Defaults zurueckfallen:
        self.assertEqual(slider._mode(), "linked")
        self.assertEqual(slider._active_index(), 0)


if __name__ == "__main__":
    unittest.main()

"""SDK-01: Simple Desk färbt die Fader nach Fixture (visuelle Gruppierung)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.app_state import get_state
from src.ui.views.simple_desk import SimpleDeskView

_app = QApplication.instance() or QApplication([])


class _F:
    def __init__(self, fid, universe, address, channel_count, label):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.label = label


class FaderTintTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: []      # Tooltip-Namen egal fuer den Test

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def test_tints_grouped_by_fixture(self):
        view = SimpleDeskView()
        view._universe = 1
        # 2 Fixtures je 4 Kanaele: CH 1-4 und CH 5-8 (Universe 1); CH 9+ frei.
        self.state._patch_cache = [
            _F(1, 1, 1, 4, "PAR 1"),
            _F(2, 1, 5, 4, "PAR 2"),
            _F(3, 2, 1, 4, "Other-Universe"),    # anderes Universe -> ignoriert
        ]
        view._apply_fixture_tints()

        # Kanaele 1-8 getintet, ab 9 neutral.
        self.assertNotEqual(view._faders[0].styleSheet(), "")   # CH1
        self.assertNotEqual(view._faders[3].styleSheet(), "")   # CH4
        self.assertNotEqual(view._faders[4].styleSheet(), "")   # CH5
        self.assertNotEqual(view._faders[7].styleSheet(), "")   # CH8
        self.assertEqual(view._faders[8].styleSheet(), "")      # CH9 frei

        # Verschiedene Fixtures -> verschiedene Farbe.
        self.assertNotEqual(view._faders[0].styleSheet(), view._faders[4].styleSheet())
        # Gleiche Fixture -> gleiche Farbe.
        self.assertEqual(view._faders[0].styleSheet(), view._faders[3].styleSheet())

    def test_reset_clears_tint(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [_F(1, 1, 1, 2, "X")]
        view._apply_fixture_tints()
        self.assertNotEqual(view._faders[0].styleSheet(), "")
        # Patch leeren -> erneut anwenden -> neutral
        self.state._patch_cache = []
        view._apply_fixture_tints()
        self.assertEqual(view._faders[0].styleSheet(), "")


if __name__ == "__main__":
    unittest.main()


class TintIsIdempotentTest(unittest.TestCase):
    """Patchen fror die Oberfläche 11–12 s ein (crash.log 03.07. + 10.07.).

    Die Kette: `add_fixture` → Patch-Signal → `_rebuild_overview` →
    `_apply_fixture_tints`. Dort wurden erst ALLE 512 Fader auf neutral
    zurückgesetzt und die gepatchten danach neu eingefärbt — für jeden
    gepatchten Kanal also zweimal ``setStyleSheet`` pro Aufruf, und
    ``setStyleSheet`` ist in Qt ein voller Style-Repolish.

    Gemessen (offscreen, 12 Geräte nacheinander gepatcht): 3510 ms → 55 ms.
    Zeit ist aber ein schlechter Test — festgenagelt wird darum der
    Mechanismus: ein Aufruf OHNE echte Änderung darf kein Widget anfassen.
    """

    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: []

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def _view(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [_F(1, 1, 1, 4, "PAR 1"), _F(2, 1, 5, 4, "PAR 2")]
        return view

    def _count_style_writes(self, view, fn):
        writes = []
        originals = []
        for f in view._faders:
            originals.append((f, f.setStyleSheet))
            f.setStyleSheet = (lambda *a, _f=f: writes.append(_f))  # type: ignore[assignment]
        try:
            fn()
        finally:
            for f, orig in originals:
                f.setStyleSheet = orig                 # type: ignore[assignment]
        return len(writes)

    def test_second_identical_pass_touches_no_widget(self):
        view = self._view()
        view._apply_fixture_tints()                    # Zielzustand herstellen
        again = self._count_style_writes(view, view._apply_fixture_tints)
        self.assertEqual(again, 0,
                         "ein Durchlauf ohne Aenderung darf kein setStyleSheet ausloesen")

    def test_a_real_change_still_gets_through(self):
        """Gegenprobe: der Guard darf echte Aenderungen nicht verschlucken."""
        view = self._view()
        view._apply_fixture_tints()
        self.state._patch_cache = [_F(1, 1, 1, 8, "PAR 1 breiter")]
        n = self._count_style_writes(view, view._apply_fixture_tints)
        self.assertGreater(n, 0, "geaenderter Patch muss die Faerbung nachziehen")

    def test_set_tint_with_same_color_is_a_noop(self):
        from PySide6.QtGui import QColor
        view = self._view()
        fader = view._faders[0]
        fader.set_tint(QColor("#1f6feb"))
        n = self._count_style_writes(view, lambda: fader.set_tint(QColor("#1f6feb")))
        self.assertEqual(n, 0)

    def test_set_tint_none_twice_is_a_noop(self):
        view = self._view()
        fader = view._faders[0]
        fader.set_tint(None)
        n = self._count_style_writes(view, lambda: fader.set_tint(None))
        self.assertEqual(n, 0)

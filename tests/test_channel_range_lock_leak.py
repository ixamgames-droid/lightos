"""RL-01: Range-Lock „entfernen" darf keinen Identitaets-Modifier zurücklassen.

Regression (Feature-Verifikations-Sweep 2026-07-09): ChannelRangeLockDialog._on_accept
nullte beim Entfernen eines Range-Locks nur range_min/range_max, statt den Eintrag zu
loeschen. Ein Modifier, der NUR wegen des Locks existierte (LINEAR, kein custom_lut),
blieb so als Identitaets-Eintrag (0-255) im geteilten ChannelModifierManager haengen —
funktional folgenlos (Identitaet), aber unnoetig und persistiert. Fix: den Eintrag ganz
entfernen, wenn er ausschliesslich der Range-Lock war; eine echte Kurve wird bewahrt.
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.channel_modifier import (
    ChannelModifier, ChannelModifierManager, CurveType)
from src.ui.widgets.channel_range_lock_dialog import ChannelRangeLockDialog

_app = QApplication.instance() or QApplication([])


class _FakeCombo:
    def __init__(self, data, enabled=True):
        self._data = data
        self._enabled = enabled

    def isEnabled(self):
        return self._enabled

    def currentData(self):
        return self._data


def _fake_dialog(mgr, combo_data):
    """Leichtes Fake-`self` fuer ChannelRangeLockDialog._on_accept (Muster wie
    test_viz10_stability): ein Kanal (CH1 -> DMX-Adresse 1), ein Combo."""
    return SimpleNamespace(
        _channels=[SimpleNamespace(channel_number=1, name="Gobo")],
        _combos=[_FakeCombo(combo_data)],
        _fixture=SimpleNamespace(universe=1, address=1, label="TestFix"),
        _mgr=mgr,
        accept=lambda: None,
    )


class RangeLockLeakTest(unittest.TestCase):
    def test_removing_lock_deletes_pure_rangelock_modifier(self):
        """Reiner Range-Lock (LINEAR, kein LUT) -> beim Entfernen ganz weg."""
        mgr = ChannelModifierManager()
        mgr.add(ChannelModifier(universe=1, address=1, name="lock",
                                curve=CurveType.LINEAR, range_min=10, range_max=200))
        fake = _fake_dialog(mgr, (0, 255))          # „kein Lock" gewaehlt
        ChannelRangeLockDialog._on_accept(fake)
        self.assertIsNone(mgr.get(1, 1),
                          "Identitaets-Modifier muss nach Lock-Entfernen weg sein")

    def test_removing_lock_keeps_real_curve(self):
        """Modifier mit ECHTER Kurve -> Range aufheben, Kurve behalten."""
        mgr = ChannelModifierManager()
        mgr.add(ChannelModifier(universe=1, address=1, name="curve",
                                curve=CurveType.INVERSE, range_min=10, range_max=200))
        fake = _fake_dialog(mgr, (0, 255))
        ChannelRangeLockDialog._on_accept(fake)
        m = mgr.get(1, 1)
        self.assertIsNotNone(m, "Modifier mit echter Kurve darf NICHT geloescht werden")
        self.assertEqual(m.curve, CurveType.INVERSE)
        self.assertEqual((m.range_min, m.range_max), (0, 255),
                         "Range muss auf 0-255 (kein Lock) zurueckgesetzt sein")

    def test_setting_lock_still_adds_modifier(self):
        """Regression: einen Lock SETZEN legt weiterhin einen Modifier an."""
        mgr = ChannelModifierManager()
        fake = _fake_dialog(mgr, (10, 200))         # Sub-Range gewaehlt
        ChannelRangeLockDialog._on_accept(fake)
        m = mgr.get(1, 1)
        self.assertIsNotNone(m)
        self.assertEqual((m.range_min, m.range_max), (10, 200))
        self.assertEqual(m.curve, CurveType.LINEAR)

    def test_removing_when_no_modifier_is_noop(self):
        """Kein Modifier + „kein Lock" gewaehlt -> nichts angelegt."""
        mgr = ChannelModifierManager()
        fake = _fake_dialog(mgr, (0, 255))
        ChannelRangeLockDialog._on_accept(fake)
        self.assertIsNone(mgr.get(1, 1))


if __name__ == "__main__":
    unittest.main()

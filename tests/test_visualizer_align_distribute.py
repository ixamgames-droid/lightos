"""Tests fuer Branch feature/stage-align-distribute (Audit-Paket 6).

Align/Distribute der ausgewaehlten Fixtures: die JS-Handler (jsAlignSelected /
jsDistributeSelected, operieren auf den bereits multi-selektierbaren
selectedFids) existierten, wurden aber nie angestossen (Signale nie emittiert,
keine UI). Neu: Toolbar-Button + Emitter alignSelected/distributeSelected +
Enable-Gating ab 2 selektierten Fixtures.

Reine Logik ueber Fake-self (kein echtes VisualizerWindow -> kein QtWebEngine).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class EmitTest(unittest.TestCase):
    def _fake_bridge(self, sink):
        return SimpleNamespace(
            alignSelected=SimpleNamespace(emit=lambda m: sink.append(("align", m))),
            distributeSelected=SimpleNamespace(emit=lambda a: sink.append(("dist", a))),
        )

    def test_emit_align_forwards_mode(self):
        sink = []
        fake = SimpleNamespace(_bridge=self._fake_bridge(sink))
        modes = ("left", "right", "front", "back", "center_x", "center_z")
        for m in modes:
            VW.VisualizerWindow._emit_align(fake, m)
        self.assertEqual(sink, [("align", m) for m in modes])

    def test_emit_distribute_forwards_axis(self):
        sink = []
        fake = SimpleNamespace(_bridge=self._fake_bridge(sink))
        VW.VisualizerWindow._emit_distribute(fake, "x")
        VW.VisualizerWindow._emit_distribute(fake, "z")
        self.assertEqual(sink, [("dist", "x"), ("dist", "z")])

    def test_emit_swallows_bridge_errors(self):
        # Defensiv: fehlendes Signal darf nicht crashen (try/except).
        fake = SimpleNamespace(_bridge=SimpleNamespace())
        VW.VisualizerWindow._emit_align(fake, "left")
        VW.VisualizerWindow._emit_distribute(fake, "x")


class EnableGatingTest(unittest.TestCase):
    def _fake(self):
        btn = SimpleNamespace(state=None)
        btn.setEnabled = lambda v: setattr(btn, "state", v)
        pl = MagicMock()
        pl.count.return_value = 0
        # VIZ-14: der Handler treibt jetzt auch die globale Auswahl -> _state + Guard.
        return SimpleNamespace(_btn_align=btn, _patch_list=pl,
                               _state=MagicMock(), _applying_selection=False), btn

    def test_enabled_with_two_or_more(self):
        fake, btn = self._fake()
        VW.VisualizerWindow._on_fixture_selection_from_js(fake, [1, 2, 3])
        self.assertTrue(btn.state)

    def test_disabled_with_one(self):
        fake, btn = self._fake()
        VW.VisualizerWindow._on_fixture_selection_from_js(fake, [1])
        self.assertFalse(btn.state)

    def test_disabled_when_empty(self):
        fake, btn = self._fake()
        VW.VisualizerWindow._on_fixture_selection_from_js(fake, [])
        self.assertFalse(btn.state)


if __name__ == "__main__":
    unittest.main()

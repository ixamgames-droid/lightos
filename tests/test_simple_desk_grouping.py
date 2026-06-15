"""SimpleDesk-Audit 2026-06-13: visuelle Zusammengehörigkeit + Kohärenz.

Deckt die neuen Bausteine ab:
- Header-Band-Geometrie (Balken sitzt exakt über den richtigen Fader-Spalten),
- Header-Band wird aus dem Patch befüllt (Span pro Fixture im aktuellen Universe),
- Klick in der Übersicht aktiviert die passenden Fader (fixture_activated),
- Universe-Kohärenz zwischen Fader-Combo und Übersichts-Filter,
- Sync-Timer pausiert, wenn der Tab versteckt ist,
- flash()/reveal greifen ohne Exceptions.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.app_state import get_state
from src.ui.views.simple_desk import (
    SimpleDeskView, FixtureHeaderBand,
    _FADER_MARGIN, _FADER_STRIDE, _FADER_W,
)

_app = QApplication.instance() or QApplication([])


class _F:
    def __init__(self, fid, universe, address, channel_count, label):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = channel_count
        self.label = label
        # Felder, die die Geräteübersicht liest:
        self.mode_name = "Mode"
        self.manufacturer_name = "Hersteller"
        self.fixture_name = "Modell"
        self.fixture_type = "par"


class HeaderBandGeometryTest(unittest.TestCase):
    def test_x_for_matches_fader_columns(self):
        band = FixtureHeaderBand()
        # Kanal 1 sitzt am linken Rand, jeder weitere Kanal eine Stride weiter.
        self.assertEqual(band._x_for(1), _FADER_MARGIN)
        self.assertEqual(band._x_for(2), _FADER_MARGIN + _FADER_STRIDE)
        self.assertEqual(band._x_for(10), _FADER_MARGIN + 9 * _FADER_STRIDE)

    def test_fixture_hit_test(self):
        band = FixtureHeaderBand()
        from PySide6.QtGui import QColor
        band.set_spans([(5, 4, QColor("#1f6feb"), "PAR")])  # CH 5..8
        # Mitte von Kanal 6 trifft das Fixture, Kanal 1 nicht.
        x_mid6 = band._x_for(6) + _FADER_W // 2
        x_ch1 = band._x_for(1) + _FADER_W // 2
        self.assertIsNotNone(band._fixture_at(x_mid6))
        self.assertIsNone(band._fixture_at(x_ch1))

    def test_click_emits_start_channel(self):
        band = FixtureHeaderBand()
        from PySide6.QtGui import QColor
        band.set_spans([(5, 4, QColor("#1f6feb"), "PAR")])
        got = []
        band.channel_clicked.connect(got.append)
        # _fixture_at über der Fixture-Region liefert den Span; Klick emittiert Start.
        hit = band._fixture_at(band._x_for(7))
        band.channel_clicked.emit(hit[0])
        self.assertEqual(got, [5])


class GroupingTest(unittest.TestCase):
    def setUp(self):
        self.state = get_state()
        self._orig_patch = self.state._patch_cache
        self._orig_gc = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: []

    def tearDown(self):
        self.state._patch_cache = self._orig_patch
        A.get_channels_for_patched = self._orig_gc

    def test_band_spans_built_for_current_universe(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [
            _F(1, 1, 1, 4, "PAR 1"),
            _F(2, 1, 5, 4, "PAR 2"),
            _F(3, 2, 1, 4, "Andere-Univ"),   # anderes Universe -> nicht im Band
        ]
        view._apply_fixture_tints()
        spans = view._header_band._spans
        starts = sorted(s[0] for s in spans)
        self.assertEqual(starts, [1, 5])               # nur Universe 1
        # Label landet im Span.
        labels = {s[0]: s[3] for s in spans}
        self.assertEqual(labels[1], "PAR 1")
        self.assertEqual(labels[5], "PAR 2")

    def test_band_span_clamped_to_512(self):
        view = SimpleDeskView()
        view._universe = 1
        # Fixture läuft über 512 hinaus -> Band-Breite wird begrenzt.
        self.state._patch_cache = [_F(1, 1, 510, 8, "Overflow")]
        view._apply_fixture_tints()
        span = view._header_band._spans[0]
        self.assertEqual(span[0], 510)
        self.assertEqual(span[1], 3)                   # 510,511,512

    def test_overview_click_activates_faders(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [_F(7, 1, 20, 3, "Spot")]
        view._rebuild_overview()
        revealed = []
        view._reveal_fixture = lambda a, c: revealed.append((a, c))
        # Top-Item der Übersicht simuliert anklicken.
        tree = view._overview._tree
        top = tree.topLevelItem(0)
        view._overview._on_item_clicked(top, 0)
        self.assertEqual(revealed, [(20, 3)])

    def test_universe_coherence_overview_follows_fader(self):
        view = SimpleDeskView()
        self.state._patch_cache = [
            _F(1, 1, 1, 4, "U1"),
            _F(2, 2, 1, 4, "U2"),
        ]
        view._rebuild_overview()
        # Filter bewusst auf Universe 1 -> beim Fader-Wechsel zieht er auf 2 nach.
        view._overview.set_universe_filter(1)
        view._uni_combo.setCurrentIndex(1)             # Universe 2
        self.assertEqual(view._overview._filter_universe, 2)

    def test_alle_filter_is_respected_on_universe_switch(self):
        view = SimpleDeskView()
        self.state._patch_cache = [
            _F(1, 1, 1, 4, "U1"),
            _F(2, 2, 1, 4, "U2"),
        ]
        view._rebuild_overview()
        view._overview.set_universe_filter(0)          # "Alle"
        view._uni_combo.setCurrentIndex(1)             # Universe 2
        self.assertEqual(view._overview._filter_universe, 0)   # bleibt "Alle"

    def test_reveal_and_flash_no_exception(self):
        view = SimpleDeskView()
        view._universe = 1
        self.state._patch_cache = [_F(1, 1, 1, 4, "PAR")]
        view._apply_fixture_tints()
        view._reveal_fixture(1, 4)                      # darf nicht werfen
        # flash setzt einen Hervorhebungs-Style auf den ersten Kanal.
        self.assertIn("ffd33d", view._faders[0].styleSheet())


class TimerVisibilityTest(unittest.TestCase):
    def test_timer_pauses_when_hidden(self):
        view = SimpleDeskView()
        self.assertTrue(view._sync_timer.isActive())
        view.show()
        _app.processEvents()
        self.assertTrue(view._sync_timer.isActive())
        view.hide()
        _app.processEvents()
        self.assertFalse(view._sync_timer.isActive())
        # Wieder einblenden -> Timer läuft erneut.
        view.show()
        _app.processEvents()
        self.assertTrue(view._sync_timer.isActive())
        view.hide()


if __name__ == "__main__":
    unittest.main()

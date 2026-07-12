"""Getrennt-Modus-Kopf-Slider: aktives Fixture per fid statt rohem Combo-Index.

Regression (Bug-Jagd Runde 2, 2026-07-12): Im Einzeln-Modus lieferte
AttributeSlider._active_index() den Combo-Index in die VOLLE Selektion, die
Kopf-Slider des Getrennt-Modus arbeiten aber auf einer GEFILTERTEN Teilmenge
(Fixtures ohne diesen Kopf fallen raus) -> der Wert landete auf dem falschen
Geraet bzw. der Slider zeigte den falschen Ist-Wert. Fix: fid-basiertes Mapping
(active_fixture_fid) in die lokale Liste; -1 wenn das aktive Fixture den Kopf
nicht besitzt (No-Op).
"""
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.ui.views.programmer_view import AttributeSlider, ProgrammerView


class ActiveIndexFidMappingTest(unittest.TestCase):
    def test_maps_by_fid_into_filtered_list(self):
        """Selektion [1(PAR),2,3], Kopf-Slider-owners gefiltert [2,3], aktiv fid=3:
        lokal muss Index 1 rauskommen (roher Combo-Index waere 2 = daneben)."""
        owner = SimpleNamespace(active_fixture_fid=lambda: 3)
        fake = SimpleNamespace(_owner=owner,
                               _fixtures=[SimpleNamespace(fid=2), SimpleNamespace(fid=3)])
        self.assertEqual(AttributeSlider._active_index(fake), 1)

    def test_active_fixture_without_head_returns_sentinel(self):
        """Aktives Fixture (PAR, fid=1) besitzt diesen Kopf nicht -> -1 (No-Op),
        nicht faelschlich ein anderes Geraet."""
        owner = SimpleNamespace(active_fixture_fid=lambda: 1)
        fake = SimpleNamespace(_owner=owner, _fixtures=[SimpleNamespace(fid=2)])
        self.assertEqual(AttributeSlider._active_index(fake), -1)

    def test_fallback_to_raw_index_without_fid_api(self):
        """Owner ohne active_fixture_fid (Fremd-Einbettung) -> alter Index-Pfad."""
        owner = SimpleNamespace(active_fixture_index=lambda: 1)
        fake = SimpleNamespace(_owner=owner,
                               _fixtures=[SimpleNamespace(fid=5), SimpleNamespace(fid=6)])
        self.assertEqual(AttributeSlider._active_index(fake), 1)

    def test_no_owner_returns_zero(self):
        fake = SimpleNamespace(_owner=None, _fixtures=[])
        self.assertEqual(AttributeSlider._active_index(fake), 0)


class ActiveFixtureFidTest(unittest.TestCase):
    def test_returns_fid_of_combo_selection(self):
        fake = SimpleNamespace(_combo_selected_fids=[7, 8, 9],
                               active_fixture_index=lambda: 2)
        self.assertEqual(ProgrammerView.active_fixture_fid(fake), 9)

    def test_returns_none_when_unknown(self):
        fake = SimpleNamespace(_combo_selected_fids=None,
                               active_fixture_index=lambda: 0)
        self.assertIsNone(ProgrammerView.active_fixture_fid(fake))
        fake2 = SimpleNamespace(_combo_selected_fids=[7],
                                active_fixture_index=lambda: 5)
        self.assertIsNone(ProgrammerView.active_fixture_fid(fake2))


if __name__ == "__main__":
    unittest.main()

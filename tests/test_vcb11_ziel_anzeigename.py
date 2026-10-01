"""VCB-11: die Liste „Blackout-Ziel" nennt Geraete beim Namen.

Das Patch-Modell heisst ``label`` (nicht ``name``); vorher stand jedes Geraet
als „Gerät: #9 [#9]" in der Auswahl.
"""
import unittest
from unittest import mock

from src.ui.virtualconsole import target_list_editor as tle


class _Fx:
    def __init__(self, fid, label):
        self.fid = fid
        self.label = label


class _State:
    def __init__(self, fixtures):
        self._fx = fixtures

    def get_patched_fixtures(self):
        return list(self._fx)

    def _session(self):  # Gruppen-Teil schlaegt fehl -> nur Geraete
        raise RuntimeError("keine DB im Test")


class ZielAnzeigenameTest(unittest.TestCase):
    def _choices(self, fixtures):
        with mock.patch("src.core.app_state.get_state", return_value=_State(fixtures)):
            return dict(tle._blackout_choices())

    def test_geraet_traegt_seinen_namen(self):
        c = self._choices([_Fx(9, "PAR links 1")])
        self.assertEqual(c["f:9"], "Gerät: PAR links 1  [#9]")

    def test_ohne_namen_bleibt_die_nummer(self):
        c = self._choices([_Fx(4, "")])
        self.assertEqual(c["f:4"], "Gerät: #4  [#4]")


if __name__ == "__main__":
    unittest.main()

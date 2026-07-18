"""A3D-15: Art-Net-Startuniversum-Spinbox verdrahtet — externe Universe einstellbar.

Vorher war `_spin_artnet_start_univ` komplett tot: `_apply_artnet` las sie nie,
`add_artnet` bekam kein `out_universe`, der Send-Pfad sendete hart `univ_num-1`.
Der Backend-Pfad (add_artnet(out_universe) -> _send_all) ist bereits durch
`test_external_universe_number.py` abgesichert; hier wird die UI-Verdrahtung des
Dialogs getestet: (a) `_apply_artnet` reicht die Spinbox durch, (b) persistiert
sie in universes.json, (c) Default (univ-1) -> None (abwaertskompatibel, nicht
persistiert), (d) die Spinbox folgt dem internen Universum bzw. einer bereits
gespeicherten Wahl (kein stiller Universe-0-Fehl-Apply / Ueberschreiben).
"""
import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.ui.widgets.output_config as oc


def _app():
    return QApplication.instance() or QApplication([])


class ArtnetStartUniverseWiringTest(unittest.TestCase):
    def setUp(self):
        _app()
        self._tmp = tempfile.mktemp(suffix="_universes.json")
        self._orig_path = oc._UNIV_CONFIG_PATH
        oc._UNIV_CONFIG_PATH = self._tmp
        self.dlg = oc.OutputConfigDialog()

    def tearDown(self):
        oc._UNIV_CONFIG_PATH = self._orig_path
        try:
            self.dlg.deleteLater()
        except Exception:
            pass
        try:
            os.remove(self._tmp)
        except OSError:
            pass

    def _spy_add_artnet(self):
        from src.core.app_state import get_state
        om = get_state().output_manager
        calls = []
        orig = om.add_artnet

        def spy(universe, target_ip="255.255.255.255", out_universe=None):
            calls.append({"universe": universe, "ip": target_ip,
                          "out_universe": out_universe})
        om.add_artnet = spy
        self.addCleanup(lambda: setattr(om, "add_artnet", orig))
        return calls

    def _rows(self):
        with open(self._tmp, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_apply_passes_explicit_out_universe_and_persists(self):
        calls = self._spy_add_artnet()
        self.dlg._check_artnet.setChecked(True)
        self.dlg._spin_artnet_univ.setValue(3)
        self.dlg._spin_artnet_start_univ.setValue(7)    # != univ-1 (2) -> explizit
        self.dlg._apply_artnet()
        self.assertTrue(calls, "add_artnet wurde nicht aufgerufen")
        self.assertEqual(calls[-1]["universe"], 3)
        self.assertEqual(calls[-1]["out_universe"], 7,
                         "Startuniversum-Spinbox wurde nicht an add_artnet durchgereicht")
        row = next(r for r in self._rows() if r["num"] == 3)
        self.assertEqual(row["out_universe"], 7)         # persistiert

    def test_apply_at_default_passes_none_and_omits_persist(self):
        calls = self._spy_add_artnet()
        self.dlg._check_artnet.setChecked(True)
        self.dlg._spin_artnet_univ.setValue(5)           # sync -> start-univ = 4 (univ-1)
        self.dlg._apply_artnet()
        self.assertIsNone(calls[-1]["out_universe"],
                          "Default (univ-1) muss None sein (Send-Pfad-Default), nicht explizit")
        row = next(r for r in self._rows() if r["num"] == 5)
        self.assertNotIn("out_universe", row,
                         "Default darf nicht als out_universe persistiert werden (leer = Default)")

    def test_start_univ_follows_internal_default(self):
        self.dlg._spin_artnet_univ.setValue(9)
        self.assertEqual(self.dlg._spin_artnet_start_univ.value(), 8)   # univ-1

    def test_start_univ_restores_persisted_choice(self):
        oc._save_universe_config([{"num": 6, "name": "U6", "output": "ArtNet",
                                   "patch": "", "out_universe": 42}])
        self.dlg._spin_artnet_univ.setValue(6)
        self.assertEqual(self.dlg._spin_artnet_start_univ.value(), 42,
                         "gespeicherte externe Universe wird beim Universumswechsel nicht gezeigt")

    def test_persist_output_unset_preserves_out_universe(self):
        # Review-Fund #1 (kritisch): das geteilte _persist_output darf eine per
        # Tabelle (OUT-03) gesetzte out_universe NICHT loeschen, wenn ein Caller
        # (sACN-/Enttec-„Übernehmen") es ohne Wert ruft. _UNSET = bewahren.
        oc._save_universe_config([{"num": 5, "name": "U5", "output": "sACN",
                                   "patch": "", "out_universe": 20}])
        oc._persist_output(5, "sACN", "")                 # OHNE out_universe -> bewahren
        self.assertEqual(self._rows()[0].get("out_universe"), 20,
                         "sACN-Übernehmen loeschte die per Tabelle gesetzte externe Universe")
        oc._persist_output(5, "sACN", "", out_universe=7)  # explizit setzen
        self.assertEqual(self._rows()[0].get("out_universe"), 7)
        oc._persist_output(5, "sACN", "", out_universe=None)  # explizit entfernen
        self.assertNotIn("out_universe", self._rows()[0])

    def test_apply_reloads_table_with_persisted_out_universe(self):
        # Review-Fund #2: nach „Übernehmen" muss die Universe-Tabelle die frisch
        # persistierte externe Universe zeigen, sonst ueberschreibt ein Tabellen-
        # Speichern sie aus der stalen (leeren) Ext-Zelle.
        self._spy_add_artnet()
        self.dlg._check_artnet.setChecked(True)
        self.dlg._spin_artnet_univ.setValue(3)
        self.dlg._spin_artnet_start_univ.setValue(7)
        self.dlg._apply_artnet()
        # Zeile fuer Universum 3 in der Tabelle finden, Ext-Spalte (4) pruefen.
        tbl = self.dlg._univ_table
        ext = None
        for r in range(tbl.rowCount()):
            if tbl.item(r, 0) and tbl.item(r, 0).text() == "3":
                ext = tbl.item(r, 4).text() if tbl.item(r, 4) else None
                break
        self.assertEqual(ext, "7",
                         "Tabelle zeigt die frisch persistierte externe Universe nicht")


if __name__ == "__main__":
    unittest.main()

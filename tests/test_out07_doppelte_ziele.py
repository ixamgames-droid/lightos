"""OUT-07: zwei Universen auf demselben Ziel werden gemeldet.

**Was bisher passierte:** die `#`-Spalte und das Feld für die externe
Universe-Nummer sind frei editierbar, und es gab **keine** Prüfung, ob zwei
Zeilen am Ende dorthin senden. Beide gingen dann auf dieselbe externe Nummer
desselben Adapters; der Empfänger bekommt abwechselnd zwei verschiedene Inhalte
und zeigt Flackern — **ohne dass irgendwo etwas gemeldet wird**. Dieselbe Klasse
wie A3D-33 (getippte Universe-Nummer ohne Range-Guard), nur eine Ebene höher.

**Warum nur gemeldet und nicht korrigiert:** welches der beiden Universen
gemeint war, weiß nur der Bediener. Automatisch umzunummerieren hieße zu raten
und im schlechtesten Fall das falsche Rig dunkel zu schalten.

Der Test prüft die **reine Funktion** `_doppelte_ziele` — kein Qt, kein Dialog.
Die Frage ist eine der Logik („kollidieren diese Zeilen?"), nicht der Oberfläche.
"""
from __future__ import annotations

import unittest

from src.ui.widgets.output_config import _doppelte_ziele


def _z(num, output="ArtNet", patch="10.0.0.5", out_universe=None):
    e = {"num": num, "name": f"U{num}", "output": output, "patch": patch}
    if out_universe is not None:
        e["out_universe"] = out_universe
    return e


class DoppelteZieleTest(unittest.TestCase):

    def test_saubere_konfiguration_meldet_nichts(self):
        rows = [_z(1), _z(2), _z(3)]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_zwei_zeilen_auf_derselben_externen_nummer(self):
        """Der Kernfall: verschiedene interne Nummern, gleiches externes Ziel."""
        rows = [_z(1, out_universe=5), _z(2, out_universe=5)]
        treffer = _doppelte_ziele(rows)
        self.assertEqual(len(treffer), 1)
        zeilen, was = treffer[0]
        self.assertIn("Zeile 1", zeilen)
        self.assertIn("Zeile 2", zeilen)
        self.assertIn("5", was)

    def test_default_der_externen_nummer_wird_mitgerechnet(self):
        """Fehlt `out_universe`, gilt `num - 1` — genau wie in `_send_all`.

        Ohne diese Regel bliebe die haeufigste Kollision unsichtbar: eine Zeile
        mit explizitem `out_universe`, eine ohne, die auf denselben Wert faellt.
        """
        rows = [_z(3), _z(9, out_universe=2)]      # 3-1 == 2
        self.assertEqual(len(_doppelte_ziele(rows)), 1)

    def test_verschiedene_ziele_kollidieren_nicht(self):
        rows = [_z(1, patch="10.0.0.5"), _z(1, patch="10.0.0.6")]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_verschiedene_adapter_kollidieren_nicht(self):
        """sACN und Art-Net auf derselben Nummer sind zwei getrennte Netze."""
        rows = [_z(1, output="ArtNet", patch=""), _z(1, output="sACN", patch="")]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_abgeschaltete_zeilen_kollidieren_mit_nichts(self):
        """`Disabled` sendet nicht — zwei davon sind keine Kollision, und eine
        abgeschaltete Zeile darf auch keine aktive melden."""
        rows = [_z(1, output="Disabled"), _z(1, output="Disabled"),
                _z(1, output="ArtNet")]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_drei_auf_demselben_ziel_sind_EIN_treffer(self):
        """Sonst bekaeme der Bediener drei Dialoge fuer einen Fehler."""
        rows = [_z(1, out_universe=7), _z(2, out_universe=7), _z(3, out_universe=7)]
        treffer = _doppelte_ziele(rows)
        self.assertEqual(len(treffer), 1)
        self.assertIn("Zeile 3", treffer[0][0])

    def test_zwei_getrennte_kollisionen_werden_beide_gemeldet(self):
        rows = [_z(1, out_universe=1), _z(2, out_universe=1),
                _z(3, patch="10.0.0.9", out_universe=4),
                _z(4, patch="10.0.0.9", out_universe=4)]
        self.assertEqual(len(_doppelte_ziele(rows)), 2)


if __name__ == "__main__":
    unittest.main()

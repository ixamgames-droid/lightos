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
        """Fehlt `out_universe`, gilt bei **Art-Net** `num - 1` — wie in `_send_all`.

        Ohne diese Regel bliebe die haeufigste Kollision unsichtbar: eine Zeile
        mit explizitem `out_universe`, eine ohne, die auf denselben Wert faellt.
        """
        rows = [_z(3), _z(9, out_universe=2)]      # Art-Net: 3-1 == 2
        self.assertEqual(len(_doppelte_ziele(rows)), 1)


# ── Die Defaults sind je Protokoll VERSCHIEDEN (CDX, Codex zu PR #570) ───────
#
# Die erste Fassung rechnete fuer jeden Adaptertyp `num - 1`, und der Docstring
# behauptete ausdruecklich, „genau so rechnet auch `OutputManager._send_all`".
# Das stimmte nur fuer Art-Net. Nachgemessen am Sende-Pfad
# (`output_manager.py`, `_send_all`):
#
#     artnet.send_dmx(ext if ext is not None else univ_num - 1, data)
#     sacn.send_dmx(  ext if ext is not None else univ_num,     data)
#
# Die Behauptung wurde also aufgeschrieben, ohne sie an der Stelle nachzusehen,
# auf die sie sich beruft — dieselbe Klasse wie der Shim, der still `undefined`
# lieferte: es sah richtig aus und war nie geprueft.

class SacnDefaultTest(unittest.TestCase):
    """sACN zaehlt ab 1, Art-Net ab 0 — beides muss der Schluessel treffen."""

    def test_sacn_default_ist_num_nicht_num_minus_1(self):
        """Der Falsch-NEGATIV-Fall: eine echte Kollision blieb stumm.

        sACN-Zeile 1 ohne Angabe geht real auf Universum **1**; Zeile 2 mit
        ausdruecklicher 1 ebenfalls. Mit `num - 1` bekamen sie die Schluessel 0
        und 1 — kein Treffer, obwohl beide auf dasselbe senden.
        """
        rows = [_z(1, output="sACN", patch="10.0.0.5"),
                _z(2, output="sACN", patch="10.0.0.5", out_universe=1)]
        treffer = _doppelte_ziele(rows)
        self.assertEqual(len(treffer), 1, "echte sACN-Kollision nicht gemeldet")
        self.assertIn("Universum 1", treffer[0][1])

    def test_sacn_meldet_keinen_fehlalarm(self):
        """Der Falsch-POSITIV-Fall aus derselben Verwechslung.

        sACN-Zeile 2 ohne Angabe geht real auf 2, Zeile 3 mit ausdruecklicher 1
        auf 1. Mit `num - 1` ergaben beide den Schluessel 1 — ein Dialog fuer
        eine Kollision, die es nicht gibt. Ein Warnhinweis, der bei sauberer
        Konfiguration erscheint, wird als Erstes weggeklickt und dann auch dann,
        wenn er recht hat.
        """
        rows = [_z(2, output="sACN", patch="10.0.0.5"),
                _z(3, output="sACN", patch="10.0.0.5", out_universe=1)]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_artnet_bleibt_bei_num_minus_1(self):
        """Gegenprobe: der Art-Net-Default darf durch den Fix nicht verrutschen."""
        rows = [_z(1, output="ArtNet", patch="10.0.0.5"),
                _z(2, output="ArtNet", patch="10.0.0.5", out_universe=0)]
        self.assertEqual(len(_doppelte_ziele(rows)), 1)


class ZielAufloesungTest(unittest.TestCase):
    """Auch das ZIEL braucht die Default-Aufloesung, nicht den Rohtext."""

    def test_artnet_leer_ist_dasselbe_wie_ausgeschriebener_broadcast(self):
        """`apply_output_config` setzt `patch or "255.255.255.255"`.

        Ein leeres Feld und die ausgeschriebene Adresse sind derselbe Ort. Der
        Vergleich der Rohtexte liess genau dieses Paar durch.
        """
        rows = [_z(1, output="ArtNet", patch="", out_universe=3),
                _z(2, output="ArtNet", patch="255.255.255.255", out_universe=3)]
        self.assertEqual(len(_doppelte_ziele(rows)), 1)

    def test_sacn_leer_ist_die_MULTICAST_ADRESSE_dieses_universums(self):
        """★ Dieser Test stand hier vorher mit der GEGENTEILIGEN Aussage.

        Er hiess `…_und_nicht_gleich_einer_unicast_ip` und behauptete, ein
        leeres sACN-Ziel sei etwas anderes als ein ausgeschriebenes
        `239.255.0.3`. **Das ist falsch:** `SACNSender._dest()` rechnet fuer ein
        leeres Ziel `239.255.<hi>.<lo>` — bei Universum 3 also genau diese
        Adresse. Beide Zeilen senden an denselben Ort und Port.

        Aufgefallen ist es Codex (CDX-47, zu PR #574). Die erste Fassung setzte
        als Ziel den festen Text `"<Multicast>"` — sie hat den Default
        **benannt statt ausgerechnet**, und ein Name kann nicht kollidieren.
        *Damit stand die falsche Behauptung im Code UND im Gate: der Test hat
        den Fehler nicht uebersehen, er hat ihn festgeschrieben.*
        """
        rows = [_z(1, output="sACN", patch="", out_universe=3),
                _z(2, output="sACN", patch="239.255.0.3", out_universe=3)]
        treffer = _doppelte_ziele(rows)
        self.assertEqual(len(treffer), 1,
                         "leeres sACN-Ziel und die ausgeschriebene "
                         "Multicast-Adresse desselben Universums kollidieren")
        self.assertIn("239.255.0.3", treffer[0][1])

    def test_sacn_leer_kollidiert_nicht_mit_einer_echten_unicast_ip(self):
        """Die Gegenprobe, die der alte Test eigentlich sein wollte.

        Ein leeres Feld heisst Multicast; eine ausgeschriebene Unicast-Adresse
        ist ein anderer Ort. Nur muss man dafuer eine Adresse nehmen, die NICHT
        zufaellig der Multicast-Adresse dieses Universums entspricht.
        """
        rows = [_z(1, output="sACN", patch="", out_universe=3),
                _z(2, output="sACN", patch="10.0.0.7", out_universe=3)]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_zwei_leere_sacn_zeilen_auf_verschiedenen_universen(self):
        """Multicast ist NICHT ein Ziel, sondern eines je Universum.

        Beide Zeilen sind leer — mit einem festen Platzhalter als Ziel haetten
        sie denselben Schluessel bekommen und waeren nur deshalb nicht gemeldet
        worden, weil ihre Universe-Nummern verschieden sind. Hier zaehlt, dass
        auch das ZIEL verschieden ist.
        """
        rows = [_z(1, output="sACN", patch="", out_universe=3),
                _z(2, output="sACN", patch="", out_universe=4)]
        self.assertEqual(_doppelte_ziele(rows), [])
        # ... und mit gleicher Nummer kollidieren sie sehr wohl.
        rows = [_z(1, output="sACN", patch="", out_universe=3),
                _z(2, output="sACN", patch="", out_universe=3)]
        self.assertEqual(len(_doppelte_ziele(rows)), 1)


class EnttecPortTest(unittest.TestCase):
    """Enttec hat gar keine externe Nummer — der Port IST das Ziel.

    `_send_all` ruft `enttec.send_dmx(data)` ohne Universum. Zwei Zeilen auf
    demselben Port schreiben also zwangslaeufig auf dieselbe Leitung, ganz
    gleich, welche internen Nummern sie tragen. Die erste Fassung rechnete auch
    hier `num - 1` in den Schluessel und meldete deshalb **nie** etwas — der
    handgreiflichste Fall von allen (ein Stecker, zwei Absender) war der
    einzige, der garantiert unsichtbar blieb.
    """

    def test_zwei_zeilen_auf_demselben_port_kollidieren_immer(self):
        rows = [_z(1, output="Enttec", patch="/dev/ttyUSB0"),
                _z(2, output="Enttec", patch="/dev/ttyUSB0")]
        self.assertEqual(len(_doppelte_ziele(rows)), 1)

    def test_verschiedene_ports_kollidieren_nicht(self):
        rows = [_z(1, output="Enttec", patch="/dev/ttyUSB0"),
                _z(2, output="Enttec", patch="/dev/ttyUSB1")]
        self.assertEqual(_doppelte_ziele(rows), [])

    def test_meldung_erfindet_keine_externe_nummer(self):
        """„externes Universum None" waere schlechter als gar keine Angabe."""
        rows = [_z(1, output="Enttec", patch="/dev/ttyUSB0"),
                _z(2, output="Enttec", patch="/dev/ttyUSB0")]
        _, was = _doppelte_ziele(rows)[0]
        self.assertNotIn("None", was)
        self.assertNotIn("externes Universum", was)
        self.assertIn("/dev/ttyUSB0", was)

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

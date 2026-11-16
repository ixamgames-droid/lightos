"""CDX-75 (Nachbesserung): eine alte Kanal-Kopplung (MappedChannelChange) mit
Ziel ``laser_twist#1`` (SH-LASER3W, Pattern A vertikal) trifft nach der
Lade-Migration NUR Pattern A vertikal — dasselbe Muster wie der VC-Fader.

Die Migration (LAS-47) benennt das Ziel in den Basis-Schluessel
``laser_twist_y`` um; ``MappedChannelChange.write`` spiegelt einen
Basis-Schluessel auf jeden weiteren Kopf (``laser_twist_y#1`` = Pattern B
vertikal). Vor LAS-28 war ``laser_twist#1`` ein exakter Schluessel: B
vertikal blieb unberuehrt. Jetzt traegt die Regel ``nur_kopf0``.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import get_state
from src.core.engine.mapped_channel import MappedRule
from src.core.show import show_file as SF
from src.core.show.las28_ziele import funktionen_nachziehen

import test_las47_laser_twist_ziele as L47
from test_las47_laser_twist_ziele import KANAL, _laden, _mapping


class Cdx75Kopf1Kopplung(unittest.TestCase):
    # Bibliothek/Patch-Aufbau aus LAS-47 uebernehmen, ohne dessen Tests
    # mitzusammeln.
    setUpClass = classmethod(L47.Las47Ziele.setUpClass.__func__)
    tearDownClass = classmethod(L47.Las47Ziele.tearDownClass.__func__)
    _patch = L47.Las47Ziele._patch
    _show = L47.Las47Ziele._show
    _fm = L47.Las47Ziele._fm

    def _schreiben(self, quelle_tilt=200):
        st = get_state()
        m = self._fm().get(8)
        u = st.universes[1]
        for k in KANAL.values():
            u.set_channel(k, 0)
        m._read_source = lambda *a, **k: quelle_tilt
        m._running = True
        m.write(st.universes, list(st.get_patched_fixtures()), 0.02)
        return {n: u.get_channel(k) for n, k in KANAL.items()}

    def test_cdx75_migration_markiert_die_regel(self):
        _laden(self._show([_mapping(ziel="laser_twist#1"),
                           _mapping(fid=9, ziel="laser_twist#3")]))
        r = self._fm().get(8).rules[0]
        self.assertEqual(r.target, "laser_twist_y")
        self.assertTrue(r.nur_kopf0)
        self.assertIs(r.to_dict().get("nur_kopf0"), True)
        # #3 -> laser_twist_y#1 ist exakt: keine Markierung, Datei wie bisher
        r3 = self._fm().get(9).rules[0]
        self.assertFalse(r3.nur_kopf0)
        self.assertNotIn("nur_kopf0", r3.to_dict())
        # zweiter Lauf: unveraendert
        funktionen_nachziehen(self._fm(), {1}, True, set())
        self.assertEqual(len(self._fm().get(8).rules), 1)
        self.assertTrue(self._fm().get(8).rules[0].nur_kopf0)

    def test_cdx75_kopplung_bewegt_b_vertikal_nicht_mit(self):
        _laden(self._show([_mapping(ziel="laser_twist#1")]))
        werte = self._schreiben()
        self.assertEqual(werte["Pattern A Vertical Flip"], 200)
        self.assertEqual(werte["Pattern B Vertical Flip"], 0,
                         "Kopplung auf A vertikal zieht B vertikal mit")
        self.assertEqual(werte["Pattern B Horizontal Flip"], 0)

    def test_cdx75_speichern_und_neu_laden_behaelt_die_markierung(self):
        import json
        _laden(self._show([_mapping(ziel="laser_twist#1")]))
        daten = SF._show_daten(get_state(), [])
        for mit_marker in (True, False):
            dd = json.loads(json.dumps(daten, default=str))
            if not mit_marker:
                dd.pop("attribut_migrationen", None)
            _laden(dd)
            r = self._fm().get(8).rules[0]
            self.assertEqual(r.target, "laser_twist_y")
            self.assertTrue(r.nur_kopf0)

    def test_cdx75_neue_regel_auf_laser_twist_y_bleibt_geraeteweit(self):
        _laden(self._show([_mapping(ziel="laser_twist_y")]))
        werte = self._schreiben(quelle_tilt=90)
        self.assertEqual(werte["Pattern A Vertical Flip"], 90)
        self.assertEqual(werte["Pattern B Vertical Flip"], 90)

    def test_cdx75_regel_ohne_feld_bleibt_byte_gleich(self):
        d = MappedRule(target="laser_twist_y").to_dict()
        self.assertNotIn("nur_kopf0", d)
        self.assertEqual(MappedRule.from_dict(d).to_dict(), d)


if __name__ == "__main__":
    unittest.main()

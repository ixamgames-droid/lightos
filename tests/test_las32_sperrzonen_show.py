"""LAS-32 (S1): Sperrzonen in der Show-Datei.

Eigener Abschnitt ``sperrzonen`` mit eigener Versionsnummer — kein Knoten im
Szenengraph (ein aelterer Programmstand macht aus einer unbekannten Knotenart
beim Speichern ein Geraet). Geprueft am echten ``save_show``/``load_show``.
"""
import json
import os
import shutil
import tempfile
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.show.show_file as SF
from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import LaserFeld, Sperrzone, SperrzonenDaten


def _show_json(pfad):
    with zipfile.ZipFile(pfad, "r") as zf:
        return json.loads(zf.read("show.json").decode("utf-8"))


def _schreibe(pfad, data):
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(data, indent=2, ensure_ascii=False))


class SperrzonenShowTest(unittest.TestCase):
    def setUp(self):
        from src.core.app_state import get_state
        self.st = get_state()
        SF.reset_show()
        self.tmp = tempfile.mkdtemp(prefix="las32_")
        self.pfad = os.path.join(self.tmp, "t.lshow")

    def tearDown(self):
        SF.reset_show()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fuelle(self):
        self.st.sperrzonen.zonen.append(Sperrzone(
            id="z1", name="Publikum", x=1.0, y=0.0, z=6.5,
            breite=8.0, hoehe=3.0, tiefe=5.0, dreh_y=15.0))
        self.st.sperrzonen.zonen.append(Sperrzone(id="z2", name="Bar"))
        self.st.sperrzonen.setze_feld(7, LaserFeld(links=12, rechts=20, oben=5,
                                                   unten=25, zuschlag=4))

    def test_frischer_state_hat_leeren_bestand(self):
        self.assertIsInstance(self.st.sperrzonen, SperrzonenDaten)
        self.assertTrue(self.st.sperrzonen.ist_leer())

    def test_speichern_und_laden(self):
        self._fuelle()
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        self.assertEqual(data["sperrzonen"]["version"], S.SPERRZONEN_VERSION)
        self.assertEqual([z["name"] for z in data["sperrzonen"]["zonen"]],
                         ["Publikum", "Bar"])
        SF.reset_show()
        self.assertTrue(self.st.sperrzonen.ist_leer())
        ok, _msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        z = self.st.sperrzonen.zone("z1")
        self.assertEqual((z.name, z.x, z.y, z.z, z.breite, z.hoehe, z.tiefe, z.dreh_y),
                         ("Publikum", 1.0, 0.0, 6.5, 8.0, 3.0, 5.0, 15.0))
        f = self.st.sperrzonen.feld(7)
        self.assertEqual((f.links, f.rechts, f.oben, f.unten, f.zuschlag),
                         (12.0, 20.0, 5.0, 25.0, 4.0))
        self.assertEqual(SF.letzte_ladeprobleme(), [])

    def test_zonen_sind_kein_knoten_im_szenengraph(self):
        self._fuelle()
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        graph = json.dumps(data.get("scene_graph", {}))
        self.assertNotIn("Publikum", graph)
        self.assertNotIn("sperrzone", graph.lower())
        self.assertNotIn("sperrzone", json.dumps(data.get("visualizer", {})).lower())

    def test_show_ohne_zonen_schreibt_keinen_abschnitt(self):
        SF.save_show(self.pfad)
        self.assertNotIn("sperrzonen", _show_json(self.pfad))

    def test_alt_show_ohne_abschnitt_laedt_unveraendert(self):
        # Einmal durch laden/speichern, damit der Vergleich nur noch misst, was
        # ein weiterer Durchgang aendert (der Lader ergaenzt Vorgabefelder).
        erste = os.path.join(self.tmp, "t0.lshow")
        SF.save_show(erste)
        SF.load_show(erste)
        SF.save_show(self.pfad)
        vorher = _show_json(self.pfad)
        self.assertNotIn("sperrzonen", vorher)
        ok, _msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertEqual(SF.letzte_ladeprobleme(), [])
        self.assertTrue(self.st.sperrzonen.ist_leer())
        zweite = os.path.join(self.tmp, "t2.lshow")
        SF.save_show(zweite)
        self.assertEqual(_show_json(zweite), vorher)

    def test_laden_einer_show_ohne_abschnitt_raeumt_alte_zonen_ab(self):
        SF.save_show(self.pfad)          # Show OHNE Zonen
        self._fuelle()                   # danach liegen Zonen im Speicher
        ok, _msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertTrue(self.st.sperrzonen.ist_leer(),
                        "Zonen der vorigen Show duerfen nicht stehen bleiben")
        kopf, befunde = S.state_befunde(self.st)
        self.assertEqual(befunde, [])
        self.assertNotIn("Sperrzonen:", kopf)

    def test_aenderung_an_zonen_zaehlt_als_ungespeichert(self):
        SF.save_show(self.pfad)
        SF.merke_show_stand(self.st)
        self.assertFalse(SF.show_hat_aenderungen(self.st))
        self._fuelle()
        self.assertTrue(SF.show_hat_aenderungen(self.st))

    def test_kaputte_zone_kostet_nur_sich_selbst(self):
        self._fuelle()
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        data["sperrzonen"]["zonen"].insert(1, "kaputt")
        data["sperrzonen"]["laser_felder"]["x"] = {"links": 1}
        _schreibe(self.pfad, data)
        SF.reset_show()
        ok, msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertEqual([z.name for z in self.st.sperrzonen.zonen], ["Publikum", "Bar"])
        probleme = SF.letzte_ladeprobleme()
        self.assertEqual(len(probleme), 2, probleme)
        self.assertIn("ABER", msg)

    def test_unlesbarer_abschnitt_wird_gemeldet(self):
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        data["sperrzonen"] = [1, 2, 3]
        _schreibe(self.pfad, data)
        ok, _msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertTrue(self.st.sperrzonen.zonen == [])
        self.assertTrue(any("Sperrzonen" in p for p in SF.letzte_ladeprobleme()))

    def test_abschnitt_aus_neuerem_stand_wird_nicht_gedeutet_aber_bewahrt(self):
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        neu = {"version": S.SPERRZONEN_VERSION + 1,
               "zonen": [{"id": "a", "name": "Publikum", "form": "polygon"}],
               "neues_feld": {"x": 1}}
        data["sperrzonen"] = neu
        _schreibe(self.pfad, data)
        ok, _msg = SF.load_show(self.pfad)
        self.assertTrue(ok)
        self.assertEqual(self.st.sperrzonen.zonen, [])
        self.assertTrue(any("neueren Programmstand" in p
                            for p in SF.letzte_ladeprobleme()))
        kopf, befunde = S.state_befunde(self.st)
        self.assertEqual(befunde, [])
        self.assertIn("neueren Programmstand", kopf)
        zweite = os.path.join(self.tmp, "t2.lshow")
        SF.save_show(zweite)
        self.assertEqual(_show_json(zweite)["sperrzonen"], neu)

    def test_zuschlag_null_in_der_datei_wird_zum_minimum(self):
        self._fuelle()
        SF.save_show(self.pfad)
        data = _show_json(self.pfad)
        data["sperrzonen"]["laser_felder"]["7"]["zuschlag"] = 0
        _schreibe(self.pfad, data)
        SF.load_show(self.pfad)
        self.assertEqual(self.st.sperrzonen.feld(7).zuschlag, S.ZUSCHLAG_MIN)

    def test_doppelte_zonen_id_wird_entschaerft(self):
        daten, _p = S.daten_aus_abschnitt({"version": 1, "zonen": [
            {"id": "a", "name": "A"}, {"id": "a", "name": "B"}]})
        self.assertEqual(len({z.id for z in daten.zonen}), 2)


if __name__ == "__main__":
    unittest.main()

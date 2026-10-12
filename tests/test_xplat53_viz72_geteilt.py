"""XPLAT-53: ``test_viz72_spot_pool_umgebung.py`` ist in drei Dateien geteilt.

**Der Befund** (Nebenbefund aus XPLAT-36, 11.10.2026): die Datei brauchte in
der Windows-ARM64-CI 186 / 217 / 237 / 287 s — bei 300 s Segmentlimit, und
damit knapper als jede andere WebEngine-Datei. Sie baut je Test eine frische
Seite (20 Szenen-Tests); eine geteilte Seite käme nicht ohne echten Reset je
Test aus. Geteilt ist deshalb die DATEI, nicht die Seite:

* ``test_viz72_spot_pool_umgebung.py``           Stufen und Vergabe + Quelltext
* ``test_viz72b_spot_pool_bewegung_scene.py``    Wellen, Lauflicht, Verteilung, Blackout, 2D
* ``test_viz72c_umgebung_modi_scene.py``         Umgebung und Modi
* ``_viz72_szene.py``                            gemeinsames Gerüst (keine Tests)

Gemessen unter Gate-Last (Windows x64): vorher 134 s, jetzt 55 / 43 / 47 s.

**Was hier bewacht wird** — die Stellen, an denen eine Teilung still kaputtgeht:

1. Kein Test ist verloren gegangen oder doppelt (die 23 Namen von vorher).
2. Jede Testdatei nennt und importiert die WebEngine-Ansicht SELBST. Daran
   hängen zwei Mechanismen, die nur den Text bzw. den Namensraum der TESTDATEI
   ansehen: der Segment-Runner sortiert sie in die serielle WebEngine-Spur,
   und ``conftest`` schaltet die Exit-Härtung scharf. Wandert der Import ganz
   ins Gerüst, läuft die Datei in der parallelen Spur — das fällt erst als
   sporadischer Absturz auf.

   (Der Klassenname steht in DIESER Datei absichtlich nirgends am Stück: der
   Runner sucht genau dieses Wort, und ein reiner Quelltext-Test gehört nicht
   in die serielle Spur.)
3. Jede Testdatei räumt ihre Fenster selbst ab (XPLAT-15).
4. Keine der drei wächst wieder an die Grenze.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TEILE = (
    "test_viz72_spot_pool_umgebung.py",
    "test_viz72b_spot_pool_bewegung_scene.py",
    "test_viz72c_umgebung_modi_scene.py",
)
GERUEST = "_viz72_szene.py"
BASIS = "Viz72SzeneBasis"
# Zusammengesetzt, damit diese Datei das Wort nicht enthaelt (s. Docstring).
ANSICHT = "QWeb" + "EngineView"

# Die Tests der ungeteilten Datei (Stand main 669d17c6).
ERWARTET = frozenset("""
test_lichterzahl_ist_konstant_und_haengt_an_der_stufe
test_kleines_rig_behaelt_ein_licht_je_geraet
test_stufen_niedrig_und_maximal
test_stufe_maximal
test_pool_vergibt_an_die_hellsten
test_dunkler_halter_behaelt_platz_bis_er_gebraucht_wird
test_vergabe_rein
test_vergabe_rein_bremsen
test_welle_laesst_die_lichter_stehen
test_langsame_welle_schattendurchlaeufe_gedeckelt
test_lauflicht_folgt_den_lichtern
test_gleich_hell_raeumlich_verteilt
test_blackout_grosses_rig
test_pool_in_der_2d_ansicht
test_umgebung_im_ansehen_modus_zusammengefasst
test_bauen_modus_zeigt_einzelobjekte_und_rueckweg
test_moduswechsel_baut_nicht_neu
test_farbaenderung_im_ansehen_modus_baut_neu
test_aenderung_im_ansehen_modus_baut_neu
test_picking_und_andocken_unberuehrt
test_geraete_spot_nicht_mehr_in_der_szene
test_render_closure_vergibt_vor_den_schatten
test_stufentabelle_echte_lichter
""".split())

# Rund 14 s je Szenen-Test in der Windows-ARM64-CI (287 s / 20 Tests). Zehn
# Tests sind damit etwa die halbe Grenze — wer darueber kommt, teilt weiter.
MAX_SZENEN_TESTS = 10


def _baum(name: str) -> ast.Module:
    return ast.parse((TESTS / name).read_text(encoding="utf-8"))


def _klassen(baum: ast.Module):
    """``[(klassenname, basisnamen, [testnamen])]``."""
    aus = []
    for knoten in baum.body:
        if isinstance(knoten, ast.ClassDef):
            basen = [getattr(b, "id", getattr(b, "attr", "")) for b in knoten.bases]
            tests = [g.name for g in knoten.body
                     if isinstance(g, ast.FunctionDef) and g.name.startswith("test_")]
            aus.append((knoten.name, basen, tests))
    return aus


class Viz72GeteiltTest(unittest.TestCase):

    def test_alle_teile_sind_da(self):
        for name in TEILE + (GERUEST,):
            self.assertTrue((TESTS / name).is_file(), f"{name} fehlt")

    def test_kein_test_verloren_keiner_doppelt(self):
        gefunden: list[str] = []
        for name in TEILE:
            for _klasse, _basen, tests in _klassen(_baum(name)):
                gefunden.extend(tests)
        self.assertEqual(sorted(gefunden), sorted(set(gefunden)), "ein Test steht doppelt")
        self.assertEqual(ERWARTET - set(gefunden), set(), "Tests der alten Datei fehlen")

    def test_geruest_hat_keine_tests_aber_die_basis(self):
        baum = _baum(GERUEST)
        klassen = _klassen(baum)
        self.assertIn(BASIS, [k for k, _b, _t in klassen])
        self.assertEqual([t for _k, _b, tests in klassen for t in tests], [])
        self.assertFalse(GERUEST.startswith("test_"),
                         "das Geruest darf pytest nicht als Testdatei einsammeln")

    def test_jede_testdatei_importiert_die_webengine_ansicht_selbst(self):
        for name in TEILE:
            with self.subTest(datei=name):
                text = (TESTS / name).read_text(encoding="utf-8")
                # (a) der Text, nach dem der Segment-Runner sucht
                self.assertIn(ANSICHT, text,
                              "ohne das Wort laeuft die Datei in der PARALLELEN Spur")
                # (b) der Name im Modul, nach dem conftest fragt (hasattr)
                importiert = [
                    alias.asname or alias.name
                    for knoten in _baum(name).body if isinstance(knoten, ast.ImportFrom)
                    and (knoten.module or "").endswith("QtWebEngineWidgets")
                    for alias in knoten.names]
                self.assertIn(ANSICHT, importiert,
                              "conftest erkennt das Modul nur an diesem Namen "
                              "im Modul selbst (Exit-Haertung)")

    def test_jede_testdatei_raeumt_ihre_fenster_ab(self):
        for name in TEILE:
            with self.subTest(datei=name):
                funktionen = {k.name: k for k in _baum(name).body
                              if isinstance(k, ast.FunctionDef)}
                self.assertIn("_xplat15_no_leaked_widgets", funktionen)
                quelle = ast.unparse(funktionen["_xplat15_no_leaked_widgets"])
                self.assertIn("autouse=True", quelle)
                self.assertIn("destroy_all_top_level_widgets", quelle)

    def test_dieser_waechter_laeuft_nicht_in_der_webengine_spur(self):
        self.assertNotIn(ANSICHT, Path(__file__).read_text(encoding="utf-8"))

    def test_szenen_tests_haengen_an_der_basis(self):
        for name in TEILE:
            with self.subTest(datei=name):
                szene = [(k, t) for k, basen, t in _klassen(_baum(name)) if BASIS in basen]
                self.assertTrue(szene, "keine Klasse erbt vom gemeinsamen Geruest")

    def test_keine_datei_waechst_wieder_an_die_grenze(self):
        for name in TEILE:
            with self.subTest(datei=name):
                anzahl = sum(len(t) for _k, basen, t in _klassen(_baum(name)) if BASIS in basen)
                self.assertLessEqual(
                    anzahl, MAX_SZENEN_TESTS,
                    f"{name} hat {anzahl} Szenen-Tests — jeder baut eine frische Seite "
                    f"(rund 14 s in der Windows-ARM64-CI). Lieber eine vierte Datei.")


if __name__ == "__main__":
    unittest.main()

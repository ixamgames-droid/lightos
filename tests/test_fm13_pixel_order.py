"""FM-13 — die Pixel-Reihenfolge eines Panels ist eine Geraete-Eigenschaft.

Der Befund kam aus dem Bau der realen Panel-Builtins: die **ADJ Dotz Matrix**
nummeriert im Werkszustand („Pixel Flip: Standard", Manual S. 12) in
**Schlangenlinien** ::

     1  2  3  4
     8  7  6  5
     9 10 11 12
    16 15 14 13

``buildMatrixPanel`` legte die Pixel dagegen zeilenweise an. Folge: ein
horizontales Lauflicht laeuft im 3D geradeaus und am **echten Geraet im
Zickzack** — ein Fehler, den kein Test sehen konnte, weil beide Seiten fuer sich
konsistent waren.

Die Reihenfolge gehoert ans GEPATCHTE GERAET, nicht ans Profil: dasselbe Modell
ist am Geraet umstellbar, und ein Umsortieren im Profil waere fuer die anderen
Flip-Stellungen wieder falsch.

★ Der Test haelt ausserdem die **Python- und die JS-Fassung der Regel**
gegeneinander. Zwei parallel gepflegte Formeln sind eine Drift-Quelle (Lehre
FM16E) — und hier faellt Drift besonders spaet auf, weil sie nur am echten Rig
sichtbar waere.
"""
from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.pixel_order import (                       # noqa: E402
    DEFAULT_PIXEL_ORDER, PIXEL_ORDER_LABELS, PIXEL_ORDERS,
    normalize_pixel_order, pixel_cell,
)

JS_MODUL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "src", "ui", "visualizer", "scene_src", "fixtures", "pixel_order.js")


class NormalisierungTest(unittest.TestCase):
    def test_default_ist_bestandsverhalten(self):
        self.assertEqual(DEFAULT_PIXEL_ORDER, "rowwise",
                         "Alt-Shows muessen unveraendert zeilenweise rendern")

    def test_unbekanntes_faellt_auf_den_default(self):
        for wert in ("", None, "quatsch", "ROWWISE ", 7):
            self.assertIn(normalize_pixel_order(wert), PIXEL_ORDERS)
        self.assertEqual(normalize_pixel_order("QUATSCH"), "rowwise")

    def test_gross_klein_und_leerzeichen(self):
        self.assertEqual(normalize_pixel_order(" Serpentine "), "serpentine")

    def test_jede_reihenfolge_hat_ein_label(self):
        for key in PIXEL_ORDERS:
            self.assertTrue(PIXEL_ORDER_LABELS.get(key))


class RasterTest(unittest.TestCase):
    """4x4 — dieselbe Form wie die Dotz Matrix im Manual."""

    def _raster(self, order):
        """Rendert die Zuordnung als Gitter aus DMX-Indizes (1-basiert wie im
        Manual), damit die Zusicherung lesbar bleibt."""
        gitter = [[0] * 4 for _ in range(4)]
        for i in range(16):
            r, c = pixel_cell(i, 4, order)
            gitter[r][c] = i + 1
        return gitter

    def test_zeilenweise(self):
        self.assertEqual(self._raster("rowwise"), [
            [1, 2, 3, 4],
            [5, 6, 7, 8],
            [9, 10, 11, 12],
            [13, 14, 15, 16],
        ])

    def test_schlangenlinien_wie_im_dotz_manual(self):
        self.assertEqual(self._raster("serpentine"), [
            [1, 2, 3, 4],
            [8, 7, 6, 5],
            [9, 10, 11, 12],
            [16, 15, 14, 13],
        ], "genau die Nummerierung aus dem ADJ-Manual S. 12")

    def test_gespiegelt(self):
        self.assertEqual(self._raster("mirrored"), [
            [4, 3, 2, 1],
            [8, 7, 6, 5],
            [12, 11, 10, 9],
            [16, 15, 14, 13],
        ])

    def test_jede_reihenfolge_ist_eine_permutation(self):
        """Keine Zelle darf doppelt belegt oder leer bleiben — sonst waeren
        Pixel unerreichbar bzw. wuerden sich gegenseitig ueberschreiben."""
        for order in PIXEL_ORDERS:
            for n, cols in ((16, 4), (144, 12), (9, 3), (10, 4)):
                zellen = [pixel_cell(i, cols, order) for i in range(n)]
                self.assertEqual(len(set(zellen)), n, f"{order}/{n}")

    def test_unvollstaendige_letzte_zeile(self):
        """10 Pixel auf 4 Spalten: die letzte Zeile ist halb leer. Bei
        Schlangenlinien darf das nicht ausserhalb des Rasters landen."""
        for order in PIXEL_ORDERS:
            for i in range(10):
                r, c = pixel_cell(i, 4, order)
                self.assertTrue(0 <= c < 4, f"{order}: Spalte {c} ausserhalb")

    def test_robuste_eingaben(self):
        self.assertEqual(pixel_cell(0, 0, "rowwise"), (0, 0))
        self.assertEqual(pixel_cell(-5, 4, "rowwise"), (0, 0))


class PersistenzTest(unittest.TestCase):
    """Eine Einstellung, die das Speichern nicht ueberlebt, ist keine."""

    def test_rundlauf_durch_das_showformat(self):
        from src.core.database.models import PatchedFixture
        from src.core.show.show_file import (_fixture_to_dict,
                                             _patched_fixture_from_data)
        pf = PatchedFixture(fid=7, label="Panel", fixture_profile_id=1,
                            mode_name="52-Kanal", channel_count=52,
                            universe=1, address=1, fixture_type="matrix",
                            pixel_order="serpentine")
        d = _fixture_to_dict(pf)
        self.assertEqual(d["pixel_order"], "serpentine")
        zurueck = _patched_fixture_from_data(d, 7)
        self.assertEqual(zurueck.pixel_order, "serpentine")

    def test_altshow_ohne_feld_bleibt_zeilenweise(self):
        """Bestands-Shows kennen das Feld nicht — sie muessen unveraendert
        zeilenweise rendern, nicht auf einen neuen Default kippen."""
        from src.core.show.show_file import _patched_fixture_from_data
        alt = {"fid": 3, "label": "Alt", "fixture_profile_id": 1,
               "mode_name": "8-Kanal", "channel_count": 8,
               "universe": 1, "address": 1}
        self.assertEqual(_patched_fixture_from_data(alt, 3).pixel_order,
                         "rowwise")

    def test_kaputter_wert_in_der_show_wirft_nicht(self):
        from src.core.show.show_file import _patched_fixture_from_data
        alt = {"fid": 3, "label": "Alt", "fixture_profile_id": 1,
               "mode_name": "8-Kanal", "channel_count": 8,
               "universe": 1, "address": 1, "pixel_order": "zickzack"}
        self.assertEqual(_patched_fixture_from_data(alt, 3).pixel_order,
                         "rowwise")


class PythonUndJsSindDieselbeRegelTest(unittest.TestCase):
    """★ Die JS-Fassung rendert, die Python-Fassung persistiert/prueft — laufen
    sie auseinander, sieht man es NUR am echten Geraet."""

    def test_js_modul_kennt_dieselben_reihenfolgen(self):
        js = open(JS_MODUL, encoding="utf-8").read()
        m = re.search(r"PIXEL_ORDERS\s*=\s*\[([^\]]*)\]", js)
        self.assertIsNotNone(m, "PIXEL_ORDERS fehlt im JS-Modul")
        js_orders = tuple(x.strip().strip("'\"") for x in m.group(1).split(",")
                          if x.strip())
        self.assertEqual(js_orders, PIXEL_ORDERS)
        self.assertIn(f"DEFAULT_PIXEL_ORDER = '{DEFAULT_PIXEL_ORDER}'", js)

    def test_js_hat_dieselbe_umrechnung(self):
        """Die Formel selbst: serpentine dreht ungerade Zeilen, mirrored jede."""
        js = open(JS_MODUL, encoding="utf-8").read()
        self.assertIn("serpentine' && r % 2 === 1", js)
        self.assertIn("nc - 1 - c", js)

    def test_nur_eine_stelle_rechnet_die_zelle_aus(self):
        """3D-Panel und 2D-Top-Down-Icon muessen dieselbe Quelle benutzen —
        zwei Formeln waeren die Drift-Quelle aus der FM16E-Lehre."""
        basis = os.path.dirname(JS_MODUL)
        for datei in ("builders.js", "topdown_icons.js"):
            quelle = open(os.path.join(basis, datei), encoding="utf-8").read()
            self.assertIn("pixelCell(", quelle, datei)
            self.assertNotIn("const r = Math.floor(i / cols), c = i % cols;",
                             quelle, f"{datei} rechnet die Zelle noch selbst aus")


if __name__ == "__main__":
    unittest.main()


# ── PIXELORDER (2026-08-05): der Weg vom Dialog in den State ─────────────────
#
# ★ Die Persistenz ins Showformat war getestet (PersistenzTest oben) — der Weg
# DORTHIN nicht. Und genau dort war das Feature seit dem Bau (PR #514) TOT:
# `pixel_order` fehlte in der `allowed`-Whitelist von `AppState.update_fixture`,
# der Wert wurde still verworfen, und die Methode meldete trotzdem True, weil
# Label/Universum/Adresse mitreisen.
#
# Dieselbe Falle wie bei `head_mode` — deren Kommentar steht in derselben
# Whitelist, zwei Zeilen darueber. Der Fix wurde damals am Ort angebracht, nicht
# an der Klasse. Diese Tests sind das Gegenstueck zu
# `test_head_mode_option.py::UpdateFixturePersistsHeadModeTest`.

class _PixelOrderStateBase(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _add(self, fid=1, pixel_order="rowwise"):
        from src.core.database.models import PatchedFixture
        f = PatchedFixture(fid=fid, label="Panel", fixture_profile_id=1,
                           mode_name="52-Kanal", universe=1, address=1,
                           channel_count=52, fixture_type="matrix",
                           pixel_order=pixel_order)
        self.state.add_fixture(f)
        return fid

    def _order_of(self, fid):
        f = next((x for x in self.state.get_patched_fixtures() if x.fid == fid), None)
        return None if f is None else getattr(f, "pixel_order", None)


class UpdateFixtureBehaeltPixelOrderTest(_PixelOrderStateBase):
    def test_die_wahl_kommt_ueberhaupt_an(self):
        self._add(pixel_order="rowwise")
        self.assertTrue(self.state.update_fixture(1, pixel_order="serpentine"))
        self.assertEqual(self._order_of(1), "serpentine")

    def test_realistische_dialog_nutzlast(self):
        """★ Der Test, der den Fehler ueberhaupt sichtbar macht.

        Der Patch-Dialog schickt IMMER Label, Universum, Adresse und Kanalzahl
        mit. Genau deshalb lieferte `update_fixture` `True`, obwohl die
        Pixel-Reihenfolge unterwegs verschwand — ein Test, der nur den
        Rueckgabewert prueft, ist hier gruen und sagt nichts.
        """
        self._add(pixel_order="rowwise")
        self.assertTrue(self.state.update_fixture(
            1, label="Panel L", universe=1, address=1, channel_count=52,
            pixel_order="serpentine"))
        self.assertEqual(
            self._order_of(1), "serpentine",
            "die Pixel-Reihenfolge ging in der Dialog-Nutzlast unter — genau "
            "der Zustand, in dem das Feature seit PR #514 war")

    def test_muell_wird_geklemmt_statt_gespeichert(self):
        self._add()
        self.state.update_fixture(1, pixel_order="ZICKZACK")
        self.assertEqual(self._order_of(1), "rowwise")
        self.state.update_fixture(1, pixel_order=" Serpentine ")
        self.assertEqual(self._order_of(1), "serpentine")


class UndoBehaeltPixelOrderTest(_PixelOrderStateBase):
    """Loeschen + Rueckgaengig darf die Reihenfolge nicht auf `rowwise`
    zuruecksetzen — sonst laeuft ein Lauflicht danach wieder im Zickzack, ohne
    dass jemand etwas umgestellt haette."""

    def test_loeschen_und_zurueck(self):
        self._add(pixel_order="serpentine")
        self.state.remove_fixture(1)
        from src.core.undo import get_undo_stack
        get_undo_stack().undo()
        self.assertEqual(self._order_of(1), "serpentine")


class KopierenBehaeltPixelOrderTest(unittest.TestCase):
    """„Mit Offset kopieren" baut das Ziel-Fixture aus dem Quell-Fixture neu —
    ohne das Feld faellt jede Kopie auf den ORM-Default. Man kopiert vier
    Panels und drei zaehlen anders als das Original."""

    def test_kopie_erbt_die_reihenfolge(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.models import PatchedFixture
        from src.ui.views.patch_view import _copy_fixture
        quelle = PatchedFixture(fid=1, label="Panel", fixture_profile_id=1,
                                mode_name="52-Kanal", universe=1, address=1,
                                channel_count=52, fixture_type="matrix",
                                pixel_order="serpentine")
        kopie = _copy_fixture(quelle, fid=2, universe=1, address=53)
        self.assertEqual(getattr(kopie, "pixel_order", None), "serpentine")

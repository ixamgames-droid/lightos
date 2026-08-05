"""ORIENT: wie ein Matrix-Panel HAENGT — zusaetzlich zu seiner Nummerierung.

`pixel_cell` beantwortet, in welcher Reihenfolge das GERAET seine Pixel auf DMX
legt (Werkszustand/Flip-Schalter). Offen blieb die davon UNABHAENGIGE Frage, wie
das Panel montiert ist: waagerecht oder hochkant, kopfueber, gespiegelt.

★ Warum das nicht dasselbe Feld sein darf: ein Panel kann in Schlangenlinien
zaehlen UND hochkant haengen. Beides in eine Angabe zu pressen hiesse, eine der
beiden Aussagen zu verlieren.

★★ Und warum `mirrored` allein nicht reichte: `pixel_cell` aendert
AUSSCHLIESSLICH die Spalte, nie die Zeile (`pixel_order.py`). Damit war
  - 180° (Zeilen- UND Spaltenumkehr) gar nicht ausdrueckbar — genau der Fall
    „Pixel Dir = invert", den das Stairville-Panel im Geraetemenue anbietet,
  - 90°/270° erst recht nicht, denn dort tauschen Zeilen und Spalten die Rollen
    und das RASTER aendert seine Form.

Der Paritaetsteil vergleicht Python und JS **numerisch** ueber alle
Kombinationen. Der bestehende Test dazu prueft den JS-Quelltext textuell — das
faengt eine umbenannte Konstante, aber keine falsche Formel.
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.pixel_order import (          # noqa: E402
    DEFAULT_ELEMENT_ROTATION, ELEMENT_ROTATIONS, PIXEL_ORDERS,
    normalize_element_rotation, pixel_cell, place_element, rotate_cell)

_JS_MODUL = ROOT / "src" / "ui" / "visualizer" / "scene_src" / "fixtures" / "pixel_order.js"


class NormalisierungTest(unittest.TestCase):
    def test_gueltige_werte(self):
        for w in ELEMENT_ROTATIONS:
            self.assertEqual(normalize_element_rotation(w), w)

    def test_muell_faellt_auf_null(self):
        for w in ("quatsch", None, "", 45, 17, [1], object()):
            self.assertEqual(normalize_element_rotation(w),
                             DEFAULT_ELEMENT_ROTATION)

    def test_vielfache_werden_umgerechnet(self):
        self.assertEqual(normalize_element_rotation(450), 90)
        self.assertEqual(normalize_element_rotation(-90), 270)
        self.assertEqual(normalize_element_rotation(360), 0)


class DrehungTest(unittest.TestCase):
    def test_ohne_drehung_ist_es_die_alte_rechnung(self):
        """★ Bestandsschutz: jedes heutige Geraet muss sich unveraendert
        verhalten. Ohne diesen Test waere die Aenderung nicht abnehmbar."""
        for cols, rows in ((12, 4), (4, 4), (1, 8), (7, 1), (5, 3)):
            for order in PIXEL_ORDERS:
                for i in range(cols * rows):
                    alt = pixel_cell(i, cols, order)
                    r, c, nr, nc = place_element(i, cols, rows, order)
                    self.assertEqual(
                        (r, c), alt,
                        f"place_element weicht ohne Drehung von pixel_cell ab "
                        f"({cols}x{rows}, {order}, Index {i})")
                    self.assertEqual((nr, nc), (rows, cols))

    def test_180_grad_kehrt_zeile_UND_spalte_um(self):
        """★ Der Fall, den es vorher gar nicht gab. `mirrored` spiegelt nur
        Spalten — ein kopfueber montiertes Panel war damit nicht abbildbar."""
        r, c, nr, nc = rotate_cell(0, 0, 4, 12, rotation=180)
        self.assertEqual((r, c), (3, 11))
        self.assertEqual((nr, nc), (4, 12), "180° darf das Raster nicht drehen")
        r, c, _, _ = rotate_cell(3, 11, 4, 12, rotation=180)
        self.assertEqual((r, c), (0, 0), "180° zweimal muss zurueckfuehren")

    def test_90_grad_vertauscht_das_raster(self):
        """Aus 4x12 wird 12x4 — genau deshalb muss die Rastergroesse
        mitgegeben werden, sonst rechnet jeder Aufrufer sie selbst."""
        _, _, nr, nc = rotate_cell(0, 0, 4, 12, rotation=90)
        self.assertEqual((nr, nc), (12, 4))
        _, _, nr, nc = rotate_cell(0, 0, 4, 12, rotation=270)
        self.assertEqual((nr, nc), (12, 4))

    def test_vier_mal_neunzig_ist_die_identitaet(self):
        """Die staerkste Aussage ueber die Rechnung: sie ist eine echte
        Drehung, keine Naeherung."""
        for rows, cols in ((4, 12), (3, 5), (1, 6)):
            for r0 in range(rows):
                for c0 in range(cols):
                    r, c, nr, nc = r0, c0, rows, cols
                    for _ in range(4):
                        r, c, nr, nc = rotate_cell(r, c, nr, nc, rotation=90)
                    self.assertEqual((r, c, nr, nc), (r0, c0, rows, cols))

    def test_drehung_ist_eine_bijektion(self):
        """Keine zwei Elemente duerfen auf derselben Zelle landen — sonst
        verschwaende eins still."""
        for rot in ELEMENT_ROTATIONS:
            for flip in (False, True):
                belegt = set()
                for r0 in range(4):
                    for c0 in range(12):
                        r, c, _, _ = rotate_cell(r0, c0, 4, 12, rot, flip)
                        self.assertNotIn(
                            (r, c), belegt,
                            f"zwei Elemente auf derselben Zelle "
                            f"(Drehung {rot}, flip {flip})")
                        belegt.add((r, c))
                self.assertEqual(len(belegt), 48)

    def test_spiegeln_bleibt_in_den_grenzen(self):
        for rot in ELEMENT_ROTATIONS:
            for r0 in range(4):
                for c0 in range(12):
                    r, c, nr, nc = rotate_cell(r0, c0, 4, 12, rot, flip=True)
                    self.assertTrue(0 <= r < nr and 0 <= c < nc,
                                    f"({r},{c}) liegt ausserhalb {nr}x{nc}")

    def test_nummerierung_wird_vor_der_drehung_angewandt(self):
        """★ Die Reihenfolge ist nicht beliebig: die Nummerierung ist eine
        Aussage ueber das UNGEDREHTE Geraet. Erst drehen und dann die
        Schlangenlinie anwenden liesse die Schlange ueber die falsche Achse
        laufen."""
        i, cols, rows = 13, 12, 4
        vor = pixel_cell(i, cols, "serpentine")
        erwartet = rotate_cell(vor[0], vor[1], rows, cols, rotation=90)
        self.assertEqual(
            place_element(i, cols, rows, "serpentine", rotation=90), erwartet)


class PythonUndJsRechnenNumerischGleichTest(unittest.TestCase):
    """★ Der bestehende Paritaetstest vergleicht den JS-QUELLTEXT. Das faengt
    eine umbenannte Konstante — aber keine falsche Formel. Hier laufen beide
    Fassungen ueber dieselben Eingaben und die Ergebnisse werden verglichen."""

    def test_alle_kombinationen_stimmen_ueberein(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtCore import QUrl

        app = QApplication.instance() or QApplication([])
        view = QWebEngineView()
        s = view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        faelle = [(i, cols, rows, order, rot, flip)
                  for cols, rows in ((12, 4), (5, 3))
                  for order in PIXEL_ORDERS
                  for rot in ELEMENT_ROTATIONS
                  for flip in (False, True)
                  for i in range(cols * rows)]

        html = f"""<!doctype html><meta charset="utf-8">
        <script type="module">
        import {{ placeElement }} from './pixel_order.js';
        const faelle = {json.dumps(faelle)};
        window.__out = JSON.stringify(faelle.map(function (f) {{
          const z = placeElement(f[0], f[1], f[2], f[3], f[4], f[5]);
          return [z.r, z.c, z.rows, z.cols];
        }}));
        </script>"""
        tmp = _JS_MODUL.parent / "_orient_paritaet_tmp.html"
        tmp.write_text(html, encoding="utf-8")
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))

        geladen = []
        view.loadFinished.connect(geladen.append)
        view.load(QUrl.fromLocalFile(str(tmp)))
        ende = time.monotonic() + 40
        while not geladen and time.monotonic() < ende:
            app.processEvents(); time.sleep(0.05)
        self.assertTrue(geladen and geladen[-1], "Seite nicht geladen")

        box = []
        ende = time.monotonic() + 20
        while not box and time.monotonic() < ende:
            view.page().runJavaScript("window.__out || ''", box.append)
            ende2 = time.monotonic() + 2
            while not box and time.monotonic() < ende2:
                app.processEvents(); time.sleep(0.05)
            if box and not box[0]:
                box.clear()
            time.sleep(0.05)
        self.assertTrue(box and box[0], "JS lieferte kein Ergebnis")
        js_werte = json.loads(box[0])

        from _qt_lifecycle import destroy_webengine_view

        def _pump(sek):
            e = time.monotonic() + sek
            while time.monotonic() < e:
                app.processEvents(); time.sleep(0.02)
        self.addCleanup(destroy_webengine_view, view, _pump)

        self.assertEqual(len(js_werte), len(faelle))
        for (i, cols, rows, order, rot, flip), js in zip(faelle, js_werte):
            py = list(place_element(i, cols, rows, order, rot, flip))
            self.assertEqual(
                py, js,
                f"Python und JS weichen ab: Index {i}, {cols}x{rows}, "
                f"{order}, {rot}°, flip={flip} — Python {py}, JS {js}")


if __name__ == "__main__":
    unittest.main()


# ── Die vier Nachzieh-Stellen ────────────────────────────────────────────────
#
# ★ `pixel_order` ist an genau diesen vier Wegen durchgefallen (PR #514, behoben
# 2026-08-05): Whitelist, Undo-Schnappschuss, Wiederherstellung, Kopieren mit
# Offset. Der Kommentar in der Whitelist beschrieb die Falle damals schon —
# fuer `head_mode`, den Vorgaenger. Zweimal am ORT behoben, nie an der KLASSE.
#
# Deshalb wird die Orientierung von Anfang an an allen vier Wegen geprueft,
# statt beim naechsten Vorfall gesucht.

class _StateBasis(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.fixture_db import ensure_builtins
        from src.core.show.show_file import reset_show
        from src.core.app_state import get_state
        ensure_builtins()
        reset_show()
        self.state = get_state()

    def _add(self, fid=1, rotation=0, flip=False):
        from src.core.database.models import PatchedFixture
        f = PatchedFixture(fid=fid, label="Panel", fixture_profile_id=1,
                           mode_name="154-Kanal", universe=1, address=1,
                           channel_count=154, fixture_type="matrix",
                           element_rotation=rotation, element_flip=flip)
        self.state.add_fixture(f)
        return fid

    def _stand(self, fid):
        f = next((x for x in self.state.get_patched_fixtures() if x.fid == fid), None)
        return (None if f is None else
                (int(getattr(f, "element_rotation", 0) or 0),
                 bool(getattr(f, "element_flip", False))))


class WegEinsSpeichernTest(_StateBasis):
    def test_die_wahl_kommt_an(self):
        self._add(rotation=0)
        self.assertTrue(self.state.update_fixture(1, element_rotation=90,
                                                  element_flip=True))
        self.assertEqual(self._stand(1), (90, True))

    def test_realistische_dialog_nutzlast(self):
        """★ Der Test, der den `pixel_order`-Fehler sichtbar gemacht haette:
        der Dialog schickt IMMER Label/Universum/Adresse mit, und genau deshalb
        meldete `update_fixture` Erfolg, obwohl das Feld unterwegs verschwand."""
        self._add()
        self.assertTrue(self.state.update_fixture(
            1, label="Panel L", universe=1, address=1, channel_count=154,
            element_rotation=180, element_flip=False))
        self.assertEqual(
            self._stand(1), (180, False),
            "die Montage-Drehung ging in der Dialog-Nutzlast unter")

    def test_muell_wird_geklemmt(self):
        self._add()
        self.state.update_fixture(1, element_rotation="quatsch")
        self.assertEqual(self._stand(1)[0], 0)
        self.state.update_fixture(1, element_rotation=450)
        self.assertEqual(self._stand(1)[0], 90)


class WegZweiUndDreiUndoTest(_StateBasis):
    def test_loeschen_und_zurueck_behaelt_die_orientierung(self):
        self._add(rotation=270, flip=True)
        self.state.remove_fixture(1)
        from src.core.undo import get_undo_stack
        get_undo_stack().undo()
        self.assertEqual(self._stand(1), (270, True))


class WegVierKopierenTest(unittest.TestCase):
    def test_kopie_erbt_die_orientierung(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from src.core.database.models import PatchedFixture
        from src.ui.views.patch_view import _copy_fixture
        quelle = PatchedFixture(fid=1, label="Panel", fixture_profile_id=1,
                                mode_name="154-Kanal", universe=1, address=1,
                                channel_count=154, fixture_type="matrix",
                                element_rotation=90, element_flip=True)
        kopie = _copy_fixture(quelle, fid=2, universe=1, address=155)
        self.assertEqual(int(getattr(kopie, "element_rotation", 0)), 90)
        self.assertTrue(bool(getattr(kopie, "element_flip", False)))


class ShowRundlaufTest(unittest.TestCase):
    """Eine Einstellung, die das Speichern nicht ueberlebt, ist keine."""

    def test_rundlauf_durch_das_showformat(self):
        from src.core.database.models import PatchedFixture
        from src.core.show.show_file import (_fixture_to_dict,
                                             _patched_fixture_from_data)
        pf = PatchedFixture(fid=7, label="Panel", fixture_profile_id=1,
                            mode_name="154-Kanal", channel_count=154,
                            universe=1, address=1, fixture_type="matrix",
                            element_rotation=180, element_flip=True)
        d = _fixture_to_dict(pf)
        self.assertEqual(d["element_rotation"], 180)
        self.assertIs(d["element_flip"], True)
        zurueck = _patched_fixture_from_data(d, 7)
        self.assertEqual(zurueck.element_rotation, 180)
        self.assertIs(zurueck.element_flip, True)

    def test_altshow_ohne_feld_bleibt_ungedreht(self):
        """Bestands-Shows kennen das Feld nicht — sie muessen unveraendert
        rendern, nicht auf eine neue Voreinstellung kippen."""
        from src.core.show.show_file import _patched_fixture_from_data
        alt = {"fid": 3, "label": "Alt", "fixture_profile_id": 1,
               "mode_name": "8-Kanal", "channel_count": 8,
               "universe": 1, "address": 1}
        f = _patched_fixture_from_data(alt, 3)
        self.assertEqual(f.element_rotation, 0)
        self.assertFalse(f.element_flip)

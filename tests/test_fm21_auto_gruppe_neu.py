"""FM-21 (a) — die automatische Kopf-Gruppe folgt Rasterform, Nummerierung und
Montage, und wird nach einer Aenderung nur MIT Rueckfrage neu aufgebaut.

Entscheidung des Projektinhabers vom 17.11.2026:

* Ein Matrix-Geraet mit hinterlegter Rasterform (``grid_rows x grid_cols`` ==
  Kopfzahl) bekommt beim Patchen gleich ``rows x cols`` statt 1xN — gebaut
  ueber ``place_element``, also mit ``pixel_order`` UND Montage-Drehung.
* Aendert der Bediener danach Pixel-Reihenfolge oder Montage, fragt LightOS,
  ob die vorhandene Auto-Gruppe neu aufgebaut werden soll („Nein“ ist
  vorgewaehlt). Ja = neues Raster, als EIN Rueckgaengig-Schritt zusammen mit
  der Feldaenderung. Nein = alles bleibt.
* Beim LADEN einer Show wird nie gefragt und nie umgebaut.
* Ohne Rasterform bleibt es 1xN, Pixel-Koepfe bleiben beim Ring-Raster.

Alle Erwartungen sind von HAND aus der Geraete-Nummerierung abgeleitet (Zahlen
im Test), nicht mit ``place_element`` nachgerechnet — sonst pruefte der Test
nur, dass die Formel sich selbst gleicht.

Der Weg ist der echte: Patch-Dialog (nur ``exec`` ersetzt) ->
``PatchView._on_double_click`` -> ``update_fixture`` -> Rueckfrage
(``QMessageBox.question`` im Modul ``patch_view``, aufgezeichnet) -> Kern.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox   # noqa: E402
from sqlalchemy import select                                       # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

import pytest as _pytest_xplat15                                    # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from _fixture_quelle import frische_library                         # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


# ZQ06121: 48 Farbzonen, im Profil als 4 Reihen x 12 Spalten hinterlegt.
MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE = 154
# Spider: zwei Farbkoepfe, KEINE Rasterform -> bleibt 1xN.
SPIDER_MODUS, SPIDER_KANAELE = "14-Kanal", 14
# Pixel-Kopf: Ring-Raster wie bisher.
SPIIDER_MODUS, SPIIDER_KANAELE = "91-Kanal Pixel RGB (Mode 7)", 91

JA = QMessageBox.StandardButton.Yes
NEIN = QMessageBox.StandardButton.No


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Frage:
    """Ersatz fuer ``QMessageBox`` im Modul ``patch_view``: zeichnet jede
    Rueckfrage auf und antwortet wie vorgegeben. Alles andere wirft — ein
    unerwarteter Hinweis soll den Test rot machen, nicht still durchgehen."""
    StandardButton = QMessageBox.StandardButton

    def __init__(self, antwort):
        self.antwort = antwort
        self.fragen: list[dict] = []

    def question(self, _eltern, titel, text, knoepfe=None, vorgabe=None):
        self.fragen.append({"titel": str(titel), "text": str(text),
                            "vorgabe": vorgabe})
        return self.antwort

    def information(self, *a, **kw):
        raise AssertionError(f"unerwarteter Hinweis: {a!r}")

    warning = information


class _Basis(unittest.TestCase):
    def setUp(self):
        from src.core.app_state import clear_channel_cache, get_state
        from src.core.show.show_file import reset_show
        from src.core.undo import get_undo_stack
        _app()
        self._eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        reset_show()
        self.addCleanup(reset_show)
        get_undo_stack().clear()
        self.addCleanup(get_undo_stack().clear)
        self.state = get_state()

    # ── Bausteine ──────────────────────────────────────────────────────────

    def _pid(self, short: str) -> int:
        from src.core.database.models import FixtureProfile
        with Session(self._eng) as s:
            pid = s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == short)).scalars().first()
        self.assertIsNotNone(pid, f"Profil {short} fehlt in der Bibliothek")
        return int(pid)

    def _patch(self, short="ZQ06121", modus=MODUS, kanaele=KANAELE, *, fid=1,
               adresse=1, typ="matrix", **felder):
        from src.core.database.models import PatchedFixture
        self.state.add_fixture(PatchedFixture(
            fid=fid, label=f"Balken{fid}", fixture_profile_id=self._pid(short),
            mode_name=modus, universe=1, address=adresse, channel_count=kanaele,
            fixture_type=typ, **felder), undoable=False)
        return self._frisch(fid)

    def _frisch(self, fid=1):
        return next(f for f in self.state.get_patched_fixtures() if f.fid == fid)

    def _gruppe(self, fid=1):
        from src.core.database.models import FixtureGroup
        gid = self.state.find_head_matrix_group(fid, dedicated=True)
        self.assertIsNotNone(gid, "keine Auto-Kopf-Gruppe")
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            return (gid, g.name, int(g.cols), int(g.rows),
                    json.loads(g.positions_json or "{}"))

    def _gruppe_setzen(self, gid, cols, rows, positions):
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            g.cols, g.rows = cols, rows
            g.positions_json = json.dumps(positions)
            s.commit()

    def _im_dialog(self, fid, antwort, *, order=None, drehung=None):
        """Echter Patch-Dialog ueber den echten Aufrufer; nur ``exec`` und die
        Rueckfrage sind ersetzt. Rueckgabe: die aufgezeichneten Fragen."""
        import src.ui.views.patch_view as PV

        class _Dialog(PV.PatchFixtureEditDialog):
            def exec(self_inner):
                if order is not None:
                    c = self_inner._combo_pixel_order
                    c.setCurrentIndex(c.findData(order))
                if drehung is not None:
                    c = self_inner._combo_rotation
                    c.setCurrentIndex(c.findData(drehung))
                self_inner._on_accept()
                return QDialog.DialogCode.Accepted

        frage = _Frage(antwort)
        pv = PV.PatchView()
        self.addCleanup(pv.deleteLater)
        echt_dlg, echt_box = PV.PatchFixtureEditDialog, PV.QMessageBox
        PV.PatchFixtureEditDialog, PV.QMessageBox = _Dialog, frage
        try:
            zeile = next(r for r in range(pv._table.rowCount())
                         if pv._fid_at_row(r) == fid)
            pv._on_double_click(pv._table.model().index(zeile, 0))
        finally:
            PV.PatchFixtureEditDialog, PV.QMessageBox = echt_dlg, echt_box
        return frage.fragen


# ════════════════════════════════════════════════════════════════════════════
# 1. Beim Patchen: das Raster aus Rasterform, Nummerierung und Montage
# ════════════════════════════════════════════════════════════════════════════

class AutoGruppeBeimPatchenTest(_Basis):

    def test_panel_mit_form_bekommt_4x12_in_werksnummerierung(self):
        fx = self._patch(pixel_order="serpentine")
        _gid, name, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows), (12, 4),
                         "das Panel haengt als 12 Spalten x 4 Reihen — die "
                         "Auto-Gruppe ist noch die 1xN-Reihe")
        self.assertTrue(name.endswith("· Köpfe"), name)
        # Schlangenlinie, von Hand: Zeile 0 = Koepfe 0..11 links->rechts,
        # Zeile 1 laeuft rueckwaerts: links Kopf 23, rechts Kopf 12.
        self.assertEqual(pos["0,0"], f"{fx.fid}:0")
        self.assertEqual(pos["11,0"], f"{fx.fid}:11")
        self.assertEqual(pos["0,1"], f"{fx.fid}:23")
        self.assertEqual(pos["11,1"], f"{fx.fid}:12")
        self.assertEqual(pos["0,2"], f"{fx.fid}:24")
        self.assertEqual(len(pos), 48)

    def test_zeilenweise_ist_der_default(self):
        self._patch()
        _gid, _n, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows), (12, 4))
        self.assertEqual(pos["0,1"], "1:12", "zeilenweise beginnt Zeile 1 mit Kopf 12")

    def test_montage_90_grad_dreht_das_raster(self):
        self._patch(element_rotation=90)
        _gid, _n, cols, rows, pos = self._gruppe()
        # 90 Grad im Uhrzeigersinn: aus 12 x 4 wird 4 Spalten x 12 Reihen; die
        # obere Panel-Reihe (Koepfe 0..11) wird zur RECHTEN Spalte, von oben
        # nach unten; die zweite Panel-Reihe (12..23) zur Spalte links daneben.
        self.assertEqual((cols, rows), (4, 12))
        self.assertEqual(pos["3,0"], "1:0")
        self.assertEqual(pos["3,11"], "1:11")
        self.assertEqual(pos["2,0"], "1:12")
        self.assertEqual(pos["0,11"], "1:47")

    def test_geraet_ohne_form_bleibt_1xN(self):
        fx = self._patch("SPIDER14", SPIDER_MODUS, SPIDER_KANAELE,
                         typ="moving_head", pixel_order="mirrored",
                         element_rotation=90)
        from src.core.app_state import color_head_count
        n = int(color_head_count(fx))
        self.assertGreaterEqual(n, 2)
        _gid, _n, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows), (n, 1),
                         "ohne Rasterform muss es die 1xN-Reihe bleiben — "
                         "auch Spiegelung/Drehung erfinden keine Form")
        self.assertEqual(pos, {f"{h},0": f"1:{h}" for h in range(n)})

    def test_pixel_kopf_bleibt_beim_ring(self):
        from src.core.pixel_order import waben_raster
        self._patch("SPIIDER", SPIIDER_MODUS, SPIIDER_KANAELE, typ="moving_head")
        _gid, name, cols, rows, pos = self._gruppe()
        self.assertTrue(name.endswith("· Pixel"), name)
        w_cols, w_rows, plaetze = waben_raster(19)
        self.assertEqual((cols, rows), (w_cols, w_rows))
        self.assertEqual(pos, {f"{c},{r}": f"1:{i + 1}"
                               for i, (c, r) in plaetze.items()})


# ════════════════════════════════════════════════════════════════════════════
# 2. Nachtraeglich geaendert: Rueckfrage, Ja / Nein, umgebaute Gruppe, Undo
# ════════════════════════════════════════════════════════════════════════════

class NeuaufbauMitRueckfrageTest(_Basis):

    def test_ja_baut_neu(self):
        self._patch()
        fragen = self._im_dialog(1, JA, order="serpentine")
        self.assertEqual(len(fragen), 1, "keine Rueckfrage nach der Aenderung")
        f = fragen[0]
        self.assertIn("„Balken1 · Köpfe“ neu aufbauen?", f["text"])
        self.assertEqual(f["vorgabe"], NEIN, "„Nein“ muss vorgewaehlt sein")
        _gid, _n, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows), (12, 4))
        self.assertEqual(pos["0,1"], "1:23", "Ja hat das Raster nicht neu gebaut")
        self.assertEqual(self._frisch().pixel_order, "serpentine")

    def test_unveraenderte_gruppe_kurze_frage_ohne_verlustwarnung(self):
        self._patch()
        f = self._im_dialog(1, NEIN, order="serpentine")[0]
        self.assertNotIn("verloren", f["text"],
                         "die Gruppe war unveraendert — die Verlustwarnung "
                         "waere hier falsch")

    def test_nein_laesst_alles(self):
        self._patch()
        vorher = self._gruppe()
        fragen = self._im_dialog(1, NEIN, order="serpentine")
        self.assertEqual(len(fragen), 1)
        self.assertEqual(self._gruppe(), vorher, "Nein hat die Gruppe veraendert")
        self.assertEqual(self._frisch().pixel_order, "serpentine",
                         "die Feldaenderung selbst muss trotzdem gelten")

    def test_umgebaute_gruppe_ja_ueberschreibt(self):
        self._patch()
        gid, _n, _c, _r, _p = self._gruppe()
        eigen = {"0,0": "1:5", "1,0": "1:0"}
        self._gruppe_setzen(gid, 2, 1, eigen)
        f = self._im_dialog(1, JA, order="serpentine")[0]
        self.assertIn("Eigene Änderungen an dieser Gruppe gehen dabei verloren.",
                      f["text"])
        _gid, _n, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows, pos["0,1"]), (12, 4, "1:23"))

    def test_umgebaute_gruppe_nein_bleibt(self):
        self._patch()
        gid, *_ = self._gruppe()
        eigen = {"0,0": "1:5", "1,0": "1:0"}
        self._gruppe_setzen(gid, 2, 1, eigen)
        self._im_dialog(1, NEIN, order="serpentine")
        self.assertEqual(self._gruppe()[2:], (2, 1, eigen))

    def test_nur_umbenennen_fragt_nicht(self):
        """Gefragt wird nur, wenn sich das Soll-Raster verschoben hat — eine
        umgebaute Gruppe darf nicht bei jedem Speichern zur Frage werden."""
        self._patch()
        gid, *_ = self._gruppe()
        self._gruppe_setzen(gid, 2, 1, {"0,0": "1:5"})
        self.assertEqual(self._im_dialog(1, JA), [])

    def test_montage_aendern_fragt_und_dreht(self):
        self._patch()
        self.assertEqual(len(self._im_dialog(1, JA, drehung=90)), 1)
        _gid, _n, cols, rows, pos = self._gruppe()
        self.assertEqual((cols, rows, pos["3,0"]), (4, 12, "1:0"))

    def test_undo_ist_ein_schritt(self):
        from src.core.undo import get_undo_stack
        self._patch()
        vorher = self._gruppe()
        self._im_dialog(1, JA, order="serpentine")
        stapel = get_undo_stack()
        self.assertEqual(len(stapel._undo), 1,
                         "Feldaenderung und Neuaufbau muessen EIN Schritt sein")
        stapel.undo()
        self.assertEqual(self._frisch().pixel_order, "rowwise")
        self.assertEqual(self._gruppe(), vorher, "Undo stellt die Gruppe nicht her")
        stapel.redo()
        self.assertEqual(self._frisch().pixel_order, "serpentine")
        self.assertEqual(self._gruppe()[4]["0,1"], "1:23")

    def test_kern_aendert_ohne_ui_nichts_still(self):
        """``update_fixture`` allein (Skript/Remote) baut nie still um."""
        self._patch()
        vorher = self._gruppe()
        self.state.update_fixture(1, pixel_order="serpentine")
        self.assertEqual(self._gruppe(), vorher)
        befund = self.state.auto_kopfgruppe_abweichung(1)
        self.assertIsNotNone(befund, "die Abfrage sieht die Abweichung nicht")


# ════════════════════════════════════════════════════════════════════════════
# 3. Laufende Matrix und gespeicherte Show
# ════════════════════════════════════════════════════════════════════════════

class MatrixUndShowTest(_Basis):

    def _matrix_auf_gruppe(self, gid):
        from src.ui.views.rgb_matrix_view import RgbMatrixView
        self.state.set_selected_group_id(gid)
        mv = RgbMatrixView()
        self.addCleanup(mv.deleteLater)
        mv._add()
        mv._assign_from_selection()
        return mv._current

    def test_laufende_matrix_ueberlebt_den_neuaufbau(self):
        from src.core.dmx.universe import Universe
        from src.core.show.show_file import load_show, save_show
        self._patch()
        gid, *_ = self._gruppe()
        inst = self._matrix_auf_gruppe(gid)
        self.assertEqual((inst.cols, inst.rows), (12, 4))
        inst.start()
        u = Universe(1)
        inst.write({1: u}, self.state.get_patched_fixtures(), 0.0)
        self._im_dialog(1, JA, drehung=90)
        self.assertEqual(self._gruppe()[2:4], (4, 12))
        # Die Matrix schreibt weiter (ihr Raster ist ihre eigene Kopie).
        inst.write({1: u}, self.state.get_patched_fixtures(), 0.05)
        inst.stop()
        with tempfile.TemporaryDirectory() as td:
            pfad = os.path.join(td, "fm21.lshow")
            save_show(pfad)
            load_show(pfad)
        from src.core.engine.function_manager import get_function_manager
        geladen = [f for f in get_function_manager().all()
                   if getattr(f, "id", None) == inst.id]
        self.assertEqual(len(geladen), 1, "die Matrix laedt nicht mehr")
        self.assertEqual((geladen[0].cols, geladen[0].rows), (12, 4))

    def test_alt_show_laedt_ohne_rueckfrage_und_unveraendert(self):
        """Eine Show von VOR FM-21: das Panel hat noch die 1xN-Auto-Gruppe.
        Laden fragt nicht und baut nicht um; erst eine Geraeteaenderung fragt
        — und dann gilt die alte Reihe als unveraenderte Automatik."""
        import src.ui.views.patch_view as PV
        from src.core.show.show_file import load_show, reset_show, save_show
        self._patch()
        gid, *_ = self._gruppe()
        reihe = {f"{h},0": f"1:{h}" for h in range(48)}
        self._gruppe_setzen(gid, 48, 1, reihe)
        frage = _Frage(JA)
        echt = PV.QMessageBox
        PV.QMessageBox = frage
        try:
            with tempfile.TemporaryDirectory() as td:
                pfad = os.path.join(td, "alt.lshow")
                save_show(pfad)
                reset_show()
                load_show(pfad)
            pv = PV.PatchView()          # die Patch-Ansicht baut sich auf
            self.addCleanup(pv.deleteLater)
        finally:
            PV.QMessageBox = echt
        self.assertEqual(frage.fragen, [], "beim Laden wurde gefragt")
        self.assertEqual(self._gruppe()[2:], (48, 1, reihe),
                         "beim Laden wurde die Alt-Gruppe umgebaut")
        f = self._im_dialog(1, NEIN, order="serpentine")
        self.assertEqual(len(f), 1)
        self.assertNotIn("verloren", f[0]["text"],
                         "die alte 1xN-Reihe ist unveraenderte Automatik")
        self.assertEqual(self._gruppe()[2:], (48, 1, reihe))


if __name__ == "__main__":
    unittest.main()

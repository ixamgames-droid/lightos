"""FM-80 — LED-Matrix-Assistent: eigenes Matrix-Geraet aus Pixelzahl, Flaeche,
Bauform, Kanalformat und Verdrahtung.

Geprueft wird die Rechnung (``src/core/led_matrix.py``), das Speichern in eine
FRISCHE Test-Bibliothek (nie die echte fixtures.db), das Patchen mit
Auto-Kopf-Gruppe (FM-21) und Gesamt-Gruppe, das nachtraegliche Bearbeiten und
der Dialog selbst (Vorschau, Touch-Groessen).

Erwartete Raster sind von HAND aus der Verdrahtung abgeleitet (Zahlen im
Test), nicht mit ``place_element`` nachgerechnet.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget                # noqa: E402
from sqlalchemy.orm import Session                                  # noqa: E402

import pytest                                                       # noqa: E402
from _fixture_quelle import frische_library                         # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402

from src.core import led_matrix as LM                               # noqa: E402


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app():
    return QApplication.instance() or QApplication([])


def _raster(a: LM.MatrixAngaben) -> list[list[int]]:
    """Anzeige-Raster mit 1-basierten Pixelnummern."""
    g = [[0] * a.breite_px for _ in range(a.hoehe_px)]
    for p in range(a.breite_px * a.hoehe_px):
        r, c = LM.pixel_platz(a, p)
        g[r][c] = p + 1
    return g


# ════════════════════════════════════════════════════════════════════════════
# 1. Rechnung: Kanalbelegung, Universen, Masse, Verdrahtung
# ════════════════════════════════════════════════════════════════════════════

class KanalbelegungTest(unittest.TestCase):

    def _attrs(self, **kw):
        a = LM.MatrixAngaben(breite_px=2, hoehe_px=1, **kw)
        t = LM.teile(a)[0]
        return [(c["name"], c["attribute"]) for c in LM.kanaele_fuer_teil(a, t)]

    def test_rgb(self):
        self.assertEqual(self._attrs(format="RGB"), [
            ("P1 Rot", "color_r"), ("P1 Grün", "color_g"), ("P1 Blau", "color_b"),
            ("P2 Rot", "color_r"), ("P2 Grün", "color_g"), ("P2 Blau", "color_b")])

    def test_grb(self):
        self.assertEqual([x[1] for x in self._attrs(format="GRB")],
                         ["color_g", "color_r", "color_b"] * 2)

    def test_rgbw(self):
        self.assertEqual([x[1] for x in self._attrs(format="RGBW")],
                         ["color_r", "color_g", "color_b", "color_w"] * 2)

    def test_master_und_strobe_vorn(self):
        a = LM.MatrixAngaben(breite_px=2, hoehe_px=1, master=True, strobe=True)
        kan = LM.kanaele_fuer_teil(a, LM.teile(a)[0])
        self.assertEqual([c["attribute"] for c in kan[:3]],
                         ["intensity", "strobe", "color_r"])
        self.assertEqual(kan[0]["default_value"], 0,
                         "Master startet auf 0 — Farbe zieht den Dimmer nie mit")
        self.assertEqual([c["channel_number"] for c in kan], list(range(1, 9)))
        self.assertEqual(kan[1]["ranges"][0]["kind"], "open")


class UniversenTest(unittest.TestCase):

    def test_20x40_rgb_2400_kanaele_auf_5_universen(self):
        a = LM.MatrixAngaben(breite_px=20, hoehe_px=40, format="RGB")
        tl = LM.teile(a)
        self.assertEqual(len(tl), 5)
        self.assertEqual(sum(t.kanaele for t in tl), 2400)
        self.assertTrue(all(t.zeilen == 8 and t.kanaele == 480 for t in tl))
        p = LM.profil_payload(a)
        self.assertEqual([(m["grid_rows"], m["grid_cols"]) for m in p["modes"]],
                         [(8, 20)] * 5)
        self.assertEqual(p["modes"][1]["channels"][0]["name"], "P161 Rot",
                         "Pixel sind global nummeriert")

    def test_mit_master_passen_170_pixel(self):
        a = LM.MatrixAngaben(breite_px=17, hoehe_px=30, master=True)
        self.assertEqual(a.pixel_je_universum(), 170)
        tl = LM.teile(a)
        self.assertEqual([t.zeilen for t in tl], [10, 10, 10])
        self.assertTrue(all(t.kanaele == 511 for t in tl))

    def test_kein_pixel_ueber_universumsgrenze(self):
        for fmt in LM.FORMATE:
            for b in (1, 7, 20, 33, 100):
                a = LM.MatrixAngaben(breite_px=b, hoehe_px=50, format=fmt,
                                     master=True, strobe=True)
                for t in LM.teile(a):
                    self.assertLessEqual(t.kanaele, 512)
                    self.assertEqual((t.kanaele - 2) % len(LM.FORMATE[fmt]), 0)

    def test_rest_teil_und_wunschzeilen(self):
        a = LM.MatrixAngaben(breite_px=20, hoehe_px=40, zeilen_je_teil=6)
        self.assertEqual([t.zeilen for t in LM.teile(a)], [6] * 6 + [4])
        a.zeilen_je_teil = 99   # mehr als passt -> geklemmt
        self.assertEqual(a.zeilen_teil(), 8)

    def test_zu_breite_zeile_wird_abgelehnt(self):
        a = LM.MatrixAngaben(breite_px=200, hoehe_px=2, format="RGB")
        self.assertTrue(any("mehr als ein Universum" in f for f in a.fehler()))
        with self.assertRaises(ValueError):
            LM.profil_payload(a)

    def test_passt_in_ein_universum(self):
        a = LM.MatrixAngaben(breite_px=8, hoehe_px=8)
        tl = LM.teile(a)
        self.assertEqual(len(tl), 1)
        self.assertEqual(tl[0].name, "8×8 RGB (192 Kanäle)")


class MasseTest(unittest.TestCase):

    def test_pixelabstand_aus_flaeche(self):
        a = LM.MatrixAngaben(breite_px=20, hoehe_px=40, breite_cm=30, hoehe_cm=50)
        self.assertEqual(a.pixelabstand_mm(), (15.0, 12.5))
        p = LM.profil_payload(a)
        d = json.loads(p["matrix_angaben"])
        self.assertEqual((d["breite_cm"], d["hoehe_cm"]), (30, 50))
        self.assertIn("15×12.5 mm", p["notes"])

    def test_ohne_flaeche_kein_abstand(self):
        a = LM.MatrixAngaben(breite_cm=0, hoehe_cm=0)
        self.assertEqual(a.pixelabstand_mm(), (0.0, 0.0))
        self.assertEqual(a.fehler(), [])


class VerdrahtungTest(unittest.TestCase):

    def test_zeilenweise_oben_links(self):
        a = LM.MatrixAngaben(breite_px=3, hoehe_px=2)
        self.assertEqual(_raster(a), [[1, 2, 3], [4, 5, 6]])

    def test_schlange_ueber_teilgrenzen_mit_ungerader_zeilenzahl(self):
        a = LM.MatrixAngaben(breite_px=3, hoehe_px=4, verdrahtung="schlange",
                             zeilen_je_teil=1)
        self.assertEqual(_raster(a), [[1, 2, 3], [6, 5, 4], [7, 8, 9], [12, 11, 10]])

    def test_startecken(self):
        a = LM.MatrixAngaben(breite_px=3, hoehe_px=2, startecke="oben_rechts")
        self.assertEqual(_raster(a), [[3, 2, 1], [6, 5, 4]])
        a.startecke = "unten_rechts"
        self.assertEqual(_raster(a), [[6, 5, 4], [3, 2, 1]])
        a.startecke = "unten_links"
        a.verdrahtung = "schlange"
        self.assertEqual(_raster(a), [[6, 5, 4], [1, 2, 3]])

    def test_unten_links_mit_teilen(self):
        a = LM.MatrixAngaben(breite_px=3, hoehe_px=4, verdrahtung="schlange",
                             startecke="unten_links", zeilen_je_teil=3)
        self.assertEqual(_raster(a), [[12, 11, 10], [7, 8, 9], [6, 5, 4], [1, 2, 3]])


class BauformTest(unittest.TestCase):

    def test_bestand_ist_panel(self):
        class P:
            bauform = ""
        self.assertEqual(LM.bauform_von(P()), "panel")
        self.assertEqual(LM.bauform_von(None), "panel")
        self.assertEqual(LM.normalize_bauform("Vorhang"), "vorhang")
        self.assertEqual(LM.normalize_bauform("quatsch"), "panel")

    def test_kaputte_angaben(self):
        self.assertIsNone(LM.angaben_aus_json(""))
        self.assertIsNone(LM.angaben_aus_json("{kaputt"))
        self.assertIsNone(LM.angaben_aus_json("[1]"))


# ════════════════════════════════════════════════════════════════════════════
# 2. Bibliothek: Speichern, Bauform-Feld, Datei-Format, Migration
# ════════════════════════════════════════════════════════════════════════════

class BibliothekTest(unittest.TestCase):

    def setUp(self):
        self.eng = frische_library(self)

    def _profil(self, pid):
        from src.core.database.models import FixtureProfile
        s = Session(self.eng)
        self.addCleanup(s.close)
        return s.get(FixtureProfile, pid)

    def test_speichern_mit_bauform_und_raster(self):
        from src.core.database import fixture_db as fdb
        a = LM.MatrixAngaben(modell="Vorhang 20x40", breite_px=20, hoehe_px=40,
                             bauform="vorhang")
        pid = fdb.create_user_profile(LM.profil_payload(a), engine=self.eng)
        p = self._profil(pid)
        self.assertEqual(p.fixture_type, "matrix")
        self.assertEqual(p.source, "user")
        self.assertEqual(p.bauform, "vorhang")
        self.assertEqual(LM.bauform_von(p), "vorhang")
        self.assertEqual(LM.masse_von(p), (30.0, 50.0))
        self.assertEqual(len(p.modes), 5)
        self.assertTrue(all((m.grid_rows, m.grid_cols, m.channel_count) == (8, 20, 480)
                            for m in p.modes))
        wieder = LM.angaben_von_profil(p)
        self.assertEqual((wieder.modell, wieder.breite_px, wieder.bauform),
                         ("Vorhang 20x40", 20, "vorhang"))

    def test_vorhandene_profile_bleiben_panel(self):
        from sqlalchemy import select
        from src.core.database.models import FixtureProfile
        with Session(self.eng) as s:
            p = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "MATRIXPANEL")).scalars().first()
            self.assertIn(p.bauform or "", ("",))
            self.assertEqual(LM.bauform_von(p), "panel")
            self.assertIsNone(LM.angaben_von_profil(p))

    def test_generator_ueberschreiben_behaelt_bauform(self):
        from src.core.database import fixture_db as fdb
        a = LM.MatrixAngaben(modell="Ring", breite_px=4, hoehe_px=1, bauform="ring")
        pid = fdb.create_user_profile(LM.profil_payload(a), engine=self.eng)
        payload = LM.profil_payload(a)
        payload.pop("bauform")
        payload.pop("matrix_angaben")
        fdb.update_user_profile(pid, payload, engine=self.eng)
        p = self._profil(pid)
        self.assertEqual(p.bauform, "ring")
        self.assertEqual(p.matrix_angaben, "",
                         "von Hand geaendert -> nicht mehr im Assistenten oeffnen")

    def test_bibliotheksdatei_traegt_bauform_und_angaben(self):
        from src.core.database import bibliothek_format as BF
        from src.core.database import fixture_db as fdb
        a = LM.MatrixAngaben(modell="Saeule", breite_px=4, hoehe_px=3, bauform="saeule")
        pid = fdb.create_user_profile(LM.profil_payload(a), engine=self.eng)
        d = BF.profil_zu_daten(self._profil(pid))
        self.assertEqual(d["bauform"], "saeule")
        self.assertEqual(d["matrix"]["breite_px"], 4)
        self.assertEqual(BF.pruefe(d), [])
        neu = BF._soll_profil(d)
        self.assertEqual(neu.bauform, "saeule")
        self.assertEqual(json.loads(neu.matrix_angaben)["hoehe_px"], 3)
        d["bauform"] = "kugel"
        self.assertTrue(any("bauform" in f for f in BF.pruefe(d)))


class MigrationTest(unittest.TestCase):

    def test_alte_fixtures_db_ohne_spalten(self):
        from src.core.database.fixture_db import get_engine
        from src.core.database.models import FixtureProfile
        d = tempfile.mkdtemp(prefix="lightos_fm80_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        pfad = os.path.join(d, "fixtures.db")
        con = sqlite3.connect(pfad)
        con.executescript(
            "CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name VARCHAR(120),"
            " short_name VARCHAR(20));"
            "CREATE TABLE fixtures (id INTEGER PRIMARY KEY, manufacturer_id INTEGER,"
            " name VARCHAR(120), short_name VARCHAR(40), fixture_type VARCHAR(40),"
            " power_w INTEGER, notes TEXT, source VARCHAR(20));"
            "INSERT INTO manufacturers VALUES (1, 'Alt', 'ALT');"
            "INSERT INTO fixtures VALUES (1, 1, 'Altpanel', 'ALTP', 'matrix', 0, '', 'user');")
        con.commit()
        con.close()
        eng = get_engine(pfad)
        self.addCleanup(eng.dispose)
        with Session(eng) as s:
            p = s.get(FixtureProfile, 1)
            self.assertEqual(p.name, "Altpanel")
            self.assertEqual(LM.bauform_von(p), "panel")
            self.assertIsNone(LM.angaben_von_profil(p))


# ════════════════════════════════════════════════════════════════════════════
# 3. Patch: je Teil ein Geraet, Auto-Kopf-Gruppe (FM-21), Gesamt-Gruppe
# ════════════════════════════════════════════════════════════════════════════

class _ShowBasis(unittest.TestCase):

    def setUp(self):
        from src.core.app_state import clear_channel_cache, get_state
        from src.core.show.show_file import reset_show
        from src.core.undo import get_undo_stack
        _app()
        self.eng = frische_library(self)
        clear_channel_cache()
        self.addCleanup(clear_channel_cache)
        reset_show()
        self.addCleanup(reset_show)
        get_undo_stack().clear()
        self.addCleanup(get_undo_stack().clear)
        self.state = get_state()

    def _anlegen(self, **kw):
        from src.core.database import fixture_db as fdb
        a = LM.MatrixAngaben(**kw)
        return a, fdb.create_user_profile(LM.profil_payload(a), engine=self.eng)

    def _gruppe(self, gid):
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            g = s.get(FixtureGroup, gid)
            return g.name, int(g.cols), int(g.rows), json.loads(g.positions_json)

    def _gruppen(self):
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup
        with self.state._session() as s:
            return {g.name: (int(g.cols), int(g.rows), json.loads(g.positions_json))
                    for g in s.execute(select(FixtureGroup)).scalars()}


class PatchTest(_ShowBasis):

    def test_20x40_fuenf_teile_in_fuenf_universen(self):
        _a, pid = self._anlegen(modell="M20x40", breite_px=20, hoehe_px=40)
        fids = LM.matrix_patchen(self.state, pid, start_universum=3)
        self.assertEqual(len(fids), 5)
        fx = {f.fid: f for f in self.state.get_patched_fixtures()}
        self.assertEqual([(fx[f].universe, fx[f].address, fx[f].channel_count)
                          for f in fids], [(u, 1, 480) for u in range(3, 8)])
        for f in fids:
            gid = self.state.find_head_matrix_group(f, dedicated=True)
            self.assertIsNotNone(gid, "Auto-Kopf-Gruppe fehlt")
            _n, cols, rows, pos = self._gruppe(gid)
            self.assertEqual((cols, rows, len(pos)), (20, 8, 160),
                             "FM-21: Teil als 20x8-Rechteck gerastert")
        gesamt = self._gruppen()["M20x40 · Matrix"]
        self.assertEqual((gesamt[0], gesamt[1], len(gesamt[2])), (20, 40, 800))
        # Zeile 8 (0-basiert) = erste Zeile von Teil 2, Kopf 0.
        self.assertEqual(gesamt[2]["0,8"], f"{fids[1]}:0")
        self.assertEqual(gesamt[2]["19,39"], f"{fids[4]}:159")

    def test_schlange_von_unten_links_von_hand(self):
        _a, pid = self._anlegen(modell="S", breite_px=3, hoehe_px=4,
                                verdrahtung="schlange", startecke="unten_links",
                                zeilen_je_teil=3)
        f1, f2 = LM.matrix_patchen(self.state, pid)
        fx = {f.fid: f for f in self.state.get_patched_fixtures()}
        self.assertEqual((fx[f1].pixel_order, fx[f1].element_rotation,
                          bool(fx[f1].element_flip)), ("serpentine", 180, True))
        self.assertEqual(bool(fx[f2].element_flip), False,
                         "Teil 2 beginnt auf ungerader Zeile -> Gegenrichtung")
        _c, _r, pos = self._gruppen()["S · Matrix"]
        # Anzeige (Pixel 1-basiert): [[12,11,10],[7,8,9],[6,5,4],[1,2,3]]
        erwartet = {"0,3": (f1, 0), "1,3": (f1, 1), "2,3": (f1, 2),
                    "2,2": (f1, 3), "0,2": (f1, 5), "0,1": (f1, 6),
                    "2,1": (f1, 8), "2,0": (f2, 0), "0,0": (f2, 2)}
        for zelle, (fid, kopf) in erwartet.items():
            self.assertEqual(pos[zelle], f"{fid}:{kopf}", zelle)
        # Auto-Kopf-Gruppe des ersten Teils (3x3, unten links, Schlange)
        _n, cols, rows, tpos = self._gruppe(
            self.state.find_head_matrix_group(f1, dedicated=True))
        self.assertEqual((cols, rows), (3, 3))
        self.assertEqual(tpos["0,2"], f"{f1}:0")
        self.assertEqual(tpos["0,1"], f"{f1}:5")

    def test_konflikt_patcht_nichts(self):
        _a, pid = self._anlegen(modell="K", breite_px=20, hoehe_px=40)
        LM.matrix_patchen(self.state, pid, start_universum=1)
        n = len(self.state.get_patched_fixtures())
        with self.assertRaises(ValueError):
            LM.matrix_patchen(self.state, pid, start_universum=5)
        self.assertEqual(len(self.state.get_patched_fixtures()), n)

    def test_nie_ueber_das_letzte_universum(self):
        """Pruefung: LightOS patcht Universum 1..32 (wie „Geraet hinzufuegen“
        und die Patch-Tabelle). 5 Teile ab Universum 30 haetten 33 und 34
        belegt — abgelehnt, und es wird nichts gepatcht."""
        from src.core.patch_tabelle import UNIVERSUM_MAX
        self.assertEqual(LM.TEILE_MAX, UNIVERSUM_MAX)
        _a, pid = self._anlegen(modell="U32", breite_px=20, hoehe_px=40)
        n = len(self.state.get_patched_fixtures())
        with self.assertRaisesRegex(ValueError, "Universum 1 bis 32"):
            LM.matrix_patchen(self.state, pid, start_universum=30)
        self.assertEqual(len(self.state.get_patched_fixtures()), n)
        fids = LM.matrix_patchen(self.state, pid, start_universum=28)
        fx = {f.fid: f for f in self.state.get_patched_fixtures()}
        self.assertEqual([fx[f].universe for f in fids], [28, 29, 30, 31, 32])

    def test_30x20_rgbw_jeder_pixel_in_gesamt_und_teilgruppe(self):
        """Eigenes Beispiel der Pruefung: 30x20 RGBW + Master, 3 Zeilen je
        Teil (ungerade, letzter Teil kuerzer), Schlange von unten rechts.
        128 Pixel je Universum -> 3 Zeilen = 90 Pixel = 1 + 360 Kanaele; 7
        Teile, der letzte mit 2 Zeilen (241). Jeder Pixel liegt in Gesamt-
        und Teil-Gruppe dort, wo die Vorschau (pixel_platz) ihn zeigt."""
        a, pid = self._anlegen(modell="R30", breite_px=30, hoehe_px=20,
                               format="RGBW", master=True, verdrahtung="schlange",
                               startecke="unten_rechts", zeilen_je_teil=3)
        fids = LM.matrix_patchen(self.state, pid)
        fx = {f.fid: f for f in self.state.get_patched_fixtures()}
        self.assertEqual([fx[f].channel_count for f in fids], [361] * 6 + [241])
        _c, _r, pos = self._gruppen()["R30 · Matrix"]
        self.assertEqual(len(pos), 600)
        for t, fid in zip(LM.teile(a), fids):
            _n, _cols, _rows, tpos = self._gruppe(
                self.state.find_head_matrix_group(fid, dedicated=True))
            z0 = LM.teil_anzeige_zeile(a, t)
            for k in range(t.zeilen * 30):
                r, c = LM.pixel_platz(a, t.erstes_pixel + k)
                self.assertEqual(pos[f"{c},{r}"], f"{fid}:{k}")
                self.assertEqual(tpos[f"{c},{r - z0}"], f"{fid}:{k}")

    def test_alt_show_mit_panel_laedt_unveraendert(self):
        """Show ohne irgendein FM-80-Feld (Bestandsformat) laedt wie bisher;
        ihr Panel gilt als Bauform 'panel'."""
        from sqlalchemy import select
        from src.core.database.models import FixtureProfile, PatchedFixture
        from src.core.show.show_file import load_show, reset_show, save_show
        with Session(self.eng) as s:
            p = s.execute(select(FixtureProfile).where(
                FixtureProfile.short_name == "MATRIXPANEL")).scalars().first()
            pid, modus = p.id, p.modes[0].name
            n = p.modes[0].channel_count
        self.state.add_fixture(PatchedFixture(
            fid=1, label="Alt", fixture_profile_id=pid, mode_name=modus,
            universe=1, address=1, channel_count=n, fixture_type="matrix",
            pixel_order="serpentine"), undoable=False)
        d = tempfile.mkdtemp(prefix="lightos_fm80_show_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        pfad = os.path.join(d, "alt.lshow")
        save_show(pfad)
        reset_show()
        ok, msg = load_show(pfad)
        self.assertTrue(ok, msg)
        f = next(f for f in self.state.get_patched_fixtures() if f.fid == 1)
        self.assertEqual(f.pixel_order, "serpentine")
        with Session(self.eng) as s:
            self.assertEqual(LM.bauform_von(s.get(FixtureProfile, f.fixture_profile_id)),
                             "panel")


# ════════════════════════════════════════════════════════════════════════════
# 4. Dialog: Vorschau, Speichern, Bearbeiten, Touch
# ════════════════════════════════════════════════════════════════════════════

class DialogTest(_ShowBasis):

    def _dialog(self, **kw):
        from src.ui.widgets.led_matrix_assistent import LedMatrixAssistent
        dlg = LedMatrixAssistent(**kw)
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_vorschau_nummeriert_live(self):
        dlg = self._dialog()
        dlg.sp_breite.setValue(3)
        dlg.sp_hoehe.setValue(2)
        dlg.cb_verdrahtung.setCurrentIndex(dlg.cb_verdrahtung.findData("schlange"))
        self.assertEqual(dlg.vorschau.zelle(1, 0), (5, 0), "Pixel 6 unten links")
        dlg.cb_startecke.setCurrentIndex(dlg.cb_startecke.findData("oben_rechts"))
        self.assertEqual(dlg.vorschau.zelle(0, 2), (0, 0))
        self.assertIn("6 Pixel, 18 Kanäle", dlg.lbl_info.text())
        dlg.resize(600, 400)
        dlg.grab()  # zeichnet ohne Fehler

    def test_zu_breit_sperrt_speichern(self):
        dlg = self._dialog()
        dlg.sp_breite.setValue(200)
        self.assertFalse(dlg.btn_speichern.isEnabled())
        self.assertIn("mehr als ein Universum", dlg.lbl_fehler.text())

    def test_speichern_und_gleich_patchen(self):
        dlg = self._dialog(state=self.state)
        dlg.ed_modell.setText("Testmatrix")
        dlg.sp_breite.setValue(20)
        dlg.sp_hoehe.setValue(40)
        dlg.sp_breite_cm.setValue(30)
        dlg.sp_hoehe_cm.setValue(50)
        dlg.cb_bauform.setCurrentIndex(dlg.cb_bauform.findData("vorhang"))
        self.assertTrue(dlg.chk_patchen.isChecked())
        self.assertEqual(dlg.lbl_abstand.text(), "15 × 12.5 mm")
        self.assertTrue(dlg.speichern())
        self.assertIsNotNone(dlg.saved_id)
        self.assertEqual(len(dlg.gepatchte_fids), 5)
        from src.core.database.models import FixtureProfile
        with Session(self.eng) as s:
            self.assertEqual(s.get(FixtureProfile, dlg.saved_id).bauform, "vorhang")

    def test_universum_bleibt_im_erlaubten_bereich(self):
        from src.core.patch_tabelle import UNIVERSUM_MAX
        dlg = self._dialog(state=self.state)
        self.assertEqual(dlg.sp_universum.maximum(), UNIVERSUM_MAX)
        dlg.sp_breite.setValue(20)
        dlg.sp_hoehe.setValue(40)          # 5 Teile
        dlg.sp_universum.setValue(30)
        self.assertFalse(dlg.btn_speichern.isEnabled())
        self.assertIn("höchstens ab Universum 28", dlg.lbl_fehler.text())
        dlg.chk_patchen.setChecked(False)  # nur Profil anlegen geht weiter
        self.assertTrue(dlg.btn_speichern.isEnabled())

    def test_bearbeiten_aendert_dasselbe_profil(self):
        import src.ui.widgets.led_matrix_assistent as LMA
        from src.core.database.models import FixtureProfile
        _a, pid = self._anlegen(modell="Edit", breite_px=4, hoehe_px=4)
        fragen = []
        echt = LMA._ueberschreiben_fragen
        LMA._ueberschreiben_fragen = lambda *a: fragen.append(a) or True
        self.addCleanup(setattr, LMA, "_ueberschreiben_fragen", echt)
        dlg = self._dialog(profil_id=pid)
        self.assertEqual(dlg.sp_breite.value(), 4)
        self.assertEqual(dlg.btn_speichern.text(), "Profil aktualisieren")
        dlg.cb_format.setCurrentIndex(dlg.cb_format.findData("RGBW"))
        dlg.chk_master.setChecked(True)
        self.assertTrue(dlg.speichern())
        self.assertEqual(dlg.saved_id, pid)
        self.assertEqual(len(fragen), 1)
        with Session(self.eng) as s:
            p = s.get(FixtureProfile, pid)
            self.assertEqual(p.modes[0].channel_count, 1 + 16 * 4)
            self.assertEqual(LM.angaben_von_profil(p).format, "RGBW")

    def test_mitgeliefertes_profil_nicht_im_assistenten(self):
        from sqlalchemy import select
        from src.core.database.models import FixtureProfile
        from src.ui.widgets.led_matrix_assistent import ist_matrix_profil
        with Session(self.eng) as s:
            pid = s.execute(select(FixtureProfile.id).where(
                FixtureProfile.short_name == "MATRIXPANEL")).scalar()
        self.assertFalse(ist_matrix_profil(pid))
        dlg = self._dialog(profil_id=pid)
        self.assertEqual(dlg.btn_speichern.text(), "In Bibliothek speichern",
                         "ein fremdes Profil wird nie ueberschrieben")

    def test_touch_mindestgroesse(self):
        from src.ui import touch_keyboard as TK
        alt = TK.is_touch_mode()
        TK.setze_touch_modus(True)
        self.addCleanup(TK.setze_touch_modus, alt)
        dlg = self._dialog()
        for w in (dlg.btn_speichern, dlg.btn_abbrechen, dlg.sp_breite,
                  dlg.cb_format, dlg.chk_master):
            self.assertGreaterEqual(w.minimumHeight(), 44, w)

    def test_einstiege_vorhanden(self):
        import src.ui.views.patch_view as PV
        pv = PV.PatchView()
        self.addCleanup(pv.deleteLater)
        texte = [b.text() for b in pv.findChildren(QWidget)
                 if hasattr(b, "text") and callable(b.text)]
        self.assertIn("LED-Matrix…", texte)
        self.assertTrue(hasattr(pv, "_open_matrix_assistent"))


if __name__ == "__main__":
    unittest.main()

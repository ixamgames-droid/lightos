"""VIZ-67 (Teil 1): eigene 3D-Dateien (STL/OBJ) als Buehnenobjekt.

* Parser (``src/core/stage/modell_import.py``): STL binaer + ASCII, OBJ mit
  Vierecken/Fuenfeck (Faecher-Triangulierung, negative Indizes), Einheiten,
  Z-oben-Drehung, kaputte Dateien und Grenzen -> verstaendliche Meldung.
* Einbetten: das Netz steht im Buehnenobjekt (``StageElement.model``) und im
  Szenengraph der ``.lshow`` — Speichern, Originaldatei loeschen, in einem
  FRISCHEN Datenordner laden: Objekt mit gleicher Geometrie und Lage wieder da.
* Fenster-Weg: der Import legt ein Buehnenobjekt mit Undo an; eine kaputte
  Datei endet in einer Meldung statt in einer Ausnahme.

Beispieldateien: ``tests/fixtures/viz67/viz67_*``.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage import modell_import as mi            # noqa: E402
from src.core.stage import stage_definition as SD         # noqa: E402

DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "viz67")


def _datei(name):
    return os.path.join(DATEN, name)


def _dreiecke_als_mengen(netz):
    """Geometrie unabhaengig von der Eckpunkt-Reihenfolge vergleichbar machen."""
    p = netz.positionen
    out = set()
    for t in range(netz.dreiecke):
        ecken = []
        for k in range(3):
            i = netz.indizes[3 * t + k]
            ecken.append(tuple(round(p[3 * i + a], 5) for a in range(3)))
        out.add(frozenset(ecken))
    return out


class ParserTest(unittest.TestCase):

    def test_stl_binaer(self):
        netz = mi.lies_datei(_datei("viz67_quader_binaer.stl"), "mm", z_oben=True)
        self.assertEqual(netz.dreiecke, 12)
        self.assertEqual(netz.eckpunkte, 8, "gleiche Eckpunkte nicht zusammengelegt")
        # 100 x 100 x 50 mm, Z oben -> 0,1 breit, 0,05 hoch, 0,1 tief (Meter)
        for ist, soll in zip(netz.groesse, (0.1, 0.05, 0.1)):
            self.assertAlmostEqual(ist, soll, places=6)
        # zentriert
        for a in range(3):
            werte = netz.positionen[a::3]
            self.assertAlmostEqual(min(werte) + max(werte), 0.0, places=6)

    def test_stl_ascii_gleich_binaer(self):
        a = mi.lies_datei(_datei("viz67_quader_ascii.stl"), "mm", z_oben=True)
        b = mi.lies_datei(_datei("viz67_quader_binaer.stl"), "mm", z_oben=True)
        self.assertEqual(_dreiecke_als_mengen(a), _dreiecke_als_mengen(b))

    def test_ohne_z_oben_bleibt_y_die_hoehe(self):
        netz = mi.lies_datei(_datei("viz67_quader_binaer.stl"), "mm", z_oben=False)
        for ist, soll in zip(netz.groesse, (0.1, 0.1, 0.05)):
            self.assertAlmostEqual(ist, soll, places=6)

    def test_einheiten(self):
        for einheit, faktor in (("mm", 0.001), ("cm", 0.01), ("m", 1.0)):
            with self.subTest(einheit=einheit):
                if einheit == "m":   # 100 m waere zu gross -> Meldung
                    with self.assertRaises(mi.ModellImportFehler) as cm:
                        mi.lies_datei(_datei("viz67_quader_binaer.stl"), einheit)
                    self.assertIn("Einheit", str(cm.exception))
                    continue
                netz = mi.lies_datei(_datei("viz67_quader_binaer.stl"), einheit)
                self.assertAlmostEqual(netz.groesse[0], 100 * faktor, places=5)

    def test_obj_mit_vierecken_und_fuenfeck(self):
        netz = mi.lies_datei(_datei("viz67_kiste_quads.obj"), "m")
        # 6 Vierecke -> 12 Dreiecke, Fuenfeck (negative Indizes) -> 3, Linie -> 0
        self.assertEqual(netz.dreiecke, 15)
        self.assertEqual(netz.eckpunkte, 13)
        for ist, soll in zip(netz.groesse, (2.0, 1.5, 0.55)):   # Fuenfeck ragt bis z=0,3
            self.assertAlmostEqual(ist, soll, places=5)
        self.assertLess(max(netz.indizes), netz.eckpunkte)

    def test_kaputte_dateien_melden_statt_abzustuerzen(self):
        for name in ("viz67_kaputt.obj", "viz67_kaputt.stl"):
            with self.subTest(name=name):
                with self.assertRaises(mi.ModellImportFehler) as cm:
                    mi.lies_datei(_datei(name), "mm")
                self.assertTrue(str(cm.exception))
        faelle = {
            "leer": (b"", ".stl"),
            "nur Text": (b"hallo welt", ".stl"),
            "ASCII ohne ganze Dreiecke": (b"solid x\nvertex 0 0 0\nvertex 1 0 0\nendsolid", ".stl"),
            "Zahl kaputt": (b"solid x\nvertex 0 a 0\nvertex 1 0 0\nvertex 0 1 0\n", ".stl"),
            "NaN": (b"v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", ".obj"),
            "OBJ ohne Flaechen": (b"v 0 0 0\nv 1 0 0\n", ".obj"),
            "Index 0": (b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 1 2\n", ".obj"),
            "Index kein Zahl": (b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf a b c\n", ".obj"),
            "alles ein Punkt": (b"v 0 0 0\nv 0 0 0\nv 0 0 0\nf 1 2 3\n", ".obj"),
            "falsche Endung": (b"v 0 0 0\n", ".dxf"),
            "Binaer-STL 0 Dreiecke": (b"\0" * 80 + struct.pack("<I", 0), ".stl"),
        }
        for name, (daten, endung) in faelle.items():
            with self.subTest(name=name):
                with self.assertRaises(mi.ModellImportFehler):
                    mi.lies_bytes(daten, endung, "m")

    def test_dreieck_grenze(self):
        n = mi.MAX_DREIECKE + 1
        kopf = b"\0" * 80 + struct.pack("<I", n)
        dreieck = struct.pack("<12x9f2x", 0, 0, 0, 1, 0, 0, 0, 1, 0)
        with self.assertRaises(mi.ModellImportFehler) as cm:
            mi.lies_bytes(kopf + dreieck * n, ".stl", "m")
        self.assertIn("200.000", str(cm.exception))
        # OBJ: die Grenze greift beim Lesen, nicht erst danach
        zeilen = ["v 0 0 0", "v 1 0 0", "v 0 1 0"] + ["f 1 2 3"] * n
        with self.assertRaises(mi.ModellImportFehler):
            mi.lies_bytes("\n".join(zeilen).encode(), ".obj", "m")

    def test_datei_grenze(self):
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "riesig.stl")
            with open(pfad, "wb") as f:
                f.truncate(mi.MAX_DATEI_BYTES + 1)
            with self.assertRaises(mi.ModellImportFehler) as cm:
                mi.lies_datei(pfad, "mm")
            self.assertIn("MB", str(cm.exception))

    def test_packen_und_entpacken(self):
        netz = mi.lies_datei(_datei("viz67_kiste_quads.obj"), "m")
        text = mi.packen(netz)
        self.assertTrue(text.startswith("lsm1:"))
        zurueck = mi.entpacken(text)
        self.assertEqual(list(zurueck.indizes), list(netz.indizes))
        self.assertEqual(list(zurueck.positionen), list(netz.positionen))
        js = mi.js_daten(text)
        self.assertEqual(set(js), {"key", "pos", "idx"})

    def test_kaputte_einbettung_wird_abgelehnt(self):
        netz = mi.lies_datei(_datei("viz67_kiste_quads.obj"), "m")
        text = mi.packen(netz)
        for kaputt in ("", "lsm1:", "lsm1:!!!", text[:-8], "xyz:" + text[5:]):
            with self.subTest(kaputt=kaputt[:12]):
                with self.assertRaises(mi.ModellImportFehler):
                    mi.entpacken(kaputt)
        self.assertIsNone(mi.js_daten("lsm1:kaputt"))


class ElementTest(unittest.TestCase):

    def test_js_payload_nur_mit_modell_erweitert(self):
        ohne = SD.StageElement(id="el_a", type="platform")
        self.assertNotIn("modell", ohne.to_js_dict())
        self.assertNotIn("model", SD.StageDefinition(elements=[ohne]).to_dict()["elements"][0],
                         "Buehnendateien ohne Import sollen unveraendert bleiben")
        netz = mi.lies_datei(_datei("viz67_kiste_quads.obj"), "m")
        mit = SD.StageElement(id="el_b", type="imported_model", model=mi.packen(netz))
        self.assertIn("modell", mit.to_js_dict())
        self.assertIn("imported_model", SD.SUPPORTED_TYPES)

    def test_typ_ist_ueberall_bekannt(self):
        from src.core.stage.scene_graph import NodeKind
        self.assertEqual(NodeKind("imported_model").value, "imported_model")
        js = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "ui", "visualizer", "scene_src")
        with open(os.path.join(js, "stage", "stage_objects.js"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertIn("imported_model: {", quelle)
        with open(os.path.join(js, "interaction", "tools.js"), encoding="utf-8") as f:
            self.assertIn("imported_model:", f.read())


class RundlaufTest(unittest.TestCase):
    """★ Abnahme: Show auf einem anderen Rechner ohne Originaldatei."""

    NAME = "VIZ67 Rundlauf"

    def setUp(self):
        from src.core.show import show_file as SF
        self.SF = SF
        self.tmp = tempfile.mkdtemp(prefix="viz67_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(SF.reset_show)

    def _ordner(self, name):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        return d

    def test_show_traegt_das_modell_ohne_originaldatei(self):
        from src.core.app_state import get_state
        from src.core.stage.scene_graph import SceneGraph
        SF = self.SF
        # Originaldatei an einen Ort kopieren, den wir danach loeschen.
        original = os.path.join(self.tmp, "kiste.obj")
        shutil.copy(_datei("viz67_kiste_quads.obj"), original)
        netz = mi.lies_datei(original, "m")

        rechner_a = self._ordner("rechner_a_stages")
        with mock.patch.object(SD, "stages_dir", lambda: rechner_a):
            SF.reset_show()
            st = SD.StageDefinition(name=self.NAME)
            el = st.add("imported_model", id="el_import", x=1.5, y=0.75, z=-2.0,
                        w=4.0, h=1.5, d=0.5, rotation=0.7, color="#8c8c8c",
                        name="Kiste", model=mi.packen(netz))
            SD.save_stage(st)
            state = get_state()
            state.active_stage_name = self.NAME
            SF._replace_scene(state, SceneGraph.from_legacy(
                positions={}, rotations={}, docks={}, active_stage_name=self.NAME,
                live_view_positions={}, stage_def=st))
            pfad = os.path.join(self.tmp, "show.lshow")
            ok = SF.save_show(pfad)
            self.assertNotEqual(ok, False)
        os.remove(original)
        shutil.rmtree(rechner_a)

        # Rechner B: frischer, leerer Buehnen-Ordner.
        rechner_b = self._ordner("rechner_b_stages")
        with mock.patch.object(SD, "stages_dir", lambda: rechner_b):
            SF.reset_show()
            self.assertIsNone(SD.load_stage(self.NAME))
            ok, msg = SF.load_show(pfad)
            self.assertTrue(ok, msg)
            geladen = SD.load_stage(self.NAME)
            self.assertIsNotNone(geladen, "Buehne fehlt nach dem Laden")
            els = {e.id: e for e in geladen.elements}
            self.assertIn("el_import", els, "importiertes Modell fehlt nach dem Laden")
            b = els["el_import"]
            self.assertEqual(("imported_model", "Kiste"), (b.type, b.name))
            for ist, soll in zip((b.x, b.y, b.z, b.w, b.h, b.d),
                                 (el.x, el.y, el.z, el.w, el.h, el.d)):
                self.assertAlmostEqual(ist, soll, places=6)
            self.assertAlmostEqual(b.rotation, 0.7, places=6)
            zurueck = mi.entpacken(b.model)
            self.assertEqual(_dreiecke_als_mengen(zurueck), _dreiecke_als_mengen(netz))
            # ... und der Szenengraph der geladenen Show traegt es weiter
            knoten = get_state()._scene.get("el_import")
            self.assertIsNotNone(knoten)
            self.assertEqual(knoten.model, b.model)
            self.assertEqual(json.loads(json.dumps(knoten.model)), b.model)


class FensterImportTest(unittest.TestCase):
    """Der Knopf-Weg ohne echtes Fenster (wie test_viz68_objekt_bibliothek)."""

    def _fake(self):
        from unittest.mock import MagicMock
        from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
        QApplication.instance() or QApplication([])
        import src.ui.visualizer.visualizer_window as VW
        tabs = QTabWidget()
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            tabs.addTab(QWidget(), name)
        tree = MagicMock()
        tree.topLevelItemCount.return_value = 0
        fake = SimpleNamespace(
            _state=SimpleNamespace(), _current_stage=SD.StageDefinition(),
            _tabs=tabs, _stage_tree=tree, _lbl_info=MagicMock(), _bridge=MagicMock(),
            _stage_dirty=False, _selected_stage_id="",
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _sync_stage_node_to_scene=MagicMock(), _remove_stage_node_from_scene=MagicMock(),
            _refresh_stage_tree=MagicMock(), _update_status_counts=MagicMock(),
            _set_build_mode=lambda build=True: None,
        )
        fake._add_stage_element = lambda t, vorgaben=None: VW.VisualizerWindow._add_stage_element(
            fake, t, vorgaben=vorgaben)
        self._tabs = tabs
        return VW, fake

    def tearDown(self):
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()

    def test_import_legt_objekt_mit_undo_an(self):
        from src.core.undo import get_undo_stack
        VW, fake = self._fake()
        get_undo_stack().clear()
        el = VW.VisualizerWindow._import_model_file(
            fake, _datei("viz67_quader_binaer.stl"), "mm", True)
        self.assertIsNotNone(el)
        self.assertEqual([e.id for e in fake._current_stage.elements], [el.id])
        self.assertEqual(el.type, "imported_model")
        self.assertEqual(el.name, "viz67_quader_binaer")
        self.assertAlmostEqual(el.w, 0.1, places=5)
        self.assertAlmostEqual(el.h, 0.05, places=5)
        self.assertAlmostEqual(el.y, 0.025, places=5, msg="steht nicht auf dem Boden")
        self.assertTrue(el.model.startswith("lsm1:"))
        gesendet = fake._bridge.push_add_stage_object_data.call_args[0][0]
        self.assertIn("modell", gesendet.to_js_dict(), "Netz geht nicht an die 3D-Seite")
        get_undo_stack().undo()
        self.assertEqual(fake._current_stage.elements, [])
        get_undo_stack().redo()
        self.assertEqual(len(fake._current_stage.elements), 1)

    def test_dialog_abbrechen_importiert_nichts(self):
        """Review: Esc/Schliessen in der Ausrichtungs-Frage bricht ab."""
        VW, fake = self._fake()
        fake._import_model_file = mock.MagicMock()
        pfad = _datei("viz67_quader_binaer.stl")
        SB = VW.QMessageBox.StandardButton
        with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName",
                        return_value=(pfad, "")), \
             mock.patch.object(VW.QInputDialog, "getItem",
                               return_value=("Millimeter (mm)", True)):
            with mock.patch.object(VW.QMessageBox, "question", return_value=SB.Cancel):
                VW.VisualizerWindow._on_import_model_clicked(fake)
            fake._import_model_file.assert_not_called()
            with mock.patch.object(VW.QMessageBox, "question", return_value=SB.Yes):
                VW.VisualizerWindow._on_import_model_clicked(fake)
        fake._import_model_file.assert_called_once_with(pfad, "mm", True)

    def test_kaputte_datei_meldet(self):
        VW, fake = self._fake()
        with mock.patch.object(VW.QMessageBox, "warning") as warnung:
            el = VW.VisualizerWindow._import_model_file(fake, _datei("viz67_kaputt.obj"), "m")
        self.assertIsNone(el)
        self.assertEqual(warnung.call_count, 1)
        self.assertEqual(fake._current_stage.elements, [])


if __name__ == "__main__":
    unittest.main()

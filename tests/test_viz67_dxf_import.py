"""VIZ-67 (Teil 2): DXF-Dateien (ASCII) als Buehnenobjekt.

* Parser (``src/core/stage/dxf_import.py``): 3DFACE, Polyface-Netz (Flag 64),
  Polygon-Netz (Flag 16), MESH, LINE/LWPOLYLINE/CIRCLE/ARC, Bloecke ueber
  INSERT, Objekt-Koordinatensystem (210/220/230), $INSUNITS, kaputte und
  binaere Dateien, Grenzen.
* Linien reisen eingebettet mit (Format ``LSM2``); ohne Linien bleibt das
  Format ``LSM1`` — alte Shows laden unveraendert.
* Rundlauf: Show mit DXF-Grundriss speichern, Original loeschen, in einem
  frischen Datenordner laden.
* Fenster-Weg: Einheiten-Vorschlag aus der Datei, keine Ausrichtungs-Frage,
  „Linien als Waende?" mit Abbrechen, Hinweise nach dem Import.

Beispieldateien: ``tests/fixtures/viz67/viz67_*.dxf``.
"""
from __future__ import annotations

import base64
import os
import shutil
import tempfile
import unittest
import zlib
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage import dxf_import as dx               # noqa: E402
from src.core.stage import modell_import as mi            # noqa: E402
from src.core.stage import stage_definition as SD         # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(HIER, "fixtures", "viz67")
ANLEITUNG = os.path.join(HIER, "..", "docs", "anleitung_3d_visualizer_2026",
                         "ANLEITUNG_3D_BUEHNE.md")


def _datei(name):
    return os.path.join(DATEN, name)


def _dxf(entities, header=None, bloecke=None) -> bytes:
    """Kleine DXF aus (code, wert)-Paaren bauen."""
    teile = []
    if header is not None:
        teile += [(0, "SECTION"), (2, "HEADER")] + header + [(0, "ENDSEC")]
    if bloecke is not None:
        teile += [(0, "SECTION"), (2, "BLOCKS")] + bloecke + [(0, "ENDSEC")]
    teile += [(0, "SECTION"), (2, "ENTITIES")] + entities + [(0, "ENDSEC"), (0, "EOF")]
    return "".join(f"{c}\n{w}\n" for c, w in teile).encode("ascii")


def _strecken(netz):
    p = netz.positionen
    out = set()
    for k in range(netz.strecken):
        ecken = []
        for j in range(2):
            i = netz.linien[2 * k + j]
            ecken.append(tuple(round(p[3 * i + a], 4) + 0.0 for a in range(3)))
        out.add(frozenset(ecken))
    return out


class ParserTest(unittest.TestCase):

    def setUp(self):
        dx._letzter = (b"", None)   # Merk-Ergebnis leeren (Grenzen-Tests patchen)

    def test_3dface_und_polyface(self):
        netz = mi.lies_datei(_datei("viz67_flaechen.dxf"), "mm", True)
        # 3DFACE-Dreieck (1) + 3DFACE-Viereck (2) + Polyface mit 2 Flaechen
        self.assertEqual(netz.dreiecke, 5)
        self.assertEqual(netz.strecken, 0)
        # 0..3000 mm in X, 0..1000 in Z (oben), 0..1000 in Y -> Meter, Y oben
        for ist, soll in zip(netz.groesse, (3.0, 1.0, 1.0)):
            self.assertAlmostEqual(ist, soll, places=5)
        self.assertEqual(netz.hinweise, ())

    def test_grundriss_linien_bloecke_und_hinweise(self):
        netz = mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True)
        self.assertEqual(netz.dreiecke, 0)
        # Rechteck (4) + LINE (1) + zwei eingesetzte Bloecke (je 1)
        self.assertEqual(netz.strecken, 7)
        for ist, soll in zip(netz.groesse, (10.0, 0.0, 8.0)):
            self.assertAlmostEqual(ist, soll, places=5)
        s = _strecken(netz)
        # Weltpunkt (x, y) -> (x, 0, -y), zentriert um (5, 0, -4)
        def welt(x, y):
            return (round(x - 5.0, 4) + 0.0, 0.0, round(-y + 4.0, 4) + 0.0)
        self.assertIn(frozenset({welt(0, 0), welt(10, 0)}), s)
        self.assertIn(frozenset({welt(0, 8), welt(0, 0)}), s, "geschlossene LWPOLYLINE")
        self.assertIn(frozenset({welt(2, 2), welt(2, 3)}), s, "INSERT um 90° gedreht")
        self.assertIn(frozenset({welt(7, 2), welt(9, 2)}), s, "INSERT mit Faktor 2")
        self.assertTrue(any("TEXT" in h for h in netz.hinweise), netz.hinweise)

    def test_linien_als_waende(self):
        netz = mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True, wand_hoehe_m=3.0)
        self.assertEqual(netz.strecken, 0)
        self.assertEqual(netz.dreiecke, 14)
        self.assertAlmostEqual(netz.groesse[1], 3.0, places=5)
        with self.assertRaises(mi.ModellImportFehler):
            mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True, wand_hoehe_m=0.0)

    def test_insunits(self):
        self.assertEqual(mi.dxf_info(_datei("viz67_flaechen.dxf")).einheit, "mm")
        info = mi.dxf_info(_datei("viz67_grundriss.dxf"))
        self.assertEqual((info.einheit, info.linien, info.dreiecke), ("m", 7, 0))
        linie = [(0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0)]
        for code, soll in ((1, "in"), (2, "ft"), (5, "cm"), (0, None), (99, None)):
            with self.subTest(code=code):
                roh = dx.lies_dxf(_dxf(linie, header=[(9, "$INSUNITS"), (70, code)]))
                self.assertEqual(roh.einheit, soll)
        self.assertIsNone(dx.lies_dxf(_dxf(linie)).einheit, "ohne HEADER")
        netz = mi.lies_bytes(_dxf(linie), ".dxf", "in")
        self.assertAlmostEqual(netz.groesse[0], 0.0254, places=6)

    def test_polygon_netz_mesh_und_boegen(self):
        # Polygon-Netz 2 x 2 (Flag 16) = ein Viereck = 2 Dreiecke
        pm = [(0, "POLYLINE"), (66, 1), (70, 16), (71, 2), (72, 2)]
        for p in ((0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0)):
            pm += [(0, "VERTEX"), (10, p[0]), (20, p[1]), (30, p[2]), (70, 64)]
        pm += [(0, "SEQEND")]
        self.assertEqual(mi.lies_bytes(_dxf(pm), ".dxf", "m").dreiecke, 2)
        # MESH: 4 Punkte, eine Vierecks-Flaeche
        me = [(0, "MESH"), (71, 2), (72, 0), (91, 0), (92, 4)]
        for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)):
            me += [(10, p[0]), (20, p[1]), (30, p[2])]
        me += [(93, 5), (90, 4), (90, 0), (90, 1), (90, 2), (90, 3), (94, 0)]
        self.assertEqual(mi.lies_bytes(_dxf(me), ".dxf", "m").dreiecke, 2)
        # Kreis r=1 -> Durchmesser 2; Viertelbogen
        kreis = [(0, "CIRCLE"), (10, 0), (20, 0), (30, 0), (40, 1)]
        netz = mi.lies_bytes(_dxf(kreis), ".dxf", "m")
        self.assertEqual(netz.strecken, dx._KREIS_SEGMENTE)
        self.assertAlmostEqual(netz.groesse[0], 2.0, places=5)
        bogen = [(0, "ARC"), (10, 0), (20, 0), (30, 0), (40, 1), (50, 0), (51, 90)]
        self.assertEqual(mi.lies_bytes(_dxf(bogen), ".dxf", "m").strecken,
                         dx._KREIS_SEGMENTE // 4)

    def test_ocs_gespiegelt(self):
        """Extrusion (0, 0, -1) — haeufig bei gespiegelten Zeichnungen: X kippt."""
        lw = [(0, "LWPOLYLINE"), (90, 2), (70, 0), (10, 1), (20, 0), (10, 3), (20, 0),
              (210, 0), (220, 0), (230, -1)]
        roh = dx.lies_dxf(_dxf(lw))
        xs = sorted(roh.pos[0::3])
        self.assertEqual(xs, [-3.0, -1.0])

    def test_papierbereich_wird_ignoriert(self):
        linien = [(0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0),
                  (0, "LINE"), (67, 1), (10, 0), (20, 0), (30, 0), (11, 50), (21, 0), (31, 0)]
        self.assertEqual(dx.lies_dxf(_dxf(linien)).linien, 1)

    def test_kaputte_und_binaere_dateien_melden(self):
        with self.assertRaises(mi.ModellImportFehler) as ctx:
            mi.lies_datei(_datei("viz67_kaputt.dxf"), "m", True)
        self.assertIn("Zeile", str(ctx.exception))
        faelle = {
            "binaer": (b"AutoCAD Binary DXF\r\n\x1a\x00" + bytes(200), "Binäre DXF"),
            "nur_text": (b"0\nSECTION\n2\nENTITIES\n0\nTEXT\n1\nHallo\n0\nENDSEC\n0\nEOF\n",
                         "keine verwendbare Geometrie"),
            "kein_dxf": (b"Das ist keine Zeichnung\nsondern Text\n", "Gruppencode"),
            "zahl": (_dxf([(0, "LINE"), (10, "x"), (20, 0), (11, 1), (21, 1)]), "Zahl"),
            "unendlich": (_dxf([(0, "LINE"), (10, "inf"), (20, 0), (11, 1), (21, 1)]),
                          "unendlich"),
            "polyface_index": (_dxf(
                [(0, "POLYLINE"), (70, 64), (0, "VERTEX"), (10, 0), (20, 0), (30, 0), (70, 192),
                 (0, "VERTEX"), (70, 128), (71, 1), (72, 2), (73, 9), (0, "SEQEND")]),
                "Eckpunkt"),
            "mesh_index": (_dxf([(0, "MESH"), (92, 1), (10, 0), (20, 0), (30, 0),
                                 (93, 4), (90, 3), (90, 0), (90, 1), (90, 2)]), "Eckpunkt"),
            "leer": (b"", "leer"),
            "abgeschnitten": (_dxf([(0, "3DFACE"), (10, 0), (20, 0), (30, 0)])[:-30],
                              "Geometrie"),
        }
        for name, (daten, wort) in faelle.items():
            with self.subTest(name=name):
                with self.assertRaises(mi.ModellImportFehler) as ctx:
                    mi.lies_bytes(daten, ".dxf", "m")
                self.assertIn(wort, str(ctx.exception))

    def test_volumenkoerper_werden_gemeldet(self):
        e = [(0, "3DSOLID"), (1, "acis"), (0, "LINE"), (10, 0), (20, 0), (30, 0),
             (11, 1), (21, 0), (31, 0)]
        roh = dx.lies_dxf(_dxf(e))
        text = " ".join(roh.hinweise)
        self.assertIn("3DSOLID", text)
        self.assertIn("STL", text)

    def test_block_rekursion_endet(self):
        bl = [(0, "BLOCK"), (2, "A"), (10, 0), (20, 0), (30, 0),
              (0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0),
              (0, "INSERT"), (2, "A"), (10, 0), (20, 0), (30, 0), (0, "ENDBLK")]
        roh = dx.lies_dxf(_dxf([(0, "INSERT"), (2, "A"), (10, 0), (20, 0), (30, 0)],
                               bloecke=bl))
        self.assertEqual(roh.linien, 1, "gleiche Strecke je Ebene zusammengelegt")
        self.assertTrue(any("verschachtelt" in h for h in roh.hinweise))

    def test_block_vervielfachung_endet_schnell(self):
        """Ein Block, der sich zehnmal selbst einsetzt: 10^8 Aufrufe bis zur
        Tiefengrenze. Gleiche Strecken werden zusammengelegt, die Linien-
        Grenze greift also nie — ohne eigene Arbeitsgrenze haengt der Import."""
        import time
        bl = [(0, "BLOCK"), (2, "A"), (10, 0), (20, 0), (30, 0),
              (0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0)]
        for _ in range(10):
            bl += [(0, "INSERT"), (2, "A"), (10, 0), (20, 0), (30, 0)]
        bl += [(0, "ENDBLK")]
        start = time.monotonic()
        with self.assertRaises(mi.ModellImportFehler) as ctx:
            dx.lies_dxf(_dxf([(0, "INSERT"), (2, "A"), (10, 0), (20, 0), (30, 0)],
                             bloecke=bl))
        self.assertIn("Blöcke", str(ctx.exception))
        self.assertLess(time.monotonic() - start, 30.0)

    def test_sonderzeichen_im_text_verschieben_keine_zeilen(self):
        """Nur Zeilenumbrueche trennen Zeilen — nicht jedes Zeichen, das
        ``str.splitlines`` als Umbruch zaehlt (z. B. U+2028, \\x1c, \\x0c)."""
        e = [(0, "TEXT"), (1, "Bühne Saal\x1cA\x0cB"),
             (0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0)]
        daten = "".join(f"{c}\r\n{w}\r\n" for c, w in
                        [(0, "SECTION"), (2, "ENTITIES")] + e
                        + [(0, "ENDSEC"), (0, "EOF")]).encode("utf-8")
        roh = dx.lies_dxf(daten)
        self.assertEqual(roh.linien, 1)
        self.assertTrue(any("TEXT" in h for h in roh.hinweise), roh.hinweise)

    def test_grenzen(self):
        with mock.patch.object(dx, "MAX_DREIECKE", 3):
            with self.assertRaises(mi.ModellImportFehler) as ctx:
                mi.lies_datei(_datei("viz67_flaechen.dxf"), "mm", True)
            self.assertIn("Dreiecke", str(ctx.exception))
        with mock.patch.object(dx, "MAX_LINIEN", 5):
            with self.assertRaises(mi.ModellImportFehler) as ctx:
                mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True)
            self.assertIn("Linien", str(ctx.exception))
        with mock.patch.object(mi, "MAX_DATEI_BYTES", 100):
            with self.assertRaises(mi.ModellImportFehler) as ctx:
                mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True)
            self.assertIn("MB", str(ctx.exception))
        # Einheit falsch (Meter statt Millimeter) -> zu gross fuer die Buehne
        with self.assertRaises(mi.ModellImportFehler):
            mi.lies_datei(_datei("viz67_flaechen.dxf"), "m", True)


class EinbettungTest(unittest.TestCase):

    def _magie(self, text):
        return zlib.decompress(base64.b64decode(text[5:]))[:4]

    def test_linien_reisen_eingebettet(self):
        netz = mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True)
        text = mi.packen(netz)
        self.assertTrue(text.startswith("lsm1:"))
        self.assertEqual(self._magie(text), b"LSM2")
        zurueck = mi.entpacken(text)
        self.assertEqual(list(zurueck.linien), list(netz.linien))
        self.assertEqual(list(zurueck.positionen), list(netz.positionen))
        self.assertEqual(zurueck.dreiecke, 0)
        js = mi.js_daten(text)
        self.assertEqual(set(js), {"key", "pos", "idx", "lin"})
        self.assertEqual(js["idx"], "")

    def test_ohne_linien_bleibt_das_alte_format(self):
        """Abwaertskompatibel: Flaechen-Modelle packen byte-gleich wie Teil 1."""
        netz = mi.lies_datei(_datei("viz67_flaechen.dxf"), "mm", True)
        text = mi.packen(netz)
        self.assertEqual(self._magie(text), b"LSM1")
        self.assertNotIn("lin", mi.js_daten(text))
        alt = mi.lies_datei(_datei("viz67_kiste_quads.obj"), "m")
        self.assertEqual(self._magie(mi.packen(alt)), b"LSM1")
        self.assertEqual(mi.entpacken(mi.packen(alt)).strecken, 0)

    def test_kaputte_lsm2_wird_abgelehnt(self):
        import struct
        netz = mi.lies_datei(_datei("viz67_grundriss.dxf"), "m", True)
        roh = zlib.decompress(base64.b64decode(mi.packen(netz)[5:]))
        def verpacken(b):
            return "lsm1:" + base64.b64encode(zlib.compress(b)).decode("ascii")
        nv, nt, nl = struct.unpack_from("<III", roh, 4)
        kaputt = {
            "abgeschnitten": roh[:-4],
            "ohne_linien": b"LSM2" + struct.pack("<III", nv, 0, 0) + roh[16:16 + 12 * nv],
            "index_zu_gross": roh[:-4] + struct.pack("<I", nv + 5),
            "zu_viele": b"LSM2" + struct.pack("<III", nv, nt, mi.MAX_LINIEN + 1) + roh[16:],
        }
        for name, b in kaputt.items():
            with self.subTest(name=name):
                with self.assertRaises(mi.ModellImportFehler):
                    mi.entpacken(verpacken(b))


class RundlaufTest(unittest.TestCase):
    """★ Show mit DXF-Grundriss auf einem anderen Rechner ohne Originaldatei."""

    NAME = "VIZ67 DXF Rundlauf"

    def setUp(self):
        from src.core.show import show_file as SF
        self.SF = SF
        self.tmp = tempfile.mkdtemp(prefix="viz67dxf_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(SF.reset_show)

    def test_show_traegt_linien_ohne_originaldatei(self):
        from src.core.app_state import get_state
        from src.core.stage.scene_graph import SceneGraph
        SF = self.SF
        original = os.path.join(self.tmp, "halle.dxf")
        shutil.copy(_datei("viz67_grundriss.dxf"), original)
        netz = mi.lies_datei(original, "m", True)
        rechner_a = os.path.join(self.tmp, "a")
        os.makedirs(rechner_a)
        with mock.patch.object(SD, "stages_dir", lambda: rechner_a):
            SF.reset_show()
            st = SD.StageDefinition(name=self.NAME)
            w, h, d = mi.element_groesse(netz)
            st.add("imported_model", id="el_halle", x=0.0, y=h / 2, z=0.0,
                   w=w, h=h, d=d, color="#8c8c8c", name="Halle", model=mi.packen(netz))
            SD.save_stage(st)
            state = get_state()
            state.active_stage_name = self.NAME
            SF._replace_scene(state, SceneGraph.from_legacy(
                positions={}, rotations={}, docks={}, active_stage_name=self.NAME,
                live_view_positions={}, stage_def=st))
            pfad = os.path.join(self.tmp, "show.lshow")
            self.assertNotEqual(SF.save_show(pfad), False)
        os.remove(original)
        shutil.rmtree(rechner_a)

        rechner_b = os.path.join(self.tmp, "b")
        os.makedirs(rechner_b)
        with mock.patch.object(SD, "stages_dir", lambda: rechner_b):
            SF.reset_show()
            ok, msg = SF.load_show(pfad)
            self.assertTrue(ok, msg)
            geladen = SD.load_stage(self.NAME)
            self.assertIsNotNone(geladen)
            b = {e.id: e for e in geladen.elements}["el_halle"]
            zurueck = mi.entpacken(b.model)
            self.assertEqual(zurueck.strecken, 7)
            self.assertEqual(_strecken(zurueck), _strecken(netz))
            self.assertIn("lin", b.to_js_dict()["modell"])
            self.assertEqual(get_state()._scene.get("el_halle").model, b.model)


class FensterImportTest(unittest.TestCase):
    """Dialog-Weg fuer DXF ohne echtes Fenster (wie test_viz67_modell_import)."""

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

    def _klick(self, VW, fake, pfad, antwort, hoehe=(2.5, True)):
        einheit_frage = mock.MagicMock(side_effect=lambda *a: (a[3][a[4]], True))
        with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName",
                        return_value=(pfad, "")) as datei, \
             mock.patch.object(VW.QInputDialog, "getItem", einheit_frage), \
             mock.patch.object(VW.QInputDialog, "getDouble", return_value=hoehe) as hoch, \
             mock.patch.object(VW.QMessageBox, "question", return_value=antwort) as frage:
            VW.VisualizerWindow._on_import_model_clicked(fake)
        return datei, einheit_frage, hoch, frage

    def test_dateifilter_kennt_dxf(self):
        VW, fake = self._fake()
        datei, *_ = self._klick(VW, fake, "", None)
        self.assertIn("*.dxf", datei.call_args[0][3])

    def test_einheit_vorgeschlagen_und_waende(self):
        VW, fake = self._fake()
        fake._import_model_file = mock.MagicMock()
        SB = VW.QMessageBox.StandardButton
        pfad = _datei("viz67_grundriss.dxf")
        _d, einheit, hoch, frage = self._klick(VW, fake, pfad, SB.Yes)
        args = einheit.call_args[0]
        self.assertEqual(args[3][args[4]], "Meter (m)", "$INSUNITS nicht vorgewählt")
        self.assertIn("Die Datei gibt an", args[2])
        self.assertEqual(frage.call_count, 1, "nur die Wand-Frage, keine Ausrichtungs-Frage")
        self.assertIn("Wände", frage.call_args[0][1])
        fake._import_model_file.assert_called_once_with(pfad, "m", True, wand_hoehe_m=2.5)

    def test_flache_linien_und_abbrechen(self):
        VW, fake = self._fake()
        fake._import_model_file = mock.MagicMock()
        SB = VW.QMessageBox.StandardButton
        pfad = _datei("viz67_grundriss.dxf")
        self._klick(VW, fake, pfad, SB.Cancel)
        fake._import_model_file.assert_not_called()
        self._klick(VW, fake, pfad, SB.Yes, hoehe=(0.0, False))
        fake._import_model_file.assert_not_called()
        self._klick(VW, fake, pfad, SB.No)
        fake._import_model_file.assert_called_once_with(pfad, "m", True, wand_hoehe_m=None)

    def test_ohne_linien_keine_wandfrage(self):
        VW, fake = self._fake()
        fake._import_model_file = mock.MagicMock()
        pfad = _datei("viz67_flaechen.dxf")
        _d, einheit, _h, frage = self._klick(VW, fake, pfad, None)
        args = einheit.call_args[0]
        self.assertEqual(args[3][args[4]], "Millimeter (mm)")
        frage.assert_not_called()
        fake._import_model_file.assert_called_once_with(pfad, "mm", True, wand_hoehe_m=None)

    def test_kaputte_dxf_meldet_schon_beim_vorab_lesen(self):
        VW, fake = self._fake()
        fake._import_model_file = mock.MagicMock()
        with mock.patch.object(VW.QMessageBox, "warning") as warnung:
            self._klick(VW, fake, _datei("viz67_kaputt.dxf"), None)
        self.assertEqual(warnung.call_count, 1)
        fake._import_model_file.assert_not_called()

    def test_import_legt_objekt_an_und_nennt_hinweise(self):
        VW, fake = self._fake()
        with mock.patch.object(VW.QMessageBox, "information") as info:
            el = VW.VisualizerWindow._import_model_file(
                fake, _datei("viz67_grundriss.dxf"), "m", True)
        self.assertIsNotNone(el)
        self.assertEqual(el.type, "imported_model")
        self.assertAlmostEqual(el.w, 10.0, places=4)
        self.assertAlmostEqual(el.d, 8.0, places=4)
        self.assertAlmostEqual(el.h, mi.MIN_GROESSE_M, places=6)
        self.assertEqual(mi.entpacken(el.model).strecken, 7)
        self.assertEqual(info.call_count, 1)
        self.assertIn("TEXT", info.call_args[0][2])
        with mock.patch.object(VW.QMessageBox, "information") as info:
            el2 = VW.VisualizerWindow._import_model_file(
                fake, _datei("viz67_grundriss.dxf"), "m", True, wand_hoehe_m=4.0)
        self.assertAlmostEqual(el2.h, 4.0, places=4)
        self.assertEqual(mi.entpacken(el2.model).dreiecke, 14)


class AnleitungTest(unittest.TestCase):

    def test_anleitung_beschreibt_dxf(self):
        with open(ANLEITUNG, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("DXF folgt später", text)
        for wort in ("DXF-Zeichnungen", "ASCII-DXF", "$INSUNITS", "Linien als Wände",
                     "Wandhöhe", "glTF"):
            self.assertIn(wort, text)


if __name__ == "__main__":
    unittest.main()

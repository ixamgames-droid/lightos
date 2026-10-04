"""VIZ-68 — Objekt-Bibliothek fuer den 3D-Viewer (Event-Moebel).

Neue Buehnenobjekte, wie VIZ-66 komplett im Code gebaut (keine Modelldateien):
Biertischgarnitur, Stehtisch, Bar/Theke, Podest mit Treppe — je Typ ein Knopf
im Buehnen-Tab, Speichern/Laden ueber die bestehende Buehnendefinition.

Die Typen stehen an mehreren Stellen (Python-Typliste, Andock-Klassen,
Szenengraph, Knoepfe + Standardmasse, JS-Bauplaene, 2D-Farben, Statusleiste).
Dieser Test haelt sie zusammen — ein Typ, der nur auf einer Seite existiert,
waere ein Knopf ohne 3D-Koerper oder ein geladenes Objekt, das verschwindet.

Die Szenen-Tests bauen jedes Objekt in der ECHTEN Seite (stage_scene.html) und
pruefen, dass die Form ihre Bounding-Box exakt fuellt — in Standard- und in
geaenderter Groesse (das Groesse-Aendern baut neu).
"""
from __future__ import annotations

import json
import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.stage import stage_definition as sd          # noqa: E402
from src.core.stage.scene_graph import NodeKind            # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(REPO, "src", "ui", "visualizer", "scene_src")
NEU = ("beer_table", "high_table", "bar_counter", "riser_stairs", "foh_desk")


def _js(*teile) -> str:
    with open(os.path.join(JS, *teile), encoding="utf-8") as f:
        return f.read()


def _js_objekt_schluessel(quelle: str, name: str) -> set[str]:
    """Schluessel eines ``export const NAME = { ... };`` (oberste Ebene)."""
    start = quelle.index(f"export const {name}")
    rumpf = quelle[quelle.index("{", start) + 1:]
    tiefe, ende = 1, 0
    for i, ch in enumerate(rumpf):
        tiefe += ch == "{"
        tiefe -= ch == "}"
        if tiefe == 0:
            ende = i
            break
    rumpf = rumpf[:ende]
    schluessel, tiefe = set(), 0
    for zeile in rumpf.splitlines():
        if tiefe == 0:
            m = re.match(r"\s*([a-z_]+)\s*:", zeile)
            if m:
                schluessel.add(m.group(1))
        tiefe += zeile.count("{") - zeile.count("}")
    return schluessel


class TypenKonsistenzTest(unittest.TestCase):

    def test_neue_typen_ueberall_bekannt(self):
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        knopf_typen = [t for t, _ in VisualizerWindow.STAGE_TYPES]
        blaupausen = _js_objekt_schluessel(_js("stage", "stage_objects.js"), "STAGE_BLUEPRINTS")
        farben_2d = _js_objekt_schluessel(_js("stage", "stage_objects.js"), "STAGE_2D_COLORS")
        statuszeile = _js("interaction", "tools.js")
        for typ in NEU:
            with self.subTest(typ=typ):
                self.assertIn(typ, sd.SUPPORTED_TYPES)
                self.assertIn(typ, knopf_typen, "kein Knopf im Buehnen-Tab")
                self.assertIn(typ, VisualizerWindow.STAGE_DEFAULTS)
                self.assertEqual(NodeKind(typ).value, typ)
                self.assertIn(typ, blaupausen, "kein 3D-Bauplan")
                self.assertIn(typ, farben_2d, "keine 2D-Darstellung")
                self.assertIn(f"{typ}:", statuszeile, "kein Name in der Statuszeile")

    def test_jeder_knopf_hat_bauplan_und_standardwerte(self):
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        blaupausen = _js_objekt_schluessel(_js("stage", "stage_objects.js"), "STAGE_BLUEPRINTS")
        for typ, _label in VisualizerWindow.STAGE_TYPES:
            with self.subTest(typ=typ):
                self.assertIn(typ, blaupausen)
                self.assertIn(typ, VisualizerWindow.STAGE_DEFAULTS)
                d = VisualizerWindow.STAGE_DEFAULTS[typ]
                if typ in NEU:   # neue Moebel stehen auf dem Boden
                    self.assertAlmostEqual(d["y"], d["h"] / 2, places=3,
                                           msg="Objekt steht nicht auf dem Boden")

    def test_andock_klassen_python_und_js_gleich(self):
        m = re.search(r"DOCK_TOP_TYPES\s*=\s*\{([^}]*)\}", _js("stage", "docking.js"))
        js_top = set(re.findall(r"([a-z_]+)\s*:", m.group(1)))
        self.assertEqual(js_top, set(sd.DOCK_TOP_TYPES))
        self.assertIn("bar_counter", sd.DOCK_TOP_TYPES)
        self.assertNotIn("foh_desk", sd.DOCK_TOP_TYPES)
        self.assertIn("riser_stairs", sd.DOCK_TOP_TYPES)
        self.assertNotIn("beer_table", sd.DOCK_TOP_TYPES)

    def test_knopf_legt_mit_den_standardwerten_an(self):
        import inspect
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        quelle = inspect.getsource(VisualizerWindow._add_stage_element)
        self.assertIn("STAGE_DEFAULTS", quelle)


class SpeichernLadenTest(unittest.TestCase):

    def test_roundtrip_ueber_buehnendatei(self):
        st = sd.StageDefinition(name="viz68-test")
        for i, typ in enumerate(NEU):
            st.add(typ, x=i, y=0.5, z=-i, w=1.5 + i, h=1.0, d=0.9, color="#123456",
                   name=f"Objekt {i}", rotation=0.5)
        zurueck = sd.StageDefinition.from_dict(json.loads(json.dumps(st.to_dict())))
        self.assertEqual([e.type for e in zurueck.elements], list(NEU))
        for a, b in zip(st.elements, zurueck.elements):
            self.assertEqual((a.w, a.h, a.d, a.color, a.name, a.rotation),
                             (b.w, b.h, b.d, b.color, b.name, b.rotation))

    def test_js_format_behaelt_den_typ(self):
        el = sd.StageElement(type="riser_stairs", w=2, h=0.6, d=2.8)
        back = sd.StageElement.from_js_dict(el.to_js_dict())
        self.assertEqual(back.type, "riser_stairs")
        self.assertEqual((back.w, back.h, back.d), (2, 0.6, 2.8))

    def test_podest_und_bar_tragen_strahler(self):
        st = sd.StageDefinition(name="dock")
        st.add("bar_counter", x=0, y=0.55, z=0, w=3, h=1.1, d=0.8)
        ziel = st.dock_target_for(0.0, 0.0)
        self.assertIsNotNone(ziel, "auf der Bar laesst sich kein Strahler abstellen")

    def test_treppe_ist_keine_flache_top_flaeche(self):
        """Review A2: ueber einer Stufe steht der Strahler auf der Stufe, nicht
        schwebend auf Podesthoehe; neben der Treppe ist kein Podest."""
        st = sd.StageDefinition(name="treppe")
        # Standardmass 2,0 x 0,6 x 2,8: Deck bis z=0,8, zwei Stufen à 0,3 m
        # (0,4 m und 0,2 m hoch), Treppe 1,2 m breit.
        st.add("riser_stairs", id="p", x=0, y=0.3, z=0, w=2.0, h=0.6, d=2.8)
        off = sd.DOCK_TOP_OFFSET
        self.assertAlmostEqual(st.dock_target_for(0.0, 0.0)["y"], 0.6 + off)
        self.assertAlmostEqual(st.dock_target_for(0.0, 0.95)["y"], 0.4 + off)
        self.assertAlmostEqual(st.dock_target_for(0.0, 1.3)["y"], 0.2 + off)
        self.assertIsNone(st.dock_target_for(0.9, 1.3), "neben der Treppe angedockt")
        # Darunter liegender Boden faengt den Strahler neben der Treppe auf.
        st.add("floor", id="f", x=0, y=0.05, z=0, w=14, h=0.1, d=10)
        self.assertEqual(st.dock_target_for(0.9, 1.3)["id"], "f")
        self.assertEqual(st.dock_target_for(0.0, 1.3)["id"], "p")


class RasterTest(unittest.TestCase):
    """„Mehrere auf einmal als Reihe/Raster anlegen“ (VIZ-68)."""

    def test_positionen_zentriert_mit_abstand(self):
        from src.ui.visualizer.visualizer_window import raster_positionen
        self.assertEqual(raster_positionen(0, 6, 2.2, 1.3, 1, 1, 1.0), [(0.0, 6.0)])
        orte = raster_positionen(0, 0, 2.0, 1.0, 2, 3, 0.5)
        self.assertEqual(len(orte), 6)
        xs = sorted({x for x, _ in orte})
        zs = sorted({z for _, z in orte})
        self.assertEqual(xs, [-2.5, 0.0, 2.5])          # Breite 2 + Abstand 0,5
        self.assertEqual(zs, [-0.75, 0.75])             # Tiefe 1 + Abstand 0,5

    def test_ungueltige_werte_werden_abgefangen(self):
        from src.ui.visualizer.visualizer_window import raster_positionen
        self.assertEqual(len(raster_positionen(0, 0, 1, 1, 0, -3, -2)), 1)

    def _fake(self, reihen, spalten, abstand):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
        QApplication.instance() or QApplication([])
        import src.ui.visualizer.visualizer_window as VW
        tabs = QTabWidget()
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            tabs.addTab(QWidget(), name)
        tree = MagicMock()
        tree.topLevelItemCount.return_value = 0
        class _Feld:
            def __init__(self, v):
                self.v = v

            def value(self):
                return self.v

            def setValue(self, v):
                self.v = v
        self.felder = (_Feld(reihen), _Feld(spalten), _Feld(abstand))
        fake = SimpleNamespace(
            _state=SimpleNamespace(), _current_stage=sd.StageDefinition(),
            _tabs=tabs, _stage_tree=tree, _lbl_info=MagicMock(), _bridge=MagicMock(),
            _stage_dirty=False, _selected_stage_id="",
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _sync_stage_node_to_scene=MagicMock(), _remove_stage_node_from_scene=MagicMock(),
            _refresh_stage_tree=MagicMock(), _update_status_counts=MagicMock(),
            _set_build_mode=lambda build=True: None,
            _spin_reihen=self.felder[0], _spin_spalten=self.felder[1],
            _spin_abstand=self.felder[2],
        )
        return VW, fake

    def tearDown(self):
        from src.core.undo import get_undo_stack
        get_undo_stack().clear()

    def test_knopf_legt_raster_an_und_ein_undo_nimmt_alles_zurueck(self):
        from src.core.undo import get_undo_stack
        VW, fake = self._fake(3, 4, 1.0)
        get_undo_stack().clear()
        VW.VisualizerWindow._add_stage_element(fake, "beer_table")
        els = fake._current_stage.elements
        self.assertEqual(len(els), 12)
        self.assertTrue(all(e.type == "beer_table" for e in els))
        self.assertEqual(len({(e.x, e.z) for e in els}), 12, "Objekte liegen aufeinander")
        # Review A: EIN gebuendelter Push statt je Element.
        self.assertEqual(fake._bridge.push_add_stage_object_data.call_count, 0)
        self.assertEqual(fake._bridge.push_add_stage_objects_data.call_count, 1)
        self.assertEqual(len(fake._bridge.push_add_stage_objects_data.call_args[0][0]), 12)
        self.assertEqual(els[0].name, "Biertischgarnitur 1")
        # Review A: danach wieder 1 x 1
        self.assertEqual((self.felder[0].value(), self.felder[1].value()), (1, 1))
        get_undo_stack().undo()
        self.assertEqual(fake._current_stage.elements, [], "Undo nahm nicht die ganze Reihe")
        self.assertEqual(fake._bridge.push_remove_stage_objects.call_count, 1)
        self.assertEqual(len(fake._bridge.push_remove_stage_objects.call_args[0][0]), 12)
        get_undo_stack().redo()
        self.assertEqual(len(fake._current_stage.elements), 12)

    def test_ueber_200_nur_nach_rueckfrage(self):
        from unittest import mock
        VW, fake = self._fake(15, 15, 0.5)            # 225 > 200
        with mock.patch.object(VW.QMessageBox, "question",
                               return_value=VW.QMessageBox.StandardButton.No) as frage:
            VW.VisualizerWindow._add_stage_element(fake, "high_table")
        self.assertEqual(frage.call_count, 1)
        self.assertEqual(fake._current_stage.elements, [], "ohne Zustimmung angelegt")
        with mock.patch.object(VW.QMessageBox, "question",
                               return_value=VW.QMessageBox.StandardButton.Yes):
            VW.VisualizerWindow._add_stage_element(fake, "high_table")
        self.assertEqual(len(fake._current_stage.elements), 225)

    def test_unter_200_keine_rueckfrage(self):
        from unittest import mock
        VW, fake = self._fake(10, 20, 0.5)            # genau 200
        with mock.patch.object(VW.QMessageBox, "question") as frage:
            VW.VisualizerWindow._add_stage_element(fake, "high_table")
        frage.assert_not_called()
        self.assertEqual(len(fake._current_stage.elements), 200)

    def test_groesstes_raster_passt_in_die_eingabefelder(self):
        """Review A: 30 Reihen erzeugten Z ausserhalb des alten Feldbereichs
        (-30..30) — das Feld klemmte die Position. Review A2: mit dem
        GROESSTEN einstellbaren Abstand (vorher 20 m -> bis 340 m)."""
        import inspect
        import src.ui.visualizer.visualizer_window as VW
        from src.ui.visualizer.visualizer_window import VisualizerWindow, raster_positionen
        quelle = inspect.getsource(VisualizerWindow)
        bx = int(re.search(r"_stage_spin_x\.setRange\(-?(\d+)", quelle).group(1))
        bz = int(re.search(r"_stage_spin_z\.setRange\(-?(\d+)", quelle).group(1))
        roh = re.search(r"_spin_abstand\.setRange\([^,]+,\s*([^)]+)\)", quelle).group(1).strip()
        abstand_max = float(getattr(VW, roh)) if hasattr(VW, roh) else float(roh)
        from src.ui.visualizer.visualizer_window import RASTER_TYPEN
        for typ in RASTER_TYPEN:
            d = VisualizerWindow.STAGE_DEFAULTS[typ]
            orte = raster_positionen(d["x"], d["z"], d["w"], d["d"], 30, 30, abstand_max)
            with self.subTest(typ=typ):
                self.assertLessEqual(max(abs(x) for x, _ in orte), bx)
                self.assertLessEqual(max(abs(z) for _, z in orte), bz)

    def test_zu_grosses_raster_wird_mit_meldung_abgelehnt(self):
        """Review A2: ein Raster ueber +-200 m hinaus wird nicht still
        geklemmt, sondern mit Meldung abgelehnt (nichts angelegt)."""
        from unittest import mock
        VW, fake = self._fake(30, 30, 20.0)           # Feld haette 10 m begrenzt
        with mock.patch.object(VW.QMessageBox, "warning") as warnung, \
                mock.patch.object(VW.QMessageBox, "question") as frage:
            VW.VisualizerWindow._add_stage_element(fake, "bar_counter")
        self.assertEqual(warnung.call_count, 1)
        self.assertIn("200", warnung.call_args[0][2])
        frage.assert_not_called()
        self.assertEqual(fake._current_stage.elements, [], "trotz Meldung angelegt")
        self.assertFalse(VW.raster_passt([(0.0, 200.5)]))
        self.assertTrue(VW.raster_passt([(-200.0, 200.0)]))

    def test_fixture_positionsfelder_reichen_so_weit_wie_die_buehne(self):
        """Review A2: Fixture-X/Z standen bei +-50/+-30 — ein Geraet auf einer
        entfernten Bar wurde beim Anzeigen/Zurueckschreiben geklemmt."""
        import inspect
        import src.ui.visualizer.visualizer_window as VW
        quelle = inspect.getsource(VW.VisualizerWindow)
        for achse in ("x", "z"):
            with self.subTest(achse=achse):
                m = re.search(rf"self\._spin_{achse}\.setRange\((-?\d+),\s*(\d+)\)", quelle)
                self.assertEqual((float(m.group(1)), float(m.group(2))),
                                 (-VW.POSITION_GRENZE_M, VW.POSITION_GRENZE_M))
                m = re.search(rf"_stage_spin_{achse}\.setRange\((-?\d+),\s*(\d+)\)", quelle)
                self.assertEqual(float(m.group(2)), VW.POSITION_GRENZE_M)

    def test_raster_nur_fuer_moebel(self):
        VW, fake = self._fake(3, 3, 1.0)
        VW.VisualizerWindow._add_stage_element(fake, "truss_h")
        self.assertEqual(len(fake._current_stage.elements), 1, "Trasse im Raster angelegt")

    def test_einzelnes_objekt_wie_bisher(self):
        VW, fake = self._fake(1, 1, 1.0)
        VW.VisualizerWindow._add_stage_element(fake, "high_table")
        els = fake._current_stage.elements
        self.assertEqual(len(els), 1)
        self.assertEqual(els[0].name, "Stehtisch")
        d = VW.VisualizerWindow.STAGE_DEFAULTS["high_table"]
        self.assertEqual((els[0].x, els[0].z), (d["x"], d["z"]))


try:
    from tests.test_viz13_scene_modules_smoke import (  # noqa: E402
        _HTML_PATH, _MockVisualizerBridge, _app, _pump, destroy_webengine_view)
    _SZENE = True
except Exception:   # ohne QtWebEngine (z. B. natives ARM64) kein Szenen-Test
    _SZENE = False


@unittest.skipUnless(_SZENE, "QtWebEngine fehlt")
class SzeneTest(unittest.TestCase):
    """Jedes Objekt in der echten Seite: Form fuellt ihre Box exakt."""

    def setUp(self):
        import time
        from PySide6.QtCore import QUrl
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._view = QWebEngineView()
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self._bridge_obj = _MockVisualizerBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge_obj)
        self._view.page().setWebChannel(self._channel)
        geladen = []
        self._view.loadFinished.connect(geladen.append)
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + 40
        while not geladen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(0.02)
        self.assertTrue(geladen and geladen[-1], "stage_scene.html laedt nicht")

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)
        self._view = None

    def _eval(self, ausdruck, timeout_s=10.0):
        import time
        box = []
        ende = time.monotonic() + timeout_s
        while time.monotonic() < ende:
            box.clear()
            self._view.page().runJavaScript(ausdruck, 0, box.append)
            t = time.monotonic() + 2
            while not box and time.monotonic() < t:
                _app.processEvents()
                time.sleep(0.01)
            if box and box[0] not in (None, False, ""):
                return box[0]
            _pump(0.1)
        return box[0] if box else None

    def test_formen_fuellen_ihre_box(self):
        self._eval("!!(window.__lightos && window.__lightos.stageObjects)", 30)
        groessen = {
            "beer_table": [(2.2, 0.76, 1.3), (3.0, 0.8, 1.6)],
            "high_table": [(0.8, 1.1, 0.8), (1.2, 1.0, 0.6)],
            "bar_counter": [(3.0, 1.1, 0.8), (5.0, 1.2, 1.0)],
            "riser_stairs": [(2.0, 0.6, 2.8), (3.0, 1.0, 4.0)],
            "foh_desk": [(1.8, 0.9, 0.9), (2.4, 1.0, 1.2)],
        }
        objekte = []
        for typ, liste in groessen.items():
            for j, (x, y, z) in enumerate(liste):
                objekte.append({"id": f"{typ}-{j}", "type": typ, "name": typ,
                                "position": {"x": 0, "y": y / 2, "z": 0},
                                "size": {"x": x, "y": y, "z": z}, "rotation": 0,
                                "color": "#806040"})
        payload = json.dumps({"objects": objekte, "fixtures": [], "_reloadToken": 68})
        import time
        ende = time.monotonic() + 15
        anzahl = 0
        while time.monotonic() < ende:
            self._bridge_obj.stageLoaded.emit(payload)
            _pump(0.3)
            anzahl = self._eval("Object.keys(window.__lightos.stageObjects).length", 2) or 0
            if anzahl == len(objekte):
                break
        self.assertEqual(anzahl, len(objekte), "nicht alle Objekte gebaut")
        messung = json.loads(self._eval("""JSON.stringify(Object.values(window.__lightos.stageObjects).map(so => {
            const mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9]; let meshes = 0, metall = 0;
            so.mesh.traverse(c => { if (!c.isMesh) return; meshes++;
              if (c.userData.eigeneFarbe) metall++;
              c.geometry.computeBoundingBox(); const b = c.geometry.boundingBox;
              for (const [i, k] of [[0, 'x'], [1, 'y'], [2, 'z']]) {
                mn[i] = Math.min(mn[i], b.min[k]); mx[i] = Math.max(mx[i], b.max[k]); } });
            return {id: so.data.id, size: so.data.size, box: mx.map((v, i) => v - mn[i]),
                    mitte: mx.map((v, i) => (v + mn[i]) / 2), meshes, metall,
                    gruppe: !!so.mesh.isGroup};
          }))"""))
        self.assertEqual(len(messung), len(objekte))
        # Review A: gebuendelt anlegen/entfernen (Raster) ueber dieselben Kanaele
        bulk = [{"id": f"bulk-{i}", "type": "high_table", "name": "S",
                 "position": {"x": i, "y": 0.55, "z": 3}, "size": {"x": 0.8, "y": 1.1, "z": 0.8},
                 "rotation": 0, "color": "#ffffff"} for i in range(20)]
        self._bridge_obj.addStageObjectData.emit(json.dumps({"bulk": bulk}))
        _pump(0.5)
        self.assertEqual(self._eval("Object.keys(window.__lightos.stageObjects)"
                                    ".filter(k => k.startsWith('bulk-')).length", 5), 20)
        self._bridge_obj.removeStageObject.emit(json.dumps([b["id"] for b in bulk]))
        _pump(0.5)
        rest = self._eval("String(Object.keys(window.__lightos.stageObjects)"
                          ".filter(k => k.startsWith('bulk-')).length)", 5)
        self.assertEqual(rest, "0", "gebuendeltes Entfernen ließ Objekte stehen")
        for m in messung:
            with self.subTest(objekt=m["id"]):
                self.assertTrue(m["gruppe"])
                soll = (m["size"]["x"], m["size"]["y"], m["size"]["z"])
                for ist, s in zip(m["box"], soll):
                    self.assertAlmostEqual(ist, s, delta=0.01, msg=f"Box {m['box']} != {soll}")
                for c in m["mitte"]:
                    self.assertAlmostEqual(c, 0.0, delta=0.01, msg="Form nicht um den Mittelpunkt")
                if not m["id"].startswith("riser_stairs"):
                    self.assertEqual(m["metall"], 1, "Gestell fehlt bzw. nicht als Metall markiert")

    def test_andocken_auf_der_treppe_nimmt_die_stufenhoehe(self):
        """Review A2: JS-Raycast und Python-Spiegel liefern ueber Deck und
        Stufen dieselbe Andock-Hoehe (nicht die Podestkante)."""
        self._eval("!!(window.__lightos && window.__lightos.__findDockTarget)", 30)
        st = sd.StageDefinition(name="treppe")
        el = st.add("riser_stairs", id="p", x=1.0, y=0.5, z=-2.0, w=3.0, h=1.0, d=4.0)
        payload = json.dumps({"objects": [el.to_js_dict()], "fixtures": [], "_reloadToken": 682})
        import time
        ende = time.monotonic() + 15
        while time.monotonic() < ende:
            self._bridge_obj.stageLoaded.emit(payload)
            _pump(0.3)
            if self._eval("String(Object.keys(window.__lightos.stageObjects).length)", 2) == "1":
                break
        self._eval("window.__lightos.__renderTick && window.__lightos.__renderTick(), true", 2)
        # Deck, dann die vier Stufen (Mitte je Tritt), zuletzt neben der Treppe.
        punkte = [(1.0, -3.0), (1.0, -1.05), (1.0, -0.75), (1.0, -0.45), (1.0, -0.15),
                  (2.0, -0.15)]
        ist = json.loads(self._eval(
            "(()=>{const so=window.__lightos.stageObjects['p']; so.mesh.updateMatrixWorld(true);"
            f"return JSON.stringify({json.dumps(punkte)}.map(([x,z])=>{{"
            "const t=window.__lightos.__findDockTarget(x,z); return t ? t.y : null;}));})()", 5))
        for (x, z), y_js in zip(punkte, ist):
            with self.subTest(punkt=(x, z)):
                soll = st.dock_target_for(x, z)
                if soll is None:
                    self.assertIsNone(y_js, "JS dockt neben der Treppe an")
                else:
                    self.assertIsNotNone(y_js)
                    self.assertAlmostEqual(y_js, soll["y"], delta=0.01)
        self.assertAlmostEqual(ist[0], 1.0 + sd.DOCK_TOP_OFFSET, delta=0.01)
        self.assertLess(ist[4], ist[0] - 0.5, "Stufe vorn nicht tiefer als das Deck")


if __name__ == "__main__":
    unittest.main()

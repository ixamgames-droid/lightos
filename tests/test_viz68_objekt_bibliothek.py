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
        wert = lambda v: SimpleNamespace(value=lambda: v)  # noqa: E731
        fake = SimpleNamespace(
            _state=SimpleNamespace(), _current_stage=sd.StageDefinition(),
            _tabs=tabs, _stage_tree=tree, _lbl_info=MagicMock(), _bridge=MagicMock(),
            _stage_dirty=False, _selected_stage_id="",
            STAGE_TYPES=VW.VisualizerWindow.STAGE_TYPES,
            _sync_stage_node_to_scene=MagicMock(), _remove_stage_node_from_scene=MagicMock(),
            _refresh_stage_tree=MagicMock(), _update_status_counts=MagicMock(),
            _set_build_mode=lambda build=True: None,
            _spin_reihen=wert(reihen), _spin_spalten=wert(spalten), _spin_abstand=wert(abstand),
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
        self.assertEqual(fake._bridge.push_add_stage_object_data.call_count, 12)
        self.assertEqual(els[0].name, "Biertischgarnitur 1")
        get_undo_stack().undo()
        self.assertEqual(fake._current_stage.elements, [], "Undo nahm nicht die ganze Reihe")
        get_undo_stack().redo()
        self.assertEqual(len(fake._current_stage.elements), 12)

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


if __name__ == "__main__":
    unittest.main()

"""VIZ-67: ein importiertes Modell (STL/OBJ) kommt in der ECHTEN 3D-Seite an.

Laeuft in der seriellen Spur der QWebEngineView-Dateien (echte Seite).

Python schickt das Netz als ``modell = {key, pos, idx}`` im Buehnenobjekt
(``StageElement.to_js_dict``). Geprueft wird: das Mesh hat genau die
Dreiecke/Eckpunkte der Datei, fuellt die Objektgroesse (Griffe/Groessenfelder
skalieren es), das Echo an Python traegt das Netz NICHT zurueck, und auch der
Bulk-Weg (``loadStageJson``, Buehne laden) baut es.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from PySide6.QtCore import Slot                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from src.core.stage import modell_import as mi        # noqa: E402
from src.core.stage.stage_definition import StageDefinition, StageElement  # noqa: E402
from test_viz96_gobo_projektion_scene import (         # noqa: E402
    _Basis, _MockBridge, _pump)

DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "viz67")


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _MerkendeBridge(_MockBridge):
    def __init__(self):
        super().__init__()
        self.echos = []

    @Slot(str)
    def stageListChanged(self, payload):
        self.echos.append(payload)


def _element(sid, datei="viz67_quader_binaer.stl", einheit="mm", z_oben=True, **lage):
    netz = mi.lies_datei(os.path.join(DATEN, datei), einheit, z_oben)
    w, h, d = mi.element_groesse(netz)
    werte = dict(x=1.0, y=h / 2, z=-1.0, w=w, h=h, d=d)
    werte.update(lage)
    return StageElement(id=sid, type="imported_model", color="#8c8c8c",
                        name="Test", model=mi.packen(netz), **werte), netz


_INFO_JS = """
(function(){
  const L = window.__lightos, so = L.stageObjects['%s'];
  if (!so) return null;
  const m = so.mesh.children.find(c => c.isMesh);
  so.mesh.updateMatrixWorld(true);
  const bb = new window.THREE.Box3().setFromObject(m);
  return JSON.stringify({
    dreiecke: m.geometry.index ? m.geometry.index.count / 3 : -1,
    ecken: m.geometry.attributes.position.count,
    normalen: !!m.geometry.attributes.normal,
    platzhalter: !!(m.material && m.material.wireframe) || !so.mesh.userData.importModell,
    groesse: [bb.max.x - bb.min.x, bb.max.y - bb.min.y, bb.max.z - bb.min.z],
    mitte: [(bb.max.x + bb.min.x) / 2, (bb.max.y + bb.min.y) / 2, (bb.max.z + bb.min.z) / 2],
    imData: 'modell' in so.data,
  });
})()
"""


class ModellInDerSzeneTest(_Basis):
    def setUp(self):
        super().setUp()
        self._channel.deregisterObject(self._bridge_obj)
        self._bridge_obj = _MerkendeBridge()
        self._channel.registerObject("bridge", self._bridge_obj)

    def _info(self, sid):
        return json.loads(self._poll_until_true(_INFO_JS % sid))

    def _pruefe_groesse(self, info, soll):
        for ist, s in zip(info["groesse"], soll):
            self.assertAlmostEqual(ist, s, places=4)

    def test_stl_mesh_kommt_an_und_fuellt_seine_groesse(self):
        self._load_and_wait()
        el, netz = _element("imp1")
        self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(json.dumps(el.to_js_dict())),
            "!!window.__lightos.stageObjects['imp1']")
        info = self._info("imp1")
        self.assertFalse(info["platzhalter"], "nur der Platzhalter gebaut")
        self.assertEqual(info["dreiecke"], netz.dreiecke)
        self.assertEqual(info["ecken"], netz.eckpunkte)
        self.assertTrue(info["normalen"], "Normalen fehlen (computeVertexNormals)")
        self._pruefe_groesse(info, (el.w, el.h, el.d))
        for ist, s in zip(info["mitte"], (el.x, el.y, el.z)):
            self.assertAlmostEqual(ist, s, places=4)
        self.assertFalse(info["imData"], "Netz steht in so.data -> Echo waere riesig")

    def test_groesse_aendern_streckt_das_modell(self):
        self._load_and_wait()
        el, _ = _element("imp2", datei="viz67_kiste_quads.obj", einheit="m", z_oben=False)
        self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(json.dumps(el.to_js_dict())),
            "!!window.__lightos.stageObjects['imp2']")
        el.w, el.h, el.d = 4.0, 3.0, 1.1
        self._bridge_obj.addStageObjectData.emit(json.dumps(el.to_js_dict()))
        self._poll_until_true(
            "Math.abs(window.__lightos.stageObjects['imp2'].data.size.x - 4) < 1e-9")
        info = self._info("imp2")
        self.assertEqual(info["dreiecke"], 15)
        self._pruefe_groesse(info, (4.0, 3.0, 1.1))

    def test_echo_traegt_kein_netz(self):
        self._load_and_wait()
        el, _ = _element("imp3")
        self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(json.dumps(el.to_js_dict())),
            "!!window.__lightos.stageObjects['imp3']")
        deadline = 40
        while not self._bridge_obj.echos and deadline:
            _pump(0.1)
            deadline -= 1
        self.assertTrue(self._bridge_obj.echos, "kein stageListChanged-Echo")
        letztes = self._bridge_obj.echos[-1]
        self.assertIn("imp3", letztes)
        self.assertNotIn("modell", letztes)
        self.assertLess(len(letztes), 2000)

    def test_buehne_laden_baut_das_modell(self):
        """Bulk-Weg: Show/Buehne laden (push_stage_definition -> loadStageJson)."""
        self._load_and_wait()
        el, netz = _element("imp4")
        st = StageDefinition(name="viz67", elements=[el])
        payload = st.to_js_dict()
        payload["_reloadToken"] = 7
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(json.dumps(payload)),
            "!!window.__lightos.stageObjects['imp4']")
        info = self._info("imp4")
        # Review: der Quader hat 12 Dreiecke wie der Drahtgitter-Platzhalter
        # (BoxGeometry) — erst Eckpunkte + Platzhalter-Flag trennen beides.
        self.assertFalse(info["platzhalter"], "Bulk-Weg baut nur den Platzhalter")
        self.assertEqual(info["dreiecke"], netz.dreiecke)
        self.assertEqual(info["ecken"], netz.eckpunkte)
        self._pruefe_groesse(info, (el.w, el.h, el.d))

"""VIZ-67 (Teil 2): ein DXF-Import kommt in der ECHTEN 3D-Seite an.

Laeuft ueber die Produktiv-Seite (Geruest ``_viz72_szene.py``; ``__renderTick``
zeichnet ohne ``view.show()``). Geprueft wird:

* ein reiner Grundriss (nur Linien) wird zu ``THREE.LineSegments`` mit genau
  den Strecken der Datei, fuellt seine Objektgroesse und bleibt ueber einen
  unsichtbaren Quader anklickbar;
* Flaechen und Linien in einem Modell: beide kommen an, gleich skaliert;
* eine Farbaenderung faerbt die Linien mit;
* ★ im Ansehen-Modus fasst die Umgebung (VIZ-72) ein Objekt mit Linien NICHT
  zusammen — sonst wuerde das Original versteckt und die Linien verschwaenden.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Der Name MUSS in dieser Datei stehen (WebEngine-Spur, s. _viz72_szene.py).
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from _viz72_szene import Viz72SzeneBasis               # noqa: E402

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from src.core.stage import modell_import as mi        # noqa: E402
from src.core.stage.stage_definition import StageDefinition, StageElement  # noqa: E402

DATEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "viz67")


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _element(sid, netz, **lage):
    w, h, d = mi.element_groesse(netz)
    werte = dict(x=0.0, y=h / 2, z=0.0, w=w, h=h, d=d)
    werte.update(lage)
    return StageElement(id=sid, type="imported_model", color="#8c8c8c",
                        name="DXF", model=mi.packen(netz), **werte)


def _gemischt():
    """Ein 3DFACE (1 x 1 m, senkrecht) und eine Linie auf dem Boden."""
    paare = [(0, "SECTION"), (2, "ENTITIES"),
             (0, "3DFACE"), (10, 0), (20, 0), (30, 0), (11, 1), (21, 0), (31, 0),
             (12, 1), (22, 0), (32, 1), (13, 0), (23, 0), (33, 1),
             (0, "LINE"), (10, 0), (20, 0), (30, 0), (11, 0), (21, 2), (31, 0),
             (0, "ENDSEC"), (0, "EOF")]
    daten = "".join(f"{c}\n{w}\n" for c, w in paare).encode("ascii")
    return mi.lies_bytes(daten, ".dxf", "m")


_INFO_JS = """
(function(){
  const L = window.__lightos, so = L.stageObjects['%s'];
  if (!so) return null;
  so.mesh.updateMatrixWorld(true);
  const lin = so.mesh.children.find(c => c.isLineSegments);
  const m = so.mesh.children.find(c => c.isMesh);
  const box = (o) => { const bb = new window.THREE.Box3().setFromObject(o);
    return [bb.max.x - bb.min.x, bb.max.y - bb.min.y, bb.max.z - bb.min.z]; };
  return JSON.stringify({
    ok: !!so.mesh.userData.importModell,
    strecken: lin ? lin.geometry.index.count / 2 : -1,
    linGroesse: lin ? box(lin) : null,
    linFarbe: lin ? lin.material.color.getHexString() : null,
    linSichtbar: lin ? lin.visible : false,
    dreiecke: (m && m.geometry.index && !m.userData.pickHilfe) ? m.geometry.index.count / 3 : 0,
    meshGroesse: m ? box(m) : null,
    pickHilfe: !!(m && m.userData.pickHilfe && !m.visible),
    // Strahl 0,3 m neben dem ersten Linienpunkt senkrecht nach unten: three
    // raycastet Linien mit ~1 m Toleranz — das soll die Linie NICHT treffen.
    linTreffer: lin ? (() => {
      const v = new window.THREE.Vector3().fromBufferAttribute(
        lin.geometry.attributes.position, lin.geometry.index.getX(0));
      lin.localToWorld(v);
      const r = new window.THREE.Raycaster(
        new window.THREE.Vector3(v.x + 0.3, v.y + 5, v.z + 0.3),
        new window.THREE.Vector3(0, -1, 0));
      return r.intersectObject(lin, false).length;
    })() : -1,
  });
})()
"""


class DxfInDerSzeneTest(Viz72SzeneBasis):

    def _laden(self, *elemente):
        self._load_and_wait()
        payload = StageDefinition(name="viz67dxf", elements=list(elemente)).to_js_dict()
        payload["_reloadToken"] = 6767
        ids = json.dumps([e.id for e in elemente])
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(json.dumps(payload)),
            f"{ids}.every(i => !!window.__lightos.stageObjects[i])")

    def _info(self, sid):
        return json.loads(self._poll_until_true(_INFO_JS % sid))

    def test_grundriss_kommt_als_linien_an(self):
        netz = mi.lies_datei(os.path.join(DATEN, "viz67_grundriss.dxf"), "m", True)
        el = _element("dxf1", netz)
        self._laden(el)
        info = self._info("dxf1")
        self.assertTrue(info["ok"], "nur der Platzhalter gebaut")
        self.assertEqual(info["strecken"], netz.strecken)
        self.assertEqual(info["dreiecke"], 0)
        self.assertTrue(info["pickHilfe"], "Grundriss ohne Flaechen ist nicht anklickbar")
        self.assertAlmostEqual(info["linGroesse"][0], el.w, places=4)
        self.assertAlmostEqual(info["linGroesse"][2], el.d, places=4)
        # Wie der 2D-Umriss (_outline2d): Linien nie pickbar, sonst fangen sie
        # Klicks/Andocken/Zielen bis ~1 m daneben ab. Gepickt wird ueber die
        # unsichtbare Hilfe bzw. die Flaechen.
        self.assertEqual(info["linTreffer"], 0, "Linie faengt Klicks daneben ab")

    def test_flaechen_und_linien_gleich_skaliert(self):
        netz = _gemischt()
        self.assertEqual((netz.dreiecke, netz.strecken), (2, 1))
        el = _element("dxf2", netz, w=netz.groesse[0] * 3, d=netz.groesse[2] * 3)
        self._laden(el)
        info = self._info("dxf2")
        self.assertEqual(info["dreiecke"], 2)
        self.assertEqual(info["strecken"], 1)
        self.assertFalse(info["pickHilfe"])
        # Linie laeuft in Z (Tiefe 2 m -> x3), die Flaeche in X (1 m -> x3)
        self.assertAlmostEqual(info["linGroesse"][2], el.d, places=4)
        self.assertAlmostEqual(info["meshGroesse"][0], el.w, places=4)

    def test_farbe_faerbt_die_linien_mit(self):
        netz = mi.lies_datei(os.path.join(DATEN, "viz67_grundriss.dxf"), "m", True)
        el = _element("dxf3", netz)
        self._laden(el)
        el.color = "#ff0000"
        self._bridge_obj.addStageObjectData.emit(json.dumps(el.to_js_dict()))
        self._poll_until_true(
            "window.__lightos.stageObjects['dxf3'].data.color === '#ff0000'")
        self.assertEqual(self._info("dxf3")["linFarbe"], "ff0000")

    def test_ansehen_modus_versteckt_die_linien_nicht(self):
        netz = mi.lies_datei(os.path.join(DATEN, "viz67_grundriss.dxf"), "m", True)
        traverse = StageElement(id="t1", type="truss_h", x=0, y=6, z=0,
                                w=8, h=0.4, d=0.4, color="#a0a0a8")
        self._laden(_element("dxf4", netz), _element("dxf5", _gemischt(), x=3.0), traverse)
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()
        u = json.loads(self._eval("JSON.stringify(window.__lightos.umgebungInfo())"))
        self.assertTrue(u["aktiv"], "Gegenprobe: Umgebung nicht zusammengefasst")
        self.assertEqual(u["objekteZusammengefasst"], 1, "nur die Traverse")
        for sid in ("dxf4", "dxf5"):
            with self.subTest(sid=sid):
                sichtbar = self._eval(
                    f"window.__lightos.stageObjects['{sid}'].mesh.visible")
                self.assertTrue(sichtbar, "Objekt mit Linien versteckt -> Linien weg")
                self.assertTrue(self._info(sid)["linSichtbar"])

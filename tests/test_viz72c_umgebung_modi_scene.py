"""VIZ-72, Teil 3: zusammengefasste Umgebung — Ansehen, Bauen, Moduswechsel, Picking.

Abgetrennt aus ``test_viz72_spot_pool_umgebung.py`` (XPLAT-53: die Datei lief
in der Windows-ARM64-CI 186-287 s bei 300 s Segmentlimit). Die Tests sind
unveraendert uebernommen; Befund, Messwerte und Entwurf stehen im Kopf der
Ursprungsdatei, das gemeinsame Geruest in ``_viz72_szene.py``.

Laeuft ueber die ECHTE Produktiv-Seite (Muster test_viz69_render_ruckler.py).
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Der Name MUSS in dieser Datei stehen: daran erkennt der Segment-Runner die
# WebEngine-Spur und conftest die Exit-Haertung (XPLAT-53, s. _viz72_szene.py).
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from _viz72_szene import (  # noqa: F401
    Viz72SzeneBasis, _BUEHNE, _FIDS, _N, _SCENE_SRC)

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class Viz72UmgebungTest(Viz72SzeneBasis):
    # ── (3) Umgebung: Ansehen zusammengefasst, Bauen einzeln ─────────────────
    def _buehne(self):
        self._load_and_wait()
        self._emit_until_true(
            lambda: self._bridge_obj.stageLoaded.emit(json.dumps(_BUEHNE)),
            "Object.keys(window.__lightos.stageObjects).length === 5")
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()

    def _sichtbar(self):
        return self._json("Object.fromEntries(Object.entries(window.__lightos.stageObjects)"
                          ".map(([k, s]) => [k, s.mesh.visible]))")

    def test_umgebung_im_ansehen_modus_zusammengefasst(self):
        self._buehne()
        u = self._json("window.__lightos.umgebungInfo()")
        self.assertTrue(u["aktiv"])
        self.assertEqual(u["objekteZusammengefasst"], 5)
        # Traversen (gleiches Material) -> 1, Podest -> 1, Wand -> 1.
        self.assertEqual(u["koerper"], 3)
        self.assertFalse(any(self._sichtbar().values()), "Originale zusaetzlich sichtbar")
        # Ruhende Szene baut nicht neu.
        n = u["neubauten"]
        self._tick()
        self._tick()
        self.assertEqual(self._json("window.__lightos.umgebungInfo()")["neubauten"], n)

    def test_bauen_modus_zeigt_einzelobjekte_und_rueckweg(self):
        self._buehne()
        for modus in ("stage", "edit"):
            self._eval(f"window.__lightos.setEditMode('{modus}'); 1")
            self._tick()
            u = self._json("window.__lightos.umgebungInfo()")
            self.assertFalse(u["aktiv"], f"Modus {modus}: noch zusammengefasst")
            self.assertTrue(all(self._sichtbar().values()),
                            f"Modus {modus}: Einzelobjekte unsichtbar")
            self._eval("window.__lightos.setEditMode('view'); 1")
            self._tick()
            self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # 2D-Draufsicht: einzeln (halbtransparenter 2D-Stil).
        self._eval("window.__lightos.setViewMode('2D'); 1")
        self._tick()
        self.assertFalse(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        self.assertTrue(all(self._sichtbar().values()))
        self._eval("window.__lightos.setViewMode('3D'); 1")
        self._tick()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])

    def test_moduswechsel_baut_nicht_neu(self):
        """Review N2: Ansehen <-> Bauen ohne Aenderung behaelt die Koerper.
        Eine Aenderung im Bauen-Modus baut beim Rueckweg genau einmal neu."""
        self._buehne()
        n = self._json("window.__lightos.umgebungInfo()")["neubauten"]
        for _ in range(5):
            self._eval("window.__lightos.setEditMode('edit'); 1")
            self._tick()
            self.assertFalse(self._json("window.__lightos.umgebungInfo()")["aktiv"])
            self.assertTrue(all(self._sichtbar().values()))
            self._eval("window.__lightos.setEditMode('view'); 1")
            self._tick()
            u = self._json("window.__lightos.umgebungInfo()")
            self.assertTrue(u["aktiv"])
            self.assertFalse(any(self._sichtbar().values()))
        self.assertEqual(u["neubauten"], n, "Moduswechsel hat neu zusammengefasst")
        # Aenderung im Bauen-Modus -> Rueckweg baut neu.
        self._eval("window.__lightos.setEditMode('edit'); 1")
        self._tick()
        self._bridge_obj.removeStageObject.emit("t2")
        self._poll_until_true("!window.__lightos.stageObjects['t2']")
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()
        u = self._json("window.__lightos.umgebungInfo()")
        self.assertEqual(u["neubauten"], n + 1)
        self.assertEqual(u["objekteZusammengefasst"], 4)

    def test_farbaenderung_im_ansehen_modus_baut_neu(self):
        """Review N1: die Zahlen-Signatur sieht auch eine reine Farbaenderung."""
        self._buehne()
        n = self._json("window.__lightos.umgebungInfo()")["neubauten"]
        self._eval("(function(){ window.__lightos.stageObjects['p1'].mesh.traverse(o => {"
                   " if (o.isMesh) o.material.color.setRGB(0.9, 0.1, 0.1); }); return 1; })()")
        self._tick()
        self.assertEqual(self._json("window.__lightos.umgebungInfo()")["neubauten"], n + 1)
        self._tick()
        self.assertEqual(self._json("window.__lightos.umgebungInfo()")["neubauten"], n + 1)

    def test_aenderung_im_ansehen_modus_baut_neu(self):
        self._buehne()
        n = self._json("window.__lightos.umgebungInfo()")["neubauten"]
        self._bridge_obj.removeStageObject.emit("t2")
        self._poll_until_true("!window.__lightos.stageObjects['t2']")
        self._tick()
        u = self._json("window.__lightos.umgebungInfo()")
        self.assertEqual(u["neubauten"], n + 1)
        self.assertEqual(u["objekteZusammengefasst"], 4)

    def test_picking_und_andocken_unberuehrt(self):
        self._buehne()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # Andocken: im Ansehen-Modus (zusammengefasst) dasselbe Ziel wie im
        # Bauen-Modus (Einzelobjekte) — an mehreren Stellen.
        punkte = [(0, 0), (0, -3), (-4, 0), (3, -2), (0, -6)]
        ansehen = [self._json(f"window.__lightos.__findDockTarget({x}, {z})")
                   for x, z in punkte]
        self._eval("window.__lightos.setEditMode('edit'); 1")
        self._tick()
        self.assertFalse(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        bauen = [self._json(f"window.__lightos.__findDockTarget({x}, {z})")
                 for x, z in punkte]
        self.assertEqual(ansehen, bauen)
        self.assertTrue(any(z is not None for z in ansehen), ansehen)
        self._eval("window.__lightos.setEditMode('view'); 1")
        self._tick()
        self.assertTrue(self._json("window.__lightos.umgebungInfo()")["aktiv"])
        # Sammelkoerper sind nie Treffer eines Raycasts.
        treffer = self._eval("""(function(){
            const T = window.THREE; const L = window.__lightos;
            const rc = new T.Raycaster(new T.Vector3(0, 50, -2), new T.Vector3(0, -1, 0));
            const alle = Object.values(L.stageObjects).map(s => s.mesh);
            const hits = rc.intersectObjects(alle, true);
            return hits.length > 0 && hits.every(h => !h.object.userData.umgebungKoerper); })()""")
        self.assertTrue(treffer, "Raycast gegen die Originale liefert nichts")

if __name__ == "__main__":
    unittest.main()

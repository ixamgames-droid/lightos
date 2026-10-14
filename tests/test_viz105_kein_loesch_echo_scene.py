"""VIZ-105 (Review-Nachtrag): die 3D-Seite meldet ein Entfernen, das von Python kam, nicht zurueck.

Laeuft in der seriellen Spur der QWebEngineView-Dateien (echte Seite).

**Der Fund:** ``stage_objects.js#removeStageObject`` meldete JEDES Entfernen
ueber ``bridge.stageObjectDeleted`` an Python — auch das, das Python selbst
angestossen hatte (Loeschen-Knopf, Undo eines Hinzufuegens, Redo eines
Loeschens). Im Normalfall ist das Echo harmlos: das Element steht nicht mehr im
Python-Modell. Folgen aber Wiederholen und Rueckgaengig im selben Poll-Takt
der Seite aufeinander, kommt das Echo an, wenn das Element schon wieder da ist
— und loescht es im Python-Modell ein zweites Mal. Seit das Loeschen aus dem
3D-Bild ein Undo-Schritt ist (VIZ-105), entstand dabei zusaetzlich ein
Phantom-Schritt, und die gerade wiederhergestellten Andockungen waren wieder
weg.

**Jetzt:** nur eine Loeschung, die der Nutzer im 3D-Bild ausloest, wird
gemeldet. Der Loesch-Vermerk der Seite (kein Wiederauferstehen durch eine
automatische Wiederherstellung) bleibt in beiden Faellen.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from PySide6.QtCore import Slot                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz96_gobo_projektion_scene import (         # noqa: E402
    _Basis, _MockBridge, _pump)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _MerkendeBridge(_MockBridge):
    """Die Test-Bridge der Gobo-Szenen plus die beiden Rueckwege, um die es
    hier geht — sie merkt sich, was die Seite meldet."""

    def __init__(self):
        super().__init__()
        self.geloescht = []
        self.abgedockt = []

    @Slot(str)
    def stageObjectDeleted(self, sid):
        self.geloescht.append(sid)

    @Slot(str, str)
    def fixtureDockChanged(self, fid, sid):
        self.abgedockt.append((fid, sid))


_PODEST = {"type": "platform", "position": {"x": 0, "y": 0.5, "z": 0},
           "size": {"x": 4, "y": 1, "z": 3}, "rotation": 0, "color": "#332520"}


class LoeschEchoTest(_Basis):
    def setUp(self):
        super().setUp()
        # Vor dem Laden der Seite tauschen: sie verbindet sich mit dem, was
        # unter „bridge“ registriert ist.
        self._channel.deregisterObject(self._bridge_obj)
        self._bridge_obj = _MerkendeBridge()
        self._channel.registerObject("bridge", self._bridge_obj)

    def _anlegen(self, sid, **mehr):
        daten = dict(_PODEST, id=sid, **mehr)
        self._emit_until_true(
            lambda: self._bridge_obj.addStageObjectData.emit(json.dumps(daten)),
            f"!!window.__lightos.stageObjects['{sid}']")

    def _da(self, sid):
        return bool(self._eval(f"!!window.__lightos.stageObjects['{sid}']"))

    def test_entfernen_von_python_wird_nicht_zurueckgemeldet(self):
        """★ Der Fund."""
        self._load_and_wait()
        self._anlegen("p1")
        self._emit_until_true(
            lambda: self._bridge_obj.removeStageObject.emit("p1"),
            "!window.__lightos.stageObjects['p1']")
        _pump(0.4)
        self.assertEqual(self._bridge_obj.geloescht, [],
                         "Python hat das Entfernen selbst angestossen — kein Echo")

    def test_liste_von_python_wird_auch_nicht_zurueckgemeldet(self):
        """Raster-Undo (VIZ-68) entfernt mehrere auf einmal."""
        self._load_and_wait()
        self._anlegen("r1")
        self._anlegen("r2", position={"x": 5, "y": 0.5, "z": 0})
        self._emit_until_true(
            lambda: self._bridge_obj.removeStageObject.emit(json.dumps(["r1", "r2"])),
            "!window.__lightos.stageObjects['r1'] && !window.__lightos.stageObjects['r2']")
        _pump(0.4)
        self.assertEqual(self._bridge_obj.geloescht, [])

    def test_loeschen_durch_den_nutzer_wird_weiter_gemeldet(self):
        """Gegenprobe: der runde Loeschen-Knopf im 3D-Bild (derselbe Weg wie
        die Entf-Taste) meldet — sonst bliebe das Element im Python-Modell."""
        self._load_and_wait()
        self._anlegen("p2")
        self._bridge_obj.editModeChanged.emit("stage")
        self._emit_until_true(
            lambda: self._bridge_obj.selectStageObject.emit("p2"),
            "(function(){ const L = window.__lightos; return L.view.editMode === 'stage'"
            " && L.view.selectedStageId === 'p2'; })()")
        self._eval("(function(){ window.fabDelete(); return 1; })()")
        self.assertFalse(self._da("p2"))
        deadline = 40
        while not self._bridge_obj.geloescht and deadline:
            _pump(0.1)
            deadline -= 1
        self.assertEqual(self._bridge_obj.geloescht, ["p2"])

    def test_der_loesch_vermerk_bleibt(self):
        """Eine automatische Wiederherstellung darf das Element nicht
        zurueckbringen — auch ohne Echo (A3D-12/A3D-30)."""
        self._load_and_wait()
        self._anlegen("p3")
        self._emit_until_true(
            lambda: self._bridge_obj.removeStageObject.emit("p3"),
            "!window.__lightos.stageObjects['p3']")
        for _ in range(5):
            self._bridge_obj.addStageObjectData.emit(
                json.dumps(dict(_PODEST, id="p3", reassert=True)))
            _pump(0.1)
            self.assertFalse(self._da("p3"), "eine Wiederherstellung hat es zurueckgebracht")
        # ... ein echtes Wieder-Anlegen (Rueckgaengig) schon.
        self._anlegen("p3")
        self.assertTrue(self._da("p3"))
        self.assertEqual(self._bridge_obj.geloescht, [])

    def test_wiederholen_und_gleich_rueckgaengig_laesst_das_element_stehen(self):
        """Die Folge aus dem Fund in einem Takt: entfernen (Wiederholen), wieder
        anlegen (Rueckgaengig) — danach steht das Element, und es kam keine
        Loesch-Meldung, die es in Python wieder entfernen koennte."""
        self._load_and_wait()
        self._anlegen("p4")
        self._bridge_obj.removeStageObject.emit("p4")
        self._bridge_obj.addStageObjectData.emit(json.dumps(dict(_PODEST, id="p4")))
        self._poll_until_true("!!window.__lightos.stageObjects['p4']")
        _pump(0.4)
        self.assertTrue(self._da("p4"))
        self.assertEqual(self._bridge_obj.geloescht, [])

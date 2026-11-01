"""CDX-63 (Codex zu #1183, VIZ-101) — Wandende: Licht geht seitlich vorbei.

Befund: Ob die (unendliche) Wandebene den Kegel beschneiden darf, pruefte
``_wandDeckt`` nur nach oben (Oberkante), und der Breitenvergleich in
``_schmalerAlsKegel`` sah nur die GESAMTE Wandbreite. Trifft die Strahlmitte
eine 10 m breite Wand 0,1 m vor ihrem Ende, gehen die aeusseren Randstrahlen
des 5 m weiten Kegels neben der Wand vorbei — sie wurden trotzdem an der
Wandebene abgeschnitten, das Licht neben der Wand verschwand. Dasselbe galt
fuer ``_wandImFleck`` (Mitte trifft den Boden vor der Wand).

Jetzt prueft ``_wandDeckt`` den Durchstosspunkt jedes Randstrahls auch
seitlich gegen den Welt-Kasten der Wand. Geometrie ohne GL.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import _Basis, _geraet, _payload  # noqa: E402
from test_viz101_licht_durch_wand_scene import (  # noqa: E402
    _FID, _GEOMETRIE_JS, _RING, _TILT, _WAND_Z)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


class _SeitlichBasis(_Basis):
    __test__ = False
    GERAETE = [_geraet(_FID, x=0, y=4, z=0)]

    def _geometrie(self):
        return self._json(_GEOMETRIE_JS % _FID)

    def _wand_bei(self, mitte_x, breite=10.0, hoehe=6.0):
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": "wand1", "type": "wall",
            "position": {"x": mitte_x, "y": hoehe / 2, "z": _WAND_Z},
            "size": {"x": breite, "y": hoehe, "z": 0.2}}))
        self._poll_until_true("!!window.__lightos.stageObjects['wand1']")

    def _lauf(self, mitte_x, tilt=_TILT, **attrs):
        self._load_and_wait()
        self._wand_bei(mitte_x)
        self._push(_payload(_FID, tilt=tilt, **attrs))
        for _ in range(4):
            self._bild()
        return self._geometrie()

    # Wand x = -9,9 … 0,1: die Mitte (x = 0) trifft sie knapp vor dem Ende.
    def test_mitte_am_wandende_offen_kein_beschnitt(self):
        g = self._lauf(-4.9)
        self.assertGreater(abs(g["normale"][2]), 0.99, "Mitte trifft die Wand nicht")
        self.assertFalse(g["geschnitten"], "Kegel neben der Wand abgeschnitten")

    def test_mitte_am_wandende_gobo_kein_beschnitt(self):
        g = self._lauf(-4.9, gobo_wheel=_RING)
        self.assertFalse(g["geschnitten"], "Gobo-Kegel neben der Wand abgeschnitten")

    def test_boden_vor_dem_wandende_kein_beschnitt(self):
        # Mitte trifft den Boden 0,6 m vor der Wand (s. VIZ-101, Tilt 160).
        g = self._lauf(-4.9, tilt=160, gobo_wheel=_RING)
        self.assertFalse(g["geschnitten"], "Kegel am Boden vor dem Wandende abgeschnitten")

    # Gegenprobe: dieselbe Wand mittig — deckt den Kegel ganz ab.
    def test_wand_mittig_wird_weiter_beschnitten(self):
        self.assertTrue(self._lauf(0.0)["geschnitten"])

    def test_boden_vor_mittiger_wand_wird_weiter_beschnitten(self):
        self.assertTrue(self._lauf(0.0, tilt=160, gobo_wheel=_RING)["geschnitten"])


class Cdx63WandSeitlichTest(_SeitlichBasis):
    __test__ = True
    TIER = "high"

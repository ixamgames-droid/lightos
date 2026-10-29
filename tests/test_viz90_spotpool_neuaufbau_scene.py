"""VIZ-90: der Spot-Pool vergisst ein Geraet, wenn es neu aufgebaut wird.

Befund (Codex-Review #950): ``scene/spot_pool.js`` fuehrt Spitzenwert,
Vorbild-Helligkeit und Dunkel-Zeit je fid (``_spitze``/``_vorher``/
``_dunkelSeit``) und den Halter je Slot. Ein Neuaufbau mit derselben fid
(Showwechsel, ``addFixture`` -> ``removeFixture``) liess das alles stehen —
das neue Geraet erbte die Spitze des alten, und die Lichtvergabe hing bis zu
einer Spitzen-Halbwertszeit (8 s) am alten Wert.

Laeuft ueber die ECHTE Produktiv-Seite (Geruest ``_viz72_szene.py``), mit
simulierter Uhr und direkt gesetzten Strahlwerten wie
``test_viz72b_spot_pool_bewegung_scene.py``.
"""
import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Der Name MUSS in dieser Datei stehen: daran erkennt der Segment-Runner die
# WebEngine-Spur und conftest die Exit-Haertung (XPLAT-53, s. _viz72_szene.py).
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from _viz72_szene import Viz72SzeneBasis  # noqa: F401

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_N = 5           # Stufe "low": 4 Pool-Lichter, also ein Geraet zu viel
_FIDS = [720001 + i for i in range(_N)]

# Bilder mit simulierter Uhr (30/s); `werte` = {fid: Strahl-Intensitaet}.
_BILDER = r"""(function(werte, bilder){ const L = window.__lightos;
  if (window.__viz90T === undefined) { window.__viz90T = 1e6;
    L.__spotPoolUhr(() => window.__viz90T); }
  for (let k = 0; k < bilder; k++) { window.__viz90T += 1000 / 30;
    for (const fid in werte) { const f = L.fixtures[fid];
      f.spot.intensity = werte[fid]; f.spot.color.setRGB(1, 1, 1); }
    L.requestRender(); L.__renderTick(); }
  return L.spotPoolInfo().halter; })"""


class Viz90SpotPoolNeuaufbauTest(Viz72SzeneBasis):

    def tearDown(self):
        try:
            self._eval("(function(){ const L = window.__lightos;"
                       " if (L && L.__spotPoolUhr) L.__spotPoolUhr(null); return 1; })()")
        except Exception:
            pass
        super().tearDown()

    def _bilder(self, werte, bilder):
        return self._json(f"{_BILDER}({json.dumps(werte)}, {bilder})")

    def test_neues_geraet_erbt_keine_spitze(self):
        self._rig(n=_N, tier="low")
        self.assertEqual(self._pool()["groesse"], 4)

        # Alte Show: vier Geraete voll, das fuenfte dunkel.
        alt = {fid: 3.0 for fid in _FIDS[:4]}
        alt[_FIDS[4]] = 0.0
        halter = self._bilder(alt, 10)
        self.assertEqual(sorted(halter), _FIDS[:4])

        # Showwechsel: dieselben fids, neue Geraete-Objekte.
        self._eval("(function(){ const L = window.__lightos;"
                   " for (const k in L.fixtures) L.fixtures[k].__viz90Alt = true; return 1; })()")
        payload = json.dumps([
            {"fid": fid, "type": "par", "x": i * 1.5 - 4, "y": 6, "z": 0,
             "r": 0, "g": 0, "b": 0, "intensity": 0} for i, fid in enumerate(_FIDS)])
        self._emit_until_true(
            lambda: self._bridge_obj.allFixtures.emit(payload),
            "(function(){ const F = window.__lightos.fixtures; const k = Object.keys(F);"
            " return k.length === %d && k.every(x => !F[x].__viz90Alt); })()" % _N)

        # Die neuen Geraete halten keinen Slot des alten Geraets gleicher fid.
        self.assertTrue(all(h is None for h in self._pool()["halter"]),
                        self._pool()["halter"])

        # Neue Show: vier Geraete gedimmt, eine Sekunde spaeter das fuenfte
        # deutlich heller (1.5 > 0.6 * Hysterese). Ohne Vergessen zaehlte
        # fuer die Halter noch die alte Spitze (3.0, abklingend ~2.7) — das
        # fuenfte bekaeme erst nach rund 10 s ein Licht.
        neu = {fid: 0.6 for fid in _FIDS[:4]}
        neu[_FIDS[4]] = 0.0
        self._bilder(neu, 30)
        neu[_FIDS[4]] = 1.5
        halter = self._bilder(neu, 30)
        self.assertIn(_FIDS[4], halter,
                      f"neues Geraet bekommt kein Licht, Halter {halter}")


if __name__ == "__main__":
    unittest.main()

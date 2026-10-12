"""VIZ-72, Teil 2: der Spot-Pool in Bewegung — Wellen, Lauflicht, Verteilung, Blackout, 2D.

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


class Viz72BewegungTest(Viz72SzeneBasis):
    # ── (2b) Wellen, Lauflicht, Verteilung, Blackout, 2D (Review M1/M2/N4) ───
    # Simulierte Uhr (30 Bilder/s) und Strahl-Parameter direkt gesetzt: der Pool
    # liest nur f.spot — so laufen 10 s Show in einer Sekunde Testzeit.
    _SHOW = r"""(function(periode, bilder, art){ const L = window.__lightos; let t = 1e6;
      if (L.__spotPoolUhr) L.__spotPoolUhr(() => t);
      const fids = Object.keys(L.fixtures).filter(k => L.fixtures[k].spot); const n = fids.length;
      const v0 = L.spotPoolInfo().vergaben, s0 = L.shadowUpdateStats().neubauten;
      let deck = 0, deckN = 0;
      for (let k = 0; k < bilder; k++) { t += 1000 / 30; const an = new Set();
        fids.forEach((fid, i) => { const f = L.fixtures[fid]; let x;
          if (art === 'welle') x = 0.5 + 0.5 * Math.sin(i / n * 4 * Math.PI + 2 * Math.PI * t / periode);
          else x = ((i + Math.floor(t / periode)) % 8 === 0) ? 1 : 0;
          x = Math.round(x * 255) / 255; if (x > 0) an.add(Number(fid));
          f.spot.intensity = 3 * x; f.spot.color.setRGB(1, 1, 1); });
        L.requestRender(); L.__renderTick();
        if (k >= 30) { let c = 0; for (const fid of L.spotPoolInfo().halter) if (an.has(fid)) c++;
          deck += c / Math.min(8, an.size); deckN++; } }
      if (L.__spotPoolUhr) L.__spotPoolUhr(null);
      return { wechsel: L.spotPoolInfo().vergaben - v0,
               schatten: L.shadowUpdateStats().neubauten - s0, deckung: deck / deckN }; })"""

    def _show(self, periode_ms, bilder, art):
        return self._json(f"{self._SHOW}({periode_ms}, {bilder}, '{art}')")

    def test_welle_laesst_die_lichter_stehen(self):
        """Review M1: Dimmer-Welle ueber 68 PARs. Vorher 476 (1 s) bzw. 260
        (2 s) Lichtwechsel und 297/143 Schattendurchlaeufe in 300 Bildern."""
        self._rig(n=68)
        self._dmx({f: 255 for f in range(720001, 720069)})
        for periode in (1000, 2000):
            r = self._show(periode, 300, "welle")
            self.assertLessEqual(r["wechsel"], 2, f"Welle {periode} ms: {r}")
            self.assertLessEqual(r["schatten"], 2, f"Welle {periode} ms: {r}")

    def test_langsame_welle_schattendurchlaeufe_gedeckelt(self):
        """Eine langsame Welle darf den Lichtern folgen — aber Verdraengungen
        kommen hoechstens alle WECHSEL_ABSTAND_MS."""
        self._rig(n=68)
        self._dmx({f: 255 for f in range(720001, 720069)})
        abstand = self._pool()["wechselAbstandMs"]
        r = self._show(10000, 300, "welle")
        self.assertLessEqual(r["schatten"], 10000 // abstand + 1, r)

    def test_lauflicht_folgt_den_lichtern(self):
        """Die Bremsen duerfen ein Lauflicht nicht abhaengen: jeder Schritt
        bekommt seine Lichter (ein Schattendurchlauf je Schritt)."""
        self._rig(n=68)
        self._dmx({f: 255 for f in range(720001, 720069)})
        r = self._show(500, 300, "lauf")
        self.assertGreaterEqual(r["deckung"], 0.99, r)
        self.assertLessEqual(r["schatten"], 22, r)   # 20 Schritte in 10 s

    def test_gleich_hell_raeumlich_verteilt(self):
        """Review M2: 68 gleich helle PARs in einer Reihe — die 8 Lichter
        verteilen sich ueber die Reihe statt an die 8 kleinsten fids."""
        self._rig(n=68)
        self._dmx({f: 255 for f in range(720001, 720069)})
        xs = self._json("""window.__lightos.spotPoolInfo().halter.map(fid => {
            const p = new window.THREE.Vector3();
            window.__lightos.fixtures[fid].group.getWorldPosition(p); return p.x; })""")
        breite = 67 * 1.5
        self.assertGreaterEqual(max(xs) - min(xs), 0.8 * breite, xs)
        xs.sort()
        luecken = [b - a for a, b in zip(xs, xs[1:])]
        self.assertGreaterEqual(min(luecken), 0.5 * breite / 8, xs)

    def test_blackout_grosses_rig(self):
        """Blackout: alle Pool-Lichter auf 0, Halter und Shadow-Maps bleiben;
        wieder hell -> dieselben Halter, kein Schattendurchlauf."""
        self._rig(n=68)
        alle = range(720001, 720069)
        self._dmx({f: 255 for f in alle})
        self._tick()
        h0 = self._pool()["halter"]
        n0 = self._eval("window.__lightos.shadowUpdateStats().neubauten")
        self._dmx({f: 0 for f in alle})
        self.assertEqual(self._pool()["leuchtend"], 0)
        self.assertEqual(self._json("window.__lightos.spotPoolLights().map(l => l.intensity)"),
                         [0] * 8)
        self._dmx({f: 255 for f in alle})
        self._tick()
        self.assertEqual(self._pool()["halter"], h0)
        self.assertEqual(self._pool()["leuchtend"], 8)
        self.assertEqual(self._eval("window.__lightos.shadowUpdateStats().neubauten"), n0)

    def test_pool_in_der_2d_ansicht(self):
        """2D-Draufsicht: Geraete-Gruppen unsichtbar -> kein echtes Licht;
        zurueck in 3D leuchten dieselben Halter wieder."""
        self._rig(n=20)
        self._dmx({f: 255 for f in range(720001, 720021)})
        h0 = self._pool()["halter"]
        self._eval("window.__lightos.setViewMode('2D'); 1")
        self._tick()
        self.assertEqual(self._pool()["leuchtend"], 0)
        self._eval("window.__lightos.setViewMode('3D'); 1")
        self._tick()
        self.assertEqual(self._pool()["leuchtend"], 8)
        self.assertEqual(self._pool()["halter"], h0)

if __name__ == "__main__":
    unittest.main()

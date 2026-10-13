"""VIZ-72: Spot-Pool (feste Zahl echter Lichter) und zusammengefasste Umgebung.

**Was langsam war** (gemessen offscreen an der Buehnen-Show: 80 Geraete, 68 mit
Strahl, 23 Buehnenobjekte; Stufe Hoch, 1280x720, Median je Bild):

    main (68 SpotLights)        54,6 ms
    nur 8 SpotLights            19,8 ms
    ohne Kegel                  51,2 ms
    ohne Geraete-Gehaeuse       45,2 ms

In three.js r128 rechnet jedes beleuchtete Material in jedem Pixel ALLE
sichtbaren Lichter durch. Jetzt gibt es nur noch einen Pool echter Lichter je
Qualitaetsstufe (Niedrig 4 / Hoch 8 / Maximal 16), vergeben an die hellsten
Strahlen mit Hysterese; die Lichterzahl aendert sich nie wegen DMX (VIZ-69:
sie steckt im Programmschluessel). Im Ansehen-Modus werden die
Buehnenobjekte je Material zu einem Koerper zusammengefasst; Bauen-Modi, 2D und
eine Auswahl zeigen wieder die Einzelobjekte. Picking/Andocken gehen weiter
gegen die (unsichtbaren) Originale.

Laeuft ueber die ECHTE Produktiv-Seite (Muster test_viz69_render_ruckler.py).

XPLAT-53: diese Datei haelt Teil 1 — Lichterzahl je Stufe und die Vergabe an
die hellsten Strahlen — sowie die Quelltext-Pruefungen. Teil 2 (Wellen,
Lauflicht, Verteilung, Blackout, 2D) steht in
``test_viz72b_spot_pool_bewegung_scene.py``, Teil 3 (Umgebung und Modi) in
``test_viz72c_umgebung_modi_scene.py``; das gemeinsame Geruest in
``_viz72_szene.py``. Grund der Teilung: 186-287 s in der Windows-ARM64-CI bei
300 s Segmentlimit.
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


class Viz72SzeneTest(Viz72SzeneBasis):
    # ── (1) Lichterzahl konstant, Pool-Groesse je Stufe ──────────────────────
    def test_lichterzahl_ist_konstant_und_haengt_an_der_stufe(self):
        self._rig()
        self._dmx({f: 255 for f in _FIDS})
        info = self._json("window.__lightos.renderInfo()")
        self.assertEqual(info["spots"], 8, "Stufe Hoch: genau 8 echte SpotLights")
        self.assertEqual(info["schatten"], 8)
        self.assertEqual(
            self._eval("Object.values(window.__lightos.fixtures)"
                       ".filter(f => f.spot && f.spot.parent).length"), 0,
            "Geraete-Spots haengen noch in der Szene")
        programme = info["programme"]
        # Hell/Dunkel/Teil-dunkel/Farbe: Lichter- und Programmzahl bleiben.
        for schritt in range(6):
            werte = {f: (0 if (i + schritt) % 3 == 0 else 40 + 30 * i)
                     for i, f in enumerate(_FIDS)}
            werte[_FIDS[0]] = 0 if schritt % 2 else 255
            self._dmx(werte)
            jetzt = self._json("window.__lightos.renderInfo()")
            self.assertEqual(jetzt["spots"], 8, f"Schritt {schritt}: Lichterzahl geaendert")
            self.assertEqual(jetzt["schatten"], 8, f"Schritt {schritt}: Schattenzahl geaendert")
            self.assertEqual(jetzt["programme"], programme,
                             f"Schritt {schritt}: Shader neu kompiliert")
            self.assertTrue(self._eval(
                "window.__lightos.spotPoolLights().every(l => l.visible)"),
                "Pool-Licht unsichtbar geschaltet (Programmschluessel, VIZ-69)")

    def test_kleines_rig_behaelt_ein_licht_je_geraet(self):
        self._rig(n=3)
        self._dmx({f: 255 for f in _FIDS[:3]})
        p = self._pool()
        self.assertEqual(p["groesse"], 3)
        self.assertEqual(p["schatten"], 3)
        self.assertEqual(sorted(p["halter"]), list(_FIDS[:3]))

    def test_stufen_niedrig_und_maximal(self):
        self._rig(n=20, tier="low")
        self.assertEqual(self._pool()["groesse"], 4)
        self.assertEqual(self._json("window.__lightos.renderInfo()")["spots"], 4)

    def test_stufe_maximal(self):
        self._rig(n=20, tier="max")
        self.assertEqual(self._pool()["groesse"], 16)
        # QA-90: Maximal hebt das Schatten-DACH auf 16 — wie viele Schatten es
        # dann wirklich sind, deckelt zusaetzlich die Textur-Reserve der GPU
        # (fixtures.js#shadowSpotBudget, gewollt seit VIZ-71). Unter Windows
        # meldet ANGLE/D3D11 immer 16 Textur-Einheiten -> 16 - 6 = 10 Schatten;
        # eine Linux-Desktop-GPU (32 Einheiten) kommt auf die vollen 16. Fest
        # 16 zu erwarten machte den Test unter Windows rot (10 != 16).
        info = self._json("window.__lightos.shadowBudgetInfo()")
        self.assertEqual(info["hardCap"], 16, "Maximal hebt das Dach nicht auf 16")
        erwartet = min(16, max(2, info["maxTextures"] - info["reserve"]))
        self.assertEqual(info["budget"], erwartet, info)
        self.assertEqual(self._pool()["schatten"], erwartet, info)

    # ── (2) Vergabe an die hellsten, mit Hysterese ───────────────────────────
    def test_pool_vergibt_an_die_hellsten(self):
        self._rig()
        # Helligkeit steigt mit dem Index: die 8 hellsten sind die letzten 8.
        werte = {f: 20 + 19 * i for i, f in enumerate(_FIDS)}
        self._dmx(werte)
        self.assertEqual(sorted(self._pool()["halter"]), list(_FIDS[4:]))
        self.assertEqual(self._pool()["leuchtend"], 8)

        # Pool-Licht sitzt an der Linse des Geraets (VIZ-92: vorher 1 m ueber
        # dem Sockel, das eigene Gehaeuse warf Schatten), Ziel wie f.spot.
        lage = self._json("""(function(){ const L = window.__lightos;
            const l = L.spotPoolLights()[0]; const fid = L.spotPoolInfo().halter[0];
            const f = L.fixtures[fid];
            const v = L.__lichtUrsprung(f, new window.THREE.Vector3());
            return [l.position.distanceTo(v), l.target.position.distanceTo(f.spot.target.position),
                    Math.abs(l.intensity - f.spot.intensity)]; })()""")
        self.assertLess(max(lage), 1e-6, lage)

        # Hysterese: knapp heller als der schwaechste Halter -> kein Wechsel.
        vorher = self._pool()
        schwaechster = _FIDS[4]
        werte[_FIDS[3]] = werte[schwaechster] + 5
        self._dmx(werte)
        self.assertEqual(self._pool()["halter"], vorher["halter"],
                         "Vergabe flattert ohne Hysterese")
        # Deutlich heller -> verdraengt den Schwaechsten (spaetestens nach der
        # Mindesthaltezeit, MIN_HALT_MS).
        werte[_FIDS[3]] = 255
        self._dmx(werte)
        self._poll_until_true(
            "(function(){ const L = window.__lightos; L.requestRender(); L.__renderTick();"
            " return L.spotPoolInfo().halter.includes(%d); })()" % _FIDS[3])
        halter = self._pool()["halter"]
        self.assertIn(_FIDS[3], halter)
        self.assertNotIn(schwaechster, halter)

    def test_dunkler_halter_behaelt_platz_bis_er_gebraucht_wird(self):
        """Abdunkeln + Aufhellen derselben Geraete: Lichter bleiben, wo sie
        waren -> kein Schattendurchlauf (VIZ-69: Farbe/Dimmer kostet keinen)."""
        self._rig(n=4)
        hell = {f: 255 for f in _FIDS[:4]}
        self._dmx(hell)
        self._tick()
        h0 = self._pool()["halter"]
        n0 = self._eval("window.__lightos.shadowUpdateStats().neubauten")
        self._dmx({f: 0 for f in _FIDS[:4]})
        self.assertEqual(self._pool()["leuchtend"], 0)
        self._dmx(hell)
        self.assertEqual(self._pool()["halter"], h0)
        self.assertEqual(self._eval("window.__lightos.shadowUpdateStats().neubauten"), n0,
                         "Hell/Dunkel hat die Shadow-Maps neu gezeichnet")

    def test_vergabe_rein(self):
        """Die Vergabe-Regel als reine Funktion (Map fid -> Helligkeit)."""
        self._load_and_wait()
        r = self._json("""(function(){ const V = window.__lightos.__spotPoolVergeben;
          const m = (o) => new Map(Object.entries(o).map(([k, v]) => [Number(k), v]));
          return {
            frei: V([null, null], m({1: 1, 2: 3, 3: 2})),
            knapp: V([1, 3], m({1: 1.0, 2: 1.2, 3: 2})),
            deutlich: V([1, 3], m({1: 1.0, 2: 1.3, 3: 2})),
            dunkel: V([1, 3], m({1: 0, 2: 0.1, 3: 2})),
            weg: V([9, 3], m({2: 0.5, 3: 2})),
          }; })()""")
        self.assertEqual(r["frei"], [2, 3])
        self.assertEqual(r["knapp"], [1, 3])
        self.assertEqual(r["deutlich"], [2, 3])
        self.assertEqual(r["dunkel"], [2, 3])
        self.assertEqual(r["weg"], [2, 3])

    def test_vergabe_rein_bremsen(self):
        """Review M1: Spitzenwert, Mindesthaltezeit, Wechselabstand — und ein
        dunkler Halter ist trotz Haltezeit sofort frei."""
        self._load_and_wait()
        r = self._json("""(function(){ const V = window.__lightos.__spotPoolVergeben;
          const m = (o) => new Map(Object.entries(o).map(([k, v]) => [Number(k), v]));
          const info = {};
          return {
            ohne_spitze: V([1, 3], m({1: 0.5, 2: 1, 3: 2})),
            mit_spitze: V([1, 3], m({1: 0.5, 2: 1, 3: 2}), 1.25, {spitze: m({1: 1, 3: 2})}),
            gesperrt: V([1, 3], m({1: 1, 2: 2, 3: 2}), 1.25, {seit: [0, 0], jetzt: 100}),
            frei: V([1, 3], m({1: 1, 2: 2, 3: 2}), 1.25, {seit: [0, 0], jetzt: 500}),
            dunkel: V([1, 3], m({1: 0, 2: 0.1, 3: 2}), 1.25,
                      {seit: [0, 0], jetzt: 1, spitze: m({1: 0, 3: 2})}),
            abstand: V([1, 3], m({1: 1, 2: 2, 3: 2}), 1.25, {wechselErlaubt: false, info}),
            ausstehend: info.ausstehend,
          }; })()""")
        self.assertEqual(r["ohne_spitze"], [2, 3])
        self.assertEqual(r["mit_spitze"], [1, 3], "Halter im Wellental verliert sein Licht")
        self.assertEqual(r["gesperrt"], [1, 3], "Mindesthaltezeit ignoriert")
        self.assertEqual(r["frei"], [2, 3])
        self.assertEqual(r["dunkel"], [2, 3], "dunkler Halter blockiert trotz Haltezeit")
        self.assertEqual(r["abstand"], [1, 3])
        self.assertTrue(r["ausstehend"], "aufgeschobener Wechsel nicht gemeldet")


class Viz72QuelltextTest(unittest.TestCase):
    def _js(self, *teile):
        return open(os.path.join(_SCENE_SRC, *teile), encoding="utf-8").read()

    def test_geraete_spot_nicht_mehr_in_der_szene(self):
        code = "\n".join(z for z in self._js("fixtures", "fixtures.js").splitlines()
                         if not z.lstrip().startswith("//"))
        self.assertNotIn("root.add(spot)", code)

    def test_render_closure_vergibt_vor_den_schatten(self):
        app = self._js("app.js")
        rumpf = app.split("function renderFrame()", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(rumpf.index("syncSpotPool()"), rumpf.index("prepareShadowMap()"))
        self.assertLess(rumpf.index("syncUmgebung()"), rumpf.index("prepareShadowMap()"))

    def test_stufentabelle_echte_lichter(self):
        q = self._js("scene", "quality_tiers.js")
        for stufe, n in (("low", 4), ("high", 8), ("max", 16)):
            block = q.split(stufe + ": Object.freeze({", 1)[1].split("})", 1)[0]
            self.assertIn(f"realLights: {n},", block, stufe)

if __name__ == "__main__":
    unittest.main()

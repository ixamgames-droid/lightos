"""MODELLOADER: Cache, Sammel-Callbacks, Format-Weiche und Groessen-Vertrag von
``scene/model_loader.js`` — in echter QWebEngine.

Das Modul haengt an **sechs** Fixture-Buildern (``par``/``strobe``/``smoke``/
``hazer``-DAE) und an den Buehnen-Objekten (Truss-OBJ) — und hatte bis 2026-08-05
**null Tests**. Weder der Cache, noch die Sammel-Callbacks (mehrfaches Laden
desselben Pfads erzeugt genau EINE Anfrage), noch die Format-Weiche, noch
``fitModelToSize`` waren von aussen geprueft.

★ Der Grund, warum das mehr ist als eine Abdeckungs-Luecke: ``fitModelToSize``
rechnet mit der Bounding-Box eines FREMD geladenen Modells. Deren Werte kommen
aus einer Datei, die niemand hier kontrolliert — ein flaches oder leeres Modell
ist kein exotischer Fall, sondern das, was eine kaputte/unvollstaendige
Asset-Datei liefert. Und eine NaN-Position schlaegt in three.js weiter: sie
wandert in die Matrix, von dort in die Bounding-Sphere, und ein Frustum-Cull mit
NaN verhaelt sich nicht mehr vorhersagbar.
"""
import json
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, QUrl
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05


def _pump(seconds):
    ende = time.monotonic() + seconds
    while time.monotonic() < ende:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


class ModelLoaderSceneTest(unittest.TestCase):
    def setUp(self):
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._obj = QObject()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._obj)
        self._view.page().setWebChannel(self._channel)
        self._loaded = []
        self._view.loadFinished.connect(self._loaded.append)

    def tearDown(self):
        destroy_webengine_view(self._view, _pump)   # XPLAT-09
        self._view = None

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _load_and_wait(self):
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded and self._loaded[-1], "Page nicht geladen")
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < ende:
            if self._eval("!!window.__lightosAppReady"):
                return
            time.sleep(_POLL_INTERVAL_S)
        self.fail("Szene wurde nicht bereit")

    # ── Alle Checks in EINER Ladung (jede Vollladung kostet ~4 s) ─────────────

    def test_groessen_vertrag_und_entartete_modelle(self):
        self._load_and_wait()
        roh = self._eval("""
        (function () {
          const T = window.THREE;
          const fit = window.__lightos.__fitModelToSize;
          const ziel = {x: 2, y: 2, z: 2};

          // ★ Der Versatz gehoert in die GEOMETRIE, nicht auf `position`.
          // Ein geladenes Modell traegt seinen Ursprung in den Vertices; die
          // erste Fassung dieses Tests schob stattdessen das Mesh und mass
          // damit einen Fall, den es gar nicht gibt (der Test war rot, der
          // Code richtig).
          function box(bx, by, bz, mx, my, mz) {
            const g = new T.BoxGeometry(Math.max(bx, 1e-9),
                                        Math.max(by, 1e-9),
                                        Math.max(bz, 1e-9));
            g.translate(mx, my, mz);
            const m = new T.Mesh(g, new T.MeshBasicMaterial());
            m.updateMatrixWorld(true);
            return m;
          }
          function weltMitte(o) {
            o.updateMatrixWorld(true);
            const b = new T.Box3().setFromObject(o);
            const c = b.getCenter(new T.Vector3());
            return [c.x, c.y, c.z];
          }
          function zustand(o) {
            return {pos: [o.position.x, o.position.y, o.position.z],
                    scale: [o.scale.x, o.scale.y, o.scale.z]};
          }

          const out = {};

          // (a) Normalfall: 4x4x4 in eine 2x2x2-Box, versetzt bei (10, 0, 0)
          const normal = box(4, 4, 4, 10, 0, 0);
          fit(normal, ziel);
          out.normal = zustand(normal);
          out.normalMitte = weltMitte(normal);

          // (b) FLACH in x (Dicke ~0), sitzt bei x = 5. Genau das liefert eine
          //     Asset-Datei, die eine Achse verliert (Plane statt Koerper).
          const flach = box(0, 4, 4, 5, 0, 0);
          fit(flach, ziel);
          out.flach = zustand(flach);

          // (c) LEER: ein Object3D ohne jede Geometrie -> leere Bounding-Box.
          const leer = new T.Object3D();
          leer.position.set(1, 2, 3);
          fit(leer, ziel);
          out.leer = zustand(leer);

          return JSON.stringify(out);
        })()
        """)
        d = json.loads(roh)

        # (a) Der Normalfall muss stimmen — sonst misst der Rest nichts.
        self.assertAlmostEqual(d["normal"]["scale"][0], 0.5, places=6,
                               msg=f"4 m in eine 2-m-Box = Faktor 0,5: {d['normal']}")
        for achse, wert in zip("xyz", d["normalMitte"]):
            self.assertAlmostEqual(
                wert, 0.0, places=4,
                msg=f"das Modell sitzt nach dem Einpassen nicht im Ursprung "
                    f"({achse} = {wert}, {d['normalMitte']})")

        # (b) ★ Eine Achse ohne Ausdehnung darf das Modell NICHT wegkatapultieren.
        #     Vorher wurde der Versatz mit `size.x / max(ms.x, 1e-6)` gerechnet —
        #     bei ms.x = 0 also mit dem Faktor 2e6, und ein Modell bei x = 5 lag
        #     danach bei rund 10 Millionen Einheiten. Unsichtbar, ohne Fehler.
        for achse, wert in zip("xyz", d["flach"]["pos"]):
            self.assertLess(
                abs(wert), 1000.0,
                f"das flache Modell wurde auf {achse} = {wert} geschoben — bei "
                f"einer Achse ohne Ausdehnung darf kein Riesenversatz entstehen "
                f"({d['flach']})")

        # (c) ★ Ein leeres Modell darf keine NaN-Position bekommen. NaN wandert
        #     in die Matrix, von dort in die Bounding-Sphere, und ein
        #     Frustum-Cull mit NaN ist nicht mehr vorhersagbar.
        for achse, wert in zip("xyz", d["leer"]["pos"]):
            self.assertEqual(
                wert, wert,     # NaN != NaN
                f"leeres Modell bekam NaN auf {achse} ({d['leer']})")
            self.assertLess(abs(wert), 1e6, f"leeres Modell weggeschoben: {d['leer']}")
        for achse, wert in zip("xyz", d["leer"]["scale"]):
            self.assertEqual(wert, wert, f"leeres Modell bekam NaN-Skalierung auf {achse}")

    def test_cache_liefert_klone_und_laedt_nur_einmal(self):
        """Zwei Ladungen desselben Pfads: EINE Anfrage, und jeder Aufrufer
        bekommt ein EIGENES Objekt — sonst teilten sich zwei Fixtures ein
        Modell, und das Verschieben des einen bewegte das andere."""
        self._load_and_wait()
        roh = self._eval("""
        (function () {
          const T = window.THREE;
          const lade = window.__lightos.__loadModel;
          if (typeof T.OBJLoader !== 'function') return JSON.stringify({uebersprungen: true});
          const pfad = 'assets/models/stage/truss_square_2m.obj';
          window.__mlErgebnis = [];
          lade(pfad, o => window.__mlErgebnis.push(o));
          lade(pfad, o => window.__mlErgebnis.push(o));
          return JSON.stringify({gestartet: true});
        })()
        """)
        if json.loads(roh).get("uebersprungen"):
            self.skipTest("kein OBJLoader in dieser Umgebung")
        ende = time.monotonic() + 15.0
        while time.monotonic() < ende:
            if self._eval("(window.__mlErgebnis || []).length >= 2"):
                break
            _pump(0.2)
        stand = json.loads(self._eval("""
        (function () {
          const e = window.__mlErgebnis || [];
          return JSON.stringify({
            anzahl: e.length,
            beideDa: e.length >= 2 && !!e[0] && !!e[1],
            verschieden: e.length >= 2 && e[0] !== e[1]});
        })()
        """))
        self.assertEqual(stand["anzahl"], 2,
                         "nicht beide Callbacks wurden bedient — die "
                         "Sammel-Liste verliert Aufrufer")
        self.assertTrue(stand["beideDa"], "ein Callback bekam null statt eines Modells")
        self.assertTrue(
            stand["verschieden"],
            "beide Aufrufer bekamen DASSELBE Objekt — dann bewegt das "
            "Verschieben des einen Fixtures das andere mit")

    def test_unbekannte_endung_meldet_sich_statt_still_zu_bleiben(self):
        """Ein Pfad ohne passenden Loader muss den Callback mit ``null``
        bedienen. Bliebe er einfach aus, haenge der Aufrufer fuer immer in der
        Sammel-Liste — und das Fixture behielte kommentarlos sein
        Prozedural-Modell, was wie Absicht aussieht."""
        self._load_and_wait()
        self._eval("""
        (function () {
          window.__mlUnbekannt = 'wartet';
          window.__lightos.__loadModel('assets/models/gibtsnicht.xyz',
                                       o => { window.__mlUnbekannt = (o === null) ? 'null' : 'objekt'; });
          return true;
        })()
        """)
        ende = time.monotonic() + 8.0
        while time.monotonic() < ende:
            if self._eval("window.__mlUnbekannt !== 'wartet'"):
                break
            _pump(0.2)
        self.assertEqual(
            self._eval("window.__mlUnbekannt"), "null",
            "unbekannte Dateiendung: der Callback muss mit null kommen, nicht "
            "ausbleiben")


if __name__ == "__main__":
    unittest.main()

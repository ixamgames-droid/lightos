"""A3D-41 — kein NaN aus der Zeiger-Mathematik in den SceneGraph.

**Der Bug.** ``setMouseFromCoords`` (``scene_src/interaction/picking.js``)
rechnete ``((clientX - rect.left) / rect.width) * 2 - 1``. Ein nicht
gelayoutetes Canvas — Visualizer im unsichtbaren Tab, zugezogener Splitter,
Layout-Umbau — liefert ``rect.width === 0``, und damit ist der Quotient je
nach Zaehler ``NaN`` (0/0) oder ``±Infinity``. ``mouse`` ist ein modulweit
GETEILTES ``Vector2``: EIN solcher Aufruf vergiftet jeden folgenden Raycast,
bis der naechste gueltige Aufruf ihn ueberschreibt.

Der Weg von dort in die Nutzerdaten lief ueber den Gizmo-**Translate**-Zweig:
``axisParamUnderPointer`` hatte keinen Null-Rueckgabepfad (die Schwester-
Funktion ``rotationAngleUnderPointer`` hat einen — deshalb trat der Fehler nur
beim Verschieben auf, nie beim Drehen), also fiel dort ``NaN`` heraus,
``f.group.position.x = start.x + NaN`` machte das Geraet unsichtbar, und am
Gestik-Ende wurde daraus ``"x": null`` in der Bridge-Payload (``JSON.stringify``
kennt kein NaN). Python starb an ``float(None)`` und verlor die GANZE Gestik.
16 Vorkommen in zwei Sitzungen im ``crash.log``, ueber zwei Codestaende hinweg.

Die Python-Seite des Fixes (Filter + Heil-Push) deckt
``test_a3d_gesture_batch.py`` ab; hier steht die JS-Seite, also die Quelle.

Aufbau nach dem Muster von ``test_viz_labels_js.py``: echte
``stage_scene.html`` in einer ``QWebEngineView``, Pruefung ueber die
``window.__lightos``-Test-Seams. Ein 0-grosses Canvas MIT Pointer-Event laesst
sich nicht per Mauseingabe herstellen, daher der direkte Aufruf.
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
from PySide6.QtCore import QObject, QUrl, Slot
from _qt_lifecycle import destroy_webengine_view  # XPLAT-09

_app = QApplication.instance() or QApplication([])

_HTML_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "src", "ui", "visualizer", "stage_scene.html"))

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 12.0
_POLL_INTERVAL_S = 0.05


class _MiniBridge(QObject):
    """Minimal-Bridge: ``tryChannel()`` in bridge.js ist vollstaendig defensiv
    (``if (bridge.X)`` pro Signal), daher reicht der Poll-Slot, damit die Page
    ohne Fehler bis ``__lightosAppReady`` durchlaeuft."""
    @Slot(result=str)
    def pollControl(self):
        return "{}"


class MouseNanGuardJsTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"stage_scene.html fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._bridge = _MiniBridge()
        self._channel = QWebChannel(self._view)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        self._loaded_ok = []
        self._view.loadFinished.connect(self._loaded_ok.append)

    def tearDown(self):
        # XPLAT-09: deleteLater() allein raeumt hier nichts ab — Herleitung in
        # tests/_qt_lifecycle.py.
        destroy_webengine_view(self._view, self._pump)
        self._view = None

    def _pump(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)

    def _load_and_wait(self):
        self._loaded_ok.clear()
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        deadline = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._loaded_ok and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._loaded_ok, "loadFinished nie ausgeloest (Timeout)")
        self.assertTrue(self._loaded_ok[-1], "stage_scene.html konnte nicht geladen werden")

    def _eval(self, js_expr):
        box = []
        self._view.page().runJavaScript(js_expr, lambda r: box.append(r))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript-Callback nie ausgeloest fuer: {js_expr}")
        return box[0]

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter Wert: {last!r})")

    def _ready(self):
        self._load_and_wait()
        self._poll_until_true("window.__lightosAppReady === true")
        self._poll_until_true(
            "!!(window.__lightos && window.__lightos.view "
            "&& window.__lightos.view.activeCam)")

    def _give_canvas_a_size(self):
        """Der offscreen-View wird nie gelayoutet: ``window.innerWidth`` ist 0,
        und ``renderer.setSize`` setzt das Canvas entsprechend auf ``0px``.

        Das ist kein Test-Artefakt, sondern **genau der Fehlerzustand** — er
        belegt nebenbei, wie normal ein 0-grosses Canvas ist. Fuer einen
        gueltigen Bezugspunkt braucht der Test aber vorher ein Canvas MIT
        Groesse; ein Element darf breiter sein als der Viewport, das Layout
        gibt ihm die gesetzten 800x600.
        """
        self.assertTrue(self._eval(
            "(function(){"
            "  var c = document.querySelector('canvas');"
            "  c.style.width = '800px'; c.style.height = '600px';"
            "  var r = c.getBoundingClientRect();"
            "  return r.width === 800 && r.height === 600;"
            "})()"), "Canvas liess sich nicht auf 800x600 bringen")

    # ── Der Fehlerfall: Canvas ohne Layout-Groesse ──────────────────────────

    def test_zero_sized_canvas_never_poisons_mouse(self):
        """Beide Spielarten in einem Durchgang: ``clientX === rect.left`` waere
        ``0/0 = NaN``, jeder andere Zaehler ``±Infinity``. Nach beiden Aufrufen
        muss ``mouse`` unveraendert auf dem letzten GUELTIGEN Wert stehen."""
        self._ready()
        self._give_canvas_a_size()
        raw = self._eval(
            "(function(){"
            "  var L = window.__lightos;"
            "  var c = document.querySelector('canvas');"
            "  var okReturn = L.__setMouseFromCoords(12, 34);"   # gueltiger Bezugspunkt
            "  var before = { x: L.__mouse.x, y: L.__mouse.y };"
            "  var prev = c.style.display;"
            "  c.style.display = 'none';"                        # -> rect ist ueberall 0
            "  var rect = c.getBoundingClientRect();"
            "  var retZero = L.__setMouseFromCoords(0, 0);"      # 0/0
            "  var afterZero = { x: L.__mouse.x, y: L.__mouse.y };"
            "  var retFar = L.__setMouseFromCoords(50, 50);"     # 50/0
            "  var afterFar = { x: L.__mouse.x, y: L.__mouse.y };"
            "  c.style.display = prev;"
            "  return JSON.stringify({"
            "    okReturn: okReturn, retZero: retZero, retFar: retFar,"
            "    rectWidth: rect.width, rectHeight: rect.height,"
            "    before: before, afterZero: afterZero, afterFar: afterFar,"
            "    allFinite: [before.x, before.y, afterZero.x, afterZero.y,"
            "                afterFar.x, afterFar.y].every(Number.isFinite)"
            "  });"
            "})()")
        r = json.loads(raw)

        self.assertEqual(r["rectWidth"], 0,
                         "Testaufbau kaputt: das Canvas ist nicht 0 breit")
        self.assertEqual(r["rectHeight"], 0)
        self.assertTrue(r["okReturn"],
                        "der gueltige Aufruf muss true melden")
        self.assertFalse(r["retZero"],
                         "0/0-Aufruf muss als verworfen (false) gemeldet werden")
        self.assertFalse(r["retFar"],
                         "x/0-Aufruf muss als verworfen (false) gemeldet werden")
        self.assertTrue(r["allFinite"],
                        f"mouse enthaelt nicht-endliche Werte: {r}")
        self.assertEqual(r["afterZero"], r["before"],
                         "der verworfene Aufruf hat mouse veraendert")
        self.assertEqual(r["afterFar"], r["before"],
                         "der verworfene Aufruf hat mouse veraendert")

    # ── Die Kamera: der breitere NaN-Pfad ───────────────────────────────────

    def test_camera_survives_a_zero_sized_viewport(self):
        """Der schwerwiegendere Fund. ``new PerspectiveCamera(60, w/h, …)`` mit
        ``w === h === 0`` ergibt ``aspect = NaN`` — und eine Kamera mit
        NaN-Aspect hat eine **vollstaendig nicht-endliche Projektionsmatrix**.
        Ab da liefert JEDER Raycast NaN, ganz unabhaengig von der
        Zeigerposition, und die erste Gestik danach schreibt NaN-Positionen.

        Das ist in der echten App der wahrscheinlichere Weg in den Crash als
        der ``mouse``-Pfad: ``mouse`` braucht ein Pointer-Event WAEHREND das
        Canvas 0 gross ist, die Kamera dagegen wird beim Aufbau bzw. beim
        Resize-auf-0 vergiftet und bleibt es, bis ein echter Resize sie heilt.

        Dieser Test laeuft im Ernstfall selbst: die offscreen-Page hat
        ``innerWidth === innerHeight === 0``, gemessen wurde hier vor dem Fix
        ``aspect: NaN`` und ``projectionMatrix.elements`` nicht-endlich.
        """
        self._ready()
        raw = self._eval(
            "(function(){"
            "  var L = window.__lightos;"
            "  var cam = L.view.activeCam;"
            "  return JSON.stringify({"
            "    innerW: window.innerWidth, innerH: window.innerHeight,"
            "    aspectFinite: Number.isFinite(cam.aspect),"
            "    aspect: Number.isFinite(cam.aspect) ? cam.aspect : String(cam.aspect),"
            "    projFinite: cam.projectionMatrix.elements.every(Number.isFinite),"
            "    posFinite: [cam.position.x, cam.position.y, cam.position.z]"
            "               .every(Number.isFinite)"
            "  });"
            "})()")
        r = json.loads(raw)

        self.assertEqual(r["innerW"], 0,
                         "Testaufbau: die offscreen-Page ist erwartungsgemaess "
                         "0 breit — genau der Fehlerzustand")
        self.assertTrue(r["aspectFinite"],
                        f"Kamera-Aspect ist nicht endlich: {r['aspect']}")
        self.assertTrue(r["projFinite"],
                        "die Projektionsmatrix enthaelt NaN — ab hier ist JEDER "
                        "Raycast NaN und jede Gestik schreibt kaputte Positionen")
        self.assertTrue(r["posFinite"])

    def test_pan_on_a_zero_sized_viewport_keeps_the_camera_finite(self):
        """``(2*size*a)/0`` ist Infinity, und ``0 * Infinity`` ist NaN — per
        ``-=`` bleibt das DAUERHAFT in ``orthoCam.position`` stehen und macht
        jeden 2D-Raycast NaN. Getestet ueber den echten Pan-Pfad
        (``handlePointerMove`` im ``pan``-Modus), nicht ueber die Formel."""
        self._ready()
        raw = self._eval(
            "(function(){"
            "  var L = window.__lightos;"
            "  L.setViewMode('2D');"
            "  var before = { x: L.view.activeCam.position.x, z: L.view.activeCam.position.z };"
            "  var P = L.__pointerState;"
            "  P.dragMode = 'pan';"
            "  P.isLeftDragging = true;"
            "  P.lastMouseX = 10; P.lastMouseY = 10;"
            "  L.__handlePointerMove(10, 10);"   # dx=dy=0 -> genau der 0*Infinity-Fall
            "  L.__handlePointerMove(25, 40);"   # und ein echtes Delta durch /0
            "  P.isLeftDragging = false;"
            "  P.dragMode = 'none';"
            "  var after = { x: L.view.activeCam.position.x, z: L.view.activeCam.position.z };"
            "  L.setViewMode('3D');"
            "  return JSON.stringify({"
            "    before: before, after: after,"
            "    finite: Number.isFinite(after.x) && Number.isFinite(after.z)"
            "  });"
            "})()")
        r = json.loads(raw)
        self.assertTrue(r["finite"],
                        f"Pan bei 0-grossem Viewport hat die Ortho-Kamera "
                        f"vergiftet: {r['before']} -> {r['after']}")

    # ── Die Guards dahinter, gegen den vergifteten Zustand von damals ───────

    def test_ground_intersect_reports_a_miss_instead_of_the_origin(self):
        """``intersectGround`` gab IMMER einen Vector3 zurueck: ``intersectPlane``
        liefert bei einem Fehlschlag ``null`` und laesst ``target`` unangetastet
        — herausgefallen ist dann der frische Nullvektor. Alle sechs Aufrufer
        pruefen ``if (gh)`` und waren damit wirkungslos; statt die Gestik zu
        verwerfen, rechneten sie mit dem Buehnen-URSPRUNG weiter und rissen das
        Geraet dorthin."""
        self._ready()
        self._give_canvas_a_size()
        raw = self._eval(
            "(function(){"
            "  var L = window.__lightos;"
            "  var okHit = L.__setMouseFromCoords(400, 300) && !!L.__intersectGround();"
            "  var sx = L.__mouse.x, sy = L.__mouse.y;"
            # Vector3 ohne THREE-Import: der Kamera-Positionsvektor ist einer.
            "  var A = L.view.activeCam.position.clone().set(0, 0, 0);"
            "  var axis = L.view.activeCam.position.clone().set(1, 0, 0);"
            "  L.__mouse.x = NaN; L.__mouse.y = NaN;"        # Zustand von damals
            "  var miss = L.__intersectGround();"
            "  var param = L.__axisParamUnderPointer(A, axis);"
            "  L.__mouse.x = sx; L.__mouse.y = sy;"          # sauberen Zustand hinterlassen
            "  return JSON.stringify({"
            "    okHit: okHit, missIsNull: miss === null,"
            "    missKind: Object.prototype.toString.call(miss),"
            "    paramIsNull: param === null"
            "  });"
            "})()")
        r = json.loads(raw)

        self.assertTrue(r["okHit"],
                        "Testaufbau kaputt: der gueltige Raycast trifft den Boden nicht")
        self.assertTrue(r["missIsNull"],
                        f"intersectGround meldet den Fehlschlag nicht als null "
                        f"(bekam {r['missKind']}) — die if(gh)-Guards der Aufrufer "
                        f"bleiben damit wirkungslos")
        self.assertTrue(r["paramIsNull"],
                        "axisParamUnderPointer liefert bei kaputtem Ray keinen "
                        "null-Abbruch — genau so kam NaN in f.group.position")


if __name__ == "__main__":
    unittest.main()

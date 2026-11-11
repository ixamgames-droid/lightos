"""FM-64 (Teil 2): die Mini-3D-Vorschau in echter QWebEngine.

Gebaut wird das Produkt-Widget ``FixtureVorschau3D`` selbst (es laedt
``stage_scene.html?vorschau=1`` und schiebt Geraet und Licht per
runJavaScript hinein). Gemessen wird an der Szene:

* der Kegel hat den Abstrahlwinkel aus den Dialogdaten und WAECHST, wenn der
  Winkel groesser wird (live, ohne Neuladen der Seite);
* bei einer Zoom-Spanne laeuft er mit dem Zoom-Regler von eng nach weit;
* ein Gobo aus der Liste kommt im Strahl an;
* Buehnen-Overlays und Werkzeugleisten sind ausgeblendet, es steht genau EIN
  Geraet in der Szene.

Kein WebGL-Kontext: QA-74-Weg ueber ``_webgl_gate`` (einmal neu laden, danach
ueberspringen mit Grund) — ein Testfehler bleibt jeder andere Grund.
"""
import json
import os
import time
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from _qt_lifecycle import (destroy_webengine_view, destroy_widget,  # noqa: F401  XPLAT-09
                           flush_deferred_deletes)
import _webgl_gate                      # QA-74

_app = QApplication.instance() or QApplication([])

from src.ui.widgets import fixture_vorschau_3d as V   # noqa: E402

_BEREIT_TIMEOUT_S = 12.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _app.processEvents()
        time.sleep(_POLL_INTERVAL_S)


_GOBO = SimpleNamespace(attribute="gobo_wheel", ranges=[
    SimpleNamespace(range_from=0, range_to=9, name="Offen"),
    SimpleNamespace(range_from=10, range_to=19, name="Punkte"),
])


class VorschauSzeneTest(unittest.TestCase):
    # EINE Ansicht fuer alle Tests (wie test_viz14_drag_scene): offscreen
    # bekommt hier die zweite WebGL-Seite eines Prozesses oft keinen Kontext
    # mehr (QA-70) — die Messungen bauen das Geraet ohnehin je Test neu.
    _view = None
    _kein_gl = ""          # Grund, falls die Ansicht keinen WebGL-Kontext bekam

    @classmethod
    def setUpClass(cls):
        cls._daten = V.VorschauDaten()
        # ``_view`` ist hier das Vorschau-Widget; die QWebEngineView baut es
        # beim Aufklappen selbst (Produktweg).
        cls._view = V.FixtureVorschau3D(lambda: cls._daten)
        cls._view.resize(640, 320)
        cls._view._view_platz.setContentsMargins(0, 0, 0, 0)
        cls._view.show()

    @classmethod
    def tearDownClass(cls):
        # Produkt-Abbau (WebChannel trennen, deleteLater), dann DeferredDelete
        # wirklich zustellen — processEvents allein tut das nicht (XPLAT-09).
        try:
            cls._view.abbauen()
        finally:
            flush_deferred_deletes()
            _pump(0.2)
            destroy_widget(cls._view, _app)
            cls._view = None

    def setUp(self):
        d = type(self)._daten
        d.typ, d.viz_model, d.attribute, d.kanaele = "par", "", [], []
        d.abstrahlwinkel, d.zoom_umgekehrt = (15.0, 0.0), False

    # ── Helfer ───────────────────────────────────────────────────────────

    def _seite(self):
        return self._view.view

    def _warte_auf_szene(self, _zweiter_versuch=False):
        """Aufklappen und warten, bis die Vorschau ihr Geraet geschickt hat.
        Laeuft die Szene schon (geteilte Ansicht), Geraet nur neu bauen."""
        if type(self)._kein_gl:
            # Die geteilte Ansicht bekam schon keinen Kontext — derselbe Grund.
            raise unittest.SkipTest(type(self)._kein_gl)
        if self._view._bereit:
            self._view.aktualisieren()
            _pump(0.2)
            self._poll_until_true(f"!!window.__lightos.fixtures[{V.VORSCHAU_FID}]")
            return
        self._view.zeigen()
        try:
            self._poll_until_true("!!window.__lightosAppReady",
                                  timeout_s=_BEREIT_TIMEOUT_S)
            ende = time.monotonic() + _POLL_TIMEOUT_S
            while not self._view._bereit and time.monotonic() < ende:
                _pump(0.05)
            self.assertTrue(self._view._bereit, "Vorschau meldete die Szene nie bereit")
            self._poll_until_true(f"!!window.__lightos.fixtures[{V.VORSCHAU_FID}]")
        except AssertionError as e:
            seite = self._seite()
            diagnose = (_webgl_gate.szenen_diagnose(seite, _pump, 3.0)
                        if seite is not None else "kein Rueckruf (Ansicht abgebaut)")
            try:
                neu = _webgl_gate.nach_szenen_timeout(
                    e, diagnose, zweiter_versuch=_zweiter_versuch)
            except unittest.SkipTest as skip:
                type(self)._kein_gl = str(skip)
                raise
            if neu:
                self._view.btn.setChecked(False)
                flush_deferred_deletes()
                _pump(1.0)
                return self._warte_auf_szene(_zweiter_versuch=True)

    def _eval(self, js_expr):
        seite = self._seite()
        self.assertIsNotNone(seite, "keine WebEngine-Ansicht in der Vorschau")
        huelle = ("(function(){try{return JSON.stringify(['ok',(0,eval)("
                  + json.dumps(js_expr) + ")]);}"
                  "catch(e){return JSON.stringify(['err',String(e)]);}})()")
        box = []
        seite.page().runJavaScript(huelle, lambda r: box.append(r))
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < deadline:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box and box[0], f"kein Ergebnis fuer: {js_expr}")
        art, wert = json.loads(box[0])
        self.assertNotEqual(art, "err", f"JS warf bei '{js_expr}': {wert}")
        return wert

    def _poll_until_true(self, js_expr, timeout_s=_POLL_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        last = None
        while time.monotonic() < deadline:
            last = self._eval(js_expr)
            if last:
                return last
            time.sleep(_POLL_INTERVAL_S)
        self.fail(f"Timeout beim Warten auf truthy '{js_expr}' (letzter: {last!r})")

    def _kegel(self):
        """Halber Kegelwinkel in Grad (Geometrie x Zoom-Weite)."""
        return self._eval(
            f"(function(){{const f=window.__lightos.fixtures[{V.VORSCHAU_FID}];"
            "const p=f.beam.geometry.parameters;"
            "const k=(typeof f._optikK==='number')?f._optikK:1;"
            "return Math.atan(p.radius*k/p.height)*180/Math.PI;})()")

    def _warte_auf_kegel(self, soll, delta=0.05):
        ende = time.monotonic() + _POLL_TIMEOUT_S
        ist = None
        while time.monotonic() < ende:
            ist = self._kegel()
            if abs(ist - soll) <= delta:
                return ist
            _pump(0.1)
        self.fail(f"Kegel {ist!r}° statt {soll}° (halber Winkel)")

    # ── Messungen ────────────────────────────────────────────────────────

    def test_kegel_waechst_mit_dem_abstrahlwinkel(self):
        self._warte_auf_szene()
        klein = self._warte_auf_kegel(7.5)            # 15° voll
        type(self)._daten.abstrahlwinkel = (40.0, 0.0)
        self._view.aktualisieren()                    # wie das Winkelfeld
        gross = self._warte_auf_kegel(20.0)           # 40° voll
        self.assertGreater(gross, klein + 10.0)
        self.assertEqual(1, self._eval("Object.keys(window.__lightos.fixtures).length"))

    def test_zoom_regler_faehrt_von_eng_nach_weit(self):
        type(self)._daten.abstrahlwinkel = (10.0, 40.0)
        self._warte_auf_szene()
        self.assertFalse(self._view.sld_zoom.isHidden())
        self._view.sld_zoom.setValue(0)
        self._warte_auf_kegel(5.0)
        self._view.sld_zoom.setValue(255)
        self._warte_auf_kegel(20.0)

    def test_gobo_aus_der_liste_und_ohne_buehnen_bedienung(self):
        type(self)._daten.typ = "moving_head"
        type(self)._daten.kanaele = [_GOBO]
        type(self)._daten.attribute = ["gobo_wheel"]
        self._warte_auf_szene()
        self.assertTrue(self._eval("window.__lightos.vorschau === true"))
        for elem in ("top-hud", "overlay", "controls", "mode-frame", "empty-state"):
            self.assertEqual("none", self._eval(
                f"getComputedStyle(document.getElementById('{elem}')).display"),
                f"#{elem} ist in der Vorschau sichtbar")
        self._view.cb_gobo.setCurrentIndex(self._view.cb_gobo.findText("Punkte"))
        self._poll_until_true(
            f"window.__lightos.fixtures[{V.VORSCHAU_FID}].lastGobo === 'dots'")
        self._view.cb_gobo.setCurrentIndex(0)          # offen
        self._poll_until_true(
            f"window.__lightos.fixtures[{V.VORSCHAU_FID}].lastGobo === ''")


if __name__ == "__main__":
    unittest.main()

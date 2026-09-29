"""FM-14b — Python- und JS-Ringordnung gegeneinander, in echter QWebEngine.

Die Ringordnung eines Pixel-Kopfes steht seit FM-14 in
``scene_src/fixtures/pixel_order.js#wabenPlatz`` (3D-Segmente + 2D-Icon). FM-14b
braucht sie auch auf der Python-Seite — dort wird der Ring BEDIENT (Kopf-Matrix
im Programmer). Damit steht dieselbe Regel in zwei Sprachen, und das ist genau
die Drift-Quelle, an der VIZ-51/52 gearbeitet haben: eine der beiden Fassungen
wird angefasst, die andere nicht, und niemand merkt es.

★ Deshalb prueft diese Datei **beide Seiten gegeneinander**, nicht jede fuer
sich — Index fuer Index, ueber das ECHTE JS-Modul, so wie die Szene es laedt
(dynamischer ``import()`` derselben URL, also dieselbe Modul-Instanz, die
``buildPixelHead`` und ``addGridCells`` benutzen). Kein ``assertIn`` auf dem
Quelltext: eine Textprobe haette die Formel nie ausgerechnet und waere bei
jedem Umbau der Schreibweise falsch-rot bzw. bei jeder Verhaltensaenderung
falsch-gruen.

★★ Arrays reisen ueber die QtWebEngine-Bruecke nicht zuverlaessig zurueck. Die
Python-Erwartung wird deshalb als JSON-STRING in die Seite gegeben, dort
verglichen, und zurueck kommt eine einzelne ZAHL (Zahl der Abweichungen). Wie
viele Indizes wirklich verglichen wurden, wird getrennt abgefragt — sonst waere
ein Vergleich ueber die leere Menge auch „0 Abweichungen".

★★★ Der Vergleicher selbst hat seine eigene Gegenprobe: dieselbe Messung mit
einer absichtlich verstellten Erwartung MUSS Abweichungen melden — auch bei
einer winzigen (1e-9), sonst waere die Toleranz so weit, dass sie alles
durchlaesst.
"""
import json
import math
import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                       # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView            # noqa: E402
from PySide6.QtWebEngineCore import (QWebEngineSettings,         # noqa: E402
                                     QWebEngineProfile)
from PySide6.QtCore import QUrl                                  # noqa: E402
from _qt_lifecycle import destroy_webengine_view                 # noqa: E402

from src.core.pixel_order import waben_platz, waben_plaetze      # noqa: E402

_app = QApplication.instance() or QApplication([])

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_ROOT, "src", "ui", "visualizer", "stage_scene.html")

_LOAD_TIMEOUT_S = 40.0
_POLL_TIMEOUT_S = 10.0
_POLL_INTERVAL_S = 0.05

# Bis Ring 3 (37 Plaetze) — mehr als das reale Geraet hat (19). Die Regel gilt
# fuer beliebig viele Ringe, und genau dort trennen sich geratene Formeln von
# der abgelesenen: der Startwinkel haengt am Ring (270° - Schritt/2).
_BIS = waben_plaetze(3)

# Toleranz: beide Seiten rechnen IEEE-754-Doubles, aber cos/sin duerfen sich um
# die letzten Bits unterscheiden (V8 vs. libm). 1e-12 laesst das durch und
# faengt jede inhaltliche Abweichung — die kleinste denkbare (ein halber
# Ringschritt) liegt bei ~0,26.
_TOLERANZ = 1e-12


def _erwartung(bis: int = _BIS) -> list:
    """Die Python-Fassung als reine Liste ``[[ring, x, y], …]``."""
    return [list(waben_platz(i)) for i in range(bis)]


class RingZwillingTest(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.isfile(_HTML_PATH), f"fehlt: {_HTML_PATH}")
        self._view = QWebEngineView()
        try:
            self._view.page().profile().setHttpCacheType(
                QWebEngineProfile.HttpCacheType.NoCache)
        except Exception:
            pass
        s = self._view.settings()
        s.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self._geladen = []
        self._view.loadFinished.connect(self._geladen.append)

    def tearDown(self):
        destroy_webengine_view(self._view, lambda sek: self._pump(sek))
        self._view = None

    # ── Werkzeug ────────────────────────────────────────────────────────────

    @staticmethod
    def _pump(sekunden):
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)

    def _eval(self, js):
        box = []
        self._view.page().runJavaScript(js, box.append)
        ende = time.monotonic() + _POLL_TIMEOUT_S
        while not box and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(box, f"runJavaScript ohne Callback: {js}")
        return box[0]

    def _zahl(self, js):
        wert = self._eval(js)
        self.assertIsNotNone(wert, f"kein Wert fuer: {js}")
        return float(wert)

    def _modul_laden(self):
        """Seite laden und DAS ECHTE Modul holen.

        Der Import laeuft ueber ein ``<script type="module">`` IN DER SEITE, mit
        genau dem relativen Pfad, den ``builders.js``/``topdown_icons.js``
        benutzen — ES-Module sind pro URL genau einmal instanziiert, es ist also
        dieselbe Funktion, die die Szene zeichnet, keine Kopie. (Ein
        ``import()`` direkt aus ``runJavaScript`` geht nicht: dessen Basis-URL
        ist ``about:blank``, der relative Pfad loest gar nicht auf.)"""
        url = QUrl.fromLocalFile(_HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        self._view.load(url)
        ende = time.monotonic() + _LOAD_TIMEOUT_S
        while not self._geladen and time.monotonic() < ende:
            _app.processEvents()
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(self._geladen and self._geladen[-1], "Page nicht geladen")

        self._eval(
            "window.__fm14b = null; window.__fm14bFehler = '';"
            "try {"
            "  const s = document.createElement('script');"
            "  s.type = 'module';"
            "  s.textContent = \"import * as m from"
            " './scene_src/fixtures/pixel_order.js'; window.__fm14b = m;\";"
            "  s.onerror = function () { window.__fm14bFehler = 'script error'; };"
            "  document.head.appendChild(s);"
            "} catch (e) { window.__fm14bFehler = String(e); }"
            "true")
        ende = time.monotonic() + _POLL_TIMEOUT_S
        da = False
        while time.monotonic() < ende:
            if self._eval("!!window.__fm14b"):
                da = True
                break
            time.sleep(_POLL_INTERVAL_S)
        self.assertTrue(da, "pixel_order.js liess sich nicht laden: "
                            f"{self._eval('window.__fm14bFehler')}")
        self.assertEqual(
            self._zahl("typeof window.__fm14b.wabenPlatz === 'function' ? 1 : 0"),
            1.0, "das Modul exportiert wabenPlatz nicht mehr")

    def _abweichungen(self, erwartung, toleranz=_TOLERANZ) -> tuple:
        """``(zahl_der_abweichungen, zahl_der_verglichenen)`` — beides als
        EINZELNE Zahl abgefragt (Arrays reisen nicht zuverlaessig)."""
        self._eval("window.__fm14bSoll = " + json.dumps(json.dumps(erwartung))
                   + "; true")
        js = ("(function () {"
              " const soll = JSON.parse(window.__fm14bSoll);"
              " const tol = %r;"
              " let schlecht = 0, geprueft = 0;"
              " for (let i = 0; i < soll.length; i++) {"
              "   const p = window.__fm14b.wabenPlatz(i);"
              "   geprueft++;"
              "   if (p.ring !== soll[i][0]"
              "       || Math.abs(p.x - soll[i][1]) > tol"
              "       || Math.abs(p.y - soll[i][2]) > tol) schlecht++;"
              " }"
              " window.__fm14bGeprueft = geprueft;"
              " return schlecht; })()" % toleranz)
        schlecht = self._zahl(js)
        geprueft = self._zahl("window.__fm14bGeprueft")
        return schlecht, geprueft

    # ── Die Messung ─────────────────────────────────────────────────────────

    def test_beide_fassungen_liefern_denselben_platz(self):
        """★★ Der Kern: fuer JEDEN Index bis Ring 3 liefern JS und Python
        denselben Ring und dieselbe Position."""
        self._modul_laden()
        schlecht, geprueft = self._abweichungen(_erwartung())
        self.assertEqual(geprueft, float(_BIS),
                         "es wurden nicht alle Indizes verglichen — ein "
                         "Vergleich ueber nichts meldet auch null Abweichungen")
        self.assertEqual(schlecht, 0.0,
                         f"{int(schlecht)} von {int(geprueft)} Plaetzen weichen "
                         f"ab: Python und JS sind auseinandergelaufen")

    def test_der_vergleich_wuerde_eine_abweichung_auch_melden(self):
        """★ Gegenprobe fuer den Vergleicher: EIN verschobener Platz muss
        auffallen. Ohne sie belegt der Test oben nur, dass die Schleife laeuft."""
        self._modul_laden()
        falsch = _erwartung()
        falsch[8][1] += 0.5          # ein halber Ringschritt beim Aussenring
        schlecht, geprueft = self._abweichungen(falsch)
        self.assertEqual(geprueft, float(_BIS))
        self.assertEqual(schlecht, 1.0)

    def test_die_toleranz_ist_eng_genug_fuer_kleine_drift(self):
        """★ Und sie darf nicht so weit sein, dass sie alles durchlaesst: schon
        1e-9 — viel zu klein fuer eine echte Positionsaenderung, aber tausendmal
        groesser als Rundungsrauschen — muss auffallen."""
        self._modul_laden()
        falsch = _erwartung()
        falsch[13][2] += 1e-9
        schlecht, _g = self._abweichungen(falsch)
        self.assertEqual(schlecht, 1.0)

    def test_ein_falscher_ring_faellt_auch_auf(self):
        """Die Ringnummer wird EXAKT verglichen (kein Toleranzfenster) — sie
        entscheidet im Raster ueber die ZEILE."""
        self._modul_laden()
        falsch = _erwartung()
        falsch[3][0] += 1
        schlecht, _g = self._abweichungen(falsch)
        self.assertEqual(schlecht, 1.0)

    def test_die_ringgroessen_stimmen_auf_beiden_seiten(self):
        """Die Aufteilung 1 / 6 / 12 / 18 ist die Aussage des Manuals; sie steht
        in beiden Fassungen in derselben Hilfsfunktion (``wabenPlaetze``, im JS
        modul-intern). Gemessen wird sie hier ueber das Ergebnis: wie viele
        Indizes JS auf welchem Ring einsortiert."""
        self._modul_laden()
        for ring, erwartet in ((0, 1), (1, 6), (2, 12), (3, 18)):
            js = ("(function () { let n = 0;"
                  " for (let i = 0; i < %d; i++)"
                  "   if (window.__fm14b.wabenPlatz(i).ring === %d) n++;"
                  " return n; })()" % (_BIS, ring))
            self.assertEqual(self._zahl(js), float(erwartet),
                             f"JS legt {erwartet} Plaetze auf Ring {ring} an?")
            self.assertEqual(
                sum(1 for i in range(_BIS) if waben_platz(i)[0] == ring),
                erwartet, f"Python legt {erwartet} Plaetze auf Ring {ring} an?")

    def test_der_erste_platz_liegt_wo_das_manual_ihn_zeichnet(self):
        """Eine von der Formel unabhaengige Ansage aus der Quelle: der erste
        Platz eines Rings liegt eine HALBE Teilung links von „unten" (270°).
        Innenring: 240°. Aussenring: 255°. Gemessen im JS, damit die Zusage
        nicht nur in der Python-Fassung steht."""
        self._modul_laden()
        for index, grad in ((1, 240.0), (7, 255.0)):
            js = ("(function () { const p = window.__fm14b.wabenPlatz(%d);"
                  " return ((Math.atan2(p.y, p.x) * 180 / Math.PI) %% 360"
                  "         + 360) %% 360; })()" % index)
            self.assertAlmostEqual(self._zahl(js), grad, places=6)
            k, x, y = waben_platz(index)
            self.assertAlmostEqual(
                (math.degrees(math.atan2(y, x)) % 360 + 360) % 360, grad,
                places=6)


if __name__ == "__main__":
    unittest.main()

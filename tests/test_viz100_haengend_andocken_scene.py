"""VIZ-100: an eine Traverse angedockte Moving Heads haengen wirklich darunter.

Befund (Projektinhaber, Gobo-Demo): "Die Koepfe stecken in der Traverse."
Gemessen: Traverse 5,85-6,15 m, Andocken setzt den Geraete-Ursprung 0,25 m
unter die Unterkante (5,60 m). Das Modell wurde aber vom Sockel nach OBEN
gebaut — Kopf-Drehpunkt 5,975 m, der Lichtaustritt sass mitten im Rohr.

Jetzt (ueber die ECHTE Seite, Geraeteliste + Buehne + Produktiv-Push):

* haengt das Geraet an einer horizontalen Traverse, sitzt der Sockel oben an
  deren Unterkante, Buegel und Kopf haengen frei darunter;
* die GESPEICHERTE Position bleibt, wo sie war (keine Show verschiebt sich);
* Pan/Tilt zeigen in dieselbe Richtung wie beim stehenden Geraet, Kegel und
  Bodenfleck gehen vom haengenden Kopf aus;
* An- und Abdocken, Entfernen der Traverse und ein Neuladen der Buehne
  schalten die Haltung um bzw. behalten sie;
* PARs und Stuetzen (vertikale Traversen) bleiben unveraendert.

Kein WebGL noetig: gemessen wird der Szenenzustand.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _geraet, _payload)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_HAENGT, _STEHT, _PAR_DOCK, _PAR_FREI, _STUETZE, _PIXEL = (
    921001, 921002, 921003, 921004, 921005, 921006)

_TRAVERSE = {"id": "t1", "type": "truss_h", "name": "Back",
             "position": {"x": 0, "y": 6.0, "z": 0},
             "size": {"x": 12, "y": 0.3, "z": 0.3}, "rotation": 0,
             "color": "#888888"}
_STUETZE_EL = {"id": "s1", "type": "truss_v", "name": "Stuetze",
               "position": {"x": 8, "y": 3.0, "z": 0},
               "size": {"x": 0.3, "y": 6.0, "z": 0.3}, "rotation": 0,
               "color": "#888888"}
_UNTERKANTE = 6.0 - 0.3 / 2          # 5,85
_DOCK_Y = _UNTERKANTE - 0.25         # 5,60 — das setzt das Andocken seit jeher
_KOPF_UEBER_SOCKEL = 0.375           # Kopf-Drehpunkt des stehenden Modells


# Lage eines Geraets in Weltkoordinaten. Die Koerperteile werden ueber ihre
# Stellung im Modell gefunden (Sockel = feste Teile der Modellgruppe, Buegel =
# Teile des Pan-Gelenks ohne den Kopf), nicht ueber Namen.
_LAGE_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  f.group.updateMatrixWorld(true);
  function yBereich(objs){
    let lo = Infinity, hi = -Infinity;
    objs.forEach(o => o.traverse(m => {
      if (!m.isMesh || !m.geometry) return;
      if (!m.geometry.boundingBox) m.geometry.computeBoundingBox();
      const b = m.geometry.boundingBox, e = m.matrixWorld.elements;
      [b.min.x, b.max.x].forEach(x => [b.min.y, b.max.y].forEach(y =>
        [b.min.z, b.max.z].forEach(z => {
          const wy = e[1]*x + e[5]*y + e[9]*z + e[13];
          lo = Math.min(lo, wy); hi = Math.max(hi, wy);
        })));
    }));
    return [lo, hi];
  }
  const out = { gruppe: [f.group.position.x, f.group.position.y, f.group.position.z],
                dock: f.dockedTo || null };
  if (f.yoke && f.head) {
    const modell = f.yoke.parent;
    out.sockel = yBereich(modell.children.filter(c => c !== f.yoke));
    out.buegel = yBereich(f.yoke.children.filter(c => c !== f.head));
    const e = f.head.matrixWorld.elements;
    const n = Math.hypot(e[4], e[5], e[6]) || 1;
    out.kopf = [e[12], e[13], e[14]];
    out.dir = [-e[4] / n, -e[5] / n, -e[6] / n];
    out.linseY = f.lens.matrixWorld.elements[13];
  } else {
    out.koerper = yBereich(f.group.children.filter(c => !c.isSprite));
  }
  if (f.floorSpot) {
    const p = f.floorSpot.position;
    out.fleck = [p.x, p.y, p.z];
    out.fleckSichtbar = f.floorSpot.visible;
  }
  if (f.beam) {
    f.beam.updateMatrixWorld(true);
    const a = f.beam.parent.matrixWorld.elements;
    out.kegelSpitze = [a[12], a[13], a[14]];
  }
  return JSON.stringify(out);
})()
"""


class _Viz100Basis(_Basis):
    BUEHNE = [_TRAVERSE, _STUETZE_EL]

    def _lage(self, fid):
        return json.loads(self._eval(_LAGE_JS % fid))

    def _buehne(self, objekte=None):
        daten = {"name": "T", "objects": self.BUEHNE if objekte is None else objekte}
        self._eval("(function(){ window.__lightos.loadStageJson(%s); return 1; })()"
                   % json.dumps(json.dumps(daten)))
        self._bild()

    def _start(self):
        self._load_and_wait()
        self._buehne()

    def _pruefe_haengt(self, z, y_ursprung=_DOCK_Y):
        # Sockel oben, buendig an der Unterkante der Traverse.
        self.assertAlmostEqual(z["sockel"][1], _UNTERKANTE, delta=0.003, msg=z)
        # Nichts vom Geraet ragt in die Traverse.
        self.assertLessEqual(z["buegel"][1], _UNTERKANTE + 0.001, z)
        self.assertLess(z["kopf"][1], _UNTERKANTE - 0.2, z)
        # Reihenfolge von oben nach unten: Sockel, Kopf-Drehpunkt, Linse.
        self.assertLess(z["kopf"][1], z["sockel"][0], z)
        self.assertLess(z["linseY"], z["kopf"][1], z)
        # Die gespeicherte Position hat sich nicht bewegt.
        self.assertAlmostEqual(z["gruppe"][1], y_ursprung, places=6, msg=z)

    def _pruefe_steht(self, z):
        self.assertAlmostEqual(z["sockel"][0], z["gruppe"][1], delta=0.003, msg=z)
        self.assertAlmostEqual(z["kopf"][1], z["gruppe"][1] + _KOPF_UEBER_SOCKEL,
                               places=4, msg=z)


class Viz100HaengendTest(_Viz100Basis):
    GERAETE = [
        _geraet(_HAENGT, x=-2, y=_DOCK_Y, dockedTo="t1", tiltRange=270),
        _geraet(_STEHT, x=2, y=_DOCK_Y, tiltRange=270),
    ]

    def test_angedockter_kopf_haengt_unter_der_traverse(self):
        """Der Befund: Geraeteliste zuerst, Buehne danach (Ladereihenfolge)."""
        self._start()
        self._pruefe_haengt(self._lage(_HAENGT))
        # Dasselbe Geraet ohne Andock-Bindung steht wie bisher.
        self._pruefe_steht(self._lage(_STEHT))

    def test_pan_tilt_richtung_und_bodenfleck(self):
        self._start()
        # Stellbare Uhr: die Bewegungsglaettung (VIZ-92) ist je Schritt
        # ausgelaufen, bevor gemessen wird.
        self._uhr(0)
        werte = ((128, 128), (128, 90), (60, 100), (200, 150), (10, 70))
        for i, (pan, tilt) in enumerate(werte):
            self._uhr((i + 1) * 10000.0)
            self._push(_payload(_HAENGT, pan=pan, tilt=tilt),
                       _payload(_STEHT, pan=pan, tilt=tilt))
            self._bild((i + 1) * 10000.0 + 5000.0)
            h, s = self._lage(_HAENGT), self._lage(_STEHT)
            with self.subTest(pan=pan, tilt=tilt):
                self._pruefe_haengt(h)
                # Gleiche DMX-Werte -> gleiche Strahlrichtung wie stehend.
                for a, b in zip(h["dir"], s["dir"]):
                    self.assertAlmostEqual(a, b, places=6, msg=(h, s))
                # Der Kegel beginnt am haengenden Kopf.
                for a, b in zip(h["kegelSpitze"], h["kopf"]):
                    self.assertAlmostEqual(a, b, places=6, msg=h)
                # Der Bodenfleck liegt dort, wo der Strahl AUS DIESEM KOPF den
                # Boden trifft (nichts im Weg: die Traverse liegt ueber ihm).
                self.assertLess(h["dir"][1], -0.05, h)          # Vorbedingung
                t = -h["kopf"][1] / h["dir"][1]
                self.assertTrue(h["fleckSichtbar"], h)
                self.assertAlmostEqual(h["fleck"][0], h["kopf"][0] + h["dir"][0] * t,
                                       places=4, msg=h)
                self.assertAlmostEqual(h["fleck"][2], h["kopf"][2] + h["dir"][2] * t,
                                       places=4, msg=h)
                self.assertAlmostEqual(h["fleck"][1], 0.01, places=3, msg=h)

    def test_abdocken_und_andocken_schalten_um(self):
        self._start()
        self._pruefe_haengt(self._lage(_HAENGT))

        def transform(fid, dock):
            return lambda: self._bridge_obj.applyFixtureTransform.emit(json.dumps(
                {"fid": fid, "x": None, "y": None, "z": None, "dock": dock}))

        # Abdocken ueber den Python->JS-Weg (Undo/Redo einer Gestik).
        self._emit_until_true(
            transform(_HAENGT, ""),
            "!window.__lightos.fixtures['%d'].dockedTo" % _HAENGT)
        self._bild()
        self._pruefe_steht(self._lage(_HAENGT))
        # Der Bodenfleck folgt dem Kopf zurueck (senkrecht darunter).
        self._push(_payload(_HAENGT))
        self._bild()
        z = self._lage(_HAENGT)
        self.assertAlmostEqual(z["fleck"][0], -2, places=4, msg=z)

        # Andocken wie am Ende eines Ziehens (pointer.js schreibt f.dockedTo).
        self._eval("(function(){ window.__lightos.fixtures['%d'].dockedTo = 't1';"
                   " window.__lightos.requestRender(); return 1; })()" % _STEHT)
        self._bild()
        self._pruefe_haengt(self._lage(_STEHT))

    def test_traverse_entfernen_stellt_das_geraet_wieder_auf(self):
        self._start()
        self._pruefe_haengt(self._lage(_HAENGT))
        self._emit_until_true(
            lambda: self._bridge_obj.removeStageObject.emit("t1"),
            "!window.__lightos.stageObjects['t1']")
        self._bild()
        z = self._lage(_HAENGT)
        self.assertIsNone(z["dock"], z)
        self._pruefe_steht(z)

    def test_buehne_neu_laden_behaelt_bindung_und_haltung(self):
        """Ein Neuladen der Buehne raeumt alle Elemente weg und baut sie neu.
        Die Bindung an ein Element, das danach wieder da ist, bleibt."""
        self._start()
        verschoben = dict(_TRAVERSE, name="Back 2")
        self._buehne([verschoben, _STUETZE_EL])
        z = self._lage(_HAENGT)
        self.assertEqual(z["dock"], "t1", z)
        self._pruefe_haengt(z)
        # Ist das Element nach dem Laden NICHT mehr da, ist auch die Bindung weg.
        self._buehne([_STUETZE_EL])
        z = self._lage(_HAENGT)
        self.assertIsNone(z["dock"], z)
        self._pruefe_steht(z)


class Viz100AndereGeraeteTest(_Viz100Basis):
    GERAETE = [
        _geraet(_PAR_DOCK, typ="par", x=-3, y=_DOCK_Y, dockedTo="t1"),
        _geraet(_PAR_FREI, typ="par", x=3, y=_DOCK_Y),
        # An einer Stuetze "haengt" nichts — die Haltung bleibt stehend.
        _geraet(_STUETZE, x=8, y=1.0, dockedTo="s1"),
        _geraet(_PIXEL, typ="pixel_head", x=0, y=_DOCK_Y, dockedTo="t1",
                nHeads=8, pixelBase=1),
    ]

    def test_par_bleibt_wie_es_war(self):
        self._start()
        a, b = self._lage(_PAR_DOCK), self._lage(_PAR_FREI)
        self.assertEqual([round(v, 6) for v in a["koerper"]],
                         [round(v, 6) for v in b["koerper"]])

    def test_stuetze_dreht_nichts_um(self):
        self._start()
        self._pruefe_steht(self._lage(_STUETZE))

    def test_pixel_kopf_haengt_ebenfalls(self):
        self._start()
        self._pruefe_haengt(self._lage(_PIXEL))

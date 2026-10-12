"""VIZ-104: Strobe im 3D — die Verdrahtung in der ECHTEN Seite.

``test_viz104_strobe_im_3d.py`` prueft die Rechnung (Python und, unter Node,
``scene_src/fixtures/strobe.js``). Hier laeuft der Produktiv-Weg: Payload aus
``_build_fixture_payload`` -> Push -> ``updateFixture`` -> Takt je Bild
(``tickStrobe``) mit einer stellbaren Uhr.

* Shutter im Strobe-Bereich: Kegel, Licht, Bodenfleck und Linse gehen im Takt
  an und aus — an fuer rund ein Viertel der Bilder;
* Shutter offen: Dauerlicht, kein Bild dunkel;
* ein Update mitten im Lauf (anderer Dimmerwert, andere Farbe) startet die
  Phase nicht neu, und die Farbe bleibt, wie sie gemeldet wurde;
* „Gedaempft" pulsiert, ohne je dunkel zu werden; „Aus" ist Dauerlicht — beides
  wirkt sofort, ohne neues Update;
* je Blitz entsteht keine neue Shadow-Map;
* Dimmer auf 0 mit Strobe: dunkel, und das Geraet zaehlt nicht als blitzend.

Kein WebGL noetig: gemessen wird der Szenenzustand.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _Ch, _FID, _Range, _fx, _geraet, _pump)
from src.ui.visualizer.visualizer_service import _build_fixture_payload  # noqa: E402


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _bereich(lo, hi, name, kind):
    r = _Range(lo, hi, name)
    r.kind = kind
    return r


_KANAELE = [
    _Ch("intensity"), _Ch("color_r"), _Ch("color_g"), _Ch("color_b"),
    _Ch("pan"), _Ch("tilt"),
    _Ch("shutter", [_bereich(0, 9, "Zu", "closed"),
                    _bereich(10, 19, "Offen", "open"),
                    _bereich(20, 219, "Strobe 1-20 Hz", "strobe"),
                    _bereich(220, 255, "Offen", "open")]),
]
_OFFEN = 15
_STROBE_5HZ = 20 + round(199 * (5 - 1) / 19)       # ~5 Hz im Bereich 1-20 Hz


def _payload(**attrs):
    a = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
         "pan": 128, "tilt": 128, "shutter": _OFFEN}
    a.update(attrs)
    return _build_fixture_payload(_fx(_FID), a, _KANAELE)


_ZUSTAND_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  const i = L.strobeInfo(%d);
  return JSON.stringify({
    spot: f.spot ? f.spot.intensity : null,
    kegel: f.beam ? f.beam.material.opacity : null,
    kegelSichtbar: f.beam ? f.beam.visible : null,
    fleck: f.floorSpot ? f.floorSpot.material.opacity : null,
    linse: (f.lens && f.lens.material) ? f.lens.material.emissiveIntensity : null,
    farbe: f.beam ? [f.beam.material.color.r, f.beam.material.color.g, f.beam.material.color.b] : null,
    info: i,
    schatten: L.shadowUpdateStats ? L.shadowUpdateStats().neubauten : null,
  });
})()
"""


class Viz104StrobeSzeneTest(_Basis):
    GERAETE = [_geraet()]

    def _z(self):
        return json.loads(self._eval(_ZUSTAND_JS % (_FID, _FID)))

    def _strobe_uhr(self, t, fps=60):
        self._eval("(function(){ window.__t104 = %r; window.__lightos.__strobeUhr("
                   "() => window.__t104, %r); return 1; })()" % (float(t), float(fps)))

    def _bild104(self, t):
        self._eval("(function(){ window.__t104 = %r; window.__lightos.__renderTick();"
                   " return 1; })()" % float(t))
        return self._z()

    def _lauf(self, start, dauer_ms, schritt_ms=1000 / 60):
        """Bilder im 60er-Raster; liefert je Bild den Zustand."""
        bilder, t = [], start
        while t < start + dauer_ms:
            bilder.append(self._bild104(t))
            t += schritt_ms
        return bilder

    def _modus(self, modus):
        self._bridge_obj.settingsChanged.emit(json.dumps({"strobeMode": modus}))
        self._poll_until_true(
            "window.__lightos.strobeInfo(%d).modus === '%s'" % (_FID, modus))

    def test_payload_meldet_die_frequenz(self):
        self.assertEqual(_payload()["strobe_hz"], 0.0)
        self.assertAlmostEqual(_payload(shutter=_STROBE_5HZ)["strobe_hz"], 5.0, delta=0.06)

    def test_strobe_blitzt_kegel_licht_fleck_und_linse(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_STROBE_5HZ))
        bilder = self._lauf(2.0, 2000)
        an = [b for b in bilder if b["spot"] > 0]
        aus = [b for b in bilder if b["spot"] == 0]
        self.assertTrue(an and aus, "der Lauf muss an UND aus sehen")
        anteil = len(an) / len(bilder)
        self.assertTrue(0.2 <= anteil <= 0.34, anteil)
        # Zahl der Blitze: ~5 Hz ueber 2 s.
        blitze = sum(1 for i in range(1, len(bilder))
                     if bilder[i]["spot"] > 0 and bilder[i - 1]["spot"] == 0)
        self.assertTrue(9 <= blitze <= 11, blitze)
        for b in an:
            self.assertGreater(b["kegel"], 0, b)
            self.assertGreater(b["linse"], 0, b)
            self.assertGreater(b["fleck"], 0, b)
            self.assertEqual(b["info"]["faktor"], 1)
        for b in aus:
            self.assertEqual(b["kegel"], 0, b)
            self.assertFalse(b["kegelSichtbar"], b)
            self.assertEqual(b["linse"], 0, b)
            self.assertEqual(b["fleck"], 0, b)
        self.assertTrue(bilder[0]["info"]["aktiv"])
        self.assertAlmostEqual(bilder[0]["info"]["hz"], 5.0, delta=0.06)

    def test_shutter_offen_ist_dauerlicht(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_OFFEN))
        bilder = self._lauf(2.0, 600)
        self.assertTrue(all(b["spot"] > 0 and b["kegel"] > 0 for b in bilder))
        self.assertFalse(bilder[0]["info"]["aktiv"])
        self.assertEqual(bilder[0]["info"]["blitzend"], 0)

    def test_update_startet_die_phase_nicht_neu_und_laesst_die_farbe(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_STROBE_5HZ))
        ohne = [b["spot"] > 0 for b in self._lauf(2.0, 1000)]
        # Derselbe Lauf noch einmal, diesmal mit einem Update vor JEDEM Bild
        # (wechselnder Dimmerwert, rote Farbe).
        mit, farben, t = [], [], 2.0
        i = 0
        while t < 2.0 + 1000:
            self._eval("(function(){ window.__t104 = %r; return 1; })()" % float(t))
            self._push(_payload(shutter=_STROBE_5HZ, intensity=200 + (i % 2) * 55,
                                color_g=0, color_b=0))
            b = self._bild104(t)
            mit.append(b["spot"] > 0)
            farben.append(b["farbe"])
            t += 1000 / 60
            i += 1
        self.assertEqual(mit, ohne, "ein Update darf den Blitz nicht neu starten")
        for f in farben:
            self.assertEqual([round(v, 3) for v in f], [1.0, 0.0, 0.0])

    def test_gedaempft_und_aus_wirken_sofort(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_STROBE_5HZ))
        voll = max(b["spot"] for b in self._lauf(2.0, 400))
        self._modus("soft")
        weich = [b["spot"] for b in self._lauf(1000.0, 1500)]
        self.assertGreater(min(weich), voll * 0.5, "gedaempft wird nie dunkel")
        self.assertAlmostEqual(max(weich), voll, delta=voll * 0.01)
        self.assertGreater(len(set(round(w, 4) for w in weich)), 4, "es pulsiert")
        self.assertLess(min(weich), voll * 0.7)
        self._modus("off")
        aus = self._lauf(3000.0, 600)
        self.assertTrue(all(abs(b["spot"] - voll) < 1e-9 for b in aus), "Dauerlicht")
        self.assertFalse(aus[-1]["info"]["aktiv"])
        self._modus("flash")
        wieder = [b["spot"] for b in self._lauf(4000.0, 600)]
        self.assertIn(0, wieder)
        self.assertIn(voll, wieder)

    def test_kein_schatten_neubau_je_blitz(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_STROBE_5HZ))
        self._lauf(2.0, 400)                       # einschwingen (Pool vergibt Lichter)
        vorher = self._z()["schatten"]
        if vorher is None:
            self.skipTest("shadowUpdateStats nicht exportiert")
        bilder = self._lauf(500.0, 2000)
        blitze = sum(1 for i in range(1, len(bilder))
                     if bilder[i]["spot"] > 0 and bilder[i - 1]["spot"] == 0)
        self.assertGreaterEqual(blitze, 9)
        self.assertLessEqual(bilder[-1]["schatten"] - vorher, 2,
                             "je Blitz entstand eine neue Shadow-Map")

    def test_dimmer_null_blitzt_nicht(self):
        self._load_and_wait()
        self._strobe_uhr(0)
        self._push(_payload(shutter=_STROBE_5HZ, intensity=0))
        bilder = self._lauf(2.0, 500)
        self.assertTrue(all(b["spot"] == 0 and b["kegel"] == 0 for b in bilder))
        self.assertFalse(bilder[0]["info"]["aktiv"])
        self.assertAlmostEqual(bilder[0]["info"]["hz"], 5.0, delta=0.06)

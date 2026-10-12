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


_N = 11
_FIDS = [_FID + i for i in range(_N)]


def _payload_fid(fid, **attrs):
    a = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
         "pan": 128, "tilt": 128, "shutter": _OFFEN}
    a.update(attrs)
    return _build_fixture_payload(_fx(fid), a, _KANAELE)


class Viz104StrobeBehaeltSeinLichtTest(_Basis):
    """Mehr Strahlen als echte Lichter (Stufe Hoch: 8): ein Geraet, das zu
    blitzen beginnt, gibt sein Licht in der Dunkelphase NICHT an einen
    wartenden Strahl ab — sonst beleuchtete der Strobe die Buehne nach dem
    ersten Blitz nicht mehr, und jeder Wechsel kostete einen Schattendurchlauf."""

    GERAETE = [_geraet(fid=f, x=(i - _N // 2) * 1.5) for i, f in enumerate(_FIDS)]

    def _pool(self):
        return json.loads(self._eval("JSON.stringify(window.__lightos.spotPoolInfo())"))

    def _bild_t(self, t):
        self._eval("(function(){ window.__t104 = %r; window.__lightos.__renderTick();"
                   " return 1; })()" % float(t))

    def test_blitzender_halter_behaelt_sein_licht(self):
        self._load_and_wait()
        self._eval("(function(){ window.__t104 = 0; const L = window.__lightos;"
                   " L.__strobeUhr(() => window.__t104, 60);"
                   " L.__spotPoolUhr(() => window.__t104); return 1; })()")
        self._push(*[_payload_fid(f) for f in _FIDS])
        t = 0.0
        for _ in range(60):                       # einschwingen
            t += 1000 / 60
            self._bild_t(t)
        vorher = self._pool()
        halter = [h for h in vorher["halter"] if h is not None]
        self.assertEqual(len(halter), vorher["groesse"])
        self.assertLess(len(halter), _N, "Vorbedingung: mehr Strahlen als Lichter")
        blitzer = halter[:2]
        self._push(*[_payload_fid(f, shutter=_STROBE_5HZ) for f in blitzer])
        dunkel_gesehen = False
        for _ in range(180):                      # 3 s, 15 Blitze
            t += 1000 / 60
            self._bild_t(t)
            if json.loads(self._eval(
                    "JSON.stringify(window.__lightos.strobeInfo(%d))" % blitzer[0]))["faktor"] == 0:
                dunkel_gesehen = True
        self.assertTrue(dunkel_gesehen)
        nachher = self._pool()
        for f in blitzer:
            self.assertIn(f, nachher["halter"], "der Strobe hat sein Licht verloren")
        self.assertEqual(nachher["vergaben"], vorher["vergaben"], "Lichter sind gewandert")


# ── Je Kopf: eigener Shutter je Kopf -> jeder Kopf blitzt fuer sich ───────────

_BAR = _FID + 500
_SHUTTER_BEREICHE = _KANAELE[-1].ranges
_BAR_EIGEN = [_Ch("intensity"),
              _Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("shutter", _SHUTTER_BEREICHE),
              _Ch("color_r"), _Ch("color_g"), _Ch("color_b"), _Ch("shutter", _SHUTTER_BEREICHE)]
_BAR_GEMEINSAM = _BAR_EIGEN[:-1]
_STROBE_2HZ = 20 + round(199 * (2 - 1) / 19)


def _bar_payload(kanaele, **attrs):
    a = {"intensity": 255, "color_r": 255, "color_g": 255, "color_b": 255,
         "color_r#1": 255, "color_g#1": 255, "color_b#1": 255, "shutter": _OFFEN}
    if kanaele is _BAR_EIGEN:
        a["shutter#1"] = _OFFEN
    a.update(attrs)
    return _build_fixture_payload(_fx(_BAR, "led_bar"), a, kanaele)


_KOEPFE_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  return JSON.stringify({
    linsen: f.parHeads.map(p => p.lens.material.emissiveIntensity),
    info: L.strobeInfo(%d),
  });
})()
"""


def _blitze(folge):
    return sum(1 for i in range(1, len(folge)) if folge[i] > 0 and folge[i - 1] == 0)


class Viz104StrobeJeKopfTest(_Basis):
    GERAETE = [dict(_geraet(fid=_BAR, typ="par_bar"), nHeads=2)]

    def _lauf_koepfe(self, start, dauer_ms):
        bilder, t = [], start
        while t < start + dauer_ms:
            self._eval("(function(){ window.__t104 = %r; window.__lightos.__renderTick();"
                       " return 1; })()" % float(t))
            bilder.append(json.loads(self._eval(_KOEPFE_JS % (_BAR, _BAR))))
            t += 1000 / 60
        return bilder

    def _start(self, payload):
        self._load_and_wait()
        self._eval("(function(){ window.__t104 = 0; window.__lightos.__strobeUhr("
                   "() => window.__t104, 60); return 1; })()")
        self._push(payload)

    def test_payload_traegt_die_frequenz_je_kopf(self):
        p = _bar_payload(_BAR_EIGEN, shutter=_STROBE_5HZ)
        self.assertAlmostEqual(p["heads"][0]["strobe_hz"], 5.0, delta=0.06)
        self.assertEqual(p["heads"][1]["strobe_hz"], 0.0)
        for h in _bar_payload(_BAR_GEMEINSAM, shutter=_STROBE_5HZ)["heads"]:
            self.assertNotIn("strobe_hz", h)

    def test_nur_kopf_1_blitzt_kopf_2_bleibt_ruhig(self):
        self._start(_bar_payload(_BAR_EIGEN, shutter=_STROBE_5HZ))
        bilder = self._lauf_koepfe(2.0, 2000)
        k1 = [b["linsen"][0] for b in bilder]
        k2 = [b["linsen"][1] for b in bilder]
        self.assertIn(0, k1)
        self.assertTrue(9 <= _blitze(k1) <= 11, _blitze(k1))
        self.assertTrue(all(v > 0 for v in k2), "Kopf 2 muss Dauerlicht zeigen")
        self.assertEqual(len(set(k2)), 1)
        self.assertEqual(max(k1), k2[0], "im Blitz so hell wie der ruhige Kopf")
        self.assertTrue(bilder[0]["info"]["aktiv"])
        self.assertEqual(bilder[0]["info"]["faktor"], 1, "das Geraet als Ganzes blitzt nicht")

    def test_nur_kopf_2_blitzt(self):
        self._start(_bar_payload(_BAR_EIGEN, **{"shutter#1": _STROBE_5HZ}))
        bilder = self._lauf_koepfe(2.0, 1000)
        self.assertTrue(all(b["linsen"][0] > 0 for b in bilder))
        self.assertIn(0, [b["linsen"][1] for b in bilder])

    def test_beide_koepfe_verschieden_schnell(self):
        self._start(_bar_payload(_BAR_EIGEN, shutter=_STROBE_2HZ,
                                 **{"shutter#1": _STROBE_5HZ}))
        bilder = self._lauf_koepfe(2.0, 2000)
        b1 = _blitze([b["linsen"][0] for b in bilder])
        b2 = _blitze([b["linsen"][1] for b in bilder])
        self.assertTrue(3 <= b1 <= 5, b1)
        self.assertTrue(9 <= b2 <= 11, b2)
        hz = bilder[0]["info"]["kopfHz"]
        self.assertAlmostEqual(hz[0], 2.0, delta=0.06)
        self.assertAlmostEqual(hz[1], 5.0, delta=0.06)

    def test_ein_gemeinsamer_kanal_blitzt_alle_koepfe_zusammen(self):
        self._start(_bar_payload(_BAR_GEMEINSAM, shutter=_STROBE_5HZ))
        bilder = self._lauf_koepfe(2.0, 2000)
        k1 = [b["linsen"][0] for b in bilder]
        k2 = [b["linsen"][1] for b in bilder]
        self.assertEqual([v > 0 for v in k1], [v > 0 for v in k2])
        self.assertTrue(9 <= _blitze(k1) <= 11, _blitze(k1))
        self.assertIsNone(bilder[0]["info"]["kopfHz"])

    def test_aus_und_gedaempft_gelten_auch_je_kopf(self):
        self._start(_bar_payload(_BAR_EIGEN, shutter=_STROBE_5HZ))
        voll = max(b["linsen"][0] for b in self._lauf_koepfe(2.0, 400))
        self._bridge_obj.settingsChanged.emit(json.dumps({"strobeMode": "soft"}))
        self._poll_until_true("window.__lightos.strobeInfo(%d).modus === 'soft'" % _BAR)
        weich = [b["linsen"][0] for b in self._lauf_koepfe(1000.0, 1000)]
        self.assertGreater(min(weich), voll * 0.5)
        self._bridge_obj.settingsChanged.emit(json.dumps({"strobeMode": "off"}))
        self._poll_until_true("window.__lightos.strobeInfo(%d).modus === 'off'" % _BAR)
        aus = [b["linsen"][0] for b in self._lauf_koepfe(3000.0, 400)]
        self.assertTrue(all(abs(v - voll) < 1e-9 for v in aus))

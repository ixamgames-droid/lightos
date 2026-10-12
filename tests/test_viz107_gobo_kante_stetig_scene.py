"""VIZ-107 — das Gobo-Muster springt nicht, wenn die Strahlmitte die Buehnenkante ueberquert.

Laeuft in der seriellen Spur der QWebEngineView-Dateien (echte Seite).

**Der Befund (Bedientest QA-96, 11.10.2026, Stand MIT VIZ-102):** auf der
Stufe „Niedrig“ — die „Automatisch“ auf Intel-UHD waehlt — springt das
Gobo-Muster an der Buehnenkante. Dort ist jedes Gobo die flache Musterscheibe.

**Gemessen** (Moving Head 6 m hoch ueber einem Podest 6 x 1 x 4 m, Tilt in
Einzelschritten ueber die Vorderkante): solange die Strahlmitte auf der
Oberseite liegt, beschneidet VIZ-102 die Scheibe an der Kante und legt den
Ueberhang als zweite Scheibe auf den Hallenboden. Im Schritt, in dem die Mitte
die Kante ueberquert, galt aber „trifft den Boden, keine Kante“: der Teil des
Musters auf der Buehne verschwand in einem Bild, obwohl der halbe Kegel sie
noch traf; der Kegel wurde im selben Bild schmaler und der Bodenteil heller.

**Jetzt** bleibt die Anordnung stehen, bis der Kegel die Oberseite verlassen
hat (``builders.js#_oberseiteImKegel``): erste Scheibe auf der Oberseite,
zweite am Boden; Kegelwinkel und Helligkeit gehen stufenlos ueber.

Gemessen wird ueber die echte Seite (Produktiv-Push), Tilt in Einzelschritten.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz96_gobo_projektion_scene import (         # noqa: E402
    _Basis, _FID, _RING, _geraet, _payload)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


_OBEN = 1.0            # Oberkante des Podests (m)
_KANTE_Z = 2.0         # Vorderkante des Podests (m)

# Je Schritt: wo liegen die Scheiben, wie weit ist der Kegel, wie hell der Boden?
_LAGE_JS = """
(function(){
  try {
  const L = window.__lightos, f = L.fixtures['%d'];
  function lage(o){ o.updateMatrixWorld(true); const e = o.matrixWorld.elements;
    return [e[12], e[13], e[14]]; }
  function geschnitten(m){ const c = m && m.clippingPlanes;
    return !!c && c.some(p => Math.abs(p.constant) < 1e5); }
  const a = f.floorSpot, b = f.floorSpot2 || null;
  const kt = f._koerperTreffer || null;
  const p = f.beam.geometry.parameters;
  const zwei = !!(b && b.visible);
  return JSON.stringify({
    eins: lage(a), einsSichtbar: a.visible, einsGeschnitten: geschnitten(a.material),
    einsDeck: a.material.opacity, fleckY: a.position.y,
    zwei: zwei ? lage(b) : null,
    zweiDeck: zwei ? b.material.opacity : null,
    mitteOben: !!(kt && kt.oben && kt.kante),
    ziel: [f.spotTarget.position.x, f.spotTarget.position.y, f.spotTarget.position.z],
    durchmesser: 2 * p.radius * f.beam.scale.x,
    laenge: f.baseBeamLength * f.beam.scale.y, grund: f.baseBeamLength,
    kegelGeschnitten: !!f._kegelSchnitt,
    innen: (f._neben && typeof f._neben.innen === 'number') ? f._neben.innen : null,
  });
  } catch (e) { return JSON.stringify({fehler: String(e && e.stack || e)}); }
})()
"""


def _boden(z):
    """Mitte und Deckkraft des Musterteils, der am Hallenboden liegt."""
    if z["zwei"] is not None:
        return z["zwei"], z["zweiDeck"]
    if abs(z["eins"][1] - 0.01) < 1e-6:
        return z["eins"], z["einsDeck"]
    return None, None


def _auf_der_buehne(z):
    """Liegt ein Teil des Musters auf der Oberseite des Podests?"""
    return z["einsSichtbar"] and abs(z["eins"][1] - (_OBEN + 0.01)) < 1e-6


class _KanteBasis(_Basis):
    GERAETE = [_geraet(tiltRange=270)]
    TILTS = list(range(128, 88, -1))      # von senkrecht ueber die Vorderkante hinaus

    def _podest(self):
        self._bridge_obj.addStageObjectData.emit(json.dumps({
            "id": "podest", "type": "platform",
            "position": {"x": 0, "y": _OBEN / 2, "z": 0},
            "size": {"x": 6, "y": _OBEN, "z": 2 * _KANTE_Z},
        }))
        self._poll_until_true("!!window.__lightos.stageObjects['podest']")

    def _lage(self):
        z = json.loads(self._eval(_LAGE_JS % _FID))
        self.assertNotIn("fehler", z, z.get("fehler"))
        return z

    def _fahrt(self, tilts, **attrs):
        """Tilt in Einzelschritten; die Uhr laeuft weit genug, dass der
        angezeigte Kopf je Schritt am Ziel steht (Glaettung, VIZ-92)."""
        reihe = []
        for tilt in tilts:
            self._schritt += 1
            t = self._schritt * 100000.0
            self._uhr(t)
            self._push(_payload(tilt=tilt, **attrs))
            self._bild(t + 50000.0)
            z = self._lage()
            z["tilt"] = tilt
            reihe.append(z)
        return reihe

    def _start(self, podest=True):
        self._load_and_wait()
        if podest:
            self._podest()
        self._schritt = 0
        self._uhr(0)


class Viz107NiedrigTest(_KanteBasis):
    TIER = "low"

    def _hin(self):
        self._start()
        reihe = self._fahrt(self.TILTS, gobo_wheel=_RING)
        mitte = [z["mitteOben"] for z in reihe]
        self.assertTrue(mitte[0] and not mitte[-1], "Aufbau: die Fahrt ueberquert die Kante")
        wechsel = mitte.index(False)
        self.assertTrue(all(mitte[:wechsel]) and not any(mitte[wechsel:]), mitte)
        self.assertGreaterEqual(wechsel, 5)
        return reihe, wechsel

    def test_teil_auf_der_buehne_bleibt_nach_dem_kantenwechsel(self):
        """★ Der gemeldete Sprung: im Schritt nach dem Kantenwechsel war der
        Teil auf der Buehne weg, obwohl der halbe Kegel sie noch traf."""
        reihe, wechsel = self._hin()
        nach = reihe[wechsel]
        self.assertTrue(_auf_der_buehne(nach), f"Teil auf der Buehne verschwunden: {nach}")
        self.assertTrue(nach["einsGeschnitten"], "auf der Buehne muss an der Kante Schluss sein")
        self.assertIsNotNone(nach["zwei"], "der Rest gehoert auf den Hallenboden")
        self.assertAlmostEqual(nach["zwei"][1], 0.01, places=6)
        self.assertTrue(nach["kegelGeschnitten"], "Kegel scheint sonst durch die Buehne")
        # ... und er bleibt mehrere Schritte, nicht nur einen.
        dauer = sum(1 for z in reihe[wechsel:] if _auf_der_buehne(z))
        self.assertGreaterEqual(dauer, 3, [z["innen"] for z in reihe[wechsel:]])

    def test_anteil_auf_der_buehne_nimmt_stetig_ab(self):
        reihe, wechsel = self._hin()
        innen = [z["innen"] for z in reihe[wechsel:] if z["innen"] is not None]
        self.assertGreater(innen[0], 0.6, "kurz nach der Kante liegt noch viel auf der Buehne")
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(innen, innen[1:])), innen)
        self.assertLess(max(a - b for a, b in zip(innen, innen[1:])), 0.45, innen)

    def test_muster_am_boden_wandert_ohne_sprung(self):
        reihe, wechsel = self._hin()
        spur = [(z["tilt"],) + tuple(_boden(z)[0]) for z in reihe if _boden(z)[0] is not None]
        self.assertGreaterEqual(len(spur), len(reihe) - wechsel)
        schritte = [abs(b[3] - a[3]) for a, b in zip(spur, spur[1:])]
        self.assertLess(max(schritte), 0.35, f"Sprung am Boden: {spur}")
        self.assertTrue(all(abs(p[2] - 0.01) < 1e-6 for p in spur), spur)

    def test_kegel_bleibt_gleich_weit_ueber_den_kantenwechsel(self):
        """Vorher wechselte der Bezug des Kegelwinkels im selben Bild von der
        Buehne zum Boden — der Kegel (und mit ihm das Muster) wurde schmaler."""
        reihe, wechsel = self._hin()
        weite = [z["durchmesser"] for z in reihe]
        rel = [abs(b - a) / a for a, b in zip(weite, weite[1:])]
        self.assertLess(max(rel), 0.06, f"Kegelweite springt: {list(zip(self.TILTS, weite))}")
        self.assertAlmostEqual(weite[wechsel], weite[wechsel - 1], delta=0.06 * weite[wechsel - 1])

    def test_helligkeit_am_boden_ohne_sprung(self):
        """Der Bodenteil ist schwaecher als der auf der Buehne (Abstandsquadrat)
        und wird erst heller, waehrend der Kegel die Buehne verlaesst."""
        reihe, wechsel = self._hin()
        hell = [(z["tilt"], _boden(z)[1] / z["einsDeck"]) for z in reihe[wechsel - 1:]
                if _boden(z)[1] is not None and z["einsDeck"] > 0]
        werte = [h for _t, h in hell]
        self.assertLess(max(abs(b - a) for a, b in zip(werte, werte[1:])), 0.2, hell)
        self.assertLess(werte[0], 0.9, "auf dem Boden schwaecher als auf der Buehne")
        self.assertAlmostEqual(werte[-1], 1.0, places=6, msg="allein am Boden: volle Helligkeit")

    def test_am_ende_wie_ohne_buehne(self):
        reihe, _wechsel = self._hin()
        ende = reihe[-1]
        self.assertIsNone(ende["innen"], "der Kegel hat die Buehne verlassen")
        self.assertIsNone(ende["zwei"])
        self.assertFalse(ende["einsGeschnitten"])
        self.assertFalse(ende["kegelGeschnitten"])
        self.assertAlmostEqual(ende["eins"][1], 0.01, places=6)
        self.assertAlmostEqual(ende["fleckY"], 0.01, places=6)

    def test_rueckweg_ist_derselbe_weg(self):
        """Von der Halle zurueck auf die Buehne: dieselben Zustaende in
        umgekehrter Reihenfolge — der Teil auf der Buehne erscheint, BEVOR
        die Strahlmitte die Kante erreicht."""
        reihe, wechsel = self._hin()
        zurueck = self._fahrt(list(reversed(self.TILTS)), gobo_wheel=_RING)[::-1]
        for hin, her in zip(reihe, zurueck):
            with self.subTest(tilt=hin["tilt"]):
                self.assertEqual(_auf_der_buehne(hin), _auf_der_buehne(her))
                self.assertEqual(hin["zwei"] is None, her["zwei"] is None)
                self.assertAlmostEqual(hin["durchmesser"], her["durchmesser"], places=6)
                for x, y in zip(hin["eins"], her["eins"]):
                    self.assertAlmostEqual(x, y, places=6)
        self.assertTrue(_auf_der_buehne(zurueck[wechsel]))

    def test_das_ziel_des_lichts_bleibt_der_echte_auftreffpunkt(self):
        """Die Scheibe bleibt auf der Buehne, das Licht zielt weiter dorthin,
        wo die Strahlmitte auftrifft: auf den Boden."""
        reihe, wechsel = self._hin()
        nach = reihe[wechsel]
        self.assertAlmostEqual(nach["ziel"][1], 0.0, places=6)
        self.assertGreater(nach["ziel"][2], _KANTE_Z)
        self.assertAlmostEqual(nach["fleckY"], 0.01, places=6)

    def test_offener_strahl_wie_bisher(self):
        """Ohne Gobo gibt es keine zweite Scheibe (VIZ-102) — und auch nach dem
        Kantenwechsel keine Scheibe, die auf der Buehne liegen bleibt."""
        self._start()
        reihe = self._fahrt(self.TILTS, gobo_wheel=0)
        wechsel = [z["mitteOben"] for z in reihe].index(False)
        nach = reihe[wechsel]
        self.assertIsNone(nach["innen"])
        self.assertIsNone(nach["zwei"])
        self.assertAlmostEqual(nach["eins"][1], 0.01, places=6)
        self.assertFalse(nach["einsGeschnitten"])

    def test_ohne_buehne_wird_nichts_gesucht(self):
        self._start(podest=False)
        reihe = self._fahrt(self.TILTS[::4], gobo_wheel=_RING)
        self.assertTrue(all(z["innen"] is None and z["zwei"] is None for z in reihe))
        self.assertTrue(all(abs(z["eins"][1] - 0.01) < 1e-6 for z in reihe))


class Viz107HochTest(_KanteBasis):
    """Auf „Hoch“ projiziert das Licht das Muster; die flache Scheibe ist dort
    das Rueckfall-Muster. Kegel und Anordnung folgen derselben Regel."""
    TIER = "high"

    def test_kegel_und_anordnung_wie_auf_niedrig(self):
        self._start()
        reihe = self._fahrt(self.TILTS, gobo_wheel=_RING)
        mitte = [z["mitteOben"] for z in reihe]
        wechsel = mitte.index(False)
        weite = [z["durchmesser"] for z in reihe]
        rel = [abs(b - a) / a for a, b in zip(weite, weite[1:])]
        self.assertLess(max(rel), 0.06, f"Kegelweite springt: {list(zip(self.TILTS, weite))}")
        self.assertTrue(_auf_der_buehne(reihe[wechsel]))
        self.assertTrue(reihe[wechsel]["kegelGeschnitten"])

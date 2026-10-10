"""VIZ-98: Bodenfleck und Gobo-Muster verschwinden, wenn der Strahl nichts trifft.

Befund (Projektinhaber 10.10., main a1ab2c71, Mega Arena, MH 1 mit Zebra-Gobo):
der Scheinwerfer leuchtete geradeaus bzw. nach oben, das Zebra-Muster lag aber
weiter am Boden. Gemessen am selben Geraet: Tilt 55 -> Strahlrichtung y = -0,23,
Fleck 22 m entfernt; Tilt 40/20 -> y = +0,05/+0,41, Fleck unveraendert SICHTBAR
am letzten Auftreffpunkt. ``applyFloorAim`` setzte ohne Treffer weder Position
noch Sichtbarkeit, und das Pool-Ziel (echtes Licht) blieb ebenfalls stehen.

Jetzt (ueber die ECHTE Seite, Produktiv-Push):

* kein Treffer -> Fleck/Muster unsichtbar, Pool-Ziel in Strahlrichtung;
* zurueckschwenken -> Fleck wieder da, am neuen Auftreffpunkt;
* auch mitten in der VIZ-92-Glaettung liegt in KEINEM Bild ein Fleck am Boden,
  waehrend der angezeigte Kopf ueber der Waagerechten steht;
* ein Settings-Wechsel schaltet ihn nicht wieder ein;
* steht ein Koerper im Weg (Decke/Wand), bleibt der Treffer dort sichtbar.

Kein WebGL noetig: gemessen wird der Szenenzustand.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

# Dieselbe Szenen-Basis wie VIZ-92 (Seite mit gputier=high, Produktiv-Push,
# stellbare Glaettungs-Uhr) — die Glaettung ist hier Teil der Pruefung.
from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _Basis, _FID, _TAKT, _geraet, _payload, _pump)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Lage des Strahls und des Bodenflecks. dirY: y-Anteil der Strahlrichtung
# (-1 = senkrecht nach unten), kopfY: Hoehe der Linse.
_LAGE_JS = """
(function(){
  const L = window.__lightos, f = L.fixtures['%d'];
  const o = f.head || f.group; o.updateMatrixWorld();
  const e = o.matrixWorld.elements;
  const n = Math.hypot(e[4], e[5], e[6]) || 1;
  const p = f.floorSpot.position, s = f.spotTarget.position;
  return JSON.stringify({
    dirY: -e[5] / n, kopfY: e[13],
    sichtbar: f.floorSpot.visible, fleck: [p.x, p.y, p.z], ziel: [s.x, s.y, s.z],
    muster: !!f.floorSpot.material.map, spot: f.spot ? f.spot.intensity : null,
  });
})()
"""

_UNTEN, _OBEN = 128, 20          # Tilt: senkrecht nach unten / deutlich nach oben


def _trifft_boden(z) -> bool:
    """Trifft der Strahl die Bodenebene in Reichweite (wie applyFloorAim)?"""
    if z["dirY"] >= -0.001:
        return False
    return 0 < (-z["kopfY"] / z["dirY"]) < 100


class Viz98BodenfleckTest(_Basis):
    # Tilt-Bereich 270 Grad wie der Moving Head aus dem Befund (Vorgabe der
    # Szene waeren 180 Grad — damit kaeme der Kopf nie ueber die Waagerechte).
    GERAETE = [_geraet(tiltRange=270)]

    def _lage(self):
        return json.loads(self._eval(_LAGE_JS % _FID))

    def _setze(self, **attrs):
        self._push(_payload(**attrs))
        self._bild()
        return self._lage()

    def test_strahl_nach_oben_blendet_den_fleck_aus_und_zurueck(self):
        self._load_and_wait()
        unten = self._setze(tilt=_UNTEN)
        self.assertLess(unten["dirY"], -0.9, unten)             # Vorbedingung
        self.assertTrue(unten["sichtbar"], unten)
        self.assertAlmostEqual(unten["fleck"][1], 0.01, places=3)

        oben = self._setze(tilt=_OBEN)
        self.assertGreater(oben["dirY"], 0.05, oben)            # Vorbedingung
        self.assertFalse(oben["sichtbar"],
                         f"Strahl zeigt nach oben, Fleck liegt noch am Boden: {oben}")
        # Das Pool-Ziel folgt dem Strahl: ueber der Linse, nicht am alten Fleck.
        self.assertGreater(oben["ziel"][1], oben["kopfY"], oben)

        zurueck = self._setze(tilt=_UNTEN)
        self.assertTrue(zurueck["sichtbar"], zurueck)
        self.assertEqual([round(v, 6) for v in zurueck["fleck"]],
                         [round(v, 6) for v in unten["fleck"]])
        self.assertEqual([round(v, 6) for v in zurueck["ziel"]],
                         [round(v, 6) for v in unten["ziel"]])

    def test_gobo_muster_verschwindet_mit_dem_fleck(self):
        self._load_and_wait()
        unten = self._setze(tilt=_UNTEN, gobo_wheel=75)         # Zebra
        self.assertTrue(unten["sichtbar"] and unten["muster"], unten)
        oben = self._setze(tilt=_OBEN, gobo_wheel=75)
        self.assertFalse(oben["sichtbar"], f"Zebra liegt noch am Boden: {oben}")
        zurueck = self._setze(tilt=_UNTEN, gobo_wheel=75)
        self.assertTrue(zurueck["sichtbar"] and zurueck["muster"], zurueck)

    def test_waagerecht_ohne_koerper_ist_auch_kein_treffer(self):
        self._load_and_wait()
        self._setze(tilt=_UNTEN)
        # Rund um die Waagerechte: was den Boden in Reichweite nicht trifft,
        # zeigt keinen Fleck — was ihn trifft, zeigt ihn.
        for tilt in (50, 46, 44, 43, 42, 41, 40, 36):
            z = self._setze(tilt=tilt)
            with self.subTest(tilt=tilt, dirY=round(z["dirY"], 3)):
                self.assertEqual(z["sichtbar"], _trifft_boden(z), z)

    def test_glaettung_kein_bild_mit_fleck_ueber_der_waagerechten(self):
        """Kleine Schritte im 30-Hz-Takt durch die Waagerechte: die Glaettung
        (VIZ-92) ruft applyFloorAim je Bild — in jedem Bild muss die
        Sichtbarkeit zum ANGEZEIGTEN Kopf passen, in beiden Richtungen."""
        self._load_and_wait()
        self._uhr(0)
        self._setze(tilt=52)
        tilts = list(range(52, 33, -1)) + list(range(34, 53))   # hoch und zurueck
        falsch, gesehen = [], set()
        for i, tilt in enumerate(tilts):
            t = (i + 1) * _TAKT
            self._uhr(t)
            self._push(_payload(tilt=tilt))
            for versatz in (_TAKT / 4, 3 * _TAKT / 4):
                self._bild(t + versatz)
                z = self._lage()
                gesehen.add(z["sichtbar"])
                if z["sichtbar"] != _trifft_boden(z):
                    falsch.append((tilt, round(z["dirY"], 4), z["sichtbar"]))
        self.assertEqual(falsch[:5], [], f"{len(falsch)} Bilder mit falschem Fleck")
        self.assertEqual(gesehen, {True, False}, "der Lauf muss beide Zustaende sehen")

    def test_settings_wechsel_schaltet_ihn_nicht_wieder_ein(self):
        self._load_and_wait()
        self._setze(tilt=_UNTEN)
        oben = self._setze(tilt=_OBEN)
        self.assertFalse(oben["sichtbar"], oben)
        self._bridge_obj.settingsChanged.emit(json.dumps({"showFloorSpots": True}))
        _pump(0.4)
        self.assertFalse(self._lage()["sichtbar"],
                         "Settings-Wechsel hat den Fleck eines Strahls ohne "
                         "Treffer wieder eingeschaltet")
        # ... und der Schalter selbst wirkt weiter, sobald der Strahl trifft.
        self._bridge_obj.settingsChanged.emit(json.dumps({"showFloorSpots": False}))
        _pump(0.4)
        self.assertFalse(self._setze(tilt=_UNTEN)["sichtbar"])
        self._bridge_obj.settingsChanged.emit(json.dumps({"showFloorSpots": True}))
        _pump(0.4)
        self.assertTrue(self._lage()["sichtbar"])

    def test_koerper_im_weg_bleibt_ein_treffer(self):
        """Zeigt der Strahl nach oben und trifft dort einen Buehnenkoerper
        (Decke, Wand, Traverse), gehoert der Fleck auf diesen Treffer."""
        self._load_and_wait()
        sid = self._eval("window.__lightos.addStageObject('platform')")
        self.assertTrue(sid)
        ok = self._eval("""(function(){
          const m = window.__lightos.stageObjects[%s].mesh;
          m.position.set(0, 9.5, 0); m.scale.set(60, 0.2, 60); m.updateMatrixWorld(true);
          return 1; })()""" % json.dumps(sid))
        self.assertEqual(ok, 1)
        oben = self._setze(tilt=_OBEN)
        self.assertGreater(oben["dirY"], 0.05, oben)
        self.assertTrue(oben["sichtbar"], f"Treffer an der Decke nicht gezeigt: {oben}")
        self.assertGreater(oben["fleck"][1], oben["kopfY"], oben)
        self.assertAlmostEqual(oben["ziel"][1], oben["fleck"][1] - 0.01, places=3)


class Viz98OhneZielrechnungTest(_Basis):
    """Codex-Befund zu #999: im 2D-Plan mit mehr als 50 Geraeten rechnet
    ``applyFloorAim`` keinen Auftreffpunkt (``skipBeam``) und kehrte zurueck,
    BEVOR der Merker „kein Auftreffpunkt" aktualisiert war. Zeigte der Kopf
    zuletzt nach oben, blieb sein Fleck dort dauerhaft aus — der 2D-Plan lebt
    aber gerade von den Flecken.

    Jetzt: ohne Zielrechnung zaehlt wie vor VIZ-98 nur die Helligkeit, und ein
    Wechsel 2D/3D ordnet den Fleck sofort neu ein (auch ohne DMX-Update)."""

    # 1 Moving Head + 51 PARs = 52 Geraete -> im 2D-Plan gilt „ohne Zielrechnung".
    GERAETE = [_geraet(tiltRange=270)] + [
        _geraet(_FID + 1 + i, "par", x=-10 + (i % 17) * 1.2, z=-4 + (i // 17) * 2.0)
        for i in range(51)]

    def _lage(self):
        return json.loads(self._eval(_LAGE_JS % _FID))

    def _setze(self, **attrs):
        self._push(_payload(**attrs))
        self._bild()
        return self._lage()

    def _modus(self, modus):
        self._bridge_obj.viewModeChanged.emit(modus)
        _pump(0.4)
        self.assertEqual(self._eval("window.__lightos.view.mode"), modus)

    def _ohne_zielrechnung(self):
        return self._eval("window.__lightos.view.mode === '2D' && "
                          "Object.keys(window.__lightos.fixtures).length > 50")

    def test_vorbedingung_52_geraete_und_die_regel_greift_nur_in_2d(self):
        self._load_and_wait()
        self.assertEqual(self._eval("Object.keys(window.__lightos.fixtures).length"), 52)
        self.assertFalse(self._ohne_zielrechnung())
        self._modus("2D")
        self.assertTrue(self._ohne_zielrechnung())

    def test_fleck_bleibt_im_2d_plan_nicht_dauerhaft_aus(self):
        """Der Fall aus dem Befund: Kopf zeigt in 3D nach oben (Fleck aus),
        dann 2D-Plan."""
        self._load_and_wait()
        self._setze(tilt=_UNTEN)
        oben = self._setze(tilt=_OBEN)
        self.assertFalse(oben["sichtbar"], oben)                # Vorbedingung: 3D, aus
        self._modus("2D")
        self.assertTrue(self._lage()["sichtbar"],
                        "nach dem Wechsel in den 2D-Plan bleibt der Fleck aus, "
                        "obwohl dort niemand rechnet, ob der Strahl trifft")
        # ... und er bleibt an, auch wenn weitere Updates kommen (Kopf weiter oben).
        for tilt in (_OBEN, _OBEN + 5, _OBEN):
            z = self._setze(tilt=tilt)
            self.assertTrue(z["sichtbar"], z)
        # Helligkeit schaltet ihn weiterhin.
        self.assertFalse(self._setze(tilt=_OBEN, intensity=0)["sichtbar"])
        self.assertTrue(self._setze(tilt=_OBEN, intensity=255)["sichtbar"])

    def test_update_im_2d_plan_setzt_einen_stehen_gebliebenen_merker_zurueck(self):
        """Nur der DMX-Weg, ohne die Hilfe des Moduswechsels: der Merker steht
        noch auf „kein Auftreffpunkt", das naechste Update im 2D-Plan muss ihn
        loesen."""
        self._load_and_wait()
        self._setze(tilt=_UNTEN)
        self._modus("2D")
        self._eval("(function(){ const f = window.__lightos.fixtures['%d'];"
                   " f._keinAuftreffer = true; f.floorSpot.visible = false; return 1; })()" % _FID)
        self.assertFalse(self._lage()["sichtbar"])
        self.assertTrue(self._setze(tilt=_OBEN)["sichtbar"],
                        "applyFloorAim kehrt bei skipBeam zurueck, ohne den Merker zu loesen")

    def test_zurueck_in_3d_entscheidet_wieder_der_auftreffpunkt(self):
        self._load_and_wait()
        self._setze(tilt=_UNTEN)
        self._modus("2D")
        oben = self._setze(tilt=_OBEN)
        self.assertTrue(oben["sichtbar"], oben)                 # 2D: nur Helligkeit
        self._modus("3D")
        z = self._lage()
        self.assertGreater(z["dirY"], 0.05, z)                  # Kopf zeigt nach oben
        self.assertFalse(z["sichtbar"],
                         f"zurueck in 3D liegt der Fleck noch am Boden: {z}")
        unten = self._setze(tilt=_UNTEN)
        self.assertTrue(unten["sichtbar"], unten)
        self.assertAlmostEqual(unten["fleck"][1], 0.01, places=3)

    def test_wenige_geraete_rechnen_auch_im_2d_plan(self):
        """Die Ausnahme gilt erst ab 51 Geraeten — darunter rechnet auch der
        2D-Plan den Auftreffpunkt, und der Fleck folgt ihm."""
        self.GERAETE = [_geraet(tiltRange=270)]
        self._load_and_wait()
        self._modus("2D")
        self.assertFalse(self._ohne_zielrechnung())
        self.assertTrue(self._setze(tilt=_UNTEN)["sichtbar"])
        self.assertFalse(self._setze(tilt=_OBEN)["sichtbar"])


if __name__ == "__main__":
    import unittest
    unittest.main()

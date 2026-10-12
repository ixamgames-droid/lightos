"""VIZ-103: ein haengender Moving Head sitzt an der WIRKLICHEN Unterkante der
Traverse — auch wenn seine Hoehe nicht vom Andocken stammt.

Befund (Windows-Test VIZ-100, echte App, Buehnen-Show 2026): 20 Moving Heads
haengen an 0,4 m dicken Traversen (Unterkante 8,30 m), ihr Geraete-Ursprung
liegt bei 8,10 m — 0,20 m unter der Unterkante. Frisch angedockt waeren es
0,25 m (``DOCK_HANG_OFFSET``). ``mount_pose`` legte die Oberkante des Modells
auf „Ursprung + 0,25“, nicht auf die Unterkante des Traegers: der Sockel ragte
5 cm in die Traverse. Fuer eine von Hand oder vom Show-Builder gesetzte Hoehe
stimmte „buendig“ also nicht.

Jetzt (ueber die ECHTE Seite):

* die Oberkante des Sockels liegt an der Unterkante der Traverse, egal ob der
  Ursprung 0,25 m, 0,20 m oder 0,10 m darunter liegt oder in der Traverse;
* die GESPEICHERTE Position bleibt, wo sie war;
* aendert sich die Traverse (dicker, hoeher) oder die Hoehe des Geraets,
  waehrend es angedockt ist, zieht die Haltung nach — ohne Ab- und Andocken;
* liegt der Ursprung weit von der Traverse weg (mehr als 0,5 m darunter oder
  ueber ihr), bleibt das Modell bei seiner gespeicherten Position: es wird
  nicht meterweit von dort weg gezeichnet;
* Strahlrichtung, Kegel und Bodenfleck gehen weiter vom haengenden Kopf aus.

Kein WebGL noetig: gemessen wird der Szenenzustand.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

from test_viz92_gobo_feinschliff_scene import (        # noqa: E402
    _geraet, _payload)
from test_viz100_haengend_andocken_scene import (      # noqa: E402
    _KOPF_UEBER_SOCKEL, _Viz100Basis)


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


# Die Traverse der Buehnen-Show: 0,4 m dick, Mitte 8,5 m.
_T_Y, _T_H = 8.5, 0.4
_UNTERKANTE = _T_Y - _T_H / 2          # 8,30
_DOCK_OFFSET = 0.25                    # DOCK_HANG_OFFSET
_NAH = 0.5                             # so weit unter der Unterkante zieht die Haltung nach

_TRAVERSE = {"id": "t1", "type": "truss_h", "name": "Mittel-Traverse",
             "position": {"x": 0, "y": _T_Y, "z": 0},
             "size": {"x": 24, "y": _T_H, "z": 0.4}, "rotation": 0,
             "color": "#888888"}

_FRISCH, _SHOW, _KNAPP, _KANTE, _INNEN, _RAND, _WEIT, _DRUEBER, _STEHT, _PIXEL = (
    931001, 931002, 931003, 931004, 931005, 931006, 931007, 931008, 931009, 931010)

# fid -> Abstand des Geraete-Ursprungs UNTER der Unterkante
_ABSTAND = {
    _FRISCH: _DOCK_OFFSET,     # so setzt es das Andocken
    _SHOW: 0.20,               # Buehnen-Show 2026
    _KNAPP: 0.10,
    _KANTE: 0.0,               # Ursprung genau auf der Unterkante
    _INNEN: -_T_H / 2,         # Ursprung in der Mitte der Traverse
    _RAND: _NAH,               # gerade noch nah
}


def _y(fid):
    return _UNTERKANTE - _ABSTAND[fid]


class _Basis103(_Viz100Basis):
    BUEHNE = [_TRAVERSE]

    def _pruefe_buendig(self, z, unterkante=_UNTERKANTE, ursprung=None):
        """Sockel oben an der Unterkante, nichts in der Traverse, Kopf darunter."""
        self.assertAlmostEqual(z["sockel"][1], unterkante, delta=0.003, msg=z)
        self.assertLessEqual(z["buegel"][1], unterkante + 0.001, z)
        self.assertLess(z["kopf"][1], z["sockel"][0], z)
        self.assertLess(z["linseY"], z["kopf"][1], z)
        self.assertLess(z["kopf"][1], unterkante - 0.2, z)
        if ursprung is not None:
            # Die gespeicherte Position hat sich nicht bewegt.
            self.assertAlmostEqual(z["gruppe"][1], ursprung, places=6, msg=z)


class Viz103UnterkanteTest(_Basis103):
    GERAETE = [_geraet(fid, x=-10 + 2 * i, y=_y(fid), dockedTo="t1", tiltRange=270)
               for i, fid in enumerate(_ABSTAND)] + [
        _geraet(_STEHT, x=6, y=_UNTERKANTE - 0.20, tiltRange=270),
        _geraet(_PIXEL, typ="pixel_head", x=8, y=_UNTERKANTE - 0.20, dockedTo="t1",
                nHeads=8, pixelBase=1),
    ]

    def test_frisch_angedockt_bleibt_buendig(self):
        """Gegenprobe: der Fall, den VIZ-100 gebaut hat, aendert sich nicht."""
        self._start()
        self._pruefe_buendig(self._lage(_FRISCH), ursprung=_y(_FRISCH))

    def test_hoehe_aus_der_buehnen_show_sockel_ragt_nicht_in_die_traverse(self):
        """Der Befund: Ursprung 0,20 m statt 0,25 m unter der Unterkante."""
        self._start()
        self._pruefe_buendig(self._lage(_SHOW), ursprung=_y(_SHOW))

    def test_jede_nahe_hoehe_ist_buendig(self):
        self._start()
        for fid in _ABSTAND:
            with self.subTest(abstand=_ABSTAND[fid]):
                self._pruefe_buendig(self._lage(fid), ursprung=_y(fid))

    def test_alle_haengen_gleich_hoch(self):
        """Gleiche Traverse -> gleiche Hoehe von Sockel und Kopf, egal wo der
        gespeicherte Ursprung liegt."""
        self._start()
        lagen = [self._lage(fid) for fid in _ABSTAND]
        for z in lagen[1:]:
            self.assertAlmostEqual(z["sockel"][1], lagen[0]["sockel"][1], places=4, msg=z)
            self.assertAlmostEqual(z["kopf"][1], lagen[0]["kopf"][1], places=4, msg=z)
            self.assertAlmostEqual(z["linseY"], lagen[0]["linseY"], places=4, msg=z)

    def test_pixel_kopf_ebenfalls(self):
        self._start()
        self._pruefe_buendig(self._lage(_PIXEL), ursprung=_UNTERKANTE - 0.20)

    def test_nicht_angedockt_steht_wie_bisher(self):
        self._start()
        z = self._lage(_STEHT)
        self.assertAlmostEqual(z["sockel"][0], z["gruppe"][1], delta=0.003, msg=z)
        self.assertAlmostEqual(z["kopf"][1], z["gruppe"][1] + _KOPF_UEBER_SOCKEL,
                               places=4, msg=z)

    def test_strahl_kegel_und_bodenfleck_vom_haengenden_kopf(self):
        self._start()
        self._uhr(0)
        for i, (pan, tilt) in enumerate(((128, 128), (60, 100), (200, 150))):
            self._uhr((i + 1) * 10000.0)
            self._push(_payload(_SHOW, pan=pan, tilt=tilt),
                       _payload(_STEHT, pan=pan, tilt=tilt))
            self._bild((i + 1) * 10000.0 + 5000.0)
            h, s = self._lage(_SHOW), self._lage(_STEHT)
            with self.subTest(pan=pan, tilt=tilt):
                self._pruefe_buendig(h, ursprung=_y(_SHOW))
                # Gleiche DMX-Werte -> gleiche Strahlrichtung wie stehend.
                for a, b in zip(h["dir"], s["dir"]):
                    self.assertAlmostEqual(a, b, places=6, msg=(h, s))
                # Der Kegel beginnt am haengenden Kopf.
                for a, b in zip(h["kegelSpitze"], h["kopf"]):
                    self.assertAlmostEqual(a, b, places=6, msg=h)
                self.assertLess(h["dir"][1], -0.05, h)          # Vorbedingung
                t = -h["kopf"][1] / h["dir"][1]
                self.assertTrue(h["fleckSichtbar"], h)
                self.assertAlmostEqual(h["fleck"][0], h["kopf"][0] + h["dir"][0] * t,
                                       places=4, msg=h)
                self.assertAlmostEqual(h["fleck"][2], h["kopf"][2] + h["dir"][2] * t,
                                       places=4, msg=h)

    def test_abdocken_stellt_auf_die_gespeicherte_hoehe(self):
        self._start()
        self._pruefe_buendig(self._lage(_SHOW))
        self._emit_until_true(
            lambda: self._bridge_obj.applyFixtureTransform.emit(json.dumps(
                {"fid": _SHOW, "x": None, "y": None, "z": None, "dock": ""})),
            "!window.__lightos.fixtures['%d'].dockedTo" % _SHOW)
        self._bild()
        z = self._lage(_SHOW)
        self.assertAlmostEqual(z["gruppe"][1], _y(_SHOW), places=6, msg=z)
        self.assertAlmostEqual(z["sockel"][0], _y(_SHOW), delta=0.003, msg=z)
        self.assertAlmostEqual(z["kopf"][1], _y(_SHOW) + _KOPF_UEBER_SOCKEL, places=4, msg=z)


class Viz103NachziehenTest(_Basis103):
    """Traverse oder Geraetehoehe aendern sich, WAEHREND das Geraet haengt."""
    GERAETE = [_geraet(_SHOW, x=0, y=_y(_SHOW), dockedTo="t1", tiltRange=270)]

    def test_dickere_traverse_zieht_die_haltung_nach(self):
        self._start()
        self._pruefe_buendig(self._lage(_SHOW), ursprung=_y(_SHOW))
        # Dieselbe Mitte, 0,6 m dick: Unterkante 8,20 — der Ursprung (8,10)
        # liegt jetzt nur noch 0,10 m darunter.
        dick = dict(_TRAVERSE, size={"x": 24, "y": 0.6, "z": 0.4})
        self._buehne([dick])
        self._pruefe_buendig(self._lage(_SHOW), unterkante=_T_Y - 0.3, ursprung=_y(_SHOW))
        # … und wieder zurueck.
        self._buehne([_TRAVERSE])
        self._pruefe_buendig(self._lage(_SHOW), ursprung=_y(_SHOW))

    def test_hoehere_traverse_zieht_die_haltung_nach(self):
        self._start()
        hoeher = dict(_TRAVERSE, position={"x": 0, "y": _T_Y + 0.2, "z": 0})
        self._buehne([hoeher])
        self._pruefe_buendig(self._lage(_SHOW), unterkante=_UNTERKANTE + 0.2,
                             ursprung=_y(_SHOW))

    def test_geaenderte_geraetehoehe_zieht_die_haltung_nach(self):
        """Hoehe von Hand geaendert (Eigenschaften), Bindung bleibt."""
        self._start()
        neu = _UNTERKANTE - 0.35
        self._emit_until_true(
            lambda: self._bridge_obj.applyFixtureTransform.emit(json.dumps(
                {"fid": _SHOW, "x": None, "y": neu, "z": None, "dock": "t1"})),
            "Math.abs(window.__lightos.fixtures['%d'].group.position.y - %r) < 1e-6"
            % (_SHOW, neu))
        self._bild()
        self._pruefe_buendig(self._lage(_SHOW), ursprung=neu)

    def test_bodenfleck_folgt_der_nachgezogenen_haltung(self):
        """Nach dem Nachziehen geht der Strahl vom NEUEN Kopf aus."""
        self._start()
        self._push(_payload(_SHOW, pan=60, tilt=100))
        self._bild()
        hoeher = dict(_TRAVERSE, position={"x": 0, "y": _T_Y + 0.2, "z": 0})
        self._buehne([hoeher])
        self._bild()
        h = self._lage(_SHOW)
        self.assertLess(h["dir"][1], -0.05, h)
        t = -h["kopf"][1] / h["dir"][1]
        self.assertAlmostEqual(h["fleck"][0], h["kopf"][0] + h["dir"][0] * t, places=4, msg=h)
        self.assertAlmostEqual(h["fleck"][2], h["kopf"][2] + h["dir"][2] * t, places=4, msg=h)
        for a, b in zip(h["kegelSpitze"], h["kopf"]):
            self.assertAlmostEqual(a, b, places=6, msg=h)


class Viz103WeitWegTest(_Basis103):
    """Ursprung weit von der Traverse entfernt: das Modell bleibt bei seiner
    gespeicherten Position (fester Abstand wie bisher), statt meterweit
    davon entfernt gezeichnet zu werden."""
    GERAETE = [
        _geraet(_WEIT, x=-2, y=_UNTERKANTE - 1.5, dockedTo="t1", tiltRange=270),
        _geraet(_DRUEBER, x=2, y=_T_Y + _T_H / 2 + 0.3, dockedTo="t1", tiltRange=270),
    ]

    def test_weit_darunter_bleibt_bei_der_gespeicherten_position(self):
        self._start()
        z = self._lage(_WEIT)
        ursprung = _UNTERKANTE - 1.5
        self.assertAlmostEqual(z["gruppe"][1], ursprung, places=6, msg=z)
        # Haengend gezeichnet, Oberkante im festen Abstand ueber dem Ursprung.
        self.assertAlmostEqual(z["sockel"][1], ursprung + _DOCK_OFFSET, delta=0.003, msg=z)
        self.assertLess(z["kopf"][1], z["sockel"][0], z)

    def test_ueber_der_traverse_bleibt_bei_der_gespeicherten_position(self):
        self._start()
        z = self._lage(_DRUEBER)
        ursprung = _T_Y + _T_H / 2 + 0.3
        self.assertAlmostEqual(z["gruppe"][1], ursprung, places=6, msg=z)
        self.assertAlmostEqual(z["sockel"][1], ursprung + _DOCK_OFFSET, delta=0.003, msg=z)

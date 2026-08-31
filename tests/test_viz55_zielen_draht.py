"""VIZ-55: „⌖ Zielen" trifft am ECHTEN Rig — Modell-Wert vs. Draht-Wert.

Gemessen an Davids Aufbau vom 26.08.2026 (zwei Varytec Hero Spot 90, stehend,
``invert_pan=True``, Nullpunkte 167,5/141, Bereiche 330/260).

Die Kette hat drei Glieder, und bis zum 2026-08-30 war das mittlere doppelt
belegt:

    aim_pan_tilt  ->  Programmer  ->  Ausgabestufe  ->  Draht  ->  echter Kopf
                                     (apply_pan_tilt_orientation)

``aim_pan_tilt`` wendete ``invert_pan`` SELBST an und schrieb das Ergebnis in
den Programmer; die Ausgabestufe drehte es danach ein zweites Mal. Der Strahl
verfehlte die Wand dadurch nicht knapp, sondern zeigte nach HINTEN.

Die Tests messen am Auftreffpunkt an der Wand, nicht am DMX-Wert: eine
Zusicherung auf eine Zahl hätte die Doppel-Anwendung mitgeschrieben statt sie
zu finden.
"""
import math
import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import (AppState, apply_pan_tilt_orientation,
                                unapply_pan_tilt_orientation)
from src.core.dmx.universe import Universe
from src.core.stage.aim import _mount_matrix, aim_pan_tilt, trace_pan_tilt

# ── Davids Rig, eingemessen 26.08.2026 (tools/build_spot90_testshow.py) ──────
PAN_RANGE, TILT_RANGE = 330.0, 260.0
PAN_ZERO, TILT_ZERO = 167.5, 141.0
POS = (0.32, 0.43, 0.0)          # fid 1, Linsenmitte
ROT = (180.0, 0.0, 0.0)          # STEHEND, nicht haengend
WAND_Z = 2.50
ZIEL = (0.0, 1.10, WAND_Z)       # „Wand Mitte" — der live eingemessene Punkt

AIM_KW = dict(pan_range_deg=PAN_RANGE, tilt_range_deg=TILT_RANGE,
              pan_zero_dmx=PAN_ZERO, tilt_zero_dmx=TILT_ZERO)


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.highlight_value = 255
        self.ranges = []


MH_CHANS = [_Ch("pan", 1), _Ch("tilt", 2)]


def _fixture(**flags):
    return SimpleNamespace(
        fid=1, universe=1, address=1,
        invert_pan=flags.get("invert_pan", False),
        invert_tilt=flags.get("invert_tilt", False),
        swap_pan_tilt=flags.get("swap_pan_tilt", False),
    )


def _draht(fx, programmer):
    """Was landet auf dem Draht? Fährt den ECHTEN Render-Pfad, nicht eine
    Nachbildung — ``_apply_fixture_map`` ist dieselbe Funktion, die Programmer
    und Cues in die Universen schreibt."""
    st = AppState.__new__(AppState)
    st._fix_index = {fx.fid: (fx, MH_CHANS)}
    uni = Universe(1)
    st._apply_fixture_map({1: uni}, {fx.fid: dict(programmer)})
    return uni.get_channel(1), uni.get_channel(2)


def _physische_richtung(fx, pan_draht, tilt_draht):
    """Wohin zeigt der ECHTE Kopf bei diesem Draht-Wert?

    Ein Gerät mit ``invert_pan`` fährt den Draht-Wert spiegelverkehrt — genau
    deshalb dreht die Ausgabestufe ihn. Hier wird das Gerät nachgebildet: erst
    die Geräte-Spiegelung zurücknehmen, dann die Winkelformel des Modells.

    ★ Bewusst von Hand ausgeschrieben statt ``unapply_pan_tilt_orientation``
    aufzurufen — sonst prüfte der Test die Funktion gegen sich selbst. Die
    Reihenfolge ist die Umkehrung von ``apply_pan_tilt_orientation`` (dort erst
    Swap, dann Invert), also hier erst INVERT, dann SWAP. Die naheliegende
    spiegelbildliche Reihenfolge ist falsch, und sie stand hier auch zuerst:
    aufgefallen ist es nur, weil ``test_bild_und_rig_zeigen_dieselbe_richtung``
    rot wurde.
    """
    p, t = pan_draht, tilt_draht
    if fx.invert_pan:
        p = 255 - p
    if fx.invert_tilt:
        t = 255 - t
    if fx.swap_pan_tilt:
        p, t = t, p
    pan_rad = math.radians((p - PAN_ZERO) / 128.0 * (PAN_RANGE / 2.0))
    tilt_rad = math.radians((t - TILT_ZERO) / 128.0 * (TILT_RANGE / 2.0))
    d = (-math.sin(tilt_rad) * math.sin(pan_rad),
         -math.cos(tilt_rad),
         -math.sin(tilt_rad) * math.cos(pan_rad))
    R = _mount_matrix(*ROT)
    return tuple(sum(R[i][j] * d[j] for j in range(3)) for i in range(3))


def _auftreffpunkt(richtung, pos=POS, wand_z=WAND_Z):
    """Wo trifft der Strahl die Wand bei z = ``wand_z``? ``None`` = trifft sie
    gar nicht (zeigt weg von ihr)."""
    if abs(richtung[2]) < 1e-9:
        return None
    s = (wand_z - pos[2]) / richtung[2]
    if s <= 0:
        return None
    return (pos[0] + s * richtung[0], pos[1] + s * richtung[1])


class ZielenTrifftAmRigTest(unittest.TestCase):
    """Der eigentliche Nachweis: gemessen am Auftreffpunkt, nicht am DMX-Wert."""

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: MH_CHANS

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _treffer(self, fx, ziel=ZIEL):
        pan, tilt = aim_pan_tilt(POS, ziel, ROT, **AIM_KW)
        return _auftreffpunkt(_physische_richtung(fx, *_draht(
            fx, {"pan": pan, "tilt": tilt})))

    def test_invertiertes_geraet_trifft_den_punkt(self):
        """Hero Spot 90 (invert_pan): der Strahl muss an der Wand ankommen.

        Vor dem Fix traf er sie überhaupt nicht — ``_auftreffpunkt`` lieferte
        ``None``, weil der Strahl nach hinten zeigte.
        """
        fx = _fixture(invert_pan=True)
        treffer = self._treffer(fx)
        self.assertIsNotNone(
            treffer, "Strahl trifft die Wand nicht (zeigt weg) — Doppel-Drehung?")
        abstand = math.dist(treffer, ZIEL[:2])
        self.assertLess(abstand, 0.05,
                        f"Strahl verfehlt das Ziel um {abstand:.2f} m")

    def test_alle_vier_ziele_der_testshow(self):
        """Nicht nur der eingemessene Punkt: auch die drei nie angefahrenen.

        Ein Versatz, der nur EINEN Punkt trifft, käme hier durch — vier Punkte
        in verschiedene Richtungen tun es nicht.
        """
        fx = _fixture(invert_pan=True)
        for name, ziel in (("Wand Mitte", (0.0, 1.10, WAND_Z)),
                           ("Wand hoch", (0.0, 1.85, WAND_Z)),
                           ("Wand links", (-1.50, 1.10, WAND_Z)),
                           ("Wand rechts", (1.50, 1.10, WAND_Z))):
            with self.subTest(ziel=name):
                treffer = self._treffer(fx, ziel)
                self.assertIsNotNone(treffer, f"{name}: Wand nicht getroffen")
                abstand = math.dist(treffer, ziel[:2])
                self.assertLess(abstand, 0.06,
                                f"{name}: verfehlt um {abstand:.2f} m")

    def test_geraet_ohne_flags_unveraendert(self):
        """Positivkontrolle: ohne Flags war nie etwas kaputt und bleibt es.

        Programmer-Wert und Draht-Wert sind identisch, und der Strahl trifft.
        """
        fx = _fixture()
        pan, tilt = aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW)
        self.assertEqual(_draht(fx, {"pan": pan, "tilt": tilt}), (pan, tilt))
        treffer = self._treffer(fx)
        self.assertIsNotNone(treffer)
        self.assertLess(math.dist(treffer, ZIEL[:2]), 0.05)

    def test_swap_und_invert_zusammen(self):
        """Die unbequeme Kombination — Swap UND Invert, in beiden Achsen."""
        fx = _fixture(invert_pan=True, invert_tilt=True, swap_pan_tilt=True)
        treffer = self._treffer(fx)
        self.assertIsNotNone(treffer, "Wand nicht getroffen (swap+invert)")
        self.assertLess(math.dist(treffer, ZIEL[:2]), 0.05)

    def test_programmer_traegt_modellwert(self):
        """Der Programmer-Wert hängt NICHT an den Geräte-Flags.

        Genau das war die Doppel-Anwendung: derselbe Zielpunkt ergab je nach
        Flag verschiedene Programmer-Werte, obwohl die Geometrie dieselbe ist.
        """
        modell = aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW)
        for flags in ({}, {"invert_pan": True}, {"invert_tilt": True},
                      {"swap_pan_tilt": True},
                      {"invert_pan": True, "swap_pan_tilt": True}):
            with self.subTest(**flags):
                # aim_pan_tilt kennt die Flags gar nicht mehr -> gleicher Wert.
                self.assertEqual(aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW), modell)

    def test_nachfahren_liefert_ebenfalls_modellwerte(self):
        """``trace_pan_tilt`` (Formen-Nachfahren) teilt die Konvention."""
        punkte = [(0.0, 1.10, WAND_Z), (0.5, 1.10, WAND_Z)]
        folge = trace_pan_tilt(POS, punkte, ROT, **AIM_KW)
        einzeln = [aim_pan_tilt(POS, p, ROT, **AIM_KW) for p in punkte]
        self.assertEqual(folge, einzeln)


class BridgeSchreibtModellwertTest(unittest.TestCase):
    """Die AUFRUFSTELLE, nicht nur die Geometrie.

    ``ZielenTrifftAmRigTest`` prüft die Komposition aim -> Ausgabestufe. Ob der
    Bridge-Handler die Geräte-Flags wieder mitgibt, sähe man dort NICHT — genau
    dort standen sie aber. Deshalb hier der echte Handler (ungebunden mit
    Fake-self, wie in ``tests/test_visualizer_aim.py``).
    """

    def _programmer_werte(self, fx):
        import json
        from unittest.mock import MagicMock
        import src.ui.visualizer.visualizer_window as VW

        st = SimpleNamespace(
            get_patched_fixtures=lambda: [fx],
            visualizer_positions={fx.fid: POS},
            visualizer_rotations={fx.fid: ROT},
            set_programmer_value=MagicMock(),
        )
        fake = SimpleNamespace(
            _state=st,
            _is_moving_head=lambda f: True,
            push_apply_fixture_transform=MagicMock(),
            pyFixtureRotated=MagicMock(),
            pyAimApplied=MagicMock(),
        )
        VW.VisualizerBridge.aimFixturesAt(fake, json.dumps(
            {"x": ZIEL[0], "y": ZIEL[1], "z": ZIEL[2], "fids": [fx.fid]}))
        werte = {}
        for call in st.set_programmer_value.call_args_list:
            werte[call.args[1]] = call.args[2]
        return werte

    def _mh(self, **flags):
        fx = _fixture(**flags)
        fx.pan_range_deg = PAN_RANGE
        fx.tilt_range_deg = TILT_RANGE
        fx.pan_zero_dmx = PAN_ZERO
        fx.tilt_zero_dmx = TILT_ZERO
        return fx

    def test_flags_aendern_den_programmer_wert_nicht(self):
        """Derselbe Zielpunkt -> derselbe Programmer-Wert, egal welche Flag.

        Vor dem Fix war genau das verletzt: der Handler reichte die Flags an
        ``aim_pan_tilt`` weiter, und der Programmer trug bereits gedrehte Werte.
        """
        erwartet = aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW)
        for flags in ({}, {"invert_pan": True}, {"invert_tilt": True},
                      {"swap_pan_tilt": True},
                      {"invert_pan": True, "swap_pan_tilt": True}):
            with self.subTest(**flags):
                werte = self._programmer_werte(self._mh(**flags))
                self.assertEqual((werte["pan"], werte["tilt"]), erwartet)

    def test_strahl_trifft_ueber_die_ganze_kette(self):
        """Bridge -> Programmer -> Ausgabestufe -> echter Kopf -> Wand."""
        fx = self._mh(invert_pan=True)
        werte = self._programmer_werte(fx)
        orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda f: MH_CHANS
        try:
            draht = _draht(fx, {"pan": werte["pan"], "tilt": werte["tilt"]})
        finally:
            A.get_channels_for_patched = orig
        treffer = _auftreffpunkt(_physische_richtung(fx, *draht))
        self.assertIsNotNone(treffer, "Wand nicht getroffen")
        self.assertLess(math.dist(treffer, ZIEL[:2]), 0.05)


class UnapplyOrientationTest(unittest.TestCase):
    """``unapply_pan_tilt_orientation`` ist die exakte Umkehrung — auch dort,
    wo die naive Lösung (zweimal vorwärts) falsch liegt."""

    ALLE_FLAGS = [
        {}, {"invert_pan": True}, {"invert_tilt": True}, {"swap_pan_tilt": True},
        {"invert_pan": True, "invert_tilt": True},
        {"invert_pan": True, "swap_pan_tilt": True},
        {"invert_tilt": True, "swap_pan_tilt": True},
        {"invert_pan": True, "invert_tilt": True, "swap_pan_tilt": True},
    ]

    def test_rundreise_ist_identitaet(self):
        werte = {"pan": 37, "tilt": 201}
        for flags in self.ALLE_FLAGS:
            with self.subTest(**flags):
                fx = _fixture(**flags)
                draht = apply_pan_tilt_orientation(fx, werte)
                self.assertEqual(unapply_pan_tilt_orientation(fx, draht), werte)

    def test_rundreise_mit_feinkanaelen(self):
        """16 Bit: Grob und Fein werden als PAAR gedreht, nicht einzeln."""
        werte = {"pan": 37, "pan_fine": 200, "tilt": 201, "tilt_fine": 9}
        for flags in self.ALLE_FLAGS:
            with self.subTest(**flags):
                fx = _fixture(**flags)
                draht = apply_pan_tilt_orientation(fx, werte)
                self.assertEqual(unapply_pan_tilt_orientation(fx, draht), werte)

    def test_zweimal_vorwaerts_reicht_nicht(self):
        """Warum es die Umkehrfunktion überhaupt gibt.

        Invert und Swap sind je für sich Involutionen — ihre Komposition ist es
        NICHT. Wer die Vorwärtsfunktion zweimal anwendet, bekommt bei
        gleichzeitig gesetztem Swap und Invert das Falsche. Ohne diesen Test
        wäre die naheliegende Abkürzung nicht als Fehler erkennbar.
        """
        fx = _fixture(invert_pan=True, swap_pan_tilt=True)
        werte = {"pan": 37, "tilt": 201}
        draht = apply_pan_tilt_orientation(fx, werte)
        self.assertNotEqual(apply_pan_tilt_orientation(fx, draht), werte)
        self.assertEqual(unapply_pan_tilt_orientation(fx, draht), werte)

    def test_ohne_flags_dasselbe_objekt(self):
        """Kein Overhead im 3D-Takt: ohne Flag kommt das Original zurück."""
        fx = _fixture()
        werte = {"pan": 5, "tilt": 6}
        self.assertIs(unapply_pan_tilt_orientation(fx, werte), werte)

    def test_ohne_pan_tilt_dasselbe_objekt(self):
        fx = _fixture(invert_pan=True)
        werte = {"intensity": 200}
        self.assertIs(unapply_pan_tilt_orientation(fx, werte), werte)

    def test_kaputter_wert_stoppt_nicht(self):
        """Defensiv wie die Vorwärtsrichtung: ein None aus OSC/Web/MIDI darf
        den Visualizer-Takt nicht anhalten."""
        fx = _fixture(invert_pan=True)
        out = unapply_pan_tilt_orientation(fx, {"pan": None, "tilt": 10})
        self.assertNotIn("pan", out)
        self.assertEqual(out["tilt"], 10)


class Viz3dZeigtDenEchtenKopfTest(unittest.TestCase):
    """Das 3D-Bild muss zeigen, wohin der PHYSISCHE Kopf zeigt.

    Der Visualizer speist sich aus dem gesendeten DMX-Frame, seine Winkelformel
    (``builders.js::applyPanTilt``) kennt invert/swap aber nicht — ohne
    Rücknahme stand der Strahl im Bild gespiegelt. Das betraf JEDE Quelle
    (Fader, EFX, Cue), nicht nur das Zielen.
    """

    def test_payload_traegt_modellwert(self):
        from src.ui.visualizer.visualizer_service import _build_fixture_payload

        fx = _fixture(invert_pan=True)
        modell = {"pan": 37, "tilt": 201}
        draht = apply_pan_tilt_orientation(fx, modell)
        self.assertNotEqual(draht["pan"], modell["pan"])   # Vorbedingung
        payload = _build_fixture_payload(fx, dict(draht))
        self.assertEqual(payload["pan"], modell["pan"])
        self.assertEqual(payload["tilt"], modell["tilt"])

    def test_payload_ohne_flags_unveraendert(self):
        """Positivkontrolle: ohne Flag zeigt der Payload den Draht-Wert."""
        from src.ui.visualizer.visualizer_service import _build_fixture_payload

        fx = _fixture()
        payload = _build_fixture_payload(fx, {"pan": 37, "tilt": 201})
        self.assertEqual(payload["pan"], 37)
        self.assertEqual(payload["tilt"], 201)

    def test_bild_und_rig_zeigen_dieselbe_richtung(self):
        """Der Vergleich, um den es geht: Bild-Richtung == Kopf-Richtung."""
        from src.ui.visualizer.visualizer_service import _build_fixture_payload

        fx = _fixture(invert_pan=True, swap_pan_tilt=True)
        pan, tilt = aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW)
        draht = apply_pan_tilt_orientation(fx, {"pan": pan, "tilt": tilt})
        payload = _build_fixture_payload(fx, dict(draht))
        # Bild: die JS-Formel rechnet direkt mit dem Payload-Wert.
        bild = _physische_richtung(_fixture(), payload["pan"], payload["tilt"])
        # Rig: das echte Geraet dreht den Draht-Wert selbst zurueck.
        rig = _physische_richtung(fx, draht["pan"], draht["tilt"])
        for a, b in zip(bild, rig):
            self.assertAlmostEqual(a, b, places=9)


if __name__ == "__main__":
    unittest.main()

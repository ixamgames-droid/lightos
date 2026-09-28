"""VIZ-61: „⌖ Zielen" rechnet mit Feinkanal in 16 Bit — und das 3D zeigt es.

Befund (beim Bau von VIZ-55 Slice 1, 2026-08-30): ``aim_pan_tilt`` gab ganze
DMX-Werte zurueck, und ``aimFixturesAt`` setzte ``pan_fine``/``tilt_fine``
ausdruecklich auf 0 (der Mover-Bar-Zweig fasste sie gar nicht an — zwei
Verhalten im selben Handler). Ein DMX-Schritt sind bei 540 Grad Pan 2,11 Grad,
auf 5 m Wurf 18,4 cm. Zweite Haelfte: der 3D-Payload trug nur den Grobwert, eine
reine Feinkorrektur waere am Geraet sichtbar und im Bild unsichtbar gewesen.

Abnahme (BACKLOG): ein Zielpunkt wird mit Feinkanal genauer getroffen als ohne —
**gemessen am Auftreffpunkt, nicht am DMX-Wert**; ein Geraet OHNE Feinkanaele
verhaelt sich unveraendert (Positivkontrolle); das 3D zeigt die feine Stellung.

Die Geometrie ist Robins Aufbau vom 26.08.2026 (Hero Spot 90, stehend,
``invert_pan``) — dieselbe wie in ``test_viz55_zielen_draht.py``.
"""
import json
import math
import os
import random
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.stage.aim import _mount_matrix, aim_pan_tilt, aim_pan_tilt_16

PAN_RANGE, TILT_RANGE = 330.0, 260.0
PAN_ZERO, TILT_ZERO = 167.5, 141.0
POS = (0.32, 0.43, 0.0)
ROT = (180.0, 0.0, 0.0)
WAND_Z = 2.50
ZIEL = (0.0, 1.10, WAND_Z)
AIM_KW = dict(pan_range_deg=PAN_RANGE, tilt_range_deg=TILT_RANGE,
              pan_zero_dmx=PAN_ZERO, tilt_zero_dmx=TILT_ZERO)


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.highlight_value = 255
        self.ranges = []


GROB = [_Ch("pan", 1), _Ch("tilt", 2)]
FEIN = [_Ch("pan", 1), _Ch("pan_fine", 2), _Ch("tilt", 3), _Ch("tilt_fine", 4)]
NUR_PAN_FEIN = [_Ch("pan", 1), _Ch("pan_fine", 2), _Ch("tilt", 3)]


def _fx(invert_pan=True, **extra):
    fx = SimpleNamespace(fid=1, universe=1, address=1, invert_pan=invert_pan,
                         invert_tilt=False, swap_pan_tilt=False,
                         pan_range_deg=PAN_RANGE, tilt_range_deg=TILT_RANGE,
                         pan_zero_dmx=PAN_ZERO, tilt_zero_dmx=TILT_ZERO)
    for k, v in extra.items():
        setattr(fx, k, v)
    return fx


def _draht(fx, chans, programmer):
    """Echter Render-Pfad (``_apply_fixture_map``), wie in test_viz55."""
    st = AppState.__new__(AppState)
    st._fix_index = {fx.fid: (fx, chans)}
    uni = Universe(1)
    st._apply_fixture_map({1: uni}, {fx.fid: dict(programmer)})
    return {c.attribute: uni.get_channel(c.channel_number) for c in chans}


def _auftreffpunkt(fx, draht):
    """Wohin zeigt der ECHTE Kopf? Von Hand ausgeschrieben (nicht ueber
    ``unapply_pan_tilt_orientation``), sonst pruefte der Test die Funktion gegen
    sich selbst. Grob/Fein als 16-Bit-Paar; ein Geraet mit ``invert_pan`` faehrt
    den 16-Bit-Wert gespiegelt (65535 - v)."""
    def wert(achse):
        v = draht[achse] * 256 + draht.get(f"{achse}_fine", 0)
        if getattr(fx, f"invert_{achse}"):
            v = 65535 - v
        return v / 256.0
    p, t = wert("pan"), wert("tilt")
    pan_rad = math.radians((p - PAN_ZERO) / 128.0 * (PAN_RANGE / 2.0))
    tilt_rad = math.radians((t - TILT_ZERO) / 128.0 * (TILT_RANGE / 2.0))
    d = (-math.sin(tilt_rad) * math.sin(pan_rad), -math.cos(tilt_rad),
         -math.sin(tilt_rad) * math.cos(pan_rad))
    R = _mount_matrix(*ROT)
    r = tuple(sum(R[i][j] * d[j] for j in range(3)) for i in range(3))
    if r[2] <= 1e-9:
        return None
    s = (WAND_Z - POS[2]) / r[2]
    return (POS[0] + s * r[0], POS[1] + s * r[1])


def _handler(fx, chans):
    """Der ECHTE Bridge-Handler (ungebunden mit Fake-self, wie in test_viz55)."""
    import src.ui.visualizer.visualizer_window as VW
    st = SimpleNamespace(get_patched_fixtures=lambda: [fx],
                         visualizer_positions={fx.fid: POS},
                         visualizer_rotations={fx.fid: ROT},
                         set_programmer_value=MagicMock())
    fake = SimpleNamespace(_state=st, _is_moving_head=lambda f: True,
                           push_apply_fixture_transform=MagicMock(),
                           pyFixtureRotated=MagicMock(), pyAimApplied=MagicMock())
    orig = VW.get_channels_for_patched
    VW.get_channels_for_patched = lambda f: chans
    try:
        VW.VisualizerBridge.aimFixturesAt(fake, json.dumps(
            {"x": ZIEL[0], "y": ZIEL[1], "z": ZIEL[2], "fids": [fx.fid]}))
    finally:
        VW.get_channels_for_patched = orig
    return st.set_programmer_value.call_args_list


def _werte(calls):
    return {c.args[1]: c.args[2] for c in calls}


class ZielgenauigkeitTest(unittest.TestCase):
    """Der eigentliche Nachweis — am Auftreffpunkt an der Wand."""

    def _fehler(self, fx, chans, ziel, fein):
        if fein:
            p16, t16 = aim_pan_tilt_16(POS, ziel, ROT, **AIM_KW)
            prog = {"pan": p16 >> 8, "pan_fine": p16 & 255,
                    "tilt": t16 >> 8, "tilt_fine": t16 & 255}
        else:
            p, t = aim_pan_tilt(POS, ziel, ROT, **AIM_KW)
            prog = {"pan": p, "tilt": t}
        treffer = _auftreffpunkt(fx, _draht(fx, chans, prog))
        self.assertIsNotNone(treffer, "Wand verfehlt")
        return math.dist(treffer, ziel[:2])

    def test_feinkanal_trifft_genauer_als_grob(self):
        """200 Zielpunkte auf der Wand, invertiertes Geraet (Robins Rig)."""
        rnd = random.Random(61)
        fx = _fx()
        grob, fein = [], []
        for _ in range(200):
            ziel = (rnd.uniform(-1.2, 1.2), rnd.uniform(0.3, 2.2), WAND_Z)
            grob.append(self._fehler(fx, GROB, ziel, fein=False))
            fein.append(self._fehler(fx, FEIN, ziel, fein=True))
        # 8 Bit: Rundung bis ~1 cm auf 2,5 m Wurf; 16 Bit: 256-mal feiner.
        self.assertGreater(max(grob), 0.004)                 # die Koernung ist real
        self.assertLess(max(fein), 0.0005)                   # < 0,5 mm
        self.assertLess(sum(fein) / len(fein), sum(grob) / len(grob) / 50)

    def test_auch_ohne_invert(self):
        fx = _fx(invert_pan=False)
        self.assertLess(self._fehler(fx, FEIN, ZIEL, fein=True), 0.0005)


class HandlerSchreibtFeinkanalTest(unittest.TestCase):

    def test_geraet_mit_feinkanal_bekommt_16_bit(self):
        w = _werte(_handler(_fx(), FEIN))
        p16, t16 = aim_pan_tilt_16(POS, ZIEL, ROT, **AIM_KW)
        self.assertEqual((w["pan"], w["pan_fine"]), (p16 >> 8, p16 & 255))
        self.assertEqual((w["tilt"], w["tilt_fine"]), (t16 >> 8, t16 & 255))
        self.assertNotEqual((w["pan_fine"], w["tilt_fine"]), (0, 0))

    def test_ueber_die_ganze_kette_an_der_wand(self):
        """Handler -> Programmer -> Ausgabestufe (invert) -> Kopf -> Wand."""
        fx = _fx()
        w = _werte(_handler(fx, FEIN))
        treffer = _auftreffpunkt(fx, _draht(fx, FEIN, w))
        self.assertLess(math.dist(treffer, ZIEL[:2]), 0.0005)

    def test_positivkontrolle_ohne_feinkanal_unveraendert(self):
        """Byte-genau wie vor VIZ-61: gerundeter 8-Bit-Wert, Fein 0."""
        w = _werte(_handler(_fx(), GROB))
        self.assertEqual((w["pan"], w["tilt"]), aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW))
        self.assertEqual((w["pan_fine"], w["tilt_fine"]), (0, 0))

    def test_achsen_einzeln(self):
        """Nur Pan hat einen Feinkanal: Tilt bleibt 8 Bit."""
        w = _werte(_handler(_fx(), NUR_PAN_FEIN))
        p16, _ = aim_pan_tilt_16(POS, ZIEL, ROT, **AIM_KW)
        self.assertEqual((w["pan"], w["pan_fine"]), (p16 >> 8, p16 & 255))
        self.assertEqual(w["tilt"], aim_pan_tilt(POS, ZIEL, ROT, **AIM_KW)[1])
        self.assertEqual(w["tilt_fine"], 0)

    def test_mover_bar_bekommt_feinkanal_je_kopf(self):
        """Der Bar-Zweig fasste die Feinkanaele bisher gar nicht an."""
        import src.ui.visualizer.visualizer_window as VW
        bar = [_Ch("pan", 1), _Ch("pan_fine", 2), _Ch("tilt", 3), _Ch("tilt_fine", 4),
               _Ch("pan", 5), _Ch("pan_fine", 6), _Ch("tilt", 7), _Ch("tilt_fine", 8)]
        fx = _fx()
        st = SimpleNamespace(get_patched_fixtures=lambda: [fx],
                             visualizer_positions={1: POS}, visualizer_rotations={1: ROT},
                             set_programmer_value=MagicMock())
        fake = SimpleNamespace(_state=st, _is_moving_head=lambda f: True,
                               _mover_bar_heads=lambda f: 2,
                               push_apply_fixture_transform=MagicMock(),
                               pyFixtureRotated=MagicMock(), pyAimApplied=MagicMock())
        orig = VW.get_channels_for_patched
        VW.get_channels_for_patched = lambda f: bar
        try:
            VW.VisualizerBridge.aimFixturesAt(fake, json.dumps(
                {"x": ZIEL[0], "y": ZIEL[1], "z": ZIEL[2], "fids": [1]}))
        finally:
            VW.get_channels_for_patched = orig
        p16, _ = aim_pan_tilt_16(POS, ZIEL, ROT, **AIM_KW)
        for kopf in (0, 1):
            je = {c.args[1]: c.args[2] for c in st.set_programmer_value.call_args_list
                  if c.kwargs.get("head") == kopf}
            self.assertEqual((je["pan"], je["pan_fine"]), (p16 >> 8, p16 & 255), kopf)


class Viz3dZeigtFeineStellungTest(unittest.TestCase):
    """Zweite Haelfte: ohne sie waere die Korrektur am Geraet sichtbar, im Bild nicht."""

    def _payload(self, fx, chans, programmer):
        from src.ui.visualizer.visualizer_service import _build_fixture_payload
        return _build_fixture_payload(fx, _draht(fx, chans, programmer))

    def test_payload_traegt_die_feine_stellung(self):
        """Invertiertes Geraet: der Payload muss den MODELL-Wert inkl. Fein zeigen —
        also die Ruecknahme als 16-Bit-Paar, nicht nur des Grobwerts."""
        fx = _fx()
        p16, t16 = aim_pan_tilt_16(POS, ZIEL, ROT, **AIM_KW)
        pl = self._payload(fx, FEIN, {"pan": p16 >> 8, "pan_fine": p16 & 255,
                                      "tilt": t16 >> 8, "tilt_fine": t16 & 255})
        self.assertAlmostEqual(pl["pan"], p16 / 256.0, places=6)
        self.assertAlmostEqual(pl["tilt"], t16 / 256.0, places=6)

    def test_payload_ohne_feinkanal_bleibt_ganzzahlig(self):
        """Positivkontrolle: kein Feinkanal -> exakt der alte Payload (int)."""
        fx = _fx()
        pl = self._payload(fx, GROB, {"pan": 100, "tilt": 90})
        self.assertIsInstance(pl["pan"], int)
        self.assertIsInstance(pl["tilt"], int)

    def test_fein_null_bleibt_ganzzahlig(self):
        """Fein = 0 aendert den Payload nicht (kein Diff im Takt)."""
        fx = _fx(invert_pan=False)
        pl = self._payload(fx, FEIN, {"pan": 100, "pan_fine": 0, "tilt": 90, "tilt_fine": 0})
        self.assertEqual((pl["pan"], pl["tilt"]), (100, 90))
        self.assertIsInstance(pl["pan"], int)


if __name__ == "__main__":
    unittest.main()

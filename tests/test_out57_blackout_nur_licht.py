"""OUT-57: Blackout nullt alles ausser Position/Gobo/Optik von Moving Heads.

Vorher setzte ``OutputManager._send_all`` bei Blackout das GANZE Universum auf
``bytes(512)``, also auch Pan/Tilt/Gobo/Prisma: Moving Heads fuhren beim Blackout in
die Grundstellung und beim Loesen sichtbar zurueck. Jetzt nullt der Blackout alles
AUSSER der Erhalten-Maske (Pan/Tilt/Gobo/Prisma/Optik gepatchter Lampen mit echtem
Dimmer). Die Regel ist bewusst invertiert: ungepatchte Roh-Adressen im selben
Universum, ``raw``-/Fine-Kanaele und additives ``cmy_c`` werden sicher dunkel.
Ungepatchte Roh-Universen (kein Masken-Eintrag) bleiben komplett dunkel, der
Laser-NOT-AUS bleibt die letzte Ebene, und das Skript-``blackout`` laeuft ueber
denselben OutputManager-Weg wie Knopf/VC/Web/OSC/Kommandozeile — loest aber nur
seinen EIGENEN Blackout.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num


class _Fx:
    def __init__(self, fid, universe, address, fixture_type="", name=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = fixture_type
        self.fixture_name = name


class _FakeSender:
    def __init__(self):
        self.last = None

    def send_dmx(self, data):
        self.last = data

    def close(self):
        pass


# Moving Head ab Adresse 1: Pan, Tilt, Dimmer, R, G, B, Gobo, Prisma
_MH = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("dimmer", 3), _Ch("color_r", 4),
       _Ch("color_g", 5), _Ch("color_b", 6), _Ch("gobo", 7), _Ch("prism", 8)]
# PAR ab Adresse 20: Dimmer, R, G, B, Strobe
_PAR = [_Ch("dimmer", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4),
        _Ch("strobe", 5)]


def _st():
    return AppState.__new__(AppState)


def _fix_index():
    return {1: (_Fx(1, 1, 1), _MH), 2: (_Fx(2, 1, 20), _PAR)}


def _keep(fix_index):
    return {u: frozenset(s) for u, s in _st()._build_blackout_keep_mask(fix_index).items()}


class BuildBlackoutKeepMaskTest(unittest.TestCase):

    def test_moving_head_behaelt_pan_tilt_gobo_prisma(self):
        mask = _st()._build_blackout_keep_mask(_fix_index())
        # Nur Pan/Tilt/Gobo/Prisma des MH; PAR (Dimmer/RGB/Strobe) ganz 0.
        self.assertEqual(set(mask[1]), {1, 2, 7, 8})

    def test_laser_und_nebel_komplett(self):
        # Sicherheitsabwaegung: Laser/Nebel unter Blackout ganz aus — auch ihr
        # Pan/Gobo, selbst mit Dimmerkanal.
        laser = (_Fx(3, 2, 1, fixture_type="laser"),
                 [_Ch("dimmer", 1), _Ch("pan", 2), _Ch("gobo_wheel", 3)])
        nebel = (_Fx(4, 2, 10, fixture_type="other", name="N-10 Nebelmaschine"),
                 [_Ch("generic", 1), _Ch("generic", 2)])
        mask = _st()._build_blackout_keep_mask({3: laser, 4: nebel})
        self.assertEqual(set(mask[2]), set())

    def test_ohne_echten_dimmer_ganzes_geraet(self):
        # CMY-only-Mover mit Shutter: kein sicherer Dunkel-Kanal -> auch Pan 0.
        fx = _Fx(5, 3, 1)
        chans = [_Ch("cmy_c", 1), _Ch("cmy_m", 2), _Ch("cmy_y", 3), _Ch("shutter", 4),
                 _Ch("pan", 5)]
        mask = _st()._build_blackout_keep_mask({5: (fx, chans)})
        self.assertEqual(set(mask[3]), set())

    def test_jedes_gepatchte_universum_registriert(self):
        mask = _st()._build_blackout_keep_mask({1: (_Fx(1, 4, 1), [])})
        self.assertIn(4, mask)
        self.assertNotIn(1, mask)

    def test_ueberlappung_null_gewinnt(self):
        # Fehlpatch: PAR-Dimmer liegt auf der Pan-Adresse des MH -> Adresse 0.
        idx = {1: (_Fx(1, 1, 1), _MH), 2: (_Fx(2, 1, 1), [_Ch("dimmer", 1)])}
        self.assertNotIn(1, _st()._build_blackout_keep_mask(idx)[1])


class SendPathBlackoutTest(unittest.TestCase):

    def _om(self, extra=None):
        om = OutputManager()
        u = om.add_universe(1)
        werte = {1: 200, 2: 128, 3: 255, 4: 255, 5: 100, 6: 50, 7: 64, 8: 90,
                 20: 255, 21: 10, 22: 20, 23: 30, 24: 0}
        werte.update(extra or {})
        for a, v in werte.items():
            u.set_channel(a, v)
        fake = _FakeSender()
        om._enttec_outputs[1] = fake
        return om, fake

    def _blackout(self, om, fix_index):
        om.set_blackout_keep_mask(_keep(fix_index))
        om.set_blackout(True)
        om._send_all()

    def test_blackout_moving_head_und_par(self):
        om, fake = self._om()
        self._blackout(om, _fix_index())
        d = fake.last
        # Dimmer/RGB = 0
        for a in (3, 4, 5, 6, 20, 21, 22, 23):
            self.assertEqual(d[a - 1], 0, f"Adresse {a} muss unter Blackout 0 sein")
        # Pan/Tilt/Gobo/Prisma unveraendert
        self.assertEqual(d[0], 200)
        self.assertEqual(d[1], 128)
        self.assertEqual(d[6], 64)
        self.assertEqual(d[7], 90)
        # Anzeige-Snapshot folgt (WYSIWYG)
        self.assertEqual(om.get_display_frame(1), d)
        # Blackout aus -> wieder voll
        om.set_blackout(False)
        om._send_all()
        self.assertEqual(fake.last[2], 255)
        self.assertEqual(fake.last[0], 200)

    def test_roh_adresse_im_gepatchten_universum_wird_dunkel(self):
        # Befund 1: Dimmerpack fuers Saallicht auf ungepatchten Adressen 400..411
        # (Simple Desk/Kanal-Fader/Engine-Extra) im Universum des Moving Heads.
        om, fake = self._om({a: 255 for a in range(400, 412)})
        self._blackout(om, _fix_index())
        for a in range(400, 412):
            self.assertEqual(fake.last[a - 1], 0, f"Roh-Adresse {a} leuchtet weiter")
        self.assertEqual(fake.last[0], 200)   # Pan bleibt trotzdem

    def test_rgb_raw_cmy_ohne_dimmer_ganz_dunkel(self):
        # Befund 2: Lichtquellen ausserhalb von Dimmer/additiv-RGB (Lime als raw,
        # additives cmy_c) — ohne echten Dimmer muss das Geraet ganz dunkel sein.
        led = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3),
               _Ch("raw", 4), _Ch("cmy_c", 5), _Ch("pan", 6)]
        idx = {7: (_Fx(7, 1, 100), led)}
        om, fake = self._om({a: 255 for a in range(100, 106)})
        self._blackout(om, idx)
        self.assertEqual(fake.last[99:105], bytes(6))

    def test_16bit_dimmer_fine_wird_null(self):
        # Befund 4: QXF importiert IntensityDimmerFine als ``raw`` -> Fine auf 0,
        # Pan/Tilt-Fine dagegen bleiben.
        mh16 = [_Ch("dimmer", 1), _Ch("raw", 2), _Ch("pan", 3), _Ch("pan_fine", 4),
                _Ch("tilt", 5), _Ch("tilt_fine", 6)]
        idx = {8: (_Fx(8, 1, 200), mh16)}
        om, fake = self._om({200: 255, 201: 255, 202: 11, 203: 22, 204: 33, 205: 44})
        self._blackout(om, idx)
        self.assertEqual(fake.last[199], 0)
        self.assertEqual(fake.last[200], 0, "Dimmer-Fine leuchtet weiter")
        self.assertEqual(fake.last[201:205], bytes([11, 22, 33, 44]))

    def test_roh_universum_ohne_maske_komplett_dunkel(self):
        om, fake = self._om()
        om.set_blackout_keep_mask({})
        om.set_blackout(True)
        om._send_all()
        self.assertEqual(fake.last, bytes(512))

    def test_laser_notaus_bleibt_letzte_ebene(self):
        om, fake = self._om()
        om.set_blackout_keep_mask({1: frozenset({1, 2})})
        om.set_laser_estop_mask({1: frozenset({1})})
        om.set_blackout(True)
        om._send_all()
        self.assertEqual(fake.last[0], 0)     # NOT-AUS-Adresse trotz Erhalten dunkel
        self.assertEqual(fake.last[2], 0)     # nicht erhalten -> 0
        self.assertEqual(fake.last[1], 128)   # erhalten


class AppStateSchiebtMaskeTest(unittest.TestCase):
    """Der Patch-Rebuild muss die Maske beim OutputManager ablegen."""

    def test_rebuild_ruft_set_blackout_keep_mask(self):
        import inspect
        src = inspect.getsource(AppState._rebuild_render_plan)
        self.assertIn("set_blackout_keep_mask", src)


class SkriptBlackoutTest(unittest.TestCase):

    def setUp(self):
        from src.core import app_state as mod

        class _St:
            pass
        self.mod = mod
        self.st = _St()
        self.om = self.st.output_manager = OutputManager()
        self.u = self.om.add_universe(1)
        self.u.set_channel(1, 200)
        self._alt = mod._state
        mod._state = self.st

    def tearDown(self):
        self.mod._state = self._alt

    def _lauf(self, text, sf=None):
        from src.core.engine.script_func import ScriptFunction
        sf = sf or ScriptFunction()
        sf.script = text
        sf.start()
        sf.write({1: self.u}, [], 0.02)
        return sf

    def test_skript_blackout_laeuft_ueber_output_manager(self):
        sf = self._lauf("blackout on\n")
        self.assertTrue(self.om.blackout)
        self.assertEqual(self.u.get_channel(1), 200)   # Live-Universe nicht zerschrieben
        self._lauf("blackout off\n", sf)
        self.assertFalse(self.om.blackout)

    def test_skript_off_loest_operator_blackout_nicht(self):
        # Befund 3a: der Operator hat den Blackout gesetzt -> Skript-off wirkt nicht.
        self.om.set_blackout(True)
        self._lauf("blackout on\nblackout off\n")
        self.assertTrue(self.om.blackout)
        self._lauf("blackout off\n")
        self.assertTrue(self.om.blackout)

    def test_operator_schaltet_neu_skript_off_wirkt_nicht(self):
        sf = self._lauf("blackout on\n")
        # Operator loest und setzt selbst neu -> gehoert jetzt ihm.
        self.om.set_blackout(False)
        self.om.set_blackout(True)
        self._lauf("blackout off\n", sf)
        self.assertTrue(self.om.blackout)

    def test_skript_stop_nimmt_eigenen_blackout_zurueck(self):
        # Befund 3b: Stop/Abbruch nimmt den vom Skript gesetzten Blackout zurueck.
        sf = self._lauf("blackout on\nwait 10\n")
        self.assertTrue(self.om.blackout)
        sf.stop()
        self.assertFalse(self.om.blackout)

    def test_skript_stop_laesst_operator_blackout(self):
        self.om.set_blackout(True)
        sf = self._lauf("blackout on\nwait 10\n")
        sf.stop()
        self.assertTrue(self.om.blackout)


if __name__ == "__main__":
    unittest.main()

"""LAS-32 (S1): Sperrzonen sind NUR ANZEIGE — die DMX-Ausgabe bleibt bytegleich.

Echter Pfad wie in ``test_las25_blackout_laser_aus``: ``_rebuild_render_plan``
-> ``_render_frame`` -> ``OutputManager._send_all`` -> Display-Frame. Verglichen
wird derselbe Ablauf einmal ohne und einmal mit einer Zone, die der Laser laut
Rechnung voll erreicht. Jeder Unterschied waere eine (ungepruefte) Abschaltung
— genau das darf dieser Slice nicht tun.
"""
import os
import pathlib
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.output_manager import OutputManager
from src.core.laser import sperrzonen as S
from src.core.laser.sperrzonen import LaserFeld, Sperrzone, SperrzonenDaten


class _Rg:
    def __init__(self, von, bis, name, kind=""):
        self.range_from, self.range_to, self.name, self.kind = von, bis, name, kind


class _Ch:
    def __init__(self, attr, num, ranges=(), default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default
        self.ranges = list(ranges)
        self.name = attr


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 3
    protocol = ""

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype
        self.fixture_name = f"fx{fid}"
        self.label = f"fx{fid}"


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


_LASER = _Fx(7, 1, 10, "laser")
_PAR = _Fx(9, 1, 20)
_CHANNELS = {
    7: [_Ch("shutter", 1, [_Rg(0, 49, "Auto run", "open"),
                           _Rg(50, 99, "Laser off", "closed"),
                           _Rg(100, 255, "Manual", "open")]),
        _Ch("laser_bank", 2), _Ch("laser_x", 3)],
    9: [_Ch("intensity", 1), _Ch("color_r", 2)],
}


def _zonen_voll_im_feld() -> SperrzonenDaten:
    d = SperrzonenDaten()
    d.zonen.append(Sperrzone(id="z", name="Publikum", x=0, y=0, z=8,
                             breite=10, hoehe=3, tiefe=6))
    d.setze_feld(7, LaserFeld(links=30, rechts=30, oben=20, unten=40, zuschlag=5))
    return d


def _make(daten):
    om = OutputManager()
    om.add_universe(1)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {7: {"shutter": 120, "laser_bank": 5, "laser_x": 77},
                     9: {"intensity": 200, "color_r": 150}}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_LASER, _PAR]
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._emit = lambda *a, **k: None
    from src.core.stage.scene_graph import SceneGraph
    st._scene = SceneGraph()
    st._view_registry = A._ViewRegistry()
    st.visualizer_positions = {7: (0.0, 4.0, 0.0)}
    st.visualizer_rotations = {7: (20.0, 0.0, 0.0)}
    if daten is not None:
        st.sperrzonen = daten
    st._rebuild_render_plan()
    return st, om


class AusgabeBytegleichTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _ablauf(self, daten):
        st, om = _make(daten)
        bilder = []

        def bild():
            st._render_frame(0.025)
            om._send_all()
            bilder.append(bytes(om._display_frame[1]))

        bild()
        st.programmer[7]["laser_x"] = 200
        bild()
        om.grand_master = 0.5
        bild()
        om.set_blackout(True)
        bild()
        om.set_blackout(False)
        om.grand_master = 1.0
        om.set_laser_estop_mask({1: frozenset({10, 11, 12})})
        bild()
        om.set_laser_estop_mask({})
        bild()
        return st, om, bilder

    def test_laser_erreicht_die_zone_laut_rechnung(self):
        """Vorbedingung: sonst waere der Vergleich unten nichtssagend."""
        st, _om = _make(_zonen_voll_im_feld())
        kopf, befunde = S.state_befunde(st)
        self.assertEqual([b.status for b in befunde], [S.STATUS_ERREICHT])
        self.assertIn("NICHT ab", kopf)

    def test_ausgabe_mit_und_ohne_zonen_ist_bytegleich(self):
        _s0, om0, ohne_attribut = self._ablauf(None)
        _s1, om1, leer = self._ablauf(SperrzonenDaten())
        _s2, om2, mit = self._ablauf(_zonen_voll_im_feld())
        self.assertEqual(len(mit), 6)
        self.assertEqual(ohne_attribut, leer)
        self.assertEqual(leer, mit)
        # Der Laser laeuft im ersten Bild wirklich (Betriebsart „Manual").
        self.assertEqual(mit[0][9:12], bytes([120, 5, 77]))
        # Masken des Ausgabepfads sind identisch.
        for name in ("_gm_laser_aus_mask", "_laser_estop_mask", "_laser_adressen"):
            self.assertEqual(getattr(om1, name, None), getattr(om2, name, None), name)

    def test_abfrage_der_befunde_aendert_die_ausgabe_nicht(self):
        st, om = _make(_zonen_voll_im_feld())
        st._render_frame(0.025)
        om._send_all()
        vorher = bytes(om._display_frame[1])
        for _ in range(3):
            S.state_befunde(st)
        st._render_frame(0.025)
        om._send_all()
        self.assertEqual(bytes(om._display_frame[1]), vorher)

    def test_ausgabepfad_kennt_das_modul_nicht(self):
        wurzel = pathlib.Path(__file__).resolve().parent.parent / "src" / "core"
        for datei in sorted((wurzel / "dmx").glob("*.py")):
            text = datei.read_text(encoding="utf-8").lower()
            self.assertNotIn("sperrzon", text, datei.name)
        # app_state haelt den Bestand vor (ein Attribut) und nimmt beim
        # Loeschen/Zurueckholen eines Geraets dessen Randwinkel mit — sonst
        # nichts. Render-Pfad, Plan und Masken greifen nicht darauf zu: das
        # Wort darf nur in diesen Funktionen vorkommen.
        import ast
        quelle = (wurzel / "app_state.py").read_text(encoding="utf-8")
        erlaubt = {"__init__", "add_fixture", "remove_fixture",
                   "_sperrzonen_feld_nehmen", "_sperrzonen_feld_zurueck"}
        zeilen = quelle.splitlines()
        gefunden = set()
        for knoten in ast.walk(ast.parse(quelle)):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # nur die Zeilen der Funktion selbst, nicht die ihrer inneren defs
            innere = [k for k in ast.walk(knoten)
                      if isinstance(k, ast.FunctionDef) and k is not knoten]
            for nr in range(knoten.lineno, knoten.end_lineno + 1):
                if any(k.lineno <= nr <= k.end_lineno for k in innere):
                    continue
                z = zeilen[nr - 1]
                if "sperrzon" in z.lower() and not z.strip().startswith("#"):
                    gefunden.add(knoten.name)
        self.assertTrue(gefunden)
        self.assertEqual(gefunden - erlaubt - {"_undo", "_redo"}, set(), gefunden)
        for name in ("_render_frame", "_rebuild_render_plan",
                     "_build_gm_laser_aus_mask", "set_laser_estop"):
            self.assertIn(f"def {name}(", quelle, name)   # die Probe meint echte Namen
            self.assertNotIn(name, gefunden)


if __name__ == "__main__":
    unittest.main()

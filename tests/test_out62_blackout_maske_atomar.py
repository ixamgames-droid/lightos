"""OUT-62: Blackout-Erhalten-Maske und Render-Plan wechseln sicher; ``color`` bleibt.

Codex-Review #833:

* (P1) ``_rebuild_render_plan`` tauscht den Render-Plan unter ``_plan_lock``,
  setzt die neue Blackout-ERHALTEN-Maske aber erst danach. Im Fenster dazwischen
  rendert der neue Plan z. B. einen Dimmer an einer Adresse, die die ALTE Maske
  als Pan fuehrte - bei aktivem Blackout geht sein Wert fuer einen oder mehrere
  Frames hinaus. Jetzt steht beim Tausch die Schnittmenge alt∩neu (in beiden
  Patches ein Nicht-Licht-Kanal), danach die neue Maske.
* (P2) Das unterstuetzte Alt-Attribut ``color`` (Farbrad, wie ``color_wheel``)
  fehlte in der Erhalten-Liste: der Blackout schickte das Rad auf 0 und beim
  Loesen zurueck - genau die mechanische Bewegung, die OUT-57 vermeiden soll.
"""
import os
import threading
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe


class _Ch:
    def __init__(self, attr, num):
        self.attribute = attr
        self.channel_number = num
        self.default_value = 0


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    protocol = ""
    fixture_name = ""

    def __init__(self, fid, universe, address, kanaele, fixture_type=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channel_count = len(kanaele)
        self.fixture_type = fixture_type
        self.kanaele = kanaele


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


# Moving Head ab Adresse 1: Pan, Tilt, Dimmer, Gobo
_MH = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("dimmer", 3), _Ch("gobo", 4)]
# PAR ab Adresse 1: Dimmer, R, G, B - liegt jetzt dort, wo Pan/Tilt waren
_PAR = [_Ch("dimmer", 1), _Ch("color_r", 2), _Ch("color_g", 3), _Ch("color_b", 4)]


def _make_state(patch, om):
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = list(patch)
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._rebuild_render_plan()
    return st


class _OM:
    """Schneidet jede gesetzte Erhalten-Maske mit — samt der Angabe, ob der
    Render-Plan zu diesem Zeitpunkt schon getauscht war."""

    def __init__(self):
        self.maske = {}
        self.verlauf = []
        self.state = None
        self.alter_plan = None

    def set_gm_address_mask(self, m):
        pass

    def set_blackout_keep_mask(self, m):
        getauscht = (self.state is not None and self.alter_plan is not None
                     and self.state._fix_index is not self.alter_plan)
        self.verlauf.append((getauscht, {u: set(s) for u, s in m.items()}))
        self.maske = m


class MaskeUndPlanTest(unittest.TestCase):

    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: fx.kanaele

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_beim_plantausch_haelt_die_maske_nichts_was_der_neue_plan_licht_nennt(self):
        om = _OM()
        st = _make_state([_Fx(1, 1, 1, _MH)], om)
        self.assertEqual({1: {1, 2, 4}}, {u: set(s) for u, s in om.maske.items()},
                         "Ausgangslage: Pan/Tilt/Gobo des Moving Heads bleiben")

        # Umpatchen: an Adresse 1 liegt jetzt ein PAR (Dimmer auf 1).
        om.state, om.alter_plan, om.verlauf = st, st._fix_index, []
        st._patch_cache = [_Fx(2, 1, 1, _PAR)]
        st._rebuild_render_plan()

        neu = {u: set(s) for u, s in st._build_blackout_keep_mask(st._fix_index).items()}
        vor_dem_tausch = [m for getauscht, m in om.verlauf if not getauscht]
        beim_tausch = vor_dem_tausch[-1] if vor_dem_tausch else {1: {1, 2, 4}}
        for u, addrs in beim_tausch.items():
            self.assertTrue(addrs <= neu.get(u, set()),
                            f"beim Plantausch erhielt der Blackout {sorted(addrs)} — der "
                            f"neue Plan erlaubt nur {sorted(neu.get(u, set()))}: der neue "
                            "Dimmer auf Adresse 1 ginge durch den Blackout")
        self.assertEqual(neu, {u: set(s) for u, s in om.maske.items()},
                         "nach dem Tausch muss die neue Maske stehen")

    def test_uebergang_ist_die_schnittmenge(self):
        om = _OM()
        mh2 = [_Ch("dimmer", 1), _Ch("pan", 2), _Ch("tilt", 3), _Ch("gobo", 4)]
        st = _make_state([_Fx(1, 1, 1, _MH)], om)                    # erhaelt {1,2,4}
        om.state, om.alter_plan, om.verlauf = st, st._fix_index, []
        st._patch_cache = [_Fx(1, 1, 1, mh2)]                         # erhaelt {2,3,4}
        st._rebuild_render_plan()
        vor_dem_tausch = [m for getauscht, m in om.verlauf if not getauscht]
        self.assertTrue(vor_dem_tausch, "vor dem Plantausch wurde keine Maske gesetzt")
        self.assertEqual({1: {2, 4}}, vor_dem_tausch[-1])
        self.assertEqual({1: {2, 3, 4}}, {u: set(s) for u, s in om.maske.items()})

    def test_entpatchtes_universum_faellt_im_uebergang_ganz_weg(self):
        om = _OM()
        st = _make_state([_Fx(1, 1, 1, _MH), _Fx(2, 2, 1, _MH)], om)
        om.state, om.alter_plan, om.verlauf = st, st._fix_index, []
        st._patch_cache = [_Fx(1, 1, 1, _MH)]
        st._rebuild_render_plan()
        vor_dem_tausch = [m for getauscht, m in om.verlauf if not getauscht]
        self.assertNotIn(2, vor_dem_tausch[-1],
                         "Universum ohne Eintrag nullt der Blackout komplett")


class AltAttributColorTest(unittest.TestCase):

    def test_color_rad_bleibt_beim_blackout_stehen(self):
        st = AppState.__new__(AppState)
        mh = (_Fx(1, 1, 1, []), [_Ch("pan", 1), _Ch("dimmer", 2), _Ch("color", 3)])
        maske = st._build_blackout_keep_mask({1: mh})
        self.assertIn(3, maske[1], "Farbrad mit Alt-Attribut `color` faehrt beim "
                                   "Blackout auf 0 und beim Loesen zurueck")

    def test_color_ohne_dimmer_geht_weiter_auf_null(self):
        st = AppState.__new__(AppState)
        spot = (_Fx(1, 1, 1, []), [_Ch("pan", 1), _Ch("shutter", 2), _Ch("color", 3)])
        maske = st._build_blackout_keep_mask({1: spot})
        self.assertEqual(set(), set(maske[1]),
                         "ohne echten Dimmer bleibt nichts stehen (OUT-57)")


if __name__ == "__main__":
    unittest.main()

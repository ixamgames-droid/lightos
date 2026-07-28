"""FM-HEADLAYOUT A4 — VC-Submaster pro Kopf.

Letzter Slice von FM-HEADLAYOUT/FM-9: ein VC-Submaster-Fader darf nicht nur ganze
Geraete dimmen, sondern einzelne KOEPFE eines Mehrkopf-Geraets (Hydrabeam/Spider/
Mover-Bar). Weil ``submaster_factor_for(fid)`` nur EINEN Faktor pro Geraet kennt,
muss der Faktor adressgenau werden — das ist die „Geraete-Maske im DMX-Ausgabepfad".

Fuenf Ebenen:
  1. ``group_cells.head_restrictions`` / ``cells_in_grid_order`` (reine Funktionen):
     Zellen -> Kopf-Einschraenkung, inkl. Vorrang „ganzes Geraet schlaegt Koepfe".
  2. OutputManager-API: kopf-beschraenkte Slots zaehlen weder global noch
     geraeteweit, sondern nur in ``submaster_head_factors_for``.
  3. ``AppState._fixture_head_intensity_addrs``: die KOPF-EXKLUSIVE Adressmaske.
     Kernfalle — ein von allen Koepfen GETEILTER Master-Dimmer darf NIE dabei sein,
     sonst dimmt „Kopf 2" das ganze Geraet.
  4. Renderer (``_render_frame`` Schritt 4b): nur die Kanaele des gewaehlten Kopfes
     werden skaliert, die anderen Koepfe bleiben unberuehrt; ohne Kopf-Zellen exakt
     das Bestandsverhalten.
  5. ``VCSlider``: Reichweite 'Nur Auswahl' / 'Feste Gruppe' loest Kopf-Zellen auf
     und reicht sie an ``set_submaster(heads=...)`` durch.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.dmx.output_manager import OutputManager
from src.core.group_cells import head_restrictions, cells_in_grid_order


# ── 1. Reine Zell-Funktionen ─────────────────────────────────────────────────

class TestHeadRestrictions(unittest.TestCase):
    def test_head_cells_become_restriction(self):
        self.assertEqual(head_restrictions(["2:0", "2:3"]), {2: {0, 3}})

    def test_whole_device_cell_beats_head_cells(self):
        # Dieselbe Vorrang-Regel wie AppState.set_selected_cells: die groebere
        # Aussage ist die sichere. Sonst dimmte ein Fader, der „Geraet 3" meint,
        # nur dessen Kopf 1.
        self.assertEqual(head_restrictions(["3", "3:1"]), {})

    def test_mixed_selection_only_restricts_head_devices(self):
        self.assertEqual(head_restrictions(["1", "2:0", "2:3", "3", "3:1"]),
                         {2: {0, 3}})

    def test_plain_fids_give_no_restriction(self):
        # WICHTIG: leeres Ergebnis heisst „keine Kopf-Einschraenkung", nicht
        # „nichts gewaehlt" — sonst waere jeder normale Fader plotzlich wirkungslos.
        self.assertEqual(head_restrictions(["1", "2", 3]), {})

    def test_empty_and_garbage_are_safe(self):
        self.assertEqual(head_restrictions([]), {})
        self.assertEqual(head_restrictions(None), {})
        self.assertEqual(head_restrictions(["", "abc", None, "x:y"]), {})

    def test_int_cells_supported(self):
        self.assertEqual(head_restrictions([1, 2]), {})


class TestCellsInGridOrder(unittest.TestCase):
    def test_grid_order_row_then_col_and_keeps_heads(self):
        pos = {"0,0": "1:0", "1,0": "1:1", "0,1": 5}
        self.assertEqual(cells_in_grid_order(pos), ["1:0", "1:1", "5"])

    def test_dedup_and_bad_keys_skipped(self):
        pos = {"0,0": "1:0", "1,0": "1:0", "nope": 7, "0,1": 2}
        self.assertEqual(cells_in_grid_order(pos), ["1:0", "2"])

    def test_empty(self):
        self.assertEqual(cells_in_grid_order({}), [])
        self.assertEqual(cells_in_grid_order(None), [])


# ── 2. OutputManager-API ─────────────────────────────────────────────────────

class TestOutputManagerHeadSubmaster(unittest.TestCase):
    def setUp(self):
        self.om = OutputManager()

    def test_head_slot_not_global(self):
        self.om.set_submaster("h", 0.5, [1], heads={1: {2}})
        self.assertEqual(self.om.effective_submaster(), 1.0)

    def test_head_slot_does_not_dim_whole_fixture(self):
        # Der Kern: sonst dimmte „Kopf 2" ueber submaster_factor_for das GANZE Geraet.
        self.om.set_submaster("h", 0.5, [1], heads={1: {2}})
        self.assertEqual(self.om.submaster_factor_for(1), 1.0)
        self.assertEqual(self.om.submaster_head_factors_for(1), {2: 0.5})

    def test_head_factors_multiply_per_head(self):
        self.om.set_submaster("a", 0.5, [1], heads={1: {2}})
        self.om.set_submaster("b", 0.5, [1], heads={1: {2, 3}})
        f = self.om.submaster_head_factors_for(1)
        self.assertAlmostEqual(f[2], 0.25)     # beide treffen Kopf 2
        self.assertAlmostEqual(f[3], 0.5)      # nur b trifft Kopf 3

    def test_slot_restricting_one_fixture_still_dims_other_targets_wholly(self):
        # Ein Slot auf [1, 2] mit Kopf-Einschraenkung NUR fuer fid 1: fid 2 hat
        # keine Kopf-Angabe -> wird weiterhin als ganzes Geraet gedimmt.
        self.om.set_submaster("m", 0.5, [1, 2], heads={1: {0}})
        self.assertEqual(self.om.submaster_factor_for(1), 1.0)
        self.assertAlmostEqual(self.om.submaster_factor_for(2), 0.5)
        self.assertEqual(self.om.submaster_head_factors_for(1), {0: 0.5})
        self.assertEqual(self.om.submaster_head_factors_for(2), {})

    def test_head_entry_for_non_target_fixture_ignored(self):
        self.om.set_submaster("m", 0.5, [1], heads={9: {0}})
        self.assertEqual(self.om.submaster_head_factors_for(9), {})

    def test_heads_without_fids_is_not_global(self):
        # Defensiv: heads ohne fids-Ziel darf NIE als globaler Submaster das
        # gesamte Rig dimmen.
        self.om.set_submaster("h", 0.5, None, heads={1: {0}})
        self.assertEqual(self.om.effective_submaster(), 1.0)
        self.assertEqual(self.om.submaster_head_factors_for(1), {0: 0.5})

    def test_clear_removes_head_slot(self):
        self.om.set_submaster("h", 0.5, [1], heads={1: {2}})
        self.om.clear_submaster("h")
        self.assertEqual(self.om.submaster_head_factors_for(1), {})

    def test_empty_heads_is_plain_assigned_submaster(self):
        for empty in (None, {}, {1: set()}, {1: []}):
            with self.subTest(empty=empty):
                om = OutputManager()
                om.set_submaster("a", 0.5, [1], heads=empty)
                self.assertAlmostEqual(om.submaster_factor_for(1), 0.5)
                self.assertEqual(om.submaster_head_factors_for(1), {})

    def test_backward_compatible_calls_unchanged(self):
        # Bestandsaufrufer (2 bzw. 3 Argumente) muessen byte-gleich weiterlaufen.
        self.om.set_submaster(0, 0.4)
        self.assertAlmostEqual(self.om.effective_submaster(), 0.4)
        self.om.set_submaster("s", 0.5, [7])
        self.assertAlmostEqual(self.om.submaster_factor_for(7), 0.5)

    def test_level_clamped_and_bad_ids_survive(self):
        self.om.set_submaster("h", 2.0, [1], heads={1: {0}})
        self.assertEqual(self.om.submaster_head_factors_for(1), {0: 1.0})
        self.om.set_submaster("i", -1.0, [1], heads={1: {0}})
        self.assertEqual(self.om.submaster_head_factors_for(1)[0], 0.0)
        self.om.set_submaster("j", 0.5, [1], heads={"nope": {0}})
        self.assertEqual(self.om.submaster_head_factors_for("nope"), {})

    def test_string_fid_lookup(self):
        self.om.set_submaster("h", 0.5, [1], heads={"1": ["2"]})
        self.assertEqual(self.om.submaster_head_factors_for("1"), {2: 0.5})


# ── 3./4. Renderer: kopf-exklusive Adressmaske + Schritt 4b ──────────────────

class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


def _hydra_channels():
    """Hydrabeam-Fall: EIN geteilter Master-Dimmer (ch1) + 4 Koepfe mit je RGB."""
    chans = [_Ch("intensity", 1)]
    n = 2
    for _head in range(4):
        for attr in ("color_r", "color_g", "color_b"):
            chans.append(_Ch(attr, n))
            n += 1
    return chans                      # Adressen 1 (Dimmer), 2..13 (4x RGB)


def _per_head_dimmer_channels():
    """Geraet mit EIGENEM Dimmer je Kopf (2 Koepfe): dim/red, dim/red."""
    return [_Ch("intensity", 1), _Ch("color_r", 2),
            _Ch("intensity", 3), _Ch("color_r", 4)]


class TestHeadIntensityAddrMask(unittest.TestCase):
    """Die Maske, die entscheidet, WAS ein Kopf-Fader anfassen darf."""

    def setUp(self):
        self.st = AppState.__new__(AppState)

    def test_shared_master_dimmer_is_never_touched(self):
        # DER Kernfall: channels_for_head wuerde den geteilten Dimmer JEDEM Kopf
        # durchreichen -> „Kopf 2" dimmte das ganze Geraet. Hier darf er fehlen.
        fx, chans = _Fx(1, 1, 1), _hydra_channels()
        addrs = self.st._fixture_head_intensity_addrs(fx, chans, 2)
        self.assertNotIn(1, addrs, "geteilter Master-Dimmer gehoert NICHT zur Kopfmaske")
        self.assertEqual(addrs, [8, 9, 10], "Kopf 2 = drittes RGB-Vorkommen")

    def test_each_head_gets_its_own_addresses(self):
        fx, chans = _Fx(1, 1, 1), _hydra_channels()
        got = {h: self.st._fixture_head_intensity_addrs(fx, chans, h) for h in range(4)}
        self.assertEqual(got, {0: [2, 3, 4], 1: [5, 6, 7],
                               2: [8, 9, 10], 3: [11, 12, 13]})
        # Disjunkt — kein Kopf greift in einen anderen.
        flat = [a for v in got.values() for a in v]
        self.assertEqual(len(flat), len(set(flat)))

    def test_per_head_dimmer_wins_over_color(self):
        fx, chans = _Fx(1, 1, 1), _per_head_dimmer_channels()
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 0), [1])
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 1), [3])

    def test_single_head_fixture_has_no_head_mask(self):
        # Jedes Attribut kommt genau einmal vor -> nichts ist kopf-exklusiv. Der
        # Fader ist dort ehrlich wirkungslos, statt ersatzweise alles zu dimmen.
        fx = _Fx(1, 1, 1)
        chans = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3)]
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 0), [])

    def test_head_out_of_range_is_empty(self):
        fx, chans = _Fx(1, 1, 1), _hydra_channels()
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 9), [])

    def test_subtractive_cmy_excluded(self):
        # A3D-37: CMY Richtung 0 skalieren HELLT auf -> nie als virtueller Dimmer.
        fx = _Fx(1, 1, 1)
        chans = [_Ch("cmy_c", 1), _Ch("cmy_c", 2)]
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 0), [])

    def test_pan_tilt_never_in_mask(self):
        fx = _Fx(1, 1, 1)
        chans = [_Ch("pan", 1), _Ch("pan", 2), _Ch("color_r", 3), _Ch("color_r", 4)]
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 1), [4])

    def test_address_out_of_dmx_range_dropped(self):
        fx = _Fx(1, 1, 511)
        chans = [_Ch("color_r", 1), _Ch("color_r", 2), _Ch("color_r", 3)]
        # Adressen 511, 512, 513 -> die 513 faellt raus.
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 2), [])
        self.assertEqual(self.st._fixture_head_intensity_addrs(fx, chans, 1), [512])


class _FMAll:
    """Fake-FunctionManager: treibt Adressen 1..13 auf voll."""
    def tick(self, universes, patch_cache, dt):
        if 1 in universes:
            for a in range(1, 14):
                universes[1].set_channel(a, 255)


def _make_state_hydra():
    """AppState mit EINEM 4-Kopf-Geraet (geteilter Dimmer @1, 4x RGB @2..13)."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FMAll()
    fx = _Fx(1, 1, 1)
    st._fix_index = {1: (fx, _hydra_channels())}
    st._default_frame = {1: bytes(512)}
    st._commit_spans = {1: [(1, 13)]}
    st._patched_set = {1: frozenset(range(1, 14))}
    st._engine_extra_prev = {}
    st._patch_cache = [fx]
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    import threading as _t
    st._prog_lock = _t.RLock()
    st.output_manager = OutputManager()
    return st


class TestRendererHeadSubmaster(unittest.TestCase):
    def _v(self, st, addr):
        return st.universes[1].get_channel(addr)

    def _all(self, st):
        return [self._v(st, a) for a in range(1, 14)]

    def test_baseline_everything_full(self):
        st = _make_state_hydra()
        st._render_frame(0.02)
        self.assertEqual(self._all(st), [255] * 13)

    def test_head_submaster_dims_only_that_head(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {2}})
        st._render_frame(0.02)
        self.assertEqual(self._v(st, 1), 255, "geteilter Master-Dimmer unberuehrt")
        for a in (2, 3, 4, 5, 6, 7, 11, 12, 13):
            self.assertEqual(self._v(st, a), 255, f"fremder Kopf @{a} unberuehrt")
        for a in (8, 9, 10):
            self.assertAlmostEqual(self._v(st, a), 127, delta=1)

    def test_two_heads_independently(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("h1", 0.5, [1], heads={1: {0}})
        st.output_manager.set_submaster("h2", 0.25, [1], heads={1: {3}})
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, 2), 127, delta=1)     # Kopf 0
        self.assertEqual(self._v(st, 5), 255)                    # Kopf 1 unberuehrt
        self.assertEqual(self._v(st, 8), 255)                    # Kopf 2 unberuehrt
        self.assertAlmostEqual(self._v(st, 11), 63, delta=1)     # Kopf 3

    def test_head_and_global_submaster_combine(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("g", 0.5)                 # global
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {2}})
        st._render_frame(0.02)
        # Global trifft die Intensitaets-Quelle des Geraets = den geteilten Dimmer.
        self.assertAlmostEqual(self._v(st, 1), 127, delta=1)
        # Kopf 2 zusaetzlich ueber seine eigenen Farbkanaele -> real 25 %.
        self.assertAlmostEqual(self._v(st, 8), 127, delta=1)
        self.assertEqual(self._v(st, 5), 255)

    def test_whole_fixture_and_head_submaster_combine(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("f", 0.5, [1])            # ganzes Geraet
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {2}})
        st._render_frame(0.02)
        self.assertAlmostEqual(self._v(st, 1), 127, delta=1)      # Geraete-Dimmer
        self.assertAlmostEqual(self._v(st, 8), 127, delta=1)      # Kopf-Farbe
        self.assertEqual(self._v(st, 5), 255)

    def test_no_head_restriction_is_byte_identical(self):
        # Regression: ohne Kopf-Angabe muss der Renderer exakt das Alte tun.
        st_a = _make_state_hydra()
        st_a.output_manager.set_submaster("s", 0.5, [1])
        st_a._render_frame(0.02)
        st_b = _make_state_hydra()
        st_b.output_manager.set_submaster("s", 0.5, [1], heads=None)
        st_b._render_frame(0.02)
        self.assertEqual(self._all(st_a), self._all(st_b))
        self.assertAlmostEqual(self._v(st_a, 1), 127, delta=1)
        self.assertEqual(self._v(st_a, 2), 255, "Farbe bleibt, der Dimmer traegt")

    def test_head_submaster_at_full_changes_nothing(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("h", 1.0, [1], heads={1: {2}})
        st._render_frame(0.02)
        self.assertEqual(self._all(st), [255] * 13)

    def test_head_submaster_at_zero_blacks_out_only_that_head(self):
        st = _make_state_hydra()
        st.output_manager.set_submaster("h", 0.0, [1], heads={1: {1}})
        st._render_frame(0.02)
        self.assertEqual([self._v(st, a) for a in (5, 6, 7)], [0, 0, 0])
        self.assertEqual(self._v(st, 1), 255)
        self.assertEqual(self._v(st, 2), 255)

    def test_head_factor_applied_once_no_double_rounding(self):
        # Pro Adresse GENAU EIN int() — zwei Durchgaenge (geraeteweit, dann Kopf)
        # wuerden doppelt abrunden und den Faderweg verfaelschen.
        st = _make_state_hydra()
        st.output_manager.set_submaster("f", 0.5, [1])
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {0}})
        st._render_frame(0.02)
        # Kopf-0-Farbe traegt NUR den Kopf-Faktor (der Geraete-Faktor sitzt auf
        # dem Dimmer, der die Intensitaets-Quelle ist): 255*0.5 = 127, nicht 126.
        self.assertEqual(self._v(st, 2), 127)


class TestRendererPerHeadDimmerFixture(unittest.TestCase):
    """Geraet mit eigenem Dimmer je Kopf: der Kopf-Fader trifft dessen Dimmer."""

    def _make(self):
        st = AppState.__new__(AppState)
        st.universes = {1: Universe(1)}
        st.programmer = {}
        st.playback_engine = None

        class _FM:
            def tick(self, universes, patch_cache, dt):
                if 1 in universes:
                    for a in range(1, 5):
                        universes[1].set_channel(a, 255)

        st.function_manager = _FM()
        fx = _Fx(1, 1, 1)
        st._fix_index = {1: (fx, _per_head_dimmer_channels())}
        st._default_frame = {1: bytes(512)}
        st._commit_spans = {1: [(1, 4)]}
        st._patched_set = {1: frozenset(range(1, 5))}
        st._engine_extra_prev = {}
        st._patch_cache = [fx]
        st.submaster_level = 1.0
        st.fixture_dimmers = {}
        import threading as _t
        st._prog_lock = _t.RLock()
        st.output_manager = OutputManager()
        return st

    def test_head_fader_hits_that_heads_dimmer_only(self):
        st = self._make()
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {1}})
        st._render_frame(0.02)
        self.assertEqual(st.universes[1].get_channel(1), 255)   # Kopf 0 Dimmer
        self.assertEqual(st.universes[1].get_channel(2), 255)   # Kopf 0 Farbe
        self.assertAlmostEqual(st.universes[1].get_channel(3), 127, delta=1)
        self.assertEqual(st.universes[1].get_channel(4), 255,
                         "Farbe bleibt — der Kopf-Dimmer traegt die Helligkeit")

    def test_device_wide_and_head_multiply_on_same_address(self):
        # Hier IST die Kopf-Adresse auch eine inten_addr -> beide Faktoren treffen
        # dieselbe Adresse und muessen sich multiplizieren (0.5*0.5 = 25 %).
        st = self._make()
        st.output_manager.set_submaster("f", 0.5, [1])
        st.output_manager.set_submaster("h", 0.5, [1], heads={1: {1}})
        st._render_frame(0.02)
        self.assertAlmostEqual(st.universes[1].get_channel(1), 127, delta=1)
        self.assertAlmostEqual(st.universes[1].get_channel(3), 63, delta=1)


# ── 5. VCSlider-Verdrahtung ──────────────────────────────────────────────────

class _FakeState:
    """Zaehlt zusaetzlich die Gruppen-Abfragen — ``_apply`` laeuft bei jeder
    Fader-Bewegung, zwei DB-Sessions pro Tick waeren spuerbar."""

    def __init__(self, cells=(), group_cells=()):
        self._cells = list(cells)
        self._group = list(group_cells)
        self.group_lookups = 0

    def get_selected_cells(self):
        return list(self._cells)

    def get_selected_fids(self):
        out = []
        for c in self._cells:
            fid = int(str(c).split(":", 1)[0])
            if fid not in out:
                out.append(fid)
        return out

    def group_cells_by_name(self, name):
        self.group_lookups += 1
        return list(self._group)

    def validate_head_restrictions(self, heads):
        # Fake ohne Patch: reicht durch (die echte Pruefung hat eigene Tests).
        return dict(heads or {})


class TestVCSliderHeadScope(unittest.TestCase):
    """``_submaster_targets`` haengt nur an zwei Feldern — ohne Qt-Instanz
    getestet, damit die Reichweiten-Logik unabhaengig vom Widget-Bau gilt."""

    def _slider(self, scope, group=""):
        from src.ui.virtualconsole.vc_slider import VCSlider
        s = VCSlider.__new__(VCSlider)
        s.programmer_scope = scope
        s.programmer_group = group
        return s

    def test_scope_all_never_restricts_heads(self):
        s = self._slider("all")
        self.assertEqual(s._submaster_targets(_FakeState(["1:0"])), (None, {}))

    def test_scope_selected_uses_head_selection(self):
        s = self._slider("selected")
        fids, heads = s._submaster_targets(_FakeState(["1:0", "1:2", "2"]))
        self.assertEqual(heads, {1: {0, 2}})
        self.assertEqual(fids, [1, 2])

    def test_scope_group_uses_group_head_cells(self):
        s = self._slider("group", "Hydra · Köpfe")
        st = _FakeState(cells=["9"], group_cells=["5:0", "5:1"])
        fids, heads = s._submaster_targets(st)
        self.assertEqual(heads, {5: {0, 1}})
        self.assertEqual(fids, [5], "Kopf-Zellen tragen ihren Basis-fid bei")

    def test_group_is_queried_only_once_per_apply(self):
        s = self._slider("group", "G")
        st = _FakeState(group_cells=["5:0", "5:1"])
        s._submaster_targets(st)
        self.assertEqual(st.group_lookups, 1,
                         "Fader-Tick darf die Gruppe nur EINMAL abfragen")

    def test_scope_group_without_name_falls_back_to_global(self):
        s = self._slider("group", "")
        self.assertEqual(s._submaster_targets(_FakeState(["1:0"])), (None, {}))

    def test_plain_selection_gives_no_restriction(self):
        s = self._slider("selected")
        self.assertEqual(s._submaster_targets(_FakeState(["1", "2"]))[1], {})

    def test_broken_state_is_swallowed(self):
        class _Boom:
            def get_selected_cells(self):
                raise RuntimeError("nope")
        s = self._slider("selected")
        self.assertEqual(s._submaster_targets(_Boom()), ([], {}))

    def test_fid_view_matches_combined(self):
        s = self._slider("selected")
        st = _FakeState(["1:0", "2"])
        self.assertEqual(s._submaster_target_fids(st), s._submaster_targets(st)[0])
        self.assertEqual(s._submaster_target_heads(st), s._submaster_targets(st)[1])


class TestVCSliderPassesHeads(unittest.TestCase):
    """``_apply`` muss die Kopf-Einschraenkung wirklich durchreichen."""

    def test_apply_forwards_heads_kwarg(self):
        from PySide6.QtWidgets import QApplication
        from src.core.app_state import get_state
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        _app = QApplication.instance() or QApplication([])
        state = get_state()
        calls = []
        om = state.output_manager
        orig = om.set_submaster
        om.set_submaster = lambda *a, **k: calls.append((a, k))
        try:
            s = VCSlider("sm")
            s.mode = SliderMode.SUBMASTER
            s.programmer_scope = "selected"
            s._submaster_targets = lambda st: ([1], {1: {2}})
            s.value = 128
        finally:
            om.set_submaster = orig
            om.clear_submaster(id(s))
        self.assertTrue(calls, "SUBMASTER muss set_submaster rufen")
        self.assertEqual(calls[-1][1].get("heads"), {1: {2}})

    def test_apply_sends_none_when_no_heads(self):
        # Bestandsfall: keine Kopf-Zellen -> heads=None (nicht {}), damit der
        # OutputManager exakt den alten Pfad nimmt.
        from PySide6.QtWidgets import QApplication
        from src.core.app_state import get_state
        from src.ui.virtualconsole.vc_slider import VCSlider, SliderMode
        _app = QApplication.instance() or QApplication([])
        state = get_state()
        calls = []
        om = state.output_manager
        orig = om.set_submaster
        om.set_submaster = lambda *a, **k: calls.append((a, k))
        try:
            s = VCSlider("sm2")
            s.mode = SliderMode.SUBMASTER
            s._submaster_targets = lambda st: ([1], {})
            s.value = 200
        finally:
            om.set_submaster = orig
            om.clear_submaster(id(s))
        self.assertTrue(calls)
        self.assertIsNone(calls[-1][1].get("heads"))


# ── 6. Regressionen aus der adversarialen Review ─────────────────────────────

def _zone_master_channels():
    """„Zonen-Master"-Profil nach Vorbild `Frost FX Bar W` / `Spiider (4) Full
    RGBW`: 4 faerbbare Koepfe, aber NUR 2 `intensity`-Kanaele — und die sind
    Zonen-Master ueber ALLE Koepfe, keine Kopf-Dimmer."""
    chans = [_Ch("intensity", 1), _Ch("intensity", 2)]      # Zone A / Zone B
    n = 3
    for _head in range(4):
        for attr in ("color_r", "color_g", "color_b"):
            chans.append(_Ch(attr, n))
            n += 1
    return chans                     # 1,2 = Zonen-Master · 3..14 = 4x RGB


class TestZoneMasterNotMistakenForHead(unittest.TestCase):
    """★ Review-Fund (HIGH, bestaetigt an 107 Modi der echten Library): die Regel
    „Attribut kommt mehrfach vor ⇒ pro Kopf" ist FALSCH. Ein wiederholtes Attribut
    ist nur dann kopf-exklusiv, wenn es GENAU SO OFT vorkommt wie es Koepfe gibt."""

    def setUp(self):
        self.st = AppState.__new__(AppState)
        self.fx = _Fx(1, 1, 1)
        self.chans = _zone_master_channels()

    def test_zone_masters_are_not_head_channels(self):
        m = self.st._fixture_head_intensity_addr_map(self.fx, self.chans)
        for h, addrs in m.items():
            self.assertNotIn(1, addrs, f"Zonen-Master A darf nicht zu Kopf {h} gehoeren")
            self.assertNotIn(2, addrs, f"Zonen-Master B darf nicht zu Kopf {h} gehoeren")

    def test_every_head_keeps_its_own_colors(self):
        # Ohne den Fix haetten Kopf 0/1 die beiden Zonen-Master erwischt UND ihre
        # eigenen Farben verloren (`return inten if inten else color`).
        m = self.st._fixture_head_intensity_addr_map(self.fx, self.chans)
        self.assertEqual(m, {0: [3, 4, 5], 1: [6, 7, 8],
                             2: [9, 10, 11], 3: [12, 13, 14]})

    def test_matching_count_still_counts_as_per_head(self):
        # Gegenprobe: 4 Koepfe UND 4 Dimmer -> die Dimmer SIND kopf-exklusiv.
        chans = []
        n = 1
        for _h in range(4):
            chans.append(_Ch("intensity", n)); n += 1
            chans.append(_Ch("color_r", n)); n += 1
        m = self.st._fixture_head_intensity_addr_map(_Fx(1, 1, 1), chans)
        self.assertEqual(m, {0: [1], 1: [3], 2: [5], 3: [7]})

    def test_single_head_gives_empty_map(self):
        chans = [_Ch("intensity", 1), _Ch("color_r", 2)]
        self.assertEqual(self.st._fixture_head_intensity_addr_map(_Fx(1, 1, 1), chans), {})

    def test_laser_never_gets_a_head_map(self):
        fx = _Fx(1, 1, 1)
        fx.fixture_type = "laser"
        self.assertEqual(
            self.st._fixture_head_intensity_addr_map(fx, _hydra_channels()), {},
            "Laser ist per color_head_count einkoepfig — keine Adressrechnung")

    def test_single_head_accessor_matches_map(self):
        for h in range(4):
            self.assertEqual(
                self.st._fixture_head_intensity_addrs(self.fx, self.chans, h),
                self.st._fixture_head_intensity_addr_map(self.fx, self.chans)[h])


class _FxWithChannels:
    def __init__(self, fid, chans, ftype=""):
        self.fid = fid
        self.universe = 1
        self.address = 1
        self.fixture_type = ftype
        self._chans = chans


class TestValidateHeadRestrictions(unittest.TestCase):
    """★ Review-Fund (HIGH, bestaetigt an 317 Modi): die beim Patchen automatisch
    angelegte Gruppe „… · Koepfe" enthaelt ALLE Koepfe. Ein BESTEHENDER Fader mit
    Reichweite = dieser Gruppe haette sonst den geraeteweiten Faktor verloren und
    damit den geteilten Master-Dimmer nicht mehr gedimmt."""

    def setUp(self):
        import src.core.app_state as mod
        self.mod = mod
        self.st = AppState.__new__(AppState)
        self._fx = {}
        self.st.get_patched_fixtures = lambda: list(self._fx.values())
        orig = mod.get_channels_for_patched
        mod.get_channels_for_patched = lambda f: getattr(f, "_chans", [])
        self.addCleanup(lambda: setattr(mod, "get_channels_for_patched", orig))

    def _patch(self, fid, chans, ftype=""):
        self._fx[fid] = _FxWithChannels(fid, chans, ftype)

    def test_all_heads_falls_back_to_whole_device(self):
        self._patch(1, _hydra_channels())                  # 4 Koepfe
        self.assertEqual(self.st.validate_head_restrictions({1: {0, 1, 2, 3}}), {},
                         "alle Koepfe = ganzes Geraet -> Bestandspfad")

    def test_partial_heads_are_kept(self):
        self._patch(1, _hydra_channels())
        self.assertEqual(self.st.validate_head_restrictions({1: {0, 2}}), {1: {0, 2}})

    def test_stale_head_indices_after_mode_change_are_clamped(self):
        # Gruppe wurde fuer 4 Koepfe angelegt, das Geraet hat jetzt 2 ->
        # Koepfe 2/3 gibt es nicht mehr; 0/1 waeren ALLE -> ganzes Geraet.
        self._patch(1, _per_head_dimmer_channels())        # 2 Koepfe
        self.assertEqual(self.st.validate_head_restrictions({1: {0, 1, 2, 3}}), {})

    def test_only_stale_heads_left_drops_the_fixture(self):
        self._patch(1, _per_head_dimmer_channels())        # 2 Koepfe
        self.assertEqual(self.st.validate_head_restrictions({1: {2, 3}}), {},
                         "nur ungueltige Koepfe -> zurueck auf ganzes Geraet, "
                         "statt still wirkungslos zu werden")

    def test_single_head_fixture_dropped(self):
        self._patch(1, [_Ch("intensity", 1), _Ch("color_r", 2)])
        self.assertEqual(self.st.validate_head_restrictions({1: {0}}), {})

    def test_laser_dropped(self):
        self._patch(1, _hydra_channels(), ftype="laser")
        self.assertEqual(self.st.validate_head_restrictions({1: {0, 1}}), {})

    def test_unpatched_fid_dropped(self):
        self.assertEqual(self.st.validate_head_restrictions({99: {0}}), {})

    def test_empty_and_garbage(self):
        self._patch(1, _hydra_channels())
        self.assertEqual(self.st.validate_head_restrictions({}), {})
        self.assertEqual(self.st.validate_head_restrictions(None), {})
        self.assertEqual(self.st.validate_head_restrictions({1: {"x", 0}}), {1: {0}})

    def test_mixed_devices(self):
        self._patch(1, _hydra_channels())                  # 4 Koepfe
        self._patch(2, _hydra_channels())
        self.assertEqual(
            self.st.validate_head_restrictions({1: {0, 1, 2, 3}, 2: {1}}), {2: {1}})


class TestAutoHeadGroupIsNoRegression(unittest.TestCase):
    """End-to-end: ein Fader auf der Auto-Kopf-Gruppe muss GENAU so dimmen wie vor
    dem Branch — ueber den geteilten Master-Dimmer, nicht ueber die Kopf-Farben."""

    def test_full_head_group_dims_shared_master_like_before(self):
        st_new = _make_state_hydra()
        # Was die VC nach der Validierung liefert: {} (alle Koepfe = ganzes Geraet).
        st_new.output_manager.set_submaster("s", 0.5, [1], heads=None)
        st_new._render_frame(0.02)
        after = [st_new.universes[1].get_channel(a) for a in range(1, 14)]
        self.assertAlmostEqual(after[0], 127, delta=1,
                               msg="geteilter Master-Dimmer MUSS weiter gedimmt werden")
        self.assertEqual(after[1:], [255] * 12)


class TestHeadSubmasterEarlyOut(unittest.TestCase):
    """Ohne Kopf-Slot darf der Renderer submaster_head_factors_for gar nicht rufen."""

    def test_flag_false_without_head_slots(self):
        om = OutputManager()
        self.assertFalse(om.has_head_submasters())
        om.set_submaster("a", 0.5)
        om.set_submaster("b", 0.5, [1])
        self.assertFalse(om.has_head_submasters())

    def test_flag_true_with_head_slot_and_cleared_again(self):
        om = OutputManager()
        om.set_submaster("h", 0.5, [1], heads={1: {0}})
        self.assertTrue(om.has_head_submasters())
        om.clear_submaster("h")
        self.assertFalse(om.has_head_submasters())

    def test_renderer_skips_head_lookup_entirely(self):
        st = _make_state_hydra()
        calls = []
        st.output_manager.submaster_head_factors_for = lambda fid: calls.append(fid) or {}
        st.output_manager.set_submaster("s", 0.5, [1])      # KEIN Kopf-Slot
        st._render_frame(0.02)
        self.assertEqual(calls, [], "Bestandsfall darf keinen Kopf-Lookup kosten")


class TestBaseFidsFromCells(unittest.TestCase):
    def test_matches_grid_order_variant(self):
        from src.core.group_cells import base_fids_in_cells, base_fids_in_grid_order
        pos = {"0,0": "5:0", "1,0": "5:1", "0,1": 7, "1,1": "5:2"}
        self.assertEqual(base_fids_in_cells(cells_in_grid_order(pos)),
                         base_fids_in_grid_order(pos),
                         "eine Gruppen-Abfrage muss dieselben fids liefern wie zwei")

    def test_dedup_and_order(self):
        from src.core.group_cells import base_fids_in_cells
        self.assertEqual(base_fids_in_cells(["3:1", "3:0", "1", "x"]), [3, 1])
        self.assertEqual(base_fids_in_cells([]), [])
        self.assertEqual(base_fids_in_cells(None), [])


if __name__ == "__main__":
    unittest.main()

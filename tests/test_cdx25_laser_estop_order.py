"""CDX-25: NOT-AUS-Reihenfolge und Sichtbarkeit des DMX-Latch-Fehlers.

Der Codex-Befund („VC-Button ‚Laser NOT-AUS' latcht den DMX-Laser NICHT") ist ein
**False-Positive**: `LaserOutputManager.estop_all()` ruft selbst
`AppState.set_laser_estop(True)`, und `clear_estop_all()` hebt den Latch NICHT
wieder auf — der Button wirkt also global (Netzwerk **und** DMX). Beim Verifizieren
fielen aber drei echte Lücken auf, die dieser Test festnagelt:

1. **Reihenfolge (Safety):** Der DMX-Latch wurde ERST NACH der Netzwerk-I/O-Schleife
   gesetzt. `conn.estop()` ist ein Socket-Roundtrip mit ``timeout=0.5`` je Verbindung
   (`etherdream.py`, `idn.py`) — bei nur einem unerreichbaren DAC blieben DMX-Laser
   0,5 s pro Gerät weiter hell, obwohl der Nutzer NOT-AUS gedrückt hat. Fail-safe ist
   die billige lokale Verriegelung ZUERST (gleiche Asymmetrie wie CDX-12).
2. **Stiller Fehler:** Ein `except Exception: pass` um genau diese Verriegelung liess
   einen fehlgeschlagenen NOT-AUS wie einen erfolgreichen aussehen.
3. **Kein End-to-End-Netz:** `tests/test_laser_vc_safety.py` prüft den VC-Button nur
   gegen einen Fake-Manager — die Kopplung Button → echter Manager → DMX-Latch war
   nirgends abgedeckt.
"""
import io
import os
import threading
import types
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.laser.laser_output import LaserOutputManager


class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""                      # leer = normaler DMX-Ausgang

    def __init__(self, fid, universe, address, ftype=""):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.fixture_type = ftype


class _FM:
    def tick(self, universes, patch_cache, dt):
        pass


_LASER = _Fx(7, 1, 10, ftype="laser")

_CHANNELS = {
    7: [_Ch("laser_bank", 1), _Ch("gobo_wheel", 2),
        _Ch("laser_x", 3), _Ch("shutter", 4)],
}


def _make_state():
    """Minimal-AppState mit echtem `set_laser_estop`/Render-Plan (wie in
    tests/test_laser_dmx_estop.py) — kein Fake-State, damit die Kopplung
    Manager → AppState wirklich geprüft wird."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = _FM()
    st._patch_cache = [_LASER]
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._rebuild_render_plan()
    return st


class _SlowConn:
    """Fake-Verbindung, die beim NOT-AUS den Latch-Zustand mitschreibt — so wird
    die REIHENFOLGE beobachtbar, ohne auf echte Socket-Timeouts zu warten."""

    def __init__(self, state):
        self._state = state
        self.latch_at_estop = None
        self.estop_calls = 0
        self.closed = False

    def estop(self):
        self.estop_calls += 1
        self.latch_at_estop = bool(self._state.laser_estop_active)

    def clear_estop(self):
        pass

    def close(self):
        self.closed = True


class EstopOrderTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        self.st = _make_state()
        self.lo = LaserOutputManager(self.st)

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def test_dmx_latch_is_set_before_network_io(self):
        """Kernregression: beim ersten `conn.estop()` MUSS der DMX-Latch schon
        stehen. Auf dem alten Code (Latch nach der Schleife) ist das False."""
        conn = _SlowConn(self.st)
        self.lo._connections = {7: conn}

        self.lo.estop_all()

        self.assertEqual(conn.estop_calls, 1, "Netzwerk-Estop lief")
        self.assertTrue(
            conn.latch_at_estop,
            "DMX-Latch muss VOR der Netzwerk-I/O stehen — sonst bleiben DMX-Laser "
            "bis zum Socket-Timeout jedes unerreichbaren DACs hell")

    def test_latch_is_set_even_if_network_estop_raises(self):
        """Ein hängender/kaputter DAC darf die DMX-Verriegelung nicht verhindern."""
        class _Boom(_SlowConn):
            def estop(self):
                super().estop()
                raise OSError("DAC weg")

        conn = _Boom(self.st)
        self.lo._connections = {7: conn}

        self.lo.estop_all()

        self.assertTrue(self.st.laser_estop_active)
        self.assertTrue(conn.latch_at_estop)
        self.assertTrue(conn.closed, "kaputte Verbindung wird geschlossen")

    def test_latch_failure_is_reported_and_network_estop_still_runs(self):
        """Schlägt die DMX-Verriegelung fehl, darf das nicht still verschluckt
        werden — und die zweite Safety-Ebene (Netzwerk) läuft trotzdem."""
        def _boom(active):
            raise RuntimeError("kaputt")

        self.st.set_laser_estop = _boom
        conn = _SlowConn(self.st)
        self.lo._connections = {7: conn}

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.lo.estop_all()

        self.assertIn("NOT-AUS", buf.getvalue())
        self.assertIn("kaputt", buf.getvalue())
        self.assertEqual(conn.estop_calls, 1,
                         "Netzwerk-Estop läuft trotz Latch-Fehler")

    def test_estop_forces_laser_channels_dark_after_estop_all(self):
        """Ende-zu-Ende über den Renderer: nach estop_all() liegt der Laser dunkel."""
        self.st.programmer = {7: {"laser_bank": 100, "gobo_wheel": 55}}
        self.st._render_frame(0.02)
        self.assertEqual(self.st.universes[1].get_channel(10), 100)

        self.lo.estop_all()
        self.st._render_frame(0.02)
        for addr in (10, 11, 12, 13):
            self.assertEqual(self.st.universes[1].get_channel(addr), 0)

    def test_clear_estop_all_does_not_release_dmx_latch(self):
        """Die im Backlog-Item vermutete Lücke gibt es NICHT — hier festgenagelt,
        damit sie nicht versehentlich eingebaut wird: `clear_estop_all()` öffnet
        nur die Netzwerk-Session wieder, der DMX-Latch bleibt verriegelt."""
        self.lo._connections = {7: _SlowConn(self.st)}
        self.lo.estop_all()
        self.assertTrue(self.st.laser_estop_active)

        self.lo.clear_estop_all()

        self.assertTrue(
            self.st.laser_estop_active,
            "clear_estop_all darf den DMX-Latch NICHT lösen — nur ein bewusster "
            "emissions-relevanter Programmer-Wert (A3D-02) entriegelt")


class VcButtonEndToEndTest(unittest.TestCase):
    """Der VC-Button gegen den ECHTEN Manager (bisher nur Fake-Manager getestet)."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._orig_ch = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: _CHANNELS[fx.fid]
        self.st = _make_state()
        self.lo = LaserOutputManager(self.st)
        self.st.ensure_laser_output = lambda: self.lo
        self._orig_get_state = A.get_state
        A.get_state = lambda: self.st

    def tearDown(self):
        A.get_channels_for_patched = self._orig_ch
        A.get_state = self._orig_get_state

    def test_vc_estop_button_latches_dmx_laser(self):
        from src.ui.virtualconsole.vc_button import VCButton, ButtonAction

        btn = VCButton()
        btn.action = ButtonAction.LASER_ESTOP
        btn.function_id = None
        btn._trigger_primary(True)

        self.assertTrue(
            self.st.laser_estop_active,
            "der VC-NOT-AUS muss auch DMX-Laser verriegeln — die komplette "
            "Sequenz estop_all/set_armed(False)/clear_estop_all darf den Latch "
            "am Ende nicht wieder aufheben")
        self.assertFalse(self.lo.armed, "Netzwerk-Ausgang bleibt unscharf")


if __name__ == "__main__":
    unittest.main()

"""WEB-QA (+ WEB-02/03/04): Web-Remote-Regressionstests.

Der Web-Remote (`src/web/app.py`) ist ein externer Steuer-Eingang (rohe DMX-Kanäle,
GO/Back/Blackout/Fader) und hatte 0 Tests. Diese Suite nagelt fest:
- Clamping (Fader 0..1, Kanal 0..255),
- Bereichs-Guards (out-of-range slot/universe/channel = No-op, slot=0 kein Wraparound),
- Payload-Fehlertoleranz (nicht-numerisch -> kein HTTP 500 / Handler-Crash) [WEB-02],
- SocketIO-Handler ohne Payload (kein AttributeError) [WEB-03],
- Routing (GO/Back/Blackout/Fader/clear an die richtigen Ziele), leerer Cue-Stack.

`get_state` ist gemockt -> kein echter AppState/OutputManager/DMX.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import src.web.app as webapp


class _FakeExecutor:
    def __init__(self):
        self.fader_value = None
        self.presses = []

    def press_btn(self, btn):
        self.presses.append(btn)


class _FakeUniverse:
    def __init__(self):
        self.channels = {}

    def set_channel(self, ch, val):
        self.channels[ch] = val


class _FakeCueStack:
    def __init__(self, name="Main"):
        self.name = name
        self.cues = []
        self.actions = []

    def go(self):
        self.actions.append("go")

    def back(self):
        self.actions.append("back")

    def stop(self):
        self.actions.append("stop")


class _FakeOM:
    def __init__(self):
        self.blackout = None

    def set_blackout(self, enabled):
        self.blackout = enabled


class _FakeState:
    def __init__(self):
        self.playback_engine = mock.Mock()
        self.executors = [_FakeExecutor(), _FakeExecutor()]
        self.playback_engine.executors = self.executors
        self.universes = {1: _FakeUniverse()}
        self.cue_stacks = [_FakeCueStack()]
        self.output_manager = _FakeOM()
        self.mock_mode = True
        self.cleared = 0

    def get_patched_fixtures(self):
        return [object(), object()]

    def clear_programmer(self):
        self.cleared += 1


@unittest.skipUnless(HAS_FLASK, "Flask/flask-socketio nicht installiert")
class TestWebRemote(unittest.TestCase):
    def setUp(self):
        self.state = _FakeState()
        self._orig_get_state = webapp._get_state
        webapp._get_state = lambda: self.state
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        webapp._get_state = self._orig_get_state

    # ── Clamping ──────────────────────────────────────────────────────────────
    def test_fader_clamps_high(self):
        self.client.post("/api/executor/1/fader", json={"level": 5.0})
        self.assertEqual(self.state.executors[0].fader_value, 1.0)

    def test_fader_clamps_low(self):
        self.client.post("/api/executor/1/fader", json={"level": -3.0})
        self.assertEqual(self.state.executors[0].fader_value, 0.0)

    def test_channel_clamps(self):
        self.client.post("/api/channel/1/10", json={"value": 999})
        self.assertEqual(self.state.universes[1].channels[10], 255)

    # ── Bereichs-Guards (No-op, kein IndexError/Wraparound) ───────────────────
    def test_fader_out_of_range_slot_is_noop(self):
        r = self.client.post("/api/executor/99/fader", json={"level": 0.5})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.state.executors[0].fader_value)
        self.assertIsNone(self.state.executors[1].fader_value)

    def test_fader_slot_zero_no_wraparound(self):
        # slot=0 -> idx=-1: muss durch 0<=idx geblockt werden (nicht auf executors[-1] schreiben)
        r = self.client.post("/api/executor/0/fader", json={"level": 0.5})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.state.executors[-1].fader_value)

    def test_channel_out_of_range_is_noop(self):
        self.client.post("/api/channel/1/999", json={"value": 100})   # channel > 512
        self.client.post("/api/channel/9/10", json={"value": 100})    # universe fehlt
        self.assertEqual(self.state.universes[1].channels, {})

    # ── Payload-Fehlertoleranz (WEB-02: kein HTTP 500) ────────────────────────
    def test_fader_non_numeric_payload_no_500(self):
        for bad in ("abc", None, [1]):
            r = self.client.post("/api/executor/1/fader", json={"level": bad})
            self.assertEqual(r.status_code, 200, f"level={bad!r} sollte kein 500 sein")

    def test_channel_non_numeric_payload_no_500(self):
        r = self.client.post("/api/channel/1/10", json={"value": "xyz"})
        self.assertEqual(r.status_code, 200)
        # Default 0 -> geschrieben (0 ist gültig)
        self.assertEqual(self.state.universes[1].channels.get(10), 0)

    # ── Routing ───────────────────────────────────────────────────────────────
    def test_go_routes_to_first_cuestack(self):
        self.client.post("/api/go")
        self.assertEqual(self.state.cue_stacks[0].actions, ["go"])

    def test_back_routes_to_first_cuestack(self):
        self.client.post("/api/back")
        self.assertEqual(self.state.cue_stacks[0].actions, ["back"])

    def test_blackout_routes_to_output_manager(self):
        self.client.post("/api/blackout", json={"enabled": True})
        self.assertTrue(self.state.output_manager.blackout)

    def test_exec_go_routes_to_executor(self):
        self.client.post("/api/executor/1/go")
        self.assertEqual(self.state.executors[0].presses, ["go"])

    def test_clear_routes_to_programmer(self):
        self.client.post("/api/programmer/clear")
        self.assertEqual(self.state.cleared, 1)

    def test_go_with_empty_cuestacks_is_noop(self):
        self.state.cue_stacks = []
        r = self.client.post("/api/go")
        self.assertEqual(r.status_code, 200)

    def test_status_ok(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["fixtures"], 2)

    # ── STOP-Route + Fader-Initial-Sync (Bug-Fixes 2026-07-09) ────────────────
    def test_stop_routes_to_first_cuestack(self):
        """Bug: STOP im Web-Remote rief die tote Route /api/executor/1/back auf
        (stiller 404). Jetzt existiert /api/stop und stoppt die Cueliste."""
        r = self.client.post("/api/stop")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.state.cue_stacks[0].actions, ["stop"])

    def test_stop_with_empty_cuestacks_is_noop(self):
        self.state.cue_stacks = []
        r = self.client.post("/api/stop")
        self.assertEqual(r.status_code, 200)

    def test_status_includes_executor_fader_values(self):
        """Bug: das Remote-UI initialisierte alle Fader hart auf 100%. /api/status
        liefert jetzt die ECHTEN Executor-Fader, damit das UI synchronisieren kann."""
        self.state.executors[0].fader_value = 0.5
        self.state.executors[1].fader_value = 0.25
        data = self.client.get("/api/status").get_json()
        self.assertIn("executors", data)
        self.assertEqual(data["executors"][:2], [0.5, 0.25])

    # ── SocketIO (WEB-03: ohne Payload kein Crash) ────────────────────────────
    def test_socketio_fader_without_payload_no_crash(self):
        sio_client = self.sio.test_client(self.app)
        self.assertTrue(sio_client.is_connected())
        # Emit OHNE Payload -> Handler bekommt data=None -> darf nicht crashen.
        sio_client.emit("fader")
        sio_client.emit("blackout")
        # Und mit gültigem Payload wirkt es:
        sio_client.emit("fader", {"slot": 1, "level": 0.5})
        self.assertEqual(self.state.executors[0].fader_value, 0.5)
        sio_client.disconnect()

    def test_socketio_fader_bad_payload_no_crash(self):
        sio_client = self.sio.test_client(self.app)
        sio_client.emit("fader", {"slot": "x", "level": "y"})   # nicht-numerisch
        # Kein Crash; Default slot=1/level=1.0 -> executors[0] = 1.0
        self.assertEqual(self.state.executors[0].fader_value, 1.0)
        sio_client.disconnect()

    def test_socketio_stop_routes_to_cuestack(self):
        """Das Frontend nutzt socket.emit('stop') -> Handler muss die Cueliste
        stoppen (und darf ohne Payload nicht crashen)."""
        sio_client = self.sio.test_client(self.app)
        sio_client.emit("stop")
        self.assertEqual(self.state.cue_stacks[0].actions, ["stop"])
        sio_client.disconnect()


class TestLanIpHelper(unittest.TestCase):
    """NET-02: Der Verbindungs-Dialog soll die echte LAN-IP statt ``localhost``
    zeigen. Diese Tests decken die IP-Ermittlung ab — inkl. Fallback bei
    fehlendem Netz (kein Crash)."""

    def test_get_lan_ip_returns_plausible_ipv4(self):
        ip = webapp.get_lan_ip()
        self.assertIsInstance(ip, str)
        parts = ip.split(".")
        self.assertEqual(len(parts), 4, f"keine IPv4: {ip!r}")
        for p in parts:
            self.assertTrue(p.isdigit(), f"nicht-numerisches Oktett in {ip!r}")
            self.assertTrue(0 <= int(p) <= 255, f"Oktett out-of-range in {ip!r}")

    def test_get_lan_ip_no_network_falls_back_to_loopback(self):
        # Kein Interface / kein Netz -> connect wirft OSError -> Fallback 127.0.0.1
        with mock.patch("socket.socket") as m_sock:
            m_sock.return_value.connect.side_effect = OSError("network down")
            self.assertEqual(webapp.get_lan_ip(), "127.0.0.1")

    def test_get_lan_ip_uses_getsockname(self):
        with mock.patch("socket.socket") as m_sock:
            inst = m_sock.return_value
            inst.getsockname.return_value = ("192.168.42.7", 12345)
            self.assertEqual(webapp.get_lan_ip(), "192.168.42.7")
            inst.close.assert_called_once()

    def test_remote_url_builds_lan_url_with_port(self):
        with mock.patch.object(webapp, "get_lan_ip", return_value="10.0.0.5"):
            self.assertEqual(webapp.remote_url(5000), "http://10.0.0.5:5000")
            self.assertEqual(webapp.remote_url(8080), "http://10.0.0.5:8080")

    def test_remote_url_never_shows_localhost_when_lan_present(self):
        with mock.patch.object(webapp, "get_lan_ip", return_value="172.16.3.9"):
            self.assertNotIn("localhost", webapp.remote_url())


if __name__ == "__main__":
    unittest.main()

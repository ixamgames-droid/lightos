"""NET-01/NET-03: Token-Auth fuer das Web-Remote + OSC-Loopback-Default.

Der Web-Server bindet weiter 0.0.0.0 (sonst sperrt er das Handy aus), ist aber
durch ein pro Setup persistiertes Token geschuetzt: ein ``@before_request``-Gate
weist alle Routen ausser der Allowlist ('/', statische Assets) mit 403 ab, wenn
die Session nicht authentisiert ist. Die '/'-Route macht den Handshake
(``?k=<token>`` per constant-time-Vergleich). Der SocketIO-connect lehnt
unauthentisierte Verbindungen ab.

OSC (ungeschuetztes UDP) bindet per Default nur an 127.0.0.1.

``LIGHTOS_PREFS_DIR`` -> Temp, damit der Token-Store nicht die echten Nutzer-Prefs
beruehrt. ``get_state`` ist gemockt.
"""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem App-Import auf ein Temp-Prefs-Verzeichnis umlenken (Token-Persistenz).
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_")

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import src.web.app as webapp


class _FakeState:
    def get_patched_fixtures(self):
        return []

    universes = {}
    mock_mode = True

    def __getattr__(self, name):
        # /api/status greift auf diverse Felder zu; fuer den Auth-Test genuegt ein
        # nachsichtiger Stub (jede unbekannte Eigenschaft -> leere Liste/Objekt).
        return []


@unittest.skipUnless(HAS_FLASK, "Flask/flask-socketio nicht installiert")
class TestRemoteAuth(unittest.TestCase):
    def setUp(self):
        self._orig_get_state = webapp._get_state
        webapp._get_state = lambda: _FakeState()
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "geheim123"
        self.client = self.app.test_client()

    def tearDown(self):
        webapp._get_state = self._orig_get_state

    # (a) /api/* ohne Session -> 403
    def test_api_without_session_is_403(self):
        r = self.client.post("/api/go")
        self.assertEqual(r.status_code, 403)
        r2 = self.client.get("/api/status")
        self.assertEqual(r2.status_code, 403)

    # (b) '/?k=<richtig>' -> authed, danach /api/* erlaubt
    def test_handshake_then_api_allowed(self):
        r = self.client.get("/?k=geheim123")
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post("/api/go")
        self.assertEqual(r2.status_code, 200)

    # (c) falsches k -> weiter 403
    def test_wrong_token_stays_403(self):
        r = self.client.get("/?k=falsch")
        self.assertEqual(r.status_code, 200)   # '/' rendert immer
        r2 = self.client.post("/api/go")
        self.assertEqual(r2.status_code, 403)  # aber nicht authed

    def test_index_allowlisted_without_token(self):
        # '/' selbst ist immer erreichbar (macht ja den Handshake).
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)

    def test_socketio_rejects_unauthed_connection(self):
        # Ohne authentisierte Flask-Session lehnt der connect-Handler ab.
        sio_client = self.sio.test_client(self.app, flask_test_client=self.client)
        self.assertFalse(sio_client.is_connected())

    def test_socketio_accepts_authed_connection(self):
        self.client.get("/?k=geheim123")   # Session authentisieren
        sio_client = self.sio.test_client(self.app, flask_test_client=self.client)
        self.assertTrue(sio_client.is_connected())
        sio_client.disconnect()

    # (d) OSC-Default-ip ist 127.0.0.1
    def test_osc_default_bind_is_loopback(self):
        from src.core.osc.osc_server import OscServer
        srv = OscServer()
        self.assertEqual(srv._ip, "127.0.0.1")

    def test_osc_set_bind_ip_switches_to_all(self):
        from src.core.osc.osc_server import OscServer
        srv = OscServer()
        srv.set_bind_ip("0.0.0.0")
        self.assertEqual(srv._ip, "0.0.0.0")


@unittest.skipUnless(HAS_FLASK, "Flask/flask-socketio nicht installiert")
class TestCorsAllowlist(unittest.TestCase):
    """NET-03: konkrete Origin-Allowlist statt '*'."""

    def test_allowlist_is_list_not_star(self):
        origins = webapp.cors_allowlist(5000, lan_ip="192.168.1.5")
        self.assertIsInstance(origins, list)
        self.assertNotIn("*", origins)
        self.assertIn("http://192.168.1.5:5000", origins)
        self.assertIn("http://127.0.0.1:5000", origins)
        self.assertIn("http://localhost:5000", origins)

    def test_allowlist_no_duplicate_when_lan_is_loopback(self):
        origins = webapp.cors_allowlist(5000, lan_ip="127.0.0.1")
        self.assertEqual(origins.count("http://127.0.0.1:5000"), 1)

    def test_create_app_config_has_list_origins(self):
        _orig = webapp._get_state
        webapp._get_state = lambda: _FakeState()
        try:
            app, _sio = webapp.create_app(5000)
            origins = app.config.get("CORS_ALLOWED_ORIGINS")
            self.assertIsInstance(origins, list)
            self.assertNotEqual(origins, "*")
        finally:
            webapp._get_state = _orig


@unittest.skipUnless(HAS_FLASK, "Flask/flask-socketio nicht installiert")
class TestRemoteSettings(unittest.TestCase):
    """NET-01: Token-Persistenz + Toggles."""

    def test_token_persists_and_reused(self):
        from src.web import remote_settings
        t1 = remote_settings.get_token()
        t2 = remote_settings.get_token()
        self.assertTrue(t1)
        self.assertEqual(t1, t2)   # Neustart-stabil (gleiche Datei)

    def test_regenerate_changes_token(self):
        from src.web import remote_settings
        t1 = remote_settings.get_token()
        t2 = remote_settings.regenerate_token()
        self.assertNotEqual(t1, t2)
        self.assertEqual(remote_settings.get_token(), t2)

    def test_toggles_default_and_roundtrip(self):
        from src.web import remote_settings
        self.assertTrue(remote_settings.is_lan_remote_enabled())    # Default AN
        self.assertFalse(remote_settings.is_osc_network_enabled())  # Default AUS
        remote_settings.set_lan_remote_enabled(False)
        self.assertFalse(remote_settings.is_lan_remote_enabled())
        remote_settings.set_lan_remote_enabled(True)
        remote_settings.set_osc_network_enabled(True)
        self.assertTrue(remote_settings.is_osc_network_enabled())
        remote_settings.set_osc_network_enabled(False)


if __name__ == "__main__":
    unittest.main()

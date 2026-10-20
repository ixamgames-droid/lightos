"""WEB-12: Sicherheits-Korrekturen der Handy-Konsole aus dem Bedientest QA-96 —
Teil Web-Server.

* **Rechte-Matrix (QA96-04/20):** zwei Schluesselarten. Der Schluessel der
  Handy-Konsole oeffnet nur die Handy-Konsole, der der festen Fernbedienung nur
  die feste Seite — und die nur, solange sie unter „Erweitert“ eingeschaltet
  ist; Roh-DMX hat einen eigenen Schalter. Je Route UND je Socket-Ereignis.
* **Ungueltige Fern-Anfragen (QA96-17)** aendern nichts und antworten mit
  Fehler — kein „heller“ Standardwert mehr.
* **Blackout:** von fern wird nie ein Blackout aufgehoben, den nicht dieses
  Geraet gesetzt hat.
* **Schluessel nie im Log (QA96-03):** echter Server auf 127.0.0.1 mit freiem
  Port, Anfrage mit ``?k=…``, Diagnosepaket bauen und durchsuchen.
* **Vorgaben (QA96-36):** LAN, feste Seite, Roh-DMX und Laser ab Werk aus.

Keine echten App-Daten: Einstellungen in einem Wegwerf-Ordner, ``get_state``
wo moeglich durch einen Stub ersetzt.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web12_")

from src.web import remote_settings  # noqa: E402

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import src.web.app as webapp  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KONSOLE_K = "konsoleK1"
FEST_K = "festeK22"


class _Ex:
    def __init__(self):
        self.fader_value = 0.25
        self.presses = []
        self.stack = None

    def press_btn(self, was):
        self.presses.append(was)


class _Universe:
    def __init__(self):
        self.channels = {}


class _Stack:
    name = "Liste"

    def __init__(self):
        self.cues = []
        self.aktionen = []

    def go(self):
        self.aktionen.append("go")

    def back(self):
        self.aktionen.append("back")

    def stop(self):
        self.aktionen.append("stop")


class _OM:
    GM_LASER_AUS_SCHWELLE = 0.01

    def __init__(self):
        self._bo = False
        self.blackout_epoch = 0
        self.grand_master = 1.0

    @property
    def blackout(self):
        return self._bo

    @property
    def blackout_schalter(self):
        return self._bo

    def set_blackout(self, an):
        if bool(an) != self._bo:
            self.blackout_epoch += 1
        self._bo = bool(an)

    def set_grand_master(self, v):
        self.grand_master = max(0.0, min(1.0, float(v)))


class _State:
    def __init__(self):
        import types
        self.executors = [_Ex(), _Ex()]
        self.playback_engine = types.SimpleNamespace(executors=self.executors)
        self.universes = {1: _Universe()}
        self.cue_stacks = [_Stack()]
        self.output_manager = _OM()
        self.mock_mode = True
        self.geleert = 0
        self.kanaele = []
        self._laser_fids = frozenset()
        self._laser_estop_addrs = {}

    def get_patched_fixtures(self):
        return []

    def set_input_channel(self, u, c, v, source="web"):
        self.kanaele.append((u, c, v))

    def clear_programmer(self):
        self.geleert += 1


#: Fuer jede Route ein Aufruf, der bei gegebenem Recht etwas Gueltiges tut.
AUFRUFE = {
    "/api/status": ("get", "/api/status", None),
    "/api/go": ("post", "/api/go", None),
    "/api/back": ("post", "/api/back", None),
    "/api/stop": ("post", "/api/stop", None),
    "/api/blackout": ("post", "/api/blackout", {"enabled": True}),
    "/api/executor/<int:slot>/fader": ("post", "/api/executor/1/fader", {"level": 0.5}),
    "/api/executor/<int:slot>/go": ("post", "/api/executor/1/go", None),
    "/api/programmer/clear": ("post", "/api/programmer/clear", None),
    "/api/channel/<int:universe>/<int:channel>": ("post", "/api/channel/1/5", {"value": 9}),
    "/api/vc/widgets": ("get", "/api/vc/widgets", None),
    "/api/vc/widget/<kennung>/aktion": ("post", "/api/vc/widget/wabcdef/aktion",
                                        {"aktion": "umschalten"}),
    "/api/vc/konsole": ("get", "/api/vc/konsole", None),
    "/api/vc/pult": ("post", "/api/vc/pult", {"gm": 200}),
}

#: Schluesselarten der Matrix: (Name, Schluessel, feste Seite an, Roh-DMX an)
ARTEN = (
    ("ohne", None, True, True),
    ("konsole", KONSOLE_K, True, True),
    ("fest_aus", FEST_K, False, False),
    ("fest", FEST_K, True, False),
    ("fest_roh", FEST_K, True, True),
)

ERWARTET = {      # Art -> Rechte, die sie haben muss
    "ohne": set(),
    "konsole": {"konsole"},
    "fest_aus": set(),
    "fest": {"fest"},
    "fest_roh": {"fest", "roh_dmx"},
}


@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class _Basis(unittest.TestCase):
    def setUp(self):
        self.state = _State()
        self._alt = webapp._get_state
        webapp._get_state = lambda: self.state
        self.addCleanup(setattr, webapp, "_get_state", self._alt)
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = KONSOLE_K
        self.app.config["LIGHTOS_FESTE_TOKEN"] = FEST_K
        remote_settings.set_vc_remote_enabled(True)
        for aus in (remote_settings.set_vc_remote_enabled,
                    remote_settings.set_feste_seite_enabled,
                    remote_settings.set_roh_dmx_enabled,
                    remote_settings.set_laser_vom_handy):
            self.addCleanup(aus, False)
        from src.web import fern_pult
        fern_pult.vergessen()
        self.addCleanup(fern_pult.vergessen)

    def _client(self, schluessel=None, fest=False, roh=False):
        remote_settings.set_feste_seite_enabled(fest)
        remote_settings.set_roh_dmx_enabled(roh)
        c = self.app.test_client()
        if schluessel:
            self.assertEqual(c.get(f"/?k={schluessel}").status_code, 200)
        return c

    def _socket(self, client):
        sc = self.sio.test_client(self.app, flask_test_client=client)
        self.addCleanup(lambda: sc.is_connected() and sc.disconnect())
        return sc


# ── Vorgaben ─────────────────────────────────────────────────────────────────

class VorgabenTest(unittest.TestCase):

    def test_ab_werk_alles_zu(self):
        for schalter in ("lan_remote_enabled", "feste_seite_enabled",
                         "roh_dmx_enabled", "laser_vom_handy", "vc_remote_enabled"):
            self.assertIs(remote_settings.DEFAULTS[schalter], False, schalter)

    def test_kaputter_wert_in_der_datei_bleibt_aus(self):
        for wert in ("ja", 1, "true", None):
            remote_settings.save_settings({"feste_seite_enabled": wert,
                                           "roh_dmx_enabled": wert,
                                           "laser_vom_handy": wert,
                                           "lan_remote_enabled": wert})
            self.assertFalse(remote_settings.is_feste_seite_enabled(), wert)
            self.assertFalse(remote_settings.is_roh_dmx_enabled(), wert)
            self.assertFalse(remote_settings.is_laser_vom_handy_erlaubt(), wert)
            self.assertFalse(remote_settings.is_lan_remote_enabled(), wert)
        remote_settings.save_settings({"feste_seite_enabled": False,
                                       "roh_dmx_enabled": False,
                                       "laser_vom_handy": False,
                                       "lan_remote_enabled": False})

    def test_zwei_verschiedene_schluessel_und_erneuern_trifft_beide(self):
        k, f = remote_settings.get_token(), remote_settings.get_feste_token()
        self.assertTrue(k and f)
        self.assertNotEqual(k, f)
        neu_k = remote_settings.regenerate_token()
        neu_f = remote_settings.get_feste_token()
        self.assertNotIn(neu_k, (k, f))
        self.assertNotIn(neu_f, (k, f, neu_k))

    @unittest.skipUnless(HAS_FLASK, "flask fehlt")
    def test_server_ohne_lesbare_einstellung_bindet_nur_lokal(self):
        quelle = open(os.path.join(_REPO, "src", "web", "app.py"), encoding="utf-8").read()
        rumpf = quelle[quelle.index("def start_server"):quelle.index("def stop_server")]
        # Vorbelegung 127.0.0.1, 0.0.0.0 nur nach ausdruecklichem „an“
        self.assertLess(rumpf.index('host = "127.0.0.1"'), rumpf.index('host = "0.0.0.0"'))


# ── Rechte-Matrix ────────────────────────────────────────────────────────────

class RechteMatrixTest(_Basis):

    def test_jede_route_steht_in_der_tabelle(self):
        regeln = {r.rule for r in self.app.url_map.iter_rules()
                  if r.endpoint != "static"}
        ohne = regeln - set(webapp.ROUTEN_RECHTE) - set(webapp.OFFENE_PFADE)
        self.assertEqual(ohne, set(), "Route ohne Recht — im Gate fuer jeden gesperrt, "
                                      "aber hier bewusst einzutragen")
        self.assertEqual(set(AUFRUFE), set(webapp.ROUTEN_RECHTE))

    def test_jedes_socket_ereignis_steht_in_der_tabelle(self):
        ereignisse = set(self.sio.server.handlers.get("/", {})) - {"connect", "disconnect"}
        self.assertEqual(ereignisse, set(webapp.EREIGNIS_RECHTE))

    def test_matrix_http(self):
        for art, schluessel, fest, roh in ARTEN:
            for regel, recht in webapp.ROUTEN_RECHTE.items():
                with self.subTest(art=art, route=regel):
                    self.state = _State()
                    c = self._client(schluessel, fest, roh)
                    methode, pfad, daten = AUFRUFE[regel]
                    r = getattr(c, methode)(pfad, json=daten)
                    gate = r.status_code == 403 and r.get_data() == b"Forbidden"
                    self.assertEqual(not gate, recht in ERWARTET[art],
                                     f"{art} {regel}: {r.status_code}")

    def test_matrix_socket(self):
        daten = {"go": None, "back": None, "stop": None,
                 "fader": {"slot": 1, "level": 0.5}, "blackout": {"enabled": True},
                 "vc_hallo": {}, "vc_aktion": {"id": "wabcdef", "aktion": "umschalten"},
                 "vc_pult": {"gm": 200}}
        for art, schluessel, fest, roh in ARTEN:
            for ereignis, recht in webapp.EREIGNIS_RECHTE.items():
                with self.subTest(art=art, ereignis=ereignis):
                    self.state = _State()
                    c = self._client(schluessel, fest, roh)
                    sc = self._socket(c)
                    if not ERWARTET[art]:
                        # ohne Recht keine Verbindung (fest_aus hat die Rolle,
                        # aber kein Recht: verbunden, jedes Ereignis abgelehnt)
                        if not sc.is_connected():
                            continue
                    r = sc.emit(ereignis, daten[ereignis], callback=True)
                    abgelehnt = isinstance(r, dict) and r.get("fehler") in (
                        "kein_recht", "kein_zugang")
                    self.assertEqual(not abgelehnt, recht in ERWARTET[art],
                                     f"{art} {ereignis}: {r}")

    def test_ohne_schluessel_keine_socket_verbindung(self):
        sc = self.sio.test_client(self.app, flask_test_client=self._client())
        self.assertFalse(sc.is_connected())

    def test_feste_seite_aus_wirkt_sofort_auf_offene_verbindung(self):
        c = self._client(FEST_K, fest=True)
        sc = self._socket(c)
        self.assertTrue(sc.emit("go", callback=True)["ok"])
        remote_settings.set_feste_seite_enabled(False)
        self.assertEqual(sc.emit("go", callback=True),
                         {"ok": False, "fehler": "kein_recht"})
        self.assertEqual(c.post("/api/go").status_code, 403)
        self.assertEqual(self.state.cue_stacks[0].aktionen, ["go"])

    def test_konsolen_link_fuehrt_nicht_zur_festen_seite(self):
        c = self._client(KONSOLE_K, fest=True, roh=True)
        html = c.get("/").get_data(as_text=True)
        self.assertNotIn("BLACKOUT", html)
        self.assertIn('href="/konsole"', html)
        self.assertEqual(c.post("/api/channel/1/5", json={"value": 255}).status_code, 403)
        self.assertEqual(self.state.kanaele, [])

    def test_unbekannte_route_ist_auch_angemeldet_403(self):
        c = self._client(FEST_K, fest=True, roh=True)
        self.assertEqual(c.get("/api/gibtesnicht").status_code, 403)
        self.assertEqual(c.get("/api/go").status_code, 403)       # falsche Methode

    def test_antwort_der_festen_seite_geht_nur_an_den_absender(self):
        c = self._client(FEST_K, fest=True)
        fest = self._socket(c)
        k = self._client(KONSOLE_K, fest=True)
        handy = self._socket(k)
        handy.get_received()
        fest.emit("go", callback=True)
        self.assertEqual([m["name"] for m in handy.get_received()], [])
        self.assertIn("ack", [m["name"] for m in fest.get_received()])


# ── Ungueltige Fern-Anfragen ─────────────────────────────────────────────────

class UngueltigTest(_Basis):

    def test_http_kaputte_anfragen_aendern_nichts(self):
        c = self._client(FEST_K, fest=True, roh=True)
        om, ex = self.state.output_manager, self.state.executors[0]
        om.set_blackout(True)
        faelle = [
            ("/api/blackout", None), ("/api/blackout", {}), ("/api/blackout", {"enabled": 1}),
            ("/api/blackout", {"enabled": "false"}), ("/api/blackout", [False]),
            ("/api/executor/1/fader", None), ("/api/executor/1/fader", {}),
            ("/api/executor/1/fader", {"level": "1"}), ("/api/executor/1/fader", {"level": True}),
            ("/api/executor/1/fader", {"level": 1.5}), ("/api/executor/1/fader", {"level": -0.1}),
            ("/api/executor/9/fader", {"level": 1}), ("/api/executor/0/fader", {"level": 1}),
            ("/api/executor/9/go", None),
            ("/api/channel/1/5", None), ("/api/channel/1/5", {"value": "255"}),
            ("/api/channel/1/5", {"value": 256}), ("/api/channel/1/5", {"value": 1.5}),
            ("/api/channel/1/600", {"value": 1}), ("/api/channel/7/5", {"value": 1}),
        ]
        for pfad, daten in faelle:
            with self.subTest(pfad=pfad, daten=daten):
                r = c.post(pfad, json=daten)
                self.assertIn(r.status_code, (400, 404))
                self.assertIs(r.get_json()["ok"], False)
        self.assertTrue(om.blackout)                    # nicht aufgehoben
        self.assertEqual(ex.fader_value, 0.25)          # nicht auf 100 %
        self.assertEqual(self.state.executors[1].presses, [])
        self.assertEqual(self.state.kanaele, [])

    def test_socket_kaputte_anfragen_aendern_nichts(self):
        c = self._client(FEST_K, fest=True)
        sc = self._socket(c)
        self.state.output_manager.set_blackout(True)
        for ereignis, daten in (("fader", None), ("fader", {}), ("fader", {"slot": 1}),
                                ("fader", {"slot": "1", "level": 1}),
                                ("fader", {"slot": 1, "level": "x"}),
                                ("blackout", None), ("blackout", {}),
                                ("blackout", {"enabled": 0})):
            with self.subTest(ereignis=ereignis, daten=daten):
                r = sc.emit(ereignis, daten, callback=True)
                self.assertIs(r["ok"], False)
        self.assertTrue(self.state.output_manager.blackout)
        self.assertEqual(self.state.executors[0].fader_value, 0.25)

    def test_konsole_pult_teilweise_kaputt_aendert_nichts(self):
        # Gueltiger Grand Master + kaputter Blackout: frueher wurde der GM
        # gesetzt und danach der Fehler gemeldet.
        from src.ui.virtualconsole import vc_fernbedienung  # noqa: F401  (Qt geladen)
        from PySide6.QtWidgets import QApplication
        from src.core.app_state import get_state
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_fernbedienung import VCFernbedienung
        from src.web import vc_remote
        QApplication.instance() or QApplication([])
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        fern = VCFernbedienung(canvas)
        vc_remote.registriere(fern)
        self.addCleanup(vc_remote.abmelden, fern)
        om = get_state().output_manager
        om.set_grand_master(1.0)
        self.addCleanup(om.set_grand_master, 1.0)
        for daten in ({"gm": 10, "blackout": "ja"}, {"gm": "x", "blackout": True},
                      {"gm": 300}, {"gm": -1}, {"blackout": None, "gm": None}):
            with self.subTest(daten=daten):
                r = vc_remote.pult(**daten, geraet="g1")
                self.assertIs(r["ok"], False)
        self.assertEqual(om.grand_master, 1.0)
        self.assertFalse(om.blackout_schalter)


# ── Blackout nur vom Urheber aufheben ────────────────────────────────────────

class BlackoutUrheberTest(_Basis):

    def test_feste_seite_hebt_fremden_blackout_nicht_auf(self):
        om = self.state.output_manager
        om.set_blackout(True)                          # am Pult gesetzt
        c = self._client(FEST_K, fest=True)
        r = c.post("/api/blackout", json={"enabled": False})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["fehler"], "blackout_nicht_von_hier")
        self.assertTrue(om.blackout)

    def test_nur_das_setzende_geraet_hebt_auf(self):
        om = self.state.output_manager
        a = self._client(FEST_K, fest=True)
        b = self._client(FEST_K, fest=True)
        self.assertEqual(a.post("/api/blackout", json={"enabled": True}).status_code, 200)
        self.assertEqual(b.post("/api/blackout", json={"enabled": False}).status_code, 403)
        self.assertTrue(om.blackout)
        # auch ueber den Socket desselben Geraets (Sitzung, nicht Verbindung)
        sa = self._socket(a)
        self.assertTrue(sa.emit("blackout", {"enabled": False}, callback=True)["ok"])
        self.assertFalse(om.blackout)

    def test_am_pult_neu_gesetzt_gilt_nicht_mehr_als_eigener(self):
        om = self.state.output_manager
        a = self._client(FEST_K, fest=True)
        a.post("/api/blackout", json={"enabled": True})
        om.set_blackout(False)                          # Pult: aus …
        om.set_blackout(True)                           # … und wieder an
        self.assertEqual(a.post("/api/blackout", json={"enabled": False}).status_code, 403)
        self.assertTrue(om.blackout)

    def test_schon_gesetzter_blackout_macht_nicht_zum_urheber(self):
        om = self.state.output_manager
        om.set_blackout(True)                           # Pult
        a = self._client(FEST_K, fest=True)
        self.assertEqual(a.post("/api/blackout", json={"enabled": True}).status_code, 200)
        self.assertEqual(a.post("/api/blackout", json={"enabled": False}).status_code, 403)
        self.assertTrue(om.blackout)


# ── Schluessel nie im Log / Diagnosepaket ────────────────────────────────────

@unittest.skipUnless(HAS_FLASK, "flask / flask-socketio nicht installiert")
class SchluesselNichtImLogTest(unittest.TestCase):
    """Eigener Prozess: ``install_tee`` haengt stdout/stderr prozessweit um."""

    def test_echter_server_log_und_diagnosepaket(self):
        with tempfile.TemporaryDirectory() as tmp:
            daten = os.path.join(tmp, "daten")
            os.makedirs(daten)
            env = dict(os.environ)
            env.update({"XDG_DATA_HOME": daten, "APPDATA": daten,
                        "LIGHTOS_PREFS_DIR": os.path.join(tmp, "prefs"),
                        "LIGHTOS_CRASH_LOG": os.path.join(daten, "crash.log"),
                        "PYTHONPATH": _REPO, "PYTHONIOENCODING": "utf-8",
                        "QT_QPA_PLATFORM": "offscreen"})
            env["LIGHTOS_LOG_DIR"] = os.path.join(tmp, "logs")
            paket = os.path.join(tmp, "paket.zip")
            log = os.path.join(tmp, "logs", "lightos.log")
            code = textwrap.dedent(f"""
                import socket, sys, urllib.request
                from src.core import diagnose_log as d
                d.install_tee()
                assert d.oeffne_sitzungslog("1.0")
                assert d.log_path() == {log!r}
                d.richte_python_logging_ein()
                from src.web import remote_settings, app
                remote_settings.set_lan_remote_enabled(False)
                remote_settings.set_vc_remote_enabled(True)
                remote_settings.set_feste_seite_enabled(True)
                s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
                app.start_server(port)
                assert app.bind_host() == "127.0.0.1"
                k, f = remote_settings.get_token(), remote_settings.get_feste_token()
                for pfad in ("/konsole?k=" + k, "/?k=" + f, "/?k=" + k + "&x=1"):
                    urllib.request.urlopen(f"http://127.0.0.1:{{port}}{{pfad}}", timeout=5).read()
                print("[probe] Link: http://127.0.0.1:5000/konsole?k=" + k)
                print("[probe] nackt:", k, f)
                app.stop_server()
                sys.stdout.flush(); sys.stderr.flush()
                d.erstelle_diagnosepaket({paket!r}, "1.0")
                print("SCHLUESSEL", k, f, file=sys.__stdout__)
            """)
            r = subprocess.run([sys.executable, "-c", code], cwd=_REPO, env=env,
                               capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            zeile = [z for z in r.stdout.splitlines() if z.startswith("SCHLUESSEL")][-1]
            _w, k, f = zeile.split()
            with open(log, encoding="utf-8") as fh:
                inhalt = fh.read()
            # die Anfragen stehen im Log — nur ohne Schluessel
            self.assertIn("GET /konsole?k=<schluessel>", inhalt)
            self.assertIn("GET /?k=<schluessel>", inhalt)
            self.assertNotIn(f"k={k}", inhalt)
            self.assertNotIn(f"k={f}", inhalt)
            with zipfile.ZipFile(paket) as z:
                for name in z.namelist():
                    text = z.read(name).decode("utf-8", errors="replace")
                    self.assertNotIn(k, text, name)
                    self.assertNotIn(f, text, name)
                self.assertTrue(any(n.startswith("logs/") for n in z.namelist()))

    def test_schwaerzen_trifft_alle_schreibweisen(self):
        from src.core.diagnose_log import anonymisiere, schluessel_schwaerzen
        for roh in ('"GET /konsole?k=Ab-_9xYz HTTP/1.1" 200',
                    "http://192.168.1.5:5000/?k=Ab-_9xYz&a=1",
                    "url=/konsole?token=Ab-_9xYz", "/x?key=Ab-_9xYz"):
            self.assertNotIn("Ab-_9xYz", schluessel_schwaerzen(roh), roh)
            self.assertNotIn("Ab-_9xYz", anonymisiere(roh), roh)


if __name__ == "__main__":
    unittest.main()

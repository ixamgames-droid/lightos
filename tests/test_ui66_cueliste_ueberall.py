"""UI-66: GO / Zurück / Stop OHNE ausdrückliche Listenangabe treffen auf allen
Bedienwegen (Leertaste, Kommandozeile `go`/`back` ohne Nummer, Web-Remote
/api/go|back|stop + Socket, OSC /lightos/go|back) dieselbe, LIVE-SICHERE
Transport-Ziel-Liste:
  a) gewählte Liste, wenn sie auf einem Executor liegt;
  b) sonst Liste des ersten Executors der aktuellen Page mit Liste;
  c) sonst erste Liste, die auf irgendeinem Executor liegt;
  d) sonst gewählte bzw. erste Liste — mit Warnung „kein Licht“.
Die Aufnahme-Regel (UI-62: gewählte, Rückfall erste) bleibt davon getrennt.

Wege MIT ausdrücklichem Ziel (Executor-Nummer/Slot) bleiben unverändert.
Echter AppState; Regel zentral in src/core/cueliste_ziel.py."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.cmdline.parser import parse
from src.core.osc.osc_server import OscServer
from src.ui.main_window import MainWindow

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

_app = QApplication.instance() or QApplication([])


class _Statusleiste:
    def __init__(self):
        self.meldungen = []

    def showMessage(self, text, timeout=0):
        self.meldungen.append(text)


class _FensterAttrappe:
    """Nur das, was MainWindow._global_go/_global_back brauchen — echter AppState
    plus Statusleiste (ein volles MainWindow ist für den Test zu schwer)."""
    # getattr: Datei bleibt auch auf dem Stand vor UI-66 sammelbar (Rot-Probe).
    _global_transport = getattr(MainWindow, "_global_transport", None)

    def __init__(self, state):
        self._state = state
        self._leiste = _Statusleiste()

    def statusBar(self):
        return self._leiste


class _OscAttrappe:
    """OscServer-Handler ohne Netzwerk-Socket: nur _get_state wird gebraucht."""
    def __init__(self, state):
        self._state = state

    def _get_state(self):
        return self._state


def _spion(stack, log):
    """Protokolliert go/back/stop der Liste und ruft das Original weiter auf."""
    for aktion in ("go", "back", "stop"):
        orig = getattr(stack, aktion)

        def _w(*a, _orig=orig, _aktion=aktion, **kw):
            log.append((stack.name, _aktion))
            return _orig(*a, **kw)
        setattr(stack, aktion, _w)


class _Grundaufbau(unittest.TestCase):
    """Echter AppState mit „Akt 1“/„Akt 2“/„Akt 3“, Page 0 ohne Executor-Bindung."""

    def setUp(self):
        self.state = get_state()
        self._orig_stacks = list(self.state.cue_stacks)
        self.state.cue_stacks.clear()
        self.state.gewaehlte_cueliste = None
        self.pe = self.state.playback_engine
        self._orig_page = self.pe.current_page
        self.pe.current_page = 0
        self._orig_bindung = [ex.stack for ex in self.pe.pages[0]]
        for ex in self.pe.pages[0]:
            ex.stack = None
        self.log = []
        self.a = self.state.new_cue_stack("Akt 1")
        self.b = self.state.new_cue_stack("Akt 2")
        self.c = self.state.new_cue_stack("Akt 3")
        for st in (self.a, self.b, self.c):
            _spion(st, self.log)

    def tearDown(self):
        for ex, st in zip(self.pe.pages[0], self._orig_bindung):
            ex.stack = st
        self.pe.current_page = self._orig_page
        self.state.cue_stacks.clear()
        self.state.cue_stacks.extend(self._orig_stacks)
        self.state.gewaehlte_cueliste = None

    def _waehle_b(self):
        self.state.gewaehlte_cueliste = self.b

    def _show_fall(self, auswahl):
        """Live-Fall aus dem Review: Hauptliste „Akt 2“ auf Exec 1, „Akt 1“
        (Index 0) ungebunden. auswahl: "akt1" (Playback-Combo nach Show-Laden
        steht auf cue_stacks[0]), "keine" oder "tot" (gelöschte Liste)."""
        self.pe.get_executor(1).stack = self.b
        if auswahl == "akt1":
            self.state.gewaehlte_cueliste = self.a
        elif auswahl == "tot":
            self.state.gewaehlte_cueliste = self.c
            self.state.remove_cue_stack(self.c)
        else:
            self.state.gewaehlte_cueliste = None
        self.log.clear()          # remove_cue_stack stoppt die Liste

    def _zwei_gebunden(self):
        """Akt 2 auf Exec 1, Akt 3 auf Exec 2, Auswahl Akt 3 (Fall a)."""
        self.pe.get_executor(1).stack = self.b
        self.pe.get_executor(2).stack = self.c
        self.state.gewaehlte_cueliste = self.c

    def _liegt(self, name):
        from src.core.cueliste_ziel import liegt_auf_executor
        st = next(s for s in self.state.cue_stacks if s.name == name)
        return liegt_auf_executor(self.state, st)

    _AUSWAHLEN = ("akt1", "keine", "tot")


class CuelisteUeberallTest(_Grundaufbau):
    # ── zentrale Regel ────────────────────────────────────────────────────────
    def test_aufnahme_regel_bleibt_gewaehlte_liste(self):
        # UI-62 unverändert: Aufnahme folgt der Auswahl, auch ohne Executor.
        self._show_fall("akt1")
        self.assertIs(self.state.aufnahme_cueliste(), self.a)
        self.state.gewaehlte_cueliste = None
        self.assertIs(self.state.aufnahme_cueliste(), self.a)  # Rückfall erste

    def test_regel_a_gewaehlte_gebundene_liste(self):
        self._zwei_gebunden()
        self.assertIs(self.state.bedien_cueliste(), self.c)

    def test_regel_b_ungebundene_auswahl_nimmt_ersten_executor(self):
        for auswahl in self._AUSWAHLEN:
            with self.subTest(auswahl=auswahl):
                self._show_fall(auswahl)
                self.assertIs(self.state.bedien_cueliste(), self.b)

    def test_regel_b_nur_aktuelle_page(self):
        # Akt 3 auf Page 2 Exec 1, Akt 2 auf Page 1 Exec 5 -> aktuelle Page zählt.
        self.pe.get_executor(1, page=1).stack = self.c
        self.pe.get_executor(5).stack = self.b
        try:
            self.assertIs(self.state.bedien_cueliste(), self.b)
        finally:
            self.pe.get_executor(1, page=1).stack = None

    def test_regel_c_erste_gebundene_liste_anderer_page(self):
        self.pe.get_executor(3, page=1).stack = self.c
        try:
            self.state.gewaehlte_cueliste = self.a
            self.assertIs(self.state.bedien_cueliste(), self.c)
        finally:
            self.pe.get_executor(3, page=1).stack = None

    def test_regel_d_nichts_gebunden(self):
        from src.core.cueliste_ziel import liegt_auf_executor
        self.assertIs(self.state.bedien_cueliste(), self.a)   # Rückfall erste
        self._waehle_b()
        self.assertIs(self.state.bedien_cueliste(), self.b)
        self.assertFalse(liegt_auf_executor(self.state, self.b))

    # ── Hauptfenster (Leertaste / Shift+Leertaste) ───────────────────────────
    def _fenster(self, methode):
        f = _FensterAttrappe(self.state)
        methode(f)
        return f._leiste.meldungen

    def test_leertaste_show_load_fall_trifft_executor_liste(self):
        for auswahl in self._AUSWAHLEN:
            with self.subTest(auswahl=auswahl):
                self.log.clear()
                self._show_fall(auswahl)
                meldungen = self._fenster(MainWindow._global_go)
                self._fenster(MainWindow._global_back)
                self.assertEqual(self.log, [("Akt 2", "go"), ("Akt 2", "back")])
                self.assertTrue(self._liegt("Akt 2"))
                self.assertFalse(any("kein Licht" in m for m in meldungen),
                                 meldungen)

    def test_leertaste_gewaehlte_gebundene_liste_schlaegt_ersten_executor(self):
        # Ersetzt test_leertaste_folgt_nicht_mehr_dem_ersten_executor: die
        # Auswahl gewinnt nur, wenn sie selbst auf einem Executor liegt.
        self._zwei_gebunden()
        self._fenster(MainWindow._global_go)
        self.assertEqual(self.log, [("Akt 3", "go")])

    def test_leertaste_ohne_executor_warnt_kein_licht(self):
        self._waehle_b()
        meldungen = self._fenster(MainWindow._global_go)
        self.assertEqual(self.log, [("Akt 2", "go")])
        self.assertTrue(any("kein Licht" in m for m in meldungen), meldungen)

    # ── Kommandozeile ─────────────────────────────────────────────────────────
    def test_kommandozeile_show_load_fall(self):
        for auswahl in self._AUSWAHLEN:
            with self.subTest(auswahl=auswahl):
                self.log.clear()
                self._show_fall(auswahl)
                r1 = parse("go").execute(self.state)
                r2 = parse("back").execute(self.state)
                self.assertTrue(r1.ok and r2.ok, (r1.message, r2.message))
                self.assertEqual(self.log, [("Akt 2", "go"), ("Akt 2", "back")])
                self.assertIn("Akt 2", r1.message)

    def test_kommandozeile_gewaehlte_gebundene_liste(self):
        self._zwei_gebunden()
        r = parse("go").execute(self.state)
        self.assertTrue(r.ok)
        self.assertEqual(self.log, [("Akt 3", "go")])

    def test_kommandozeile_ohne_executor_ok_false(self):
        self._waehle_b()
        r = parse("go").execute(self.state)
        self.assertFalse(r.ok)
        self.assertIn("kein Licht", r.message)
        self.assertEqual(self.log, [("Akt 2", "go")])

    def test_kommandozeile_mit_nummer_bleibt_executor(self):
        self.pe.get_executor(1).stack = self.a
        self.pe.get_executor(2).stack = self.b
        self._waehle_b()
        parse("go 1").execute(self.state)
        parse("back 1").execute(self.state)
        parse("stop 1").execute(self.state)
        self.assertEqual(self.log, [("Akt 1", "go"), ("Akt 1", "back"),
                                    ("Akt 1", "stop")])

    def test_kommandozeile_stop_ohne_nummer_bleibt_stop_all(self):
        self.assertIsNone(parse("stop").slot)
        self.pe.get_executor(1).stack = self.a
        self.pe.get_executor(2).stack = self.b
        self._waehle_b()
        r = parse("stop").execute(self.state)
        self.assertIn("Stop All", r.message)
        self.assertIn(("Akt 1", "stop"), self.log)
        self.assertIn(("Akt 2", "stop"), self.log)

    def test_kommandozeile_ohne_listen(self):
        self.state.cue_stacks.clear()
        r = parse("go").execute(self.state)
        self.assertFalse(r.ok)

    # ── OSC ───────────────────────────────────────────────────────────────────
    def test_osc_show_load_fall(self):
        for auswahl in self._AUSWAHLEN:
            with self.subTest(auswahl=auswahl):
                self.log.clear()
                self._show_fall(auswahl)
                osc = _OscAttrappe(self.state)
                OscServer._handle_go(osc, "/lightos/go")
                OscServer._handle_back(osc, "/lightos/back")
                self.assertEqual(self.log, [("Akt 2", "go"), ("Akt 2", "back")])

    def test_osc_gewaehlte_gebundene_liste(self):
        self._zwei_gebunden()
        OscServer._handle_go(_OscAttrappe(self.state), "/lightos/go")
        self.assertEqual(self.log, [("Akt 3", "go")])

    def test_osc_exec_bleibt_executor(self):
        self.pe.get_executor(1).stack = self.a
        self._waehle_b()
        OscServer._handle_exec(_OscAttrappe(self.state), "/lightos/exec/1/go")
        self.assertEqual(self.log, [("Akt 1", "go")])


@unittest.skipUnless(HAS_FLASK, "flask/flask_socketio nicht installiert")
class WebCuelisteUeberallTest(_Grundaufbau):
    """Web-Remote über den Flask-Testclient (nur lokal, kein Netzwerk)."""

    def setUp(self):
        super().setUp()
        import src.web.app as webapp
        self.webapp = webapp
        self._orig_get_state = webapp._get_state
        webapp._get_state = lambda: self.state
        self.app, self.sio = webapp.create_app()
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = "testtoken"
        self.client = self.app.test_client()
        self.client.get("/?k=testtoken")

    def tearDown(self):
        self.webapp._get_state = self._orig_get_state
        super().tearDown()

    def test_web_rest_show_load_fall(self):
        for auswahl in self._AUSWAHLEN:
            with self.subTest(auswahl=auswahl):
                self.log.clear()
                self._show_fall(auswahl)
                for pfad in ("/api/go", "/api/back", "/api/stop"):
                    r = self.client.post(pfad)
                    self.assertEqual(r.status_code, 200)
                    j = r.get_json()
                    self.assertEqual(j.get("liste"), "Akt 2")
                    self.assertIs(j.get("licht"), True)
                    self.assertNotIn("warnung", j)
                self.assertEqual(self.log, [("Akt 2", "go"), ("Akt 2", "back"),
                                            ("Akt 2", "stop")])

    def test_web_rest_gewaehlte_gebundene_liste(self):
        self._zwei_gebunden()
        j = self.client.post("/api/go").get_json()
        self.assertEqual((j.get("liste"), j.get("licht")), ("Akt 3", True))
        self.assertEqual(self.log, [("Akt 3", "go")])

    def test_web_rest_ohne_executor_warnt(self):
        self._waehle_b()
        j = self.client.post("/api/go").get_json()
        self.assertEqual(j.get("liste"), "Akt 2")
        self.assertIs(j.get("licht"), False)
        self.assertIn("kein Licht", j.get("warnung", ""))

    def test_web_socket_show_load_fall(self):
        self._show_fall("akt1")
        sio_client = self.sio.test_client(self.app, flask_test_client=self.client)
        self.assertTrue(sio_client.is_connected())
        for ev in ("go", "back", "stop"):
            sio_client.emit(ev)
        acks = [a["args"][0] for a in sio_client.get_received()
                if a.get("name") == "ack"]
        sio_client.disconnect()
        self.assertEqual(self.log, [("Akt 2", "go"), ("Akt 2", "back"),
                                    ("Akt 2", "stop")])
        self.assertEqual(len(acks), 3, acks)
        for ack in acks:
            self.assertEqual((ack.get("liste"), ack.get("licht")), ("Akt 2", True))

    def test_web_executor_go_bleibt_executor(self):
        self.pe.get_executor(1).stack = self.a
        self._waehle_b()
        self.client.post("/api/executor/1/go")
        self.assertEqual(self.log, [("Akt 1", "go")])


if __name__ == "__main__":
    unittest.main()

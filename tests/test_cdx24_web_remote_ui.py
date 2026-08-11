"""CDX-24: die beiden Sicherheits-Bedienelemente der Web-Remote-Anleitung sind
jetzt wirklich in der UI erreichbar.

Die Anleitung bewarb seit jeher „Token neu erzeugen" und den Toggle
„LAN-/Handy-Remote" als begehbaren Sicherheitspfad — beide Funktionen hatten aber
repo-weit NUR Test-Aufrufer, die UI las die Flags nur und zeigte eine reine
Info-Box. (Es ist das im Design-Doc als Follow-up geparkte NET-02-UI; der
BACKLOG-Verweis darauf zeigte ins Leere.)

Der Kern hier ist der Teil, der leicht falsch gemacht wird: eine Rotation, die
nur persistiert, lässt den LAUFENDEN Server weiter den alten ``?k=``-Link
akzeptieren — der Gate liest das Token aus ``app.config``, und dort landet es nur
beim ``create_app``.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.web import app as web_app
from src.web import remote_settings


class RefreshRunningTokenTest(unittest.TestCase):
    """`refresh_running_token()` — der Helfer, ohne den die UI ins Leere liefe
    (das modulprivate `_flask_app` ist von aussen nicht erreichbar)."""

    def setUp(self):
        self._orig_app = web_app._flask_app

    def tearDown(self):
        web_app._flask_app = self._orig_app

    def test_returns_false_without_running_server(self):
        web_app._flask_app = None
        self.assertFalse(web_app.refresh_running_token(),
                         "ohne laufenden Server gibt es nichts nachzuziehen")

    def test_pulls_the_new_token_into_the_running_app(self):
        fake = type("_App", (), {})()
        fake.config = {"LIGHTOS_REMOTE_TOKEN": "altes-token"}
        web_app._flask_app = fake

        new_token = remote_settings.regenerate_token()
        self.assertNotEqual(new_token, "altes-token")

        self.assertTrue(web_app.refresh_running_token())
        self.assertEqual(fake.config["LIGHTOS_REMOTE_TOKEN"], new_token,
                         "der laufende Server muss das NEUE Token bekommen — sonst "
                         "akzeptiert er den alten ?k=-Link weiter")

    def test_rotation_alone_does_not_reach_the_running_server(self):
        """Belegt, warum der Helfer noetig ist (und warum der alte Docstring von
        `regenerate_token` falsch war)."""
        fake = type("_App", (), {})()
        fake.config = {"LIGHTOS_REMOTE_TOKEN": "altes-token"}
        web_app._flask_app = fake

        remote_settings.regenerate_token()

        self.assertEqual(fake.config["LIGHTOS_REMOTE_TOKEN"], "altes-token",
                         "ohne refresh_running_token bleibt der Server auf dem alten Stand")


class LanToggleRoundTripTest(unittest.TestCase):
    """Der LAN-Toggle persistiert — die UI-Checkbox spiegelt also echten Zustand."""

    def setUp(self):
        self._orig = remote_settings.is_lan_remote_enabled()

    def tearDown(self):
        remote_settings.set_lan_remote_enabled(self._orig)

    def test_toggle_round_trip(self):
        remote_settings.set_lan_remote_enabled(False)
        self.assertFalse(remote_settings.is_lan_remote_enabled())
        remote_settings.set_lan_remote_enabled(True)
        self.assertTrue(remote_settings.is_lan_remote_enabled())


class MainWindowWiringTest(unittest.TestCase):
    """Die Verdrahtung selbst — ohne das echte MainWindow hochzuziehen.

    ★★ QA-52: Drei dieser Tests suchten Zeichenketten im Quelltext von
    ``_open_web_remote_dialog``. Bei einem SICHERHEITSdialog ist das die
    falsche Art von Zuversicht: der Text bleibt auch dann stehen, wenn der
    Aufruf in einem toten Zweig landet oder an keinem Knopf mehr haengt. Die
    Helfer unten bauen den Dialog deshalb wirklich und druecken wirklich.
    """

    def _dialog_bauen(self, laeuft=False):
        """``_open_web_remote_dialog`` gegen einen Stub fahren und die
        erzeugten Bedienelemente zurueckgeben.

        ``QDialog.exec`` wird ersetzt — der echte Aufruf blockiert bis zum
        Schliessen. Alles davor (Aufbau, Verdrahtung, ``_refresh_labels``)
        laeuft unveraendert.
        """
        import types
        from unittest import mock
        from PySide6.QtWidgets import (QApplication, QDialog, QPushButton,
                                       QCheckBox)
        from src.ui import main_window as mw
        from src.web import remote_settings

        QApplication.instance() or QApplication([])
        self.regen_gerufen = False
        self.refresh_gerufen = False
        self.lan_gesetzt = False
        self.server_aktionen = []

        # ★ Ein ECHTES QWidget: `_open_web_remote_dialog` baut `QDialog(self)`,
        # koppelt die Lebensdauer also an das Fenster. Ein SimpleNamespace
        # scheitert dort mit TypeError — und genau diese Kopplung ist ja Teil
        # dessen, was der Dialog richtig machen soll.
        from PySide6.QtWidgets import QWidget

        class _FensterStub(QWidget):
            def statusBar(self):
                return types.SimpleNamespace(showMessage=lambda *a, **k: None)

        stub = _FensterStub()
        self.addCleanup(stub.deleteLater)
        stub._act_web = types.SimpleNamespace(setChecked=lambda _b: None)
        stub._lbl_web = types.SimpleNamespace(setText=lambda _t: None,
                                              setStyleSheet=lambda _s: None)
        gebaut = {}

        def _exec(dlg_self):
            gebaut["dlg"] = dlg_self
            gebaut["buttons"] = dlg_self.findChildren(QPushButton)
            gebaut["checks"] = dlg_self.findChildren(QCheckBox)
            return 0

        def _regen():
            self.regen_gerufen = True

        def _refresh():
            self.refresh_gerufen = True
            return True

        def _set_lan(wert):
            self.lan_gesetzt = True

        import src.web.app as web_app
        # ★ Die Patches muessen den KLICK ueberleben, nicht nur den Aufbau:
        # `remote_settings.regenerate_token()` und der `from src.web import app`
        # in `_lan_toggled` werden erst beim Druecken aufgeloest. Mit einem
        # `with`-Block waeren zur Klickzeit wieder die echten Funktionen aktiv —
        # der Test haette dann das echte Token rotiert und den echten Server
        # angefasst.
        for ziel, name, wert in (
                (QDialog, "exec", _exec),
                (remote_settings, "regenerate_token", _regen),
                (remote_settings, "set_lan_remote_enabled", _set_lan),
                (remote_settings, "get_token", lambda: "abc"),
                (remote_settings, "is_lan_remote_enabled", lambda: False),
                (web_app, "refresh_running_token", _refresh),
                (web_app, "is_running", lambda: laeuft),
                (web_app, "stop_server",
                 lambda: self.server_aktionen.append("stop")),
                (web_app, "start_server",
                 lambda *_a: self.server_aktionen.append("start")),
        ):
            fleck = mock.patch.object(ziel, name, wert)
            fleck.start()
            self.addCleanup(fleck.stop)
        mw.MainWindow._open_web_remote_dialog(stub)
        self.assertIn("dlg", gebaut, "der Dialog wurde nie aufgebaut")
        return gebaut

    def _drueck_token_knopf(self, *, bestaetigen: bool):
        from unittest import mock
        from PySide6.QtWidgets import QMessageBox
        from src.ui import main_window as mw
        gebaut = self._dialog_bauen()
        knopf = next(b for b in gebaut["buttons"]
                     if "Token" in b.text())
        antwort = (QMessageBox.StandardButton.Yes if bestaetigen
                   else QMessageBox.StandardButton.No)
        with mock.patch.object(mw.QMessageBox, "question",
                               lambda *a, **k: antwort):
            knopf.click()

    def _schalte_lan(self, *, laeuft: bool):
        gebaut = self._dialog_bauen(laeuft=laeuft)
        haken = gebaut["checks"][0]
        haken.setChecked(True)      # loest `toggled` aus

    def test_dialog_handler_exists(self):
        from src.ui.main_window import MainWindow
        self.assertTrue(callable(getattr(MainWindow, "_open_web_remote_dialog", None)),
                        "Menue-Eintrag 'Web-Remote: Verbindung & Token' braucht den Handler")

    def test_menu_entry_is_wired(self):
        """Der Eintrag muss ein EIGENER Menuepunkt sein: der dokumentierte
        Incident-Pfad („bei Verdacht Token neu erzeugen") muss waehrend einer
        laufenden Show erreichbar sein, nicht nur beim Einschalten."""
        import inspect
        from src.ui import main_window
        src = inspect.getsource(main_window.MainWindow)
        self.assertIn("Web-Remote: Verbindung", src)
        self.assertIn("_open_web_remote_dialog", src)

    def test_dialog_uses_both_controls_and_refreshes_the_server(self):
        """★★ QA-52: Dieser Test suchte drei Zeichenketten im QUELLTEXT.

        Er blieb damit gruen, wenn die Aufrufe in einem toten Zweig stehen, an
        einen nie verdrahteten Knopf haengen oder nur im Kommentar vorkommen —
        und bei einem SICHERHEITSdialog ist das die falsche Art von Zuversicht.
        Jetzt wird der Dialog gebaut, der Knopf gedrueckt und geprueft, was
        wirklich passiert.
        """
        self._drueck_token_knopf(bestaetigen=True)
        self.assertTrue(self.regen_gerufen,
                        "'Token neu erzeugen' muss regenerate_token() rufen")
        self.assertTrue(self.refresh_gerufen,
                        "ohne refresh_running_token() akzeptiert der LAUFENDE "
                        "Server weiter den alten ?k=-Link")

    def test_abbrechen_erzeugt_kein_neues_token(self):
        """Positivkontrolle: der Default der Rueckfrage ist bewusst 'Nein' —
        ein Enter im Showbetrieb wuerde sonst alle Geraete rauswerfen."""
        self._drueck_token_knopf(bestaetigen=False)
        self.assertFalse(self.regen_gerufen)
        self.assertFalse(self.refresh_gerufen)

    def test_lan_toggle_restarts_the_running_server(self):
        """NET-09-Falle: die Bind-Adresse wird NUR in start_server gelesen. Ohne
        Neustart glaubt der Nutzer 'aus', der Port bleibt aber im LAN offen.

        ★ QA-52: Auch dieser Test las nur den Quelltext. Jetzt wird der Haken
        wirklich umgelegt — bei LAUFENDEM Server, denn nur dann ist der
        Neustart faellig.
        """
        self._schalte_lan(laeuft=True)
        self.assertTrue(self.lan_gesetzt, "set_lan_remote_enabled() muss laufen")
        self.assertEqual(["stop", "start"], self.server_aktionen,
                         "der laufende Server muss neu gestartet werden")

    def test_lan_toggle_startet_einen_gestoppten_server_nicht(self):
        """Positivkontrolle: bei gestopptem Server waere ein start_server() ein
        ungewolltes Einschalten — der Haken aendert die Einstellung, mehr nicht."""
        self._schalte_lan(laeuft=False)
        self.assertTrue(self.lan_gesetzt)
        self.assertEqual([], self.server_aktionen)



class SocketIoRotationTest(unittest.TestCase):
    """CDX-24: die Rotation darf kein halbes Versprechen bleiben.

    Das ``before_request``-Gate sperrt jede HTTP-Anfrage der alten Epoche — ein
    SCHON VERBUNDENER WebSocket laeuft aber nicht mehr durch dieses Gate, und die
    Event-Handler (``go``/``back``/…) pruefen einzeln gar nichts. Ein Handy, das
    vor der Rotation verbunden war, koennte also weitersteuern, obwohl der Nutzer
    gerade „alle bisherigen Geraete ungueltig machen" gedrueckt hat.
    """

    def setUp(self):
        self._orig_sio = web_app._socketio
        self._orig_app = web_app._flask_app

    def tearDown(self):
        web_app._socketio = self._orig_sio
        web_app._flask_app = self._orig_app

    def test_disconnect_all_clients_drops_every_open_socket(self):
        dropped = []

        class _Mgr:
            def get_participants(self, ns, room):
                return [("sid-a", object()), ("sid-b", object())]

        class _Srv:
            manager = _Mgr()

            def disconnect(self, sid, namespace=None):
                dropped.append(sid)

        web_app._socketio = type("_Sio", (), {"server": _Srv()})()
        self.assertEqual(web_app.disconnect_all_clients(), 2)
        self.assertEqual(dropped, ["sid-a", "sid-b"])

    def test_rotation_helper_also_disconnects(self):
        dropped = []

        class _Mgr:
            def get_participants(self, ns, room):
                return [("sid-a", object())]

        class _Srv:
            manager = _Mgr()

            def disconnect(self, sid, namespace=None):
                dropped.append(sid)

        fake = type("_App", (), {})()
        fake.config = {"LIGHTOS_REMOTE_TOKEN": "alt"}
        web_app._flask_app = fake
        web_app._socketio = type("_Sio", (), {"server": _Srv()})()

        self.assertTrue(web_app.refresh_running_token())
        self.assertEqual(dropped, ["sid-a"],
                         "Token neu erzeugen muss offene Verbindungen kappen")

    def test_no_socketio_is_harmless(self):
        web_app._socketio = None
        self.assertEqual(web_app.disconnect_all_clients(), 0)

    def test_broken_manager_never_breaks_the_rotation(self):
        class _Srv:
            @property
            def manager(self):
                raise RuntimeError("kaputt")

        web_app._socketio = type("_Sio", (), {"server": _Srv()})()
        self.assertEqual(web_app.disconnect_all_clients(), 0)


class StopServerSafetyTest(unittest.TestCase):
    """CDX-24 (Review-Fund S1): `stop_server()` muss BESTEHENDE Verbindungen kappen.

    `server_close()` gibt nur den LISTEN-Socket frei. Werkzeugs
    `ThreadedWSGIServer` laeuft mit `daemon_threads = True`, deshalb sammelt
    `ThreadingMixIn` seine Handler-Threads gar nicht ein und joint beim Schliessen
    nichts — ein bereits auf WebSocket hochgestufter Client lief UNBEGRENZT weiter
    und konnte GO/STOP/Fader/Blackout schicken, obwohl der Nutzer das Interface
    ausgeschaltet bzw. auf „nur dieser PC" gestellt hatte.

    Reihenfolge ist dabei zwingend: nach einem `start_server()` zeigt `_socketio`
    auf die NEUE Instanz, die Alt-Clients waeren dann nicht mehr adressierbar.
    """

    def setUp(self):
        self._orig = (web_app._socketio, web_app._flask_app,
                      web_app._server, web_app._thread, web_app._running)

    def tearDown(self):
        (web_app._socketio, web_app._flask_app,
         web_app._server, web_app._thread, web_app._running) = self._orig

    def test_stop_server_disconnects_open_clients(self):
        dropped = []

        class _Mgr:
            def get_participants(self, ns, room):
                return [("sid-alt", object())]

        class _Srv:
            manager = _Mgr()

            def disconnect(self, sid, namespace=None):
                dropped.append(sid)

        web_app._socketio = type("_Sio", (), {"server": _Srv()})()
        web_app._server = None
        web_app._thread = None
        web_app._running = True

        web_app.stop_server()

        self.assertEqual(dropped, ["sid-alt"],
                         "ein offener WebSocket ueberlebt sonst das Ausschalten")

    def test_stop_server_clears_the_globals(self):
        web_app._flask_app = object()
        web_app._socketio = None
        web_app._server = None
        web_app._thread = None
        web_app._running = True

        web_app.stop_server()

        self.assertIsNone(web_app._flask_app)
        self.assertFalse(web_app.is_running())
        self.assertFalse(web_app.refresh_running_token(),
                         "nach dem Ausschalten darf der Dialog nicht 'Neues Token "
                         "aktiv' fuer einen toten Server melden")


class RotationFailureTest(unittest.TestCase):
    """CDX-24 (Review-Fund S3): `save_settings` schluckt Schreibfehler. Ohne
    Gegenprobe meldete die UI Erfolg, waehrend die alten Links weiter galten."""

    def test_regenerate_raises_when_nothing_was_persisted(self):
        orig = remote_settings.save_settings
        remote_settings.save_settings = lambda *_a, **_k: None   # schlaegt still fehl
        try:
            with self.assertRaises(RuntimeError):
                remote_settings.regenerate_token()
        finally:
            remote_settings.save_settings = orig

    def test_regenerate_succeeds_normally(self):
        before = remote_settings.get_token()
        after = remote_settings.regenerate_token()
        self.assertNotEqual(before, after)
        self.assertEqual(remote_settings.get_token(), after)


class AtomicSaveTest(unittest.TestCase):
    """CDX-24 (Review-Fund S8): nicht-atomares Schreiben liess den Auth-Gate im
    Schreibfenster eine leere Datei lesen -> Rueckfall auf `auth_epoch: 0`, also
    fail-OPEN ausgerechnet waehrend der Rotation."""

    def test_settings_file_is_never_half_written(self):
        import json as _json
        remote_settings.regenerate_token()
        path = remote_settings._prefs_path()
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)          # wirft, waere die Datei abgeschnitten
        self.assertIn("remote", data)
        self.assertFalse(os.path.exists(f"{path}.tmp"),
                         "die Temp-Datei muss per os.replace verschwunden sein")


if __name__ == "__main__":
    unittest.main()

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
    """Die Verdrahtung selbst — ohne das echte MainWindow hochzuziehen."""

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
        import inspect
        from src.ui.main_window import MainWindow
        src = inspect.getsource(MainWindow._open_web_remote_dialog)
        for needle in ("regenerate_token", "set_lan_remote_enabled",
                       "refresh_running_token"):
            with self.subTest(needle=needle):
                self.assertIn(needle, src)

    def test_lan_toggle_restarts_the_running_server(self):
        """NET-09-Falle: die Bind-Adresse wird NUR in start_server gelesen. Ohne
        Neustart glaubt der Nutzer 'aus', der Port bleibt aber im LAN offen."""
        import inspect
        from src.ui.main_window import MainWindow
        src = inspect.getsource(MainWindow._open_web_remote_dialog)
        self.assertIn("stop_server", src)
        self.assertIn("start_server", src)


if __name__ == "__main__":
    unittest.main()

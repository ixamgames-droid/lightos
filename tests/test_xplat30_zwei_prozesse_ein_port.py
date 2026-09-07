"""XPLAT-30: ein belegter Web-Port startet keinen zweiten Server mehr.

NET-11 hat den Fall „Port belegt" schon behandelt: ``make_server`` ruft dort
``sys.exit(1)``, und der ``SystemExit`` ging an jedem ``except Exception``
vorbei — LightOS beendete sich beim Klick auf den Menue-Schalter. Der Fix macht
daraus eine ``OSError``.

⚠️ **Auf Windows griff dieser Schutz NIE, weil dort gar nichts fehlschlaegt.**
``make_server`` setzt ``SO_REUSEADDR``, und die Option bedeutet auf den beiden
Plattformen etwas Verschiedenes:

* **Linux** — „nach TIME_WAIT wieder binden duerfen". Noetig, damit der
  Menue-Schalter aus/ein sofort wieder starten kann.
* **Windows** — „einen belegten Port MITBENUTZEN duerfen". Der zweite Bind
  gelingt, und es laufen **zwei Server auf demselben Port**; welche Instanz eine
  Verbindung bekommt, ist nicht definiert.

Die App meldete deshalb „Web laeuft", und je nach Zufall antwortete mal die eine,
mal die andere Instanz — stiller als ein Absturz und schwerer zu finden als ein
Fehler.

★ **Der Mechanismus ist in ``test_net11_web_port_belegt`` bereits gemessen**
(„er gelingt nur MIT der Option, die der Server setzt"). Diese Datei prueft
nicht den Socket noch einmal, sondern das VERHALTEN von ``start_server``.

⚠️ **Und eine Probenfalle, die hier zweimal zugeschlagen hat:** ``start_server``
bindet ``0.0.0.0`` (LAN-Remote an, der Default). Ein Halter auf ``127.0.0.1``
kollidiert damit gar nicht — die erste Messung meldete „kein Fehler" und sah aus
wie ein gescheiterter Fix. Der Halter muss auf DERSELBEN Adresse sitzen.
"""
from __future__ import annotations

import os
import socket
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.web import app as W

_HAS_FLASK = getattr(W, "HAS_FLASK", False)


def _halter(host: str):
    """Ein Listener wie eine zweite LightOS-Instanz — mit ``SO_REUSEADDR``."""
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, 0))
    s.listen(5)
    return s, s.getsockname()[1]


def _freier_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(_HAS_FLASK, "Flask/flask-socketio nicht installiert")
class StartServerTest(unittest.TestCase):
    def setUp(self):
        W._running = False
        self.addCleanup(setattr, W, "_running", False)
        # ⚠️ ``start_server`` waehlt seinen Bind-Host nach dem LAN-Remote-Schalter
        # (an -> 0.0.0.0, aus -> 127.0.0.1). Der ist eine GLOBALE App-Einstellung,
        # und ``test_cdx24_web_remote_ui`` schaltet ihn um. Ohne diese Zeile
        # kollidiert der Halter je nach Schalterstellung gar nicht mit dem Server
        # — der Test lief allein gruen und im Verbund rot, mit „OSError not
        # raised", also wie ein gescheiterter Fix statt wie eine kaputte Probe.
        # Hier wird die Stellung deshalb festgelegt, nicht vorausgesetzt.
        from src.web import remote_settings
        alt_fn = remote_settings.is_lan_remote_enabled
        remote_settings.is_lan_remote_enabled = lambda: True
        self.addCleanup(setattr, remote_settings, "is_lan_remote_enabled", alt_fn)

    def _stoppe(self):
        srv = getattr(W, "_server", None)
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        W._running = False

    def test_ein_belegter_port_meldet_sich_als_OSError(self):
        """★★ Der Kern: kein stiller zweiter Server, kein SystemExit.

        ``OSError`` ist bewusst der Typ — den behandeln die Aufrufer (Menue,
        OSC, Kommandozeile) schon, weil ein fehlgeschlagenes Binden ihn ohnehin
        haette.
        """
        # ⚠️ Auf DERSELBEN Adresse halten, die start_server bindet — sonst
        # kollidiert nichts und der Test misst nichts (s. Modul-Docstring).
        halter, port = _halter("0.0.0.0")
        self.addCleanup(halter.close)
        self.addCleanup(self._stoppe)

        with self.assertRaises(OSError) as ctx:
            W.start_server(port)
        self.assertNotIsInstance(ctx.exception, SystemExit)
        self.assertIn(str(port), str(ctx.exception),
                      "die Meldung nennt den Port nicht")
        self.assertFalse(W.is_running(),
                         "die App haelt sich fuer gestartet, obwohl nichts laeuft")

    def test_ein_freier_port_startet_unveraendert(self):
        """★ Ohne diesen Arm koennte der Fix schlicht alles abweisen."""
        self.addCleanup(self._stoppe)
        port = _freier_port()
        self.assertEqual(port, W.start_server(port))
        self.assertTrue(W.is_running())

    def test_die_option_bleibt_nicht_veraendert_zurueck(self):
        """⚠️ Der Eingriff ist global — er darf den Prozess nicht umkonfiguriert
        zuruecklassen, auch nicht im Fehlerfall."""
        from werkzeug.serving import BaseWSGIServer
        # ⚠️ Den Ausgangswert SETZEN, nicht bloss lesen. Die erste Fassung las
        # ihn nur — und wenn ein frueherer Test im selben Prozess die Option
        # verstellt zurueckliess, war „vorher" bereits False und der Vergleich
        # ging trivial auf. Die Mutationsprobe hat genau das gefangen: das
        # Entfernen der Wiederherstellung faerbte NICHTS rot.
        self.addCleanup(setattr, BaseWSGIServer, "allow_reuse_address",
                        BaseWSGIServer.allow_reuse_address)
        BaseWSGIServer.allow_reuse_address = True
        vorher = True
        halter, port = _halter("0.0.0.0")
        self.addCleanup(halter.close)
        self.addCleanup(self._stoppe)
        try:
            W.start_server(port)
        except OSError:
            pass
        self.assertEqual(vorher, BaseWSGIServer.allow_reuse_address,
                         "allow_reuse_address bleibt umgestellt — der naechste "
                         "Server im Prozess erbt eine fremde Entscheidung")

    def test_aus_und_sofort_wieder_an_geht_weiterhin(self):
        """★★ Die Gegenprobe zum Eingriff, und der Grund fuer die Windows-Grenze.

        ``SO_REUSEADDR`` gibt es auf Linux, damit genau das nach TIME_WAIT
        funktioniert. Deshalb wird die Option NUR auf Windows abgeschaltet — und
        dass es dort trotzdem traegt, steht hier als Messung.
        """
        self.addCleanup(self._stoppe)
        port = _freier_port()
        W.start_server(port)
        c = socket.create_connection(("127.0.0.1", port), timeout=3)
        try:
            c.sendall(b"GET / HTTP/1.0\r\n\r\n")
            c.recv(64)
        finally:
            c.close()
        self._stoppe()
        self.assertEqual(port, W.start_server(port),
                         "nach einer bedienten Verbindung startet der Server "
                         "nicht mehr — genau das verhindert SO_REUSEADDR auf "
                         "Linux, und deshalb bleibt sie dort an")


class HinweisTest(unittest.TestCase):
    """Der Hinweis in der Meldung muss auf der Plattform existieren.

    ⚠️ Bis XPLAT-30 stand dort fest ``ss -lptn`` — ein Werkzeug, das es auf
    Windows nicht gibt. Die Meldung schickte also genau die Nutzer ins Leere,
    bei denen der Fall ueberhaupt auftreten kann.
    """

    def test_er_nennt_den_port(self):
        self.assertIn("4711", W._halter_hinweis(4711))

    def test_er_passt_zur_plattform(self):
        hinweis = W._halter_hinweis(4711)
        if os.name == "nt":
            self.assertIn("netstat", hinweis)
            self.assertNotIn("ss -lptn", hinweis,
                             "ein Linux-Befehl auf Windows")
        else:
            self.assertIn("ss -lptn", hinweis)
            self.assertNotIn("netstat", hinweis)


class GrenzeTest(unittest.TestCase):
    """Die Windows-Grenze steht im Code und ist begruendet, nicht zufaellig."""

    def test_der_eingriff_ist_auf_windows_beschraenkt(self):
        """★ Ein pauschales Abschalten waere auf Linux ein Regress.

        Geprueft wird die BEDINGUNG im Quelltext, nicht ihre Wirkung — die
        Wirkung laesst sich auf der jeweils anderen Plattform nicht messen.
        """
        import inspect
        quelle = inspect.getsource(W.start_server)
        self.assertIn('os.name == "nt"', quelle,
                      "der Eingriff gilt fuer alle Plattformen — auf Linux "
                      "heisst das, dass 'Web aus, Web an' an TIME_WAIT "
                      "scheitern kann")
        self.assertIn("allow_reuse_address", quelle)


if __name__ == "__main__":
    unittest.main()

"""NET-11: ein belegter Web-Port darf LightOS nicht beenden.

``werkzeug.serving.make_server`` ruft bei ``EADDRINUSE`` intern ``sys.exit(1)``.
Das wirft ``SystemExit`` — und ``SystemExit`` ist **keine** ``Exception``. Jeder
Aufrufer, der ``except Exception`` schreibt, laesst es also durch; im
Menue-Schalter (`MainWindow._toggle_web_server`) steigt es aus dem Qt-Slot heraus
und beendet die Anwendung auf der Stelle — ohne Dialog, ohne Eintrag im Menue.

Gemessen vor dem Fix: ``SystemExit(1)``. Nachher: ``OSError`` mit einer Meldung,
die den Port nennt und sagt, wie man den Halter findet.

★ Repariert wird an der QUELLE, nicht am Aufrufer: ``except Exception`` ist im
Slot voellig richtig, und es gibt drei weitere Aufrufwege (Menue, OSC,
Kommandozeile). Wer nur den einen Aufrufer haerten wuerde, liesse die anderen
offen — und die naechste Aufrufstelle faengt den Fehler wieder nicht.
"""
import os
import socket
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class BelegterPortBeendetNichtTest(unittest.TestCase):

    def setUp(self):
        # Einen Port wirklich belegen — kein Attrappen-Fehler, sondern der echte
        # EADDRINUSE-Pfad von werkzeug.
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]

    def tearDown(self):
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            from src.web.app import stop_server
            stop_server()
        except Exception:
            pass

    def test_belegter_port_wirft_oserror_statt_systemexit(self):
        from src.web.app import start_server

        with self.assertRaises(OSError) as ctx:
            start_server(self.port)

        self.assertNotIsInstance(
            ctx.exception, SystemExit,
            "SystemExit laeuft an jedem `except Exception` vorbei und beendet die App")
        self.assertIn(str(self.port), str(ctx.exception),
                      "Die Meldung nennt den Port nicht — dann sucht der Nutzer blind")

    def test_ein_except_exception_faengt_es(self):
        """Die eigentliche Zusicherung: der Aufrufer-Stil, den es im Repo GIBT,
        reicht aus. ``MainWindow._toggle_web_server`` schreibt ``except Exception``
        — und das ist richtig so; der Fehler muss dorthin passen."""
        from src.web.app import start_server

        gefangen = None
        try:
            start_server(self.port)
        except Exception as e:            # exakt der Stil des Menue-Schalters
            gefangen = e
        self.assertIsNotNone(
            gefangen,
            "Der Fehler kam an `except Exception` vorbei — die App waere gestorben")

    def test_der_systemexit_pfad_wird_wirklich_umgesetzt(self):
        """Gegenprobe an der Ursache selbst.

        Falls werkzeug sein Verhalten eines Tages aendert, soll dieser Test die
        Umsetzung trotzdem festnageln: ein ``SystemExit`` aus ``make_server``
        muss als ``OSError`` herauskommen.
        """
        from src.web import app as web

        with patch("werkzeug.serving.make_server",
                   side_effect=SystemExit(1)):
            with self.assertRaises(OSError):
                web.start_server(self.port)

    def test_freier_port_startet_unveraendert(self):
        """Positivkontrolle — sonst waere „wirft nie SystemExit" auch dadurch zu
        erreichen, dass gar nichts mehr startet."""
        from src.web.app import start_server, stop_server

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            frei = s.getsockname()[1]

        port = start_server(frei)
        try:
            self.assertEqual(port, frei)
        finally:
            stop_server()


if __name__ == "__main__":
    unittest.main()

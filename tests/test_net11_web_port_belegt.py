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


def _wie_der_server_binden_wuerde(sock) -> None:
    """Setzt auf ``sock`` genau die Optionen, mit denen der Code unter Test bindet.

    ``src/web/app.py`` startet ueber ``make_server(..., threaded=True)``, also
    einen ``ThreadedWSGIServer``. Dessen ``server_bind`` (geerbt von
    ``socketserver.TCPServer``) setzt vor dem Bind ``SO_REUSEADDR``, weil
    ``allow_reuse_address`` wahr ist. Hier wird dieselbe Reihenfolge
    nachgefahren — und die Flags werden aus **derselben Quelle gelesen**, ueber
    die die Sonde eine Aussage macht, statt sie nachzubauen: aendert ``werkzeug``
    seine Option eines Tages, aendert sich die Sonde mit.
    """
    from werkzeug.serving import ThreadedWSGIServer as _Server

    # Spiegelt socketserver.TCPServer.server_bind, Bedingung fuer Bedingung.
    if _Server.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if (getattr(_Server, "allow_reuse_port", False)
            and hasattr(socket, "SO_REUSEPORT")
            and _Server.address_family in (socket.AF_INET, socket.AF_INET6)):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)


def _zweiter_bind_scheitert(port) -> bool:
    """Weist DIESES Betriebssystem einen zweiten Bind auf denselben Port ab?

    XPLAT-30: auf Linux ja, auf Windows **nein** — dort gelingt der zweite Bind,
    sobald er mit ``SO_REUSEADDR`` gestellt wird, und genau so stellt der Server
    ihn. Die Voraussetzung dieser Tests ist damit auf Windows gar nicht gegeben;
    sie faerbten sich rot, ohne etwas zu messen (von Sitzung B auf
    unveraendertem ``main`` reproduziert).

    Geprueft wird die **Voraussetzung selbst**, nicht der Plattformname: ein
    ``sys.platform == "win32"`` waere geraten, das hier ist gemessen — und es
    traegt auch, wenn sich das Verhalten einer Plattform einmal aendert.

    ★ **Und gemessen wird an DEM Socket, der spaeter wirklich bindet.** Die
    erste Fassung (#698) band mit einem **nackten** Socket. Der wird auf Windows
    sehr wohl mit ``WSAEADDRINUSE`` (10048) abgewiesen — die Sonde meldete also
    „Voraussetzung gegeben", die Tests liefen los, und ``werkzeug`` band danach
    mit ``SO_REUSEADDR`` klaglos auf den belegten Port: ``assertRaises(OSError)``
    fiel. Beide Faelle direkt gegeneinander gemessen (Windows 11, Sitzung B):
    zweiter Bind **ohne** ``SO_REUSEADDR`` → abgewiesen (10048), **mit**
    ``SO_REUSEADDR`` → gelingt. Die Lehre ist allgemeiner als dieser Test: eine
    Voraussetzungs-Sonde muss den **Binder spiegeln**, ueber den sie eine
    Aussage macht — sonst sagt sie etwas ueber einen Socket voraus, den niemand
    benutzt.
    """
    zweiter = socket.socket()
    _wie_der_server_binden_wuerde(zweiter)
    try:
        zweiter.bind(("127.0.0.1", port))
    except OSError:
        return True
    finally:
        zweiter.close()
    return False


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

    def _voraussetzung_oder_skip(self):
        """Die beiden Bind-Tests messen nur dort etwas, wo ein zweiter Bind — so
        wie ``werkzeug`` bindet — auch wirklich scheitert."""
        if _zweiter_bind_scheitert(self.port):
            return
        self.skipTest(
            'Dieses Betriebssystem laesst einen zweiten Bind auf denselben Port '
            'zu, und zwar mit genau den Optionen, mit denen der Server bindet '
            '(SO_REUSEADDR) — die Voraussetzung dieses Tests ist hier nicht '
            'gegeben. Der eigentliche Fehler (SystemExit an except Exception '
            'vorbei) wird von test_der_systemexit_pfad_wird_wirklich_umgesetzt '
            'plattformunabhaengig festgehalten. Siehe XPLAT-30.')

    def test_belegter_port_wirft_oserror_statt_systemexit(self):
        self._voraussetzung_oder_skip()
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
        self._voraussetzung_oder_skip()
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


class VoraussetzungWirdNichtStillWahrTest(unittest.TestCase):
    """Ein Test, der ueberall ueberspringt, prueft nichts.

    Die beiden Bind-Tests haengen seit XPLAT-30 an einer Voraussetzung. Faellt
    die auf DIESEM System eines Tages weg — etwa weil jemand ``SO_REUSEADDR``
    global setzt — wuerden sie stumm ueberspringen und niemand merkte es. Dieser
    Test faellt dann rot.
    """

    def test_auf_diesem_system_scheitert_der_zweite_bind(self):
        if os.name == "nt":
            self.skipTest("Auf Windows ist die Voraussetzung erwartungsgemaess "
                          "nicht gegeben — genau deshalb gibt es XPLAT-30.")
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            self.assertTrue(
                _zweiter_bind_scheitert(port),
                "Ein zweiter Bind gelingt hier — die beiden Bind-Tests "
                "ueberspringen ab jetzt still und pruefen nichts mehr")
        finally:
            s.close()

    def test_auf_windows_erzwingt_erst_die_server_option_den_zweiten_bind(self):
        """Windows-Gegenstueck: haelt fest, WARUM die Bind-Tests hier skippen.

        Der Waechter oben kann auf Windows nichts pruefen — dort ueberspringen
        die beiden Bind-Tests erwartungsgemaess. Ungeprueft bliebe damit der
        GRUND, und genau der war schon einmal falsch: #698 nahm an, auf Windows
        gelinge ein zweiter Bind ohne Weiteres. Er gelingt nur **mit** der
        Option, die der Server setzt. Beides steht hier als Messung — faellt der
        Unterschied eines Tages weg, faellt dieser Test und nicht erst die
        stille Annahme dahinter.
        """
        if os.name != "nt":
            self.skipTest("Der Unterschied zwischen den beiden Bindern zeigt "
                          "sich nur auf Windows — gegen einen aktiven Listener "
                          "scheitert der zweite Bind sonst ohnehin.")
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            nackt = socket.socket()
            try:
                with self.assertRaises(OSError):
                    nackt.bind(("127.0.0.1", port))
            finally:
                nackt.close()

            self.assertFalse(
                _zweiter_bind_scheitert(port),
                "Mit den Optionen des Servers (SO_REUSEADDR) muss der zweite "
                "Bind auf Windows GELINGEN — sonst ueberspringen die beiden "
                "Bind-Tests hier aus einem anderen Grund als dem gemessenen")
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()

"""OUT-01: echter Wire-Loopback fuer den sACN-(E1.31-)Output.

Beweist OHNE Hardware, dass `SACNSender` ein spec-konformes E1.31-Paket
TATSAECHLICH ueber einen UDP-Socket auf die Leitung legt (Unicast auf Port 5568)
und ein Empfaenger es korrekt zurueckliest. Ergaenzt den vorhandenen
In-Memory-Test (test_audit_fixes_2026_06_08::TestSacnConformance, nur
`_pack_framing` -> Parser) um den realen Socket-Pfad.

Faellt sauber auf SKIP zurueck, falls die Umgebung keinen UDP-Loopback erlaubt
(Adresse/Port nicht bindbar, Sandbox) — dann bleibt die In-Memory-Konformitaet
die Absicherung.

QA-57: Wer hier sendet, holt seine Pakete auch wieder ab, und jeder Empfaenger
sitzt auf einem eigenen Loopback-Endpunkt — begruendet und gemessen in
`_WireTestBase`.
"""
import itertools
import os
import socket
import struct
import subprocess
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.sacn import SACNSender, SACN_PORT
from src.core.dmx.sacn_input import SACNReceiver


# QA-57: laufende Nummer fuer die private Loopback-Adresse je Empfaenger.
_EMPFAENGER_ZAEHLER = itertools.count()


def _empfaenger_adresse(index: int, pid: int | None = None) -> str:
    """Private Loopback-Adresse fuer den `index`-ten Empfaenger dieses Prozesses.

    Eigene Funktion statt einer Zeile in `_open_receiver`, damit sie **ohne**
    Zaehlerstand pruefbar ist: der Prozess-Test vergleicht sonst den n-ten
    Empfaenger des Elternprozesses mit dem ERSTEN des Kindes — die sind auch
    dann verschieden, wenn die PID gar nicht mit einginge. Gemessen: ohne diese
    Trennung blieb der Test gruen, obwohl der PID-Anteil entfernt war.

    127.0.0.0/8 ist vollstaendig Loopback; der Spec-Port 5568 bleibt, damit der
    Test weiterhin genau den Weg misst, den das Produkt geht.
    """
    if pid is None:
        pid = os.getpid()
    return f"127.{(pid >> 8) & 0xFF}.{pid & 0xFF}.{101 + index % 100}"


def _beschreibe(pkt: bytes) -> str:
    """Kennfelder eines liegengebliebenen Pakets — fuer die Fehlermeldung.

    Die Offsets kommen wie im Rest der Datei direkt aus dem Wire-Format
    (E1.31-2018): Source Name 44..108, Options 112, Universum 113..115. Ohne
    diese Angaben stuende im Fehlerfall nur eine Zahl da, und die beantwortet
    die entscheidende Frage nicht: aus welcher Quelle stammt das, was da liegt —
    aus diesem Test oder von aussen?

    Im Puffer kann auch etwas liegen, das gar kein E1.31-Paket ist (fremder
    Absender, abgeschnittenes Datagramm). Das darf den Waechter nicht mit einem
    IndexError zum Absturz bringen, sonst waere die eigentliche Meldung weg.
    """
    if len(pkt) < 115:
        return f"<{len(pkt)} B — kein E1.31-Paket>"
    quelle = pkt[44:108].split(b"\x00")[0].decode("utf-8", "replace")
    art = "Terminierung" if pkt[112] & 0x40 else "Daten"
    return (f"{art}(Quelle={quelle!r}, "
            f"Universum={struct.unpack('!H', pkt[113:115])[0]})")


class _WireTestBase(unittest.TestCase):
    """QA-57 — Endpunkt-Trennung und Puffer-Messung fuer alle Tests dieser Datei.

    **Was gemessen war (12.08.2026, diese Maschine).** Jeder Test dieser Datei
    band denselben Endpunkt 127.0.0.1:5568 und liess dort je DREI Pakete liegen:
    die Stream-Terminierungen, die `SACNSender.close()` laut OUT-06 pro
    bespieltem Universum dreimal sendet. (Die im Item vermuteten „bis zu fuenf
    Datenpakete" sind es im Normalfall nicht — die Sendeschleife liest pro
    Durchgang wieder eines ab.) Dass die Reste den naechsten Test bisher nicht
    trafen, war kein Verdienst: der Socket wurde am Testende geschlossen und
    verwarf sie — in 200 von 200 Messungen ueberlebte kein Paket den
    Socket-Wechsel.

    **Warum der Nachbar trotzdem rot wurde (#610).** Der Endpunkt ist nicht nur
    unter den Tests dieser Datei geteilt, sondern auch mit PARALLELEN Segmenten:
    `tests/test_sacn_source.py` baut echte Sender auf 127.0.0.1:5568. Gemessen
    landeten so 4 Fremdpakete im Puffer dieser Tests (ein Datenpaket mit
    voellig fremder Sequenz + drei Terminierungen). Und weil beide Seiten
    `SO_REUSEADDR` setzen, ist der zweite Bind auf dieselbe Adresse nicht etwa
    ein Fehler, sondern gelingt — die Pakete bekommt dann der ZULETZT gebundene
    Socket (gemessen). Ein blosses „vor der Messung aufraeumen" haette gegen
    diesen Weg nichts ausgerichtet.

    **Die Antwort, zwei Haelften — beide noetig.**

    1. `_open_receiver()` gibt JEDEM Empfaenger eine eigene Loopback-Adresse
       `127.<pid-hi>.<pid-lo>.<n>`; 127.0.0.0/8 ist vollstaendig Loopback. Der
       Spec-Port 5568 bleibt, damit der Test weiterhin genau den Weg misst, den
       das Produkt geht. Die PID ist mit drin, weil sonst zwei gleichzeitige
       Laeufe DIESER Datei wieder dieselbe Adresse belegten — und dank
       `SO_REUSEADDR` einander die Pakete wegnaehmen statt zu scheitern.
    2. `tearDown()` MISST danach, was im Puffer liegen geblieben ist, und faellt
       aus, sobald es mehr als nichts ist. Erst das macht aus „wer sendet, holt
       ab" (`_eigene_pakete_abholen`) eine gepruefte Eigenschaft statt einer
       Verabredung, an die sich der naechste Test halten mag oder nicht.

    Tests ohne echten Draht (Fake-Socket) erben die Basis mit; sie melden keinen
    Empfaenger an, und dann misst `tearDown` nichts — genau richtig, denn ohne
    Socket kann auch nichts liegen bleiben.
    """

    def setUp(self):
        self._empfaenger: list[socket.socket] = []

    def _open_receiver(self, timeout: float = 1.0) -> socket.socket:
        """Empfaenger auf EIGENER Loopback-Adresse, Spec-Port 5568.

        `OSError` (Adresse nicht bindbar, Port belegt, Sandbox) geht wie bisher
        an den Aufrufer -> der skippt.
        """
        adresse = _empfaenger_adresse(next(_EMPFAENGER_ZAEHLER))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((adresse, SACN_PORT))
        except OSError:
            sock.close()               # sonst bliebe der Socket am Skip haengen
            raise
        sock.settimeout(timeout)
        self._empfaenger.append(sock)  # ab jetzt bewacht (s. tearDown)
        return sock

    def _eigene_pakete_abholen(self, rx: socket.socket, sender: SACNSender,
                               universen=(), offen: int = 0,
                               frist: float = 0.5) -> None:
        """Sender schliessen und abholen, was dieser Test noch offen hat.

        `offen` = gesendete, aber noch nicht gelesene Datenpakete; dazu kommen
        die drei Stream-Terminierungen je Universum, die `close()` selbst noch
        auf die Leitung legt (OUT-06) — genau die blieben bisher liegen.

        Die Frist deckt Pakete ab, die im Moment des Aufrufs noch unterwegs
        sind. Ein von UDP wirklich verschlucktes Paket laeuft in die Frist und
        bleibt folgenlos: hier wird nichts zugesichert, was UDP nicht hergibt.
        Ob am Ende wirklich nichts liegen blieb, sagt nicht diese Methode,
        sondern die Messung in `tearDown`.
        """
        sender.close()
        offen += 3 * len(universen)
        rx.settimeout(0.05)
        ende = time.monotonic() + frist
        while offen > 0 and time.monotonic() < ende:
            try:
                rx.recvfrom(2048)
            except socket.timeout:
                continue
            offen -= 1

    @staticmethod
    def _rest_lesen(sock: socket.socket) -> list[str]:
        """Alles, was noch im Empfangspuffer steht — beschrieben, nicht gezaehlt."""
        rest = []
        sock.setblocking(False)
        while True:
            try:
                pkt, _addr = sock.recvfrom(2048)
            except (BlockingIOError, socket.timeout, OSError):
                break
            rest.append(_beschreibe(pkt))
        return rest

    def tearDown(self):
        """QA-57: nach JEDEM Test messen, ob der Puffer leer ist."""
        rest: list[str] = []
        for sock in self._empfaenger:
            rest.extend(self._rest_lesen(sock))
            sock.close()
        self._empfaenger.clear()
        self.assertEqual(
            rest, [],
            f"QA-57: {self._testMethodName} laesst {len(rest)} Paket(e) im "
            f"Empfangspuffer liegen — auf einem geteilten Endpunkt haette der "
            f"naechste Test sie als seine eigenen gelesen: {rest}")


class SacnLoopbackTest(_WireTestBase):
    def test_unicast_loopback_roundtrip(self):
        try:
            rx = self._open_receiver()
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback auf Port {SACN_PORT} ({e})")

        ziel = rx.getsockname()[0]
        sender = SACNSender(target_ip=ziel, source_name="LoopTest")
        dmx = bytes((i * 3 + 1) & 0xFF for i in range(512))
        pkt = None
        gesendet = 0
        try:
            for _ in range(5):                  # UDP darf droppen -> ein paar Versuche
                sender.send_dmx(7, dmx)
                gesendet += 1
                try:
                    pkt, _addr = rx.recvfrom(2048)
                    break
                except socket.timeout:
                    continue
            if pkt is None:
                # QA-02: Der Bind ist geglueckt -> der UDP-Loopback funktioniert in
                # dieser Umgebung. Kommt das Paket trotzdem nicht an, ist das eine
                # ECHTE Sender-Regression (kein Umgebungsproblem) -> failen statt
                # skippen, sonst bliebe ein kaputter sACN-Sender gruen/unsichtbar.
                self.fail("sACN-Paket trotz erfolgreichem Bind nicht empfangen "
                          "(Sender-Regression)")

            # ── Roh-Wire-Format pruefen (nicht nur Parser-Symmetrie) ──────────
            self.assertEqual(len(pkt), 638)                          # 512 DMX -> 638 B
            self.assertEqual(pkt[4:16], b"ASC-E1.17\x00\x00\x00")    # ACN Packet ID
            self.assertEqual(struct.unpack("!H", pkt[113:115])[0], 7)  # Universe-Feld
            self.assertEqual(pkt[125], 0x00)                         # DMX Start Code
            self.assertEqual(pkt[126:638], dmx)                      # DMX-Slots roh

            # ── und durch den echten Receiver zurueckparsen ──────────────────
            parsed = SACNReceiver._parse(SACNReceiver.__new__(SACNReceiver), pkt)
            self.assertIsNotNone(parsed)
            assert parsed is not None       # Narrowing fuer den Type-Checker
            universe, payload = parsed
            self.assertEqual(universe, 7)
            self.assertEqual(payload, dmx)
        finally:
            # QA-57: die Schleife bricht beim ersten Empfang ab — alles, was bis
            # dahin gesendet und nicht gelesen wurde, gehoert diesem Test und
            # wird hier abgeholt, samt der Terminierungen aus close().
            self._eigene_pakete_abholen(
                rx, sender, universen=(7,),
                offen=gesendet - (1 if pkt is not None else 0))

    def test_sequence_number_increments_on_wire(self):
        """Aufeinanderfolgende Frames tragen hochzaehlende Sequenznummern (Offset
        111) — wichtig, damit Empfaenger Reihenfolge/Verluste erkennen."""
        try:
            rx = self._open_receiver()
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback auf Port {SACN_PORT} ({e})")
        sender = SACNSender(target_ip=rx.getsockname()[0], source_name="LoopTest")
        gesendet = 0
        seqs: list[int] = []
        try:
            # ★ QA-57: Hier stand seit dem CI-Flake-Fix (#610) ein Leeren des
            # Empfangspuffers VOR der Messung — die Wirkung, nicht die Ursache.
            # Die Ursache ist weg: dieser Empfaenger hat einen eigenen Endpunkt,
            # in den weder der Nachbartest noch ein paralleles Segment sendet,
            # und jeder Test holt seine Pakete selbst ab (s. _WireTestBase).
            for _ in range(3):
                sender.send_dmx(1, bytes(512))
                gesendet += 1
                try:
                    pkt, _addr = rx.recvfrom(2048)
                except socket.timeout:
                    # QA-02: Bind ok -> ausbleibendes Paket ist eine Sender-
                    # Regression, kein Umgebungsproblem -> failen statt skippen.
                    self.fail("sACN-Paket trotz erfolgreichem Bind nicht empfangen "
                              "(Sender-Regression)")
                seqs.append(pkt[111])

            # ★ Streng MONOTON (mod 256) — nicht exakt +1.
            #
            # Die vorige Fassung verlangte `seqs[1] == seqs[0]+1` und damit
            # LUECKENLOSE Zustellung. Das sichert UDP nicht zu, auch nicht auf
            # dem Loopback unter Last: die CI faehrt drei Segmente parallel,
            # und der Test fiel dort sporadisch mit genau einem Schritt
            # Abstand aus (13 != 14, 160 != 161) — auf `main` ebenso wie auf
            # Feature-Branches, die sACN gar nicht anfassen.
            #
            # Geprueft wird jetzt, was der Kommentar immer schon sagte und was
            # der Empfaenger wirklich braucht: die Nummer geht VORWAERTS und
            # bleibt nicht stehen. Ein Rueckwaertssprung oder ein Stillstand
            # (die echten Sender-Regressionen) faellt weiter durch; der Deckel
            # haelt „irgendeine Zahl" draussen.
            def _abstand(a, b):
                return (b - a) & 0xFF

            d1, d2 = _abstand(seqs[0], seqs[1]), _abstand(seqs[1], seqs[2])
            for i, d in enumerate((d1, d2), start=1):
                self.assertGreaterEqual(
                    d, 1, f"Sequenz {i} steht still oder laeuft rueckwaerts "
                          f"({seqs}) — Empfaenger koennen Reihenfolge und "
                          f"Verluste dann nicht mehr erkennen")
                self.assertLessEqual(
                    d, 8, f"Sequenzsprung von {d} ({seqs}) ist zu gross fuer "
                          f"drei gesendete Frames")
        finally:
            self._eigene_pakete_abholen(rx, sender, universen=(1,),
                                        offen=gesendet - len(seqs))


class PufferHygieneTest(_WireTestBase):
    """QA-57: die beiden neuen Zusicherungen selbst auf den Pruefstand.

    Beide Proben fahren den echten Weg — echte Sockets, echter `SACNSender` —
    und der Waechter wird ueber den echten unittest-Ablauf (setUp -> Test ->
    tearDown) ausgeloest, nicht direkt aufgerufen. Die Probe-Testfaelle stehen
    ABSICHTLICH innerhalb der Testmethoden: pytest sammelt jede
    `unittest.TestCase`-Klasse eines Moduls ein, auch mit fuehrendem
    Unterstrich — auf Modulebene waere der absichtlich schlampige Fall ein
    dauerhaft roter Test in der Suite.
    """

    @staticmethod
    def _lauf(testklasse) -> unittest.TestResult:
        ergebnis = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(testklasse).run(ergebnis)
        return ergebnis

    def _skip_ohne_loopback(self, ergebnis: unittest.TestResult) -> None:
        if ergebnis.skipped:
            self.skipTest(f"Probefall ohne UDP-Loopback: {ergebnis.skipped}")

    def test_zwei_empfaenger_bekommen_getrennte_endpunkte(self):
        """Was an Empfaenger A gesendet wird, kommt NICHT bei B an.

        Gefahren wird der echte Sender: er muss die private Loopback-Adresse
        auch wirklich erreichen, sonst waere die Trennung mit einer stummen
        Leitung erkauft.
        """
        try:
            a = self._open_receiver(timeout=0.5)
            b = self._open_receiver(timeout=0.5)
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback auf Port {SACN_PORT} ({e})")
        self.assertNotEqual(a.getsockname(), b.getsockname(),
                            "zwei Empfaenger auf demselben Endpunkt — mit "
                            "SO_REUSEADDR faellt das nicht auf, kostet aber "
                            "genau die Trennung, um die es hier geht")

        sender = SACNSender(target_ip=a.getsockname()[0], source_name="LoopTest-A")
        try:
            sender.send_dmx(7, bytes(512))
            self.assertEqual(len(a.recvfrom(2048)[0]), 638)   # A hat es
            with self.assertRaises(socket.timeout):           # B nicht
                b.recvfrom(2048)
        finally:
            self._eigene_pakete_abholen(a, sender, universen=(7,))

    def test_zwei_prozesse_bekommen_getrennte_endpunkte(self):
        """Auch ZWEI gleichzeitige Laeufe dieser Datei duerfen sich nicht
        denselben Endpunkt greifen.

        Genau das passiert im segmentierten Gate-Lauf. Und es faellt nicht als
        Fehler auf: mit `SO_REUSEADDR` gelingt der zweite Bind (gemessen) — die
        Pakete bekommt dann lautlos der zuletzt gebundene Socket. Deshalb steckt
        die PID in der Adresse; hier laeuft ein echter zweiter Prozess dagegen.
        """
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        umgebung = dict(os.environ, PYTHONPATH=wurzel)
        fremd = subprocess.run(
            [sys.executable, "-c",
             "import tests.test_sacn_loopback as m;"
             "print(m._empfaenger_adresse(0))"],
            cwd=wurzel, env=umgebung, capture_output=True, text=True, timeout=30)
        self.assertEqual(fremd.returncode, 0, fremd.stderr)
        eigen = _empfaenger_adresse(0)      # GLEICHER Index, anderer Prozess
        self.assertNotEqual(
            eigen, fremd.stdout.strip(),
            "Zweiter Prozess landet beim gleichen Index auf demselben "
            "Endpunkt — dann nehmen sich zwei gleichzeitige Laeufe dieser "
            "Datei dank SO_REUSEADDR lautlos die Pakete weg.")

    def test_waechter_meldet_liegengebliebene_pakete(self):
        """NEGATIVPROBE: ein Test, der sendet und nichts abholt, wird rot —
        mit Anzahl und Herkunft im Klartext, und ohne an einem Datagramm zu
        zerschellen, das gar kein E1.31-Paket ist."""

        class _LaesstLiegen(_WireTestBase):
            def test_sendet_ohne_abzuholen(self):
                try:
                    rx = self._open_receiver()
                except OSError as e:
                    raise unittest.SkipTest(str(e))
                sender = SACNSender(target_ip=rx.getsockname()[0],
                                    source_name="LoopTest-Schlamperei")
                sender.send_dmx(3, bytes(512))   # 1 Datenpaket, ungelesen
                sender.close()                   # + 3 Terminierungen (OUT-06)
                fremd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    fremd.sendto(b"kaputt", rx.getsockname())   # kein E1.31
                finally:
                    fremd.close()

        ergebnis = self._lauf(_LaesstLiegen)
        self._skip_ohne_loopback(ergebnis)
        self.assertEqual(len(ergebnis.failures), 1,
                         f"Waechter hat nicht angeschlagen: {ergebnis.errors}")
        text = ergebnis.failures[0][1]
        self.assertIn("QA-57", text)
        self.assertIn("5 Paket(e)", text)     # 1 Daten + 3 Terminierungen + 1 Muell
        self.assertIn("Daten(Quelle='LoopTest-Schlamperei', Universum=3)", text)
        self.assertIn("Terminierung(Quelle='LoopTest-Schlamperei', Universum=3)", text)
        self.assertIn("kein E1.31-Paket", text)

    def test_waechter_schweigt_wenn_der_test_abholt(self):
        """POSITIVKONTROLLE: derselbe Ablauf MIT Aufraeumen bleibt gruen.

        Ohne diese Probe koennte der Waechter auch schlicht immer anschlagen —
        dann waere jede gruene Zeile dieser Datei nur ein Zufall der
        Reihenfolge.
        """

        class _RaeumtAuf(_WireTestBase):
            def test_sendet_und_holt_ab(self):
                try:
                    rx = self._open_receiver()
                except OSError as e:
                    raise unittest.SkipTest(str(e))
                sender = SACNSender(target_ip=rx.getsockname()[0],
                                    source_name="LoopTest-Sauber")
                sender.send_dmx(3, bytes(512))
                rx.recvfrom(2048)                # Datenpaket gelesen
                self._eigene_pakete_abholen(rx, sender, universen=(3,))
                # Abholen ohne Schliessen waere die halbe Miete: dann entstuenden
                # die Terminierungen gar nicht erst, der Puffer bliebe zufaellig
                # leer — und der Socket des Senders bliebe offen.
                self.assertIsNone(sender._sock, "Sender wurde nicht geschlossen")

        ergebnis = self._lauf(_RaeumtAuf)
        self._skip_ohne_loopback(ergebnis)
        self.assertEqual(ergebnis.testsRun, 1)
        self.assertEqual((ergebnis.failures, ergebnis.errors), ([], []),
                         "sauber aufgeraeumter Test wurde trotzdem rot")

    def test_ungelesene_datenpakete_werden_mit_abgeholt(self):
        """Der Fall aus QA-57 im Kleinen: 3 gesendet, 1 gelesen.

        Die zwei uebrigen sind es, die dem naechsten Test vor die Fuesse fielen.
        Der Test muss sie selbst abholen (`offen=2`) — und dann ist der Puffer
        leer. Zugleich Positivkontrolle fuer die Buchfuehrung: sie darf im
        Normalfall nicht anschlagen.
        """

        class _LiestNurEines(_WireTestBase):
            def test_drei_senden_eines_lesen(self):
                try:
                    rx = self._open_receiver()
                except OSError as e:
                    raise unittest.SkipTest(str(e))
                sender = SACNSender(target_ip=rx.getsockname()[0],
                                    source_name="LoopTest-Rest")
                for _ in range(3):
                    sender.send_dmx(3, bytes(512))
                rx.recvfrom(2048)
                self._eigene_pakete_abholen(rx, sender, universen=(3,), offen=2)

        ergebnis = self._lauf(_LiestNurEines)
        self._skip_ohne_loopback(ergebnis)
        self.assertEqual(ergebnis.testsRun, 1)
        self.assertEqual((ergebnis.failures, ergebnis.errors), ([], []),
                         "abgeholte Restpakete wurden trotzdem als liegen "
                         "geblieben gemeldet")


class _CaptureSock:
    """Fake-Socket: sammelt sendto-Aufrufe (kein echtes Netz noetig -> deterministisch)."""
    def __init__(self):
        self.sent = []

    def sendto(self, pkt, dest):
        self.sent.append((bytes(pkt), dest))

    def close(self):
        pass

    def setsockopt(self, *a):
        pass


class SacnStreamTerminationTest(_WireTestBase):
    """OUT-06: close() sendet je bespieltem Universum 3 Pakete mit gesetztem
    Stream_Terminated-Options-Bit, damit Empfaenger die Quelle sofort verwerfen.

    Erbt `_WireTestBase` nur, damit die QA-57-Regel fuer JEDEN Test dieser Datei
    gilt: wer einen Empfaenger oeffnet, wird gemessen. Diese Tests oeffnen
    keinen (Fake-Socket) und koennen deshalb auch nichts hinterlassen.
    """

    # Options-Byte-Offset im E1.31-Paket: Root-Layer 38 + Framing bis Options
    # (Flags&Len2+Vector4+Source64+Prio1+SyncAddr2+Seq1 = 74) = 112.
    _OPTIONS_OFFSET = 112

    def _sender_with_fake_sock(self, universes=(1, 7)):
        """Sender an ``__init__`` vorbei, mit Fake-Socket.

        **Seit OUT-06 (CID-Persistenz) liegen Sequenz und Universums-Besitz in der
        prozessweiten Quelle**, nicht mehr in einem ``_seq``-Dict am Sender. Der
        Aufbau holt sich deshalb eine echte Quelle und meldet die Universen dort
        an — sonst gaebe ``release()`` beim ``close()`` ``None`` zurueck („gehoert
        dir nicht") und es wuerde gar nichts terminiert. Bewusst umgeschrieben
        statt geloescht: die Aussagen der Tests gelten unveraendert.
        """
        from src.core.dmx.sacn_source import sacn_source

        s = SACNSender.__new__(SACNSender)
        s._target_ip = None
        s._source_name = "TermTest"
        s._source = sacn_source()
        s._cid = b"\x00" * 16
        s._token = s._source.new_token()
        s._universes = set(universes)
        for universe in universes:
            s._source.next_seq(universe, s._token)   # Besitz anmelden
        s._sock = _CaptureSock()
        return s

    def test_close_sends_three_terminations_per_universe(self):
        s = self._sender_with_fake_sock()
        sock = s._sock
        s.close()
        # 2 Universen x 3 Pakete = 6.
        self.assertEqual(len(sock.sent), 6)
        # Jedes Paket hat das Stream_Terminated-Bit (0x40) im Options-Byte gesetzt.
        for pkt, _dest in sock.sent:
            self.assertEqual(pkt[self._OPTIONS_OFFSET], 0x40)
        # Multicast-Ziele beider Universen vertreten.
        dests = {d[0] for _p, d in sock.sent}
        self.assertIn("239.255.0.1", dests)
        self.assertIn("239.255.0.7", dests)
        # Socket danach geschlossen.
        self.assertIsNone(s._sock)

    def test_normal_packet_has_no_terminated_bit(self):
        from src.core.dmx.sacn import _pack_framing
        pkt = _pack_framing(bytes(512), 1, 0, "X", b"\x00" * 16)
        self.assertEqual(pkt[self._OPTIONS_OFFSET], 0x00)

    def test_close_without_universes_is_safe(self):
        s = self._sender_with_fake_sock(universes=())
        sock = s._sock
        s.close()                         # nichts gesendet, kein Fehler
        self.assertEqual(sock.sent, [])
        self.assertIsNone(s._sock)


if __name__ == "__main__":
    unittest.main()

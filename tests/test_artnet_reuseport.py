"""XPLAT-03 — Art-Net-Input setzt SO_REUSEADDR **und** SO_REUSEPORT.

Damit zwei Programme denselben UDP-Port teilen koennen, muessen auf Linux
**beide Seiten** eine passende Option setzen — und zwar dieselbe. Das ist der
Punkt, den die fruehere Fassung dieses Kommentars falsch hatte: sie behauptete,
`SO_REUSEADDR` teile den Port auf Linux gar nicht. Gemessen (Unicast-Loopback,
zweiter `bind()` auf denselben Port, `KernelPortSharingTest` unten):

| fremde App | LightOS | zweiter `bind()` |
|---|---|---|
| ohne Option | egal | **scheitert** — dann geht es prinzipiell nicht |
| `SO_REUSEADDR` | `SO_REUSEADDR` | gelingt |
| `SO_REUSEADDR` | nur `SO_REUSEPORT` | **scheitert** |
| `SO_REUSEPORT` | nur `SO_REUSEADDR` | **scheitert** |
| `SO_REUSEPORT` | `SO_REUSEPORT` | gelingt |
| beliebige Option | **beide** | gelingt |

Daraus folgt die Begruendung fuer den Code: **beide Optionen zu setzen ist die
einzige Wahl, bei der der `bind()` gegen jede fremde Konfiguration gelingt.**
Mit nur einer der beiden scheitert er schon, sobald die andere App sich fuer die
jeweils andere entschieden hat (QLC+ … auf 6454) — und das faellt nicht als
Fehler auf, sondern als Stille.

★ **Der Bind ist aber nur die halbe Frage — die andere ist die ZUSTELLUNG, und
die haengt nicht an den Optionen, sondern an der Adressierung** (CDX-51,
gemessen in `ZustellungTest`):

| Adressierung | zwei Empfaenger auf demselben Port |
|---|---|
| **Broadcast** (Art-Net-Normalfall) | **beide** bekommen jedes Paket — mit jeder Optionskombination |
| **Unicast** | **genau einer** bekommt alles, der andere nichts |

Fuer den Regelbetrieb ist damit alles gut: Art-Net-Sender broadcasten auf
255.255.255.255, und LightOS bekommt seine Kopie neben QLC+. Schickt eine
Quelle dagegen **unicast** an genau diesen Rechner, kann das Paket bei der
anderen App landen und LightOS bleibt still — daran aendert keine der beiden
Optionen etwas. Eine frueherer Fassung dieses Kopfes hat aus dem gelungenen
Bind auf die Zustellung geschlossen; das war zu weit gegriffen.

Der sACN-Input macht es bereits so; hier wird Art-Net angeglichen. Die
Verdrahtung selbst ist plattform-unabhaengig ueber einen Fake-Socket geprueft
(echte Constants gibt es auf Windows nicht); die Tabelle oben misst echtes
Kernel-Verhalten und laeuft nur auf Linux.
"""
from __future__ import annotations
import socket as _socket
import sys
import time
import unittest

import src.core.dmx.artnet_input as artnet_input

REUSEPORT = 15   # willkürlicher Wert; auf Windows fehlt socket.SO_REUSEPORT ganz


class _FakeSock:
    def __init__(self):
        self.opts = []
        self.bound = None
        self.timeout = None
        self.closed = False

    def setsockopt(self, level, opt, val):
        self.opts.append((level, opt, val))

    def bind(self, addr):
        self.bound = addr

    def settimeout(self, t):
        self.timeout = t

    def recvfrom(self, n):
        time.sleep(0.02)                 # kein tight-spin im RX-Thread
        raise _socket.timeout()

    def close(self):
        self.closed = True


def _patch_socket(monkeypatch, sock):
    monkeypatch.setattr(artnet_input.socket, "SO_REUSEPORT", REUSEPORT, raising=False)
    monkeypatch.setattr(artnet_input.socket, "socket", lambda *a, **k: sock)


def test_artnet_sets_reuseport_and_reuseaddr(monkeypatch):
    sock = _FakeSock()
    _patch_socket(monkeypatch, sock)
    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        assert (artnet_input.socket.SOL_SOCKET,
                artnet_input.socket.SO_REUSEADDR, 1) in sock.opts
        assert (artnet_input.socket.SOL_SOCKET, REUSEPORT, 1) in sock.opts   # neu
        assert sock.bound == ("0.0.0.0", artnet_input.ARTNET_PORT)
    finally:
        inp.stop()
    assert sock.closed


def test_artnet_binds_even_if_reuseport_unsupported(monkeypatch):
    # setsockopt(SO_REUSEPORT) wirft (wie auf Windows / altem Kernel) -> der guarded
    # Block schluckt es und bind() läuft trotzdem (Input bleibt funktionsfähig).
    class _Reject(_FakeSock):
        def setsockopt(self, level, opt, val):
            if opt == REUSEPORT:
                raise OSError("SO_REUSEPORT not supported")
            super().setsockopt(level, opt, val)

    sock = _Reject()
    _patch_socket(monkeypatch, sock)
    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        assert sock.bound == ("0.0.0.0", artnet_input.ARTNET_PORT)   # trotzdem gebunden
        assert inp.is_running()
    finally:
        inp.stop()


def test_reuseport_applied_before_bind(monkeypatch):
    # Reihenfolge: die Socket-Optionen müssen VOR bind() gesetzt sein.
    events = []
    sock = _FakeSock()

    real_setsockopt = sock.setsockopt
    real_bind = sock.bind
    sock.setsockopt = lambda l, o, v: (events.append(("opt", o)), real_setsockopt(l, o, v))[1]
    sock.bind = lambda a: (events.append(("bind", a)), real_bind(a))[1]
    _patch_socket(monkeypatch, sock)

    inp = artnet_input.ArtNetReceiver()
    try:
        inp.start()
        opt_idxs = [i for i, e in enumerate(events) if e[0] == "opt"]
        bind_idx = next(i for i, e in enumerate(events) if e[0] == "bind")
        assert opt_idxs and max(opt_idxs) < bind_idx     # alle Optionen vor bind
    finally:
        inp.stop()


# ════════════════════════════════════════════════════════════════════════════
# XPLAT-03-DOC: die Tabelle im Modulkopf — gemessen statt behauptet
# ════════════════════════════════════════════════════════════════════════════

class KernelPortSharingTest(unittest.TestCase):
    """Charakterisiert das Kernel-Verhalten, auf dem `_open_socket` beruht.

    Das ist ausdruecklich **kein** Test unseres Codes, sondern der Beleg fuer
    seine Begruendung: er wird rot, wenn Linux seine Regeln aendert — und genau
    dann muesste der Kommentar im Modulkopf neu geschrieben werden. Ohne diesen
    Test bliebe dort eine Behauptung stehen, die schon einmal falsch war.

    Bindet auf einem vom Kernel vergebenen Port (`bind(..., 0)`), nicht auf
    6454: ein fester Port waere genau der Fehler, den QA-57 aufgedeckt hat —
    parallele Segmente wuerden sich den Endpunkt streitig machen.
    """

    def _zweiter_bind_gelingt(self, opts_a, opts_b) -> bool:
        a = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        self.addCleanup(a.close)
        for o in opts_a:
            a.setsockopt(_socket.SOL_SOCKET, o, 1)
        try:
            a.bind(("127.0.0.1", 0))
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback in dieser Umgebung ({e})")
        port = a.getsockname()[1]
        b = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        self.addCleanup(b.close)
        for o in opts_b:
            b.setsockopt(_socket.SOL_SOCKET, o, 1)
        try:
            b.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

    def setUp(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("misst Linux-Kernel-Verhalten")
        self.RA = _socket.SO_REUSEADDR
        self.RP = _socket.SO_REUSEPORT      # auf Windows nicht vorhanden

    def test_ohne_option_scheitert_der_zweite_bind(self):
        """POSITIVKONTROLLE der Messmethode: ohne Option MUSS es scheitern.

        Fehlt diese Probe, koennte `_zweiter_bind_gelingt` immer True liefern
        (z.B. weil der Port in Wahrheit gar nicht belegt war) und alle uebrigen
        Faelle bestuenden, ohne etwas zu unterscheiden."""
        self.assertFalse(self._zweiter_bind_gelingt([], []))

    def test_dieselbe_option_auf_beiden_seiten_teilt_den_port(self):
        self.assertTrue(self._zweiter_bind_gelingt([self.RA], [self.RA]),
                        "SO_REUSEADDR teilt den UDP-Port sehr wohl — die alte "
                        "Fassung des Modulkopfs behauptete das Gegenteil")
        self.assertTrue(self._zweiter_bind_gelingt([self.RP], [self.RP]))

    def test_gemischte_optionen_teilen_den_port_nicht(self):
        """Der Fall, der den Input still bleiben laesst."""
        self.assertFalse(self._zweiter_bind_gelingt([self.RA], [self.RP]))
        self.assertFalse(self._zweiter_bind_gelingt([self.RP], [self.RA]))

    def test_beide_optionen_halten_gegen_jede_fremde_wahl(self):
        """★ Die eigentliche Begruendung fuer `_open_socket`.

        Wer hier eine der beiden Optionen entfernt, verliert genau die Faelle,
        in denen die fremde App sich anders entschieden hat."""
        for fremd in ([self.RA], [self.RP], [self.RA, self.RP]):
            with self.subTest(fremde_app=fremd):
                self.assertTrue(
                    self._zweiter_bind_gelingt(fremd, [self.RA, self.RP]))


class ZustellungTest(unittest.TestCase):
    """CDX-51: Der Bind ist nur die halbe Frage — die andere ist die Zustellung.

    Die vorige Fassung dieser Datei pruefte ausschliesslich, ob der zweite
    ``bind()`` gelingt, und der Modulkopf folgerte daraus, beide Optionen zu
    setzen halte „gegen JEDE fremde Konfiguration". Das war zu weit gegriffen:
    ein gelungener Bind sagt nichts darueber, wer die Pakete **bekommt**.

    Gemessen (und deshalb steht es jetzt im Kopf):

    * **Broadcast** — beide Empfaenger bekommen jedes Paket, mit jeder
      Optionskombination. Das ist der Art-Net-Normalfall, und deshalb
      funktioniert der Parallelbetrieb mit QLC+ ueberhaupt.
    * **Unicast** — genau EIN Empfaenger bekommt alles. Daran aendert keine der
      beiden Optionen etwas; es ist eine Eigenschaft der Adressierung.

    Der Befund stammt aus einem Codex-Review und ist hier nachgemessen, statt
    ihn zu uebernehmen oder abzutun.
    """

    def setUp(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("misst Linux-Kernel-Verhalten")

    def _zwei_empfaenger(self, opts, bind_addr="127.0.0.1"):
        socks, port = [], None
        for _ in range(2):
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            self.addCleanup(s.close)
            for o in opts:
                s.setsockopt(_socket.SOL_SOCKET, o, 1)
            try:
                s.bind((bind_addr, 0 if port is None else port))
            except OSError as e:
                self.skipTest(f"kein UDP-Loopback ({e})")
            if port is None:
                port = s.getsockname()[1]
            s.settimeout(0.1)
            socks.append(s)
        return socks, port

    @staticmethod
    def _senden_und_zaehlen(socks, ziel, port, n=6):
        tx = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        tx.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
        try:
            for i in range(n):
                tx.sendto(b"artnet-probe-%d" % i, (ziel, port))
            # ÄQUIVALENTE MUTANTE (nachgemessen): dieses Warten
            # wegzulassen laesst alle Tests gruen — auf einem unbelasteten
            # Loopback ist das Paket schon da, wenn `sendto` zurueckkehrt. Es
            # bleibt trotzdem stehen: unter Last (Gate mit -j 3, parallele
            # Agenten) ist die Zustellung nicht mehr instantan, und ein Test,
            # der dann sporadisch „0 Pakete" misst, waere genau die Sorte
            # Flake, die dieses Repo schon zweimal beschaeftigt hat (QA-57,
            # PROC-02c). Vorsorge gegen Last, nicht gegen den Normalfall.
            time.sleep(0.08)
        finally:
            tx.close()
        zaehler = []
        for s in socks:
            c = 0
            try:
                while True:
                    s.recvfrom(256)
                    c += 1
            except OSError:
                pass
            zaehler.append(c)
        return zaehler

    def test_broadcast_erreicht_BEIDE_empfaenger(self):
        """Der Fall, der den Parallelbetrieb mit QLC+ traegt."""
        for name, opts in (("REUSEADDR", [_socket.SO_REUSEADDR]),
                           ("REUSEPORT", [_socket.SO_REUSEPORT]),
                           ("beide", [_socket.SO_REUSEADDR,
                                      _socket.SO_REUSEPORT])):
            with self.subTest(optionen=name):
                socks, port = self._zwei_empfaenger(opts, "0.0.0.0")
                got = self._senden_und_zaehlen(socks, "255.255.255.255", port)
                self.assertEqual(
                    [6, 6], got,
                    f"Broadcast muss BEIDE erreichen ({name}), bekam {got} — "
                    "sonst traegt der Parallelbetrieb mit einer zweiten "
                    "Art-Net-App nicht")

    def test_unicast_erreicht_nur_EINEN_empfaenger(self):
        """Die Grenze, die der Modulkopf frueher verschwieg.

        Sie ist keine Schwaeche unseres Codes und durch keine Option zu
        beheben — aber sie gehoert benannt, weil „beide Optionen gesetzt" sonst
        als Zusicherung gelesen wird, die sie nicht ist.
        """
        socks, port = self._zwei_empfaenger([_socket.SO_REUSEADDR,
                                             _socket.SO_REUSEPORT])
        got = self._senden_und_zaehlen(socks, "127.0.0.1", port)
        self.assertEqual(
            6, sum(got), f"alle Pakete muessen ankommen, bekam {got}")
        self.assertIn(
            0, got,
            f"bei Unicast darf genau EIN Empfaenger alles bekommen, bekam "
            f"{got} — waere das anders, muesste der Modulkopf umgeschrieben "
            f"werden")

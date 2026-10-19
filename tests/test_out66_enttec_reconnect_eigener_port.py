"""OUT-66 — der Enttec-Reconnect nimmt nur den EIGENEN Dongle.

Befund (Review zu OUT-64): ``EnttecPro._try_reconnect`` oeffnete den ERSTEN per
VID/PID gefundenen Enttec. Bei zwei Dongles war das oft der des anderen
Universums — unter Linux sogar, wenn der belegt war (ohne Exklusiv-Sperre darf
jeder Prozess denselben Port oeffnen). Dann schrieben zwei Universen auf einen
Dongle, und die NOT-AUS-Sperre je Ausgabeweg (OUT-64) griff nicht.

Fix: Wiederfinden per USB-Seriennummer, sonst nur der eigene Portname bzw. der
einzige sichtbare Enttec (SERIAL-02 bleibt); Ports und Seriennummern anderer
Instanzen scheiden aus; unter POSIX wird mit ``exclusive=True`` geoeffnet; der
Weg-Schluessel der NOT-AUS-Sperre ist der konfigurierte Port (plus der neue).

Keine Hardware: ``comports()`` und ``serial.Serial`` sind Attrappen.
"""
from __future__ import annotations

import errno
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import serial                                                    # noqa: E402
import serial.tools.list_ports                                   # noqa: E402
from src.core.dmx import enttec_pro                              # noqa: E402
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_PID, ENTTEC_VID  # noqa: E402

POSIX = os.name == "posix"
# Portnamen der jeweiligen Plattform, damit _port_key (Gross-/Kleinschreibung
# unter Windows, realpath unter POSIX) nichts Unerwartetes tut.
if POSIX:
    P0, P1, P2, P3 = ("/dev/ttyFAKE_OUT66_0", "/dev/ttyFAKE_OUT66_1",
                      "/dev/ttyFAKE_OUT66_2", "/dev/ttyFAKE_OUT66_3")
else:
    P0, P1, P2, P3 = "COM90", "COM91", "COM92", "COM93"


class _Welt:
    """Was der Rechner gerade sieht: Enttec-Ports (device -> Seriennummer),
    welche Ports sich oeffnen lassen, und wer welchen exklusiv haelt."""

    def __init__(self):
        self.enttecs: dict[str, str | None] = {}
        self.fremd_exklusiv: set[str] = set()     # anderer Prozess haelt flock
        self.oeffnungen: list[tuple[str, dict]] = []

    def comports(self, *_a, **_k):
        return [SimpleNamespace(device=d, vid=ENTTEC_VID, pid=ENTTEC_PID,
                                serial_number=sn)
                for d, sn in self.enttecs.items()]


WELT = _Welt()


class _FakeSerial:
    def __init__(self, port, baud, timeout=1, write_timeout=0.5, **kw):
        WELT.oeffnungen.append((port, dict(kw)))
        if port not in WELT.enttecs:
            raise serial.SerialException(f"could not open port {port}")
        if kw.get("exclusive") and port in WELT.fremd_exklusiv:
            raise serial.SerialException(
                errno.EWOULDBLOCK,
                f"Could not exclusively lock port {port}: busy")
        self.port = port
        self.is_open = True
        self.writes: list[bytes] = []

    def write(self, data):
        self.writes.append(bytes(data))

    def reset_output_buffer(self):
        pass

    def close(self):
        self.is_open = False


class _Basis(unittest.TestCase):
    def setUp(self):
        global WELT
        WELT = _Welt()
        p1 = mock.patch.object(serial.tools.list_ports, "comports",
                               lambda *a, **k: WELT.comports())
        p2 = mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        self.geraete: list[EnttecPro] = []
        self.addCleanup(self._alle_zu)

    def _alle_zu(self):
        for d in self.geraete:
            d.close()

    def _neu(self, port) -> EnttecPro:
        d = EnttecPro(port)
        self.geraete.append(d)
        return d

    @staticmethod
    def _abziehen(dev: EnttecPro):
        """Port gilt als tot (Watchdog), Drossel aus -> naechster Frame versucht
        den Reconnect."""
        dev._disable()
        dev._last_reconnect = -1e9

    @staticmethod
    def _reconnect(dev: EnttecPro):
        dev._last_reconnect = -1e9
        dev.send_dmx(bytes(512))


class ZweiDongles(_Basis):

    def test_mit_seriennummer_nie_den_fremden(self):
        WELT.enttecs = {P0: "AAA", P1: "BBB"}
        a, b = self._neu(P0), self._neu(P1)
        self.assertEqual(("AAA", "BBB"), (a._seriennr, b._seriennr))
        self._abziehen(a)
        del WELT.enttecs[P0]                     # A abgezogen, B steckt noch
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled(), "A darf B's Dongle nicht uebernehmen")
        self.assertEqual(P0, a.port)
        self.assertNotIn(P1, [p for p, _ in WELT.oeffnungen],
                         "Reconnect oeffnete den Port des anderen Universums")

    def test_ohne_seriennummer_belegter_port_ausgelassen(self):
        # System meldet keine Seriennummern: nur noch B's Dongle sichtbar ->
        # "genau ein Enttec" — aber den hat eine andere Instanz offen.
        WELT.enttecs = {P0: None, P1: None}
        a, b = self._neu(P0), self._neu(P1)
        self._abziehen(a)
        del WELT.enttecs[P0]
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self.assertNotIn(P1, [p for p, _ in WELT.oeffnungen])

    def test_ohne_seriennummer_zwei_fremde_sichtbar_nimmt_keinen(self):
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self._abziehen(a)
        # A kommt (vielleicht) an P2 wieder, dazu steckt ein fremder an P1:
        # nicht eindeutig -> keinen von beiden nehmen.
        WELT.enttecs = {P1: None, P2: None}
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self.assertFalse({P1, P2} & {p for p, _ in WELT.oeffnungen})

    def test_fremde_seriennummer_auf_alter_nummer_nicht_genommen(self):
        WELT.enttecs = {P0: "AAA"}
        a = self._neu(P0)
        self._abziehen(a)
        WELT.enttecs = {P0: "ZZZ"}               # anderer Dongle hat die Nummer
        # Review 2: ZZZ gehoert einer ANDEREN konfigurierten Ausgabe (sonst
        # waere es ein Ersatzgeraet und wuerde uebernommen).
        a.setze_fremde_seriennr({"ZZZ"})
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self.assertEqual([], WELT.oeffnungen)

    def test_seriennummer_einer_anderen_instanz_wird_nicht_genommen(self):
        # B ist selbst gerade tot (Port zu), seine Seriennummer gehoert ihm
        # aber weiter. A (ohne bekannte Nummer) sieht nur B's Dongle.
        WELT.enttecs = {P0: None, P1: "BBB"}
        a, b = self._neu(P0), self._neu(P1)
        self.assertIsNone(a._seriennr)
        self._abziehen(a)
        self._abziehen(b)
        WELT.enttecs = {P2: "BBB"}               # nur B's Dongle, neue Nummer
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self._reconnect(b)
        self.assertFalse(b.is_disabled(), "B findet seinen Dongle (SERIAL-02)")
        self.assertEqual(P2, b.port)

    @unittest.skipUnless(POSIX, "Exklusiv-Sperre nur unter POSIX")
    def test_anderer_prozess_haelt_port_exklusiv(self):
        # Worker-Prozess-Fall: B lebt in einem anderen Prozess (keine
        # gemeinsame Registry), haelt seinen Port aber exklusiv.
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self._abziehen(a)
        WELT.enttecs = {P1: None}
        WELT.fremd_exklusiv = {P1}
        self._reconnect(a)
        self.assertTrue(a.is_disabled(), "fremd exklusiv gehaltener Port genommen")
        self.assertEqual(P0, a.port)

    def test_ohne_seriennummer_zweiter_enttec_von_anderer_instanz_belegt(self):
        # Review: B (ohne Seriennummer) haelt P1 offen, A kommt an P2 zurueck.
        # Zwei Enttec sichtbar -> ohne Seriennummer NICHT eindeutig; A bleibt
        # aus und oeffnet P2 nicht (Regel "genau EIN sichtbarer Enttec").
        WELT.enttecs = {P0: None, P1: None}
        a, b = self._neu(P0), self._neu(P1)
        self._abziehen(a)
        WELT.enttecs = {P1: None, P2: None}
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self.assertNotIn(P2, [p for p, _ in WELT.oeffnungen])


class Serial02BleibtHeil(_Basis):

    def test_einzelner_dongle_an_neuer_nummer_wird_gefunden(self):
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self._abziehen(a)
        WELT.enttecs = {P3: None}                # Replug -> neue Nummer
        self._reconnect(a)
        self.assertFalse(a.is_disabled())
        self.assertEqual(P3, a.port)
        self.assertEqual(P0, a.konfig_port, "konfigurierter Port bleibt")

    def test_gleiche_seriennummer_an_neuer_nummer_neben_fremdem(self):
        WELT.enttecs = {P0: "AAA", P1: "BBB"}
        a, b = self._neu(P0), self._neu(P1)
        self._abziehen(a)
        WELT.enttecs = {P1: "BBB", P3: "AAA"}
        self._reconnect(a)
        self.assertFalse(a.is_disabled())
        self.assertEqual(P3, a.port)

    def test_alte_nummer_als_fallback_wenn_noch_nicht_gelistet(self):
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self._abziehen(a)
        with mock.patch.object(enttec_pro, "enttec_kandidaten", lambda: []):
            self._reconnect(a)
        self.assertFalse(a.is_disabled())
        self.assertEqual(P0, a.port)


class Exklusiv(_Basis):

    @unittest.skipUnless(POSIX, "nur POSIX")
    def test_posix_oeffnet_exklusiv_auch_beim_reconnect(self):
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self.assertTrue(WELT.oeffnungen[-1][1].get("exclusive"))
        self._abziehen(a)
        WELT.enttecs = {P3: None}
        self._reconnect(a)
        self.assertEqual(P3, WELT.oeffnungen[-1][0])
        self.assertTrue(WELT.oeffnungen[-1][1].get("exclusive"))

    @unittest.skipUnless(POSIX, "nur POSIX")
    def test_eigener_port_fremd_gesperrt_wird_trotzdem_geoeffnet(self):
        # OUT-54: der KONFIGURIERTE Port wird nicht wegen einer Sperre
        # verweigert — nur gewarnt und geteilt geoeffnet.
        WELT.enttecs = {P0: None}
        WELT.fremd_exklusiv = {P0}
        a = self._neu(P0)
        self.assertTrue(a.is_open())
        self.assertNotIn("exclusive", WELT.oeffnungen[-1][1])

    @unittest.skipIf(POSIX, "nur Windows")
    def test_windows_ohne_exclusive_argument(self):
        WELT.enttecs = {P0: None}
        self._neu(P0)
        self.assertNotIn("exclusive", WELT.oeffnungen[-1][1])


class ErstesOeffnen(_Basis):
    """Review OUT-66: auch das ERSTE Oeffnen (frisch gestarteter Worker,
    Oeffnungs-Neuversuch im Worker) darf keinen fremden Dongle als eigenen
    lernen."""

    @unittest.skipUnless(POSIX, "Exklusiv-Sperre nur unter POSIX")
    def test_fremd_exklusiv_gehalten_keine_seriennummer_gelernt(self):
        # Vertauscht eingesteckt: an A's Port P0 haengt B's Dongle, B's Worker
        # haelt ihn exklusiv. A oeffnet (OUT-54) geteilt — lernt BBB aber nicht.
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        WELT.fremd_exklusiv = {P0}
        a = self._neu(P0)
        self.assertTrue(a.is_open())
        self.assertIsNone(a._seriennr, "fremde Seriennummer als eigene gelernt")

    def test_neustart_mit_bekannter_seriennummer_sucht_eigenen_dongle(self):
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        a = EnttecPro(P0, seriennr="AAA")
        self.geraete.append(a)
        self.assertEqual(P1, a.port, "Worker-Neustart nahm den fremden Dongle")
        self.assertEqual(P0, a.konfig_port)
        self.assertEqual("AAA", a._seriennr)

    def test_neustart_eigener_nicht_da_fremder_am_port_wirft(self):
        WELT.enttecs = {P0: "BBB"}
        WELT.oeffnungen.clear()
        with self.assertRaises(serial.SerialException):
            # Review 2: BBB kennt eine andere Ausgabe -> deren Dongle.
            self.geraete.append(EnttecPro(P0, seriennr="AAA", fremde={"BBB"}))
        self.assertEqual([], WELT.oeffnungen)

    def test_neustart_mit_seriennummer_am_eigenen_port(self):
        WELT.enttecs = {P0: "AAA", P1: "AAA2"}
        a = EnttecPro(P0, seriennr="AAA")
        self.geraete.append(a)
        self.assertEqual(P0, a.port)

    def test_worker_fabrik_reicht_seriennummer_weiter(self):
        from src.core.dmx import serial_process as sp
        port_akt, sn = SimpleNamespace(value=b""), SimpleNamespace(value=b"")
        WELT.enttecs = {P0: "AAA"}
        fabrik = sp._enttec_fabrik(EnttecPro, P0, port_akt, sn)
        a = fabrik()
        self.assertEqual(b"AAA", sn.value)
        self.assertEqual(P0.encode(), port_akt.value)
        a.close()
        # Worker stirbt; beim Neustart haengt B's Dongle an P0, A's an P3.
        WELT.enttecs = {P0: "BBB", P3: "AAA"}
        a2 = fabrik()
        self.geraete.append(a2)
        self.assertEqual(P3, a2.port)
        self.assertEqual(P3.encode(), port_akt.value,
                         "aktueller Port nicht an den Proxy gemeldet")

    def test_worker_main_nutzt_die_fabrik(self):
        import inspect
        from src.core.dmx import serial_process as sp
        self.assertIn("_enttec_fabrik", inspect.getsource(sp._worker_main))


class _FakeProc:
    exitcode = None

    def start(self):
        pass

    def is_alive(self):
        return True

    def join(self, timeout=None):
        pass

    def terminate(self):
        pass


class NotAusProxy(unittest.TestCase):
    """Review OUT-66: Im Standardbetrieb steckt der Prozess-Proxy dazwischen.
    Folgt sein Worker dem Dongle an eine neue Nummer, meldet er sie ueber
    ``port_aktuell`` — die NOT-AUS-Sperre greift auch dort."""

    def setUp(self):
        from src.core.dmx import output_manager as om_mod
        from src.core.dmx import serial_process as sp
        self.sp = sp
        self.proxies = []

        def mach(port):
            d = sp.EnttecProcessProxy(port, _process_factory=_FakeProc)
            self.proxies.append(d)
            return d
        p = mock.patch.object(om_mod, "_make_enttec_device", mach)
        p.start(); self.addCleanup(p.stop)
        p2 = mock.patch("src.core.dmx.port_check.warne_wenn_belegt",
                        lambda *_a, **_k: None, create=True)
        p2.start(); self.addCleanup(p2.stop)
        self.om = om_mod.OutputManager()
        for u in (1, 2):
            self.om.add_universe(u)
        self.addCleanup(self._zu)

    def _zu(self):
        for u in (1, 2):
            try:
                self.om.remove_output(u)
            except Exception:
                pass
        for d in self.proxies:
            d.close()

    def test_sperre_haelt_ueber_gemeldeten_neuen_port(self):
        self.om.add_enttec(1, P0)
        a = self.om._enttec_outputs[1]
        self.om.universes[1].set_channel(40, 255)
        self.om.set_laser_estop_mask({1: frozenset({40})}, True)
        # Worker folgt dem Dongle nach P3 (SERIAL-02), ist dort verbunden und
        # meldet das.
        self.sp._schreib_text(a._port_akt, P3, self.sp.PORT_BYTES)
        a._status.value = self.sp.ST_OK
        self.assertEqual(P3, a.port_aktuell)
        self.assertEqual(P0, a.port)
        self.assertIn(("enttec", P3), self.om._wege_enttec(a))
        self.om.universes[2].set_channel(40, 255)
        self.om.add_enttec(2, P3)
        self.assertNotIn(1, self.om._enttec_outputs,
                         "U1 schreibt weiter auf den Dongle an P3")
        b = self.om._enttec_outputs[2]
        self.assertTrue(self.om._werte_fuer(self.om._laser_estop_wege,
                                            self.om._wege_enttec(b)),
                        "U2 auf neuer Nummer ohne NOT-AUS-Sperre")
        self.om._send_all()
        self.assertEqual(0, bytes(b._buf.get_obj())[39],
                         "OUT-66: NOT-AUS ueber die neue Portnummer umgangen")

    def test_ohne_rueckmeldung_konfigurierter_port(self):
        d = self.sp.EnttecProcessProxy(P0, _process_factory=_FakeProc)
        self.proxies.append(d)
        self.assertEqual(P0, d.port_aktuell)
        self.assertIsNone(d.seriennr)


class NotAusNachPortwechsel(_Basis):
    """OUT-64-Sperre bleibt wirksam, wenn der In-Proc-Enttec seinem Dongle an
    eine neue Nummer folgt (``port`` aendert sich, ``konfig_port`` nicht)."""

    def setUp(self):
        super().setUp()
        from src.core.dmx import output_manager as om_mod
        self.om_mod = om_mod
        p = mock.patch.object(om_mod, "_make_enttec_device", self._neu)
        p.start(); self.addCleanup(p.stop)
        self.om = om_mod.OutputManager()
        for u in (1, 2):
            self.om.add_universe(u)
        self.addCleanup(self._om_zu)

    def _om_zu(self):
        for u in (1, 2):
            try:
                self.om.remove_output(u)
            except Exception:
                pass

    def _frame(self, dev):
        return dev._ser.writes[-1][5:5 + 512]     # Kopf: 7E 06 lenL lenH 00

    def test_sperre_haelt_nach_portwechsel(self):
        WELT.enttecs = {P0: None}
        self.om.add_enttec(1, P0)
        a = self.om._enttec_outputs[1]
        self.om.universes[1].set_channel(40, 255)
        self.om.set_laser_estop_mask({1: frozenset({40})}, True)
        schluessel_vorher = self.om._weg_enttec(a)
        # Dongle wird umgesteckt und kommt an neuer Nummer wieder.
        self._abziehen(a)
        WELT.enttecs = {P3: None}
        self._reconnect(a)
        self.assertEqual(P3, a.port)
        self.assertEqual(schluessel_vorher, self.om._weg_enttec(a),
                         "Weg-Schluessel der NOT-AUS-Sperre hat sich mit dem Port geaendert")
        self.assertTrue(self.om._werte_fuer(self.om._laser_estop_wege,
                                            self.om._wege_enttec(a)))
        # Universum 2 (Rig-Wert 255) wird bei aktivem Latch auf die NEUE
        # Nummer gelegt — der Laser haengt dort und muss dunkel bleiben.
        self.om.universes[2].set_channel(40, 255)
        self.om.add_enttec(2, P3)
        b = self.om._enttec_outputs[2]
        self.om._send_all()
        self.assertEqual(0, self._frame(b)[39],
                         "OUT-66: NOT-AUS ueber die neue Portnummer umgangen")


if __name__ == "__main__":
    unittest.main()

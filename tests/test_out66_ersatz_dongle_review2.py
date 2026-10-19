"""OUT-66, zweite Gegenpruefung — Ersatz-Dongle, Worker-Argumente, toter Port.

Befund 1 (Regression durch OUT-66): Hatte eine Ausgabe die Seriennummer AAA
gelernt und steckte an ihrem konfigurierten Port spaeter ein ANDERER Dongle
(Ersatzgeraet CCC), blieb sie fuer immer dunkel — der Worker-Neustart warf
„dort haengt ein anderer Enttec“, der Reconnect lieferte ``None``. Jetzt gilt:
ein Dongle am EIGENEN konfigurierten Port wird uebernommen und seine Nummer neu
gelernt, wenn keine ANDERE konfigurierte Enttec-Ausgabe diese Nummer kennt
(der ``OutputManager`` gibt jeder Ausgabe die Menge dieser fremden Nummern
mit). Ein Dongle, dessen Nummer eine andere Ausgabe kennt, bleibt verboten.
Die Uebernahme erscheint in der Ausgabe-Diagnose (``ausgabe_status``).

Befund 2: ein Test, der rot wird, wenn ``_default_process_factory`` die
Rueckmelde-Felder nicht an den Worker gibt — ueber einen Ersatz fuer
``ctx.Process`` und zusaetzlich mit einem echten ``spawn``-Prozess, in dem
``comports()``/``serial.Serial`` Attrappen sind.

Befund 4: ``port_aktuell`` zaehlt nur, solange der Ausgang dort verbunden ist —
ein toter Ausgang wird von ``close_enttec_on_port`` nicht mehr verdraengt. Die
NOT-AUS-Sperre liest weiter den zuletzt gemeldeten Port (``port_zuletzt``).

Keine Hardware, keine App-Daten.
"""
from __future__ import annotations

import errno
import io
import multiprocessing as mp
import os
import sys
import time
import unittest
from contextlib import redirect_stderr
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
from src.core.dmx import serial_process as sp                    # noqa: E402
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_PID, ENTTEC_VID  # noqa: E402
from src.core.dmx import output_manager as _om_mod               # noqa: E402

# Die ungepatchte Geraete-Fabrik (die Tests unten ersetzen sie meist).
_ECHTE_FABRIK = _om_mod._make_enttec_device

POSIX = os.name == "posix"
if POSIX:
    P0, P1, P2, P3 = ("/dev/ttyFAKE_OUT66R_0", "/dev/ttyFAKE_OUT66R_1",
                      "/dev/ttyFAKE_OUT66R_2", "/dev/ttyFAKE_OUT66R_3")
else:
    P0, P1, P2, P3 = "COM80", "COM81", "COM82", "COM83"


# ── Attrappen ────────────────────────────────────────────────────────────────

class _Welt:
    def __init__(self):
        self.enttecs: dict[str, str | None] = {}
        self.fremd_exklusiv: set[str] = set()
        self.oeffnungen: list[str] = []

    def comports(self, *_a, **_k):
        return [SimpleNamespace(device=d, vid=ENTTEC_VID, pid=ENTTEC_PID,
                                serial_number=sn)
                for d, sn in self.enttecs.items()]


WELT = _Welt()


class _FakeSerial:
    def __init__(self, port, baud, timeout=1, write_timeout=0.5, **kw):
        WELT.oeffnungen.append(port)
        if port not in WELT.enttecs:
            raise serial.SerialException(f"could not open port {port}")
        if kw.get("exclusive") and port in WELT.fremd_exklusiv:
            raise serial.SerialException(
                errno.EWOULDBLOCK, f"Could not exclusively lock port {port}")
        self.port = port
        self.is_open = True
        self.writes: list[bytes] = []
        self.out_waiting = 0

    def write(self, data):
        self.writes.append(bytes(data))

    def reset_output_buffer(self):
        pass

    def close(self):
        self.is_open = False


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


def _feld(text: str = ""):
    """Ersatz fuer ein shared ``Array('c')`` (nur ``.value``)."""
    return SimpleNamespace(value=text.encode())


class _Basis(unittest.TestCase):
    def setUp(self):
        global WELT
        WELT = _Welt()
        p1 = mock.patch.object(serial.tools.list_ports, "comports",
                               lambda *a, **k: WELT.comports())
        p2 = mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)
        self.geraete: list = []
        self.addCleanup(self._alle_zu)

    def _alle_zu(self):
        for d in self.geraete:
            try:
                d.close()
            except Exception:
                pass

    def _neu(self, port, **kw) -> EnttecPro:
        d = EnttecPro(port, **kw)
        self.geraete.append(d)
        return d

    @staticmethod
    def _abziehen(dev: EnttecPro):
        with redirect_stderr(io.StringIO()):
            dev._disable()
        dev._last_reconnect = -1e9

    @staticmethod
    def _reconnect(dev: EnttecPro):
        dev._last_reconnect = -1e9
        with redirect_stderr(io.StringIO()):
            dev.send_dmx(bytes(512))


# ── Befund 1: Ersatz-Dongle am eigenen Port ──────────────────────────────────

class ErsatzDongle(_Basis):

    def test_reconnect_uebernimmt_ersatz_am_eigenen_port(self):
        WELT.enttecs = {P0: "AAA"}
        a = self._neu(P0)
        self.assertEqual("AAA", a.seriennr)
        self._abziehen(a)
        WELT.enttecs = {P0: "CCC"}               # Ersatzgeraet, gleicher Port
        self._reconnect(a)
        self.assertFalse(a.is_disabled(), "Ersatz-Dongle bleibt dauerhaft dunkel")
        self.assertEqual(P0, a.port)
        self.assertEqual("CCC", a.seriennr, "neue Seriennummer nicht gelernt")
        self.assertIn("übernommen", a.hinweis())
        self.assertIn("Seriennr. CCC", a.hinweis())

    def test_worker_neustart_uebernimmt_ersatz_und_meldet(self):
        port_akt, sn, hin = _feld(), _feld("AAA"), _feld()
        WELT.enttecs = {P0: "CCC"}
        fabrik = sp._enttec_fabrik(EnttecPro, P0, port_akt, sn, _feld(), hin)
        with redirect_stderr(io.StringIO()):
            a = fabrik()
        self.geraete.append(a)
        self.assertEqual(P0, a.port)
        self.assertEqual(b"CCC", sn.value, "neue Nummer nicht an den Proxy")
        self.assertIn("übernommen", hin.value.decode())

    def test_worker_neustart_fremde_nummer_bleibt_verboten(self):
        # BBB kennt eine ANDERE Ausgabe (Feld vom Proxy) -> nie nehmen.
        WELT.enttecs = {P0: "BBB"}
        fabrik = sp._enttec_fabrik(EnttecPro, P0, _feld(), _feld("AAA"),
                                   _feld("BBB\nZZZ"), _feld())
        with self.assertRaises(serial.SerialException):
            self.geraete.append(fabrik())
        self.assertEqual([], WELT.oeffnungen)

    def test_erstes_oeffnen_ohne_seriennr_fremde_nummer_verboten(self):
        WELT.enttecs = {P0: "BBB"}
        with self.assertRaises(serial.SerialException):
            self._neu(P0, fremde={"BBB"})

    def test_reconnect_ohne_seriennr_fremde_nummer_am_eigenen_port(self):
        WELT.enttecs = {P0: None}
        a = self._neu(P0)
        self.assertIsNone(a.seriennr)
        self._abziehen(a)
        WELT.enttecs = {P0: "BBB"}
        a.setze_fremde_seriennr({"BBB"})
        WELT.oeffnungen.clear()
        self._reconnect(a)
        self.assertTrue(a.is_disabled())
        self.assertEqual([], WELT.oeffnungen)

    def test_eigener_dongle_an_neuer_nummer_hat_vorrang_vor_ersatz(self):
        # AAA ist an P3 zu sehen -> dem folgen (SERIAL-02), nicht CCC an P0.
        WELT.enttecs = {P0: "CCC", P3: "AAA"}
        a = self._neu(P0, seriennr="AAA")
        self.assertEqual(P3, a.port)
        self.assertEqual("AAA", a.seriennr)
        self.assertEqual("", a.hinweis())

    def test_ersatz_einer_anderen_instanz_nicht_genommen(self):
        # In-Proc: CCC gehoert Instanz B (Registry), auch ohne Manager-Menge.
        WELT.enttecs = {P0: "AAA", P1: "CCC"}
        a, b = self._neu(P0), self._neu(P1)
        self._abziehen(a)
        self._abziehen(b)
        WELT.enttecs = {P0: "CCC"}
        self._reconnect(a)
        self.assertTrue(a.is_disabled())


class ManagerReichtFremdeNummern(unittest.TestCase):
    """Der OutputManager gibt jeder Enttec-Ausgabe die Seriennummern der
    ANDEREN mit — beim Anlegen und laufend (Worker lernen erst nach dem
    Oeffnen)."""

    def setUp(self):
        from src.core.dmx import output_manager as om_mod
        self.om_mod = om_mod
        self.proxies = []

        def mach(port):
            d = sp.EnttecProcessProxy(
                port, _process_factory=_FakeProc,
                fremde_seriennr=om_mod._ANLEGE_FREMDE.get())
            self.proxies.append(d)
            return d
        p = mock.patch.object(om_mod, "_make_enttec_device", mach)
        p.start(); self.addCleanup(p.stop)
        self.om = om_mod.OutputManager()
        for u in (1, 2, 3):
            self.om.add_universe(u)
        self.addCleanup(self._zu)

    def _zu(self):
        for u in (1, 2, 3):
            try:
                self.om.remove_output(u)
            except Exception:
                pass
        for d in self.proxies:
            d.close()

    def test_nachfuehren_verteilt_gelernte_nummern(self):
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        a, b = self.om._enttec_outputs[1], self.om._enttec_outputs[2]
        sp._schreib_text(b._seriennr, "BBB", sp.SN_BYTES)   # Worker B lernt
        self.om._enttec_fremde_nachfuehren()
        self.assertEqual(["BBB"], sp._fremde_aus(a._fremde))
        self.assertEqual([], sp._fremde_aus(b._fremde), "eigene Nummer als fremd")
        sp._schreib_text(a._seriennr, "AAA", sp.SN_BYTES)
        self.om._enttec_fremde_nachfuehren()
        self.assertEqual(["AAA"], sp._fremde_aus(b._fremde))

    def test_neue_ausgabe_kennt_fremde_nummern_schon_beim_anlegen(self):
        self.om.add_enttec(1, P0)
        sp._schreib_text(self.om._enttec_outputs[1]._seriennr, "AAA",
                         sp.SN_BYTES)
        gesehen = []
        echt = sp.EnttecProcessProxy

        class _Spion(echt):
            def __init__(inner, port, **kw):
                def fabrik():
                    gesehen.append(sp._fremde_aus(inner._fremde))
                    return _FakeProc()
                echt.__init__(inner, port, _process_factory=fabrik, **kw)
                self.proxies.append(inner)

        with mock.patch.object(self.om_mod, "_make_enttec_device",
                               _ECHTE_FABRIK), \
                mock.patch.object(sp, "EnttecProcessProxy", _Spion), \
                mock.patch("src.core.dmx.port_check.warne_wenn_belegt",
                           lambda *_a, **_k: None, create=True), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LIGHTOS_SERIAL_INPROC", None)
            self.om.add_enttec(2, P1)
        self.assertEqual([["AAA"]], gesehen,
                         "Worker startete ohne die Nummern der anderen Ausgaben")

    def test_entfernte_ausgabe_gibt_ihre_nummer_frei(self):
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        a = self.om._enttec_outputs[1]
        sp._schreib_text(self.om._enttec_outputs[2]._seriennr, "BBB", sp.SN_BYTES)
        self.om._enttec_fremde_nachfuehren()
        self.assertEqual(["BBB"], sp._fremde_aus(a._fremde))
        self.om.remove_output(2)
        self.assertEqual([], sp._fremde_aus(a._fremde))

    def test_uebernahme_steht_in_der_ausgabe_diagnose(self):
        self.om.add_enttec(1, P0)
        a = self.om._enttec_outputs[1]
        sp._schreib_text(a._hinweis, "Anderer Enttec an X übernommen: "
                         "Seriennr. CCC statt Seriennr. AAA", sp.HINWEIS_BYTES)
        eintrag = [e for e in self.om.ausgabe_status() if e["universum"] == 1][0]
        self.assertIn("übernommen", eintrag["hinweis"])
        puffer = io.StringIO()
        with redirect_stderr(puffer):
            self.om._enttec_fremde_nachfuehren()
            self.om._enttec_fremde_nachfuehren()
        self.assertEqual(1, puffer.getvalue().count("übernommen"),
                         "Hinweis nicht genau einmal ins Log")




# ── Befund 2: Argumente an den Worker ────────────────────────────────────────

class _CtxErsatz:
    """Wie ``mp.get_context('spawn')``, aber ``Process`` wird abgefangen."""

    def __init__(self, echt, kind_ziel=None):
        self._echt = echt
        self._kind_ziel = kind_ziel
        self.aufrufe: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._echt, name)

    def Process(self, target=None, args=(), **kw):
        self.aufrufe.append({"target": target, "args": args, **kw})
        if self._kind_ziel is None:
            return _FakeProc()
        return self._echt.Process(target=self._kind_ziel, args=args, **kw)


class WorkerArgumente(unittest.TestCase):

    def test_default_factory_gibt_rueckmeldefelder_mit(self):
        echt = mp.get_context("spawn")
        ctx = _CtxErsatz(echt)
        with mock.patch.object(sp.mp, "get_context", lambda *_a, **_k: ctx):
            px = sp.EnttecProcessProxy(P0)
        try:
            self.assertEqual(1, len(ctx.aufrufe))
            aufruf = ctx.aufrufe[0]
            self.assertIs(sp._worker_main, aufruf["target"])
            args = aufruf["args"]
            for feld in ("_port_akt", "_seriennr", "_fremde", "_hinweis",
                         "_frueher"):
                self.assertTrue(any(a is getattr(px, feld) for a in args),
                                f"{feld} geht nicht an den Worker")
            # Reihenfolge = Signatur von _worker_main
            self.assertEqual((px._port_akt, px._seriennr, px._fremde,
                              px._hinweis, px._frueher), tuple(args[5:10]))
        finally:
            px.close()


KIND_SN = "KIND-AAA"


def _kind_mit_attrappe(port, buf, stop, status, frame_interval,
                       port_akt=None, seriennr=None, fremde=None, hinweis=None,
                       frueher=None):
    """Laeuft im ECHTEN spawn-Kind: ``comports``/``serial.Serial`` durch
    Attrappen ersetzen und dann den echten ``_worker_main`` starten. Beim
    ersten Start steckt KIND-AAA am konfigurierten Port; kennt der Worker die
    Nummer schon (nur, wenn der Proxy sie mitgibt), steckt dort ein fremder
    und KIND-AAA an ``P3``."""
    import serial as _serial
    import serial.tools.list_ports as _lp
    from src.core.dmx import serial_process as _sp

    if _sp._lies_text(seriennr):
        welt = {port: "KIND-BBB", P3: KIND_SN}
    else:
        welt = {port: KIND_SN}

    def comports(*_a, **_k):
        return [SimpleNamespace(device=d, vid=ENTTEC_VID, pid=ENTTEC_PID,
                                serial_number=s) for d, s in welt.items()]

    class _S:
        def __init__(self, p, *_a, **_k):
            if p not in welt:
                raise _serial.SerialException(f"kein Port {p}")
            self.is_open = True
            self.out_waiting = 0

        def write(self, data):
            pass

        def reset_output_buffer(self):
            pass

        def close(self):
            self.is_open = False

    _lp.comports = comports
    _serial.Serial = _S
    _sp._worker_main(port, buf, stop, status, frame_interval,
                     port_akt, seriennr, fremde, hinweis, frueher)


class EchterSpawn(unittest.TestCase):
    """Echter Kindprozess (``spawn``, Linux und Windows): der Worker meldet
    Port + Seriennummer zurueck, und ein NEU gestarteter Worker bekommt die
    Seriennummer mit und folgt seinem Dongle."""

    @staticmethod
    def _warte(bedingung, frist=30.0):
        ende = time.monotonic() + frist
        while time.monotonic() < ende:
            if bedingung():
                return True
            time.sleep(0.05)
        return False

    def test_spawn_meldet_und_bekommt_seriennummer(self):
        echt = mp.get_context("spawn")
        ctx = _CtxErsatz(echt, kind_ziel=_kind_mit_attrappe)
        uhr = [0.0]
        with mock.patch.object(sp.mp, "get_context", lambda *_a, **_k: ctx):
            px = sp.EnttecProcessProxy(P0, _clock=lambda: uhr[0])
        try:
            self.assertTrue(self._warte(lambda: px.seriennr == KIND_SN),
                            "Worker meldet keine Seriennummer an den Proxy")
            self.assertTrue(self._warte(px.is_connected))
            self.assertEqual(P0, px.port_aktuell)
            # Worker stirbt; beim Neustart steckt ein fremder an P0.
            alt = px._proc
            alt.terminate()
            alt.join(10)
            uhr[0] += 100.0
            px.send_dmx(bytes(512))                 # respawnt
            self.assertIsNot(alt, px._proc)
            self.assertTrue(self._warte(lambda: px.port_zuletzt == P3),
                            "neuer Worker bekam die Seriennummer nicht mit")
            self.assertTrue(self._warte(px.is_connected))
            self.assertEqual(P3, px.port_aktuell)
            self.assertEqual(KIND_SN, px.seriennr)
        finally:
            px.close()


# ── Befund 4: port_aktuell nur, solange verbunden ────────────────────────────

class ToterAusgangWirdNichtVerdraengt(unittest.TestCase):

    def setUp(self):
        from src.core.dmx import output_manager as om_mod
        self.proxies = []

        def mach(port):
            d = sp.EnttecProcessProxy(port, _process_factory=_FakeProc)
            self.proxies.append(d)
            return d
        p = mock.patch.object(om_mod, "_make_enttec_device", mach)
        p.start(); self.addCleanup(p.stop)
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

    def _gefolgt_und_tot(self):
        self.om.add_enttec(1, P0)
        a = self.om._enttec_outputs[1]
        sp._schreib_text(a._port_akt, P3, sp.PORT_BYTES)    # Worker folgte
        a._status.value = sp.ST_DISABLED                    # ... und verlor ihn
        return a

    def test_port_aktuell_nur_wenn_verbunden(self):
        a = self._gefolgt_und_tot()
        self.assertEqual(P0, a.port_aktuell)
        self.assertEqual(P3, a.port_zuletzt)
        a._status.value = sp.ST_OK
        self.assertEqual(P3, a.port_aktuell)

    def test_anderes_universum_auf_alte_nummer_verdraengt_nicht(self):
        self._gefolgt_und_tot()
        self.om.add_enttec(2, P3)
        self.assertIn(1, self.om._enttec_outputs,
                      "toter Ausgang U1 (konfiguriert P0) wurde verdraengt")

    def test_not_aus_sperrt_zuletzt_gemeldete_nummer_weiter(self):
        # Latch kommt NACH dem Verlust — die Sperre muss trotzdem auch die
        # zuletzt gemeldete Nummer treffen (lieber zu viel als zu wenig).
        a = self._gefolgt_und_tot()
        self.om.universes[1].set_channel(40, 255)
        self.om.set_laser_estop_mask({1: frozenset({40})}, True)
        self.assertIn(("enttec", P3), self.om._wege_enttec(a))
        self.om.universes[2].set_channel(40, 255)
        self.om.add_enttec(2, P3)
        b = self.om._enttec_outputs[2]
        self.om._send_all()
        self.assertEqual(0, bytes(b._buf.get_obj())[39],
                         "NOT-AUS ueber die zuletzt gemeldete Nummer umgangen")

    def test_verbunden_an_neuer_nummer_wird_weiter_verdraengt(self):
        a = self._gefolgt_und_tot()
        a._status.value = sp.ST_OK
        self.om.add_enttec(2, P3)
        self.assertNotIn(1, self.om._enttec_outputs)


class ToterInProcAusgang(_Basis):
    """Dasselbe fuer den In-Proc-Enttec (``LIGHTOS_SERIAL_INPROC``)."""

    def setUp(self):
        super().setUp()
        from src.core.dmx import output_manager as om_mod
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

    def test_toter_gefolgter_ausgang_bleibt_und_not_aus_haelt(self):
        WELT.enttecs = {P0: None}
        self.om.add_enttec(1, P0)
        a = self.om._enttec_outputs[1]
        self._abziehen(a)
        WELT.enttecs = {P3: None}
        self._reconnect(a)
        self.assertEqual(P3, a.port)
        self._abziehen(a)                       # und wieder verloren
        self.assertEqual(P0, a.port_aktuell)
        self.om.universes[1].set_channel(40, 255)
        self.om.set_laser_estop_mask({1: frozenset({40})}, True)
        self.om.universes[2].set_channel(40, 255)
        self.om.add_enttec(2, P3)
        self.assertIn(1, self.om._enttec_outputs, "toter Ausgang verdraengt")
        b = self.om._enttec_outputs[2]
        self.om._send_all()
        self.assertEqual(0, b._ser.writes[-1][5:5 + 512][39],
                         "NOT-AUS ueber die zuletzt benutzte Nummer umgangen")


if __name__ == "__main__":
    unittest.main()

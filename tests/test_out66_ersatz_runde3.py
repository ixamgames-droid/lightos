"""OUT-66, dritte Gegenpruefung — Ersatz-Dongle darf keine Universen vertauschen.

Befund: Die Ersatz-Regel (Review 2) uebernahm einen anderen Dongle am eigenen
konfigurierten Port, sobald keine andere Ausgabe dessen Seriennummer KANNTE.
Hatte eine andere konfigurierte Enttec-Ausgabe ihre Nummer noch nicht gelernt
(Dongle fehlte seit dem Start oder seit „Uebernehmen“), konnten zwei Universen
still tauschen:

  A (P0) lernt AAA, A wird abgezogen; B (P1) kennt noch keine Nummer; BBB
  landet an P0 -> A uebernahm BBB und vergass AAA; B oeffnete dann AAA an P1.

Entscheidung: Ersatz nur, wenn KEINE andere konfigurierte Enttec-Ausgabe ohne
gelernte Nummer existiert — ausser deren Dongle steckt nachweislich an ihrem
eigenen Port (sie ist dort verbunden). Sonst dunkel bleiben, Hinweis ueber
``ausgabe_status`` ('hinweis'). Zweite Sicherung: wer einen Ersatz uebernimmt,
behaelt die alte Nummer als „frueher eigen“ in der Fremdmenge der anderen.

Simuliert wird der Standardbetrieb (Prozess-Proxy): je Ausgabe ein
``EnttecProcessProxy`` mit Attrappen-Prozess und ein „Worker“ aus der echten
``_enttec_fabrik`` mit den echten gemeinsamen Feldern — mit EIGENER Registry
je Worker, wie getrennte Prozesse. Keine Hardware, keine App-Daten.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import contextmanager, redirect_stderr
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
from src.core.dmx import output_manager as om_mod                # noqa: E402
from src.core.dmx import serial_process as sp                    # noqa: E402
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_PID, ENTTEC_VID  # noqa: E402

if os.name == "posix":
    P0, P1 = "/dev/ttyFAKE_OUT66C_0", "/dev/ttyFAKE_OUT66C_1"
else:
    P0, P1 = "COM90", "COM91"


# ── Attrappen ────────────────────────────────────────────────────────────────

class _Welt:
    def __init__(self):
        self.enttecs: dict[str, str | None] = {}

    def comports(self, *_a, **_k):
        return [SimpleNamespace(device=d, vid=ENTTEC_VID, pid=ENTTEC_PID,
                                serial_number=sn)
                for d, sn in self.enttecs.items()]


WELT = _Welt()


class _FakeSerial:
    def __init__(self, port, baud, timeout=1, write_timeout=0.5, **kw):
        if port not in WELT.enttecs:
            raise serial.SerialException(f"could not open port {port}")
        self.port = port
        self.is_open = True
        self.out_waiting = 0

    def write(self, data):
        pass

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


class _Worker:
    """Der Worker-Prozess EINES Proxys, im Testprozess nachgestellt: echte
    Fabrik, echte gemeinsame Felder, eigene Registry (getrennte Prozesse
    teilen keine)."""

    def __init__(self, px):
        self.px = px
        self.dev: EnttecPro | None = None
        self._offen: dict = {}
        self._sn: dict = {}

    @contextmanager
    def _im_prozess(self):
        with mock.patch.object(enttec_pro, "_OFFEN", self._offen), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", self._sn), \
                redirect_stderr(io.StringIO()):
            yield

    def _status(self):
        offen = (self.dev is not None and not self.dev.is_disabled()
                 and self.dev.is_open())
        self.px._status.value = sp.ST_OK if offen else sp.ST_DISABLED

    def start(self) -> bool:
        """Worker (neu) starten — ein Versuch des Worker-Loops."""
        px = self.px
        felder = [px._port_akt, px._seriennr, px._fremde, px._hinweis]
        if hasattr(px, "_frueher"):                # Runde 3 (Gegenprobe ohne)
            felder.append(px._frueher)
        fabrik = sp._enttec_fabrik(EnttecPro, px.port, *felder)
        with self._im_prozess():
            try:
                self.dev = fabrik()
            except serial.SerialException:
                self.dev = None
        self._status()
        return self.dev is not None

    def abziehen(self):
        with self._im_prozess():
            self.dev._disable()
        self._status()

    def reconnect(self):
        with self._im_prozess():
            self.dev._last_reconnect = -1e9
            self.dev.send_dmx(bytes(512))
        self._status()


class _Basis(unittest.TestCase):
    UNIVERSEN = (1, 2)

    def setUp(self):
        global WELT
        WELT = _Welt()
        p1 = mock.patch.object(serial.tools.list_ports, "comports",
                               lambda *a, **k: WELT.comports())
        p2 = mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial)
        self.proxies = []

        def mach(port):
            d = sp.EnttecProcessProxy(
                port, _process_factory=_FakeProc,
                fremde_seriennr=om_mod._ANLEGE_FREMDE.get())
            self.proxies.append(d)
            return d
        p3 = mock.patch.object(om_mod, "_make_enttec_device", mach)
        for p in (p1, p2, p3):
            p.start()
            self.addCleanup(p.stop)
        self.om = om_mod.OutputManager()
        for u in self.UNIVERSEN:
            self.om.add_universe(u)
        self.addCleanup(self._zu)

    def _zu(self):
        for u in self.UNIVERSEN:
            try:
                self.om.remove_output(u)
            except Exception:
                pass
        for d in self.proxies:
            d.close()

    def _px(self, u):
        return self.om._enttec_outputs[u]

    def _nachfuehren(self):
        with redirect_stderr(io.StringIO()):
            self.om._enttec_fremde_nachfuehren()

    def _status_hinweis(self, u) -> str:
        return [e for e in self.om.ausgabe_status()
                if e["universum"] == u and e["weg"] == "Enttec"][0]["hinweis"]


# ── Der Ablauf aus dem Befund ────────────────────────────────────────────────

class KeinTauschMitUngelernterAusgabe(_Basis):

    def _ausgangslage(self):
        """A an P0 lernt AAA; B an P1 hat noch keinen Dongle (keine Nummer)."""
        WELT.enttecs = {P0: "AAA"}
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        wa, wb = _Worker(self._px(1)), _Worker(self._px(2))
        self.assertTrue(wa.start())
        self.assertFalse(wb.start())
        self._nachfuehren()
        self.assertEqual("AAA", self._px(1).seriennr)
        self.assertIsNone(self._px(2).seriennr)
        return wa, wb

    def test_reconnect_nimmt_ersatz_nicht_und_b_nimmt_aaa_nicht(self):
        wa, wb = self._ausgangslage()
        wa.abziehen()
        WELT.enttecs = {P0: "BBB"}                 # B's Dongle landet an P0
        self._nachfuehren()
        wa.reconnect()
        self.assertTrue(wa.dev.is_disabled(),
                        "A hat BBB uebernommen, obwohl B seinen Dongle nicht kennt")
        self.assertEqual("AAA", self._px(1).seriennr, "A hat AAA vergessen")
        hin = self._status_hinweis(1)
        self.assertIn("Nicht übernommen", hin)
        self.assertIn(f"U2 ({P1})", hin)
        self.assertIn("ihren Dongle noch nicht kennt", hin)
        # Jetzt taucht AAA an P1 auf: B darf es nicht nehmen (A kennt AAA).
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        self._nachfuehren()
        self.assertFalse(wb.start(), "B oeffnet den Dongle von A -> Tausch")
        self.assertIsNone(self._px(2).seriennr)

    def test_worker_neustart_nimmt_ersatz_nicht(self):
        wa, _wb = self._ausgangslage()
        WELT.enttecs = {P0: "BBB"}
        self.assertFalse(_Worker(self._px(1)).start(),
                         "neu gestarteter Worker uebernimmt BBB trotz Sperre")
        self.assertEqual("AAA", self._px(1).seriennr)
        self.assertIn("Nicht übernommen", self._px(1).hinweis())

    def test_hinweis_einmal_ins_log_und_in_die_diagnose(self):
        wa, _wb = self._ausgangslage()
        wa.abziehen()
        WELT.enttecs = {P0: "BBB"}
        self._nachfuehren()
        wa.reconnect()
        wa.reconnect()
        puffer = io.StringIO()
        with redirect_stderr(puffer):
            self.om._enttec_fremde_nachfuehren()
            self.om._enttec_fremde_nachfuehren()
        self.assertEqual(1, puffer.getvalue().count("Nicht übernommen"),
                         "Sperr-Hinweis nicht genau einmal ins Log")
        self.assertIn("Nicht übernommen", self._status_hinweis(1))

    def test_sperre_faellt_sobald_b_seinen_dongle_kennt(self):
        wa, wb = self._ausgangslage()
        wa.abziehen()
        WELT.enttecs = {P0: "BBB"}
        self._nachfuehren()
        wa.reconnect()
        self.assertTrue(wa.dev.is_disabled())
        # B bekommt seinen Dongle CCC und lernt ihn -> BBB ist ein Ersatz.
        WELT.enttecs = {P0: "BBB", P1: "CCC"}
        self.assertTrue(wb.start())
        self._nachfuehren()
        wa.reconnect()
        self.assertFalse(wa.dev.is_disabled())
        self.assertEqual("BBB", self._px(1).seriennr)
        hin = self._status_hinweis(1)
        self.assertNotIn("Nicht übernommen", hin, "alter Sperr-Hinweis bleibt")
        self.assertIn("übernommen", hin)

    def test_b_nachweislich_am_eigenen_port_sperrt_nicht(self):
        # B ist an P1 mit einem Dongle OHNE gemeldete Seriennummer verbunden:
        # sein Dongle ist dort, BBB an P0 kann nicht seiner sein.
        WELT.enttecs = {P0: "AAA", P1: None}
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        wa, wb = _Worker(self._px(1)), _Worker(self._px(2))
        self.assertTrue(wa.start())
        self.assertTrue(wb.start())
        self._nachfuehren()
        self.assertIsNone(self._px(2).seriennr)
        self.assertNotIn(f"{enttec_pro.OHNE_NUMMER}U2 ({P1})",
                         self.om._fremde_fuer(1))
        wa.abziehen()
        WELT.enttecs = {P0: "BBB", P1: None}
        self._nachfuehren()
        wa.reconnect()
        self.assertFalse(wa.dev.is_disabled())
        self.assertEqual("BBB", self._px(1).seriennr)

    def test_manager_meldet_ungelernte_ausgabe_als_kennung(self):
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        self._nachfuehren()
        self.assertEqual([f"U2 ({P1})"], sp._ohne_nummer_aus(self._px(1)._fremde))
        self.assertEqual([], sp._fremde_aus(self._px(1)._fremde))


# ── Einzel-Dongle: Ersatz bringt weiter Licht ────────────────────────────────

class EinzelDongle(_Basis):
    UNIVERSEN = (1,)

    def test_reconnect_uebernimmt_ersatz(self):
        WELT.enttecs = {P0: "AAA"}
        self.om.add_enttec(1, P0)
        wa = _Worker(self._px(1))
        self.assertTrue(wa.start())
        self._nachfuehren()
        wa.abziehen()
        WELT.enttecs = {P0: "CCC"}
        self._nachfuehren()
        wa.reconnect()
        self.assertFalse(wa.dev.is_disabled(), "Einzel-Dongle bleibt dunkel")
        self.assertEqual("CCC", self._px(1).seriennr)
        self.assertIn("übernommen", self._status_hinweis(1))
        self.assertNotIn("Nicht übernommen", self._status_hinweis(1))

    def test_worker_neustart_uebernimmt_ersatz(self):
        WELT.enttecs = {P0: "AAA"}
        self.om.add_enttec(1, P0)
        self.assertTrue(_Worker(self._px(1)).start())
        self._nachfuehren()
        WELT.enttecs = {P0: "CCC"}
        self.assertTrue(_Worker(self._px(1)).start())
        self.assertEqual("CCC", self._px(1).seriennr)


# ── Zweite Sicherung: „frueher eigen“ ────────────────────────────────────────

class FrueherEigen(_Basis):

    def _a_uebernimmt_bbb(self):
        """B ist nachweislich an P1 (Dongle ohne Nummer) -> A darf BBB
        uebernehmen; AAA wird „frueher eigen“."""
        WELT.enttecs = {P0: "AAA", P1: None}
        self.om.add_enttec(1, P0)
        self.om.add_enttec(2, P1)
        wa, wb = _Worker(self._px(1)), _Worker(self._px(2))
        self.assertTrue(wa.start())
        self.assertTrue(wb.start())
        self._nachfuehren()
        wa.abziehen()
        WELT.enttecs = {P0: "BBB", P1: None}
        wa.reconnect()
        self.assertEqual("BBB", self._px(1).seriennr)
        self._nachfuehren()
        return wa, wb

    def test_alte_nummer_bleibt_fuer_die_anderen_fremd(self):
        wa, wb = self._a_uebernimmt_bbb()
        self.assertEqual(frozenset({"AAA"}), self._px(1).frueher_seriennr)
        self.assertIn("AAA", sp._fremde_aus(self._px(2)._fremde))
        self.assertIn("BBB", sp._fremde_aus(self._px(2)._fremde))
        # B faellt aus, AAA taucht an P1 auf: B nimmt ihn nicht.
        wb.abziehen()
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        self._nachfuehren()
        wb.reconnect()
        self.assertTrue(wb.dev.is_disabled(),
                        "B nimmt den frueheren Dongle von A")
        self.assertFalse(_Worker(self._px(2)).start())

    def test_worker_neustart_vergisst_frueher_nicht(self):
        self._a_uebernimmt_bbb()
        w = _Worker(self._px(1))
        self.assertTrue(w.start())
        self.assertEqual(frozenset({"AAA"}), w.dev.frueher_seriennr)

    def test_neu_zuweisen_vergisst_frueher(self):
        self._a_uebernimmt_bbb()
        self.assertIn("AAA", self.om._fremde_fuer(2))
        self.om.add_enttec(1, P0)                  # Nutzer weist neu zu
        self.assertNotIn("AAA", self.om._fremde_fuer(2))

    def test_manager_merkt_beobachteten_wechsel(self):
        # Auch ohne ``frueher_seriennr`` des Geraets: sieht der Manager die
        # Nummer wechseln, bleibt die alte fuer die anderen fremd.
        a = SimpleNamespace(seriennr="AAA", port=P0)
        b = SimpleNamespace(seriennr="CCC", port=P1)
        self.om._enttec_outputs = {1: a, 2: b}
        self.om._enttec_frueher_merken()
        a.seriennr = "BBB"
        self.om._enttec_frueher_merken()
        self.assertEqual(frozenset({"AAA", "BBB"}), self.om._fremde_fuer(2))
        self.om._enttec_outputs = {}


if __name__ == "__main__":
    unittest.main()

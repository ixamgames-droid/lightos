"""OUT-80: die Enttec-Seriennummer steht dauerhaft in ``universes.json``.

Befund (zweite Gegenpruefung zu OUT-66): die gelernte USB-Seriennummer kannte
die Ausgabe nur zur Laufzeit. Nach einem Neustart — Linux vertauscht beim
Booten ``ttyUSB0``/``ttyUSB1`` — oder nach „Übernehmen“ (``apply_output_config``
legt jede Ausgabe neu an) oeffnete jedes Universum den Dongle am konfigurierten
Port, also den des anderen, und lernte ihn als eigenen.

Geprueft wird der Standardbetrieb (Prozess-Proxy ueber die echte
``_make_enttec_device``) mit Attrappen-Prozess und einem „Worker“ aus der
echten ``_enttec_fabrik`` mit eigener Registry je Worker (getrennte Prozesse),
dazu einmal der In-Prozess-Pfad. ``comports()`` und ``serial.Serial`` sind
Attrappen; ``universes.json`` ist eine Wegwerf-Datei. Keine Hardware, keine
App-Daten. Portnamen je Plattform, ohne Quellverzweigung im Code.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import serial                                                    # noqa: E402
import serial.tools.list_ports                                   # noqa: E402
from src.core.app_state import AppState                          # noqa: E402
from src.core.dmx import anschluss_auswahl                       # noqa: E402
from src.core.dmx import enttec_konfig                           # noqa: E402
from src.core.dmx import enttec_pro                              # noqa: E402
from src.core.dmx import output_manager as om_mod                # noqa: E402
from src.core.dmx import serial_process as sp                    # noqa: E402
from src.core.dmx.enttec_pro import EnttecPro, ENTTEC_PID, ENTTEC_VID  # noqa: E402

if os.name == "posix":
    P0, P1, P2 = ("/dev/ttyFAKE_OUT80_0", "/dev/ttyFAKE_OUT80_1",
                  "/dev/ttyFAKE_OUT80_2")
else:
    P0, P1, P2 = "COM80", "COM81", "COM82"

FELD = "enttec_seriennr"


# ── Attrappen ────────────────────────────────────────────────────────────────

class _Welt:
    def __init__(self):
        self.enttecs: dict[str, str | None] = {}
        self.geoeffnet: list[str] = []

    def comports(self, *_a, **_k):
        return [SimpleNamespace(device=d, vid=ENTTEC_VID, pid=ENTTEC_PID,
                                serial_number=sn, description="DMX USB PRO")
                for d, sn in self.enttecs.items()]


WELT = _Welt()


class _FakeSerial:
    def __init__(self, port, baud, timeout=1, write_timeout=0.5, **kw):
        if port not in WELT.enttecs:
            raise serial.SerialException(f"could not open port {port}")
        WELT.geoeffnet.append(port)
        self.port = port
        self.sn = WELT.enttecs[port]      # welcher Dongle steckt hier
        self.is_open = True
        self.out_waiting = 0
        self.writes: list[bytes] = []

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


class _Worker:
    """Der Worker-Prozess EINES Proxys: echte Fabrik, echte gemeinsame Felder,
    eigene Registry."""

    def __init__(self, px):
        self.px = px
        self.dev: EnttecPro | None = None
        self._offen: dict = {}
        self._sn: dict = {}

    @contextmanager
    def _im_prozess(self):
        with mock.patch.object(enttec_pro, "_OFFEN", self._offen), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", self._sn), \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            yield

    def _status(self):
        offen = (self.dev is not None and not self.dev.is_disabled()
                 and self.dev.is_open())
        self.px._status.value = sp.ST_OK if offen else sp.ST_DISABLED

    def start(self) -> bool:
        px = self.px
        fabrik = sp._enttec_fabrik(EnttecPro, px.port, px._port_akt,
                                   px._seriennr, px._fremde, px._hinweis,
                                   px._frueher)
        with self._im_prozess():
            try:
                self.dev = fabrik()
            except serial.SerialException:
                self.dev = None
        self._status()
        return self.dev is not None

    def dongle(self) -> str | None:
        """Seriennummer des Dongles, auf den dieser Worker gerade schreibt."""
        if self.dev is None or self.dev.is_disabled() or not self.dev.is_open():
            return None
        return self.dev._ser.sn

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
        self.proxies: list = []
        test = self

        class _Proxy(sp.EnttecProcessProxy):
            def __init__(self, port, **kw):
                kw.setdefault("_process_factory", _FakeProc)
                super().__init__(port, **kw)
                test.proxies.append(self)

        patches = [
            mock.patch.object(serial.tools.list_ports, "comports",
                              lambda *a, **k: WELT.comports()),
            mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial),
            mock.patch.object(sp, "EnttecProcessProxy", _Proxy),
            mock.patch("src.core.dmx.port_check.warne_wenn_belegt",
                       lambda *_a, **_k: None, create=True),
            mock.patch.dict(os.environ, {}, clear=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("LIGHTOS_SERIAL_INPROC", None)
        fd, self.pfad = tempfile.mkstemp(suffix="_out80_universes.json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.pfad) and os.remove(self.pfad))
        self.om = om_mod.OutputManager()
        self.state = SimpleNamespace(output_manager=self.om, universes={})
        self.addCleanup(self._zu)

    def _zu(self):
        sp_ = getattr(self.state, "_enttec_sn_speicher", None)
        if sp_ is not None:
            sp_.warten()
        for u in list(self.UNIVERSEN):
            try:
                self.om.remove_output(u)
            except Exception:
                pass
        for d in self.proxies:
            d.close()

    # Konfiguration ---------------------------------------------------------

    def _schreibe(self, *zeilen):
        with open(self.pfad, "w", encoding="utf-8") as f:
            json.dump(list(zeilen), f)

    def _zeilen(self) -> dict:
        with open(self.pfad, encoding="utf-8") as f:
            return {r["num"]: r for r in json.load(f)}

    def _uebernehmen(self):
        """„Übernehmen“ bzw. Programmstart: ``apply_output_config``."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            AppState.apply_output_config(self.state, path=self.pfad)

    def _speichern_abwarten(self):
        self.assertTrue(self.state._enttec_sn_speicher.warten(3.0))

    # Geraete ---------------------------------------------------------------

    def _px(self, u):
        return self.om._enttec_outputs[u]

    def _worker(self, *universen) -> dict:
        """Startet je Universum einen (neuen) Worker — in der Reihenfolge der
        Argumente, wie der Prozessstart sie zufaellig ergibt."""
        w = {}
        for u in universen:
            w[u] = _Worker(self._px(u))
            w[u].start()
        return w

    def _nachfuehren(self):
        with redirect_stderr(io.StringIO()):
            self.om._enttec_fremde_nachfuehren()

    def _hinweis(self, u) -> str:
        return [e for e in self.om.ausgabe_status()
                if e["universum"] == u and e["weg"] == "Enttec"][0]["hinweis"]


def _zeile(num, port, sn=None, **mehr):
    z = {"num": num, "name": f"U{num}", "output": "Enttec", "patch": port}
    if sn is not None:
        z[FELD] = sn
    z.update(mehr)
    return z


# ── Neustart mit vertauschten Ports ──────────────────────────────────────────

class NeustartVertauschtePorts(_Basis):

    def test_jedes_universum_auf_seinem_dongle(self):
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "BBB", P1: "AAA"}       # beim Booten vertauscht
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertEqual("AAA", w[1].dongle(), "U1 schreibt auf den Dongle von U2")
        self.assertEqual("BBB", w[2].dongle(), "U2 schreibt auf den Dongle von U1")
        self._nachfuehren()
        self.assertEqual(P1, self._px(1).port_aktuell)
        self.assertEqual(P0, self._px(2).port_aktuell)
        self._speichern_abwarten()
        z = self._zeilen()
        self.assertEqual(("AAA", "BBB"), (z[1][FELD], z[2][FELD]),
                         "gespeicherte Nummern wurden durch den Tausch ersetzt")

    def test_zweiter_worker_zuerst_gestartet(self):
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        self._uebernehmen()
        w = self._worker(2, 1)
        self.assertEqual("AAA", w[1].dongle())
        self.assertEqual("BBB", w[2].dongle())

    def test_eigener_fehlt_fremder_am_port_bleibt_dunkel_mit_hinweis(self):
        # AAA fehlt, BBB (Dongle von U2) steckt am Port von U1.
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "BBB"}
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertIsNone(w[1].dongle(), "U1 nimmt den Dongle von U2 als Ersatz")
        self.assertEqual("BBB", w[2].dongle())
        self.assertEqual("AAA", self._px(1).seriennr)
        hin = self._hinweis(1)
        self.assertIn("Nicht übernommen", hin)
        self.assertIn("anderen Ausgabe", hin)

    def test_in_prozess_pfad(self):
        os.environ["LIGHTOS_SERIAL_INPROC"] = "1"
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        with mock.patch.object(enttec_pro, "_OFFEN", {}), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", {}):
            self._uebernehmen()
            a, b = self._px(1), self._px(2)
            self.assertIsInstance(a, EnttecPro)
            self.assertEqual(("AAA", P1), (a._ser.sn, a.port))
            self.assertEqual(("BBB", P0), (b._ser.sn, b.port))
            for u in (1, 2):
                self.om.remove_output(u)


class EigenerFehltInProzess(_Basis):
    """Gegenpruefung Befund 3: im In-Prozess-Pfad wird U1 angelegt (und
    oeffnet), BEVOR U2 existiert — nur die vorgemerkte Nummer von U2 haelt
    U1 von dessen Dongle fern."""

    def test_fremder_am_port_wird_nicht_genommen(self):
        os.environ["LIGHTOS_SERIAL_INPROC"] = "1"
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "BBB"}                  # AAA fehlt
        with mock.patch.object(enttec_pro, "_OFFEN", {}), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", {}):
            self._uebernehmen()

            def _sn(u):          # dunkel = nicht angelegt oder nicht offen
                d = self.om._enttec_outputs.get(u)
                return d._ser.sn if d is not None and d.is_open() else None
            self.assertNotEqual("BBB", _sn(1), "U1 schreibt auf den Dongle von U2")
            self.assertEqual("BBB", _sn(2))
            for u in (1, 2):
                self.om.remove_output(u)


class DoppelteNummer(_Basis):
    """Gegenpruefung Befund 1: dieselbe Nummer in zwei Zeilen."""
    UNIVERSEN = (1, 3)

    def test_verdraengen_hinterlaesst_keine_doppelte_nummer(self):
        # Weg aus dem Befund (In-Prozess): U1 lief auf AAA an P0; die Datei
        # nennt jetzt U1 an P2 MIT AAA (alter Dialog-Stand) und eine neue
        # Zeile U3 an P0 ohne Nummer. U1 folgt AAA nach P0, U3 verdraengt es
        # dort und lernt AAA.
        os.environ["LIGHTOS_SERIAL_INPROC"] = "1"
        with mock.patch.object(enttec_pro, "_OFFEN", {}), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", {}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self._schreibe(_zeile(1, P0, "AAA"))
            WELT.enttecs = {P0: "AAA"}
            self._uebernehmen()
            self._nachfuehren()
            self._speichern_abwarten()
            self._schreibe(_zeile(1, P2, "AAA"), _zeile(3, P0))
            WELT.enttecs = {P0: "AAA", P2: "CCC"}
            self._uebernehmen()
            self._nachfuehren()
            self._speichern_abwarten()
            z = self._zeilen()
            self.assertEqual("AAA", z[3][FELD])
            self.assertNotEqual("AAA", z[1].get(FELD), "AAA steht in zwei Zeilen")
            for u in (1, 3):
                self.om.remove_output(u)

    def test_doppelte_nummer_wird_keinem_gegeben(self):
        # So stand es nach dem Befund in der Datei; nach dem Neustart muss
        # jedes Universum senden, keines sich selbst sperren.
        self._schreibe(_zeile(1, P2, "AAA"), _zeile(3, P0, "AAA"))
        WELT.enttecs = {P0: "AAA", P2: "CCC"}
        self._uebernehmen()
        w = self._worker(1, 3)
        self.assertEqual(("CCC", "AAA"), (w[1].dongle(), w[3].dongle()))
        notes = getattr(self.state, "enttec_port_notes", {})
        self.assertIn("steht auch bei Universum 3", notes.get(1) or "")
        self.assertIn("steht auch bei Universum 1", notes.get(3) or "")
        self._nachfuehren()
        self._speichern_abwarten()
        z = self._zeilen()
        self.assertEqual(("CCC", "AAA"), (z[1][FELD], z[3][FELD]))

    def test_vormerken_verwirft_doppelte(self):
        with redirect_stdout(io.StringIO()):
            self.om.enttec_seriennr_vormerken({1: "AAA", 3: "AAA", 4: "DDD"})
        self.assertEqual({4: "DDD"}, self.om._enttec_sn_tabelle())


# ── alte Zeilen ohne Nummer ──────────────────────────────────────────────────

class AlteZeilen(_Basis):

    def test_laedt_und_lernt_und_speichert(self):
        self._schreibe(_zeile(1, P0), _zeile(2, P1))
        WELT.enttecs = {P0: "AAA", P1: "BBB"}
        self._uebernehmen()
        self.assertIsNone(self._px(1).seriennr)
        w = self._worker(1, 2)
        self.assertEqual(("AAA", "BBB"), (w[1].dongle(), w[2].dongle()))
        self._nachfuehren()
        self._speichern_abwarten()
        z = self._zeilen()
        self.assertEqual(("AAA", "BBB"), (z[1][FELD], z[2][FELD]))
        self.assertEqual((P0, P1), (z[1]["patch"], z[2]["patch"]))

    def test_nur_bei_aenderung_geschrieben(self):
        self._schreibe(_zeile(1, P0, "AAA"))
        WELT.enttecs = {P0: "AAA"}
        self._uebernehmen()
        self._worker(1)
        mtime = os.stat(self.pfad).st_mtime_ns
        with mock.patch.object(enttec_konfig, "atomar_schreiben") as schreiben:
            for _ in range(5):
                self._nachfuehren()
            self.state._enttec_sn_speicher.warten()
        schreiben.assert_not_called()
        self.assertEqual(mtime, os.stat(self.pfad).st_mtime_ns)

    def test_andere_zeilen_und_felder_bleiben(self):
        self._schreibe(_zeile(1, P0),
                       {"num": 2, "name": "Netz", "output": "ArtNet",
                        "patch": "10.0.0.255", "out_universe": 7})
        WELT.enttecs = {P0: "AAA"}
        with mock.patch.object(self.om, "add_artnet", lambda *a, **k: None):
            self._uebernehmen()
        self._worker(1)
        self._nachfuehren()
        self._speichern_abwarten()
        z = self._zeilen()
        self.assertEqual("AAA", z[1][FELD])
        self.assertEqual({"num": 2, "name": "Netz", "output": "ArtNet",
                          "patch": "10.0.0.255", "out_universe": 7}, z[2])


# ── „Übernehmen“ zur Laufzeit ────────────────────────────────────────────────

class UebernehmenNachVertauschen(_Basis):

    def _laufzeit_vertauscht(self):
        """Start richtig, dann beide Dongles abgezogen und vertauscht wieder
        eingesteckt — der Reconnect folgt jedem Dongle (OUT-66)."""
        self._schreibe(_zeile(1, P0), _zeile(2, P1))
        WELT.enttecs = {P0: "AAA", P1: "BBB"}
        self._uebernehmen()
        w = self._worker(1, 2)
        self._nachfuehren()
        self._speichern_abwarten()
        w[1].abziehen()
        w[2].abziehen()
        WELT.enttecs = {P0: "BBB", P1: "AAA"}
        w[1].reconnect()
        w[2].reconnect()
        self._nachfuehren()
        self.assertEqual(("AAA", "BBB"), (w[1].dongle(), w[2].dongle()))
        self.assertEqual((P1, P0), (self._px(1).port_aktuell,
                                    self._px(2).port_aktuell))
        return w

    def test_verbinden_eines_universums_verdraengt_das_andere_nicht(self):
        # U1 sendet (verbunden) ueber P1; U2 wird an P1 neu angelegt (Dialog
        # „Verbinden“ mit gespeicherter Nummer) -> U1 bleibt stehen.
        w = self._laufzeit_vertauscht()
        self.om.remove_output(2)
        self.om.add_enttec(2, P1, seriennr="BBB")
        self.assertIn(1, self.om._enttec_outputs, "U1 von U2 verdraengt")
        self.assertEqual("AAA", w[1].dongle())
        w[2].dev._ser.close()                    # alter Worker von U2 endet
        neu = self._worker(2)
        self.assertEqual("BBB", neu[2].dongle())

    def test_ohne_nummer_wird_weiter_verdraengt(self):
        # Bestandsverhalten (OUT-66): kennt die neue Ausgabe keine Nummer,
        # raeumt sie den Port — ein Dongle hat genau einen Ausgang.
        self._laufzeit_vertauscht()
        self.om.remove_output(2)
        self.om.add_enttec(2, P1)
        self.assertNotIn(1, self.om._enttec_outputs)

    def test_in_prozess_kein_tausch(self):
        os.environ["LIGHTOS_SERIAL_INPROC"] = "1"
        self._schreibe(_zeile(1, P0), _zeile(2, P1))
        WELT.enttecs = {P0: "AAA", P1: "BBB"}
        with mock.patch.object(enttec_pro, "_OFFEN", {}), \
                mock.patch.object(enttec_pro, "_SN_BESITZER", {}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self._uebernehmen()
            self._nachfuehren()
            for u in (1, 2):
                self._px(u)._disable()
            WELT.enttecs = {P0: "BBB", P1: "AAA"}
            for u in (1, 2):
                self._px(u)._last_reconnect = -1e9
                self._px(u).send_dmx(bytes(512))
            self.assertEqual((P1, P0), (self._px(1).port, self._px(2).port))
            self._uebernehmen()
            self.assertEqual({1, 2}, set(self.om._enttec_outputs))
            a, b = self._px(1), self._px(2)
            self.assertEqual(("AAA", "BBB"), (a._ser.sn, b._ser.sn))
            self.assertTrue(a.is_open() and b.is_open())
            for u in (1, 2):
                self.om.remove_output(u)

    def test_kein_tausch(self):
        self._laufzeit_vertauscht()
        self._uebernehmen()
        self.assertEqual({1, 2}, set(self.om._enttec_outputs),
                         "„Übernehmen“ hat ein Universum verdraengt")
        w = self._worker(1, 2)
        self.assertEqual("AAA", w[1].dongle(), "U1 nach „Übernehmen“ getauscht")
        self.assertEqual("BBB", w[2].dongle(), "U2 nach „Übernehmen“ getauscht")

    def test_dialog_ohne_nummer_gespeichert_behaelt_laufende(self):
        # Der Dialog schrieb seine Tabelle, bevor die Nummer gespeichert war:
        # das Feld fehlt -> die des laufenden Geraets gilt.
        self._laufzeit_vertauscht()
        self._schreibe(_zeile(1, P0), _zeile(2, P1))
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertEqual(("AAA", "BBB"), (w[1].dongle(), w[2].dongle()))

    def test_gespeicherte_nummer_gilt_vor_dem_port(self):
        # Datei nennt P1 MIT der Nummer AAA (so sieht ein Neustart nach dem
        # Vertauschen aus): der Dongle zaehlt, nicht der Port. Eine
        # Portaenderung im Dialog schreibt dagegen "" (s. DialogTest).
        self._schreibe(_zeile(1, P0, "AAA"))
        WELT.enttecs = {P0: "AAA"}
        self._uebernehmen()
        self._worker(1)
        self._schreibe(_zeile(1, P1, "AAA"))
        WELT.enttecs = {P0: "AAA", P1: "CCC"}
        self._px(1)                                   # laeuft noch
        self._uebernehmen()
        w = self._worker(1)
        self.assertEqual("AAA", w[1].dongle())
        self.assertEqual("AAA", self._zeilen()[1][FELD])

    def test_portaenderung_aus_dem_dialog_nimmt_den_neuen_dongle(self):
        # Gegenpruefung Befund 2: der Dialog schreibt bei neuem Port "" —
        # dann sendet U1 auf dem Dongle am gewaehlten Port, nicht still weiter
        # auf dem alten.
        self._schreibe(_zeile(1, P0, "AAA"))
        WELT.enttecs = {P0: "AAA"}
        self._uebernehmen()
        self._worker(1)
        self._schreibe(_zeile(1, P2, ""))
        WELT.enttecs = {P0: "AAA", P2: "CCC"}
        self._uebernehmen()
        w = self._worker(1)
        self.assertEqual("CCC", w[1].dongle(), "gewaehlter Port ignoriert")
        self._nachfuehren()
        self._speichern_abwarten()
        self.assertEqual("CCC", self._zeilen()[1][FELD])

    def test_not_aus_sperre_greift_nach_uebernehmen(self):
        self._laufzeit_vertauscht()
        self.om.add_universe(1)
        self.om.add_universe(2)
        self.om.universes[1].set_channel(40, 255)
        self.om.universes[2].set_channel(40, 255)
        self.om.set_laser_estop_mask({1: frozenset({40})}, True)
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertEqual("AAA", w[1].dongle())
        self.om._send_all()
        self.assertEqual(0, bytes(self._px(1)._buf.get_obj())[39],
                         "NOT-AUS: Laser-Adresse geht auf dem Dongle von U1 raus")
        # Der Laser haengt an AAA; U2 sendet jetzt ueber P0, den Port, den U1
        # konfiguriert hat -> dieselbe Sperre (lieber zu viel als zu wenig).
        self.assertEqual(0, bytes(self._px(2)._buf.get_obj())[39],
                         "NOT-AUS ueber den konfigurierten Port von U1 umgangen")


# ── Ersatz-Dongle-Regel (OUT-66) bleibt ──────────────────────────────────────

class ErsatzRegel(_Basis):

    def test_einzel_dongle_ersatz_wird_uebernommen_und_gespeichert(self):
        self._schreibe(_zeile(1, P0, "AAA"))
        WELT.enttecs = {P0: "CCC"}
        self._uebernehmen()
        w = self._worker(1)
        self.assertEqual("CCC", w[1].dongle(), "Einzel-Dongle bleibt dunkel")
        self._nachfuehren()
        self.assertIn("übernommen", self._hinweis(1))
        self._speichern_abwarten()
        self.assertEqual("CCC", self._zeilen()[1][FELD])

    def test_ersatz_am_port_wenn_andere_ihre_nummer_kennt(self):
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1, "BBB"))
        WELT.enttecs = {P0: "CCC", P1: "BBB"}
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertEqual(("CCC", "BBB"), (w[1].dongle(), w[2].dongle()))

    def test_ersatz_gesperrt_solange_andere_ohne_nummer(self):
        self._schreibe(_zeile(1, P0, "AAA"), _zeile(2, P1))
        WELT.enttecs = {P0: "CCC"}
        self._uebernehmen()
        w = self._worker(1, 2)
        self.assertIsNone(w[1].dongle(),
                          "Ersatz uebernommen, obwohl U2 seinen Dongle nicht kennt")
        self.assertIn("Nicht übernommen", self._hinweis(1))


# ── „Dongle neu zuordnen“ ────────────────────────────────────────────────────

class Vergessen(_Basis):

    def test_leeres_feld_gibt_keine_nummer_mit(self):
        self._schreibe(_zeile(1, P0, "AAA"))
        WELT.enttecs = {P0: "AAA"}
        self._uebernehmen()
        self._worker(1)
        # „vergessen“ + Speichern: Feld leer; jetzt steckt CCC am Port.
        self._schreibe(_zeile(1, P0, ""))
        WELT.enttecs = {P0: "CCC", P1: "AAA"}
        self._uebernehmen()
        self.assertIsNone(self._px(1).seriennr,
                          "vergessene Nummer (oder die laufende) mitgegeben")
        w = self._worker(1)
        self.assertEqual("CCC", w[1].dongle())
        self._nachfuehren()
        self.assertNotIn("übernommen", self._hinweis(1))
        self._speichern_abwarten()
        self.assertEqual("CCC", self._zeilen()[1][FELD])


# ── Dialog ───────────────────────────────────────────────────────────────────

class _DialogBasis(unittest.TestCase):
    #: True = der echte ``add_enttec`` des Managers laeuft (mit Attrappen).
    ECHT = False

    def _echt_vorbereiten(self):
        pass

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        import src.ui.widgets.output_config as oc
        self.oc = oc
        QApplication.instance() or QApplication([])
        fd, self.pfad = tempfile.mkstemp(suffix="_out80_dialog.json")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.pfad) and os.remove(self.pfad))
        alt = oc._UNIV_CONFIG_PATH
        oc._UNIV_CONFIG_PATH = self.pfad
        self.addCleanup(setattr, oc, "_UNIV_CONFIG_PATH", alt)
        oc._save_universe_config([
            _zeile(1, P0, "EN0314159"),
            {"num": 2, "name": "Netz", "output": "Disabled", "patch": ""},
        ])
        from src.core.app_state import get_state
        state = get_state()
        om = state.output_manager
        self.add_enttec_aufrufe = []
        self.om = om
        if self.ECHT:
            self._echt_vorbereiten()
        else:
            p = mock.patch.object(om, "add_enttec", lambda *a, **k:
                                  self.add_enttec_aufrufe.append((a, k)))
            p.start(); self.addCleanup(p.stop)
            p = mock.patch.object(om, "remove_output", lambda *a, **k: None)
            p.start(); self.addCleanup(p.stop)
            # Die Seriennummer-Tabelle des (geteilten) Managers je Test frisch.
            p = mock.patch.object(om, "_enttec_sn_konfig", {}, create=True)
            p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(state, "apply_output_config", lambda *a, **k: None)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(oc, "QMessageBox")
        p.start(); self.addCleanup(p.stop)
        self.dlg = oc.OutputConfigDialog()
        self.addCleanup(self._zu)

    def _zu(self):
        self.dlg.close()
        self.dlg.deleteLater()
        from PySide6.QtWidgets import QApplication
        from _qt_lifecycle import destroy_all_top_level_widgets
        destroy_all_top_level_widgets(QApplication.instance())

    def _datei(self):
        with open(self.pfad, encoding="utf-8") as f:
            return {r["num"]: r for r in json.load(f)}

    def _verbinden(self, univ, port):
        self.dlg._enttec_status_pruefen_spaeter = lambda *a, **k: None
        self.dlg._combo_port.clear()
        self.dlg._combo_port.addItem("Test", port)
        self.dlg._combo_port.setCurrentIndex(0)
        self.dlg._spin_enttec_univ.setValue(univ)
        self.dlg._connect_enttec()


class DialogTest(_DialogBasis):

    def test_zeigt_gekuerzt(self):
        t = self.dlg._univ_table
        self.assertEqual("Dongle", t.horizontalHeaderItem(5).text())
        self.assertEqual("Seriennr. …4159", t.item(0, 5).text())
        self.assertNotIn("EN0314159", t.item(0, 5).text())
        self.assertEqual("—", t.item(1, 5).text())

    def test_speichern_ohne_portaenderung_behaelt_nummer(self):
        self.dlg._univ_table.item(0, 1).setText("Bühne")
        self.dlg._univ_save()
        z = self._datei()
        self.assertEqual((P0, "EN0314159"), (z[1]["patch"], z[1][FELD]))
        self.assertNotIn(FELD, z[2])

    def test_neuer_port_vergisst_nummer(self):
        # Gegenpruefung Befund 2: ein ausdruecklich anderer Port meint einen
        # anderen Dongle — sonst sendete U1 still weiter auf dem alten.
        self.dlg._univ_table.item(0, 3).setText(P1)
        self.dlg._univ_save()
        z = self._datei()
        self.assertEqual((P1, ""), (z[1]["patch"], z[1][FELD]))
        self.assertNotIn(FELD, z[2])

    def test_umnummerieren_und_neue_zeile_erbt_keine_nummer(self):
        # Gegenpruefung Befund 1: Zeile 1 -> # 3, neue Zeile 1 (Enttec).
        t = self.dlg._univ_table
        t.item(0, 0).setText("3")
        self.dlg._univ_add()
        neu = t.rowCount() - 1
        t.item(neu, 0).setText("1")
        t.cellWidget(neu, 2).setCurrentText("Enttec")
        t.item(neu, 3).setText(P1)
        self.dlg._univ_save()
        z = self._datei()
        self.assertEqual("EN0314159", z[3][FELD])
        self.assertEqual("", z[1].get(FELD, ""))
        self.assertEqual("Enttec", z[1]["output"])

    def test_warnung_waehrend_speichern_verliert_gelernte_nicht(self):
        # Gegenpruefung Befund 4: waehrend eine Warnung offen ist (eigene
        # Ereignisschleife), lernt der Hintergrund eine neue Nummer.
        def _gelernt(*_a, **_k):
            enttec_konfig.seriennr_eintragen(self.pfad, 1, "EN0888888")
        self.oc.QMessageBox.warning.side_effect = _gelernt
        self.dlg._univ_table.item(1, 0).setText("99")   # -> Warnung (Klemmung)
        self.dlg._univ_save()
        self.assertTrue(self.oc.QMessageBox.warning.called)
        self.assertEqual("EN0888888", self._datei()[1][FELD])

    def test_im_hintergrund_gelernte_nummer_geht_nicht_verloren(self):
        rows = self.oc._load_universe_config()
        rows[0][FELD] = "EN0777777"            # nach dem Oeffnen des Dialogs gelernt
        self.oc._save_universe_config(rows)
        self.dlg._univ_save()
        self.assertEqual("EN0777777", self._datei()[1][FELD])

    def test_dongle_neu_zuordnen(self):
        self.dlg._univ_table.selectRow(0)
        self.dlg._btn_dongle_neu.click()
        self.assertEqual("wird neu zugeordnet", self.dlg._univ_table.item(0, 5).text())
        self.assertEqual("EN0314159", self._datei()[1][FELD], "vor dem Speichern")
        self.dlg._univ_save()
        self.assertEqual("", self._datei()[1][FELD])
        self.assertEqual("—", self.dlg._univ_table.item(0, 5).text())
        # Ein zweites Speichern vergisst nicht erneut eine inzwischen gelernte.
        rows = self.oc._load_universe_config()
        rows[0][FELD] = "EN0111111"
        self.oc._save_universe_config(rows)
        self.dlg._univ_save()
        self.assertEqual("EN0111111", self._datei()[1][FELD])

    def test_verbinden_gibt_gespeicherte_nummer_mit(self):
        self._verbinden(1, P0)
        self.assertEqual(((1, P0), {"seriennr": "EN0314159"}),
                         self.add_enttec_aufrufe[-1])
        self.assertEqual("EN0314159", self._datei()[1][FELD])

    def test_verbinden_anderer_port_ohne_alte_nummer(self):
        # Gegenpruefung Befund 2: „Verbinden“ an einem anderen Port.
        self._verbinden(1, P1)
        self.assertEqual(((1, P1), {}), self.add_enttec_aufrufe[-1])
        self.assertEqual((P1, ""), (self._datei()[1]["patch"],
                                    self._datei()[1][FELD]))

    def test_verbinden_umzug_ersetzt_nummer_der_zielzeile(self):
        # Gegenpruefung Befund 2: U2 (P1, EN0222222) gibt seinen Adapter an U1.
        rows = self.oc._load_universe_config()
        rows[1].update(output="Enttec", patch=P1, **{FELD: "EN0222222"})
        self.oc._save_universe_config(rows)
        self._verbinden(1, P1)
        self.assertEqual(((1, P1), {"seriennr": "EN0222222"}),
                         self.add_enttec_aufrufe[-1])
        z = self._datei()
        self.assertEqual("EN0222222", z[1][FELD])
        self.assertNotIn(FELD, z[2])

    def test_verbinden_umzug_nimmt_nummer_mit(self):
        self.dlg._enttec_status_pruefen_spaeter = lambda *a, **k: None
        self.dlg._combo_port.clear()
        self.dlg._combo_port.addItem("Test", P0)
        self.dlg._combo_port.setCurrentIndex(0)
        self.dlg._spin_enttec_univ.setValue(2)
        self.dlg._connect_enttec()
        self.assertEqual(((2, P0), {"seriennr": "EN0314159"}),
                         self.add_enttec_aufrufe[-1])
        z = self._datei()
        self.assertEqual("EN0314159", z[2][FELD])
        self.assertNotIn(FELD, z[1])


# ── Gegenpruefung 2: keine zwei Namen fuer einen Anschluss ───────────────────

class KeineStabilenNamen(unittest.TestCase):
    """Entscheidung: by-id-Namen bietet OUT-80 NICHT an (sie galten in den
    NOT-AUS-Weg-Schluesseln als anderer Anschluss)."""

    def test_port_auswahl_ohne_by_id(self):
        self.assertFalse(hasattr(anschluss_auswahl, "mit_stabilen_namen"))
        self.assertFalse(hasattr(anschluss_auswahl, "BY_ID_ORDNER"))

    def test_gleicher_port_nur_windows_schreibweise(self):
        import src.ui.widgets.output_config as oc
        self.assertTrue(oc._gleicher_port("COM3", "com3"))
        self.assertTrue(oc._gleicher_port(" COM3", "COM3 "))
        self.assertFalse(oc._gleicher_port("COM3", "COM4"))
        self.assertFalse(oc._gleicher_port("", ""))
        self.assertTrue(oc._gleicher_port(P0, P0))
        self.assertFalse(oc._gleicher_port(P0, P1))

    @unittest.skipUnless(os.name == "posix", "Symlinks als Portnamen: POSIX")
    def test_gleicher_port_loest_keine_symlinks_auf(self):
        import src.ui.widgets.output_config as oc
        with tempfile.TemporaryDirectory() as d:
            ziel = os.path.join(d, "ttyFAKE_OUT80")
            open(ziel, "w").close()
            link = os.path.join(d, "usb-ENTTEC_DMX_USB_PRO_EN123456-if00-port0")
            os.symlink(ziel, link)
            self.assertFalse(oc._gleicher_port(link, ziel))


class _Sender:
    gesendet: dict = {}

    def __init__(self, port):
        self.port = port

    def send_dmx(self, data):
        _Sender.gesendet[self.port] = bytes(data)

    def close(self):
        pass

    def is_open(self):
        return True


@unittest.skipUnless(os.name == "posix", "Symlinks als Portnamen: POSIX")
class NotAusZweiNamenEinAnschluss(unittest.TestCase):
    """Gegenpruefung 2, Befund 1: ein von Hand eingetippter by-id-Name und der
    tty-Name desselben Anschlusses sind EIN Ausgabeweg (OUT-64)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ziel = os.path.join(tmp.name, "ttyFAKE_OUT80_1")
        open(self.ziel, "w").close()
        self.link = os.path.join(tmp.name,
                                 "usb-ENTTEC_DMX_USB_PRO_EN123456-if00-port0")
        os.symlink(self.ziel, self.link)
        p = mock.patch.object(om_mod, "_make_enttec_device", _Sender)
        p.start()
        self.addCleanup(p.stop)
        _Sender.gesendet = {}
        self.om = om_mod.OutputManager()
        for u in (1, 2):
            self.om.add_universe(u)
        self.om.universes[1].set_channel(40, 255)
        self.om.universes[2].set_channel(40, 255)

    def _senden(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.om._send_all()

    def _pruefen(self, laser_port, anderer_port, laser_weg_entfernen):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.om.add_enttec(1, laser_port)
            self.om.set_laser_estop_mask({1: frozenset({40})}, True)
            if laser_weg_entfernen:
                self.om.remove_output(1)
            self.om.add_enttec(2, anderer_port)
        self._senden()
        self.assertEqual(0, _Sender.gesendet[anderer_port][39],
                         f"NOT-AUS umgangen: Laser an {laser_port}, "
                         f"U2 an {anderer_port}")

    def test_laser_an_by_id_dann_tty(self):
        self._pruefen(self.link, self.ziel, False)

    def test_laser_an_by_id_entfernt_dann_tty(self):
        self._pruefen(self.link, self.ziel, True)

    def test_laser_an_tty_dann_by_id(self):
        self._pruefen(self.ziel, self.link, True)

    def test_ungesperrt_bleibt_255(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.om.add_enttec(2, self.ziel)
        self._senden()
        self.assertEqual(255, _Sender.gesendet[self.ziel][39])


class Diagnose(unittest.TestCase):

    def test_by_id_name_gekuerzt(self):
        from src.core.diagnose_log import anonymisiere
        text = anonymisiere(
            "U1 Enttec → /dev/serial/by-id/usb-ENTTEC_DMX_USB_PRO_EN555123-if00-port0")
        self.assertNotIn("EN0555123", text)
        self.assertIn("usb-ENTTEC_DMX_USB_PRO_…5123-if00-port0", text)
        self.assertEqual(text, anonymisiere(text))

    def test_einstellungen_zeigen_nummer_gekuerzt(self):
        from src.core import diagnose_log
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "universes.json"), "w", encoding="utf-8") as f:
                json.dump([_zeile(1, P0, "EN0555123")], f)
            with mock.patch.object(diagnose_log, "app_data_dir", lambda: d):
                text = diagnose_log.einstellungen_text()
        self.assertIn("Dongle Seriennr. …5123", text)
        self.assertNotIn("EN0555123", text)

    def test_ausgabe_status_und_dmx_infos(self):
        from src.core import diagnose_log
        om = om_mod.OutputManager()
        dev = SimpleNamespace(port=P0, konfig_port=P0, seriennr="EN0555123",
                              is_open=lambda: True, close=lambda: None,
                              hinweis=lambda: "")
        om._enttec_outputs[1] = dev
        eintrag = [e for e in om.ausgabe_status() if e["weg"] == "Enttec"][0]
        self.assertEqual("EN0555123", eintrag["seriennr"])
        state = SimpleNamespace(output_manager=om)
        mod = SimpleNamespace(_state=state)
        with mock.patch.dict(sys.modules, {"src.core.app_state": mod}):
            zeilen = diagnose_log.dmx_infos()
        self.assertIn("Dongle Seriennr. …5123", zeilen[0])
        self.assertNotIn("EN0555123", zeilen[0])


class Speicher(unittest.TestCase):

    def test_atomar_und_nur_enttec_zeile(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(pfad, [
                _zeile(1, P0), {"num": 2, "output": "ArtNet", "patch": ""}])
            self.assertTrue(enttec_konfig.seriennr_eintragen(pfad, 1, "AAA"))
            self.assertFalse(enttec_konfig.seriennr_eintragen(pfad, 1, "AAA"))
            self.assertFalse(enttec_konfig.seriennr_eintragen(pfad, 2, "BBB"))
            self.assertFalse(enttec_konfig.seriennr_eintragen(pfad, 3, "CCC"))
            self.assertEqual(["universes.json"], os.listdir(d), "Hilfsdatei bleibt liegen")
            with open(pfad, encoding="utf-8") as f:
                rows = json.load(f)
            self.assertEqual("AAA", rows[0][FELD])
            self.assertNotIn(FELD, rows[1])

    def test_eintragen_entfernt_nummer_aus_anderen_zeilen(self):
        # Gegenpruefung Befund 1: ein Dongle, ein Ausgang.
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(pfad, [
                _zeile(1, P2, "AAA"), _zeile(3, P0)])
            self.assertTrue(enttec_konfig.seriennr_eintragen(pfad, 3, "AAA"))
            with open(pfad, encoding="utf-8") as f:
                rows = json.load(f)
            self.assertNotIn(FELD, rows[0])
            self.assertEqual("AAA", rows[1][FELD])
            # Auch wenn die eigene Zeile die Nummer schon traegt.
            enttec_konfig.atomar_schreiben(pfad, [
                _zeile(1, P2, "AAA"), _zeile(3, P0, "AAA")])
            self.assertTrue(enttec_konfig.seriennr_eintragen(pfad, 3, "AAA"))
            with open(pfad, encoding="utf-8") as f:
                self.assertNotIn(FELD, json.load(f)[0])

    def test_schreibfehler_laesst_datei_stehen(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(pfad, [_zeile(1, P0)])
            with mock.patch.object(enttec_konfig.json, "dump",
                                   side_effect=OSError("voll")), \
                    redirect_stdout(io.StringIO()):
                self.assertFalse(enttec_konfig.seriennr_eintragen(pfad, 1, "AAA"))
            self.assertEqual(["universes.json"], os.listdir(d))
            with open(pfad, encoding="utf-8") as f:
                self.assertNotIn(FELD, json.load(f)[0])

    def test_persist_output_unter_datei_lock(self):
        # Gegenpruefung 2, Befund 4: Lesen-Aendern-Schreiben unter der Sperre
        # des Hintergrund-Speichers.
        import threading
        import src.ui.widgets.output_config as oc
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(pfad, [_zeile(1, P0)])
            frei_beim_lesen = []
            orig = oc._load_universe_config

            def _laden():
                ergebnis = {}

                def _anderer_thread():
                    ok = enttec_konfig.DATEI_LOCK.acquire(blocking=False)
                    if ok:
                        enttec_konfig.DATEI_LOCK.release()
                    ergebnis["frei"] = ok
                t = threading.Thread(target=_anderer_thread)
                t.start()
                t.join()
                frei_beim_lesen.append(ergebnis["frei"])
                return orig()
            with mock.patch.object(oc, "_UNIV_CONFIG_PATH", pfad), \
                    mock.patch.object(oc, "_load_universe_config", _laden):
                self.assertTrue(oc._persist_output(1, "Enttec", P1))
            self.assertEqual([False], frei_beim_lesen,
                             "universes.json ohne DATEI_LOCK gelesen")

    @unittest.skipIf(getattr(os, "geteuid", lambda: 1)() == 0,
                     "root darf schreibgeschuetzte Dateien schreiben")
    def test_schreibgeschuetzte_datei_bleibt(self):
        # Gegenpruefung 2, Befund 5: os.replace haette den Schutz entfernt.
        import stat
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(pfad, [_zeile(1, P0)])
            with open(pfad, encoding="utf-8") as f:
                vorher = f.read()
            os.chmod(pfad, stat.S_IREAD)
            try:
                with redirect_stdout(io.StringIO()) as aus:
                    self.assertFalse(enttec_konfig.atomar_schreiben(
                        pfad, [_zeile(1, P1)]))
                self.assertIn("nicht geschrieben", aus.getvalue())
                self.assertFalse(os.access(pfad, os.W_OK),
                                 "Schreibschutz verschwunden")
                with open(pfad, encoding="utf-8") as f:
                    self.assertEqual(vorher, f.read())
                self.assertEqual(["universes.json"], os.listdir(d))
            finally:
                os.chmod(pfad, stat.S_IREAD | stat.S_IWRITE)

    def test_symlink_bleibt_symlink(self):
        # Gegenpruefung 2, Befund 5: das ZIEL wird ersetzt, nicht der Link.
        with tempfile.TemporaryDirectory() as d:
            ziel = os.path.join(d, "echt.json")
            link = os.path.join(d, "universes.json")
            enttec_konfig.atomar_schreiben(ziel, [_zeile(1, P0)])
            try:
                os.symlink(ziel, link)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks hier nicht erlaubt")
            self.assertTrue(enttec_konfig.seriennr_eintragen(link, 1, "AAA"))
            self.assertTrue(os.path.islink(link), "Symlink durch Datei ersetzt")
            with open(ziel, encoding="utf-8") as f:
                self.assertEqual("AAA", json.load(f)[0][FELD])
            self.assertEqual(sorted(["echt.json", "universes.json"]),
                             sorted(os.listdir(d)))


# ── Gegenpruefung 2, Befund 3: „Verbinden“ mit echtem add_enttec ────────────

class _DialogEcht(_DialogBasis):
    """Wie :class:`DialogTest`, aber ``add_enttec``/``remove_output`` des
    Managers laufen echt — mit Attrappen-Ports (``comports``, ``Serial``) und
    Attrappen-Prozess. Kein echter serieller Port."""
    ECHT = True
    INPROC = False

    def _echt_vorbereiten(self):
        global WELT
        WELT = _Welt()
        WELT.enttecs = {P1: "EN0999999"}
        self.proxies = []
        test = self

        class _Proxy(sp.EnttecProcessProxy):
            def __init__(self, port, **kw):
                kw.setdefault("_process_factory", _FakeProc)
                super().__init__(port, **kw)
                test.proxies.append(self)

        self.gemeldet = []
        patches = [
            mock.patch.object(serial.tools.list_ports, "comports",
                              lambda *a, **k: WELT.comports()),
            mock.patch.object(enttec_pro.serial, "Serial", _FakeSerial),
            mock.patch.object(sp, "EnttecProcessProxy", _Proxy),
            mock.patch("src.core.dmx.port_check.warne_wenn_belegt",
                       lambda *_a, **_k: None, create=True),
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(enttec_pro, "_OFFEN", {}),
            mock.patch.object(enttec_pro, "_SN_BESITZER", {}),
            # Rueckruf des Hintergrund-Speichers: hier nur mitschreiben.
            mock.patch.object(self.om, "bei_enttec_seriennr",
                              lambda u, sn: self.gemeldet.append((u, sn)),
                              create=True),
            mock.patch.object(self.om, "_enttec_sn_konfig", {}, create=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        if self.INPROC:
            os.environ["LIGHTOS_SERIAL_INPROC"] = "1"
        else:
            os.environ.pop("LIGHTOS_SERIAL_INPROC", None)
        self.addCleanup(self._echt_zu)

    def _echt_zu(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.om.remove_output(1)
        for px in self.proxies:
            px.close()

    def _verbinden_still(self, univ, port):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self._verbinden(univ, port)

    def _nachfuehren(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.om._enttec_fremde_nachfuehren()


class DialogVerbindenInProzess(_DialogEcht):
    INPROC = True

    def test_gelernte_nummer_wird_gespeichert_nicht_geleert(self):
        # „Verbinden“ an einem anderen Port: add_enttec oeffnet sofort und
        # lernt EN0999999 — die Zeile darf danach nicht "" tragen.
        self._verbinden_still(1, P1)
        self.assertEqual("EN0999999", self.om.enttec_seriennr(1))
        z = self._datei()
        self.assertEqual((P1, "EN0999999"), (z[1]["patch"], z[1][FELD]),
                         "gelernte Nummer beim naechsten Start vergessen")


class DialogVerbindenProxy(_DialogEcht):

    def _lernt(self, px, sn="EN0999999"):
        sp._schreib_text(px._seriennr, sn, sp.SN_BYTES)
        self._nachfuehren()

    def test_spaeter_gelernte_nummer_wird_gemeldet(self):
        self._verbinden_still(1, P1)
        self.assertEqual("", self._datei()[1][FELD])
        self._lernt(self.om._enttec_outputs[1])
        self.assertIn((1, "EN0999999"), self.gemeldet)

    def test_gelernt_zwischen_anlegen_und_speichern(self):
        # Der Worker meldet die Nummer, bevor „Verbinden“ die Zeile schreibt.
        orig = self.om.add_enttec

        def _add(*a, **k):
            orig(*a, **k)
            self._lernt(self.om._enttec_outputs[1])
        with mock.patch.object(self.om, "add_enttec", _add):
            self._verbinden_still(1, P1)
        self.assertEqual("EN0999999", self._datei()[1][FELD])

    def test_gelernt_waehrend_des_speicherns_wird_erneut_gemeldet(self):
        # Die Nummer kommt erst, waehrend die Zeile mit "" geschrieben wird:
        # der naechste Abgleich meldet sie erneut, statt sie zu verschlucken.
        import src.ui.widgets.output_config as oc
        orig = oc._persist_output_ungesperrt

        def _persist(*a, **k):
            self._lernt(self.om._enttec_outputs[1])
            return orig(*a, **k)
        with mock.patch.object(oc, "_persist_output_ungesperrt", _persist):
            self._verbinden_still(1, P1)
        self.gemeldet.clear()
        self._nachfuehren()
        self.assertIn((1, "EN0999999"), self.gemeldet,
                      "gelernte Nummer nie mehr gemeldet")


if __name__ == "__main__":
    unittest.main()

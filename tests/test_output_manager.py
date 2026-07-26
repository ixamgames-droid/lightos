"""Regressionstests fuer OutputManager Thread-Disziplin.

Hintergrund (Bug 2026-06-02): Render UND Senden laufen im selben 44-Hz-Thread.
Beim 'Ausgabe neu starten' schloss der UI-Thread ein Geraet, waehrend der
Output-Thread mitten im send_dmx() steckte -> Deadlock (pyserial/Windows) ->
komplettes Einfrieren der App. Diese Tests sichern die Fixes ab:
- Reconnect schliesst das alte Geraet (kein Port-Leak / 'Access denied').
- Eine Exception im Geraet beendet den Output-Thread NICHT.
- Connect/Disconnect waehrend laufender Ausgabe fuehrt nicht zum Deadlock.
- start() ist idempotent (kein zweiter Thread).
- stop() blockiert nicht ewig, selbst bei langsamem/haengendem Geraet.
"""
import os
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.output_manager import OutputManager


class _FakeDev:
    """Minimal-Stub fuer ein Ausgabe-Geraet (Enttec-Signatur: send_dmx(data))."""
    def __init__(self, port="COM_FAKE"):
        self.port = port
        self.closed = False
        self.sends = 0

    def send_dmx(self, data):
        self.sends += 1

    def close(self):
        self.closed = True


class _RaisingDev(_FakeDev):
    def send_dmx(self, data):
        raise RuntimeError("device boom")


class _SlowDev(_FakeDev):
    """Simuliert ein haengendes write() (z. B. Enttec ohne write_timeout)."""
    def __init__(self, delay=0.2, **kw):
        super().__init__(**kw)
        self.delay = delay

    def send_dmx(self, data):
        time.sleep(self.delay)
        self.sends += 1


class TestOutputManagerThreading(unittest.TestCase):
    def setUp(self):
        self.om = OutputManager()
        self.om.add_universe(1)

    def tearDown(self):
        self.om.stop()

    def test_reconnect_closes_previous_device(self):
        d1 = _FakeDev()
        d2 = _FakeDev()
        self.om._swap_device(self.om._enttec_outputs, 1, d1)
        self.om._swap_device(self.om._enttec_outputs, 1, d2)
        self.assertTrue(d1.closed, "altes Geraet muss beim Reconnect geschlossen werden")
        self.assertFalse(d2.closed)
        self.assertIs(self.om._enttec_outputs[1], d2)

    def test_close_enttec_on_port(self):
        d = _FakeDev(port="COM7")
        self.om._enttec_outputs[2] = d
        self.om.close_enttec_on_port("COM7")
        self.assertTrue(d.closed)
        self.assertNotIn(2, self.om._enttec_outputs)

    def test_remove_output_closes_all_adapters(self):
        """OUT-05: remove_output(u) popt+schliesst Enttec/ArtNet/sACN dieses
        Universums; andere Universen bleiben unberuehrt."""
        d_en, d_an, d_sa, other = _FakeDev(), _FakeDev(), _FakeDev(), _FakeDev()
        self.om._enttec_outputs[1] = d_en
        self.om._artnet_outputs[1] = d_an
        self.om._sacn_outputs[1] = d_sa
        self.om._artnet_outputs[2] = other            # anderes Universe
        self.om.remove_output(1)
        self.assertTrue(d_en.closed and d_an.closed and d_sa.closed)
        self.assertNotIn(1, self.om._enttec_outputs)
        self.assertNotIn(1, self.om._artnet_outputs)
        self.assertNotIn(1, self.om._sacn_outputs)
        self.assertIs(self.om._artnet_outputs.get(2), other)   # U2 unberuehrt
        self.assertFalse(other.closed)

    def test_type_switch_leaves_single_adapter(self):
        """OUT-05: der Ablauf, den apply_output_config jetzt faehrt (remove_output
        VOR add_*), laesst pro Universe genau EINEN Adapter zurueck — kein
        Doppel-Output nach einem Typ-Wechsel."""
        self.om.add_artnet(1, "255.255.255.255")
        self.assertIn(1, self.om._artnet_outputs)
        self.om.remove_output(1)                      # wie apply_output_config
        self.om.add_sacn(1, None)
        self.assertNotIn(1, self.om._artnet_outputs,
                         "alter ArtNet-Adapter muss beim Typ-Wechsel weg sein")
        self.assertIn(1, self.om._sacn_outputs)

    def test_raising_device_does_not_kill_loop(self):
        self.om._enttec_outputs[1] = _RaisingDev()
        self.om.start()
        time.sleep(0.15)
        self.assertTrue(self.om._thread.is_alive(),
                        "Output-Thread darf durch Geraete-Exception nicht sterben")

    def test_start_is_idempotent(self):
        self.om.start()
        t1 = self.om._thread
        self.om.start()
        self.assertIs(self.om._thread, t1, "start() darf keinen zweiten Thread starten")

    def test_connect_while_running_no_deadlock(self):
        """Verbinden/Trennen aus einem anderen Thread waehrend die Ausgabe laeuft
        muss schnell zurueckkehren (Lock-geschuetzt, kein Deadlock)."""
        self.om._enttec_outputs[1] = _SlowDev(delay=0.05)
        self.om.start()

        done = threading.Event()

        def reconnect():
            for _ in range(10):
                self.om._swap_device(self.om._enttec_outputs, 1, _SlowDev(delay=0.05))
            done.set()

        t = threading.Thread(target=reconnect)
        t.start()
        t.join(timeout=5.0)
        self.assertTrue(done.is_set(), "Reconnect-Schleife haengt -> Deadlock-Verdacht")

    def test_stop_returns_promptly_with_slow_device(self):
        self.om._enttec_outputs[1] = _SlowDev(delay=0.2)
        self.om.start()
        time.sleep(0.1)
        t0 = time.perf_counter()
        self.om.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 3.0, "stop() darf nicht ewig blockieren")
        self.assertFalse(self.om._thread, "Thread-Referenz nach stop() geloescht")


class TestOutputManagerStopSafety(unittest.TestCase):
    """STAB-02: stop() schliesst Geraete NUR, wenn der Output-Thread sicher
    beendet ist. Schliesst er trotz noch laufendem Thread, kollidiert CloseHandle()
    unter Windows mit einem ausstehenden WriteFile -> Access Violation beim Beenden
    (crash.log 21.+22.06.)."""

    def test_stop_closes_devices_when_thread_exits(self):
        om = OutputManager()
        om.add_universe(1)
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        om.start()
        time.sleep(0.05)
        om.stop()
        self.assertTrue(dev.closed, "sauber beendeter Thread -> Geraet wird geschlossen")
        self.assertEqual(om._enttec_outputs, {}, "Registry nach stop() geleert")

    def test_stop_skips_close_when_thread_hangs(self):
        om = OutputManager()
        om._stop_join_s = 0.1
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        release = threading.Event()
        stuck = threading.Thread(target=lambda: release.wait(3.0), daemon=True)
        stuck.start()
        om._thread = stuck
        t0 = time.perf_counter()
        om.stop()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 1.0, "stop() darf bei haengendem Thread nicht blockieren")
        self.assertFalse(dev.closed,
                         "haengender Thread -> Geraet NICHT schliessen (AV-Schutz)")
        release.set()
        stuck.join(timeout=3.0)

    def test_stop_closes_process_isolated_enttec_when_thread_hangs(self):
        """STAB-09: Der Proxy-Worker darf os._exit nicht als Waise ueberleben.

        Direkte Treiber bleiben im Timeout-Fall offen (voriger Test); der
        prozessisolierte Proxy ist sicher schliessbar, weil send_dmx nur Shared
        Memory beschreibt.
        """
        om = OutputManager()
        om._stop_join_s = 0.05
        dev = _FakeDev()
        dev.process_isolated = True
        om._enttec_outputs[1] = dev
        release = threading.Event()
        stuck = threading.Thread(target=lambda: release.wait(3.0), daemon=True)
        stuck.start()
        om._thread = stuck

        om.stop()

        self.assertTrue(dev.closed)
        self.assertNotIn(1, om._enttec_outputs)
        self.assertIs(om._thread, stuck,
                      "STAB-04: haengenden Output-Thread weiterhin verfolgen")
        release.set()
        stuck.join(timeout=3.0)

    def test_second_stop_does_not_double_close(self):
        om = OutputManager()
        dev = _FakeDev()
        om._enttec_outputs[1] = dev
        om.stop()                       # kein Thread -> schliesst direkt
        self.assertTrue(dev.closed)
        dev.closed = False
        om.stop()                       # zweites Mal -> Registry leer
        self.assertFalse(dev.closed, "zweites stop() darf nicht erneut schliessen")


class TestOutputManagerThreadTimeoutTracking(unittest.TestCase):
    """STAB-04: Endet der Output-Thread beim stop() nicht im Join-Timeout
    (haengender Treiber), wurde die Referenz frueher trotzdem auf None gesetzt.
    Ein folgender start() startete dann einen ZWEITEN Thread daneben -> zwei
    Threads schreiben gleichzeitig seriell (konkurrierende Writes / Access
    Violation, Folgebug aus STAB-02). Diese Tests sichern: Referenz bleibt
    erhalten, kein zweiter Thread, und nach echtem Thread-Ende wieder ein frischer.
    """

    @staticmethod
    def _hanging_thread(started: threading.Event, release: threading.Event):
        def hang():
            started.set()
            release.wait(3.0)   # ignoriert _running -> Join laeuft in den Timeout
        return threading.Thread(target=hang, daemon=True, name="DMX-Output")

    def test_timeout_keeps_thread_reference(self):
        om = OutputManager()
        om._stop_join_s = 0.05
        started, release = threading.Event(), threading.Event()
        om._thread = self._hanging_thread(started, release)
        om._running = True
        om._thread.start()
        self.assertTrue(started.wait(1.0))
        t1 = om._thread
        om.stop()                       # Join timeoutet -> Thread lebt noch
        self.assertTrue(t1.is_alive(), "Testvoraussetzung: Thread haengt noch")
        self.assertIs(om._thread, t1,
                      "STAB-04: Referenz auf den noch lebenden Thread muss erhalten bleiben")
        release.set()
        t1.join(timeout=3.0)

    def test_start_does_not_spawn_second_thread_while_old_alive(self):
        om = OutputManager()
        om._stop_join_s = 0.05
        started, release = threading.Event(), threading.Event()
        om._thread = self._hanging_thread(started, release)
        om._running = True
        om._thread.start()
        self.assertTrue(started.wait(1.0))
        t1 = om._thread
        om.stop()                       # Timeout -> t1 lebt weiter
        self.assertTrue(t1.is_alive())
        om.start()                      # darf KEINEN zweiten Thread starten
        self.assertIs(om._thread, t1,
                      "STAB-04: kein zweiter DMX-Thread neben dem haengenden")
        self.assertTrue(om._running,
                        "noch lebender Thread wird reaktiviert (_running=True)")
        release.set()
        t1.join(timeout=3.0)

    def test_start_spawns_fresh_after_old_thread_died(self):
        om = OutputManager()
        om._stop_join_s = 0.05
        started, release = threading.Event(), threading.Event()
        om._thread = self._hanging_thread(started, release)
        om._running = True
        om._thread.start()
        self.assertTrue(started.wait(1.0))
        t1 = om._thread
        om.stop()                       # Timeout, t1 lebt
        release.set()
        t1.join(timeout=3.0)
        self.assertFalse(t1.is_alive())
        om.start()                      # alter Thread tot -> frischer Thread
        try:
            self.assertIsNotNone(om._thread)
            self.assertIsNot(om._thread, t1,
                             "nach Thread-Ende startet start() einen frischen Thread")
            self.assertTrue(om._thread.is_alive())
        finally:
            om.stop()


class _FakeEnttec:
    """Enttec-Signatur: send_dmx(data). Zeichnet die empfangenen Frames auf."""
    def __init__(self):
        self.frames = []          # je Eintrag: bytes(data)

    def send_dmx(self, data):
        self.frames.append(bytes(data))

    def close(self):
        pass


class _FakeArtNet:
    """Art-Net-Signatur: send_dmx(universe, data). Zeichnet (universe, data) auf."""
    def __init__(self):
        self.frames = []          # je Eintrag: (universe, bytes(data))

    def send_dmx(self, universe, data):
        self.frames.append((universe, bytes(data)))

    def close(self):
        pass


class TestOutputManagerMixedSend(unittest.TestCase):
    """QA-07: Zwei Universen, zwei VERSCHIEDENE Adapter — jeder bekommt genau
    seine Frames, keiner fremde Daten; der Art-Net-Sender sieht die erwartete
    externe Universe-Nummer (``univ_num - 1``). Sichert den zentralen Mixed-Send-
    Pfad ``_send_all`` (output_manager.py) gegen Regression (falsches Routing /
    Universe-Vertauschung)."""

    def setUp(self):
        self.om = OutputManager()
        self.u1 = self.om.add_universe(1)
        self.u2 = self.om.add_universe(2)
        # GM/Blackout neutral -> Kanalwerte gehen unveraendert durch (Default ist
        # bereits GM=1.0/Blackout=False; hier explizit fuer Robustheit).
        self.om.grand_master = 1.0
        self.om._blackout = False
        # Unterscheidbare Kanal-1-Werte je Universum.
        self.u1.set_channel(1, 11)
        self.u2.set_channel(1, 22)
        self.enttec = _FakeEnttec()
        self.artnet = _FakeArtNet()
        self.om._enttec_outputs[1] = self.enttec   # Enttec bedient NUR U1
        self.om._artnet_outputs[2] = self.artnet   # Art-Net bedient NUR U2

    def tearDown(self):
        self.om.stop()

    def test_each_adapter_gets_only_its_universe(self):
        self.om._send_all()

        # Enttec (U1): genau EIN Frame, mit U1-Daten (Kanal 1 == 11).
        self.assertEqual(len(self.enttec.frames), 1, "Enttec muss genau 1 Frame kriegen")
        self.assertEqual(self.enttec.frames[0][0], 11, "Enttec sah nicht die U1-Daten")

        # Art-Net (U2): genau EIN Frame, mit U2-Daten (Kanal 1 == 22) UND der
        # erwarteten externen Universe-Nummer (univ_num-1 = 2-1 = 1).
        self.assertEqual(len(self.artnet.frames), 1, "Art-Net muss genau 1 Frame kriegen")
        art_univ, art_data = self.artnet.frames[0]
        self.assertEqual(art_univ, 1, "Art-Net-Universe muss univ_num-1 (=1) sein")
        self.assertEqual(art_data[0], 22, "Art-Net sah nicht die U2-Daten")

        # Kein Adapter sah die Daten des jeweils ANDEREN Universums.
        self.assertNotEqual(self.enttec.frames[0][0], 22, "Enttec bekam fremde (U2-)Daten")
        self.assertNotEqual(art_data[0], 11, "Art-Net bekam fremde (U1-)Daten")


class _FakeEnttecDev:
    """Stub-Enttec ohne echten COM-Port (umgeht das eager serial.Serial-open)."""
    def __init__(self, port):
        self.port = port

    def send_dmx(self, data):
        pass

    def close(self):
        pass


class TestApplyOutputConfigRoundtrip(unittest.TestCase):
    """QA-08: ``apply_output_config`` liest ``universes.json`` und richtet die
    Mixed-Adapter beim Start ein — jeder Adapter landet im RICHTIGEN Registry-Dict
    für sein Universum, und ein Fehler pro Universum bricht den Loop NICHT ab.
    Sichert die ungetestete Start-Rekonstruktion (Klasse „Output kommt nach
    Neustart nicht")."""

    def setUp(self):
        # Enttec-Port-Open umgehen: kein echter COM-Port im Test.
        import src.core.dmx.output_manager as om_mod
        self._om_mod = om_mod
        self._orig_make = om_mod._make_enttec_device
        om_mod._make_enttec_device = lambda port: _FakeEnttecDev(port)

    def tearDown(self):
        self._om_mod._make_enttec_device = self._orig_make

    def _apply(self, rows):
        """Schreibt eine temporäre universes.json und ruft
        ``AppState.apply_output_config`` auf einem Stub auf (die Methode nutzt nur
        ``self.output_manager`` + ``self.universes``). Liefert den OutputManager."""
        import json
        import os
        import tempfile
        import types
        from src.core.app_state import AppState
        stub = types.SimpleNamespace()
        stub.output_manager = OutputManager()
        stub.universes = stub.output_manager.universes
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rows, f)
            AppState.apply_output_config(stub, path=path)
        finally:
            os.remove(path)
        return stub.output_manager

    def test_mixed_adapters_land_in_right_registry(self):
        om = self._apply([
            {"num": 1, "name": "A", "output": "Enttec", "patch": "COM_FAKE"},
            {"num": 2, "name": "B", "output": "ArtNet", "patch": "127.0.0.1"},
            {"num": 3, "name": "C", "output": "sACN",   "patch": ""},
        ])
        try:
            for n in (1, 2, 3):
                self.assertIn(n, om.universes, f"Universum {n} muss angelegt sein")
            # Jeder Adapter im RICHTIGEN Registry-Dict, genau sein Universum.
            self.assertIn(1, om._enttec_outputs)
            self.assertIn(2, om._artnet_outputs)
            self.assertIn(3, om._sacn_outputs)
            # Keine Kreuz-Einträge (Adapter im falschen Registry / falschem Universum).
            self.assertNotIn(1, om._artnet_outputs)
            self.assertNotIn(1, om._sacn_outputs)
            self.assertNotIn(2, om._enttec_outputs)
            self.assertNotIn(3, om._enttec_outputs)
            self.assertNotIn(3, om._artnet_outputs)
        finally:
            om.stop()

    def test_one_adapter_error_does_not_abort_the_rest(self):
        # Enttec schlägt fehl (Mock wirft) — die folgende ArtNet-Zeile muss trotzdem
        # eingerichtet werden (Loop bricht nicht ab).
        self._om_mod._make_enttec_device = (
            lambda port: (_ for _ in ()).throw(RuntimeError("enttec boom")))
        om = self._apply([
            {"num": 1, "name": "A", "output": "Enttec", "patch": "COM_FAKE"},
            {"num": 2, "name": "B", "output": "ArtNet", "patch": "127.0.0.1"},
        ])
        try:
            self.assertNotIn(1, om._enttec_outputs, "fehlgeschlagener Enttec darf nicht gesetzt sein")
            self.assertIn(2, om._artnet_outputs, "ArtNet nach Enttec-Fehler muss trotzdem gesetzt sein")
            self.assertIn(1, om.universes, "Universum 1 wird trotzdem angelegt")
        finally:
            om.stop()


if __name__ == "__main__":
    unittest.main()

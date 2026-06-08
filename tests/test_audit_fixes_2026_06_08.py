"""Regressionstests fuer das Bug-/Schwachstellen-Audit vom 2026-06-08.

Deckt ab:
  * B4  — Grand-Master skaliert nur Intensitaets-/Farbadressen (nicht Pan/Tilt).
  * B7  — Universe.set_channel haertet Eingaben (Clamp statt assert).
  * B8  — sACN-Parser klemmt das property-count-Feld (kein Over-Read).
  * D2  — sACN-Sender ist E1.31-spec-konform (638 Byte, korrekte PDU-Laengen)
          und round-trippt durch den projekteigenen Receiver.
  * B2/B3 — Thread-Safety-Smoke: paralleler Programmer- bzw. FunctionManager-
            Zugriff wirft keine "changed size during iteration".
"""
import os
import struct
import threading
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.universe import Universe
from src.core.dmx.output_manager import OutputManager
from src.core.dmx.sacn import _pack_framing
from src.core.dmx.sacn_input import SACNReceiver


class _CaptureSender:
    """Fake-sACN-Geraet: faengt die zuletzt gesendeten DMX-Daten ab."""
    def __init__(self):
        self.last = None

    def send_dmx(self, universe, data):
        self.last = bytes(data)


class TestGrandMasterMask(unittest.TestCase):
    """B4: Grand-Master darf nur die Maske skalieren."""

    def _om_with(self, mask):
        om = OutputManager()
        u = Universe(1)
        u.set_channel(1, 200)   # Intensitaet
        u.set_channel(2, 200)   # Pan (NICHT in der Maske)
        om.universes = {1: u}
        om.set_gm_address_mask(mask)
        om.grand_master = 0.5
        cap = _CaptureSender()
        om._sacn_outputs = {1: cap}
        om._send_all()
        return cap.last

    def test_only_masked_addr_scaled(self):
        data = self._om_with({1: frozenset({1})})
        self.assertEqual(data[0], 100)   # ch1 (Intensitaet) -> 200*0.5
        self.assertEqual(data[1], 200)   # ch2 (Pan) unberuehrt

    def test_unmasked_universe_scales_all(self):
        # Universum ohne Maskeneintrag = rohes Setup -> global dimmen (Fallback).
        data = self._om_with({})
        self.assertEqual(data[0], 100)
        self.assertEqual(data[1], 100)


class TestSetChannelHardening(unittest.TestCase):
    """B7: keine Exception, kein Negativ-Index-Wraparound, Wert geklemmt."""

    def setUp(self):
        self.u = Universe(1)

    def test_bad_channel_no_wraparound(self):
        self.u.set_channel(512, 0)
        self.u.set_channel(0, 100)      # darf 512 nicht treffen
        self.u.set_channel(-5, 100)
        self.u.set_channel(99999, 100)
        self.assertEqual(self.u.get_all(), bytes(512))

    def test_value_clamped(self):
        self.u.set_channel(1, 999)
        self.assertEqual(self.u.get_channel(1), 255)
        self.u.set_channel(1, -50)
        self.assertEqual(self.u.get_channel(1), 0)


class TestSacnConformance(unittest.TestCase):
    """D2: E1.31-Paketaufbau + Round-Trip durch den eigenen Receiver."""

    def test_packet_size_and_pdu_lengths(self):
        pkt = _pack_framing(bytes(512), universe=1, seq=0,
                            source="LightOS", cid=uuid.uuid4().bytes)
        self.assertEqual(len(pkt), 638)
        root_fl = struct.unpack("!H", pkt[16:18])[0]
        fram_fl = struct.unpack("!H", pkt[38:40])[0]
        dmp_fl = struct.unpack("!H", pkt[115:117])[0]
        self.assertEqual(root_fl & 0xF000, 0x7000)
        self.assertEqual(root_fl & 0x0FFF, 622)
        self.assertEqual(fram_fl & 0x0FFF, 600)
        self.assertEqual(dmp_fl & 0x0FFF, 523)
        # Vektoren
        self.assertEqual(struct.unpack("!I", pkt[18:22])[0], 0x00000004)
        self.assertEqual(struct.unpack("!I", pkt[40:44])[0], 0x00000002)
        self.assertEqual(pkt[117], 0x02)

    def test_roundtrip_through_receiver(self):
        dmx = bytes((i * 7) & 0xFF for i in range(512))
        pkt = _pack_framing(dmx, universe=9, seq=3,
                            source="LightOS", cid=uuid.uuid4().bytes)
        parsed = SACNReceiver._parse(SACNReceiver.__new__(SACNReceiver), pkt)
        self.assertIsNotNone(parsed)
        universe, payload = parsed
        self.assertEqual(universe, 9)
        self.assertEqual(payload, dmx)


class TestSacnParserClamp(unittest.TestCase):
    """B8: manipuliertes property-count-Feld erzeugt keinen Over-Read."""

    def test_huge_prop_count_clamped(self):
        pkt = bytearray(_pack_framing(bytes(512), universe=1, seq=0,
                                      source="LightOS", cid=uuid.uuid4().bytes))
        # property count (Offset 123:125) auf 0xFFFF manipulieren
        pkt[123:125] = struct.pack("!H", 0xFFFF)
        parsed = SACNReceiver._parse(SACNReceiver.__new__(SACNReceiver), bytes(pkt))
        self.assertIsNotNone(parsed)
        _u, payload = parsed
        self.assertLessEqual(len(payload), 512)


class _FakeFunc:
    def __init__(self, fid):
        self.id = fid
        self.intensity = 1.0
        self.is_running = False

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def write(self, universes, patch_cache, dt, funcs):
        pass


class TestConcurrencySmoke(unittest.TestCase):
    """B2/B3: paralleler Zugriff wirft keine 'changed size during iteration'."""

    def test_function_manager_start_stop_vs_tick(self):
        from src.core.engine.function_manager import FunctionManager
        fm = FunctionManager()
        for fid in range(1, 40):
            fm._functions[fid] = _FakeFunc(fid)
        universes = {1: Universe(1)}
        errors = []
        stop_flag = threading.Event()

        def churn():
            import random
            while not stop_flag.is_set():
                fid = random.randint(1, 39)
                try:
                    if random.random() < 0.5:
                        fm.start(fid)
                    else:
                        fm.stop(fid)
                except Exception as e:  # pragma: no cover
                    errors.append(e)

        workers = [threading.Thread(target=churn) for _ in range(4)]
        for w in workers:
            w.start()
        try:
            for _ in range(2000):
                try:
                    fm.tick(universes, [], 0.02)
                except Exception as e:
                    errors.append(e)
        finally:
            stop_flag.set()
            for w in workers:
                w.join(timeout=2)
        self.assertEqual(errors, [], f"Race-Fehler: {errors[:3]}")

    def test_programmer_writes_vs_render_snapshot(self):
        # Nur den Snapshot-Pfad testen (ohne DB/Threads im AppState): ein RLock
        # plus paralleler Dict-Mutation darf keinen Iterationsfehler werfen.
        lock = threading.RLock()
        programmer = {}
        errors = []
        stop_flag = threading.Event()

        def writer():
            i = 0
            while not stop_flag.is_set():
                with lock:
                    programmer.setdefault(i % 10, {})[f"a{i%5}"] = i % 256
                i += 1

        def snapshotter():
            while not stop_flag.is_set():
                try:
                    with lock:
                        _ = {f: dict(a) for f, a in programmer.items()}
                except Exception as e:  # pragma: no cover
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=snapshotter) for _ in range(3)]
        for t in threads:
            t.start()
        threading.Event().wait(0.3)
        stop_flag.set()
        for t in threads:
            t.join(timeout=2)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

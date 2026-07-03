"""LAS-06: IDN-Stream-Wire-Format (Golden-Bytes gegen ILDA-Spec), IDNConnection
gegen Fake-UDP-Server, und LaserOutputManager-Protokoll-Weiche (Ether Dream vs.
IDN nebeneinander) — alles ohne Hardware.
"""
import os
import socket
import struct
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.laser import idn
from src.core.laser.frame import LaserFrame, LaserPoint
from src.core.laser.laser_output import LaserOutputManager


# ---------------------------------------------------------------------------
# Wire-Format
# ---------------------------------------------------------------------------

class EncodeSamplesTest(unittest.TestCase):
    def test_sample_layout_7_bytes_big_endian(self):
        raw = idn.encode_samples(
            LaserFrame([LaserPoint(1.0, -1.0, 1.0, 0.0, 0.5)]))
        self.assertEqual(len(raw), 7)
        x, y, r, g, b = struct.unpack(">hhBBB", raw)
        self.assertEqual(x, 32767)
        self.assertEqual(y, -32767)
        self.assertEqual((r, g), (255, 0))
        self.assertEqual(b, 128)

    def test_blanked_sample_zero_color_keeps_position(self):
        raw = idn.encode_samples(
            LaserFrame([LaserPoint(0.5, -0.5, 1.0, 1.0, 1.0, blanked=True)]))
        x, y, r, g, b = struct.unpack(">hhBBB", raw)
        self.assertEqual((r, g, b), (0, 0, 0))
        self.assertGreater(x, 0)   # Position bleibt (Galvo bewegt sich)
        self.assertLess(y, 0)


class StreamPacketTest(unittest.TestCase):
    def _parse(self, packet):
        """Zerlegt ein IDN-RT-Datagramm in seine Header (für die Assertions)."""
        cmd, flags, seq = struct.unpack(">BBH", packet[:4])
        total_size, cnl, chunk_type, ts = struct.unpack(">HBBI", packet[4:12])
        scwc, cfl, svc_id, svc_mode = struct.unpack(">BBBB", packet[12:16])
        dictionary = struct.unpack(">HHHHHHHH", packet[16:32])
        (flags_duration,) = struct.unpack(">I", packet[32:36])
        samples = packet[36:]
        return dict(cmd=cmd, flags=flags, seq=seq, total_size=total_size,
                    cnl=cnl, chunk_type=chunk_type, ts=ts, scwc=scwc, cfl=cfl,
                    svc_id=svc_id, svc_mode=svc_mode, dictionary=dictionary,
                    flags_duration=flags_duration, samples=samples)

    def test_header_layout_matches_spec(self):
        frame = LaserFrame([LaserPoint(0, 0)] * 10, pps=20000)
        pkt = idn.build_stream_packet(frame, sequence=7, timestamp_us=123456)
        p = self._parse(pkt)
        # IDN-Hello-Header
        self.assertEqual(p["cmd"], idn.CMD_RT_CHANNEL_MESSAGE)   # 0x40
        self.assertEqual(p["flags"], 0x00)
        self.assertEqual(p["seq"], 7)
        # Channel-Message-Header: CNL = Bit7 (channelmsg) | Bit6 (config) | id0
        self.assertEqual(p["cnl"], 0xC0)
        self.assertEqual(p["chunk_type"], idn.CHUNK_FRAME_SAMPLES)  # 0x02
        self.assertEqual(p["ts"], 123456)
        # totalSize = alles ab dem totalSize-Feld (ohne 4-Byte-Hello-Header)
        self.assertEqual(p["total_size"], len(pkt) - 4)
        # Channel-Config: Discrete Graphic, Routing an
        self.assertEqual(p["scwc"], 4)
        self.assertEqual(p["cfl"], 0x01)          # Routing-Bit gesetzt
        self.assertEqual(p["svc_id"], 0x00)
        self.assertEqual(p["svc_mode"], idn.SERVICE_MODE_GRAPHIC_DISCRETE)

    def test_dictionary_is_standard_xyrgb(self):
        pkt = idn.build_stream_packet(
            LaserFrame([LaserPoint(0, 0)] * 4), sequence=1, timestamp_us=0)
        p = self._parse(pkt)
        self.assertEqual(
            p["dictionary"],
            (0x4200, 0x4010, 0x4210, 0x4010, 0x527E, 0x5214, 0x51CC, 0x0000))

    def test_duration_encodes_frame_time(self):
        # 200 Punkte bei 20000 pps = 10 ms = 10000 µs.
        frame = LaserFrame([LaserPoint(0, 0)] * 200, pps=20000)
        p = self._parse(idn.build_stream_packet(frame, 1, 0))
        flags = p["flags_duration"] >> 24
        duration = p["flags_duration"] & 0xFFFFFF
        self.assertEqual(flags, 0)
        self.assertEqual(duration, 10000)

    def test_sample_count_matches(self):
        frame = LaserFrame([LaserPoint(0, 0)] * 12, pps=20000)
        p = self._parse(idn.build_stream_packet(frame, 1, 0))
        self.assertEqual(len(p["samples"]), 12 * 7)


class DownsampleTest(unittest.TestCase):
    def test_downsample_preserves_endpoint_and_count(self):
        pts = [LaserPoint(i / 1000.0, 0) for i in range(1000)]
        out = idn._downsample(pts, 190)
        self.assertEqual(len(out), 190)
        self.assertIs(out[-1], pts[-1])           # Endpunkt erhalten
        self.assertIs(out[0], pts[0])             # Startpunkt erhalten

    def test_downsample_noop_when_small(self):
        pts = [LaserPoint(0, 0)] * 10
        self.assertIs(idn._downsample(pts, 190), pts)

    def test_stream_frame_downsamples_over_mtu(self):
        """stream_frame darf niemals ein Paket über der MTU bauen."""
        conn = idn.IDNConnection("127.0.0.1")
        sent = {}

        def fake_send(payload):
            sent["len"] = len(payload)
        conn._send = fake_send   # type: ignore[method-assign]
        conn.stream_frame(LaserFrame([LaserPoint(0, 0)] * 5000, pps=30000))
        self.assertLessEqual(sent["len"], 1400)


# ---------------------------------------------------------------------------
# IDNConnection gegen Fake-UDP-Empfänger
# ---------------------------------------------------------------------------

class _FakeUdpReceiver:
    """Bindet einen UDP-Socket auf 127.0.0.1:0 und sammelt Datagramme."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(1.0)
        self.port = self.sock.getsockname()[1]
        self.packets: list[bytes] = []
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while not self._stop:
            try:
                data, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            self.packets.append(data)

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass
        self._t.join(timeout=1.0)


class IDNConnectionTest(unittest.TestCase):
    def setUp(self):
        self.rx = _FakeUdpReceiver()

    def tearDown(self):
        self.rx.close()

    def _wait(self, n, timeout=1.0):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.rx.packets) >= n:
                return
            time.sleep(0.01)

    def test_stream_frame_sends_udp_with_incrementing_seq(self):
        conn = idn.IDNConnection("127.0.0.1", port=self.rx.port)
        frame = LaserFrame([LaserPoint(0, 0)] * 8, pps=20000)
        conn.stream_frame(frame)
        conn.stream_frame(frame)
        self._wait(2)
        conn.close()
        self.assertGreaterEqual(len(self.rx.packets), 2)
        s1 = struct.unpack(">H", self.rx.packets[0][2:4])[0]
        s2 = struct.unpack(">H", self.rx.packets[1][2:4])[0]
        self.assertEqual(s2, s1 + 1)
        self.assertEqual(self.rx.packets[0][0], idn.CMD_RT_CHANNEL_MESSAGE)

    def test_stop_sends_graceful_close(self):
        conn = idn.IDNConnection("127.0.0.1", port=self.rx.port)
        conn.stream_frame(LaserFrame([LaserPoint(0, 0)] * 8))
        conn.stop()
        self._wait(2)
        conn.close()
        self.assertEqual(self.rx.packets[-1][0], idn.CMD_RT_CLOSE)

    def test_estop_sends_blank_then_abort(self):
        conn = idn.IDNConnection("127.0.0.1", port=self.rx.port)
        conn.estop()
        self._wait(2)
        conn.close()
        # Letztes Paket = Abort; davor ein Stream-Paket (geblankt).
        self.assertEqual(self.rx.packets[-1][0], idn.CMD_RT_ABORT)
        self.assertTrue(any(p[0] == idn.CMD_RT_CHANNEL_MESSAGE
                            for p in self.rx.packets))


class ScanResponseTest(unittest.TestCase):
    def test_parse_scan_response_fixed_layout(self):
        # Festes IDNHDR_SCAN_RESPONSE-Layout (DexLogic idn-hello.h):
        # 4B Hello + structSize/proto/status/RESERVED + unitID[16] + hostName[20].
        hello = struct.pack(">BBH", idn.CMD_SCAN_RESPONSE, 0, 0)
        head = bytes([0x2C, 0x01, 0x01, 0x00])       # size, proto, status(RT), reserved
        # unitID[16]: Byte0=Länge(7 = Kategorie + 6 MAC), Byte1=Kategorie(0x01).
        unit = (bytes([0x07, 0x01, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff])
                ).ljust(16, b"\x00")
        hostname = b"Left".ljust(20, b"\x00")
        info = idn.parse_scan_response(hello + head + unit + hostname)
        self.assertTrue(info["offers_rt"])           # Status Bit0
        self.assertEqual(info["hostname"], "Left")   # RESERVED korrekt übersprungen
        self.assertEqual(info["unit_id"], "01:aa:bb:cc:dd:ee:ff")

    def test_parse_scan_response_rejects_short(self):
        with self.assertRaises(idn.IDNError):
            idn.parse_scan_response(struct.pack(">BBH", idn.CMD_SCAN_RESPONSE,
                                                0, 0) + b"\x00\x00\x00")


class GoldenBytesTest(unittest.TestCase):
    """Spec-UNABHÄNGIGE Golden-Bytes: hart einkodiert aus der ILDA-Spec, NICHT
    aus den Modul-Konstanten abgeleitet — fängt eine versehentliche Änderung
    von Tag-Werten/Header-Layout, die ein selbstbezüglicher Test durchließe."""

    def test_full_single_point_packet_bytes(self):
        # Ein Frame, ein sichtbarer roter Mittelpunkt (0,0). seq=1, ts=0.
        frame = LaserFrame([LaserPoint(0.0, 0.0, 1.0, 0.0, 0.0)], pps=100000)
        pkt = idn.build_stream_packet(frame, sequence=1, timestamp_us=0)
        expected = bytes.fromhex(
            "40000001"          # Hello: cmd=0x40, flags=0, seq=0x0001
            "0027"              # totalSize = 39 (8 msg + 20 cfg + 4 chunk + 7 sample)
            "c0"                # CNL: channelmsg(0x80)|config(0x40)|ch0
            "02"                # chunkType = frame samples
            "00000000"          # timestamp = 0
            "04"                # SCWC = 4 config words
            "01"                # CFL = routing
            "00"                # service id = default
            "02"                # service mode = discrete graphic
            "4200401042104010"  # dict: X, prec, Y, prec
            "527e521451cc0000"  # dict: R, G, B, void
            "0000000a"          # sample-chunk: flags=0, duration=10µs
            "00000000ff0000"    # sample: x=0, y=0, r=255, g=0, b=0
        )
        self.assertEqual(pkt.hex(), expected.hex())


# ---------------------------------------------------------------------------
# LaserOutputManager — Protokoll-Weiche
# ---------------------------------------------------------------------------

class _Fx:
    def __init__(self, fid, protocol, net_host="10.0.0.5"):
        self.fid = fid
        self.protocol = protocol
        self.net_host = net_host


class _OM:
    def __init__(self):
        self._blackout = False


class _State:
    def __init__(self, fixtures):
        self._fixtures = fixtures
        self.programmer = {}
        self.output_manager = _OM()

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get(attr)


class _FakeConn:
    def __init__(self, host, port=0, **kw):
        self.host = host
        self.frames = []

    def stream_frame(self, frame):
        self.frames.append(frame)
        return True

    def estop(self):
        pass

    def clear_estop(self):
        pass

    def stop(self):
        pass

    def close(self):
        pass


class ManagerProtocolRoutingTest(unittest.TestCase):
    def _manager(self, fixtures):
        state = _State(fixtures)
        m = LaserOutputManager(state)
        made = {}

        def ed_factory(host, **kw):
            c = _FakeConn(host); c.kind = "ed"; made[host] = c; return c

        def idn_factory(host, **kw):
            c = _FakeConn(host); c.kind = "idn"; made[host] = c; return c

        m.connection_factory = ed_factory
        m.idn_connection_factory = idn_factory
        return m, state, made

    def test_picks_backend_per_protocol(self):
        m, state, made = self._manager([
            _Fx(1, "etherdream", "10.0.0.1"),
            _Fx(2, "idn", "10.0.0.2"),
            _Fx(3, "dmx", "10.0.0.3"),        # kein Netzwerk-Laser
        ])
        state.programmer = {1: {"shutter": 255}, 2: {"shutter": 255}}
        m._tick()
        self.assertEqual(made["10.0.0.1"].kind, "ed")
        self.assertEqual(made["10.0.0.2"].kind, "idn")
        self.assertNotIn("10.0.0.3", made)       # DMX ignoriert
        self.assertEqual(len(made["10.0.0.2"].frames), 1)

    def test_protocol_switch_rebuilds_connection(self):
        fx = _Fx(1, "etherdream", "10.0.0.1")
        m, state, made = self._manager([fx])
        state.programmer = {1: {"shutter": 255}}
        m._tick()
        self.assertEqual(m._connections[1].kind, "ed")
        # Nutzer stellt im Patch von Ether Dream auf IDN um (gleiche IP).
        fx.protocol = "idn"
        m._tick()
        self.assertEqual(m._connections[1].kind, "idn")

    def test_idn_error_triggers_backoff(self):
        m, state, made = self._manager([_Fx(1, "idn", "10.0.0.2")])
        state.programmer = {1: {"shutter": 255}}
        m._tick()
        conn = m._connections[1]

        def boom(frame):
            raise idn.IDNError("weg")
        conn.stream_frame = boom
        m._tick()
        self.assertNotIn(1, m._connections)      # Verbindung entfernt
        self.assertIn(1, m._retry_at)            # Backoff gesetzt


if __name__ == "__main__":
    unittest.main()

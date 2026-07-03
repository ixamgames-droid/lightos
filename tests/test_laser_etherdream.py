"""LAS-05: Frame-Clamping, Ether-Dream-Protokoll (gegen Fake-DAC) und
LaserOutputManager-Verhalten (Blackout/E-Stop/Backoff) — alles ohne Hardware.
"""
import os
import socket
import struct
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.laser.frame import (LaserFrame, LaserLimits, LaserPoint,
                                  clamp_frame)
from src.core.laser import etherdream as ed
from src.core.laser.laser_output import LaserOutputManager, build_test_frame


# ---------------------------------------------------------------------------
# frame.py — Safety-Clamping
# ---------------------------------------------------------------------------

class ClampFrameTest(unittest.TestCase):
    def _frame(self, n=32, **kw):
        pts = [LaserPoint(x=2.0, y=-2.0, r=2.0, g=0.5, b=-1.0)] * n
        return LaserFrame(points=pts, **kw)

    def test_clamps_coords_colors_and_pps(self):
        limits = LaserLimits(max_size=0.5, max_pps=25000, min_points=4)
        out = clamp_frame(self._frame(pps=99999), limits)
        self.assertEqual(out.pps, 25000)
        p = out.points[0]
        self.assertEqual((p.x, p.y), (0.5, -0.5))
        self.assertEqual((p.r, p.g, p.b), (1.0, 0.5, 0.0))
        self.assertFalse(p.blanked)

    def test_min_pps_floor(self):
        out = clamp_frame(self._frame(pps=10), LaserLimits(min_pps=1000))
        self.assertEqual(out.pps, 1000)

    def test_too_few_points_blanks_frame(self):
        out = clamp_frame(self._frame(n=3), LaserLimits(min_points=16))
        self.assertTrue(all(p.blanked for p in out.points))

    def test_truncates_to_max_points(self):
        out = clamp_frame(self._frame(n=100), LaserLimits(max_points=10))
        self.assertEqual(len(out.points), 10)

    def test_intensity_scales_colors(self):
        limits = LaserLimits(intensity=0.5, min_points=1)
        out = clamp_frame(LaserFrame([LaserPoint(0, 0, 1, 1, 1)]), limits)
        self.assertAlmostEqual(out.points[0].r, 0.5)

    def test_blank_copy_keeps_geometry(self):
        f = LaserFrame([LaserPoint(0.25, -0.25)], pps=12000)
        b = f.blank_copy()
        self.assertTrue(b.points[0].blanked)
        self.assertEqual((b.points[0].x, b.points[0].y), (0.25, -0.25))
        self.assertFalse(f.points[0].blanked)   # Original unberührt


# ---------------------------------------------------------------------------
# etherdream.py — Wire-Format + Verbindung gegen Fake-DAC
# ---------------------------------------------------------------------------

class EncodeParseTest(unittest.TestCase):
    def test_encode_points_wire_format(self):
        frame = LaserFrame([LaserPoint(1.0, -1.0, 1.0, 0.0, 0.5)])
        raw = ed.encode_points(frame)
        self.assertEqual(len(raw), 18)
        ctrl, x, y, r, g, b, i, u1, u2 = struct.unpack("<HhhHHHHHH", raw)
        self.assertEqual((ctrl, u1, u2), (0, 0, 0))
        self.assertEqual(x, 32767)
        self.assertEqual(y, -32767)
        self.assertEqual((r, g), (65535, 0))
        self.assertEqual(b, round(0.5 * 65535))
        self.assertEqual(i, 65535)   # max(r,g,b)

    def test_blanked_point_has_zero_color(self):
        raw = ed.encode_points(
            LaserFrame([LaserPoint(0, 0, 1, 1, 1, blanked=True)]))
        _c, _x, _y, r, g, b, i, _u1, _u2 = struct.unpack("<HhhHHHHHH", raw)
        self.assertEqual((r, g, b, i), (0, 0, 0, 0))

    def test_parse_broadcast_roundtrip(self):
        status = ed._STATUS.pack(0, 0, ed.PLAYBACK_IDLE, 0, 0, 0, 0, 0,
                                 30000, 0)
        head = ed._BROADCAST_HEAD.pack(b"\x01\x02\x03\x04\x05\x06",
                                       2, 3, 1799, 100000)
        info = ed.parse_broadcast(head + status)
        self.assertEqual(info["mac"], "01:02:03:04:05:06")
        self.assertEqual(info["buffer_capacity"], 1799)
        self.assertEqual(info["max_point_rate"], 100000)
        self.assertEqual(info["status"].point_rate, 30000)


def _status_bytes(playback=ed.PLAYBACK_IDLE, light_engine=0, fullness=0):
    return ed._STATUS.pack(0, light_engine, playback, 0, 0, 0, 0,
                           fullness, 0, 0)


class _FakeDac(threading.Thread):
    """Minimaler Ether-Dream-Simulator: 1 TCP-Client, ACKt alle Befehle,
    führt playback/light_engine-State nach, protokolliert Befehle."""

    def __init__(self, nak_full_data=False):
        super().__init__(daemon=True)
        self.commands: list[int] = []
        self.playback = ed.PLAYBACK_IDLE
        self.light_engine = 0
        self.points_received = 0
        self._nak_full = nak_full_data
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]

    def _reply(self, conn, resp, cmd):
        conn.sendall(bytes([resp, cmd])
                     + _status_bytes(self.playback, self.light_engine))

    def _recv_exact(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def run(self):
        conn, _ = self._srv.accept()
        conn.settimeout(2.0)
        try:
            self._reply(conn, ed.ACK, ord("?"))   # Ping-Antwort beim Connect
            while True:
                cmd = self._recv_exact(conn, 1)[0]
                self.commands.append(cmd)
                if cmd == ord("p"):
                    self.playback = ed.PLAYBACK_PREPARED
                    self._reply(conn, ed.ACK, cmd)
                elif cmd == ord("b"):
                    self._recv_exact(conn, 6)
                    self.playback = ed.PLAYBACK_PLAYING
                    self._reply(conn, ed.ACK, cmd)
                elif cmd == ord("d"):
                    n = struct.unpack("<H", self._recv_exact(conn, 2))[0]
                    self._recv_exact(conn, 18 * n)
                    if self._nak_full:
                        self._reply(conn, ed.NAK_FULL, cmd)
                    else:
                        self.points_received += n
                        self._reply(conn, ed.ACK, cmd)
                elif cmd == 0x00:
                    self.light_engine = ed.LIGHT_ENGINE_ESTOP
                    self.playback = ed.PLAYBACK_IDLE
                    self._reply(conn, ed.ACK, cmd)
                elif cmd == ord("c"):
                    self.light_engine = 0
                    self._reply(conn, ed.ACK, cmd)
                else:               # '?', 's', 'q', ...
                    if cmd == ord("s"):
                        self.playback = ed.PLAYBACK_PREPARED
                    self._reply(conn, ed.ACK, cmd)
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            self._srv.close()


class EtherDreamConnectionTest(unittest.TestCase):
    def _connect(self, **kw) -> tuple[_FakeDac, ed.EtherDreamConnection]:
        dac = _FakeDac(**kw)
        dac.start()
        conn = ed.EtherDreamConnection("127.0.0.1", port=dac.port,
                                       timeout=2.0)
        conn.connect()
        return dac, conn

    def test_stream_frame_prepares_writes_and_begins(self):
        dac, conn = self._connect()
        frame = LaserFrame([LaserPoint(0, 0)] * 20, pps=20000)
        self.assertTrue(conn.stream_frame(frame))
        conn.close()
        dac.join(timeout=2.0)
        self.assertEqual(dac.commands, [ord("p"), ord("d"), ord("b")])
        self.assertEqual(dac.points_received, 20)

    def test_second_frame_skips_prepare_and_begin(self):
        dac, conn = self._connect()
        frame = LaserFrame([LaserPoint(0, 0)] * 8, pps=20000)
        conn.stream_frame(frame)
        conn.stream_frame(frame)
        conn.close()
        dac.join(timeout=2.0)
        self.assertEqual(dac.commands,
                         [ord("p"), ord("d"), ord("b"), ord("d")])

    def test_buffer_full_returns_false(self):
        dac, conn = self._connect(nak_full_data=True)
        frame = LaserFrame([LaserPoint(0, 0)] * 8)
        conn.prepare()
        self.assertFalse(conn.write_points(frame))
        conn.close()
        dac.join(timeout=2.0)

    def test_estop_and_clear(self):
        dac, conn = self._connect()
        status = conn.estop()
        self.assertTrue(status.estopped)
        # Verriegelt: stream_frame sendet nichts mehr.
        sent_before = list(dac.commands)
        self.assertFalse(conn.stream_frame(LaserFrame([LaserPoint(0, 0)] * 8)))
        self.assertEqual(dac.commands, sent_before)
        status = conn.clear_estop()
        self.assertFalse(status.estopped)
        conn.close()
        dac.join(timeout=2.0)


# ---------------------------------------------------------------------------
# laser_output.py — Framequelle + Manager-Verhalten (ohne Sockets)
# ---------------------------------------------------------------------------

class _Fx:
    def __init__(self, fid, protocol="etherdream", net_host="10.0.0.9"):
        self.fid = fid
        self.protocol = protocol
        self.net_host = net_host


class _OutputManagerStub:
    def __init__(self):
        self._blackout = False


class _State:
    def __init__(self, fixtures):
        self._fixtures = fixtures
        self.programmer: dict[int, dict[str, int]] = {}
        self.output_manager = _OutputManagerStub()

    def get_patched_fixtures(self):
        return list(self._fixtures)

    def get_programmer_value(self, fid, attr, head=0):
        return self.programmer.get(fid, {}).get(attr)


class _FakeConn:
    def __init__(self, host, port=0, timeout=0.0):
        self.host = host
        self.frames: list[LaserFrame] = []
        self.estops = 0
        self.clears = 0
        self.fail = False

    def stream_frame(self, frame):
        if self.fail:
            raise ed.EtherDreamError("kaputt")
        self.frames.append(frame)
        return True

    def estop(self):
        self.estops += 1

    def clear_estop(self):
        self.clears += 1

    def stop(self):
        pass

    def close(self):
        pass


def _manager(fixtures):
    state = _State(fixtures)
    m = LaserOutputManager(state)
    m.connection_factory = _FakeConn
    return m, state


class BuildTestFrameTest(unittest.TestCase):
    def test_shutter_gate_defaults_dark(self):
        state = _State([_Fx(1)])
        frame = build_test_frame(state, _Fx(1), LaserLimits(), fps=30)
        self.assertTrue(all(p.blanked for p in frame.points))

    def test_programmer_drives_pattern(self):
        state = _State([_Fx(1)])
        state.programmer[1] = {"shutter": 255, "laser_x": 255, "zoom": 255,
                               "color_r": 255, "color_g": 0, "color_b": 0,
                               "laser_draw": 128}
        frame = build_test_frame(state, _Fx(1), LaserLimits(), fps=30)
        lit = [p for p in frame.points if not p.blanked]
        self.assertTrue(lit)
        # Halber Zeichnen-Anteil -> ungefähr halber Kreis sichtbar.
        self.assertAlmostEqual(len(lit) / len(frame.points), 0.5, delta=0.05)
        self.assertEqual((lit[0].r, lit[0].g, lit[0].b), (1.0, 0.0, 0.0))
        # Punktebudget = pps/fps (Puffer-Gleichgewicht).
        self.assertEqual(len(frame.points), frame.pps // 30)

    def test_center_offset(self):
        state = _State([_Fx(1)])
        state.programmer[1] = {"shutter": 255, "laser_x": 255,
                               "laser_y": 128, "zoom": 0}
        frame = build_test_frame(state, _Fx(1), LaserLimits(), fps=30)
        self.assertAlmostEqual(frame.points[0].x, 1.0, places=2)
        self.assertAlmostEqual(frame.points[0].y, 0.0, places=2)


class LaserOutputManagerTest(unittest.TestCase):
    def test_tick_streams_clamped_frame_per_network_fixture(self):
        m, state = _manager([_Fx(1), _Fx(2, protocol="dmx"),
                             _Fx(3, net_host="")])
        state.programmer[1] = {"shutter": 255}
        m._tick()
        conns = list(m._connections.values())
        self.assertEqual(len(conns), 1)          # nur fid 1 ist Netzwerk+Host
        self.assertEqual(len(conns[0].frames), 1)
        self.assertTrue(any(not p.blanked for p in conns[0].frames[0].points))

    def test_blackout_blanks_all_frames(self):
        m, state = _manager([_Fx(1)])
        state.programmer[1] = {"shutter": 255}
        state.output_manager._blackout = True
        m._tick()
        frame = list(m._connections.values())[0].frames[0]
        self.assertTrue(all(p.blanked for p in frame.points))

    def test_estop_locks_and_stops_sending(self):
        m, state = _manager([_Fx(1)])
        state.programmer[1] = {"shutter": 255}
        m._tick()
        conn = list(m._connections.values())[0]
        m.estop_all()
        self.assertEqual(conn.estops, 1)
        m._tick()
        self.assertEqual(len(conn.frames), 1)    # nichts Neues gesendet
        m.clear_estop_all()
        self.assertEqual(conn.clears, 1)
        m._tick()
        self.assertEqual(len(conn.frames), 2)

    def test_connection_error_schedules_backoff(self):
        m, state = _manager([_Fx(1)])
        state.programmer[1] = {"shutter": 255}
        m._tick()
        conn = list(m._connections.values())[0]
        conn.fail = True
        m._tick()                                # Fehler -> Verbindung raus
        self.assertNotIn(1, m._connections)
        m._tick()                                # Backoff aktiv -> kein Reconnect
        self.assertNotIn(1, m._connections)
        m._retry_at[1] = 0.0                     # Backoff abgelaufen
        m._tick()
        self.assertIn(1, m._connections)


class NetHostFieldTest(unittest.TestCase):
    def test_migration_adds_net_host(self):
        from sqlalchemy import create_engine, text
        from src.core.database.models import migrate_show_db
        eng = create_engine("sqlite:///:memory:")
        with eng.begin() as conn:
            conn.execute(text(
                "CREATE TABLE patched_fixtures ("
                "id INTEGER PRIMARY KEY, fid INTEGER)"))
            conn.execute(text(
                "CREATE TABLE fixture_groups (id INTEGER PRIMARY KEY)"))
        migrate_show_db(eng)
        with eng.begin() as conn:
            cols = {r[1] for r in conn.execute(
                text("PRAGMA table_info(patched_fixtures)"))}
        self.assertIn("net_host", cols)

    def test_show_file_roundtrip(self):
        from src.core.show.show_file import (_fixture_to_dict,
                                             _patched_fixture_from_data)
        d = _fixture_to_dict({"fid": 1, "protocol": "etherdream",
                              "net_host": "192.168.1.50"})
        self.assertEqual(d["net_host"], "192.168.1.50")
        pf = _patched_fixture_from_data(d, fallback_fid=1)
        self.assertEqual(pf.net_host, "192.168.1.50")
        legacy = _patched_fixture_from_data({"fid": 2}, fallback_fid=2)
        self.assertEqual(legacy.net_host, "")


if __name__ == "__main__":
    unittest.main()

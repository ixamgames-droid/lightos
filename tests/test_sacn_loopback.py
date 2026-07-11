"""OUT-01: echter Wire-Loopback fuer den sACN-(E1.31-)Output.

Beweist OHNE Hardware, dass `SACNSender` ein spec-konformes E1.31-Paket
TATSAECHLICH ueber einen UDP-Socket auf die Leitung legt (Unicast
127.0.0.1:5568) und ein Empfaenger es korrekt zurueckliest. Ergaenzt den
vorhandenen In-Memory-Test (test_audit_fixes_2026_06_08::TestSacnConformance,
nur `_pack_framing` -> Parser) um den realen Socket-Pfad.

Faellt sauber auf SKIP zurueck, falls die Umgebung keinen UDP-Loopback erlaubt
(Port belegt / Sandbox) — dann bleibt die In-Memory-Konformitaet die Absicherung.
"""
import os
import socket
import struct
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx.sacn import SACNSender, SACN_PORT
from src.core.dmx.sacn_input import SACNReceiver


class SacnLoopbackTest(unittest.TestCase):
    def _open_receiver(self, timeout: float = 1.0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", SACN_PORT))     # OSError -> Caller skippt
        sock.settimeout(timeout)
        return sock

    def test_unicast_loopback_roundtrip(self):
        try:
            rx = self._open_receiver()
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback auf 127.0.0.1:{SACN_PORT} ({e})")

        sender = SACNSender(target_ip="127.0.0.1", source_name="LoopTest")
        try:
            dmx = bytes((i * 3 + 1) & 0xFF for i in range(512))
            pkt = None
            for _ in range(5):                  # UDP darf droppen -> ein paar Versuche
                sender.send_dmx(7, dmx)
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
            sender.close()
            rx.close()

    def test_sequence_number_increments_on_wire(self):
        """Aufeinanderfolgende Frames tragen hochzaehlende Sequenznummern (Offset
        111) — wichtig, damit Empfaenger Reihenfolge/Verluste erkennen."""
        try:
            rx = self._open_receiver()
        except OSError as e:
            self.skipTest(f"kein UDP-Loopback auf 127.0.0.1:{SACN_PORT} ({e})")
        sender = SACNSender(target_ip="127.0.0.1", source_name="LoopTest")
        try:
            seqs = []
            for _ in range(3):
                sender.send_dmx(1, bytes(512))
                try:
                    pkt, _addr = rx.recvfrom(2048)
                except socket.timeout:
                    # QA-02: Bind ok -> ausbleibendes Paket ist eine Sender-
                    # Regression, kein Umgebungsproblem -> failen statt skippen.
                    self.fail("sACN-Paket trotz erfolgreichem Bind nicht empfangen "
                              "(Sender-Regression)")
                seqs.append(pkt[111])
            # Streng monoton (mod 256) — hier einfach +1 pro Frame.
            self.assertEqual(seqs[1], (seqs[0] + 1) & 0xFF)
            self.assertEqual(seqs[2], (seqs[1] + 1) & 0xFF)
        finally:
            sender.close()
            rx.close()


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


class SacnStreamTerminationTest(unittest.TestCase):
    """OUT-06: close() sendet je bespieltem Universum 3 Pakete mit gesetztem
    Stream_Terminated-Options-Bit, damit Empfaenger die Quelle sofort verwerfen."""

    # Options-Byte-Offset im E1.31-Paket: Root-Layer 38 + Framing bis Options
    # (Flags&Len2+Vector4+Source64+Prio1+SyncAddr2+Seq1 = 74) = 112.
    _OPTIONS_OFFSET = 112

    def _sender_with_fake_sock(self):
        s = SACNSender.__new__(SACNSender)
        s._target_ip = None
        s._source_name = "TermTest"
        s._cid = b"\x00" * 16
        s._seq = {1: 5, 7: 200}
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
        s = self._sender_with_fake_sock()
        s._seq = {}
        sock = s._sock
        s.close()                         # nichts gesendet, kein Fehler
        self.assertEqual(sock.sent, [])
        self.assertIsNone(s._sock)


if __name__ == "__main__":
    unittest.main()

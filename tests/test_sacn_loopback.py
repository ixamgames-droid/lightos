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
                self.skipTest("kein Paket empfangen (Loopback evtl. blockiert)")

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
                    self.skipTest("kein Paket empfangen (Loopback evtl. blockiert)")
                seqs.append(pkt[111])
            # Streng monoton (mod 256) — hier einfach +1 pro Frame.
            self.assertEqual(seqs[1], (seqs[0] + 1) & 0xFF)
            self.assertEqual(seqs[2], (seqs[1] + 1) & 0xFF)
        finally:
            sender.close()
            rx.close()


if __name__ == "__main__":
    unittest.main()

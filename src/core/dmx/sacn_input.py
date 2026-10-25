"""sACN / E1.31 Input - empfaengt DMX-Pakete via Multicast oder Unicast.

Verwendung:
    rx = get_sacn_receiver()
    rx.subscribe(lambda universe, data: print(universe, len(data)))
    rx.start(universes=[1, 2, 3])
"""
from __future__ import annotations
import socket
import struct
import threading
import time
from typing import Callable

SACN_PORT = 5568
SACN_ACN_PACKET_ID = b"ASC-E1.17\x00\x00\x00"
SACN_VECTOR_DATA = 0x00000002
#: Framing-Options (E1.31 §6.2.6): Preview-Daten / Stream beendet
SACN_OPT_PREVIEW = 0x80
SACN_OPT_TERMINATED = 0x40


def _multicast_addr(universe: int) -> str:
    """E1.31 multicast: 239.255.{high}.{low} where universe = high*256+low."""
    high = (universe >> 8) & 0xFF
    low = universe & 0xFF
    return f"239.255.{high}.{low}"


class SACNReceiver:
    """sACN Empfaenger - hoert auf gewuenschten Universen (Multicast)."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._callbacks: list[Callable[[int, bytes], None]] = []
        self._callbacks_absender: list[Callable[..., None]] = []   # NET-15
        self._joined_universes: list[int] = []
        # Merge-Config wie ArtNet
        self._merges: dict[int, tuple[int, str]] = {}
        self._merge_cb_installed = False
        # OUT-79: gewaehlte Empfangsadresse + Empfangs-Lage (Firewall-Hinweis)
        self.wahl: str = ""
        self.host: str | None = None
        self._port: int | None = None
        self._mc_iface: str | None = "0.0.0.0"   # None = kein Multicast-Beitritt
        self._universen_soll: list[int] = []     # auch ohne Beitritt gemerkt
        self._absender_netz = None
        self.gestartet_um: float | None = None
        self.letztes_paket_um: float | None = None
        self.pakete = 0
        self.letzter_fehler: str = ""

    def start(self, universes: list[int] | None = None,
              host: str | None = None, port: int | None = None,
              wahl: str | None = None):
        """Starte Listener auf ``universes`` (Multicast-Join; ``None`` -> [1]).
        Ohne ``host`` gilt die gewaehlte Empfangsadresse (OUT-79); der
        Multicast-Beitritt laeuft dann ueber dieselbe Karte, bei „nur dieser
        Rechner" entfaellt er (sACN kommt dort nur als Unicast an).
        ``host``/``port`` nur fuer Tests (127.0.0.1 + freier Port, NET-15);
        ``port=None`` liest ``SACN_PORT`` erst hier."""
        if self._running:
            return
        if port is None:
            port = SACN_PORT
        if universes is None:
            universes = [1]
        from src.core.dmx import empfangsadresse as ea
        if host is None:
            w = ea.aktuelle() if wahl is None else ea.normiere(wahl)
            host = ea.bind_host(w)
            self._mc_iface = ea.multicast_iface(w)
            self._absender_netz = ea.absender_netz(w)
        else:
            # Ausdrueckliche Adresse (Tests): Beitritt wie bisher ueber die
            # Standardkarte, ausser eine Wahl ist mitgegeben.
            w = ea.normiere(host) if wahl is None else ea.normiere(wahl)
            self._mc_iface = "0.0.0.0" if wahl is None else ea.multicast_iface(w)
            self._absender_netz = None
        self.wahl = w
        self.letzter_fehler = ""
        self._universen_soll = []
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # Not on Windows
            self._sock.bind((host, int(port)))
            self._sock.settimeout(0.5)
            # Multicast Join
            for u in universes:
                self._join_universe(u)
        except Exception as e:
            print(f"[sACN-In] bind error: {e}")
            self.letzter_fehler = f"{host}:{port} — {e}"
            try:
                if self._sock is not None:
                    self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._joined_universes.clear()
            return
        self.host, self._port = host, int(port)
        self.gestartet_um = time.monotonic()
        self.letztes_paket_um = None
        self.pakete = 0
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="sACN-In"
        )
        self._thread.start()
        self._install_merge_handler()
        print(f"[sACN-In] listening on {host}:{port}, universes={universes}")

    def stop(self):
        self._running = False
        if self._sock:
            try:
                # Leave multicast groups (best effort)
                for u in self._joined_universes:
                    try:
                        mreq = (socket.inet_aton(_multicast_addr(u))
                                + socket.inet_aton(self._mc_iface or "0.0.0.0"))
                        self._sock.setsockopt(
                            socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq
                        )
                    except Exception:
                        pass
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._joined_universes.clear()
        if self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None

    def is_running(self) -> bool:
        # NET-06: ein ueber `break` gestorbener RX-Thread gilt als NICHT laufend,
        # damit der UI-Auto-Restart-Guard greift (nicht nur das Flag pruefen).
        t = self._thread
        return self._running and t is not None and t.is_alive()

    def adresse(self) -> tuple[str, int] | None:
        """OUT-79: (Adresse, Port), an die der Socket gerade gebunden ist."""
        sock = self._sock
        if sock is None:
            return None
        try:
            return tuple(sock.getsockname()[:2])
        except OSError:
            return None

    def universen(self) -> list[int]:
        """Universen, auf die der Empfang hoert (auch ohne Multicast-Beitritt)."""
        return list(self._universen_soll)

    def neu_binden(self, wahl: str) -> bool:
        """OUT-79: laufenden Empfang an eine andere Empfangsadresse binden.
        Zuhoerer, Merge-Zuordnung und Universen bleiben. ``False``, wenn er
        nicht lief (dann gilt die Wahl beim naechsten Start)."""
        if not self.is_running():
            return False
        universen = list(self._universen_soll) or [1]
        port = self._port
        self.stop()
        self.start(universes=universen, port=port, wahl=wahl)
        return True

    def _join_universe(self, universe: int):
        if self._sock is None:
            return
        if universe not in self._universen_soll:
            self._universen_soll.append(universe)
        if self._mc_iface is None or universe in self._joined_universes:
            return   # OUT-79: nur dieser Rechner -> kein Multicast-Beitritt
        try:
            mreq = (socket.inet_aton(_multicast_addr(universe))
                    + socket.inet_aton(self._mc_iface))
            self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self._joined_universes.append(universe)
        except Exception as e:
            print(f"[sACN-In] multicast join error for U{universe}: {e}")

    def join_universe(self, universe: int):
        """Spaeter weitere Multicast Group joinen."""
        self._join_universe(universe)

    # ── Subscribe ────────────────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[int, bytes], None]):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unsubscribe(self, cb: Callable[[int, bytes], None]):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def subscribe_absender(self, cb: Callable[..., None]):
        """NET-15: ``cb(universe, dmx, absender, prioritaet)`` — mit Absender,
        damit die Fernsteuerung zwei Pulte auf demselben Universum trennen
        kann. Absender = CID (hex), Prioritaet aus dem Framing-
        Layer. Preview- und Stream-Ende-Pakete bekommen diese Zuhoerer NICHT
        (Preview ist nicht fuer den Live-Betrieb, Stream-Ende-Daten sind laut
        E1.31 zu ignorieren)."""
        if cb not in self._callbacks_absender:
            self._callbacks_absender.append(cb)

    def unsubscribe_absender(self, cb: Callable[..., None]):
        if cb in self._callbacks_absender:
            self._callbacks_absender.remove(cb)

    # ── Merge ────────────────────────────────────────────────────────────────

    def set_merge(self, in_universe: int, out_universe: int, mode: str = "HTP"):
        if mode not in ("HTP", "LTP", "REPLACE"):
            mode = "HTP"
        self._merges[int(in_universe)] = (int(out_universe), mode)

    def remove_merge(self, in_universe: int):
        self._merges.pop(int(in_universe), None)

    def clear_merges(self):
        self._merges.clear()

    def merges(self) -> dict[int, tuple[int, str]]:
        """Kopie der Merge-Zuordnung ``{in_universe: (out_universe, mode)}`` —
        nur zum Lesen (IMP-2, Mitschnitt-Assistent)."""
        return dict(self._merges)

    def _install_merge_handler(self):
        if self._merge_cb_installed:
            return
        self._merge_cb_installed = True
        self.subscribe(self._merge_callback)

    def _merge_callback(self, in_univ: int, data: bytes):
        cfg = self._merges.get(in_univ)
        if not cfg:
            return
        out_univ, mode = cfg
        # F-20: in die Eingangs-Schicht des AppState legen statt direkt ins
        # Live-Universe zu schreiben — der Per-Frame-Renderer ueberschrieb sonst
        # gepatchte Kanaele. ``_render_frame`` mischt die Schicht deterministisch.
        try:
            from src.core.app_state import get_state
            # NET-15: Kanaele der DMX-Fernsteuerung nicht in die Ausgabe mischen.
            from src.core.dmx.fernsteuerung import reservierte_kanaele
            skip = reservierte_kanaele("sacn", in_univ)
            if skip:
                get_state().apply_input_merge(out_univ, data, mode, skip=skip)
            else:
                get_state().apply_input_merge(out_univ, data, mode)
        except Exception as e:
            print(f"[sACN-In] merge error: {e}")

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running and self._sock is not None:
            try:
                data, _addr = self._sock.recvfrom(2048)
                netz = self._absender_netz
                if netz is not None:
                    from src.core.dmx.empfangsadresse import absender_passt
                    if not absender_passt(netz, _addr[0] if _addr else None):
                        continue   # OUT-79: nicht aus dem Netz der Karte
                self.letztes_paket_um = time.monotonic()   # OUT-79
                self.pakete += 1
                parsed = self._parse(data)
                if parsed is None:
                    continue
                universe, dmx = parsed
                for cb in list(self._callbacks):
                    try:
                        cb(universe, dmx)
                    except Exception as e:
                        print(f"[sACN-In] cb error: {e}")
                if self._callbacks_absender:
                    kopf = self._parse_kopf(data)
                    if kopf is not None and not kopf[2]:
                        for cb in list(self._callbacks_absender):
                            try:
                                cb(universe, dmx, kopf[0], kopf[1])
                            except Exception as e:
                                print(f"[sACN-In] cb error: {e}")
            except socket.timeout:
                continue
            except OSError as e:
                if self._running:   # STAB-30: nur der unerwartete Abbruch
                    from src.core.diagnose_log import melde_still
                    melde_still("sacn.empfang", e, text="Empfang beendet")
                self._running = False   # NET-06: Status ehrlich halten -> Auto-Restart
                break
            except Exception as e:
                if self._running:
                    print(f"[sACN-In] loop error: {e}")
                self._running = False   # NET-06
                break

    @staticmethod
    def _parse_kopf(packet: bytes) -> tuple[str, int, bool] | None:
        """NET-15: ``(cid_hex, prioritaet, verwerfen)`` eines schon von
        :meth:`_parse` angenommenen Pakets. ``verwerfen`` = Preview-Daten oder
        Stream beendet (Options-Byte, Offset 112). CID: Root-Layer 22..38,
        Prioritaet: Framing-Layer Offset 108."""
        if len(packet) < 126:
            return None
        opt = packet[112]
        return (bytes(packet[22:38]).hex(), int(packet[108]),
                bool(opt & (SACN_OPT_PREVIEW | SACN_OPT_TERMINATED)))

    def _parse(self, packet: bytes) -> tuple[int, bytes] | None:
        """Parse E1.31 paket -> (universe, dmx bytes). None bei Fehler."""
        if len(packet) < 126:
            return None
        try:
            # ACN packet identifier at offset 4..16
            if packet[4:16] != SACN_ACN_PACKET_ID:
                return None
            # Root layer: vector at [18:22] -> should be 0x00000004 (VECTOR_ROOT_E131_DATA)
            # Framing layer starts at offset 38
            # Framing vector at [40:44]
            framing_vector = struct.unpack("!I", packet[40:44])[0]
            if framing_vector != SACN_VECTOR_DATA:
                return None
            # Universe at offset 113..115 (BE)
            universe = struct.unpack("!H", packet[113:115])[0]
            # DMP layer at 115. DMP vector at [117], address type [118],
            # first prop addr [119:121], increment [121:123], property count [123:125]
            prop_count = struct.unpack("!H", packet[123:125])[0]
            # Start at offset 125 + 1 (start code byte)
            if prop_count < 1:
                return None
            start_code = packet[125]
            if start_code != 0x00:
                return None  # not DMX
            # property count stammt ungeprueft aus dem Paket: Slot-Zahl gegen die
            # real vorhandenen Bytes UND 512 klemmen (513 = Startcode + 512 Slots).
            slots = max(0, min(prop_count - 1, len(packet) - 126, 512))
            dmx = packet[126:126 + slots]
            return universe, dmx
        except Exception:
            return None


_receiver: SACNReceiver | None = None


def get_sacn_receiver() -> SACNReceiver:
    global _receiver
    if _receiver is None:
        _receiver = SACNReceiver()
    return _receiver

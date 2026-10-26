"""Art-Net Input - empfaengt DMX-Pakete und ruft Callbacks.

Verwendung:
    rx = get_artnet_receiver()
    rx.subscribe(lambda universe, data: print(universe, len(data)))
    rx.start()

Merge in Universe:
    rx.set_merge(in_universe=1, out_universe=2, mode="HTP")
"""
from __future__ import annotations
import socket
import struct
import threading
import time
from typing import Callable

ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
OPCODE_ARTDMX = 0x5000


class ArtNetReceiver:
    """Empfaengt ArtDmx Pakete auf UDP Port 6454.

    Callbacks: cb(universe: int, dmx: bytes)
    Universe ist 1-basiert (Art-Net wire format ist 0-basiert).
    """

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._callbacks: list[Callable[[int, bytes], None]] = []
        self._callbacks_absender: list[Callable[..., None]] = []   # NET-15
        # Merge-Konfiguration: {in_universe: (out_universe, mode)}
        # mode: "HTP" / "LTP" / "REPLACE"
        self._merges: dict[int, tuple[int, str]] = {}
        # OUT-79: gewaehlte Empfangsadresse + Empfangs-Lage (Firewall-Hinweis)
        self.wahl: str = ""             # s. empfangsadresse (""=alle Karten)
        self.host: str | None = None    # tatsaechlich gebunden
        self._port: int | None = None
        self._absender_netz = None      # Linux/macOS + Karte: Absender-Filter
        self.gestartet_um: float | None = None
        self.letztes_paket_um: float | None = None
        self.pakete = 0
        self.letzter_fehler: str = ""
        # Letzter Start gewollt, aber am Binden gescheitert -> ein Wahlwechsel
        # (neu_binden) versucht es erneut, statt still aus zu bleiben.
        self.start_gescheitert = False
        self._eigene_ips: frozenset = frozenset()

    def start(self, host: str | None = None, port: int | None = None,
              wahl: str | None = None):
        """Ohne ``host`` gilt die gewaehlte Empfangsadresse (OUT-79,
        :mod:`src.core.dmx.empfangsadresse`; Vorgabe alle Karten = 0.0.0.0).
        ``wahl`` setzt sie fuer diesen Start ausdruecklich. ``host``/``port``
        nur fuer Tests (127.0.0.1 + freier Port, NET-15). ``port=None`` liest
        ``ARTNET_PORT`` erst hier (nicht als Default-Wert eingefroren) — Tests
        biegen die Modul-Konstante um (IMP-2)."""
        if self._running:
            return
        if port is None:
            port = ARTNET_PORT
        from src.core.dmx import empfangsadresse as ea
        if host is None:
            w = ea.aktuelle() if wahl is None else ea.normiere(wahl)
            host = ea.bind_host(w)
            self._absender_netz = ea.absender_netz(w)
        else:
            w = ea.normiere(host) if wahl is None else ea.normiere(wahl)
            self._absender_netz = None
        self.wahl = w
        self.letzter_fehler = ""
        self._port = int(port)
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # XPLAT-03: BEIDE Optionen, weil Linux den Port nur teilt, wenn beide
            # Seiten DIESELBE gesetzt haben (gemessen in test_artnet_reuseport.py,
            # Tabelle im Modulkopf). Mit nur einer bleibt der Input still, sobald
            # die 2. Art-Net-App (QLC+, anderes Tool) auf 6454 sich fuer die andere
            # entschieden hat -- und das faellt nicht als Fehler auf, sondern als
            # Stille. Wie der sACN-Input (sacn_input.py).
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # Not on Windows (kein SO_REUSEPORT)
            self._sock.bind((host, int(port)))
            self._sock.settimeout(0.5)
        except Exception as e:
            print(f"[ArtNet-In] bind error: {e}")
            self.letzter_fehler = f"{host}:{port} — {e}"
            try:
                if self._sock is not None:
                    self._sock.close()
            except Exception:
                pass
            self._sock = None
            self.start_gescheitert = True
            return
        self.start_gescheitert = False
        self.host, self._port = host, int(port)
        self._eigene_ips = ea.eigene_ips()
        if ea.karte_vorhanden(w) is False:
            # Linux/macOS binden dann trotzdem (0.0.0.0) — sagen, warum nichts
            # kommt, statt nach 5 s auf die Firewall zu zeigen.
            self.letzter_fehler = ea.karte_fehlt_text(w)
        self.gestartet_um = time.monotonic()
        self.letztes_paket_um = None
        self.pakete = 0
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ArtNet-In"
        )
        self._thread.start()
        self._install_merge_handler()
        print(f"[ArtNet-In] listening on {host}:{port}")

    def stop(self):
        self._running = False
        self.start_gescheitert = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None

    def adresse(self) -> tuple[str, int] | None:
        """OUT-79: (Adresse, Port), an die der Socket gerade gebunden ist."""
        sock = self._sock
        if sock is None:
            return None
        try:
            return tuple(sock.getsockname()[:2])
        except OSError:
            return None

    def neu_binden(self, wahl: str) -> bool:
        """OUT-79: laufenden Empfang an eine andere Empfangsadresse binden.
        Zuhoerer und Merge-Zuordnung bleiben. Ist der letzte Start an der
        vorigen Wahl gescheitert, wird mit der neuen erneut gestartet.
        Liefert, ob er danach WIRKLICH laeuft; ``False`` ohne Startversuch,
        wenn er nicht lief (dann gilt die Wahl beim naechsten Start)."""
        if not self.is_running():
            if not self.start_gescheitert:
                self.letzter_fehler = ""   # alter Fehler gilt fuer alte Wahl
                return False
        else:
            self.stop()
        self.start(port=self._port, wahl=wahl)
        return self.is_running()

    def is_running(self) -> bool:
        # NET-06: nicht nur das Flag pruefen — ein ueber `break` gestorbener RX-Thread
        # soll als NICHT laufend gelten, damit der UI-Auto-Restart-Guard greift.
        t = self._thread
        return self._running and t is not None and t.is_alive()

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
        kann. Absender = IP des Senders, Prioritaet ``None``
        (Art-Net kennt keine)."""
        if cb not in self._callbacks_absender:
            self._callbacks_absender.append(cb)

    def unsubscribe_absender(self, cb: Callable[..., None]):
        if cb in self._callbacks_absender:
            self._callbacks_absender.remove(cb)

    # ── Merge in Universe ────────────────────────────────────────────────────

    def set_merge(self, in_universe: int, out_universe: int, mode: str = "HTP"):
        """Wenn Daten auf in_universe ankommen, merge sie in out_universe.

        mode: HTP (Highest takes precedence), LTP (Latest takes precedence),
              REPLACE (komplett ueberschreiben).
        """
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
        """Subscriber, der nach Merge-Konfiguration ins lokale Universe schreibt."""
        if getattr(self, "_merge_cb_installed", False):
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
            skip = reservierte_kanaele("artnet", in_univ)
            if skip:
                get_state().apply_input_merge(out_univ, data, mode, skip=skip)
            else:
                get_state().apply_input_merge(out_univ, data, mode)
        except Exception as e:
            print(f"[ArtNet-In] merge error: {e}")

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _ist_echo(self, addr) -> bool:
        """Paket der eigenen Art-Net-Ausgabe (eigene Adresse + Quell-Port
        eines eigenen Senders)? Nur fuer die Empfangs-Diagnose (OUT-79)."""
        if not addr or len(addr) < 2:
            return False
        from src.core.dmx.artnet import eigene_quellports
        if addr[1] not in eigene_quellports():
            return False
        from src.core.dmx.empfangsadresse import ist_eigene_adresse
        return ist_eigene_adresse(addr[0], self._eigene_ips)

    def _loop(self):
        while self._running and self._sock is not None:
            try:
                data, addr = self._sock.recvfrom(1024)
                netz = self._absender_netz
                if netz is not None:
                    from src.core.dmx.empfangsadresse import absender_passt
                    if not absender_passt(netz, addr[0] if addr else None):
                        continue   # OUT-79: nicht aus dem Netz der Karte
                # OUT-79: jedes fremde Paket zaehlt — „seit dem Einschalten kam
                # gar nichts" ist der Fingerabdruck einer blockierenden Firewall.
                # Das Echo der eigenen Art-Net-Ausgabe (Broadcast kommt lokal
                # zurueck) zaehlt nicht, es kommt auch bei Firewall-Sperre an.
                if not self._ist_echo(addr):
                    self.letztes_paket_um = time.monotonic()
                    self.pakete += 1
                if len(data) < 18 or data[:8] != ARTNET_HEADER:
                    continue
                opcode = struct.unpack("<H", data[8:10])[0]
                if opcode != OPCODE_ARTDMX:
                    continue
                # [10:12] = ProtVer (BE), [12]=Seq, [13]=Phys
                # [14:16] = Universe (LE wire, 0-based)
                # [16:18] = Length (BE)
                universe = struct.unpack("<H", data[14:16])[0] + 1
                length = struct.unpack(">H", data[16:18])[0]
                # Laengenfeld stammt ungeprueft aus dem Paket: gegen die real
                # vorhandenen Bytes UND das DMX-Maximum (512) klemmen, damit ein
                # manipuliertes Paket keine ueberlangen Slices erzeugt.
                length = max(0, min(length, len(data) - 18, 512))
                dmx = data[18:18 + length]
                for cb in list(self._callbacks):
                    try:
                        cb(universe, dmx)
                    except Exception as e:
                        print(f"[ArtNet-In] cb error: {e}")
                absender = addr[0] if addr else None
                for cb in list(self._callbacks_absender):
                    try:
                        cb(universe, dmx, absender, None)
                    except Exception as e:
                        print(f"[ArtNet-In] cb error: {e}")
            except socket.timeout:
                continue
            except OSError as e:
                # Socket closed during stop() ODER transienter Netzfehler.
                if self._running:   # STAB-30: nur der unerwartete Abbruch
                    from src.core.diagnose_log import melde_still
                    melde_still("artnet.empfang", e, text="Empfang beendet")
                self._running = False   # NET-06: Status ehrlich halten -> Auto-Restart
                break
            except Exception as e:
                if self._running:
                    print(f"[ArtNet-In] loop error: {e}")
                self._running = False   # NET-06
                break


_receiver: ArtNetReceiver | None = None


def get_artnet_receiver() -> ArtNetReceiver:
    global _receiver
    if _receiver is None:
        _receiver = ArtNetReceiver()
    return _receiver

"""OUT-82: DDP-Ausgabe (WLED), WLED-Abfrage, Matrix-Verteilung.

Kein echtes Netz: Schein-Empfaenger (UDP) und Schein-HTTP-Server auf
127.0.0.1. Beispiel-IPs nur 192.0.2.x.
"""
import http.server
import json
import os
import socket
import struct
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.core.dmx import ddp, wled


# ── Hilfen ──────────────────────────────────────────────────────────────────

class _Empfaenger:
    """UDP-Schein-Empfaenger auf 127.0.0.1 (freier Port)."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]

    def pakete(self, bis_push: bool = True, zeit_s: float = 3.0) -> list[dict]:
        out = []
        ende = time.monotonic() + zeit_s
        while time.monotonic() < ende:
            try:
                p, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                if out and not bis_push:
                    break
                continue
            k = ddp.ddp_kopf_lesen(p)
            out.append(k)
            if bis_push and k["push"]:
                break
        return out

    def close(self):
        self.sock.close()


@pytest.fixture
def empfaenger():
    e = _Empfaenger()
    yield e
    e.close()


@pytest.fixture
def gesperrt(monkeypatch):
    """STAB-39-Sperre ausdruecklich setzen (wie in einem Probelauf)."""
    import src.core.paths as paths
    monkeypatch.setattr(paths, "echte_ausgabe_pruefen", lambda was: False)


@pytest.fixture
def ausgabe_frei(monkeypatch):
    """Nur fuer diesen Test: STAB-39-Sperre aufheben (Ziel ist 127.0.0.1)."""
    import src.core.paths as paths
    monkeypatch.setattr(paths, "echte_ausgabe_pruefen", lambda was: True)


# ── Kopf und Paketaufteilung gegen die Spezifikation ────────────────────────

def test_kopf_laut_spezifikation():
    k = ddp.ddp_kopf(offset=0x01020304, laenge=300, push=True, sequenz=5)
    assert len(k) == ddp.DDP_KOPF_LAENGE == 10
    assert k[0] == 0x41                      # Version 1 + Push
    assert k[1] == 5
    assert k[2] == 0x0B                      # RGB, 8 Bit
    assert k[3] == 1                         # Standard-Ausgabe
    assert struct.unpack(">I", k[4:8])[0] == 0x01020304
    assert struct.unpack(">H", k[8:10])[0] == 300
    assert ddp.ddp_kopf(0, 10)[0] == 0x40    # ohne Push
    assert ddp.DDP_PORT == 4048


def test_nutzlast_grenze():
    with pytest.raises(ValueError):
        ddp.ddp_kopf(0, 1441)


def test_aufteilung_push_nur_im_letzten():
    daten = bytes(range(256)) * 13           # 3328 Byte -> 1440 + 1440 + 448
    pakete = [ddp.ddp_kopf_lesen(p) for p in ddp.ddp_pakete(daten, offset=100, sequenz=3)]
    assert [p["laenge"] for p in pakete] == [1440, 1440, 448]
    assert [p["offset"] for p in pakete] == [100, 1540, 2980]
    assert [p["push"] for p in pakete] == [False, False, True]
    assert b"".join(p["daten"] for p in pakete) == daten
    assert all(p["version"] == 1 and p["sequenz"] == 3 for p in pakete)


def test_mehr_als_512_kanaele_in_einem_paket():
    """DDP kennt keine 512-Kanal-Grenze: 1440 Byte gehen in EIN Paket."""
    pakete = ddp.ddp_pakete(bytes(1440))
    assert len(pakete) == 1 and len(pakete[0]) == 10 + 1440


# ── Strom: mehrere Universen als ein zusammenhaengendes Bild ────────────────

def test_mehrere_universen_ein_strom(ausgabe_frei, empfaenger):
    strom = ddp.DDPStrom("127.0.0.1", port=empfaenger.port)
    a, b = ddp.DDPTeil(strom, 0), ddp.DDPTeil(strom, 480)
    a.send_dmx(bytes([1]) * 480)
    b.send_dmx(bytes([2]) * 512)
    assert strom.senden() == 1               # 992 Byte -> ein Paket
    pakete = empfaenger.pakete()
    assert len(pakete) == 1 and pakete[0]["push"]
    assert pakete[0]["daten"] == bytes([1]) * 480 + bytes([2]) * 512
    a.close()
    assert strom._sock is not None           # b nutzt den Strom noch
    b.close()
    assert strom._sock is None


def test_gesperrt_sendet_nichts(gesperrt, empfaenger):
    """STAB-39: ohne echte App geht nichts hinaus."""
    strom = ddp.DDPStrom("127.0.0.1", port=empfaenger.port)
    teil = ddp.DDPTeil(strom, 0)
    teil.send_dmx(bytes([255]) * 512)
    assert strom.senden() == 0
    assert empfaenger.pakete(bis_push=False, zeit_s=0.3) == []
    teil.close()


# ── OutputManager: neue Ausgabe-Art ────────────────────────────────────────

def _manager(monkeypatch, port):
    from src.core.dmx.output_manager import OutputManager
    monkeypatch.setattr(ddp, "DDP_PORT", port)
    om = OutputManager()
    for u in (1, 2):
        om.add_universe(u)
    return om


def test_output_manager_ddp_zwei_universen(ausgabe_frei, empfaenger, monkeypatch):
    om = _manager(monkeypatch, empfaenger.port)
    om.add_ddp(1, "127.0.0.1", offset=0)
    om.add_ddp(2, "127.0.0.1", offset=480)
    try:
        assert om._ddp_outputs[1].strom is om._ddp_outputs[2].strom
        om.universes[1].set_range(1, bytes([10]) * 480)
        om.universes[2].set_range(1, bytes([20]) * 512)
        om._send_all()
        pakete = empfaenger.pakete()
        daten = b"".join(p["daten"] for p in pakete)
        assert pakete[-1]["push"] and not any(p["push"] for p in pakete[:-1])
        assert daten[:480] == bytes([10]) * 480
        assert daten[480:992] == bytes([20]) * 512
        assert om.sendet_wirklich(1) and om.sendet_wirklich(2)
        assert {e["weg"] for e in om.ausgabe_status()} == {"DDP"}
    finally:
        om.remove_output(1)
        om.remove_output(2)
    assert not om._ddp_outputs


def test_output_manager_automatischer_offset(ausgabe_frei, empfaenger, monkeypatch):
    om = _manager(monkeypatch, empfaenger.port)
    om.add_ddp(1, "127.0.0.1")
    om.add_ddp(2, "127.0.0.1")
    try:
        assert (om._ddp_outputs[1].offset, om._ddp_outputs[2].offset) == (0, 512)
    finally:
        om.remove_output(1)
        om.remove_output(2)


def test_output_manager_blackout_gilt_fuer_ddp(ausgabe_frei, empfaenger, monkeypatch):
    om = _manager(monkeypatch, empfaenger.port)
    om.add_ddp(1, "127.0.0.1", offset=0)
    try:
        om.universes[1].set_range(1, bytes([200]) * 30)
        om.set_blackout(True)
        om._send_all()
        daten = b"".join(p["daten"] for p in empfaenger.pakete())
        assert daten[:30] == bytes(30)
    finally:
        om.set_blackout(False)
        om.remove_output(1)


def test_output_manager_gesperrt_sendet_nichts(gesperrt, empfaenger, monkeypatch):
    om = _manager(monkeypatch, empfaenger.port)
    om.add_ddp(1, "127.0.0.1", offset=0)
    try:
        om.universes[1].set_range(1, bytes([255]) * 512)
        om._send_all()
        assert empfaenger.pakete(bis_push=False, zeit_s=0.3) == []
    finally:
        om.remove_output(1)


def test_apply_output_config_ddp(monkeypatch, tmp_path):
    """universes.json mit ``DDP``-Zeile -> add_ddp(Universum, IP, Offset)."""
    import types
    from src.core.app_state import AppState
    aufrufe = []

    class _OM:
        def add_universe(self, n):
            return object()

        def ausgabe_status(self):
            return []

        def remove_output(self, *a, **k):
            pass

        def add_ddp(self, num, ip, offset=None):
            aufrufe.append((num, ip, offset))

    pfad = tmp_path / "universes.json"
    pfad.write_text(json.dumps([
        {"num": 1, "output": "DDP", "patch": "192.0.2.50", "out_universe": 0},
        {"num": 2, "output": "DDP", "patch": "192.0.2.50", "out_universe": "480"},
    ]), encoding="utf-8")
    stub = types.SimpleNamespace(output_manager=_OM(), universes={})
    AppState.apply_output_config(stub, str(pfad))
    assert aufrufe == [(1, "192.0.2.50", 0), (2, "192.0.2.50", 480)]


def test_ausgabe_typ_im_dialog():
    from src.ui.widgets import output_config as oc
    assert "DDP" in oc.AUSGABE_TYPEN
    assert oc.ausgabe_typ_text("DDP") == "DDP (WLED)"
    assert oc._ext_universe_bereich("DDP")[0] == 0


# ── WLED: /json/info und mDNS gegen lokale Scheinserver ─────────────────────

class _Info(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/json/info":
            self.send_error(404)
            return
        body = json.dumps({"name": "Matrix links", "ver": "0.15.0",
                           "leds": {"count": 800}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_json_info_abfrage():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Info)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        info = wled.wled_info("127.0.0.1", port=srv.server_address[1])
        assert info == {"ip": "127.0.0.1", "name": "Matrix links",
                        "leds": 800, "version": "0.15.0"}
    finally:
        srv.shutdown()
        srv.server_close()


def test_json_info_ohne_antwort_kurz():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                 # Port ist zu -> sofort None
    t0 = time.monotonic()
    assert wled.wled_info("127.0.0.1", port=port, zeitgrenze_s=0.5) is None
    assert time.monotonic() - t0 < 2.0


def test_mdns_suche_gegen_schein_responder():
    resp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    resp.bind(("127.0.0.1", 0))
    resp.settimeout(3.0)
    gesehen = []

    def antworten():
        try:
            anfrage, absender = resp.recvfrom(9000)
        except OSError:
            return
        gesehen.append(anfrage)
        antwort = struct.pack(">HHHHHH", 0, 0x8400, 0, 1, 0, 0) + anfrage[12:]
        resp.sendto(antwort, absender)

    t = threading.Thread(target=antworten, daemon=True)
    t.start()
    try:
        ips = wled.mdns_suche(0.5, ziel=resp.getsockname())
    finally:
        t.join(3)
        resp.close()
    assert ips == ["127.0.0.1"]
    assert b"_wled" in gesehen[0] and gesehen[0][-4:] == struct.pack(">HH", 12, 1)


# ── Matrix (FM-80) auf Universen / DDP verteilen ───────────────────────────

def test_ddp_verteilung_matrix():
    from src.core import led_matrix
    a = led_matrix.MatrixAngaben(breite_px=20, hoehe_px=20, format="RGB")
    v = wled.ddp_verteilung(a, start_universum=3)
    # 20 px * 3 = 60 Kanaele je Zeile, 8 Zeilen (480) je Universum -> 3 Teile
    assert [x["universum"] for x in v] == [3, 4, 5]
    assert [x["offset"] for x in v] == [0, 480, 960]
    assert sum(x["pixel"] for x in v) == 400
    text = wled.ddp_hinweis(a, 3)
    assert "192.0.2.50" in text and "Offset 480" in text


# ── Nachbesserung nach Pruefung ─────────────────────────────────────────────

def test_teile_ueberschreiben_sich_nicht_unabhaengig_von_reihenfolge(
        ausgabe_frei, empfaenger, monkeypatch):
    """Offset 480 (ganze Matrix-Zeilen): die unbenutzten Kanaele 481..512 von
    Universum 1 duerfen den Anfang von Universum 2 nicht schwaerzen — auch
    wenn Universum 2 vor Universum 1 angelegt wurde."""
    from src.core.dmx.output_manager import OutputManager
    monkeypatch.setattr(ddp, "DDP_PORT", empfaenger.port)
    om = OutputManager()
    for u in (2, 1):
        om.add_universe(u)
    om.add_ddp(1, "127.0.0.1", offset=0)
    om.add_ddp(2, "127.0.0.1", offset=480)
    try:
        om.universes[1].set_range(1, bytes([10]) * 480)
        om.universes[2].set_range(1, bytes([20]) * 480)
        om._send_all()
        daten = b"".join(p["daten"] for p in empfaenger.pakete())
        assert daten[:480] == bytes([10]) * 480
        assert daten[480:960] == bytes([20]) * 480
    finally:
        om.remove_output(1)
        om.remove_output(2)


def test_json_info_stummes_geraet_zeitgrenze():
    """Geraet nimmt die Verbindung an, antwortet aber nie -> Zeitgrenze."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(5)
    port = s.getsockname()[1]
    try:
        t0 = time.monotonic()
        assert wled.wled_info("127.0.0.1", port=port, zeitgrenze_s=0.5) is None
        assert time.monotonic() - t0 < 2.0
    finally:
        s.close()

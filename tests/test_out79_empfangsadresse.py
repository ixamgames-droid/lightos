"""OUT-79: Empfangsadresse des DMX-Eingangs (Art-Net/sACN) und Firewall-Hinweis.

Kein echtes Netz: echte Sockets nur auf 127.0.0.1 mit freiem Port; alle
anderen Wahlen (alle Karten, eine Karte) gegen einen aufzeichnenden
Socket-Ersatz — ``0.0.0.0`` wird in der Suite nie wirklich gebunden.
Je Fertig-Punkt eine Gegenprobe.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import netz_hinweis as nh                              # noqa: E402
from src.core.dmx import artnet_input as ai                          # noqa: E402
from src.core.dmx import empfangsadresse as ea                       # noqa: E402
from src.core.dmx import fernsteuerung as fsm                        # noqa: E402
from src.core.dmx import sacn_input as si                            # noqa: E402
from src.core.dmx.fernsteuerung import Konfig, Zuordnung             # noqa: E402

KARTE = "192.0.2.10"      # RFC 5737 — nie eine echte Adresse


@pytest.fixture(autouse=True)
def _wahl_zuruecksetzen():
    ea.zuruecksetzen()
    yield
    ea.zuruecksetzen()


def _freier_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _warte(bed, sek=3.0):
    ende = time.monotonic() + sek
    while time.monotonic() < ende:
        if bed():
            return True
        time.sleep(0.01)
    return bed()


class _Sock:
    """Socket-Ersatz: zeichnet bind/setsockopt auf, empfängt nie etwas."""
    alle: list = []

    def __init__(self, *a, **k):
        self.gebunden = None
        self.optionen = []
        _Sock.alle.append(self)

    def setsockopt(self, *a):
        self.optionen.append(a)

    def bind(self, adr):
        self.gebunden = adr

    def settimeout(self, _t):
        pass

    def getsockname(self):
        return self.gebunden

    def recvfrom(self, _n):
        time.sleep(0.05)
        raise socket.timeout()

    def close(self):
        pass


@pytest.fixture
def ersatz_socket(monkeypatch):
    _Sock.alle = []
    monkeypatch.setattr(ai.socket, "socket", _Sock)
    monkeypatch.setattr(si.socket, "socket", _Sock)
    return _Sock


def _beitritte(sock) -> list[tuple[str, str]]:
    aus = []
    for opt in sock.optionen:
        if len(opt) == 3 and opt[1] == socket.IP_ADD_MEMBERSHIP:
            mreq = opt[2]
            aus.append((socket.inet_ntoa(mreq[:4]), socket.inet_ntoa(mreq[4:8])))
    return aus


# ── Wahl + Datenformat ────────────────────────────────────────────────────

@pytest.mark.parametrize("roh, soll", [
    ("", ""), (None, ""), ("0.0.0.0", ""), ("kaputt", ""), ("239.255.0.1", ""),
    ("300.1.1.1", ""), (" 192.0.2.10 ", KARTE), ("127.0.0.1", "127.0.0.1"),
])
def test_normiere(roh, soll):
    assert ea.normiere(roh) == soll


def test_alte_datei_ohne_feld_heisst_alle_karten(tmp_path):
    pfad = tmp_path / "f.json"
    pfad.write_text(json.dumps({"version": 1, "aktiv": True, "zuordnungen": [
        {"quelle": "artnet", "universum": 2, "kanal": 5, "ziel": "grand_master"}]}),
        encoding="utf-8")
    k = fsm.lade_konfig(str(pfad))
    assert k.empfangsadresse == ""
    assert ea.lade(str(pfad)) == ea.ALLE
    # Gegenprobe: alte Datei unverändert wieder geschrieben -> kein neues Feld
    fsm.speichere_konfig(k, str(pfad))
    assert "empfangsadresse" not in json.loads(pfad.read_text(encoding="utf-8"))


def test_speichern_behaelt_zuordnungen_und_laedt_wahl(tmp_path):
    pfad = str(tmp_path / "f.json")
    fsm.speichere_konfig(Konfig(aktiv=True, zuordnungen=[
        Zuordnung(quelle="sacn", universum=7, kanal=3)]), pfad)
    assert ea.speichere(ea.LOKAL, pfad)
    d = json.loads(open(pfad, encoding="utf-8").read())
    assert d["empfangsadresse"] == "127.0.0.1"
    assert d["aktiv"] is True and d["zuordnungen"][0]["universum"] == 7
    assert ea.lade(pfad) == ea.LOKAL
    # kaputter Wert in der Datei -> alle Karten (wie früher), nicht Absturz
    d["empfangsadresse"] = "nicht-ip"
    open(pfad, "w", encoding="utf-8").write(json.dumps(d))
    assert ea.lade(pfad) == ea.ALLE


def test_bind_host_je_plattform():
    assert ea.bind_host("", "win32") == "0.0.0.0"
    assert ea.bind_host("", "linux") == "0.0.0.0"
    assert ea.bind_host(ea.LOKAL, "linux") == "127.0.0.1"
    assert ea.bind_host(ea.LOKAL, "win32") == "127.0.0.1"
    assert ea.bind_host(KARTE, "win32") == KARTE
    # Linux/macOS: an eine Karten-Adresse gebunden käme kein Broadcast /
    # Multicast an -> 0.0.0.0 + Absender-Filter
    assert ea.bind_host(KARTE, "linux") == "0.0.0.0"
    assert ea.bind_host(KARTE, "darwin") == "0.0.0.0"
    assert ea.multicast_iface("") == "0.0.0.0"
    assert ea.multicast_iface(KARTE) == KARTE
    assert ea.multicast_iface(ea.LOKAL) is None


def test_absender_filter():
    netz = ea.absender_netz(KARTE, "linux", netzmaske=lambda ip: "255.255.255.0")
    assert netz == ipaddress.IPv4Network("192.0.2.0/24")
    assert ea.absender_passt(netz, "192.0.2.77")
    assert ea.absender_passt(netz, "127.0.0.1")       # dieser Rechner
    assert not ea.absender_passt(netz, "198.51.100.4")
    assert not ea.absender_passt(netz, None)
    # Maske unbekannt -> nur die Karte selbst
    assert ea.absender_netz(KARTE, "linux", netzmaske=lambda ip: None) == \
        ipaddress.IPv4Network(f"{KARTE}/32")
    # Windows filtert das Betriebssystem (Bind an die Karte) -> kein Filter
    assert ea.absender_netz(KARTE, "win32") is None
    assert ea.absender_netz("", "linux") is None
    assert ea.absender_passt(None, "198.51.100.4")


# ── Bindung je Wahl: echte Sockets nur auf 127.0.0.1 ──────────────────────

def test_artnet_nur_dieser_rechner_bindet_loopback_und_empfaengt():
    from src.core.dmx.artnet import _build_artdmx
    port = _freier_port()
    rx = ai.ArtNetReceiver()
    rx.start(port=port, wahl=ea.LOKAL)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        assert rx.adresse() == ("127.0.0.1", port)
        assert rx.host == "127.0.0.1" and rx.wahl == ea.LOKAL
        assert rx.pakete == 0 and rx.letztes_paket_um is None
        tx.sendto(_build_artdmx(0, bytes([9] * 4), 1), ("127.0.0.1", port))
        assert _warte(lambda: rx.pakete >= 1)
        assert rx.letztes_paket_um is not None
    finally:
        tx.close()
        rx.stop()


def test_artnet_ohne_host_folgt_der_gespeicherten_wahl():
    """Der App-Weg (``start()`` ohne Adresse) nimmt die gewählte Adresse."""
    ea.setze(ea.LOKAL)
    port = _freier_port()
    rx = ai.ArtNetReceiver()
    rx.start(port=port)
    try:
        if not rx.is_running():
            pytest.skip("UDP-Loopback nicht bindbar")
        assert rx.adresse() == ("127.0.0.1", port)
    finally:
        rx.stop()


def test_sacn_nur_dieser_rechner_ohne_multicast_unicast_kommt_an():
    from src.core.dmx.sacn import _pack_framing
    port = _freier_port()
    rx = si.SACNReceiver()
    rx.start(universes=[4], port=port, wahl=ea.LOKAL)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    got = []
    rx.subscribe(lambda u, d: got.append(u))
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        assert rx.adresse() == ("127.0.0.1", port)
        assert rx._joined_universes == []          # kein Multicast-Beitritt
        assert rx.universen() == [4]               # gemerkt trotzdem
        rx.join_universe(5)
        assert rx._joined_universes == [] and rx.universen() == [4, 5]
        tx.sendto(_pack_framing(bytes([1, 2]), 4, 1, "OUT-79", bytes(16)),
                  ("127.0.0.1", port))
        assert _warte(lambda: got == [4])
        assert rx.pakete == 1
    finally:
        tx.close()
        rx.stop()


def test_alle_karten_bindet_0000_wie_bisher(ersatz_socket):
    ea.setze(ea.ALLE)
    a, s = ai.ArtNetReceiver(), si.SACNReceiver()
    a.start()
    s.start(universes=[1, 2])
    try:
        assert a.adresse() == ("0.0.0.0", ai.ARTNET_PORT)
        assert s.adresse() == ("0.0.0.0", si.SACN_PORT)
        assert _beitritte(ersatz_socket.alle[1]) == [
            ("239.255.0.1", "0.0.0.0"), ("239.255.0.2", "0.0.0.0")]
    finally:
        a.stop()
        s.stop()


def test_karte_unter_windows_bindet_karte_und_tritt_dort_bei(ersatz_socket, monkeypatch):
    monkeypatch.setattr(ea.sys, "platform", "win32")
    ea.setze(KARTE)
    a, s = ai.ArtNetReceiver(), si.SACNReceiver()
    a.start()
    s.start(universes=[3])
    try:
        assert a.adresse() == (KARTE, ai.ARTNET_PORT)
        assert s.adresse() == (KARTE, si.SACN_PORT)
        assert _beitritte(ersatz_socket.alle[1]) == [("239.255.0.3", KARTE)]
        assert a._absender_netz is None and s._absender_netz is None
    finally:
        a.stop()
        s.stop()


def test_karte_unter_linux_0000_mit_filter_und_beitritt_ueber_karte(
        ersatz_socket, monkeypatch):
    monkeypatch.setattr(ea.sys, "platform", "linux")
    monkeypatch.setattr(ea, "_netzmaske", lambda ip: "255.255.255.0")
    ea.setze(KARTE)
    a, s = ai.ArtNetReceiver(), si.SACNReceiver()
    a.start()
    s.start(universes=[3])
    try:
        assert a.adresse() == ("0.0.0.0", ai.ARTNET_PORT)
        assert _beitritte(ersatz_socket.alle[1]) == [("239.255.0.3", KARTE)]
        assert a._absender_netz is not None and s._absender_netz is not None
        assert a._absender_netz == ipaddress.IPv4Network("192.0.2.0/24")
    finally:
        a.stop()
        s.stop()


def test_gegenprobe_explizite_adresse_bleibt_beim_alten(ersatz_socket):
    """Tests/NET-15 geben ``host`` direkt -> keine Wahl greift ein."""
    ea.setze(KARTE)
    s = si.SACNReceiver()
    s.start(universes=[1], host="127.0.0.1", port=1234)
    try:
        assert s.adresse() == ("127.0.0.1", 1234)
        assert _beitritte(ersatz_socket.alle[0]) == [("239.255.0.1", "0.0.0.0")]
    finally:
        s.stop()


class _PaketSock(_Sock):
    def __init__(self, pakete):
        super().__init__()
        self._pakete = list(pakete)

    def recvfrom(self, _n):
        if self._pakete:
            return self._pakete.pop(0)
        raise OSError("ende")


def test_absender_filter_im_empfang():
    from src.core.dmx.artnet import _build_artdmx
    rx = ai.ArtNetReceiver()
    got = []
    rx.subscribe(lambda u, d: got.append(u))
    rx._absender_netz = ipaddress.IPv4Network("192.0.2.0/24")
    rx._sock = _PaketSock([
        (_build_artdmx(0, b"\x01", 1), ("198.51.100.4", 6454)),   # fremdes Netz
        (_build_artdmx(1, b"\x01", 2), ("192.0.2.50", 6454)),     # Netz der Karte
    ])
    rx._running = True
    rx._loop()
    assert got == [2] and rx.pakete == 1
    # Gegenprobe: ohne Filter kommen beide an
    rx2 = ai.ArtNetReceiver()
    got2 = []
    rx2.subscribe(lambda u, d: got2.append(u))
    rx2._sock = _PaketSock([
        (_build_artdmx(0, b"\x01", 1), ("198.51.100.4", 6454)),
        (_build_artdmx(1, b"\x01", 2), ("192.0.2.50", 6454))])
    rx2._running = True
    rx2._loop()
    assert got2 == [1, 2]


def test_neu_binden_behaelt_merge_zuhoerer_und_universen(ersatz_socket):
    ea.setze(ea.ALLE)
    a, s = ai.ArtNetReceiver(), si.SACNReceiver()
    cb = lambda u, d: None                                       # noqa: E731
    a.subscribe(cb)
    a.start()
    a.set_merge(2, 5, "LTP")
    s.start(universes=[7, 9])
    s.set_merge(7, 1, "HTP")
    try:
        neu = ea.anwenden(ea.LOKAL, a, s)
        assert neu == ["artnet", "sacn"]
        assert a.adresse() == ("127.0.0.1", ai.ARTNET_PORT)
        assert s.adresse() == ("127.0.0.1", si.SACN_PORT)
        assert a.merges() == {2: (5, "LTP")} and cb in a._callbacks
        assert s.universen() == [7, 9] and s.merges() == {7: (1, "HTP")}
        assert ea.aktuelle() == ea.LOKAL
    finally:
        a.stop()
        s.stop()
    # Gegenprobe: nicht laufend -> nichts neu gebunden, Wahl gilt beim Start
    assert ea.anwenden(ea.ALLE, ai.ArtNetReceiver(), si.SACNReceiver()) == []


def test_bind_fehler_wird_gemerkt(monkeypatch):
    class _Kaputt(_Sock):
        def bind(self, adr):
            raise OSError(99, "Cannot assign requested address")
    monkeypatch.setattr(ai.socket, "socket", _Kaputt)
    rx = ai.ArtNetReceiver()
    rx.start(wahl=KARTE)
    assert not rx.is_running()
    assert "Cannot assign" in rx.letzter_fehler


def test_beim_start_setzt_wahl_aus_der_datei(monkeypatch, tmp_path):
    pfad = str(tmp_path / "f.json")
    fsm.speichere_konfig(Konfig(empfangsadresse=ea.LOKAL), pfad)
    monkeypatch.setattr(fsm, "konfig_pfad", lambda: pfad)
    monkeypatch.setattr(fsm, "installiere_qt_wecker", lambda: None)
    monkeypatch.setattr(fsm, "_instanz", fsm.DmxFernsteuerung())
    ea.setze(ea.ALLE)
    assert fsm.beim_start() == []          # inaktiv -> kein Empfänger
    assert ea.aktuelle() == ea.LOKAL


# ── netz_hinweis (gemeinsamer Baustein, auch für WEB-07/WEB-12) ──────────

def test_vorwarnung_je_plattform():
    w = nh.vorwarnung("0.0.0.0", sys_platform="win32")
    assert w.startswith("Windows fragt gleich, ob LightOS Daten aus dem Netzwerk")
    assert "„Zulassen“ (privates Netzwerk)" in w
    assert "Ohne Freigabe kommt nur an, was auf diesem Rechner gesendet wird." in w
    assert "ufw" in nh.vorwarnung("0.0.0.0", sys_platform="linux")
    assert "Erlauben" in nh.vorwarnung("0.0.0.0", sys_platform="darwin")
    # Gegenprobe: nur dieser Rechner -> keine Abfrage
    assert "keine Firewall-Abfrage" in nh.vorwarnung("127.0.0.1", sys_platform="win32")
    assert nh.loest_abfrage_aus("0.0.0.0", "win32")
    assert nh.loest_abfrage_aus(KARTE, "win32")
    assert not nh.loest_abfrage_aus("127.0.0.1", "win32")
    assert not nh.loest_abfrage_aus("0.0.0.0", "linux")
    # Andere Dienste (Web-Server) nutzen dieselben Texte
    assert "Handy-Konsole Daten" in nh.vorwarnung(was="die Handy-Konsole",
                                                   sys_platform="win32")
    assert "TCP 5000" in nh.wo_pruefen("linux", ports="TCP 5000")


def test_programmname(monkeypatch):
    monkeypatch.setattr(nh.sys, "frozen", True, raising=False)
    monkeypatch.setattr(nh.sys, "executable", "/opt/LightOS/LightOS.exe")
    assert nh.programmname("win32") == "LightOS.exe"
    assert "„LightOS.exe“" in nh.wo_pruefen("win32")
    assert nh.programmname("linux") == "LightOS"


def test_kein_empfang_frist_und_gegenprobe():
    assert not nh.kein_empfang(None, None, 100.0)              # nicht gestartet
    assert not nh.kein_empfang(100.0, None, 104.9)             # Frist läuft
    assert nh.kein_empfang(100.0, None, 105.0)
    assert not nh.kein_empfang(100.0, 101.0, 200.0)            # kam etwas an
    t = nh.kein_empfang_text("0.0.0.0", sekunden=6, sys_platform="win32")
    assert "Seit 6 s" in t and "Firewall" in t and "Windows-Sicherheit" in t
    t = nh.kein_empfang_text("127.0.0.1", sekunden=6, sys_platform="win32")
    assert "Firewall" not in t and "127.0.0.1" in t


def test_empfaenger_ohne_empfang_nur_wenn_er_laeuft():
    class _R:
        gestartet_um = 0.0
        letztes_paket_um = None
        laeuft = True

        def is_running(self):
            return self.laeuft
    r = _R()
    assert nh.empfaenger_ohne_empfang(r, 10.0)
    r.laeuft = False
    assert not nh.empfaenger_ohne_empfang(r, 10.0)
    assert not nh.empfaenger_ohne_empfang(object(), 10.0)      # fremder Stub


def test_quelltext_aendert_keine_firewall():
    """Punkt (4) des Items wird bewusst NICHT gebaut: kein Code legt Regeln an."""
    from pathlib import Path
    wurzel = Path(__file__).resolve().parents[1]
    for rel in ("src/core/netz_hinweis.py", "src/core/dmx/empfangsadresse.py",
                "src/ui/widgets/dmx_empfang_box.py"):
        text = (wurzel / rel).read_text(encoding="utf-8").lower()
        for verboten in ("netsh", "new-netfirewallrule", "ufw allow",
                         "subprocess", "os.system"):
            assert verboten not in text, (rel, verboten)

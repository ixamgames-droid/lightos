"""OUT-68 — uDMX im Ausgabeweg: entkoppelter Sender, Sicherheitsweg, Konfiguration.

Nur Attrappen (``_out68_usb_attrappe``); ``LIGHTOS_KEIN_USB`` (conftest)
verhindert zusaetzlich, dass irgendein Test echtes USB anfasst.

Geprueft wird, was am Adapter ANKOMMT — nicht, was gerechnet wurde.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import output_manager as om_mod                # noqa: E402
from src.core.dmx import udmx, udmx_process                     # noqa: E402
from src.core.dmx.serial_process import ST_OK, ST_DISABLED      # noqa: E402
import _out68_usb_attrappe as fake                              # noqa: E402


def _warte(bedingung, s=3.0):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.005)
    return bool(bedingung())


class Empfaenger:
    """Ausgabegeraet-Attrappe fuer den OutputManager: merkt das letzte Bild."""

    def __init__(self, port="2008:1066"):
        self.port = port
        self.bilder: list[bytes] = []
        self.zu = 0

    def send_dmx(self, data):
        self.bilder.append(bytes(data))

    def is_connected(self):
        return True

    def close(self):
        self.zu += 1

    @property
    def letztes(self) -> bytes:
        return self.bilder[-1]


def _manager(wert=200):
    """Manager mit Universum 1 (alles ``wert``), uDMX UND Enttec-Attrappe —
    beide muessen dasselbe bekommen."""
    om = om_mod.OutputManager()
    u = om.add_universe(1)
    u.set_range(1, bytes([wert]) * 512)
    assert u.get_all() == bytes([wert]) * 512
    udmx_dev, enttec = Empfaenger(), Empfaenger("/dev/attrappe")
    om._udmx_outputs[1] = udmx_dev
    om._enttec_outputs[1] = enttec
    return om, udmx_dev, enttec


# ── Sender blockiert den Ausgabe-Thread nie ──────────────────────────────────

def test_haengender_adapter_haelt_weder_send_dmx_noch_den_frame_auf():
    """Der Transfer haengt (Attrappe wartet auf ein Ereignis). ``send_dmx`` und
    ein ganzer ``_send_all``-Durchlauf muessen trotzdem sofort zurueckkommen."""
    frei = threading.Event()
    g = fake.Geraet()
    g.verhalten = lambda d: (frei.wait(5), len(d))[1]
    proxy = udmx_process.UdmxThreadProxy("", frame_interval=0.002,
                                         _usb=fake.usb(g))
    try:
        assert _warte(lambda: len(g.transfers) == 1)      # steckt im Transfer
        t0 = time.perf_counter()
        for i in range(200):
            proxy.send_dmx(bytes([i % 256]) * 512)
        assert time.perf_counter() - t0 < 0.2

        om = om_mod.OutputManager()
        om.add_universe(1)
        om._udmx_outputs[1] = proxy
        t0 = time.perf_counter()
        om._send_all()
        assert time.perf_counter() - t0 < 0.2
        assert len(g.transfers) == 1                      # haengt immer noch
    finally:
        frei.set()
        proxy.close()
    assert not proxy.is_open()


def test_das_neueste_bild_gewinnt():
    g = fake.Geraet()
    proxy = udmx_process.UdmxThreadProxy("", frame_interval=0.002,
                                         _usb=fake.usb(g))
    try:
        for i in range(1, 60):
            proxy.send_dmx(bytes([i]) * 512)
        assert _warte(lambda: g.transfers and g.transfers[-1][4] == bytes([59]) * 512)
        assert proxy.is_connected() and proxy.status() == ST_OK
        assert proxy.grund() == udmx.G_OK and proxy.grund_text() == ""
        # Auch ohne neues Bild wird weiter voll gesendet (Auffrischen).
        n = len(g.transfers)
        assert _warte(lambda: len(g.transfers) >= n + 5)
        assert {(t[0], t[1], t[2], t[3]) for t in g.transfers} == {(0x40, 2, 512, 0)}
    finally:
        proxy.close()


def test_abziehen_und_wiederverbinden_ueber_den_sender(monkeypatch):
    monkeypatch.setattr(udmx.Udmx, "RECONNECT_EVERY_S", 0.02)
    g = fake.Geraet()
    usb = fake.usb(g)
    proxy = udmx_process.UdmxThreadProxy("2008:1066", frame_interval=0.002,
                                         _usb=usb)
    try:
        assert _warte(proxy.is_connected)
        g.verhalten = lambda _d: (_ for _ in ()).throw(fake.abgezogen())
        usb[0].geraete = []
        assert _warte(proxy.is_disabled)
        assert proxy.status() == ST_DISABLED and not proxy.is_connected()
        assert proxy.grund() == udmx.G_NICHT_DA
        assert "nicht gefunden" in proxy.grund_text()
        assert om_mod.geraet_zustand(proxy) == om_mod.ZUSTAND_TOT

        neu = fake.Geraet(adresse=11)
        usb[0].geraete = [neu]
        proxy.send_dmx(bytes([77]) * 512)
        assert _warte(proxy.is_connected)
        assert _warte(lambda: neu.transfers and neu.transfers[-1][4] == bytes([77]) * 512)
        assert proxy.grund() == udmx.G_OK
        assert om_mod.geraet_zustand(proxy) == om_mod.ZUSTAND_SENDET
    finally:
        proxy.close()


def test_prozess_sender_startet_den_udmx_worker_und_meldet_den_grund(monkeypatch):
    """Kein echter Prozess: die Prozess-Fabrik ist eine Attrappe. Geprueft wird,
    WAS gestartet wuerde und dass der Grund ueber den Shared-Wert ankommt."""
    class Prozess:
        exitcode = None
        sentinel = 0

        def __init__(self):
            self.lebt = False

        def start(self):
            self.lebt = True

        def is_alive(self):
            return self.lebt

        def join(self, timeout=None):
            pass

        def terminate(self):
            self.lebt = False

    proxy = udmx_process.UdmxProcessProxy("2008:1066@1-2",
                                          _process_factory=Prozess)
    try:
        assert proxy.port == "2008:1066@1-2" and proxy.process_isolated
        echt = proxy._default_process_factory()
        assert echt._target is udmx_process._udmx_worker_main
        assert echt._args[0] == "2008:1066@1-2" and echt._args[4] is proxy._grund
        assert om_mod.geraet_zustand(proxy) == om_mod.ZUSTAND_VERBINDET

        proxy.send_dmx(bytes([9]) * 512)                  # nur Shared Memory
        assert bytes(proxy._buf.get_obj()) == bytes([9]) * 512

        import sys
        monkeypatch.setattr(sys, "platform", "linux")
        proxy._status.value = ST_DISABLED
        proxy._grund.value = udmx.G_KEINE_BERECHTIGUNG
        assert proxy.is_disabled() and "udev" in proxy.grund_text()
        assert "Zugriffsrecht" in proxy.grund_kurz()
    finally:
        proxy.close()


def test_worker_fabrik_haelt_den_grund_fest():
    grund = types.SimpleNamespace(value=udmx.G_OK)
    leer = fake.usb()
    with pytest.raises(udmx.UdmxFehler):
        udmx_process._fabrik("2008:1066", grund, usb=leer)()
    assert grund.value == udmx.G_NICHT_DA
    dev = udmx_process._fabrik("2008:1066", grund, usb=fake.usb(fake.Geraet()))()
    assert grund.value == udmx.G_OK and dev.is_open()


# ── fehlendes pyusb: die App laeuft weiter ───────────────────────────────────

def test_ohne_pyusb_laeuft_die_ausgabe_weiter_und_nennt_den_grund():
    """conftest setzt LIGHTOS_KEIN_USB — fuer den Sender derselbe Weg wie ein
    fehlendes pyusb. Der Manager darf weder werfen noch haengen."""
    om = om_mod.OutputManager()
    om.add_universe(1)
    om.add_udmx(1, "2008:1066")
    try:
        dev = om._udmx_outputs[1]
        assert isinstance(dev, udmx_process.UdmxThreadProxy)
        assert _warte(dev.is_disabled)
        assert dev.grund() == udmx.G_PYUSB_FEHLT
        om._send_all()
        [status] = om.ausgabe_status()
        assert status["weg"] == "uDMX" and status["ziel"] == "2008:1066"
        assert status["verbunden"] is False and "pyusb" in status["problem"]
        assert om.sendet_wirklich(1)

        from src.ui.ausgabe_banner import ausgabe_banner, ART_STOERUNG
        banner = ausgabe_banner(om.ausgabe_status())
        assert banner.art == ART_STOERUNG
        assert "U1 uDMX" in banner.text and "pyusb" in banner.text
    finally:
        om.stop()
    assert om._udmx_outputs == {}


# ── Sicherheitsweg: wirkt VOR dem Senden, gleich wie beim Enttec ─────────────

def test_normalbetrieb_kommt_unveraendert_an():
    om, u, e = _manager(200)
    om._send_all()
    assert u.letztes == bytes([200]) * 512 == e.letztes


def test_blackout_liefert_nullen():
    om, u, e = _manager(200)
    om.set_blackout(True)
    om._send_all()
    assert u.letztes == bytes(512) == e.letztes
    om.set_blackout(False)
    om._send_all()
    assert u.letztes == bytes([200]) * 512


def test_blackout_laesst_nur_die_erhalten_maske_stehen():
    om, u, e = _manager(200)
    om.set_blackout_keep_mask({1: frozenset({10, 11})})
    om.set_blackout(True)
    om._send_all()
    erwartet = bytearray(512)
    erwartet[9] = erwartet[10] = 200
    assert u.letztes == bytes(erwartet) == e.letztes


def test_grand_master_null_liefert_nullen():
    om, u, e = _manager(200)
    om.set_grand_master(0.0)
    om._send_all()
    assert u.letztes == bytes(512) == e.letztes
    om.set_grand_master(0.5)
    om._send_all()
    assert u.letztes == bytes([100]) * 512 == e.letztes


def test_laser_aus_wert_statt_null_bei_blackout_und_gm_null():
    """LAS-24/25: der Aus-Wert eines Lasers ist nicht immer 0."""
    om, u, e = _manager(200)
    om.set_gm_address_mask({1: frozenset(range(1, 513)) - {40}})
    om.set_gm_laser_aus_mask({1: {40: 17}})
    om.set_blackout(True)
    om._send_all()
    assert u.letztes[39] == 17 == e.letztes[39]
    assert sum(u.letztes) == 17
    om.set_blackout(False)
    om.set_grand_master(0.0)
    om._send_all()
    assert u.letztes[39] == 17 and sum(u.letztes) == 17 and u.letztes == e.letztes


def test_ziel_blackout_nullt_nur_seine_adressen():
    om, u, e = _manager(200)
    om.set_target_blackout("taste", {1: frozenset({1, 2, 3})})
    om._send_all()
    assert u.letztes[:4] == bytes([0, 0, 0, 200]) and u.letztes == e.letztes


def test_laser_not_aus_nullt_die_adressen_bzw_setzt_den_aus_wert():
    om, u, e = _manager(200)
    om.set_gm_laser_aus_mask({1: {41: 9}})
    om.set_laser_estop_mask({1: frozenset({40, 41})}, aktiv=True)
    om._send_all()
    assert u.letztes[39] == 0 and u.letztes[40] == 9
    assert u.letztes[0] == 200 and u.letztes == e.letztes
    om.set_laser_estop_mask({}, aktiv=False)
    om._send_all()
    assert u.letztes[39] == 200


def test_not_aus_gilt_je_ausgabeweg_auch_fuer_udmx():
    """OUT-64: wird bei aktivem NOT-AUS ein ANDERES Universum auf den
    uDMX-Adapter gelegt, bleiben die Laser-Adressen dort gesperrt."""
    om = om_mod.OutputManager()
    for n in (1, 2):
        om.add_universe(n).set_range(1, bytes([200]) * 512)
    a = Empfaenger()
    om._udmx_outputs[1] = a
    assert om._wege_von(1) == [("udmx", None)]
    om.set_laser_estop_mask({1: frozenset({40})}, aktiv=True)
    # Umrouten: Universum 1 verliert den Adapter, Universum 2 bekommt ihn.
    om.remove_output(1)
    b = Empfaenger()
    om._udmx_outputs[2] = b
    om._send_all()
    assert a.zu == 1
    assert b.letztes[39] == 0 and b.letztes[38] == 200


def test_fehler_im_udmx_sender_beendet_den_frame_nicht():
    om, u, e = _manager(200)

    def wirft(_data):
        raise RuntimeError("kaputt")
    u.send_dmx = wirft
    for _ in range(om_mod.SENDE_FEHLER_SCHWELLE):
        om._send_all()
    assert e.letztes == bytes([200]) * 512                # Enttec lief weiter
    assert [p["weg"] for p in om.sende_probleme()] == ["uDMX"]


# ── Registrierung ────────────────────────────────────────────────────────────

def test_typwechsel_und_stop_schliessen_den_adapter(monkeypatch):
    gebaut = []

    def fabrik(schluessel):
        gebaut.append(Empfaenger(schluessel))
        return gebaut[-1]
    monkeypatch.setattr(om_mod, "_make_udmx_device", fabrik)
    om = om_mod.OutputManager()
    om.add_udmx(1, " 2008:1066@1-2 ")
    assert gebaut[0].port == "2008:1066@1-2" and om.sendet_wirklich(1)
    # Derselbe Adapter auf einem anderen Universum: dort erst schliessen.
    om.add_udmx(3, "2008:1066@1-2")
    assert gebaut[0].zu == 1 and sorted(om._udmx_outputs) == [3]
    om.remove_output(3)
    assert gebaut[1].zu == 1 and not om.sendet_wirklich(3)
    om.add_udmx(2, "")
    om.remove_output(2, ausser="udmx")
    assert 2 in om._udmx_outputs
    om.stop()
    assert gebaut[2].zu == 1 and om._udmx_outputs == {}
    assert "udmx" in om._REGISTRY_NAMEN


def test_manager_ohne_init_kommt_ohne_udmx_tabelle_aus():
    """Bestandstests bauen den Manager per ``__new__`` — ohne das neue Feld."""
    om = om_mod.OutputManager.__new__(om_mod.OutputManager)
    om._enttec_outputs, om._artnet_outputs, om._sacn_outputs = {}, {}, {}
    assert om._wege_von(1) == []
    assert not om.sendet_wirklich(1)


# ── Konfiguration ────────────────────────────────────────────────────────────

class _Protokoll:
    """OutputManager-Attrappe fuer ``apply_output_config``."""

    def __init__(self):
        self.rufe = []

    def ausgabe_status(self):
        return []

    def add_universe(self, n):
        return object()

    def __getattr__(self, name):
        if name.startswith(("add_", "remove_")):
            return lambda *a, **k: self.rufe.append((name, a, k))
        raise AttributeError(name)


def _anwenden(tmp_path, zeilen):
    from src.core.app_state import AppState
    p = tmp_path / "universes.json"
    p.write_text(json.dumps(zeilen), encoding="utf-8")
    stub = types.SimpleNamespace(output_manager=_Protokoll(), universes={})
    AppState.apply_output_config(stub, path=str(p))
    return [r for r in stub.output_manager.rufe if r[0] != "remove_output"]


ALT = [
    {"num": 1, "name": "Main", "output": "Enttec", "patch": "/dev/attrappe0"},
    {"num": 2, "name": "Netz", "output": "ArtNet", "patch": "", "out_universe": 4},
    {"num": 3, "name": "Netz2", "output": "sACN", "patch": "10.0.0.9"},
    {"num": 4, "name": "Aus", "output": "Disabled", "patch": ""},
]


def test_alte_konfiguration_wird_unveraendert_angewandt(tmp_path, monkeypatch):
    from src.core import app_state
    monkeypatch.setattr(app_state, "diagnose_enttec_port", lambda _p: None)
    rufe = _anwenden(tmp_path, ALT)
    assert rufe == [
        ("add_enttec", (1, "/dev/attrappe0"), {}),
        ("add_artnet", (2, "255.255.255.255"), {"out_universe": 4}),
        ("add_sacn", (3, "10.0.0.9"), {"out_universe": None}),
    ]
    # ... und die Datei selbst bleibt Byte fuer Byte stehen.
    assert json.loads((tmp_path / "universes.json").read_text("utf-8")) == ALT


def test_udmx_zeile_richtet_den_adapter_ein(tmp_path, monkeypatch):
    from src.core import app_state
    monkeypatch.setattr(app_state, "diagnose_enttec_port", lambda _p: None)
    rufe = _anwenden(tmp_path, ALT + [
        {"num": 5, "name": "USB", "output": "uDMX", "patch": "2008:1066@1-2"},
        {"num": 6, "name": "USB auto", "output": "uDMX", "patch": ""},
    ])
    assert rufe[-2:] == [("add_udmx", (5, "2008:1066@1-2"), {}),
                         ("add_udmx", (6, ""), {})]
    assert len(rufe) == 5


@pytest.fixture
def konfig(tmp_path, monkeypatch):
    from src.ui.widgets import output_config as oc
    p = tmp_path / "universes.json"
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(p))

    def schreibe(zeilen):
        io.open(p, "w", encoding="utf-8").write(json.dumps(zeilen))

    def lies():
        return json.loads(p.read_text("utf-8"))
    return types.SimpleNamespace(oc=oc, schreibe=schreibe, lies=lies)


def test_speichern_und_laden_einer_udmx_zeile(konfig):
    konfig.schreibe(ALT)
    assert konfig.oc._persist_output(5, "uDMX", "16c0:05dc#SN001")
    zeilen = konfig.lies()
    assert zeilen[:4] == ALT                              # Bestand unberuehrt
    assert zeilen[4] == {"num": 5, "name": "Universe 5", "output": "uDMX",
                         "patch": "16c0:05dc#SN001"}
    assert konfig.oc._gespeicherte_ausgabe_zeile("uDMX")["num"] == 5
    assert konfig.oc._gespeicherte_ausgabe_zeile("Enttec")["num"] == 1


def test_udmx_hat_keine_externe_universumsnummer(konfig):
    oc = konfig.oc
    assert oc._ext_universe_bereich("uDMX") is None
    assert oc._effektives_universum("uDMX", 7, None) is None
    doppelt = oc._doppelte_ziele([
        {"num": 1, "output": "uDMX", "patch": "2008:1066@1-2"},
        {"num": 2, "output": "uDMX", "patch": "2008:1066@1-2"},
        {"num": 3, "output": "uDMX", "patch": "2008:1066@1-3"},
    ])
    assert doppelt == [("Zeile 1, Zeile 2", "uDMX → 2008:1066@1-2")]
    assert oc.AUSGABE_TYPEN == ("Disabled", "Enttec", "uDMX", "sACN", "ArtNet")


# ── Oberflaeche ──────────────────────────────────────────────────────────────

@pytest.fixture
def dialog(konfig, qapp_oder_neu):
    konfig.schreibe([
        {"num": 1, "name": "Main", "output": "Enttec", "patch": "/dev/attrappe0"},
        {"num": 4, "name": "USB", "output": "uDMX", "patch": "2008:1066@1-2"},
    ])
    d = konfig.oc.OutputConfigDialog()
    yield d
    d.deleteLater()


@pytest.fixture
def qapp_oder_neu():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_dialog_zeigt_die_art_und_laedt_die_gespeicherte_zeile(dialog):
    from PySide6.QtWidgets import QTabWidget, QComboBox
    tabs = dialog.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())][:2] == [
        "Enttec Pro USB", "uDMX (USB)"]
    assert dialog._spin_udmx_univ.value() == 4
    assert dialog._combo_udmx.currentData() == "2008:1066@1-2"
    assert "Gespeichert" in dialog._lbl_udmx_status.text()
    # Die Universen-Tabelle kennt den Typ — sonst fiele die Zeile beim
    # naechsten „Speichern" still auf „Disabled".
    combo = dialog._univ_table.cellWidget(1, 2)
    assert isinstance(combo, QComboBox) and combo.currentText() == "uDMX"
    assert dialog._univ_table.cellWidget(0, 2).currentText() == "Enttec"
    # Beim Dialogbau wird NICHT gesucht (kein USB-Zugriff ohne Anlass).
    assert dialog._udmx_such_thread is None and not dialog._udmx_gesucht


def test_suche_laeuft_im_hilfs_thread_und_fuellt_die_auswahl(dialog, monkeypatch):
    from src.ui.widgets import output_config as oc
    wer = []

    def suchen():
        wer.append(threading.current_thread().name)
        return {"geraete": [("CYL-6602 · 2008:1066 · Anschluss 1-2", "2008:1066@1-2"),
                            ("CYL-6602 · 2008:1066 · Anschluss 1-5", "2008:1066@1-5")],
                "unklar": 0, "code": udmx.G_OK, "text": ""}
    monkeypatch.setattr(oc, "_udmx_suchen", suchen)
    dialog._tab_gewechselt(dialog._udmx_tab_index)
    dialog._udmx_such_thread.join(2)
    dialog._udmx_suche_abholen()
    assert wer == ["UdmxSuche"]
    assert dialog._combo_udmx.count() == 2
    assert dialog._combo_udmx.currentData() == "2008:1066@1-2"   # Auswahl bleibt
    assert "2 Adapter gefunden" in dialog._lbl_udmx_status.text()
    # Zweiter Tab-Wechsel sucht nicht noch einmal von selbst.
    dialog._tab_gewechselt(dialog._udmx_tab_index)
    assert wer == ["UdmxSuche"]


def test_suche_ohne_pyusb_zeigt_den_erklaerenden_hinweis(dialog):
    """Echter Suchweg: conftest schaltet USB ab -> Befund wie „pyusb fehlt"."""
    from src.ui.widgets import output_config as oc
    ergebnis = oc._udmx_suchen()
    assert ergebnis["code"] == udmx.G_PYUSB_FEHLT and ergebnis["geraete"] == []
    dialog._udmx_liste_zeigen({"geraete": [], "unklar": 0,
                               "code": udmx.G_PYUSB_FEHLT,
                               "text": udmx.grund_text(udmx.G_PYUSB_FEHLT)})
    assert "pip install pyusb" in dialog._lbl_udmx_hinweis.text()
    # Der gespeicherte Adapter bleibt gewaehlt, statt zu verschwinden.
    assert dialog._combo_udmx.currentData() == "2008:1066@1-2"


def test_gespeicherter_adapter_fehlt_in_der_liste_bleibt_sichtbar(dialog):
    dialog._udmx_liste_zeigen({"geraete": [("Anyma uDMX · 16c0:05dc", "16c0:05dc#A")],
                               "unklar": 0, "code": udmx.G_OK, "text": ""})
    assert dialog._combo_udmx.currentData() == "2008:1066@1-2"
    assert "derzeit nicht gefunden" in dialog._combo_udmx.currentText()


def test_verbinden_richtet_ein_speichert_und_nennt_den_grund(dialog, konfig, monkeypatch):
    class Geraet(Empfaenger):
        def is_connected(self):
            return False

        def is_disabled(self):
            return True

        def grund_text(self):
            return udmx.grund_text(udmx.G_KEINE_BERECHTIGUNG, self.port)

    om = om_mod.OutputManager()
    monkeypatch.setattr(om_mod, "_make_udmx_device", Geraet)
    state = types.SimpleNamespace(output_manager=om, universes={})
    monkeypatch.setattr(konfig.oc, "get_state", lambda: state)
    dialog._spin_udmx_univ.setValue(2)
    dialog._connect_udmx()
    dialog._udmx_pruef_timer.stop()
    assert om._udmx_outputs[2].port == "2008:1066@1-2"
    assert {"num": 2, "name": "Universe 2", "output": "uDMX",
            "patch": "2008:1066@1-2"} in konfig.lies()
    assert "(gespeichert)" in dialog._lbl_udmx_status.text()
    dialog._udmx_status_nachtragen()
    assert "sendet nicht" in dialog._lbl_udmx_status.text()
    assert "Zugriffsrecht" in dialog._lbl_udmx_hinweis.text()
    om.stop()


def test_verbinden_ohne_adapter_tut_nichts(dialog, konfig, monkeypatch):
    monkeypatch.setattr(konfig.oc, "get_state",
                        lambda: pytest.fail("darf nicht einrichten"))
    dialog._combo_udmx.clear()
    dialog._combo_udmx.addItem("Kein Adapter gefunden", "")
    dialog._connect_udmx()
    assert "Kein Adapter gewählt" in dialog._lbl_udmx_status.text()


# ── Diagnose / Selbsttest ────────────────────────────────────────────────────

def test_selbsttest_fuehrt_pyusb_als_optional_und_meldet_udmx():
    from src.core import selbsttest
    assert "usb.core" in selbsttest.OPTIONALE_MODULE
    assert "usb.core" not in getattr(selbsttest, "PFLICHT_MODULE", ())
    _code, zeilen = selbsttest.bericht()
    assert any(z.startswith("optional usb.core:") for z in zeilen)
    assert any(z.startswith("optional uDMX:") for z in zeilen)
    assert not any(z.startswith("FEHLER") and "usb" in z for z in zeilen)


def test_diagnosepaket_nennt_bibliothek_und_grund(monkeypatch):
    import sys
    from src.core import diagnose_log
    dev = types.SimpleNamespace(
        port="2008:1066",
        grund_text=lambda: udmx.grund_text(udmx.G_NICHT_DA, "2008:1066"))
    state = types.SimpleNamespace(
        output_manager=types.SimpleNamespace(_udmx_outputs={3: dev}))
    monkeypatch.setitem(sys.modules, "src.core.app_state",
                        types.SimpleNamespace(_state=state))
    zeilen = diagnose_log.udmx_infos()
    assert "pyusb" in zeilen[0]
    assert zeilen[1].startswith("U3 Adapter 2008:1066:") and "nicht gefunden" in zeilen[1]
    state.output_manager._udmx_outputs = {}
    assert diagnose_log.udmx_infos(immer=False) == []
    assert len(diagnose_log.udmx_infos()) == 1


def test_requirements_fuehren_pyusb_nur_als_optionalen_eintrag():
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    zeilen = open(os.path.join(wurzel, "requirements.txt"),
                  encoding="utf-8").read().splitlines()
    pyusb = [z for z in zeilen if "pyusb" in z.lower()]
    assert pyusb and all(z.lstrip().startswith("#") for z in pyusb)

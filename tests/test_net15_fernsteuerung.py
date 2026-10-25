"""NET-15: DMX-Fernsteuerung ueber den Art-Net-/sACN-Eingang.

Prueft die Zuordnung (Executor-Fader, Grand Master, GO/Zurueck/Stop), die
Schwelle mit Hysterese (GO genau einmal), „nur bei Aenderung", die Uebergabe
aus dem Empfangs-Thread in den GUI-Thread, Speichern/Laden (auch alte bzw.
fehlende Konfiguration), dass Fernsteuer-Kanaele NICHT in die Ausgabe gemischt
werden, und End-to-End mit echten Art-Net- und sACN-Paketen ueber 127.0.0.1
(freier Port). Gegenproben stehen jeweils daneben.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.dmx import fernsteuerung as fsm
from src.core.dmx.fernsteuerung import (
    DmxFernsteuerung, Konfig, Zuordnung, ZIEL_BACK, ZIEL_FADER, ZIEL_GM,
    ZIEL_GO, ZIEL_STOP,
)
from src.core.engine.executor import PlaybackEngine


# ── Hilfen ────────────────────────────────────────────────────────────────

class _OM:
    def __init__(self):
        self.grand_master = 1.0
        self.gm_aufrufe: list[tuple[float, int]] = []

    def set_grand_master(self, v):
        self.grand_master = v
        self.gm_aufrufe.append((v, threading.get_ident()))


def _state():
    pe = PlaybackEngine(None)
    tasten: list[tuple[int, str, int]] = []
    for ex in pe.executors:
        def press(btn, ex=ex):
            tasten.append((ex.slot, btn, threading.get_ident()))
        ex.press_btn = press
    return SimpleNamespace(playback_engine=pe, output_manager=_OM(), tasten=tasten)


def _fs(*zuordnungen, uhr=None):
    fs = DmxFernsteuerung(uhr=uhr or time.monotonic)
    fs.konfigurieren(Konfig(aktiv=True, zuordnungen=list(zuordnungen)))
    return fs


def _dmx(**kanaele) -> bytes:
    """_dmx(k1=10, k5=200) -> 512 Byte."""
    b = bytearray(512)
    for k, v in kanaele.items():
        b[int(k[1:]) - 1] = v
    return bytes(b)


# ── Fader / Grand Master: nur bei Aenderung ──────────────────────────────

def test_fader_erster_wert_ist_nur_ausgangslage_dann_bei_aenderung():
    st = _state()
    fs = _fs(Zuordnung(kanal=3, ziel=ZIEL_FADER, executor=2))
    ex = st.playback_engine.get_executor(2)
    ex.fader_value = 0.4                      # lokal eingestellt
    assert fs.empfange("artnet", 1, _dmx(k3=255)) == 0
    fs.abarbeiten(st)
    assert ex.fader_value == 0.4, "Ausgangslage darf lokalen Wert nicht ueberschreiben"
    assert fs.empfange("artnet", 1, _dmx(k3=0)) == 1
    assert fs.abarbeiten(st) == 1
    assert ex.fader_value == 0.0
    assert fs.empfange("artnet", 1, _dmx(k3=51)) == 1
    fs.abarbeiten(st)
    assert ex.fader_value == pytest.approx(0.2)


def test_ruhiges_pult_ueberschreibt_lokale_bedienung_nicht():
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_FADER, executor=1))
    ex = st.playback_engine.get_executor(1)
    fs.empfange("artnet", 1, _dmx(k1=100))
    fs.empfange("artnet", 1, _dmx(k1=128))
    fs.abarbeiten(st)
    assert ex.fader_value == pytest.approx(128 / 255)
    ex.fader_value = 0.9                      # Bediener greift lokal ein
    for _ in range(50):                       # Pult sendet weiter denselben Wert
        assert fs.empfange("artnet", 1, _dmx(k1=128)) == 0
    assert fs.abarbeiten(st) == 0
    assert ex.fader_value == 0.9


def test_gegenprobe_ohne_aenderungspruefung_wuerde_ueberschreiben():
    """Gegenprobe: dieselben Pakete, aber jeweils neu konfiguriert (= Ausgangslage
    vergessen) -> wieder keine Aktion. Und ein bewegter Kanal setzt sich durch."""
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_FADER))
    ex = st.playback_engine.get_executor(1)
    fs.empfange("artnet", 1, _dmx(k1=128))
    ex.fader_value = 0.9
    fs.empfange("artnet", 1, _dmx(k1=129))   # Bewegung am Pult -> gewinnt
    fs.abarbeiten(st)
    assert ex.fader_value == pytest.approx(129 / 255)


def test_grand_master_und_master_executor_folgen():
    st = _state()
    mex = st.playback_engine.get_executor(5)
    mex.fader_function = "master"
    fs = _fs(Zuordnung(quelle="sacn", kanal=10, ziel=ZIEL_GM, executor=7))
    fs.empfange("sacn", 1, _dmx(k10=255))
    fs.empfange("sacn", 1, _dmx(k10=0))
    fs.empfange("sacn", 1, _dmx(k10=102))
    # Zwei Werte in der Queue -> fallen auf den letzten zusammen.
    assert fs.abarbeiten(st) == 1
    assert st.output_manager.grand_master == pytest.approx(0.4)
    assert len(st.output_manager.gm_aufrufe) == 1
    assert mex.fader_value == pytest.approx(0.4)
    # Executor-Feld spielt fuer GM keine Rolle
    assert st.playback_engine.get_executor(7).fader_value == 1.0


def test_quelle_und_universum_muessen_passen():
    st = _state()
    fs = _fs(Zuordnung(quelle="artnet", universum=3, kanal=1, ziel=ZIEL_GM))
    for q, u in (("sacn", 3), ("artnet", 2)):
        fs.empfange(q, u, _dmx(k1=0))
        fs.empfange(q, u, _dmx(k1=200))
    assert fs.abarbeiten(st) == 0
    fs.empfange("artnet", 3, _dmx(k1=0))
    fs.empfange("artnet", 3, _dmx(k1=200))
    assert fs.abarbeiten(st) == 1


def test_inaktiv_tut_nichts():
    st = _state()
    fs = DmxFernsteuerung()
    fs.konfigurieren(Konfig(aktiv=False, zuordnungen=[Zuordnung(ziel=ZIEL_GM)]))
    fs.empfange("artnet", 1, _dmx(k1=0))
    fs.empfange("artnet", 1, _dmx(k1=200))
    assert fs.abarbeiten(st) == 0
    assert fs.reservierte_kanaele("artnet", 1) == frozenset()


def test_kurzes_paket_ohne_kanal_wird_uebergangen():
    st = _state()
    fs = _fs(Zuordnung(kanal=400, ziel=ZIEL_GM))
    fs.empfange("artnet", 1, bytes(24))
    fs.empfange("artnet", 1, bytes([255] * 24))
    assert fs.abarbeiten(st) == 0


# ── GO: Schwelle, Hysterese, genau einmal ─────────────────────────────────

def _go_fs(**kw):
    return _fs(Zuordnung(kanal=1, ziel=ZIEL_GO, executor=3, **kw))


def test_go_loest_bei_steigender_flanke_genau_einmal_aus():
    st = _state()
    fs = _go_fs()
    z = fs.konfig.zuordnungen[0]
    assert (z.ein_roh(), z.aus_roh()) == (128, 102)
    folge = [0, 127, 128, 255, 255, 200, 128, 110, 102, 200, 255]
    for v in folge:
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    # 128 erreicht -> GO; 110/102 bleiben ueber der Hysterese -> 200 loest NICHT aus
    assert [(s, b) for s, b, _t in st.tasten] == [(3, "go")]
    for v in (101, 0, 255):
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert [(s, b) for s, b, _t in st.tasten] == [(3, "go"), (3, "go")]


def test_gegenprobe_ohne_hysterese_flattert_ein_wackelnder_kanal():
    """Gegenprobe: hysterese=0 -> 127/128-Wackeln loest jedes Mal aus; mit der
    Standard-Hysterese genau einmal."""
    folge = [0, 128, 127, 128, 127, 128]
    st0 = _state()
    fs0 = _go_fs(hysterese=0)
    for v in folge:
        fs0.empfange("artnet", 1, _dmx(k1=v))
    fs0.abarbeiten(st0)
    assert len(st0.tasten) == 3
    st = _state()
    fs = _go_fs()
    for v in folge:
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert len(st.tasten) == 1


def test_go_steht_bei_ausgangslage_schon_oben_kein_ausloesen():
    st = _state()
    fs = _go_fs()
    for v in (255, 255, 200):
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert st.tasten == []
    for v in (0, 255):
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert len(st.tasten) == 1


def test_schwelle_einstellbar():
    st = _state()
    fs = _go_fs(schwelle=80)
    for v in (0, 200, 203, 204):
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert fs.konfig.zuordnungen[0].ein_roh() == 204
    assert len(st.tasten) == 1


def test_zurueck_und_stop():
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_BACK, executor=4),
             Zuordnung(kanal=2, ziel=ZIEL_STOP, executor=6))
    fs.empfange("artnet", 1, _dmx())
    fs.empfange("artnet", 1, _dmx(k1=255, k2=255))
    fs.abarbeiten(st)
    assert sorted((s, b) for s, b, _t in st.tasten) == [(4, "back"), (6, "stop")]


def test_pause_nimmt_ausgangslage_neu_auf():
    """Kommt ein Pult nach einer Empfangspause mit oben stehendem GO zurueck,
    loest das NICHT aus; ohne Pause (Gegenprobe) schon."""
    t = [0.0]
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_GO), uhr=lambda: t[0])
    fs.empfange("artnet", 1, _dmx(k1=0))
    t[0] = 10.0
    fs.empfange("artnet", 1, _dmx(k1=255))
    fs.abarbeiten(st)
    assert st.tasten == []
    # Gegenprobe ohne Pause
    st2 = _state()
    fs2 = _fs(Zuordnung(kanal=1, ziel=ZIEL_GO), uhr=lambda: t[0])
    fs2.empfange("artnet", 1, _dmx(k1=0))
    t[0] = 10.5
    fs2.empfange("artnet", 1, _dmx(k1=255))
    fs2.abarbeiten(st2)
    assert len(st2.tasten) == 1


def test_neu_konfigurieren_verwirft_wartende_aktionen():
    st = _state()
    fs = _go_fs()
    fs.empfange("artnet", 1, _dmx(k1=0))
    fs.empfange("artnet", 1, _dmx(k1=255))
    fs.konfigurieren(Konfig(aktiv=True, zuordnungen=[]))
    assert fs.abarbeiten(st) == 0


# ── Thread-Uebergabe ─────────────────────────────────────────────────────

def test_empfangs_thread_wendet_nichts_selbst_an():
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_GM), Zuordnung(kanal=2, ziel=ZIEL_GO))
    weckrufe = []
    fs.set_wecker(lambda: weckrufe.append(threading.get_ident()))

    def rx():
        fs.empfange("artnet", 1, _dmx())
        fs.empfange("artnet", 1, _dmx(k1=255, k2=255))

    th = threading.Thread(target=rx)
    th.start()
    th.join()
    assert st.output_manager.gm_aufrufe == [] and st.tasten == []
    assert weckrufe == [th.ident]
    fs.abarbeiten(st)
    haupt = threading.get_ident()
    assert [t for _v, t in st.output_manager.gm_aufrufe] == [haupt]
    assert [t for _s, _b, t in st.tasten] == [haupt]


def test_qt_bruecke_liefert_im_gui_thread_aus(monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_GM))
    monkeypatch.setattr(fsm, "_instanz", fs)
    monkeypatch.setattr(fsm, "_qt_wecker", None)
    st = _state()
    monkeypatch.setattr(fs, "abarbeiten",
                        lambda state=None, _orig=fs.abarbeiten: _orig(st))
    fsm.installiere_qt_wecker()

    def rx():
        fs.empfange("artnet", 1, _dmx())
        for v in (10, 20, 30):
            fs.empfange("artnet", 1, _dmx(k1=v))

    th = threading.Thread(target=rx)
    th.start()
    th.join()
    assert st.output_manager.gm_aufrufe == []   # noch nicht ausgeliefert
    ende = time.monotonic() + 2
    while not st.output_manager.gm_aufrufe and time.monotonic() < ende:
        app.processEvents()
    aufrufe = st.output_manager.gm_aufrufe
    assert aufrufe, "Qt-Bruecke hat nicht ausgeliefert"
    assert all(t == threading.get_ident() for _v, t in aufrufe)
    assert aufrufe[-1][0] == pytest.approx(30 / 255)
    monkeypatch.setattr(fsm, "_qt_wecker", None)


# ── Speichern / Laden ─────────────────────────────────────────────────────

def test_speichern_laden_rundlauf(tmp_path):
    pfad = str(tmp_path / "fs.json")
    k = Konfig(aktiv=True, zuordnungen=[
        Zuordnung("artnet", 2, 17, ZIEL_FADER, 4),
        Zuordnung("sacn", 7, 1, ZIEL_GO, 1, schwelle=70, hysterese=5),
        Zuordnung("artnet", 1, 512, ZIEL_GM),
    ])
    assert fsm.speichere_konfig(k, pfad)
    roh = json.load(open(pfad, encoding="utf-8"))
    assert roh["version"] == 1 and roh["aktiv"] is True
    assert roh["zuordnungen"][1] == {
        "quelle": "sacn", "universum": 7, "kanal": 1, "ziel": "executor_go",
        "executor": 1, "schwelle": 70, "hysterese": 5}
    k2 = fsm.lade_konfig(pfad)
    assert k2 == k


def test_fehlende_kaputte_und_alte_datei(tmp_path):
    assert fsm.lade_konfig(str(tmp_path / "gibtsnicht.json")) == Konfig()
    kaputt = tmp_path / "kaputt.json"
    kaputt.write_text("{nicht json", encoding="utf-8")
    assert fsm.lade_konfig(str(kaputt)) == Konfig()
    # Zeilen ohne Schwelle/Hysterese (Standard), eine kaputte Zeile kostet nur sich
    alt = tmp_path / "alt.json"
    alt.write_text(json.dumps({"aktiv": True, "zuordnungen": [
        {"quelle": "artnet", "universum": 1, "kanal": 5, "ziel": "executor_go"},
        {"quelle": "midi", "kanal": 1, "ziel": "grand_master"},
        "quatsch",
        {"quelle": "sacn", "universum": "x", "kanal": 9999, "ziel": "grand_master"},
    ]}), encoding="utf-8")
    k = fsm.lade_konfig(str(alt))
    assert [(z.quelle, z.universum, z.kanal, z.ziel, z.schwelle, z.hysterese)
            for z in k.zuordnungen] == [
        ("artnet", 1, 5, "executor_go", 50, 10)]
    # Kanal 9999 / Universum "x" wird verworfen, nicht auf 512 bzw. 1 geklemmt
    # (sonst steuerte die Zeile still einen echten anderen Kanal).


def test_universes_json_bleibt_unberuehrt(tmp_path, monkeypatch):
    """Alte Ausgangs-Konfiguration laedt unveraendert: die Fernsteuerung hat
    eine eigene Datei und schreibt nie in universes.json."""
    from src.ui.widgets import output_config as oc
    uj = tmp_path / "universes.json"
    zeilen = [{"num": 1, "name": "U1", "output": "ArtNet", "patch": "2.0.0.1"}]
    uj.write_text(json.dumps(zeilen), encoding="utf-8")
    vorher = uj.read_bytes()
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(uj))
    fsm.speichere_konfig(Konfig(aktiv=True, zuordnungen=[Zuordnung()]),
                         str(tmp_path / "fs.json"))
    assert uj.read_bytes() == vorher
    assert oc._load_universe_config() == zeilen


def test_standardpfad_ist_im_test_umgelenkt():
    from src.core.paths import app_data_dir, dmx_fernsteuerung_path
    p = dmx_fernsteuerung_path()
    assert p == os.environ["LIGHTOS_DMX_FERNSTEUERUNG"]
    assert not p.startswith(app_data_dir())


# ── nicht in die Ausgabe gemischt ─────────────────────────────────────────

def _merge_stub():
    from src.core.app_state import AppState
    stub = SimpleNamespace(input_layer={}, input_merge_modes={},
                           _input_lock=threading.RLock(), universes={1: None},
                           input_last_seen={}, input_unconfigured={})
    stub.apply_input_merge = (
        lambda out, data, mode="HTP", skip=None:
        AppState.apply_input_merge(stub, out, data, mode, skip=skip))
    return stub


def test_apply_input_merge_laesst_reservierte_kanaele_aus():
    stub = _merge_stub()
    stub.apply_input_merge(1, _dmx(k1=9, k2=200, k3=7))
    assert stub.input_layer[1][2] == 200            # Gegenprobe: ohne skip drin
    stub.apply_input_merge(1, _dmx(k1=9, k2=200, k3=7), skip=frozenset({2}))
    assert 2 not in stub.input_layer[1]             # auch der alte Wert ist raus
    assert stub.input_layer[1][1] == 9 and stub.input_layer[1][3] == 7


@pytest.mark.parametrize("modul,quelle", [("artnet_input", "artnet"),
                                          ("sacn_input", "sacn")])
def test_merge_callback_nimmt_fernsteuer_kanaele_aus(monkeypatch, modul, quelle):
    import importlib
    import src.core.app_state as app_state_mod
    mod = importlib.import_module(f"src.core.dmx.{modul}")
    rx = mod.ArtNetReceiver() if quelle == "artnet" else mod.SACNReceiver()
    stub = _merge_stub()
    monkeypatch.setattr(app_state_mod, "get_state", lambda: stub)
    rx.set_merge(4, 1, "HTP")
    # Gegenprobe: ohne Fernsteuerung landet Kanal 2 in der Ausgabe
    monkeypatch.setattr(fsm, "_instanz", None)
    rx._merge_callback(4, _dmx(k2=200))
    assert stub.input_layer[1][2] == 200
    fs = _fs(Zuordnung(quelle=quelle, universum=4, kanal=2, ziel=ZIEL_GO))
    monkeypatch.setattr(fsm, "_instanz", fs)
    rx._merge_callback(4, _dmx(k2=200, k3=5))
    assert 2 not in stub.input_layer[1]
    assert stub.input_layer[1][3] == 5
    # andere Quelle mit demselben Universum: nicht reserviert
    andere = "sacn" if quelle == "artnet" else "artnet"
    assert fs.reservierte_kanaele(andere, 4) == frozenset()


# ── End-to-End ueber 127.0.0.1 ────────────────────────────────────────────

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


class _Ziel:
    """Zaehlt eingereihte Aktionen, ohne sie anzuwenden (Weckruf aus RX-Thread)."""

    def __init__(self, fs):
        self.n = 0
        self.threads = set()
        fs.set_wecker(self._weck)

    def _weck(self):
        self.n += 1
        self.threads.add(threading.current_thread().name)


def _e2e(rx, sende, quelle, monkeypatch):
    import src.core.app_state as app_state_mod
    stub = _merge_stub()
    monkeypatch.setattr(app_state_mod, "get_state", lambda: stub)
    fs = _fs(Zuordnung(quelle=quelle, universum=3, kanal=1, ziel=ZIEL_FADER, executor=2),
             Zuordnung(quelle=quelle, universum=3, kanal=2, ziel=ZIEL_GO, executor=2),
             Zuordnung(quelle=quelle, universum=3, kanal=3, ziel=ZIEL_GM))
    monkeypatch.setattr(fsm, "_instanz", fs)
    ziel = _Ziel(fs)
    fs.verbinden(artnet_rx=rx if quelle == "artnet" else SimpleNamespace(subscribe=lambda cb: None),
                 sacn_rx=rx if quelle == "sacn" else SimpleNamespace(subscribe=lambda cb: None))
    rx.set_merge(3, 1, "HTP")
    st = _state()
    sende(_dmx(k1=0, k2=0, k3=255, k10=77))      # Ausgangslage
    assert _warte(lambda: 1 in stub.input_layer and stub.input_layer[1].get(10) == 77)
    sende(_dmx(k1=255, k2=255, k3=51, k10=77))
    assert _warte(lambda: ziel.n >= 1)
    sende(_dmx(k1=255, k2=255, k3=51, k10=77))   # unveraendert -> nichts Neues
    time.sleep(0.1)
    assert fs.abarbeiten(st) == 3
    assert st.playback_engine.get_executor(2).fader_value == 1.0
    assert [(s, b) for s, b, _t in st.tasten] == [(2, "go")]
    assert st.output_manager.grand_master == pytest.approx(0.2)
    # Fernsteuer-Kanaele 1..3 nicht in der Ausgabe, Kanal 10 schon
    assert not {1, 2, 3} & set(stub.input_layer[1])
    assert stub.input_layer[1][10] == 77
    assert ziel.threads and all(n.endswith("-In") for n in ziel.threads)


def test_e2e_artnet_ueber_loopback(monkeypatch):
    from src.core.dmx.artnet import _build_artdmx
    from src.core.dmx.artnet_input import ArtNetReceiver
    port = _freier_port()
    rx = ArtNetReceiver()
    rx.start(host="127.0.0.1", port=port)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = [0]

    def sende(data):
        seq[0] += 1
        # Art-Net-Draht ist 0-basiert: Universum 3 in LightOS = 2 auf dem Draht
        tx.sendto(_build_artdmx(2, data, seq[0]), ("127.0.0.1", port))
    try:
        _e2e(rx, sende, "artnet", monkeypatch)
    finally:
        tx.close()
        rx.stop()


def test_e2e_sacn_ueber_loopback(monkeypatch):
    from src.core.dmx.sacn import _pack_framing
    from src.core.dmx.sacn_input import SACNReceiver
    port = _freier_port()
    rx = SACNReceiver()
    rx.start(universes=[], host="127.0.0.1", port=port)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq = [0]

    def sende(data):
        seq[0] += 1
        tx.sendto(_pack_framing(data, 3, seq[0], "NET-15-Test", bytes(16)),
                  ("127.0.0.1", port))
    try:
        _e2e(rx, sende, "sacn", monkeypatch)
    finally:
        tx.close()
        rx.stop()


# ── Oberflaeche ───────────────────────────────────────────────────────────

def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_box_uebernehmen_speichert_und_laedt(tmp_path, monkeypatch):
    _app()
    from src.ui.widgets.dmx_fernsteuerung_box import (
        FernsteuerungBox, SP_EXEC, SP_SCHWELLE, SP_ZIEL)
    pfad = str(tmp_path / "fs.json")
    fs = DmxFernsteuerung()
    monkeypatch.setattr(fsm, "_instanz", fs)
    gestartet = []
    monkeypatch.setattr(fs, "empfaenger_starten",
                        lambda: gestartet.append(1) or ["artnet"])
    box = FernsteuerungBox(pfad=pfad)
    assert box.tabelle.rowCount() == 0 and box.lbl_status.text() == "Inaktiv"
    r = box.zeile_hinzu(Zuordnung(kanal=5, ziel=ZIEL_GO, executor=3,
                                  schwelle=60, hysterese=4))
    box.zeile_hinzu(Zuordnung(kanal=6, ziel=ZIEL_GM))
    assert box.tabelle.cellWidget(1, SP_EXEC).isEnabled() is False
    assert box.tabelle.cellWidget(1, SP_SCHWELLE).isEnabled() is False
    assert box.tabelle.cellWidget(r, SP_SCHWELLE).isEnabled() is True
    # Ziel umstellen schaltet die Felder um
    box.tabelle.cellWidget(1, SP_ZIEL).setCurrentIndex(0)   # Executor-Fader
    assert box.tabelle.cellWidget(1, SP_EXEC).isEnabled() is True
    box.check_aktiv.setChecked(True)
    assert box.uebernehmen()
    assert gestartet == [1]
    assert "Aktiv" in box.lbl_status.text() and "gespeichert" in box.lbl_status.text()
    assert fs.reservierte_kanaele("artnet", 1) == frozenset({5, 6})
    box2 = FernsteuerungBox(pfad=pfad)
    assert box2.konfig() == box.konfig()
    assert box2.konfig().zuordnungen[0].hysterese == 4
    assert box2.check_aktiv.isChecked()
    # Aus: speichert, startet keinen Empfang
    box2.check_aktiv.setChecked(False)
    assert box2.uebernehmen()
    assert gestartet == [1]
    assert box2.lbl_status.text().startswith("Aus")
    assert fs.reservierte_kanaele("artnet", 1) == frozenset()
    box.deleteLater()
    box2.deleteLater()
    monkeypatch.setattr(fsm, "_qt_wecker", None)



def _auswahl_lesbar(box):
    """Quelle/Ziel: Spalte und Feld mindestens so breit wie der sizeHint der
    Combo - der deckt den laengsten Eintrag samt Pfeil ab."""
    from src.ui.widgets.dmx_fernsteuerung_box import SP_QUELLE, SP_ZIEL
    kopf = box.tabelle.horizontalHeader()
    for r in range(box.tabelle.rowCount()):
        for sp in (SP_QUELLE, SP_ZIEL):
            combo = box.tabelle.cellWidget(r, sp)
            noetig = combo.sizeHint().width()
            laengster = max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                            for i in range(combo.count()))
            assert noetig > laengster
            assert kopf.sectionSize(sp) >= noetig, (r, sp, kopf.sectionSize(sp), noetig)
            assert combo.width() >= noetig, (r, sp, combo.width(), noetig)


@pytest.mark.parametrize("skala", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("breite", [737, 300])
def test_quelle_und_ziel_ganz_lesbar(tmp_path, skala, breite):
    # Windows-Gegenprobe D: ResizeToContents mass nur den Kopftext, die
    # Auswahlfelder zeigten „Art-N", „E:" bzw. „G". Wie in der App mit dem
    # Theme des Hauptfensters (Polster im QComboBox-Stil).
    app = _app()
    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from src.ui.widgets.dmx_fernsteuerung_box import FernsteuerungBox
    fenster = QWidget()
    # Das Theme setzt font-size: 12px fest; groessere Schrift (Windows-
    # Textskalierung) daher ueber dieselbe Regel. QT_SCALE_FACTOR allein
    # aendert die logischen Masse nicht.
    fenster.setStyleSheet(
        (ROOT / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
        + f"\nQWidget {{ font-size: {round(12 * skala)}px; }}\n")
    box = FernsteuerungBox(fenster, pfad=str(tmp_path / "fs.json"))
    QVBoxLayout(fenster).addWidget(box)
    try:
        # Wie der Bediener: Dialog offen, dann „+ Zuordnung" - die Spalte
        # wurde beim Einfuegen der Zeile gemessen, noch ohne Auswahlfeld.
        fenster.resize(breite, 420)
        fenster.show()
        app.processEvents()
        for ziel in (ZIEL_FADER, ZIEL_GO, ZIEL_GM):
            box.zeile_hinzu(Zuordnung(ziel=ziel))
            app.processEvents()
        _auswahl_lesbar(box)
        kopf = box.tabelle.horizontalHeader()
        if kopf.length() > box.tabelle.viewport().width():
            # zu eng: waagerecht rollen statt abschneiden
            assert box.tabelle.horizontalScrollBar().maximum() > 0
        if breite < 400:
            assert kopf.length() > box.tabelle.viewport().width()
    finally:
        fenster.close()
        fenster.deleteLater()


def test_ausgabe_dialog_hat_die_tabelle(tmp_path, monkeypatch):
    _app()
    from src.ui.widgets import output_config as oc
    from src.ui.widgets.dmx_fernsteuerung_box import FernsteuerungBox
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(tmp_path / "u.json"))
    dlg = oc.OutputConfigDialog()
    try:
        box = dlg._fernsteuerung_box
        assert isinstance(box, FernsteuerungBox)
        # sitzt im Reiter „DMX Input" neben den Merge-Gruppen
        from PySide6.QtWidgets import QTabWidget
        tabs = dlg.findChild(QTabWidget)
        i = next(i for i in range(tabs.count()) if tabs.tabText(i) == "DMX Input")
        assert tabs.widget(i).isAncestorOf(box)
        assert tabs.widget(i).isAncestorOf(dlg._check_artnet_in)
        # Standardgroesse: Tabelle und Knoepfe ueberlappen nicht (rollbar)
        dlg.show()
        tabs.setCurrentIndex(i)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        t = box.tabelle.geometry()
        k = box.btn_uebernehmen.geometry()
        assert t.bottom() < k.top(), (t, k)
    finally:
        dlg.deleteLater()


# ── Gegenpruefung (Runde 2) ───────────────────────────────────────────────

def test_zwei_pulte_auf_demselben_universum_kein_go_gewitter():
    """Haupt- und Backup-Pult senden dasselbe Universum, Pakete kommen
    abwechselnd: ohne Quellen-Trennung loeste GO ~22-mal pro Sekunde aus."""
    t = [0.0]
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_GO), uhr=lambda: t[0])
    n = 0
    for i in range(44):
        t[0] = i / 44
        if i % 2:
            n += fs.empfange("artnet", 1, _dmx(k1=0), absender="10.0.0.2")
        else:
            n += fs.empfange("artnet", 1, _dmx(k1=255), absender="10.0.0.1")
    assert n == 0          # Besitzer (erstes Pult) steht oben -> Ausgangslage
    assert fs.verworfen == 22
    # Der Besitzer drueckt GO (runter, hoch) -> genau einmal
    fs.empfange("artnet", 1, _dmx(k1=0), absender="10.0.0.1")
    fs.empfange("artnet", 1, _dmx(k1=255), absender="10.0.0.2")
    fs.empfange("artnet", 1, _dmx(k1=255), absender="10.0.0.1")
    fs.abarbeiten(st)
    assert len(st.tasten) == 1


def test_backup_pult_uebernimmt_erst_nach_pause_mit_neuer_ausgangslage():
    t = [0.0]
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_FADER, executor=2), uhr=lambda: t[0])
    fs.empfange("artnet", 1, _dmx(k1=10), absender="A")
    fs.empfange("artnet", 1, _dmx(k1=200), absender="B")   # verworfen
    assert fs.abarbeiten(st) == 0
    t[0] = fsm.PAUSE_S + 1          # A schweigt
    fs.empfange("artnet", 1, _dmx(k1=200), absender="B")   # Ausgangslage
    assert fs.abarbeiten(st) == 0
    fs.empfange("artnet", 1, _dmx(k1=100), absender="B")
    fs.empfange("artnet", 1, _dmx(k1=255), absender="A")   # jetzt fremd
    assert fs.abarbeiten(st) == 1
    assert st.playback_engine.get_executor(2).fader_value == pytest.approx(100 / 255)


def test_sacn_hoehere_prioritaet_uebernimmt_sofort():
    st = _state()
    fs = _fs(Zuordnung(quelle="sacn", kanal=1, ziel=ZIEL_FADER, executor=1))
    fs.empfange("sacn", 1, _dmx(k1=10), absender="cid-a", prioritaet=100)
    fs.empfange("sacn", 1, _dmx(k1=20), absender="cid-a", prioritaet=100)
    fs.empfange("sacn", 1, _dmx(k1=99), absender="cid-b", prioritaet=50)   # niedriger
    fs.empfange("sacn", 1, _dmx(k1=150), absender="cid-c", prioritaet=150)  # uebernimmt
    fs.empfange("sacn", 1, _dmx(k1=30), absender="cid-a", prioritaet=100)   # verworfen
    fs.empfange("sacn", 1, _dmx(k1=160), absender="cid-c", prioritaet=150)
    fs.abarbeiten(st)
    assert st.playback_engine.get_executor(1).fader_value == pytest.approx(160 / 255)
    assert fs.verworfen == 2


def test_sacn_kopf_preview_und_stream_ende_werden_verworfen():
    from src.core.dmx.sacn import _pack_framing
    from src.core.dmx.sacn_input import SACNReceiver
    cid = bytes(range(16))
    normal = _pack_framing(_dmx(k1=1), 7, 1, "t", cid)
    assert SACNReceiver._parse_kopf(normal) == (cid.hex(), 100, False)
    assert SACNReceiver._parse_kopf(_pack_framing(_dmx(), 7, 1, "t", cid, options=0x80))[2]
    assert SACNReceiver._parse_kopf(_pack_framing(_dmx(), 7, 1, "t", cid, options=0x40))[2]
    gefaelscht = bytearray(normal)
    gefaelscht[108] = 180
    assert SACNReceiver._parse_kopf(bytes(gefaelscht))[1] == 180


def test_e2e_artnet_zwei_absender_ueber_loopback(monkeypatch):
    """Zwei Art-Net-Sender (127.0.0.1 und 127.0.0.2) auf demselben
    Universum: nur der erste steuert."""
    from src.core.dmx.artnet import _build_artdmx
    from src.core.dmx.artnet_input import ArtNetReceiver
    port = _freier_port()
    rx = ArtNetReceiver()
    rx.start(host="127.0.0.1", port=port)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    tx1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            tx2.bind(("127.0.0.2", 0))
        except OSError:
            pytest.skip("127.0.0.2 nicht bindbar")
        fs = _fs(Zuordnung(universum=1, kanal=1, ziel=ZIEL_GO, executor=5))
        monkeypatch.setattr(fsm, "_instanz", fs)
        ziel = _Ziel(fs)
        fs.verbinden(artnet_rx=rx, sacn_rx=SimpleNamespace(subscribe=lambda cb: None))
        for i in range(20):
            tx1.sendto(_build_artdmx(0, _dmx(k1=0), i), ("127.0.0.1", port))
            tx2.sendto(_build_artdmx(0, _dmx(k1=255), i), ("127.0.0.1", port))
        assert _warte(lambda: fs.verworfen >= 15)
        time.sleep(0.05)
        st = _state()
        fs.abarbeiten(st)
        assert st.tasten == [] and ziel.n == 0
        tx1.sendto(_build_artdmx(0, _dmx(k1=255), 99), ("127.0.0.1", port))
        assert _warte(lambda: ziel.n >= 1)
        fs.abarbeiten(st)
        assert [(s, b) for s, b, _t in st.tasten] == [(5, "go")]
    finally:
        tx1.close()
        tx2.close()
        rx.stop()


def test_e2e_sacn_preview_steuert_nicht(monkeypatch):
    from src.core.dmx.sacn import _pack_framing
    from src.core.dmx.sacn_input import SACNReceiver
    port = _freier_port()
    rx = SACNReceiver()
    rx.start(universes=[], host="127.0.0.1", port=port)
    if not rx.is_running():
        pytest.skip("UDP-Loopback nicht bindbar")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        fs = _fs(Zuordnung(quelle="sacn", universum=4, kanal=1, ziel=ZIEL_GO, executor=1))
        monkeypatch.setattr(fsm, "_instanz", fs)
        ziel = _Ziel(fs)
        fs.verbinden(artnet_rx=SimpleNamespace(subscribe=lambda cb: None), sacn_rx=rx)
        cid = bytes(16)
        tx.sendto(_pack_framing(_dmx(k1=0), 4, 1, "t", cid), ("127.0.0.1", port))
        for i in range(5):
            tx.sendto(_pack_framing(_dmx(k1=255), 4, 2 + i, "t", cid, options=0x80),
                      ("127.0.0.1", port))
        time.sleep(0.2)
        assert ziel.n == 0
        tx.sendto(_pack_framing(_dmx(k1=255), 4, 9, "t", cid), ("127.0.0.1", port))
        assert _warte(lambda: ziel.n >= 1)
    finally:
        tx.close()
        rx.stop()


def test_art_net_keep_alive_pause_verschluckt_kein_go_und_keinen_fader():
    """Art-Net darf bei unveraenderten Daten bis zu 4 s schweigen. Danach
    darf ein GO bzw. die erste Fader-Bewegung nicht als Ausgangslage
    verschluckt werden."""
    t = [0.0]
    st = _state()
    fs = _fs(Zuordnung(kanal=1, ziel=ZIEL_GO, executor=1),
             Zuordnung(kanal=2, ziel=ZIEL_FADER, executor=2), uhr=lambda: t[0])
    fs.empfange("artnet", 1, _dmx(k1=0, k2=0))
    t[0] = 4.0
    fs.empfange("artnet", 1, _dmx(k1=0, k2=0))      # Keep-Alive
    t[0] = 7.0
    assert fs.empfange("artnet", 1, _dmx(k1=255, k2=200)) == 2
    fs.abarbeiten(st)
    assert len(st.tasten) == 1
    assert st.playback_engine.get_executor(2).fader_value == pytest.approx(200 / 255)
    assert fsm.PAUSE_S > 4.0


def test_schwelle_kleiner_gleich_hysterese_loest_jedesmal_aus():
    st = _state()
    fs = _go_fs(schwelle=10)
    z = fs.konfig.zuordnungen[0]
    assert z.aus_roh() >= 1
    for v in (0, 255, 0, 255, 0, 255):
        fs.empfange("artnet", 1, _dmx(k1=v))
    fs.abarbeiten(st)
    assert len(st.tasten) == 3      # erste 0 = Ausgangslage, dann 3 Flanken
    st2 = _state()
    fs2 = _go_fs(schwelle=1)
    for v in (0, 255, 0, 255, 0, 255, 0, 255):
        fs2.empfange("artnet", 1, _dmx(k1=v))
    fs2.abarbeiten(st2)
    assert len(st2.tasten) == 4


@pytest.mark.parametrize("zeile", [
    {"kanal": 0}, {"kanal": 513}, {"kanal": -5}, {"kanal": "x"}, {"kanal": None},
    {"universum": 0}, {"universum": 40000},
])
def test_ungueltiger_kanal_oder_universum_wird_verworfen_nicht_geklemmt(zeile):
    d = {"quelle": "artnet", "universum": 1, "kanal": 1, "ziel": ZIEL_GO}
    d.update(zeile)
    assert Zuordnung.aus_dict(d) is None
    gut = {"quelle": "artnet", "universum": 1, "kanal": 512, "ziel": ZIEL_GO}
    assert Zuordnung.aus_dict(gut).kanal == 512


def test_kurzpaket_bricht_spaetere_zuordnungen_nicht_ab():
    """Paket mit 10 Kanaelen: Zuordnungen auf 11 und 20 fehlen im Paket,
    Kanal 5 (danach eingetragen) muss trotzdem verarbeitet werden."""
    st = _state()
    fs = _fs(Zuordnung(kanal=11, ziel=ZIEL_GM),
             Zuordnung(kanal=20, ziel=ZIEL_GO),
             Zuordnung(kanal=5, ziel=ZIEL_FADER, executor=3))
    fs.empfange("artnet", 1, bytes(10))
    b = bytearray(10)
    b[4] = 255
    assert fs.empfange("artnet", 1, bytes(b)) == 1
    fs.abarbeiten(st)
    assert st.playback_engine.get_executor(3).fader_value == 1.0


def test_mitschnitt_laesst_fernsteuer_kanaele_aus():
    from types import SimpleNamespace as NS
    from src.core import mitschnitt as M
    par = [NS(channel_number=i, attribute=a, name=a) for i, a in
           enumerate(("intensity", "color_r", "color_g", "color_b"), 1)]
    fx = NS(fid=1, universe=1, address=1, channel_count=4, label="PAR",
            fixture_type="par", fixture_name="", manufacturer_name="",
            protocol="dmx", _kanaele=par)
    puffer = M.Eingangspuffer()
    puffer.melde("artnet", 3, _dmx(k1=255, k2=200, k3=7))
    bild = M.eingangsbild(puffer, lambda p, u: 1,
                          reserviert=lambda p, u: frozenset({1}) if (p, u) == ("artnet", 3)
                          else frozenset())
    assert bild.ausgelassen == {1: frozenset({1})}
    m = M.lies_abbild(bild.abbild, [fx], kanaele_fuer=lambda f: f._kanaele,
                      auslassen=bild.ausgelassen)
    assert m.geraete[0].attribute == {"color_r": 200, "color_g": 7, "color_b": 0}
    # Vorgabe: die App-Fernsteuerung
    fs = _fs(Zuordnung(quelle="artnet", universum=3, kanal=2, ziel=ZIEL_GO))
    import src.core.dmx.fernsteuerung as fsmod
    alt = fsmod._instanz
    fsmod._instanz = fs
    try:
        assert M.eingangsbild(puffer, lambda p, u: 1).ausgelassen == {1: frozenset({2})}
    finally:
        fsmod._instanz = alt

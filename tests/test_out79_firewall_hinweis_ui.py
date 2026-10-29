"""OUT-79: Reiter „DMX-Eingang“ — Empfangsadresse, Vorwarnung vor der
Windows-Abfrage, „seit dem Einschalten kam nichts an“ in den Statuszeilen
und im Mitschnitt-Assistenten. Offscreen, ohne Netz (vorgespielte Empfänger).
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel        # noqa: E402

from src.core.dmx import empfangsadresse as ea                       # noqa: E402
from src.core.dmx import fernsteuerung as fsm                        # noqa: E402
from src.core.dmx.fernsteuerung import Konfig, Zuordnung             # noqa: E402
from src.ui.widgets import dmx_empfang_box as EB                     # noqa: E402

_app = QApplication.instance() or QApplication([])
KARTEN = [{"name": "eth1", "ip": "192.0.2.10"}]


class _Rx:
    def __init__(self, laeuft=False, gestartet_um=None):
        self.laeuft = laeuft
        self.gestartet_um = gestartet_um
        self.letztes_paket_um = None
        self.host = "0.0.0.0"
        self.letzter_fehler = ""
        self.gebunden = []

    def is_running(self):
        return self.laeuft

    def neu_binden(self, wahl):
        if not self.laeuft:
            return False
        self.gebunden.append(wahl)
        return True


@pytest.fixture
def prefs(monkeypatch):
    daten = {}
    monkeypatch.setattr(EB, "_prefs", lambda: dict(daten))
    monkeypatch.setattr(EB, "_prefs_merken", lambda u: daten.update(u))
    return daten


@pytest.fixture
def fenster(monkeypatch):
    gezeigt = []
    monkeypatch.setattr(EB, "_zeige_vorwarnung", lambda p, t: gezeigt.append(t))
    return gezeigt


@pytest.fixture(autouse=True)
def _wahl():
    ea.zuruecksetzen()
    yield
    ea.zuruecksetzen()


def _box(tmp_path, plattform="win32", rx=None, uhr=None, **kw):
    rx = rx if rx is not None else {"artnet": _Rx(), "sacn": _Rx()}
    return EB.EmpfangsBox(pfad=str(tmp_path / "f.json"), karten=KARTEN,
                          empfaenger=rx, sys_platform=plattform,
                          uhr=uhr or (lambda: 0.0), **kw), rx


def test_auswahl_vorgabe_alle_karten(tmp_path, prefs):
    box, _rx = _box(tmp_path)
    daten = [box.combo_adresse.itemData(i) for i in range(box.combo_adresse.count())]
    assert daten == ["", "192.0.2.10", "127.0.0.1"]
    assert box.wahl() == ea.ALLE          # keine Datei -> wie bisher
    assert box.combo_adresse.itemText(2) == "Nur dieser Rechner (127.0.0.1)"


def test_gespeicherte_wahl_wird_gezeigt_auch_fehlende_karte(tmp_path, prefs):
    ea.speichere("127.0.0.1", str(tmp_path / "f.json"))
    box, _ = _box(tmp_path)
    assert box.wahl() == "127.0.0.1"
    ea.speichere("192.0.2.99", str(tmp_path / "f.json"))
    box2, _ = _box(tmp_path)
    assert box2.wahl() == "192.0.2.99"
    assert "derzeit nicht gefunden" in box2.combo_adresse.currentText()


def test_wahl_aendern_speichert_und_bindet_laufende_neu(tmp_path, prefs, fenster):
    pfad = str(tmp_path / "f.json")
    fsm.speichere_konfig(Konfig(aktiv=True, zuordnungen=[Zuordnung()]), pfad)
    rx = {"artnet": _Rx(laeuft=True, gestartet_um=0.0), "sacn": _Rx()}
    box, _ = _box(tmp_path, plattform="linux", rx=rx)
    box.combo_adresse.setCurrentIndex(box.combo_adresse.findData("127.0.0.1"))
    assert rx["artnet"].gebunden == ["127.0.0.1"] and rx["sacn"].gebunden == []
    d = json.loads(open(pfad, encoding="utf-8").read())
    assert d["empfangsadresse"] == "127.0.0.1" and len(d["zuordnungen"]) == 1
    assert ea.aktuelle() == "127.0.0.1"
    assert "neu gestartet" in box.lbl_status.text()
    assert "gespeichert" in box.lbl_status.text()


def test_vorwarnung_unter_windows_genau_einmal(tmp_path, prefs, fenster):
    box, _ = _box(tmp_path, plattform="win32")
    assert box.vorwarnen() is True
    assert fenster and fenster[0].startswith("Windows fragt gleich")
    # Gegenprobe: zweites Mal nicht mehr (auch nach neuem Dialog)
    assert box.vorwarnen() is False
    box2, _ = _box(tmp_path, plattform="win32")
    box2.beim_haken(True)
    assert len(fenster) == 1


def test_keine_vorwarnung_ohne_abfrage(tmp_path, prefs, fenster):
    box, _ = _box(tmp_path, plattform="linux")
    assert box.vorwarnen() is False                      # Linux fragt nie
    box_w, _ = _box(tmp_path, plattform="win32")
    box_w.combo_adresse.setCurrentIndex(box_w.combo_adresse.findData("127.0.0.1"))
    assert box_w.vorwarnen() is False                    # nur dieser Rechner
    box_w.beim_haken(False)                              # Haken weg -> nichts
    assert fenster == []


def test_hinweis_im_reiter_plattformgerecht_und_ausblendbar(tmp_path, prefs, fenster):
    box, _ = _box(tmp_path, plattform="win32")
    assert box.lbl_hinweis.text().startswith("Windows fragt gleich")
    assert not box.lbl_hinweis.isHidden()
    box_l, _ = _box(tmp_path, plattform="linux")
    assert "ufw" in box_l.lbl_hinweis.text()
    box.combo_adresse.setCurrentIndex(box.combo_adresse.findData("127.0.0.1"))
    assert "keine Firewall-Abfrage" in box.lbl_hinweis.text()
    box.hinweis_ausblenden()
    assert box.lbl_hinweis.isHidden() and box.btn_ausblenden.isHidden()
    assert prefs[EB.PREF_AUS] is True
    box3, _ = _box(tmp_path, plattform="win32")
    assert box3.lbl_hinweis.isHidden()                   # bleibt aus


def test_statuszeile_nennt_firewall_nach_frist(tmp_path, prefs):
    uhr = SimpleNamespace(t=0.0)
    rx = {"artnet": _Rx(laeuft=True, gestartet_um=0.0), "sacn": _Rx()}
    box, _ = _box(tmp_path, plattform="win32", rx=rx, uhr=lambda: uhr.t)
    lbl, check = QLabel("Aktiv: U1 -> U1 (HTP)"), QCheckBox()
    check.setChecked(True)
    box.ueberwache(lbl, check, ("artnet",))
    uhr.t = 4.0
    box.pruefen()
    assert lbl.text() == "Aktiv: U1 -> U1 (HTP)"         # Frist läuft noch
    uhr.t = 6.0
    box.pruefen()
    assert lbl.text().startswith("Aktiv: U1 -> U1 (HTP)" + EB.MARKE)
    assert "Firewall" in lbl.text() and "Windows-Sicherheit" in lbl.text()
    # Gegenprobe 1: ein Paket kommt -> Zusatz verschwindet
    rx["artnet"].letztes_paket_um = 6.5
    box.pruefen()
    assert lbl.text() == "Aktiv: U1 -> U1 (HTP)"
    # Gegenprobe 2: Haken aus -> kein Zusatz, auch ohne Pakete
    rx["artnet"].letztes_paket_um = None
    check.setChecked(False)
    box.pruefen()
    assert lbl.text() == "Aktiv: U1 -> U1 (HTP)"


def test_statuszeile_meldet_gescheiterten_start(tmp_path, prefs):
    rx = {"artnet": _Rx(), "sacn": _Rx()}
    rx["sacn"].letzter_fehler = "192.0.2.99:5568 — Cannot assign requested address"
    box, _ = _box(tmp_path, rx=rx)
    lbl, check = QLabel("Aktiv: U1 -> U1 (HTP)"), QCheckBox()
    check.setChecked(True)
    box.ueberwache(lbl, check, ("sacn",))
    box.pruefen()
    assert "konnte nicht starten" in lbl.text()


def test_fernsteuerung_zeile_nutzt_ihre_quellen(tmp_path, prefs, monkeypatch):
    fs = fsm.DmxFernsteuerung()
    fs.konfigurieren(Konfig(aktiv=True, zuordnungen=[Zuordnung(quelle="sacn")]))
    monkeypatch.setattr(fsm, "_instanz", fs)
    rx = {"artnet": _Rx(laeuft=True, gestartet_um=0.0),
          "sacn": _Rx(laeuft=True, gestartet_um=0.0)}
    rx["sacn"].letztes_paket_um = 1.0            # sACN bekommt etwas
    box, _ = _box(tmp_path, rx=rx, uhr=lambda: 10.0)
    lbl, check = QLabel("Aktiv"), QCheckBox()
    check.setChecked(True)
    box.ueberwache(lbl, check)                   # Quellen der Fernsteuerung
    box.pruefen()
    assert lbl.text() == "Aktiv"                 # Art-Net-Stille zählt nicht
    rx["sacn"].letztes_paket_um = None
    box.pruefen()
    assert "Firewall" in lbl.text()


def test_fernsteuerung_uebernehmen_behaelt_empfangsadresse(tmp_path, monkeypatch):
    from src.ui.widgets.dmx_fernsteuerung_box import FernsteuerungBox
    pfad = str(tmp_path / "f.json")
    ea.speichere("127.0.0.1", pfad)
    monkeypatch.setattr(fsm, "_instanz", fsm.DmxFernsteuerung())
    monkeypatch.setattr(fsm, "installiere_qt_wecker", lambda: None)
    box = FernsteuerungBox(pfad=pfad)
    box.zeile_hinzu(Zuordnung())
    box.check_aktiv.setChecked(False)
    box.uebernehmen()
    d = json.loads(open(pfad, encoding="utf-8").read())
    assert d["empfangsadresse"] == "127.0.0.1" and len(d["zuordnungen"]) == 1


def test_ausgabe_dialog_verdrahtet(tmp_path, monkeypatch, prefs, fenster):
    from src.ui.widgets import output_config as oc
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(tmp_path / "u.json"))
    monkeypatch.setattr(EB.nh, "loest_abfrage_aus", lambda host, p=None: True)
    dlg = oc.OutputConfigDialog()
    try:
        box = dlg._empfang_box
        assert isinstance(box, EB.EmpfangsBox)
        from PySide6.QtWidgets import QTabWidget
        tabs = dlg.findChild(QTabWidget)
        i = next(i for i in range(tabs.count())
                 if tabs.tabText(i) in ("DMX Input", "DMX-Eingang"))
        assert tabs.widget(i).isAncestorOf(box)
        # Haken -> Vorwarnung VOR dem Start (Übernehmen nicht gedrückt)
        dlg._check_sacn_in.setChecked(True)
        assert len(fenster) == 1
        dlg._fernsteuerung_box.check_aktiv.setChecked(True)
        assert len(fenster) == 1                         # nur einmal
        ueberwacht = [lbl for lbl, _c, _p in box._ueberwacht]
        assert dlg._lbl_artnet_in_status in ueberwacht
        assert dlg._lbl_sacn_in_status in ueberwacht
        assert dlg._fernsteuerung_box.lbl_status in ueberwacht
    finally:
        dlg.deleteLater()


# ── Mitschnitt-Assistent ──────────────────────────────────────────────────

def test_mitschnitt_status_nennt_firewall(monkeypatch):
    from src.core import mitschnitt as M
    from src.ui.widgets import mitschnitt_dialog as D

    class _MRx(_Rx):
        def subscribe(self, cb):
            pass

        def unsubscribe(self, cb):
            pass

        def merges(self):
            return {1: (1, "HTP")}
    art = _MRx(laeuft=True, gestartet_um=0.0)
    sacn = _MRx(laeuft=True, gestartet_um=None)
    leser = M.EingangsLeser(M.Eingangspuffer(), {M.ARTNET: art, M.SACN: sacn})
    monkeypatch.setattr(D.time, "monotonic", lambda: 100.0)
    ns = SimpleNamespace(_leser=leser)
    ns._firewall_zusatz = lambda p: D.MitschnittDialog._firewall_zusatz(ns, p)
    bild = leser.bild()
    text = D.MitschnittDialog._status_text(ns, M.ARTNET, bild)
    assert "kein Signal" in text and "Firewall" in text
    assert "Seit 100 s" in text
    # Gegenprobe: ein Paket kam an -> kein Firewall-Zusatz
    art.letztes_paket_um = 99.0
    assert "Firewall" not in D.MitschnittDialog._status_text(ns, M.ARTNET, bild)
    # Gegenprobe: Empfänger ohne Zeitstempel (nicht gestartet) -> nichts
    assert "Firewall" not in D.MitschnittDialog._status_text(ns, M.SACN, bild)


# ── Gegenprüfung ──────────────────────────────────────────────────────────

class _ScheiterndRx(_Rx):
    """Läuft, aber der Neustart auf die neue Wahl scheitert (Karte fehlt)."""
    start_gescheitert = False

    def neu_binden(self, wahl):
        self.laeuft = False
        self.start_gescheitert = True
        self.letzter_fehler = f"{wahl}:6454 — WSAEADDRNOTAVAIL"
        return False


def test_gescheiterter_neustart_ist_keine_erfolgsmeldung(tmp_path, prefs, fenster):
    rx = {"artnet": _ScheiterndRx(laeuft=True, gestartet_um=0.0), "sacn": _Rx()}
    box, _ = _box(tmp_path, plattform="win32", rx=rx)
    box.combo_adresse.setCurrentIndex(box.combo_adresse.findData("192.0.2.10"))
    text = box.lbl_status.text()
    assert "neu gestartet" not in text
    assert "Neustart gescheitert" in text and "Art-Net" in text
    assert "WSAEADDRNOTAVAIL" in text


def test_vorwarnung_beim_wechsel_auf_karte_nur_mit_laufendem_empfang(
        tmp_path, prefs, fenster):
    # Gegenprobe zuerst: nichts läuft -> der Wechsel fragt Windows nicht
    box, _ = _box(tmp_path, plattform="win32")
    box.combo_adresse.setCurrentIndex(box.combo_adresse.findData("192.0.2.10"))
    assert fenster == []
    ea.speichere(ea.ALLE, str(tmp_path / "f.json"))
    rx = {"artnet": _Rx(laeuft=True, gestartet_um=0.0), "sacn": _Rx()}
    box2, _ = _box(tmp_path, plattform="win32", rx=rx)
    box2.combo_adresse.setCurrentIndex(box2.combo_adresse.findData("192.0.2.10"))
    assert len(fenster) == 1 and fenster[0].startswith("Windows fragt gleich")


def test_bekannter_fehler_geht_vor_firewall_hinweis(tmp_path, prefs):
    rx = {"artnet": _Rx(laeuft=True, gestartet_um=0.0), "sacn": _Rx()}
    rx["artnet"].letzter_fehler = ea.karte_fehlt_text("192.0.2.10")
    box, _ = _box(tmp_path, plattform="linux", rx=rx, uhr=lambda: 60.0)
    text = box.meldung(("artnet",))
    assert "nicht gefunden" in text and "Firewall" not in text
    # Gegenprobe: ohne Fehler nach der Frist -> Firewall (ufw)
    rx["artnet"].letzter_fehler = ""
    assert "ufw" in box.meldung(("artnet",))


# ── QA-106: ohne Bildschirm haelt die Vorwarnung niemanden an ────────────────

def test_vorwarnung_ohne_bildschirm_oeffnet_kein_fenster(monkeypatch):
    """Unter Windows hing jeder Test, der „…-Eingang aktivieren“ anhakt, im
    modalen Fenster bis in den Timeout. Ohne Bildschirm erreicht es niemanden:
    kein ``QMessageBox`` — mit Bildschirm (sichtbare App) bleibt es."""
    from src.core import qt_plattform
    gezeigt = []
    monkeypatch.setattr(EB.QMessageBox, "information",
                        lambda *a, **k: gezeigt.append(a))
    monkeypatch.setattr(qt_plattform, "ohne_bildschirm", lambda: True)
    EB._zeige_vorwarnung(None, "x")
    assert gezeigt == []
    monkeypatch.setattr(qt_plattform, "ohne_bildschirm", lambda: False)
    EB._zeige_vorwarnung(None, "x")
    assert len(gezeigt) == 1                             # Gegenprobe


def test_haken_unter_windows_haengt_nicht(tmp_path, monkeypatch, prefs):
    """Der Weg aus tests/test_input_reconfigure_cleanup.py unter nachgestelltem
    Windows, OHNE ersetztes Fenster: Haken setzen kehrt zurueck, die Vorwarnung
    gilt als gezeigt (einmal), ein ``QMessageBox`` wird nie gebaut."""
    from src.ui.widgets import output_config as oc
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(tmp_path / "u.json"))
    monkeypatch.setattr(EB.nh, "plattform", lambda p=None: EB.nh.WINDOWS)
    # Aufzeichnen statt pytest.fail: eine Ausnahme im toggled-Slot schluckt Qt.
    fenster = []
    monkeypatch.setattr(EB.QMessageBox, "information",
                        lambda *a, **k: fenster.append(a))
    dlg = oc.OutputConfigDialog()
    try:
        dlg._check_artnet_in.setChecked(True)
        assert prefs.get(EB.PREF_GEZEIGT) is True        # Weg wirklich gegangen
        assert fenster == [], "modales Fenster im Test"
    finally:
        dlg.close()
        dlg.deleteLater()

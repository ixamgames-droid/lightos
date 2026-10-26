"""OSC-06: Dialog „OSC-Zuordnungen & Rückmeldung“ — Laden/Übernehmen,
Learn (Nachricht aus einem Fremd-Thread), Vorlagen, Menüeintrag."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from src.core.osc import osc_zuordnung as oz
from src.core.osc.osc_zuordnung import Konfig, RueckmeldeKonfig, Zuordnung


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app, tmp_path):
    from src.ui.widgets.osc_einstellungen_dialog import OscEinstellungenDialog
    pfad = str(tmp_path / "osc.json")
    oz.speichere_konfig(Konfig(zuordnungen=[
        Zuordnung("/exec/{n}/go", oz.ZIEL_GO)]), pfad)
    dlg = OscEinstellungenDialog(None, pfad=pfad, server_laeuft=True)
    yield dlg, pfad
    oz.get_osc_zuordnung().lerne(None)
    oz.anwenden(Konfig())
    dlg.deleteLater()
    app.processEvents()


def _warte(app, bedingung, s=2.0):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        app.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return False


def test_laden_und_uebernehmen_schreibt_datei(dialog, app):
    dlg, pfad = dialog
    assert dlg.tabelle.rowCount() == 1
    assert dlg.tabelle.cellWidget(0, 0).text() == "/exec/{n}/go"
    dlg.zeile_hinzu(Zuordnung("/Page1/Fader{n}", oz.ZIEL_FADER, versatz=-200,
                              bereich=oz.BEREICH_100))
    dlg.zeile_hinzu(Zuordnung("/a"))
    dlg.tabelle.cellWidget(2, 0).setText("kaputt ohne strich")
    assert dlg.uebernehmen()
    assert "NICHT übernommen" in dlg.lbl_status.text()
    roh = json.load(open(pfad, encoding="utf-8"))
    assert [z["adresse"] for z in roh["zuordnungen"]] == ["/exec/{n}/go", "/Page1/Fader{n}"]
    assert roh["zuordnungen"][1]["versatz"] == -200
    # wirksam im Singleton
    assert len(oz.get_osc_zuordnung().konfig.zuordnungen) == 2
    # die kaputte Zeile bleibt zum Korrigieren stehen
    assert dlg.tabelle.rowCount() == 3


def test_learn_fuellt_zeile_mit_vorschlag(dialog, app):
    dlg, _pfad = dialog
    dlg.tabelle.setCurrentCell(-1, -1)
    dlg.btn_lernen.setChecked(True)
    assert oz.get_osc_zuordnung().lernt
    assert "Warte" in dlg.lbl_status.text()
    t = threading.Thread(target=oz.get_osc_zuordnung().empfange,
                         args=("/Page1/Fader203", (50.0,), "192.0.2.10"))
    t.start()
    t.join()
    assert _warte(app, lambda: dlg.tabelle.rowCount() == 2)
    w = dlg.tabelle.cellWidget
    assert w(1, 0).text() == "/Page1/Fader{n}"
    assert w(1, 1).currentData() == oz.ZIEL_FADER
    assert w(1, 3).value() == -200
    assert w(1, 6).currentData() == oz.BEREICH_100
    assert not dlg.btn_lernen.isChecked()
    assert "192.0.2.10" in dlg.lbl_status.text() and "n = 203" in dlg.lbl_status.text()
    assert not oz.get_osc_zuordnung().lernt


def test_learn_in_gewaehlte_zeile_und_abbrechen(dialog, app):
    dlg, _pfad = dialog
    dlg.tabelle.selectRow(0)
    dlg.btn_lernen.setChecked(True)
    oz.get_osc_zuordnung().empfange("/exec/7/back", ())
    assert _warte(app, lambda: dlg.tabelle.cellWidget(0, 0).text() == "/exec/{n}/back")
    assert dlg.tabelle.cellWidget(0, 1).currentData() == oz.ZIEL_BACK
    assert dlg.tabelle.rowCount() == 1
    dlg.btn_lernen.setChecked(True)
    dlg.btn_lernen.setChecked(False)
    assert not oz.get_osc_zuordnung().lernt


def test_schliessen_beendet_lernen(dialog, app):
    dlg, _pfad = dialog
    dlg.btn_lernen.setChecked(True)
    dlg.reject()
    assert not oz.get_osc_zuordnung().lernt


def test_rueckmeldung_vorlage_und_uebernehmen(dialog, app):
    dlg, pfad = dialog
    dlg.combo_vorlage.setCurrentIndex(dlg.combo_vorlage.findData("grandma3"))
    dlg._vorlage_gewaehlt()
    assert dlg.edit_rm[oz.RM_FADER].text() == "/Page1/Fader{n}"
    assert dlg.spin_rm_versatz.value() == 200
    assert "ungeprüft" in dlg.combo_vorlage.currentText()
    dlg.check_rm.setChecked(True)
    # Netz in Tests nur auf 127.0.0.1 (es wird ohnehin nichts gesendet,
    # solange kein Tick laeuft)
    dlg.edit_ip.setText("127.0.0.1")
    dlg.spin_port.setValue(8000)
    assert dlg.uebernehmen()
    roh = json.load(open(pfad, encoding="utf-8"))["rueckmeldung"]
    assert roh["aktiv"] and roh["ziel_ip"] == "127.0.0.1" and roh["ziel_port"] == 8000
    assert roh["vorlage"] == "grandma3" and roh["bereich"] == oz.BEREICH_100
    assert oz.get_osc_rueckmeldung().aktiv
    dlg.edit_ip.setText("kein.host")
    dlg.uebernehmen()
    assert "Ziel-IP ungültig" in dlg.lbl_status.text()


def test_funktionsfeld_nur_bei_funktionszielen(dialog, app):
    dlg, _ = dialog
    r = dlg.zeile_hinzu(Zuordnung("/s", oz.ZIEL_FKT_START, funktion="Lauflicht"))
    assert dlg.tabelle.cellWidget(r, 5).isEnabled()
    combo = dlg.tabelle.cellWidget(r, 1)
    combo.setCurrentIndex(combo.findData(oz.ZIEL_GM))
    assert not dlg.tabelle.cellWidget(r, 5).isEnabled()
    assert not dlg.tabelle.cellWidget(r, 2).isEnabled()


def test_menueeintrag_und_start_hook_im_hauptfenster():
    quelle = open(os.path.join(os.path.dirname(__file__), "..", "src", "ui",
                               "main_window.py"), encoding="utf-8").read()
    assert '"OSC-Zuordnungen && Rückmeldung…"' in quelle
    assert "osc_zuordnung.beim_start()" in quelle
    # der OSC-Server bleibt opt-in: beim_start startet keinen Server
    import inspect
    assert ".start(" not in inspect.getsource(oz.beim_start)


def test_beim_start_ohne_datei(app, monkeypatch, tmp_path):
    monkeypatch.setenv("LIGHTOS_OSC_ZUORDNUNGEN", str(tmp_path / "fehlt.json"))
    k = oz.beim_start()
    assert k.zuordnungen == [] and not oz.get_osc_rueckmeldung().aktiv
    assert not os.path.exists(tmp_path / "fehlt.json")

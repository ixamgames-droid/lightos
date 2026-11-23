"""OUT-84 + OUT-85 (1)-(3): Universen-Reiter im Ausgabe-Dialog.

* OUT-84: neue Zeile nach dem Loeschen bekommt die naechste FREIE Nummer;
  doppelte Nummern werden beim Speichern abgelehnt (Datei bleibt unveraendert).
* OUT-85 (1): Art-Net und „Matrix verteilen“ lehnen ungueltige IPs ab.
* OUT-85 (2): Schliessen mit ungespeicherten Aenderungen fragt nach.
* OUT-85 (3): Loeschen eines Universums mit gepatchten Geraeten warnt.

Wegwerf-universes.json (tmp_path), kein Netz, Ausgaben sind Attrappen.
Beispiel-IPs nur 192.0.2.x.
"""
import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


class _MB:
    """Ersatz fuer QMessageBox: zeichnet auf, antwortet wie vorgegeben."""
    StandardButton = None
    antwort = None
    meldungen: list = []

    @classmethod
    def warning(cls, *a, **k):
        cls.meldungen.append(("warning",) + tuple(str(x) for x in a[1:3]))

    @classmethod
    def information(cls, *a, **k):
        cls.meldungen.append(("information",) + tuple(str(x) for x in a[1:3]))

    @classmethod
    def critical(cls, *a, **k):
        cls.meldungen.append(("critical",) + tuple(str(x) for x in a[1:3]))

    @classmethod
    def question(cls, *a, **k):
        cls.meldungen.append(("question",) + tuple(str(x) for x in a[1:3]))
        return cls.antwort


@pytest.fixture
def umgebung(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from src.ui.widgets import output_config as oc
    pfad = tmp_path / "universes.json"
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(pfad))
    from src.core.app_state import get_state
    state = get_state()
    om = state.output_manager
    for name in ("add_enttec", "add_sacn", "add_artnet", "add_ddp",
                 "remove_output"):
        if hasattr(om, name):
            monkeypatch.setattr(om, name, lambda *a, **k: None)
    monkeypatch.setattr(state, "apply_output_config", lambda *a, **k: None)
    monkeypatch.setattr(state, "get_patched_fixtures", lambda: [])
    _MB.StandardButton = QMessageBox.StandardButton
    _MB.antwort = QMessageBox.StandardButton.No
    _MB.meldungen = []
    monkeypatch.setattr(oc, "QMessageBox", _MB)
    gebaut = []

    def bauen(zeilen):
        oc._save_universe_config(zeilen)
        d = oc.OutputConfigDialog()
        gebaut.append(d)
        return d

    yield oc, pfad, state, bauen
    for d in gebaut:
        d.hide()
        d.deleteLater()
    from _qt_lifecycle import destroy_all_top_level_widgets
    destroy_all_top_level_widgets(QApplication.instance())


ZWEI = [{"num": 1, "name": "Main", "output": "Disabled", "patch": ""},
        {"num": 2, "name": "WLED", "output": "DDP", "patch": "192.0.2.50"}]


def _num(d, z):
    return d._univ_table.item(z, 0).text()


def _waehle(d, z):
    d._univ_table.clearSelection()
    d._univ_table.selectRow(z)


# ── OUT-84 ──────────────────────────────────────────────────────────────────

def test_neue_zeile_nach_loeschen_bekommt_freie_nummer(umgebung):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    _waehle(d, 0)
    d._univ_delete()
    assert d._univ_table.rowCount() == 1 and _num(d, 0) == "2"
    d._univ_add()
    assert _num(d, 1) == "1"            # vorher: "2" (doppelt)
    d._univ_add()
    assert _num(d, 2) == "3"
    assert d._univ_table.item(2, 1).text() == "Universe 3"


def test_speichern_lehnt_doppelte_nummer_ab_und_ddp_bleibt(umgebung):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    vorher = pfad.read_text(encoding="utf-8")
    d._univ_table.item(0, 0).setText("2")    # von Hand doppelt eingetragen
    assert d._univ_save() is False
    assert pfad.read_text(encoding="utf-8") == vorher
    warn = [m for m in _MB.meldungen if m[0] == "warning"]
    assert warn and "Doppelte" in warn[0][1] and "Zeile 1, 2" in warn[0][2]
    ddp = [r for r in json.loads(vorher) if r["output"] == "DDP"]
    assert ddp and ddp[0]["patch"] == "192.0.2.50"


def test_doppelt_nach_klemmen_wird_auch_abgelehnt(umgebung):
    oc, pfad, state, bauen = umgebung
    d = bauen([{"num": 32, "name": "A", "output": "Disabled", "patch": ""},
               {"num": 31, "name": "B", "output": "DDP", "patch": "192.0.2.51"}])
    vorher = pfad.read_text(encoding="utf-8")
    d._univ_table.item(1, 0).setText("40")    # klemmt auf 32 -> doppelt
    assert d._univ_save() is False
    assert pfad.read_text(encoding="utf-8") == vorher


def test_eindeutige_nummern_werden_gespeichert(umgebung):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    _waehle(d, 0)
    d._univ_delete()
    d._univ_add()
    assert d._univ_save() is True
    rows = json.loads(pfad.read_text(encoding="utf-8"))
    assert sorted(r["num"] for r in rows) == [1, 2]
    assert [r for r in rows if r["num"] == 2][0]["output"] == "DDP"
    info = [m for m in _MB.meldungen if m[0] == "information"]
    assert info and "gespeichert" in info[-1][2]


def test_alte_datei_ohne_neue_felder_laedt(umgebung):
    """Abwaertskompatibel: eine alte universes.json (nur num/output/patch,
    sogar mit doppelter Nummer aus dem alten Fehler) laedt ohne Fehler."""
    oc, pfad, state, bauen = umgebung
    d = bauen([{"num": 2, "output": "Disabled", "patch": ""},
               {"num": 2, "output": "DDP", "patch": "192.0.2.50"}])
    assert d._univ_table.rowCount() == 2
    assert not d.univ_ungespeichert()
    d._univ_add()
    assert _num(d, 2) == "1"


# ── OUT-85 (1): ungueltige IP ───────────────────────────────────────────────

@pytest.mark.parametrize("ip", ["abc", "999.1.1", "192.0.2", "1.2.3.256"])
def test_artnet_lehnt_ungueltige_ip_ab(umgebung, ip):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    vorher = pfad.read_text(encoding="utf-8")
    d._edit_artnet_ip.setText(ip)
    d._check_artnet.setChecked(True)
    d._apply_artnet()
    text = d._lbl_artnet_status.text()
    assert "keine gültige IP" in text and "Aktiv" not in text
    assert pfad.read_text(encoding="utf-8") == vorher


def test_artnet_gueltige_ip_und_leer_weiter_moeglich(umgebung):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    d._spin_artnet_univ.setValue(1)
    d._edit_artnet_ip.setText("192.0.2.10")
    d._check_artnet.setChecked(True)
    d._apply_artnet()
    assert d._lbl_artnet_status.text().startswith("Aktiv → 192.0.2.10")
    d._edit_artnet_ip.setText("")
    d._apply_artnet()
    assert d._lbl_artnet_status.text().startswith("Aktiv → 255.255.255.255")


def test_matrix_verteilen_eintragen_nur_mit_gueltiger_ip():
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    QApplication.instance() or QApplication([])
    from src.ui.widgets import wled_auswahl
    g = {"name": "Matrix", "start": 1, "teile": 1,
         "angaben": {"breite": 16, "hoehe": 16}}
    try:
        dlg = wled_auswahl.MatrixVerteilenDialog([g], "abc")
    except Exception:
        g["angaben"] = {}
        dlg = wled_auswahl.MatrixVerteilenDialog([g], "abc")
    ok = dlg._knoepfe.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    assert "keine gültige IP" in dlg._vorschau.text()
    dlg._ip.setText("192.0.2.50")
    assert ok.isEnabled()
    dlg._ip.setText("999.1.1")
    assert not ok.isEnabled()
    dlg.deleteLater()


# ── OUT-85 (2): Rueckfrage beim Schliessen ──────────────────────────────────

def _warten_bis(bedingung, zeit_s=5.0):
    from PySide6.QtWidgets import QApplication
    ende = time.monotonic() + zeit_s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


def test_schliessen_ohne_aenderung_fragt_nicht(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    gefragt = []
    monkeypatch.setattr(d, "_univ_rueckfrage",
                        lambda: gefragt.append(1) or "zurueck")
    d.show()
    assert _warten_bis(d.isVisible)
    d.accept()
    assert not gefragt and not d.isVisible()


def test_schliessen_mit_aenderung_zurueck_bleibt_offen(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    gefragt = []
    monkeypatch.setattr(d, "_univ_rueckfrage",
                        lambda: gefragt.append(1) or "zurueck")
    d.show()
    assert _warten_bis(d.isVisible)
    d._univ_add()
    assert d.univ_ungespeichert()
    d.accept()                      # „Schließen“
    assert gefragt and d.isVisible()
    d.reject()                      # Esc / Fenster-X
    assert len(gefragt) == 2 and d.isVisible()
    d.close()
    assert len(gefragt) == 3 and d.isVisible()


def test_schliessen_mit_aenderung_speichern(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    monkeypatch.setattr(d, "_univ_rueckfrage", lambda: "speichern")
    d.show()
    assert _warten_bis(d.isVisible)
    d._univ_add()
    d._univ_table.item(2, 3).setText("192.0.2.60")
    d.accept()
    assert not d.isVisible()
    rows = json.loads(pfad.read_text(encoding="utf-8"))
    assert [r["num"] for r in rows] == [1, 2, 3]


def test_schliessen_speichern_scheitert_bleibt_offen(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    monkeypatch.setattr(d, "_univ_rueckfrage", lambda: "speichern")
    d.show()
    assert _warten_bis(d.isVisible)
    d._univ_table.item(0, 0).setText("2")   # doppelt -> nicht gespeichert
    d.accept()
    assert d.isVisible()


def test_schliessen_mit_aenderung_verwerfen(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    d = bauen(ZWEI)
    vorher = pfad.read_text(encoding="utf-8")
    monkeypatch.setattr(d, "_univ_rueckfrage", lambda: "verwerfen")
    d.show()
    assert _warten_bis(d.isVisible)
    d._univ_add()
    d.accept()
    assert not d.isVisible()
    assert pfad.read_text(encoding="utf-8") == vorher


def test_rueckfrage_voreinstellung_ist_zurueck(umgebung, monkeypatch):
    """Die echte Rueckfrage: Voreinstellung und Esc = „Zurück“; Knoepfe im
    Touch-Modus >= 44 px."""
    from PySide6.QtWidgets import QMessageBox
    oc, pfad, state, bauen = umgebung
    monkeypatch.setattr(oc, "QMessageBox", QMessageBox)
    from src.ui.widgets import wled_auswahl
    monkeypatch.setattr(wled_auswahl, "_touch", lambda: True)
    d = bauen(ZWEI)
    gesehen = {}

    def exec_(box):
        gesehen["default"] = box.defaultButton().text()
        gesehen["escape"] = box.escapeButton().text()
        gesehen["hoehen"] = [b.minimumHeight() for b in box.buttons()]
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    assert d._univ_rueckfrage() == "zurueck"
    assert gesehen["default"] == gesehen["escape"] == "Zurück"
    assert min(gesehen["hoehen"]) >= 44


# ── OUT-85 (3): Warnung beim Loeschen ───────────────────────────────────────

class _Geraet:
    def __init__(self, u):
        self.universe = u


def test_loeschen_mit_geraeten_warnt_und_nein_behaelt(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    monkeypatch.setattr(state, "get_patched_fixtures",
                        lambda: [_Geraet(1)] * 14 + [_Geraet(2)])
    d = bauen(ZWEI)
    _waehle(d, 0)
    _MB.antwort = _MB.StandardButton.No
    d._univ_delete()
    frage = [m for m in _MB.meldungen if m[0] == "question"]
    assert frage and "U1: 14 Gerät(e)" in frage[0][2]
    assert d._univ_table.rowCount() == 2
    _MB.antwort = _MB.StandardButton.Yes
    d._univ_delete()
    assert d._univ_table.rowCount() == 1 and _num(d, 0) == "2"


def test_loeschen_ohne_geraete_fragt_nicht(umgebung, monkeypatch):
    oc, pfad, state, bauen = umgebung
    monkeypatch.setattr(state, "get_patched_fixtures", lambda: [_Geraet(1)])
    d = bauen(ZWEI)
    _waehle(d, 1)
    d._univ_delete()
    assert not [m for m in _MB.meldungen if m[0] == "question"]
    assert d._univ_table.rowCount() == 1 and _num(d, 0) == "1"

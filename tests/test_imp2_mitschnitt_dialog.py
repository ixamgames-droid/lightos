"""IMP-2: Mitschnitt-Assistent — der Dialog (offscreen) gegen einen echten
``AppState`` mit eigener Show-Datei und einen vorgespielten Eingang.

Geprüft wird, was am Ende in der Funktionsliste steht, dass der Rundlauf über
den echten Renderer byte-gleich ist und dass der Assistent weder Programmer
noch Ausgabe noch den Eingang anfasst.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtGui import QKeySequence                               # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402
from sqlalchemy import select                                        # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core import mitschnitt as M                                 # noqa: E402
from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins  # noqa: E402
from src.core.database.models import (                               # noqa: E402
    FixtureChannel, FixtureMode, PatchedFixture,
)
from src.core.engine.function import FunctionType                    # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import mitschnitt_dialog as D                    # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Uhr:
    def __init__(self):
        self.t = 500.0

    def __call__(self):
        return self.t

    def vor(self, s):
        self.t += s


class _Rx:
    """Vorgespielter Empfänger — zählt jeden Aufruf, der ein Eingriff wäre."""

    def __init__(self, zuordnung=None, laeuft=True):
        self.cbs = []
        self.zuordnung = dict(zuordnung or {})
        self.laeuft = laeuft
        self.eingriffe = []

    def subscribe(self, cb):
        self.cbs.append(cb)

    def unsubscribe(self, cb):
        self.cbs.remove(cb)

    def is_running(self):
        return self.laeuft

    def merges(self):
        return {k: (v, "HTP") for k, v in self.zuordnung.items()}

    def start(self, *a, **k):
        self.eingriffe.append("start")

    def stop(self, *a, **k):
        self.eingriffe.append("stop")

    def set_merge(self, *a, **k):
        self.eingriffe.append("set_merge")

    def sende(self, universum, daten):
        for cb in list(self.cbs):
            cb(universum, bytes(daten))


def _modus_mit(attribut: str, mindestens: int = 1, max_kanaele: int = 40):
    """(profil_id, modus_name, kanalzahl) eines Bibliotheks-Modus, der
    ``attribut`` mindestens so oft führt."""
    with Session(fdb_engine()) as s:
        for m in s.execute(select(FixtureMode).order_by(FixtureMode.id)).scalars():
            if not (0 < int(m.channel_count or 0) <= max_kanaele):
                continue
            attrs = [c.attribute for c in s.execute(select(FixtureChannel).where(
                FixtureChannel.mode_id == m.id)).scalars()]
            if (attrs.count(attribut) >= mindestens
                    and not any((a or "").startswith("laser_") for a in attrs)):
                return int(m.fixture_id), m.name, int(m.channel_count)
    raise AssertionError(f"Kein Modus mit {mindestens}x {attribut} in der Bibliothek")


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def state(tmp_path, monkeypatch):
    ensure_builtins()
    # Der FunctionManager ist prozessweit EINER — für jeden Test ein frischer,
    # sonst zählt „Mitschnitt N“ über die Tests hinweg weiter.
    import src.core.engine.function_manager as FMod
    monkeypatch.setattr(FMod, "_manager", None)
    stack = get_undo_stack()
    stack.clear()
    st = A.AppState()
    st.open_show(str(tmp_path / "show.db"))
    yield st
    stack.clear()
    try:
        st._show_engine.dispose()
    except Exception:
        pass


def _patche(state, fid, modus, universum, adresse, label, typ="par"):
    pid, name, anzahl = modus
    state.add_fixture(PatchedFixture(
        fid=fid, label=label, fixture_profile_id=pid, mode_name=name,
        universe=universum, address=adresse, channel_count=anzahl,
        fixture_type=typ), undoable=False)
    return anzahl


@pytest.fixture
def rig(state):
    """Ein Gerät mit 16-Bit-Pan, ein Mehrkopf-Gerät — beide in Universum 2."""
    fein = _modus_mit("pan_fine")
    mehr = _modus_mit("color_r", 2)
    n1 = _patche(state, 1, fein, 2, 1, "Kopf")
    n2 = _patche(state, 2, mehr, 2, 100, "Leiste")
    return {"adressen": list(range(1, 1 + n1)) + list(range(100, 100 + n2))}


@pytest.fixture
def aufbau(state):
    uhr = _Uhr()
    art = _Rx({1: 2})                    # Art-Net-Universum 1 -> LightOS 2
    sacn = _Rx({}, laeuft=False)
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=uhr), {M.ARTNET: art, M.SACN: sacn})
    dlg = D.MitschnittDialog(state=state, leser=leser)
    dlg._timer.stop()                    # die Tests rufen aktualisiere() selbst
    return dlg, art, sacn, uhr


def _bild(adressen, wert):
    b = bytearray(512)
    for i, a in enumerate(adressen):
        b[a - 1] = (wert + i * 3) % 256
    return bytes(b)


def _spiele_ruhig(art, uhr, daten):
    art.sende(1, daten)
    uhr.vor(0.6)
    art.sende(1, daten)


# ── Ohne Signal ──────────────────────────────────────────────────────────────

def test_ohne_signal_erklaert_der_knopf_und_legt_nichts_an(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    dlg.aktualisiere()
    assert dlg._btn_festhalten.isEnabled()
    assert dlg._btn_festhalten.toolTip() == D.GRUND_KEIN_SIGNAL
    assert not dlg._lbl_hilfe.isHidden() and "DMX Input" in dlg._lbl_hilfe.text()
    assert "kein Signal" in dlg._lbl_status[M.ARTNET].text()
    assert "Universum 1 → LightOS-Universum 2" in dlg._lbl_status[M.ARTNET].text()
    assert dlg._lbl_status[M.SACN].text() == "sACN: Eingang ist aus."
    assert dlg._lbl_live.text() == "Kein Signal."
    assert dlg.festhalten() is None
    assert D.GRUND_KEIN_SIGNAL in dlg._lbl_meldung.text()
    assert "Art-Net Input aktivieren" in dlg._lbl_meldung.text()
    assert state.function_manager.all() == []
    assert not get_undo_stack().can_undo()


def test_hilfetext_nennt_was_im_einstellungsdialog_wirklich_steht():
    import pathlib
    wurzel = pathlib.Path(__file__).resolve().parents[1] / "src" / "ui"
    ausgabe = (wurzel / "widgets" / "output_config.py").read_text(encoding="utf-8")
    haupt = (wurzel / "main_window.py").read_text(encoding="utf-8")
    for wort in ("DMX Input", "Art-Net Input aktivieren", "sACN Input aktivieren",
                 "Eingehendes Universe", "Merge in Universe", "Übernehmen"):
        assert wort in D.HILFE_EINGANG and wort in ausgabe, wort
    assert '"&Ausgabe"' in haupt and '"Konfigurieren..."' in haupt
    assert "„Ausgabe“ → „Konfigurieren...“" in D.HILFE_EINGANG


def test_ohne_patch_sagt_der_knopf_dass_der_patch_fehlt(state, aufbau):
    dlg, art, sacn, uhr = aufbau
    _spiele_ruhig(art, uhr, bytes([200] * 512))
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_PATCH
    assert state.function_manager.all() == []


# ── Mit Signal ───────────────────────────────────────────────────────────────

def test_signal_status_live_anzeige_und_szene(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    daten = _bild(rig["adressen"], 40)
    _spiele_ruhig(art, uhr, daten)
    for _ in range(6):                   # 12 s lang weiter dasselbe Bild
        uhr.vor(2.0)
        art.sende(1, daten)
    dlg.aktualisiere()
    assert "Signal seit 12 s" in dlg._lbl_status[M.ARTNET].text()
    assert dlg._lbl_hilfe.isHidden()
    assert dlg._lbl_live.text().startswith(
        "2 von 2 gepatchten Geräten bekommen gerade Werte. Das Bild steht ruhig.")
    assert dlg._edit_name.text() == "Mitschnitt 1"

    szene = dlg.festhalten()
    assert szene is not None and szene.name == "Mitschnitt 1"
    assert szene.function_type == FunctionType.Scene
    assert state.function_manager.get(szene.id) is szene
    assert len(szene.values) == len(rig["adressen"])       # Vorgabe: alle Kanäle
    assert dlg._liste.count() == 1
    assert dlg._liste.item(0).text().startswith("Mitschnitt 1 — 2 Geräte")
    assert dlg._edit_name.text() == "Mitschnitt 2"         # zählt hoch
    assert "festgehalten" in dlg._lbl_meldung.text()


def test_rundlauf_ueber_den_echten_renderer_ist_byte_gleich(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    daten = _bild(rig["adressen"], 17)
    _spiele_ruhig(art, uhr, daten)
    szene = dlg.festhalten()
    dlg.fertig()

    vorher_programmer = {k: dict(v) for k, v in state.programmer.items()}
    assert vorher_programmer == {}                          # nichts hineingeschrieben
    state.function_manager.start(szene.id)
    for _ in range(3):
        state._render_frame(0.03)
    aus = state.universes[2].get_all()
    for adresse in rig["adressen"]:
        assert aus[adresse - 1] == daten[adresse - 1], adresse


def test_laufende_ueberblendung_wird_abgelehnt_bis_das_bild_steht(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    for i in range(5):                                      # das Bild läuft
        art.sende(1, _bild(rig["adressen"], 10 + i))
        uhr.vor(0.1)
    dlg.aktualisiere()
    assert "Das Bild ändert sich noch." in dlg._lbl_live.text()
    assert dlg._btn_festhalten.toolTip() == D.GRUND_UNRUHIG
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_UNRUHIG
    assert state.function_manager.all() == []
    uhr.vor(0.5)                                            # jetzt steht es
    assert dlg.festhalten() is not None
    # Ausdrücklich erlaubt: auch ein laufendes Bild festhalten.
    art.sende(1, _bild(rig["adressen"], 99))
    assert dlg.festhalten() is None
    dlg._check_unruhig.setChecked(True)
    szene = dlg.festhalten()
    assert szene is not None and "nicht ruhig" in dlg._lbl_meldung.text()


def test_leertaste_haelt_fest(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    assert dlg._kuerzel.key() == QKeySequence(Qt.Key.Key_Space)
    # Gehaltene Leertaste darf nicht Szene um Szene anlegen.
    assert not dlg._kuerzel.autoRepeat()
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 5))
    dlg._kuerzel.activated.emit()
    assert [f.name for f in state.function_manager.all()] == ["Mitschnitt 1"]


def test_namen_ueberspringen_vorhandene_und_eigener_name_gilt(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    state.function_manager.new_scene("Mitschnitt 2")
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 5))
    assert dlg.festhalten().name == "Mitschnitt 1"
    assert dlg._edit_name.text() == "Mitschnitt 3"
    dlg._edit_name.setText("Rot voll")
    assert dlg.festhalten().name == "Rot voll"
    assert dlg._edit_name.text() == "Mitschnitt 3"


# ── Chaser, Entfernen, Rückgängig ────────────────────────────────────────────

def _drei_szenen(dlg, art, uhr, adressen):
    ids = []
    for wert in (10, 20, 30):
        _spiele_ruhig(art, uhr, _bild(adressen, wert))
        ids.append(dlg.festhalten().id)
    return ids


def test_chaser_aus_drei_szenen_reihenfolge_schrittzeit_rueckgaengig(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    stack = get_undo_stack()
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])
    assert [dlg._liste.item(i).data(Qt.ItemDataRole.UserRole) for i in range(3)] == ids
    assert [fm.get(i).name for i in ids] == ["Mitschnitt 1", "Mitschnitt 2", "Mitschnitt 3"]
    erster = rig["adressen"][0]
    assert [fm.get(i).get_value(1, 1) for i in ids] == [10, 20, 30]
    assert erster == 1

    dlg._check_chaser.setChecked(True)
    dlg._spin_schritt.setValue(2.5)
    dlg.fertig()
    assert dlg.result() == D.QDialog.DialogCode.Accepted
    chaser = dlg.chaser
    assert chaser is not None and chaser.function_type == FunctionType.Chaser
    assert chaser.name == "Mitschnitt Chaser 1"
    assert [s.function_id for s in chaser.steps] == ids
    assert [s.hold for s in chaser.steps] == [2.5, 2.5, 2.5]
    assert len(fm.all()) == 4

    # Vier Schritte: erst der Chaser, dann jede Szene einzeln (jüngste zuerst).
    assert stack.undo() and fm.get(chaser.id) is None and len(fm.all()) == 3
    assert stack.undo() and fm.get(ids[2]) is None
    assert stack.undo() and fm.get(ids[1]) is None
    assert stack.undo() and fm.all() == []
    assert not stack.can_undo()
    for _ in range(4):
        assert stack.redo()
    assert [s.function_id for s in fm.get(chaser.id).steps] == ids


def test_ohne_haken_entsteht_kein_chaser(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    _drei_szenen(dlg, art, uhr, rig["adressen"])
    dlg.fertig()
    assert dlg.chaser is None
    assert len(state.function_manager.by_type(FunctionType.Chaser)) == 0
    assert len(state.function_manager.all()) == 3


def test_entfernen_loescht_die_szene_und_laesst_sie_aus_dem_chaser(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])
    dlg._liste.setCurrentRow(1)
    dlg.entferne_markierte()
    assert fm.get(ids[1]) is None and dlg._liste.count() == 2
    assert dlg.szenen_ids == [ids[0], ids[2]]
    dlg._check_chaser.setChecked(True)
    dlg.fertig()
    assert [s.function_id for s in dlg.chaser.steps] == [ids[0], ids[2]]
    stack = get_undo_stack()
    assert stack.undo()                                     # Chaser
    assert stack.undo() and fm.get(ids[1]) is not None      # Entfernen zurück


# ── Auswahl und Laser ────────────────────────────────────────────────────────

def test_auswahl_vorgabe_und_die_beiden_anderen_regeln(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    assert dlg._combo_auswahl.currentData() == M.AUSWAHL_ALLE
    assert [dlg._combo_auswahl.itemText(i) for i in range(3)] == [
        D.AUSWAHL_TEXT[a] for a in M.AUSWAHLEN]
    b = bytearray(512)
    b[99] = 200                                             # nur Adresse 100
    dlg._combo_auswahl.setCurrentIndex(M.AUSWAHLEN.index(M.AUSWAHL_UNGLEICH_NULL))
    _spiele_ruhig(art, uhr, b)
    szene = dlg.festhalten()
    assert [(v.fixture_id, v.channel, v.value) for v in szene.values] == [(2, 1, 200)]
    # „geändert“: Bezug ist das zuletzt festgehaltene Bild.
    dlg._combo_auswahl.setCurrentIndex(M.AUSWAHLEN.index(M.AUSWAHL_GEAENDERT))
    b[100] = 50
    _spiele_ruhig(art, uhr, b)
    szene = dlg.festhalten()
    assert [(v.fixture_id, v.channel, v.value) for v in szene.values] == [(2, 2, 50)]


def test_laser_wird_ausgelassen_mit_hinweis_und_nur_mit_haken_aufgenommen(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    _patche(state, 9, _modus_mit("color_r"), 2, 300, "Laser hinten", typ="laser")
    b = bytearray(_bild(rig["adressen"], 5))
    b[299] = 222
    _spiele_ruhig(art, uhr, b)
    dlg.aktualisiere()
    assert not dlg._check_laser.isChecked()
    assert not dlg._lbl_laser.isHidden()
    assert "Laser werden ausgelassen" in dlg._lbl_laser.text()
    assert "Gerade ausgelassen: 1." in dlg._lbl_laser.text()
    szene = dlg.festhalten()
    assert all(v.fixture_id != 9 for v in szene.values)
    assert "1 Laser ausgelassen" in dlg._lbl_meldung.text()
    dlg._check_laser.setChecked(True)
    szene = dlg.festhalten()
    assert szene.get_value(9, 1) == 222


# ── Der Assistent liest nur ──────────────────────────────────────────────────

def test_assistent_fasst_eingang_programmer_und_ausgabe_nicht_an(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    vorher = {u: uni.get_all() for u, uni in state.universes.items()}
    laufend = set(state.function_manager.running_ids())
    _drei_szenen(dlg, art, uhr, rig["adressen"])
    dlg._check_chaser.setChecked(True)
    dlg.fertig()
    assert art.eingriffe == [] and sacn.eingriffe == []     # kein start/stop/set_merge
    assert art.cbs == [] and sacn.cbs == []                 # wieder abgemeldet
    assert state.programmer == {}
    assert set(state.function_manager.running_ids()) == laufend   # nichts gestartet
    assert {u: uni.get_all() for u, uni in state.universes.items()} == vorher


def test_schliessen_ueber_das_fenster_meldet_den_zuhoerer_ab(state, aufbau):
    dlg, art, sacn, uhr = aufbau
    assert len(art.cbs) == 1
    dlg.reject()
    assert art.cbs == [] and not dlg._timer.isActive()


def test_nicht_zugeordnetes_universum_wird_genannt(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    art.sende(1, bytes(512))
    art.sende(7, bytes([255] * 512))
    dlg.aktualisiere()
    text = dlg._lbl_status[M.ARTNET].text()
    assert "nicht zugeordnet" in text and "Universum 7" in text
    assert "ein Universum je Protokoll" in text


# ── Erreichbar im Programmer, Reiter „Assistent“ ─────────────────────────────

def test_knopf_im_programmer_oeffnet_den_assistenten(state, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from src.ui.views.programmer_view import ProgrammerView
    monkeypatch.setattr(A, "_state", state, raising=False)
    geoeffnet = []
    monkeypatch.setattr(D.MitschnittDialog, "exec",
                        lambda self: geoeffnet.append(self) or 0)
    view = ProgrammerView()
    try:
        knopf = view._btn_mitschnitt
        assert isinstance(knopf, QPushButton)
        assert knopf.text() == D.TITEL + "..."
        assert knopf.toolTip()
        knopf.click()
        assert len(geoeffnet) == 1 and isinstance(geoeffnet[0], D.MitschnittDialog)
        geoeffnet[0].reject()
    finally:
        view.deleteLater()

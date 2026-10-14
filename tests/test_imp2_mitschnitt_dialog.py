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
    # Die Meldung bleibt kurz und zeigt auf die Wegbeschreibung, die dabei
    # eingeblendet wird (sie kann eingeklappt gewesen sein).
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_SIGNAL + " " + D.VERWEIS_HILFE
    assert not dlg._lbl_hilfe.isHidden() and dlg._btn_hilfe.isChecked()
    assert "Art-Net Input aktivieren" in dlg._lbl_hilfe.text()
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


def test_rueckgaengig_von_entfernen_bringt_die_szene_in_liste_und_chaser(
        state, rig, aufbau):
    """Codex-Review #1085 (CDX-59): Rueckgaengig holte die Szene in die Show
    zurueck, in der Liste und im spaeter erzeugten Chaser fehlte sie aber."""
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])
    dlg._liste.setCurrentRow(1)
    dlg.entferne_markierte()
    assert dlg.szenen_ids == [ids[0], ids[2]] and dlg._liste.count() == 2
    assert get_undo_stack().undo() and fm.get(ids[1]) is not None
    dlg.aktualisiere()
    assert dlg.szenen_ids == ids, "wieder an ihrem Platz"
    assert [dlg._liste.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(dlg._liste.count())] == ids
    # Wiederholen nimmt sie wieder heraus.
    assert get_undo_stack().redo() and fm.get(ids[1]) is None
    dlg.aktualisiere()
    assert dlg.szenen_ids == [ids[0], ids[2]]
    assert get_undo_stack().undo()
    dlg._check_chaser.setChecked(True)
    dlg.fertig()
    assert [s.function_id for s in dlg.chaser.steps] == ids


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


# ── Erreichbar im Programmer, Reiter „Assistent“ — nicht modal, eine Instanz ──

import pathlib                                                       # noqa: E402

import shiboken6                                                     # noqa: E402
from PySide6.QtCore import QPoint, QRect, QSize                           # noqa: E402
from PySide6.QtGui import QAction                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QAbstractButton, QAbstractSpinBox, QComboBox, QGroupBox, QLabel, QLineEdit,
    QListWidget, QWidget,
)

from src.core.sync import SyncEvent                                  # noqa: E402

_WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _verarbeite(n=4):
    for _ in range(n):
        _app.processEvents()


@pytest.fixture
def vorgespielter_eingang(monkeypatch):
    """Der Assistent, den die App selbst baut, bekommt vorgespielte Empfänger."""
    echt = M.EingangsLeser
    empfaenger = {M.ARTNET: _Rx({1: 2}), M.SACN: _Rx({}, laeuft=False)}
    monkeypatch.setattr(
        M, "EingangsLeser",
        lambda *a, **k: echt(M.Eingangspuffer(), dict(empfaenger)))
    yield empfaenger
    D._vergiss()


def test_knopf_im_programmer_oeffnet_den_assistenten_nicht_modal_und_nur_einmal(
        state, monkeypatch, vorgespielter_eingang):
    from PySide6.QtWidgets import QPushButton
    from src.ui.views.programmer_view import ProgrammerView
    monkeypatch.setattr(A, "_state", state, raising=False)
    view = ProgrammerView()
    try:
        knopf = view._btn_mitschnitt
        assert isinstance(knopf, QPushButton)
        assert knopf.text() == D.TITEL + "..."
        assert knopf.toolTip()
        assert D.offener_assistent() is None
        knopf.click()                    # kehrt zurück: kein exec(), keine Sperre
        dlg = D.offener_assistent()
        assert isinstance(dlg, D.MitschnittDialog)
        assert dlg.isVisible() and not dlg.isModal()
        assert dlg.windowModality() == Qt.WindowModality.NonModal
        # Kind des Hauptfensters: bleibt darüber und geht mit ihm.
        assert dlg.parentWidget() == view.window() and dlg.isWindow()
        # Zweiter Klick: dieselbe Instanz, kein zweites Fenster.
        knopf.click()
        assert D.offener_assistent() is dlg
        assert len([w for w in _app.topLevelWidgets()
                    if isinstance(w, D.MitschnittDialog)]) == 1
        # Nach „Fertig“ ist er weg, der nächste Klick baut einen neuen.
        dlg.fertig()
        assert D.offener_assistent() is None
        knopf.click()
        neu = D.offener_assistent()
        assert neu is not None and neu is not dlg
        neu.reject()
        assert D.offener_assistent() is None
    finally:
        view.deleteLater()
    quelle = (_WURZEL / "src" / "ui" / "views" / "programmer_view.py").read_text(
        encoding="utf-8")
    assert "zeige_assistent(self)" in quelle
    assert "MitschnittDialog(self).exec()" not in quelle


# ── Leertaste: im Assistenten festhalten, im Hauptfenster weiter GO ──────────

def _hauptfenster_mit_go():
    """Ein Fenster, das die Leertaste so belegt wie das Hauptfenster: eine
    QAction mit Kürzel „Space“ (Vorgabe-Kontext: nur im eigenen Fenster)."""
    haupt = QWidget()
    haupt.resize(400, 300)
    gedrueckt = []
    act = QAction("GO", haupt)
    act.setShortcut("Space")
    act.triggered.connect(lambda *_: gedrueckt.append("go"))
    haupt.addAction(act)
    return haupt, gedrueckt


def _aktiviere(fenster):
    fenster.activateWindow()
    _verarbeite()
    if _app.activeWindow() is not fenster:
        pytest.skip("Die Plattform aktiviert hier keine Fenster.")


def test_leertaste_ist_im_hauptfenster_go_und_nur_im_assistenten_festhalten(
        state, rig):
    haupt, gedrueckt = _hauptfenster_mit_go()
    uhr = _Uhr()
    art = _Rx({1: 2})
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=uhr),
                            {M.ARTNET: art, M.SACN: _Rx({}, laeuft=False)})
    haupt.show()
    dlg = D.MitschnittDialog(haupt, state=state, leser=leser)
    dlg._timer.stop()
    dlg.show()
    _verarbeite()
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 5))
    fm = state.function_manager

    # Hauptfenster aktiv, Assistent offen daneben: Leertaste = GO, keine Szene.
    _aktiviere(haupt)
    QTest.keyClick(haupt, Qt.Key.Key_Space)
    _verarbeite()
    assert gedrueckt == ["go"]
    assert fm.all() == []

    # Assistent aktiv: Leertaste hält fest, GO bleibt aus.
    _aktiviere(dlg)
    dlg._btn_festhalten.setFocus()
    QTest.keyClick(dlg, Qt.Key.Key_Space)
    _verarbeite()
    assert [f.name for f in fm.all()] == ["Mitschnitt 1"]
    assert gedrueckt == ["go"]

    # Im Namensfeld schreibt die Leertaste ein Leerzeichen.
    dlg._edit_name.setFocus()
    dlg._edit_name.setText("Rot")
    QTest.keyClick(dlg._edit_name, Qt.Key.Key_Space)
    _verarbeite()
    assert dlg._edit_name.text() == "Rot " and len(fm.all()) == 1

    # Zurück im Hauptfenster geht GO wieder — auch nach dem Schließen.
    _aktiviere(haupt)
    QTest.keyClick(haupt, Qt.Key.Key_Space)
    dlg.fertig()
    _verarbeite()
    QTest.keyClick(haupt, Qt.Key.Key_Space)
    _verarbeite()
    assert gedrueckt == ["go", "go", "go"] and len(fm.all()) == 1


def test_go_im_hauptfenster_und_kuerzel_im_assistenten_gelten_je_fuer_ihr_fenster():
    """Die beiden Belegungen der Leertaste kommen sich nur dann nicht in die
    Quere, wenn KEINE von beiden anwendungsweit gilt."""
    haupt = (_WURZEL / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
    i = haupt.index('act_go = QAction("GO", self)')
    block = haupt[i:haupt.index("act_back = QAction", i)]
    assert 'act_go.setShortcut("Space")' in block
    assert "self.addAction(act_go)" in block
    assert "ApplicationShortcut" not in block and "setShortcutContext" not in block
    dialog = (_WURZEL / "src" / "ui" / "widgets" / "mitschnitt_dialog.py").read_text(
        encoding="utf-8")
    assert "self._kuerzel.setContext(Qt.ShortcutContext.WindowShortcut)" in dialog
    assert "ApplicationShortcut" not in dialog


# ── Show oder Patch ändern sich, während der Assistent offen ist ─────────────

def test_show_wechsel_leert_die_liste_und_sagt_es(state, rig, aufbau, tmp_path):
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])
    dlg._check_chaser.setChecked(True)
    state.open_show(str(tmp_path / "zweite.db"))         # meldet SHOW_LOADED
    assert dlg._lage.show_gewechselt
    # „Fertig“ gleich danach: kein Chaser aus der alten Liste, Fenster bleibt.
    dlg.fertig()
    assert dlg.chaser is None and not dlg._abgebaut
    assert dlg._lbl_meldung.text() == D.MELDUNG_SHOW_GEWECHSELT
    assert dlg._liste.count() == 0 and dlg.szenen_ids == []
    assert len(fm.by_type(FunctionType.Chaser)) == 0
    # „Entfernen“ hat nichts mehr, woran es sich vergreifen könnte.
    dlg.entferne_markierte()
    assert [fm.get(i) is not None for i in ids] == [True, True, True]
    # Weiterarbeiten geht: die neue Show hat keinen Patch, das wird gesagt.
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 60))
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_PATCH
    dlg.fertig()
    assert dlg.chaser is None and dlg._abgebaut


def test_fremde_funktion_mit_derselben_nummer_wird_nie_angefasst(state, rig, aufbau):
    """Auch ohne Meldung vom Sync-Bus: steht unter der Nummer einer
    festgehaltenen Szene inzwischen eine ANDERE Funktion (neue Show), kommt
    sie weder in den Chaser noch wird sie von „Entfernen“ gelöscht."""
    dlg, art, sacn, uhr = aufbau
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])
    fremd = fm.new_scene("Fremde Szene")
    del fm._functions[fremd.id]
    fremd.id = ids[0]
    fm._functions[ids[0]] = fremd
    dlg.aktualisiere()
    assert [dlg._liste.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(dlg._liste.count())] == ids[1:]
    dlg._check_chaser.setChecked(True)
    dlg.fertig()
    assert [s.function_id for s in dlg.chaser.steps] == ids[1:]
    assert fm.get(ids[0]) is fremd


def test_patch_aenderung_gilt_ab_dem_naechsten_festhalten(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    daten = _bild(rig["adressen"], 30)
    _spiele_ruhig(art, uhr, daten)
    erste = dlg.festhalten()
    assert {v.fixture_id for v in erste.values} == {1, 2}
    state.remove_fixture(1, undoable=False)              # Gerät 1 fliegt raus
    assert dlg._lage.patch_geaendert
    dlg.aktualisiere()
    assert dlg._lbl_meldung.text() == D.MELDUNG_PATCH_GEAENDERT
    assert dlg._lbl_live.text().startswith("1 von 1 gepatchten Geräten")
    _spiele_ruhig(art, uhr, daten)
    zweite = dlg.festhalten()
    # Kein veraltetes Gerät in der neuen Szene; die alte bleibt, wie sie war.
    assert {v.fixture_id for v in zweite.values} == {2}
    assert dlg._liste.count() == 2 and dlg.szenen_ids == [erste.id, zweite.id]
    # Alles weg: der Assistent sagt es, statt eine leere Szene anzulegen.
    state.remove_fixture(2, undoable=False)
    _spiele_ruhig(art, uhr, daten)
    assert dlg.festhalten() is None
    assert dlg._lbl_meldung.text() == D.GRUND_KEIN_PATCH


def test_rueckgaengig_im_hauptfenster_zieht_die_liste_nach(state, rig, aufbau):
    dlg, art, sacn, uhr = aufbau
    stack = get_undo_stack()
    fm = state.function_manager
    ids = _drei_szenen(dlg, art, uhr, rig["adressen"])

    def gezeigt():
        return [dlg._liste.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(dlg._liste.count())]

    assert stack.undo() and fm.get(ids[2]) is None
    dlg.aktualisiere()
    assert gezeigt() == ids[:2]
    assert stack.redo() and fm.get(ids[2]) is not None
    dlg.aktualisiere()
    assert gezeigt() == ids
    assert stack.undo()
    dlg._check_chaser.setChecked(True)
    dlg.fertig()
    assert [s.function_id for s in dlg.chaser.steps] == ids[:2]


# ── Abbau: nach dem Schließen läuft nichts mehr in das Fenster ───────────────

def _lauscht(lage) -> bool:
    from src.core.sync import get_sync
    sync = get_sync()
    return (lage._bei_show in sync._subscribers[SyncEvent.SHOW_LOADED]
            or lage._bei_patch in sync._subscribers[SyncEvent.PATCH_CHANGED])


@pytest.mark.parametrize("weg", ["fertig", "reject", "close"])
def test_schliessen_raeumt_zeitgeber_und_verbindungen_ab(state, rig, aufbau, weg):
    dlg, art, sacn, uhr = aufbau
    dlg._timer.start()
    dlg.show()
    _verarbeite()
    assert dlg._timer.isActive() and len(art.cbs) == 1 and len(sacn.cbs) == 1
    assert dlg._lage.verbunden and _lauscht(dlg._lage)
    getattr(dlg, weg)()
    _verarbeite()
    assert not dlg.isVisible()
    assert not dlg._timer.isActive() and not dlg._sicht_timer.isActive()
    assert not dlg._markierung_timer.isActive()
    assert art.cbs == [] and sacn.cbs == []
    assert not dlg._lage.verbunden and not _lauscht(dlg._lage)
    assert not dlg._kuerzel.isEnabled()
    # Nachzügler dürfen nichts mehr bewirken.
    state.sync.emit(SyncEvent.SHOW_LOADED, None)
    state.sync.emit(SyncEvent.PATCH_CHANGED, None)
    assert not dlg._lage.show_gewechselt and not dlg._lage.patch_geaendert
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 9))
    dlg._kuerzel.activated.emit()
    dlg.aktualisiere()
    assert dlg.festhalten() is None
    dlg.entferne_markierte()
    dlg.fertig()
    assert state.function_manager.all() == []
    dlg.close()                                         # zweimal schadet nicht


def test_zerstoeren_ohne_schliessen_meldet_trotzdem_ab(state, rig):
    """Das Hauptfenster reißt den Assistenten beim Beenden mit — ohne
    closeEvent. Danach darf kein Bus und kein Empfänger mehr hineinrufen."""
    haupt = QWidget()
    art, sacn = _Rx({1: 2}), _Rx({}, laeuft=False)
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=_Uhr()),
                            {M.ARTNET: art, M.SACN: sacn})
    dlg = D.MitschnittDialog(haupt, state=state, leser=leser)
    lage = dlg._lage
    haupt.show()
    dlg.show()
    _verarbeite()
    assert len(art.cbs) == 1 and _lauscht(lage)
    shiboken6.delete(haupt)
    assert not shiboken6.isValid(dlg)
    assert art.cbs == [] and sacn.cbs == [] and not _lauscht(lage)
    state.sync.emit(SyncEvent.SHOW_LOADED, None)
    state.sync.emit(SyncEvent.PATCH_CHANGED, None)
    _verarbeite()


def test_assistent_schliesst_mit_dem_hauptfenster(state, rig):
    haupt = QWidget()
    art = _Rx({1: 2})
    leser = M.EingangsLeser(M.Eingangspuffer(uhr=_Uhr()),
                            {M.ARTNET: art, M.SACN: _Rx({}, laeuft=False)})
    dlg = D.MitschnittDialog(haupt, state=state, leser=leser)
    haupt.show()
    dlg.show()
    _verarbeite()
    assert dlg.isVisible() and len(art.cbs) == 1
    haupt.close()
    _verarbeite()
    assert not dlg.isVisible() and dlg._abgebaut
    assert art.cbs == [] and not dlg._timer.isActive()


# ── Größe: bei jeder Bildschirmhöhe ab 600 px liegt nichts übereinander ──────
#
# Befunde der Sichtproben: (1) der Dialog ging mit 560 x 620 px auf, brauchte
# aber rund 900 px — Namensfeld 10 px hoch, Meldung über dem Knopf. (2) Auf
# einem 800 px hohen Bildschirm wurde er auf 760 px gekappt; Liste, „Entfernen“
# und die Chaser-Zeile lagen außerhalb, auf 1366 x 768 rollte der Inhalt rund
# 190 px.
#
# Deshalb liegt jetzt FEST unter dem Rollbereich, was man bei jeder Szene
# braucht. Geprüft wird die ECHTE Startgröße (kein resize() von Hand) bei den
# verfügbaren Flächen aus dem Auftrag, mit und ohne Signal, mit der längsten
# Meldung.

_FLAECHEN = {"1920x1040": QRect(0, 0, 1920, 1040),
             "1366x728": QRect(0, 0, 1366, 728),
             "1280x680": QRect(0, 0, 1280, 680),
             "1024x600": QRect(0, 0, 1024, 600)}
_BLATT = (QLabel, QAbstractButton, QAbstractSpinBox, QComboBox, QLineEdit,
          QListWidget)


def _stelle_bildschirm(monkeypatch, flaeche):
    from src.ui.widgets import dialog_groesse as DG
    monkeypatch.setattr(DG, "verfuegbare_flaeche", lambda _w=None: flaeche)
    return flaeche


@pytest.fixture(params=sorted(_FLAECHEN))
def bildschirm(request, monkeypatch):
    return _stelle_bildschirm(monkeypatch, _FLAECHEN[request.param])


def _zeige(dlg):
    dlg.show()
    _verarbeite()
    return dlg


def _blaetter(wurzel, bezug):
    """Sichtbare Bedienteile und Texte unter ``wurzel`` (ohne Qt-Innenleben
    wie Rollbalken oder das Eingabefeld im Drehfeld)."""
    aus = []
    for w in wurzel.findChildren(QWidget):
        if not isinstance(w, _BLATT) or not w.isVisibleTo(bezug):
            continue
        eltern = w.parentWidget()
        if isinstance(eltern, (QAbstractSpinBox, QComboBox, QListWidget)) \
                or (w.objectName() or "").startswith("qt_"):
            continue
        aus.append(w)
    return aus


def _name(w):
    text = getattr(w, "text", lambda: "")() if not isinstance(w, QListWidget) else ""
    return f"{type(w).__name__}({text[:30]!r})"


def _lage_in(bezug, w) -> QRect:
    return QRect(w.mapTo(bezug, QPoint(0, 0)), w.size())


def _pruefe_teile(teile, bezug, rahmen=()):
    """Kein Teil kleiner als sein Mindestmaß, kein umbrochener Text
    abgeschnitten, kein Paar übereinander, nichts außerhalb von ``bezug``.
    ``rahmen`` (Gruppenrahmen) werden nur auf ihr Mindestmaß geprüft — sie
    umschließen ihre Teile ja."""
    for w in list(teile) + list(rahmen):
        # Wie Qt rechnet: ein ausdrücklich gesetztes Mindestmaß gilt an
        # Stelle des Vorschlags (die Liste: drei Zeilen statt 70 px).
        vorschlag = w.minimumSizeHint()
        mindest = QSize(w.minimumWidth() or vorschlag.width(),
                        w.minimumHeight() or vorschlag.height())
        assert w.width() >= mindest.width(), (_name(w), w.size(), mindest)
        assert w.height() >= mindest.height(), (_name(w), w.size(), mindest)
        if isinstance(w, QLabel) and w.wordWrap() and w.text():
            assert w.height() >= w.heightForWidth(w.width()), (
                _name(w), w.size(), w.heightForWidth(w.width()))
    lagen = [(_name(w), _lage_in(bezug, w)) for w in teile]
    for name, lage in lagen:
        assert bezug.rect().contains(lage), (name, lage, bezug.rect())
    for i, (na, a) in enumerate(lagen):
        for nb, b in lagen[i + 1:]:
            assert not a.intersects(b), (na, a, nb, b)


def _feste_teile(dlg):
    return [w for w in _blaetter(dlg, dlg) if not dlg._rollbereich.isAncestorOf(w)]


def _sichtbare_zeilen(dlg) -> int:
    liste = dlg._liste
    leer = liste.count() == 0
    if leer:
        liste.addItem("X")
    hoehe = liste.sizeHintForRow(0)
    if leer:
        liste.clear()
    return liste.viewport().height() // hoehe


def _pruefe_fenster(dlg, flaeche):
    """Das ganze Fenster: Größe, fester Teil, Rollbereich."""
    from src.ui.widgets import dialog_groesse as DG
    grenze = DG.groesste_fenstergroesse(dlg)
    assert dlg.width() <= grenze.width() and dlg.height() <= grenze.height(), (
        dlg.size(), grenze)
    assert dlg.height() <= flaeche.height()

    # 1) Der feste Teil: ganz im Fenster, ohne Rollen, kein Paar übereinander.
    fest = _feste_teile(dlg)
    pflicht = [dlg._edit_name, dlg._btn_festhalten, dlg._lbl_meldung, dlg._liste,
               dlg._btn_entfernen, dlg._check_chaser, dlg._spin_schritt,
               dlg._btn_fertig]
    for w in pflicht:
        assert w in fest, _name(w)
        assert not dlg._rollbereich.isAncestorOf(w), _name(w)
    _pruefe_teile(fest, dlg, [b for b in dlg.findChildren(QGroupBox)
                              if not dlg._rollbereich.isAncestorOf(b)])
    rollbereich = _lage_in(dlg, dlg._rollbereich)
    assert dlg.rect().contains(rollbereich)
    for w in fest:
        assert not rollbereich.intersects(_lage_in(dlg, w)), (_name(w), rollbereich)
    # Reihenfolge von oben nach unten, wie man sie bedient.
    oben = [_lage_in(dlg, w) for w in (dlg._rollbereich, dlg._btn_festhalten,
                                       dlg._lbl_meldung, dlg._liste,
                                       dlg._btn_entfernen, dlg._check_chaser,
                                       dlg._btn_fertig)]
    for a, b in zip(oben, oben[1:]):
        assert b.top() > a.bottom(), (a, b)
    assert dlg._edit_name.height() >= dlg._edit_name.sizeHint().height()
    assert _sichtbare_zeilen(dlg) >= D.MINDESTZEILEN, dlg._liste.size()

    # 2) Der Rollbereich: der Inhalt ist nie kleiner als sein Bedarf (was
    #    nicht passt, rollt), nie breiter als die Sicht, und innen liegt
    #    nichts übereinander.
    inhalt = _blaetter(dlg._inhalt, dlg._inhalt)
    assert len(inhalt) >= 7, [_name(w) for w in inhalt]
    _pruefe_teile(inhalt, dlg._inhalt, dlg._inhalt.findChildren(QGroupBox))
    balken = dlg._rollbereich.verticalScrollBar()
    sicht = dlg._rollbereich.viewport().height()
    assert sicht >= D.ROLLBEREICH_MINDESTHOEHE - 2 * dlg._rollbereich.frameWidth()
    assert dlg._inhalt.height() >= sicht
    assert balken.maximum() == max(0, dlg._inhalt.height() - sicht)
    assert dlg._rollbereich.horizontalScrollBar().maximum() == 0


def _laengste_meldung(dlg):
    texte = [D.GRUND_KEIN_SIGNAL + " " + D.VERWEIS_HILFE, D.GRUND_KEIN_PATCH,
             D.GRUND_UNRUHIG, D.GRUND_KEINE_WERTE, D.MELDUNG_SHOW_GEWECHSELT,
             D.MELDUNG_PATCH_GEAENDERT]
    return max(texte, key=len)


def test_startgroesse_ohne_signal_bei_jeder_flaeche(state, rig, aufbau, bildschirm):
    dlg, art, sacn, uhr = aufbau
    _zeige(dlg)
    assert not dlg._btn_hilfe.isHidden()
    _pruefe_fenster(dlg, bildschirm)
    if bildschirm.height() >= 1040:
        # Großer Bildschirm: alles da, nichts rollt, die Liste hat fünf Zeilen.
        assert dlg._btn_hilfe.isChecked() and not dlg._lbl_hilfe.isHidden()
        assert dlg._rollbereich.verticalScrollBar().maximum() == 0
        assert _sichtbare_zeilen(dlg) >= D.LISTENZEILEN
        assert dlg.width() >= D.STARTBREITE
    if bildschirm.height() <= 680:
        # Wenig Höhe: die Wegbeschreibung startet eingeklappt …
        assert not dlg._btn_hilfe.isChecked() and dlg._lbl_hilfe.isHidden()
        assert dlg._btn_hilfe.text() == D.TEXT_HILFE_ZEIGEN
    # … und „Festhalten“ ohne Signal blendet sie ein. Die Meldung steht fest
    # unter dem Knopf, nichts verschiebt sich über etwas anderes.
    assert dlg.festhalten() is None
    _verarbeite()
    assert dlg._lbl_meldung.text().startswith(D.GRUND_KEIN_SIGNAL)
    assert dlg._btn_hilfe.isChecked() and not dlg._lbl_hilfe.isHidden()
    assert dlg._btn_hilfe.text() == D.TEXT_HILFE_WEG
    _pruefe_fenster(dlg, bildschirm)
    sicht = dlg._rollbereich.viewport().rect()
    hilfe = QRect(dlg._lbl_hilfe.mapTo(dlg._rollbereich.viewport(), QPoint(0, 0)),
                  dlg._lbl_hilfe.size())
    assert sicht.intersects(hilfe), (hilfe, sicht)
    # Einklappen geht von Hand wieder.
    dlg._btn_hilfe.click()
    _verarbeite()
    assert dlg._lbl_hilfe.isHidden() and dlg._btn_hilfe.text() == D.TEXT_HILFE_ZEIGEN
    _pruefe_fenster(dlg, bildschirm)
    # Die längste Meldung, die der Assistent kennt.
    dlg._melde(_laengste_meldung(dlg), fehler=True)
    _verarbeite()
    _pruefe_fenster(dlg, bildschirm)


def test_startgroesse_mit_signal_bei_jeder_flaeche(state, rig, aufbau, bildschirm):
    dlg, art, sacn, uhr = aufbau
    _spiele_ruhig(art, uhr, _bild(rig["adressen"], 40))
    dlg.aktualisiere()
    _zeige(dlg)
    assert dlg._lbl_hilfe.isHidden() and dlg._btn_hilfe.isHidden()
    _pruefe_fenster(dlg, bildschirm)
    for wert in (40, 90, 140, 190, 240):
        _spiele_ruhig(art, uhr, _bild(rig["adressen"], wert))
        assert dlg.festhalten() is not None
    _verarbeite()
    assert dlg._liste.count() == 5 and "festgehalten" in dlg._lbl_meldung.text()
    _pruefe_fenster(dlg, bildschirm)
    # Laser-Hinweis weg, Haken gesetzt, dann die längste Meldung.
    dlg._check_laser.setChecked(True)
    dlg._check_unruhig.setChecked(True)
    dlg.aktualisiere()
    dlg._melde(_laengste_meldung(dlg), fehler=True)
    _verarbeite()
    _pruefe_fenster(dlg, bildschirm)


@pytest.mark.parametrize("hoehe", [600, 620, 660, 700, 760, 800, 860, 940])
def test_jede_hoehe_ab_600_zeigt_den_festen_teil_ohne_rollen(
        state, rig, aufbau, monkeypatch, hoehe):
    dlg, art, sacn, uhr = aufbau
    flaeche = _stelle_bildschirm(monkeypatch, QRect(0, 0, 1280, hoehe))
    _zeige(dlg)
    _pruefe_fenster(dlg, flaeche)
    assert dlg.festhalten() is None                     # blendet die Hilfe ein
    _verarbeite()
    _pruefe_fenster(dlg, flaeche)


def test_fenster_laesst_sich_nicht_kleiner_ziehen_als_der_feste_teil(
        state, rig, aufbau, monkeypatch):
    dlg, art, sacn, uhr = aufbau
    flaeche = _stelle_bildschirm(monkeypatch, _FLAECHEN["1366x728"])
    _zeige(dlg)
    dlg._melde(_laengste_meldung(dlg), fehler=True)
    for breite, hoehe in ((D.MINDESTBREITE, 100), (300, 300), (520, 250)):
        dlg.resize(breite, hoehe)
        _verarbeite()
        assert dlg.width() >= D.MINDESTBREITE and dlg.height() > hoehe
        assert dlg.size() == dlg.size().expandedTo(dlg.minimumSize())
        _pruefe_fenster(dlg, flaeche)
    assert dlg.minimumWidth() <= 520
    # … und passt trotzdem auf den kleinsten Bildschirm aus dem Auftrag.
    assert dlg.minimumHeight() <= 600 - 60


def test_startgroesse_folgt_dem_inhalt_und_nicht_einer_festen_zahl(
        state, rig, aufbau, monkeypatch):
    dlg, art, sacn, uhr = aufbau
    _stelle_bildschirm(monkeypatch, QRect(0, 0, 2560, 1400))
    _zeige(dlg)
    # Auf einem großen Bildschirm passt alles ohne Rollen, und das Fenster
    # ist genau so hoch wie sein Bedarf — nicht bildschirmhoch.
    assert dlg._rollbereich.verticalScrollBar().maximum() == 0
    assert dlg.width() >= D.STARTBREITE
    assert dlg.height() == dlg.startbedarf(dlg.width()) < 1000
    assert dlg._rollbereich.height() <= dlg._inhalt.height() + 2


def test_eigene_groesse_vor_dem_zeigen_bleibt(state, rig, aufbau, bildschirm):
    dlg, art, sacn, uhr = aufbau
    dlg.resize(560, 520)
    _zeige(dlg)
    assert (dlg.width(), dlg.height()) == (560, 520)
    assert dlg._lbl_hilfe.isHidden()     # klein heißt: einklappen und rollen
    _pruefe_fenster(dlg, bildschirm)

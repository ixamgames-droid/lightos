"""ENG-41: Ueberschneidungs-Hinweis kennt die ausschliessenden Tasten-Haken.

Drei Regeln stoppen beim Start einer Taste andere Funktionen
(``VCButton._start_function_group``): „Andere Funktionen stoppen (nur diese
aktiv)“, „Andere Effekte auf denselben Geräten stoppen“ und ein gemeinsamer
Live-Edit-Slot. Stoppen sich zwei Tasten GEGENSEITIG, laufen sie nie zusammen
— dann kein gelber Hinweis (wie in einer Exklusiv-Gruppe). Stoppt nur eine
die andere, bleibt der Hinweis und benennt das Stoppen. Ausserdem zieht die
Zeile nach, wenn ein ANDERES Bedienelement umbelegt wird.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QLabel,
                               QLineEdit, QVBoxLayout, QWidget)

from src.core.app_state import get_state
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import MatrixStyle
from src.core.undo import get_undo_stack
from src.ui.virtualconsole.target_list_editor import TargetListEditor
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_canvas import VCCanvas

HINTERGRUND = [9001, 9002, 9003, 9004]
HIMMEL = [9005, 9006, 9007, 9008]
NAME = "vcUeberschneidungsHinweis"
EXKLUSIV = "Andere Funktionen stoppen (nur diese aktiv)"
SOLO = "Andere Effekte auf denselben Geräten stoppen"


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fm():
    _app()
    manager = get_function_manager()
    manager.stop_all()
    vorher = {f.id for f in manager.all()}
    get_undo_stack().clear()
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if f.id not in vorher:
            manager.remove(f.id)
    get_undo_stack().clear()


@pytest.fixture
def flaeche(fm, monkeypatch):
    monkeypatch.setattr(
        get_state(), "list_fixture_groups",
        lambda: [{"name": "Hintergrund", "fids": list(HINTERGRUND)},
                 {"name": "Himmel", "fids": list(HIMMEL)}], raising=False)
    c = VCCanvas()
    c.resize(800, 600)
    yield c
    c.close()
    c.deleteLater()
    _app().processEvents()


def _matrix(fm, name, geraete):
    m = fm.new_rgb_matrix(name)
    m.style = MatrixStyle.DIMMER
    m.drive_intensity = False
    m.fixture_grid = list(geraete)
    m.priority = 0
    return m


def _taste(eltern, funktion, name="Taste", exklusiv=False, solo=False, slot=""):
    b = VCButton(name, parent=eltern)
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = funktion.id
    b.exclusive = exklusiv
    b.solo_fixtures = solo
    b.edit_slot = slot
    return b


def _eigenschaften(taste):
    """Der Eigenschaften-Bereich wie im Inspector (jede Aenderung sofort)."""
    wirt = QWidget()
    lay = QVBoxLayout(wirt)
    koerper = taste.build_inspector_body(wirt)
    lay.addWidget(koerper)
    wirt.resize(420, 700)
    wirt.show()
    _app().processEvents()
    zeile = koerper.findChild(QLabel, NAME)
    assert zeile is not None
    return wirt, zeile


def _haken(wirt, text):
    return next(cb for cb in wirt.findChildren(QCheckBox) if cb.text() == text)


def _zu(wirt):
    wirt.close()
    wirt.deleteLater()
    _app().processEvents()


def _zwei(fm, flaeche, a=None, b=None):
    """Zwei Tasten mit Dimmer-Effekten auf denselben Geraeten; die Eigenschaften
    der zweiten sind offen."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    andere = _taste(flaeche, lauf, "Lauflicht", **(a or {}))
    taste = _taste(flaeche, puls, "Puls", **(b or {}))
    wirt, zeile = _eigenschaften(taste)
    return lauf, puls, andere, taste, wirt, zeile


# ── gegenseitiges Stoppen: kein Hinweis ─────────────────────────────────────

@pytest.mark.parametrize("regel", [
    {"exklusiv": True},
    {"solo": True},
    {"slot": "MX"},
], ids=["nur_diese_aktiv", "gleiche_geraete", "gleicher_live_edit_slot"])
def test_gegenseitig_stoppende_tasten_zeigen_keinen_hinweis(fm, flaeche, regel):
    *_r, wirt, zeile = _zwei(fm, flaeche, regel, regel)
    try:
        assert zeile.text() == "" and not zeile.isVisible(), zeile.text()
    finally:
        _zu(wirt)


def test_gemischte_regeln_stoppen_sich_auch_gegenseitig(fm, flaeche):
    """„Nur diese aktiv“ an der einen, „gleiche Geräte“ an der anderen: jede
    stoppt beim Start die andere."""
    *_r, wirt, zeile = _zwei(fm, flaeche, {"exklusiv": True}, {"solo": True})
    try:
        assert zeile.text() == ""
    finally:
        _zu(wirt)


def test_verschiedene_live_edit_slots_schliessen_nichts_aus(fm, flaeche):
    *_r, wirt, zeile = _zwei(fm, flaeche, {"slot": "MH"}, {"slot": "MX"})
    try:
        assert "steuern beide den Dimmer" in zeile.text()
        assert "stoppt" not in zeile.text()
    finally:
        _zu(wirt)


def test_exklusiv_mit_live_edit_slot_greift_nicht(fm, flaeche):
    """Mit Live-Edit-Slot stoppt die Taste nur das Ziel ihres Slots — der Haken
    „nur diese aktiv“ wirkt dann nicht (``elif`` in _start_function_group)."""
    *_r, wirt, zeile = _zwei(fm, flaeche, {"exklusiv": True},
                             {"exklusiv": True, "slot": "MX"})
    try:
        assert zeile.text() == (
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt gestartet "
            "wurde. Die Taste mit „Lauflicht HG“ stoppt beim Start „Puls HG“ — "
            "erst wenn „Puls HG“ danach startet, laufen beide.")
    finally:
        _zu(wirt)


# ── einseitiges Stoppen: Hinweis bleibt und sagt es ─────────────────────────

def test_einseitiger_haken_an_dieser_taste_wird_benannt(fm, flaeche):
    *_r, wirt, zeile = _zwei(fm, flaeche, None, {"solo": True})
    try:
        assert zeile.text() == (
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt gestartet "
            "wurde. Beim Start stoppt diese Taste „Lauflicht HG“ — erst wenn "
            "„Lauflicht HG“ danach startet, laufen beide.")
    finally:
        _zu(wirt)


def test_einseitiger_haken_an_der_anderen_taste_wird_benannt(fm, flaeche):
    *_r, wirt, zeile = _zwei(fm, flaeche, {"exklusiv": True}, None)
    try:
        assert ("Die Taste mit „Lauflicht HG“ stoppt beim Start „Puls HG“"
                in zeile.text())
    finally:
        _zu(wirt)


def test_eigener_haken_zaehlt_aus_dem_feld_und_zieht_sofort_nach(fm, flaeche):
    """Die andere Taste hat „gleiche Geräte“; setzt man denselben Haken an
    dieser Taste, verschwindet der Hinweis sofort (ohne Neuoeffnen)."""
    *_r, wirt, zeile = _zwei(fm, flaeche, {"solo": True}, None)
    try:
        assert "stoppt beim Start" in zeile.text()
        _haken(wirt, SOLO).setChecked(True)
        _app().processEvents()
        assert zeile.text() == ""
        _haken(wirt, SOLO).setChecked(False)
        _app().processEvents()
        assert "stoppt beim Start" in zeile.text()
    finally:
        _zu(wirt)


def test_modaler_dialog_liest_die_haken_aus_den_feldern(fm, flaeche, monkeypatch):
    """Im OK/Abbrechen-Dialog ist noch nichts uebernommen — der Hinweis muss
    trotzdem den gerade gesetzten Haken kennen."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, lauf, exklusiv=True)
    taste = _taste(flaeche, puls)
    gesehen = []

    def _exec(dlg):
        zeile = dlg.findChild(QLabel, NAME)
        gesehen.append(zeile.text())
        _haken(dlg, EXKLUSIV).setChecked(True)
        zeile.neu_berechnen()
        gesehen.append(zeile.text())
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", _exec)
    taste._open_properties()
    assert "stoppt beim Start" in gesehen[0]
    assert gesehen[1] == ""
    assert taste.exclusive is False, "Abbrechen uebernimmt nichts"


def test_funktion_auf_zwei_tasten_braucht_den_ausschluss_an_beiden(fm, flaeche):
    """Liegt die andere Funktion zusaetzlich auf einer Taste ohne Haken, kann
    sie dort weiterlaufen — der Hinweis bleibt."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, lauf, exklusiv=True)
    _taste(flaeche, lauf, "Lauflicht 2")
    wirt, zeile = _eigenschaften(_taste(flaeche, puls, exklusiv=True))
    try:
        assert "steuern beide den Dimmer" in zeile.text()
    finally:
        _zu(wirt)


# ── Nachziehen bei fremder Umbelegung ───────────────────────────────────────

def test_zeile_zieht_nach_wenn_andere_taste_im_dialog_umbelegt_wird(
        fm, flaeche, monkeypatch):
    # Vorher anlegen: eine NEUE Funktion meldet FUNCTION_CHANGED und loeste
    # die Rechnung sonst schon selbst aus.
    himmel = _matrix(fm, "Himmel", HIMMEL)
    lauf, puls, andere, taste, wirt, zeile = _zwei(fm, flaeche)
    try:
        _app().processEvents()
        assert "steuern beide den Dimmer" in zeile.text()

        def _exec(dlg):
            dlg.findChild(TargetListEditor).set_targets([himmel.id])
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(QDialog, "exec", _exec)
        andere._open_properties()
        assert andere.function_id == himmel.id, "Vorbedingung: umbelegt"
        _app().processEvents()
        assert zeile.text() == "" and not zeile.isVisible()
    finally:
        _zu(wirt)


def test_zeile_zieht_nach_wenn_andere_taste_ihren_haken_bekommt(fm, flaeche):
    """Die andere Taste wird im Inspector live geaendert (Haken „gleiche
    Geräte“) — die offene Zeile dieser Taste (ebenfalls mit Haken) wird leer."""
    lauf, puls, andere, taste, wirt, zeile = _zwei(fm, flaeche, None, {"solo": True})
    wirt2, _z2 = _eigenschaften(andere)
    try:
        assert "Beim Start stoppt diese Taste" in zeile.text()
        _haken(wirt2, SOLO).setChecked(True)
        assert andere.solo_fixtures is True
        _app().processEvents()
        assert zeile.text() == ""
    finally:
        _zu(wirt2)
        _zu(wirt)


def test_zeile_zieht_nach_bei_drop_und_loeschen(fm, flaeche):
    lauf, puls, andere, taste, wirt, zeile = _zwei(fm, flaeche, None, {"slot": "MX"})
    try:
        assert "steuern beide" in zeile.text()
        # Live-Edit-Slot an der anderen Taste (Feld im eigenen Inspector)
        wirt2, _z2 = _eigenschaften(andere)
        slot = next(e for e in wirt2.findChildren(QLineEdit)
                    if e.text() == "" and "Live-Edit-Slot" in e.toolTip())
        slot.setText("MX")
        _app().processEvents()
        assert zeile.text() == "", "gleicher Slot: stoppen sich gegenseitig"
        _zu(wirt2)
        slot = None
        andere.edit_slot = ""
        # Neue Taste per Drop (umbelegen der Konsole ohne Dialog)
        flaeche.apply_drop(function_id=lauf.id, target=None, pos=None)
        _app().processEvents()
        assert "steuern beide" in zeile.text()
        # alle anderen Tasten loeschen -> keine Ueberschneidung mehr
        for w in [w for w in flaeche.findChildren(VCButton) if w is not taste]:
            flaeche._remove_widget(w)
        _app().processEvents()
        assert zeile.text() == ""
    finally:
        _zu(wirt)


# ── Gegenpruefung: die andere Taste startet die eigene Funktion selbst mit ───

@pytest.mark.parametrize("regel", [
    {"exklusiv": True},
    {"solo": True},
], ids=["nur_diese_aktiv", "gleiche_geraete"])
def test_andere_taste_mit_der_eigenen_funktion_stoppt_sie_nicht(fm, flaeche, regel):
    """Die andere Taste startet „Puls HG“ UND „Lauflicht HG“. Ihr Haken stoppt
    „Puls HG“ nicht — sie startet es ja selbst mit (``stop_all`` vor dem Start
    bzw. ``stop_others_sharing_fixture_group`` schuetzt die eigenen Ziele).
    Nach ihrem Druck laufen beide: der Hinweis darf nicht verschwinden."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    andere = _taste(flaeche, puls, "Beide", **regel)
    andere.function_ids = [lauf.id]
    assert andere._all_function_ids() == [puls.id, lauf.id]
    wirt, zeile = _eigenschaften(_taste(flaeche, puls, "Puls", **regel))
    try:
        assert "steuern beide den Dimmer" in zeile.text(), zeile.text()
        # und am echten Druck: nach der anderen Taste laufen beide
        andere._start_function_group(get_state(), andere._all_function_ids())
        assert fm.is_running(puls.id) and fm.is_running(lauf.id)
    finally:
        _zu(wirt)


def test_zeile_zieht_nach_wenn_live_regler_angelegt_werden(fm, flaeche):
    """„Live-Regler anlegen“ legt Effekt-Fader mit festem Ziel an — die zaehlen
    (ENG-39) und muessen die offene Zeile nachziehen lassen."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    wirt, zeile = _eigenschaften(_taste(flaeche, puls, "Puls"))
    try:
        _app().processEvents()
        assert zeile.text() == ""
        from src.core.engine import effect_live
        schluessel = [s.key for s in effect_live.list_params(lauf.id)][:1]
        assert schluessel, "Vorbedingung: Matrix hat Live-Parameter"
        flaeche.add_live_controls(lauf.id, schluessel, [])
        _app().processEvents()
        assert "steuern beide den Dimmer" in zeile.text(), zeile.text()
    finally:
        _zu(wirt)

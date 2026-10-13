"""ENG-39 Oberflaeche: gelbe Hinweiszeile in den Eigenschaften einer Taste.

Die Zeile erscheint bei einer Ueberschneidung und verschwindet ohne, zieht bei
einem Stufenwechsel nach, schreibt hoechstens drei Treffer aus — und aendert
dabei nichts an der Taste oder an der Show. Dazu die Leistungsmessung
(200 Funktionen, 100 Tasten) und der Tooltip in der Ansicht „Prioritäten“.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout

from src.core.app_state import get_state
from src.core.engine import stufen
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import MatrixStyle
from src.core.undo import get_undo_stack
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
from src.ui.virtualconsole.vc_canvas import VCCanvas
from src.ui.virtualconsole.vc_frame import VCFrame
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
from src.ui.widgets import ueberschneidung_hinweis as H
from src.ui.widgets.stufe_auswahl import setze_stufen

STROBE = stufen.stufe_fuer_schluessel("strobe_blinder").zahl
HINTERGRUND = [9001, 9002, 9003, 9004]
HIMMEL = [9005, 9006, 9007, 9008]
NAME = "vcUeberschneidungsHinweis"


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
    """Eine leere Virtual Console; die Show kennt die Gruppe „Hintergrund“."""
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


def _matrix(fm, name, geraete, stil=MatrixStyle.DIMMER, stufe=0):
    m = fm.new_rgb_matrix(name)
    m.style = stil
    m.drive_intensity = False
    m.fixture_grid = list(geraete)
    m.priority = stufe
    return m


def _taste(eltern, funktion=None, name="Taste", aktion=ButtonAction.FUNCTION_TOGGLE):
    b = VCButton(name, parent=eltern)
    b.action = aktion
    b.function_id = funktion.id if funktion is not None else None
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
    assert zeile is not None, "die Hinweiszeile gehoert in jede Tasten-Eigenschaft"
    return wirt, zeile


def _zu(wirt):
    wirt.close()
    wirt.deleteLater()
    _app().processEvents()


# ── erscheint / verschwindet ─────────────────────────────────────────────────

def test_zeile_erscheint_bei_ueberschneidung_mit_dem_satz_des_konzepts(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, lauf, "Lauflicht")
    wirt, zeile = _eigenschaften(_taste(flaeche, puls, "Puls"))
    try:
        assert zeile.isVisible()
        assert zeile.text() == (
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt gestartet wurde.")
        assert zeile.wordWrap() and "background:#3a3214" in zeile.styleSheet()
        assert "ändert und sperrt nichts" in zeile.toolTip()
    finally:
        _zu(wirt)


def test_keine_zeile_ohne_treffer(fm, flaeche):
    """Andere Geraete, Farbe gegen Dimmer, oder die andere Funktion liegt auf
    gar keiner Taste — jeweils nichts zu sehen."""
    lauf = _matrix(fm, "Lauflicht Himmel", HIMMEL)
    farbe = _matrix(fm, "Farbe HG", HINTERGRUND, MatrixStyle.RGB)
    _matrix(fm, "Ohne Taste", HINTERGRUND)              # nur in der Show
    _taste(flaeche, lauf)
    _taste(flaeche, farbe)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    wirt, zeile = _eigenschaften(_taste(flaeche, puls))
    try:
        assert zeile.text() == "" and not zeile.isVisible()
    finally:
        _zu(wirt)


def test_taste_ohne_funktion_und_andere_aktionen_zeigen_nichts(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, lauf)
    for taste in (_taste(flaeche, None),
                  _taste(flaeche, puls, aktion=ButtonAction.EFFECT_ACTION),
                  _taste(flaeche, None, aktion=ButtonAction.BLACKOUT)):
        wirt, zeile = _eigenschaften(taste)
        try:
            assert zeile.text() == "" and not zeile.isVisible(), taste.action
        finally:
            _zu(wirt)


def test_zeile_folgt_der_funktionswahl_der_taste(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    himmel = _matrix(fm, "Puls Himmel", HIMMEL)
    _taste(flaeche, lauf)
    taste = _taste(flaeche, himmel)
    wirt = QWidget()
    try:
        S = taste._build_settings(wirt, live=False)
        zeile = S["ueberschneidungs_hinweis"]
        sichtbar = []
        S["update_visibility"](lambda w, an: sichtbar.append((w, an)), None)
        assert (zeile, False) in sichtbar
        editor = next(w for label, w in S["sections"][0][4] if label == "Ziele:")
        editor.set_targets([puls.id])
        editor.changed.emit()
        _app().processEvents()
        assert "„Lauflicht HG“" in zeile.text()
        assert sichtbar[-1] == (zeile, True), "Zeile wird eingeblendet"
        assert taste.function_id == himmel.id, "im Dialog noch nichts uebernommen"
        editor.set_targets([himmel.id])
        editor.changed.emit()
        _app().processEvents()
        assert zeile.text() == "" and sichtbar[-1] == (zeile, False)
    finally:
        _zu(wirt)


# ── Stufenwechsel ────────────────────────────────────────────────────────────

def test_zeile_zieht_bei_stufenwechsel_nach(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    blinder = _matrix(fm, "Blinder", HINTERGRUND)
    _taste(flaeche, blinder)
    wirt, zeile = _eigenschaften(_taste(flaeche, lauf))
    try:
        assert zeile.text().endswith("es gewinnt, wer zuletzt gestartet wurde.")
        setze_stufen([(blinder, STROBE)])
        _app().processEvents()
        assert zeile.text().endswith(
            "— „Blinder“ liegt zwei Stufen höher und gewinnt.")
        setze_stufen([(lauf, stufen.stufe_fuer_schluessel("notfall").zahl)])
        _app().processEvents()
        assert zeile.text().endswith(
            "— diese Taste liegt eine Stufe höher und gewinnt.")
        assert zeile.isVisible()
    finally:
        _zu(wirt)


# ── hoechstens drei + Rest ───────────────────────────────────────────────────

def test_hoechstens_drei_treffer_ausgeschrieben_dann_rest(fm, flaeche):
    ich = _matrix(fm, "Ich", HINTERGRUND)
    for i in range(5):
        _taste(flaeche, _matrix(fm, f"Effekt {i}", HINTERGRUND), f"T{i}")
    wirt, zeile = _eigenschaften(_taste(flaeche, ich))
    try:
        zeilen = zeile.text().split("\n")
        assert len(zeilen) == 4 and zeilen[-1] == (
            "… und 2 weitere Überschneidungen: bei 2 entscheidet, wer zuletzt "
            "gestartet wurde.")
        assert len(zeile.treffer) == 5
    finally:
        _zu(wirt)


# ── gegen Fehlalarme ─────────────────────────────────────────────────────────

def test_tasten_im_selben_solo_rahmen_zaehlen_nicht(fm, flaeche):
    """Im Solo-Rahmen ist immer nur eine Taste aktiv — kein Hinweis. Dieselbe
    Funktion auf einer Taste AUSSERHALB des Rahmens zaehlt wieder."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    rahmen = VCFrame(parent=flaeche)
    rahmen.set_solo(True)
    _taste(rahmen, lauf)
    taste = _taste(rahmen, puls)
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == []
    _taste(flaeche, lauf, "draussen")
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == [lauf.id]
    rahmen.set_solo(False)
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == [lauf.id]


def test_tasten_und_jeder_effekt_fader_zaehlen(fm, flaeche):
    """Entscheidung der Leitung (Nachtrag): ein Effekt-Fader zaehlt IMMER mit
    — frueher nur mit dem Haken „bei 0 wirklich stoppen“. Ohne den Haken
    laeuft sein Effekt bei 0 weiter; das merkt sich ``haltende_ids``."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    tempo = _matrix(fm, "Tempo-Ziel", HINTERGRUND)
    _taste(flaeche, lauf, aktion=ButtonAction.FUNCTION_FLASH)
    _taste(flaeche, tempo, aktion=ButtonAction.EFFECT_ACTION)   # startet nichts
    fader = VCSlider("Fader", parent=flaeche)
    fader.mode = SliderMode.EFFECT_INTENSITY
    fader.function_id = puls.id
    regler = VCSlider("Master", parent=flaeche)
    regler.mode = SliderMode.GROUP_DIMMER
    regler.function_id = tempo.id
    regler.effect_autostart = True          # ohne Effekt-Modus wirkungslos
    frei = VCSlider("Aktiver Effekt", parent=flaeche)
    frei.mode = SliderMode.EFFECT_SPEED     # ohne festes Ziel: nichts zu sagen
    assert H.konsolen_funktions_ids(flaeche) == [lauf.id, puls.id], (
        "auch der Fader, der nur regelt, zaehlt mit")
    assert H.haltende_ids(flaeche) == {puls.id}
    assert H.haltende_ids(flaeche, ausser=fader) == set()
    fader.effect_autostart = True
    assert H.konsolen_funktions_ids(flaeche) == [lauf.id, puls.id]
    assert H.haltende_ids(flaeche) == set(), "stoppt bei 0 wirklich"
    for modus in (SliderMode.EFFECT_SPEED, SliderMode.EFFECT_PARAM):
        fader.mode = modus
        assert H.konsolen_funktions_ids(flaeche) == [lauf.id, puls.id], modus


def _fader(eltern, funktion, name="Fader", stoppt=False):
    f = VCSlider(name, parent=eltern)
    f.mode = SliderMode.EFFECT_INTENSITY
    f.function_id = funktion.id
    f.effect_autostart = stoppt
    return f


def test_taste_nennt_den_fader_der_bei_null_weiterlaufen_laesst(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    fader = _fader(flaeche, lauf)
    taste = _taste(flaeche, puls)
    wirt, zeile = _eigenschaften(taste)
    try:
        assert zeile.text() == (
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der "
            "Gruppe „Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt "
            "gestartet wurde. Ein Fader hält „Lauflicht HG“ auch bei 0 am "
            "Laufen — der Effekt belegt die Geräte dann weiter.")
        fader.effect_autostart = True
        zeile.neu_berechnen()
        assert zeile.hat_hinweis() and "am Laufen" not in zeile.text(), (
            "mit „bei 0 wirklich stoppen“ zaehlt der Fader weiter, ohne Zusatz")
    finally:
        _zu(wirt)


def _fader_dialog(fader, monkeypatch, im_dialog):
    """Oeffnet die Eigenschaften des Faders; ``im_dialog(dlg, zeile)`` laeuft,
    solange er offen ist."""
    from PySide6.QtWidgets import QDialog

    def _exec(dlg):
        zeile = dlg.findChild(QLabel, NAME)
        assert zeile is not None, "die Hinweiszeile gehoert in die Fader-Eigenschaften"
        im_dialog(dlg, zeile)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", _exec)
    fader._open_properties()


def test_fader_eigenschaften_zeigen_den_hinweis_und_den_satz_zu_null(
        fm, flaeche, monkeypatch):
    from PySide6.QtWidgets import QCheckBox
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND, stufe=STROBE)
    _taste(flaeche, puls)
    fader = _fader(flaeche, lauf)
    gesehen = {}

    def im_dialog(dlg, zeile):
        gesehen["ohne Haken"] = zeile.text()
        haken = next(c for c in dlg.findChildren(QCheckBox)
                     if c.text().startswith("bei 0 wirklich stoppen"))
        haken.setChecked(True)
        _app().processEvents()
        gesehen["mit Haken"] = zeile.text()
        gesehen["Tooltip"] = zeile.toolTip()

    _fader_dialog(fader, monkeypatch, im_dialog)
    satz = ("Dieser Fader und „Puls HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — „Puls HG“ liegt zwei Stufen höher und gewinnt.")
    assert gesehen["ohne Haken"] == (
        satz + "\nDieser Fader hält den Effekt auch bei 0 am Laufen — er "
        "belegt die Geräte dann weiter.")
    assert gesehen["mit Haken"] == satz, "die Zeile folgt dem Haken im Dialog"
    assert gesehen["Tooltip"].endswith(H.HINWEIS_TOOLTIP)
    assert fader.effect_autostart is False, "Abbrechen uebernimmt nichts"
    # Geschlossen rechnet die Zeile nicht weiter.
    zeilen = fader.findChildren(H.UeberschneidungsHinweis)
    from src.core.sync import get_sync, SyncEvent
    get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
    assert zeilen and not any(z._sammler.isActive() for z in zeilen)
    _app().processEvents()


def test_fader_ohne_ueberschneidung_oder_in_anderem_modus_zeigt_nichts(
        fm, flaeche, monkeypatch):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    himmel = _matrix(fm, "Himmel", HIMMEL)
    _taste(flaeche, himmel)
    fader = _fader(flaeche, lauf)
    texte = []
    _fader_dialog(fader, monkeypatch, lambda dlg, zeile: texte.append(zeile.text()))
    _taste(flaeche, _matrix(fm, "Puls HG", HINTERGRUND))
    fader.mode = SliderMode.GROUP_DIMMER
    _fader_dialog(fader, monkeypatch, lambda dlg, zeile: texte.append(zeile.text()))
    assert texte == ["", ""]


# ── Exklusiv-Gruppe (Solo-Frame) ─────────────────────────────────────────────

def _solo(eltern, an=True):
    rahmen = VCFrame(parent=eltern)
    rahmen.set_solo(an)
    return rahmen


def test_exklusiv_gruppe_ist_nur_was_der_solo_frame_wirklich_ausschaltet(fm, flaeche):
    """Die Regel folgt ``VCFrame.on_child_activated``: ausgeschaltet werden
    nur die DIREKTEN Kinder mit ``deactivate_for_solo`` — also Tasten."""
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    c = _matrix(fm, "C", HINTERGRUND)
    d = _matrix(fm, "D", HINTERGRUND)
    gruppe_a = _solo(flaeche)
    taste = _taste(gruppe_a, a)
    _taste(gruppe_a, b, "Partner")
    assert H.exklusiv_gruppe(taste) is gruppe_a
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == []

    # Fader im selben Solo-Frame: den schaltet der Rahmen NICHT aus.
    fader = _fader(gruppe_a, c)
    assert H.exklusiv_gruppe(fader) is None
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == [c.id]
    assert H.konsolen_funktions_ids(flaeche, ausser=fader) == [a.id, b.id]

    # Taste in einem Unter-Rahmen des Solo-Frames: kein direktes Kind.
    unter = VCFrame(parent=gruppe_a)
    innen = _taste(unter, d, "innen")
    assert H.exklusiv_gruppe(innen) is None
    assert H.konsolen_funktions_ids(flaeche, ausser=taste) == [c.id, d.id]
    assert H.konsolen_funktions_ids(flaeche, ausser=innen) == [a.id, b.id, c.id]


def test_zwei_exklusiv_gruppen_und_verschachtelte_solo_frames(fm, flaeche):
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    c = _matrix(fm, "C", HINTERGRUND)
    gruppe_a = _solo(flaeche)
    gruppe_b = _solo(flaeche)
    taste_a = _taste(gruppe_a, a)
    _taste(gruppe_b, b)
    assert H.konsolen_funktions_ids(flaeche, ausser=taste_a) == [b.id], (
        "Gruppe A gegen Gruppe B: beide koennen gleichzeitig laufen")
    # Solo-Frame im Solo-Frame: es zaehlt der innere, direkte Rahmen.
    innen = _solo(gruppe_a)
    taste_c = _taste(innen, c)
    assert H.exklusiv_gruppe(taste_c) is innen
    assert H.konsolen_funktions_ids(flaeche, ausser=taste_c) == [a.id, b.id]
    assert sorted(H.konsolen_funktions_ids(flaeche, ausser=taste_a)) == [b.id, c.id]


def test_sammlung_deren_mitglied_in_der_exklusiv_gruppe_liegt(fm, flaeche):
    """Taste 1 startet eine Sammlung, Taste 2 im selben Solo-Frame deren
    Mitglied: kein Hinweis zwischen den beiden. Eine Taste AUSSERHALB, die
    das Mitglied startet, meldet sich gegen die Sammlung weiterhin."""
    mitglied = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    sammlung = fm.new_collection("Bild 1")
    sammlung.function_ids = [puls.id]
    gruppe = _solo(flaeche)
    taste = _taste(gruppe, sammlung, "Sammlung")
    _taste(gruppe, mitglied, "Mitglied")
    wirt, zeile = _eigenschaften(taste)
    try:
        assert not zeile.hat_hinweis()
        _taste(flaeche, mitglied, "draussen")
        zeile.neu_berechnen()
        assert zeile.text().startswith(
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — ")
    finally:
        _zu(wirt)


def test_beziehungen_fuer_die_ansicht_prioritaeten(fm, flaeche):
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    c = _matrix(fm, "C", HINTERGRUND)
    d = _matrix(fm, "D", HINTERGRUND)
    e = _matrix(fm, "E", HINTERGRUND)
    gruppe = _solo(flaeche)
    _taste(gruppe, a)
    _taste(gruppe, b)
    doppelt = _taste(flaeche, c, "zwei Ziele")
    doppelt.function_ids = [d.id]
    _fader(flaeche, e)
    ids, gegenueber, haltend = H.konsolen_beziehungen([flaeche])
    assert ids == [a.id, b.id, c.id, d.id, e.id]
    assert gegenueber[a.id] == {c.id, d.id, e.id}, "nicht gegen den Partner B"
    assert gegenueber[b.id] == {c.id, d.id, e.id}
    assert gegenueber[c.id] == {a.id, b.id, e.id}, "nicht gegen D derselben Taste"
    assert gegenueber[e.id] == {a.id, b.id, c.id, d.id}
    assert haltend == {e.id}
    _taste(flaeche, b, "B draussen")
    _ids, gegenueber, _h = H.konsolen_beziehungen([flaeche])
    assert b.id in gegenueber[a.id], "B liegt jetzt auch ausserhalb der Gruppe"
    assert a.id in gegenueber[b.id]


def test_eigene_funktionen_einer_taste_melden_sich_nicht_gegenseitig(fm, flaeche):
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    c = _matrix(fm, "C", HINTERGRUND)
    _taste(flaeche, c)
    assert H.treffer_fuer([a.id, b.id], [a.id, b.id]) == []
    treffer = H.treffer_fuer([a.id, b.id], [c.id, a.id])
    assert [(t.eigene.name, t.andere.name) for t in treffer] == [
        ("A", "C"), ("B", "C")]


# ── reine Auskunft ───────────────────────────────────────────────────────────

def test_hinweis_aendert_weder_taste_noch_funktionen(fm, flaeche):
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND, stufe=STROBE)
    andere = _taste(flaeche, lauf)
    taste = _taste(flaeche, puls)
    vorher = (taste.to_dict(), andere.to_dict(), lauf.to_dict(), puls.to_dict())
    wirt, zeile = _eigenschaften(taste)
    try:
        assert zeile.text()
        zeile.neu_berechnen()
        nachher = (taste.to_dict(), andere.to_dict(), lauf.to_dict(), puls.to_dict())
        assert nachher == vorher
        assert "ueberschn" not in str(taste.to_dict()).lower(), "nichts Neues in der Show"
    finally:
        _zu(wirt)


def test_hinweiszeile_haengt_an_keinem_dauer_zeitgeber(fm, flaeche):
    from PySide6.QtCore import QTimer
    wirt, zeile = _eigenschaften(_taste(flaeche, _matrix(fm, "A", HINTERGRUND)))
    try:
        uhren = zeile.findChildren(QTimer)
        assert all(u.isSingleShot() for u in uhren)
        assert not any(u.isActive() for u in uhren)
    finally:
        _zu(wirt)


def test_geschlossener_dialog_rechnet_nicht_weiter(fm, flaeche, monkeypatch):
    """Der Eigenschaften-Dialog bleibt nach dem Schliessen als Kind der Taste
    bestehen. Seine Hinweiszeile darf dann nicht bei jeder Aenderung
    weiterrechnen — sonst waechst die Arbeit mit jedem Oeffnen."""
    from PySide6.QtWidgets import QDialog
    from src.core.sync import get_sync, SyncEvent
    from src.ui.widgets.stufe_auswahl import stufen_melder
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, lauf)
    taste = _taste(flaeche, puls)
    gesehen = []

    def _exec(dlg):
        zeile = dlg.findChild(QLabel, NAME)
        gesehen.append(zeile.text())        # solange offen: Hinweis steht da
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", _exec)
    for _ in range(3):
        taste._open_properties()
    assert all("steuern beide den Dimmer" in t for t in gesehen) and len(gesehen) == 3

    zeilen = taste.findChildren(H.UeberschneidungsHinweis)
    assert len(zeilen) == 3, "Vorbedingung: die Dialoge leben an der Taste weiter"
    get_sync().emit(SyncEvent.FUNCTION_CHANGED, None)
    stufen_melder().geaendert.emit(frozenset({lauf.id}))
    assert not any(z._sammler.isActive() for z in zeilen), (
        "geschlossene Dialoge rechnen weiter")
    _app().processEvents()


# ── Ansicht „Prioritäten“ ────────────────────────────────────────────────────

def test_ansicht_prioritaeten_zeigt_dieselben_saetze_als_tooltip(fm, flaeche):
    from src.ui.views.prioritaeten_view import PrioritaetenView, _ROLLE_FID
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND, stufe=STROBE)
    frei = _matrix(fm, "Ohne Taste", HINTERGRUND)
    fenster = QWidget()
    lay = QVBoxLayout(fenster)
    lay.addWidget(flaeche)
    ansicht = PrioritaetenView()
    lay.addWidget(ansicht)
    _taste(flaeche, lauf)
    _taste(flaeche, puls)
    try:
        def _tipps():
            tipps = {}
            wurzel = ansicht._baum.invisibleRootItem()
            for i in range(wurzel.childCount()):
                kopf = wurzel.child(i)
                for j in range(kopf.childCount()):
                    it = kopf.child(j)
                    tipps[it.data(0, _ROLLE_FID)] = it.toolTip(0)
            return tipps

        ansicht.neu_aufbauen()
        tipps = _tipps()
        assert tipps[lauf.id] == (
            "Dieser Effekt und „Puls HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — „Puls HG“ liegt zwei Stufen höher und gewinnt.")
        assert "dieser Effekt liegt zwei Stufen höher und gewinnt" in tipps[puls.id]
        assert tipps[frei.id] == "", "liegt auf keiner Taste -> kein Hinweis"

        # Nachtrag: dieselben Regeln wie an der Taste. Ein Fader ohne „bei 0
        # wirklich stoppen“ zaehlt mit und wird genannt …
        wash = _matrix(fm, "Wash HG", HINTERGRUND)
        _fader(flaeche, wash)
        ansicht.neu_aufbauen()
        tipps = _tipps()
        assert tipps[wash.id].endswith(
            "\nEin Fader hält diesen Effekt auch bei 0 am Laufen — er belegt "
            "die Geräte dann weiter.")
        assert ("Ein Fader hält „Wash HG“ auch bei 0 am Laufen — der Effekt "
                "belegt die Geräte dann weiter.") in tipps[lauf.id]
        # … und Tasten desselben Solo-Frames melden sich untereinander nicht.
        solo_a = _matrix(fm, "Solo A", HIMMEL)
        solo_b = _matrix(fm, "Solo B", HIMMEL)
        rahmen = VCFrame(parent=flaeche)
        rahmen.set_solo(True)
        _taste(rahmen, solo_a)
        _taste(rahmen, solo_b)
        ansicht.neu_aufbauen()
        tipps = _tipps()
        assert tipps[solo_a.id] == "" and tipps[solo_b.id] == ""
        rahmen.set_solo(False)
        ansicht.neu_aufbauen()
        assert "„Solo B“" in _tipps()[solo_a.id]
    finally:
        flaeche.setParent(None)
        ansicht.close()
        fenster.close()
        fenster.deleteLater()
        _app().processEvents()


# ── Leistung ─────────────────────────────────────────────────────────────────

def test_leistung_200_funktionen_100_tasten(fm, flaeche):
    """Ziel laut Auftrag: unter 50 ms. Die Grenze hier ist grosszuegig, damit
    ein belasteter Rechner den Test nicht kippt; die gemessene Zahl steht in
    der Ausgabe (``-s``)."""
    funktionen = []
    for i in range(200):
        start = 9000 + (i % 25) * 4                 # 25 Gruppen zu je 8 Geraeten,
        stil = (MatrixStyle.DIMMER, MatrixStyle.RGB)[i % 2]     # ueberlappend
        funktionen.append(_matrix(fm, f"L{i:03d}", range(start, start + 8), stil,
                                  stufe=(0, 20, 40)[i % 3]))
    for i in range(100):
        _taste(flaeche, funktionen[i], f"T{i}")
    taste = _taste(flaeche, funktionen[150], "Neu")
    zeile = H.UeberschneidungsHinweis(taste, lambda: [funktionen[150].id])
    try:
        zeiten = []
        for _ in range(5):
            t0 = time.perf_counter()
            zeile.neu_berechnen()
            zeiten.append(time.perf_counter() - t0)
        assert zeile.treffer, "die Messung soll echte Treffer rechnen"
        beste = min(zeiten) * 1000.0
        print(f"\nENG-39 Leistung: {beste:.1f} ms (beste von 5), "
              f"{len(zeile.treffer)} Treffer, 200 Funktionen, 101 Tasten")
        assert beste < 250.0, f"{beste:.1f} ms"
    finally:
        zeile.deleteLater()
        _app().processEvents()


# ── Nachtrag Sichtprobe: Reihenfolge, vollstaendiger Tooltip, Breite ─────────

def test_verlierer_fall_steht_oben_und_der_tooltip_traegt_alles(fm, flaeche):
    """Fuenf Effekte auf gleicher Stufe und einer, der staerker ist: der
    staerkere steht in der ersten Zeile, nicht hinter „… und n weitere“. Der
    Tooltip nennt alle sechs."""
    ich = _matrix(fm, "Ich", HINTERGRUND)
    for i in range(5):
        _taste(flaeche, _matrix(fm, f"Effekt {i}", HINTERGRUND), f"T{i}")
    _taste(flaeche, _matrix(fm, "Zzz Blinder", HINTERGRUND, stufe=STROBE), "B")
    wirt, zeile = _eigenschaften(_taste(flaeche, ich))
    try:
        zeilen = zeile.text().split("\n")
        assert zeilen[0] == (
            "Diese Taste und „Zzz Blinder“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — „Zzz Blinder“ liegt zwei Stufen höher und gewinnt.")
        assert len(zeilen) == 4
        assert zeilen[-1] == ("… und 3 weitere Überschneidungen: bei 3 "
                              "entscheidet, wer zuletzt gestartet wurde.")
        tipp = zeile.toolTip()
        for name in ["Zzz Blinder"] + [f"Effekt {i}" for i in range(5)]:
            assert f"„{name}“" in tipp, name
        assert "… und" not in tipp, "der Tooltip fasst nichts zusammen"
        assert tipp.index("„Zzz Blinder“") < tipp.index("„Effekt 0“")
        assert "ändert und sperrt nichts" in tipp
    finally:
        _zu(wirt)


def test_tooltip_ohne_treffer_ist_nur_die_erklaerung(fm, flaeche):
    from src.ui.widgets.ueberschneidung_hinweis import HINWEIS_TOOLTIP
    wirt, zeile = _eigenschaften(_taste(flaeche, _matrix(fm, "Allein", HIMMEL)))
    try:
        assert zeile.text() == "" and zeile.toolTip() == HINWEIS_TOOLTIP
    finally:
        _zu(wirt)


def test_zeile_bricht_bei_240_px_um_und_verlangt_keine_breite(fm, flaeche):
    """Die Zeile allein, 240 px breit: sie verlangt nicht mehr und wird
    mehrzeilig. Auch ein langer Name ohne Leerzeichen macht sie nicht breiter."""
    from PySide6.QtWidgets import QSizePolicy
    from src.ui.widgets.ueberschneidung_hinweis import UeberschneidungsHinweis
    lang = "Lauflicht_Hintergrund_sehr_langer_Name_ohne_Leerzeichen_0123456789"
    ich = _matrix(fm, "Ich", HINTERGRUND)
    _taste(flaeche, _matrix(fm, lang, HINTERGRUND), "L")
    taste = _taste(flaeche, ich)
    zeile = UeberschneidungsHinweis(taste, lambda: [ich.id])
    try:
        assert zeile.hat_hinweis() and "\n" not in zeile.text()
        zeile.resize(240, 40)
        assert zeile.wordWrap()
        assert zeile.minimumSizeHint().width() <= 240
        assert zeile.minimumWidth() == 0
        assert (zeile.sizePolicy().horizontalPolicy()
                == QSizePolicy.Policy.Ignored), "der Wunsch der Zeile zaehlt nicht"
        einzeilig = zeile.fontMetrics().lineSpacing()
        assert zeile.hasHeightForWidth()
        assert zeile.heightForWidth(240) >= 3 * einzeilig, "ein Satz, mehrere Zeilen"
        assert zeile.heightForWidth(240) > zeile.heightForWidth(900)
    finally:
        zeile.stilllegen()
        zeile.deleteLater()
        _app().processEvents()


def _inspector(taste, breite):
    from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
    panel = VCInspectorPanel()
    panel.resize(breite, 800)
    panel.show()
    panel.bind(taste)
    for _ in range(3):
        _app().processEvents()
    inhalt = panel._scroll.widget()
    return panel, inhalt, inhalt.findChild(QLabel, NAME)


def _inspector_zu(panel):
    panel._before = None            # keinen Rueckgaengig-Schritt fuer den Test
    panel.close()
    panel.deleteLater()
    _app().processEvents()


@pytest.mark.parametrize("breite", [260, 440])
def test_zeile_liegt_im_inspector_ganz_im_sichtbaren_bereich(fm, flaeche, breite):
    """Sichtprobe: im 260 px schmalen Inspector lag die gelbe Zeile grossteils
    ausserhalb des Bildes. Jetzt steht sie oben links, gleich unter „Aktion“,
    und ist nie breiter als das, was zu sehen ist."""
    from src.ui.widgets.collapsible_section import CollapsibleSection
    ich = _matrix(fm, "Ich", HINTERGRUND)
    _taste(flaeche, _matrix(fm, "Lauflicht HG", HINTERGRUND), "L")
    _taste(flaeche, _matrix(fm, "Blinder", HINTERGRUND, stufe=STROBE), "B")
    panel, inhalt, zeile = _inspector(_taste(flaeche, ich), breite)
    try:
        sicht = panel._scroll.viewport()
        assert zeile.isVisible() and zeile.hat_hinweis()
        links = zeile.mapTo(inhalt, zeile.rect().topLeft()).x()
        assert links == 0, "ganz links"
        assert links + zeile.width() <= sicht.width(), (zeile.width(), sicht.width())
        # Hoehe folgt dem umbrochenen Text — nichts ist abgeschnitten.
        assert zeile.height() >= zeile.heightForWidth(zeile.width())
        # Oben: ueber allen Klappbereichen.
        bereiche = inhalt.findChildren(CollapsibleSection)
        assert bereiche and all(
            zeile.mapTo(inhalt, zeile.rect().topLeft()).y()
            < b.mapTo(inhalt, b.rect().topLeft()).y() for b in bereiche)
        # Die Zeile selbst erhoeht die Mindestbreite des Inhalts nicht.
        ohne = max(b.minimumSizeHint().width() for b in bereiche)
        assert inhalt.minimumSizeHint().width() <= ohne
        if breite == 440:
            assert inhalt.width() <= sicht.width(), (
                "bei 440 px passt der ganze Inhalt ohne Querrollen")
    finally:
        _inspector_zu(panel)


def test_zeile_bleibt_bei_zugeklapptem_bereich_ziel_und_verhalten(fm, flaeche):
    from src.ui.widgets.collapsible_section import CollapsibleSection
    ich = _matrix(fm, "Ich", HINTERGRUND)
    _taste(flaeche, _matrix(fm, "Lauflicht HG", HINTERGRUND), "L")
    panel, inhalt, zeile = _inspector(_taste(flaeche, ich), 440)
    try:
        for bereich in inhalt.findChildren(CollapsibleSection):
            bereich._content.setVisible(False)       # ohne die Vorgabe zu speichern
        _app().processEvents()
        assert zeile.isVisible()
    finally:
        _inspector_zu(panel)


# ── Gegenpruefung Nachtrag: die Regel gegen das echte Schaltverhalten ────────

def _druck(taste):
    taste._trigger(True)
    taste._trigger(False)


def _gegenseitig_sichtbar(flaeche, a, b) -> bool:
    """Meldet der Hinweis an ``a`` die Funktionen von ``b`` — und umgekehrt?"""
    hin = set(H._start_ids(b)) <= set(H.konsolen_funktions_ids(flaeche, ausser=a))
    her = set(H._start_ids(a)) <= set(H.konsolen_funktions_ids(flaeche, ausser=b))
    assert hin == her, "die Regel muss in beide Richtungen dasselbe sagen"
    return hin


@pytest.mark.parametrize("aktion", [ButtonAction.FUNCTION_TOGGLE,
                                    ButtonAction.FUNCTION_FLASH])
def test_kein_hinweis_nur_wo_der_solo_frame_wirklich_ausschaltet(fm, flaeche, aktion):
    """Verschwiegen wird ein Paar nur, wenn es NIE gleichzeitig laufen kann.
    Geprueft am echten Tastendruck — auch fuer gehaltene Flash-Tasten: die
    zweite gehaltene Taste stoppt im Solo-Frame die erste."""
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    gruppe = _solo(flaeche)
    ta = _taste(gruppe, a, "A", aktion)
    tb = _taste(gruppe, b, "B", aktion)
    for erst, dann in ((ta, tb), (tb, ta)):
        fm.stop_all()
        erst._trigger(True)                 # halten bzw. einschalten
        dann._trigger(True)
        assert not (fm.is_running(a.id) and fm.is_running(b.id)), (
            "Vorbedingung: der Solo-Frame laesst nur eine Taste laufen")
        erst._trigger(False)
        dann._trigger(False)
    assert not _gegenseitig_sichtbar(flaeche, ta, tb)

    # Ohne Solo-Haken steht der Rahmen nur optisch zusammen: beide laufen.
    gruppe.set_solo(False)
    fm.stop_all()
    ta._trigger(True)
    tb._trigger(True)
    assert fm.is_running(a.id) and fm.is_running(b.id)
    assert _gegenseitig_sichtbar(flaeche, ta, tb), (
        "ein Rahmen ohne Solo-Haken schliesst nichts aus")
    fm.stop_all()


def test_hinweis_bleibt_wo_trotz_solo_frame_beides_laufen_kann(fm, flaeche):
    """Fader im Solo-Frame, Taste im Unter-Rahmen, zweiter Solo-Frame: dort
    laufen beide Effekte wirklich gleichzeitig — der Hinweis muss kommen."""
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    c = _matrix(fm, "C", HINTERGRUND)
    d = _matrix(fm, "D", HINTERGRUND)
    gruppe = _solo(flaeche)
    ta = _taste(gruppe, a, "A")
    fader = _fader(gruppe, b, stoppt=True)
    innen = _taste(VCFrame(parent=gruppe), c, "innen")
    andere = _taste(_solo(flaeche), d, "andere Gruppe")

    # Fader im Solo-Frame: er startet seinen Effekt, die Taste stoppt ihn nicht.
    fm.start(b.id)                      # wie der Fader mit Wert > 0
    _druck(ta)
    assert fm.is_running(a.id) and fm.is_running(b.id), (
        "Vorbedingung: der Solo-Frame schaltet den Fader nicht aus")
    assert _gegenseitig_sichtbar(flaeche, ta, fader)

    # Taste im Unter-Rahmen: erst sie, dann die Taste direkt im Solo-Frame.
    fm.stop_all()
    _druck(innen)
    _druck(ta)
    assert fm.is_running(a.id) and fm.is_running(c.id), (
        "Vorbedingung: der Solo-Frame schaltet nur seine direkten Tasten aus")
    assert _gegenseitig_sichtbar(flaeche, ta, innen)

    # Zwei Solo-Frames nebeneinander.
    fm.stop_all()
    _druck(ta)
    _druck(andere)
    assert fm.is_running(a.id) and fm.is_running(d.id)
    assert _gegenseitig_sichtbar(flaeche, ta, andere)
    fm.stop_all()


NICHT_EFFEKT_MODI = [SliderMode.LEVEL, SliderMode.PLAYBACK, SliderMode.SUBMASTER,
                     SliderMode.GRANDMASTER, SliderMode.PROGRAMMER, SliderMode.BPM,
                     SliderMode.SPEED, SliderMode.GROUP_DIMMER,
                     SliderMode.FEATURE_DIMMER, SliderMode.TEMPO_BUS]


@pytest.mark.parametrize("modus", NICHT_EFFEKT_MODI)
def test_fader_die_keinen_effekt_steuern_zaehlen_nie(fm, flaeche, modus):
    """Grand Master, Tempo, Submaster, Gruppen-Dimmer, Pegel … sind kein
    Effekt — auch dann nicht, wenn aus einem frueheren Modus noch ein Ziel im
    Fader steht."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    rest = _matrix(fm, "Rest HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    fader = VCSlider("Master", parent=flaeche)
    fader.mode = modus
    fader.function_id = lauf.id             # Altlast aus einem Effekt-Modus
    fader.function_ids = [rest.id]
    assert H.konsolen_funktions_ids(flaeche) == []
    assert H.haltende_ids(flaeche) == set()
    assert not H.haelt_bei_null(fader)
    ids, _gegenueber, haltend = H.konsolen_beziehungen([flaeche])
    assert ids == [] and haltend == set()
    wirt, zeile = _eigenschaften(_taste(flaeche, puls))
    try:
        assert not zeile.hat_hinweis(), modus
    finally:
        _zu(wirt)


def test_fader_ohne_ziel_zaehlt_nicht_und_haelt_nichts(fm, flaeche):
    """Effekt-Fader ohne festes Ziel („aktiver Effekt“) und einer, dessen Ziel
    es nicht mehr gibt: kein Hinweis, kein Halte-Satz."""
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    leer = VCSlider("leer", parent=flaeche)
    leer.mode = SliderMode.EFFECT_INTENSITY
    weg = VCSlider("weg", parent=flaeche)
    weg.mode = SliderMode.EFFECT_INTENSITY
    weg.function_id = 987654                # gibt es nicht (mehr)
    assert H.haltende_ids(flaeche) == {987654}
    wirt, zeile = _eigenschaften(_taste(flaeche, puls))
    try:
        assert not zeile.hat_hinweis()
    finally:
        _zu(wirt)


def test_fader_der_selbst_stoppt_behauptet_nicht_er_halte_den_effekt(
        fm, flaeche, monkeypatch):
    """Zwei Fader am selben Effekt (Helligkeit mit „bei 0 wirklich stoppen“,
    Tempo ohne): in den Eigenschaften des Helligkeits-Faders darf nicht stehen,
    DIESER Fader halte den Effekt am Laufen — das tut der andere."""
    lauf = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    puls = _matrix(fm, "Puls HG", HINTERGRUND)
    _taste(flaeche, puls)
    hell = _fader(flaeche, lauf, "Helligkeit", stoppt=True)
    tempo = _fader(flaeche, lauf, "Tempo", stoppt=False)
    tempo.mode = SliderMode.EFFECT_SPEED
    texte = []
    _fader_dialog(hell, monkeypatch, lambda dlg, zeile: texte.append(zeile.text()))
    _fader_dialog(tempo, monkeypatch, lambda dlg, zeile: texte.append(zeile.text()))
    satz = ("Dieser Fader und „Puls HG“ steuern beide den Dimmer der Gruppe "
            "„Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt gestartet "
            "wurde.")
    assert texte[0] == (
        satz + "\nEin anderer Fader hält „Lauflicht HG“ auch bei 0 am Laufen — "
        "der Effekt belegt die Geräte dann weiter.")
    assert texte[1] == (
        satz + "\nDieser Fader hält den Effekt auch bei 0 am Laufen — er "
        "belegt die Geräte dann weiter.")


def test_farbe_gegen_dimmer_bleibt_auch_mit_fader_ohne_hinweis(fm, flaeche, monkeypatch):
    """Farbe und Dimmer sind getrennt: ein Farb-Fader und eine Dimmer-Taste auf
    denselben Lampen ueberschneiden sich nicht — in keiner Richtung, und der
    Halte-Satz steht dann auch nicht allein da."""
    farbe = _matrix(fm, "Farbe HG", HINTERGRUND, MatrixStyle.RGB)
    dimmer = _matrix(fm, "Puls HG", HINTERGRUND, MatrixStyle.DIMMER)
    fader = _fader(flaeche, farbe)
    taste = _taste(flaeche, dimmer)
    texte = []
    _fader_dialog(fader, monkeypatch, lambda dlg, zeile: texte.append(zeile.text()))
    wirt, zeile = _eigenschaften(taste)
    try:
        texte.append(zeile.text())
    finally:
        _zu(wirt)
    assert texte == ["", ""]


def test_leistung_300_bedienelemente_mit_fadern_und_solo_frames(fm, flaeche):
    """300 Bedienelemente (Tasten frei und in Solo-Frames, Fader mit und ohne
    „bei 0 wirklich stoppen“): Ziel unter 50 ms je Rechnung. Grenze
    grosszuegig, die gemessene Zahl steht in der Ausgabe (``-s``)."""
    funktionen = []
    for i in range(300):
        start = 9000 + (i % 25) * 4
        stil = (MatrixStyle.DIMMER, MatrixStyle.RGB)[i % 2]
        funktionen.append(_matrix(fm, f"L{i:03d}", range(start, start + 8), stil,
                                  stufe=(0, 20, 40)[i % 3]))
    rahmen = [_solo(flaeche) for _ in range(6)]
    for i in range(150):
        _taste(flaeche, funktionen[i], f"T{i}")
    for i in range(150, 210):
        _taste(rahmen[i % 6], funktionen[i], f"S{i}")
    for i in range(210, 299):
        _fader(flaeche, funktionen[i], f"F{i}", stoppt=bool(i % 2))
    taste = _taste(rahmen[0], funktionen[299], "Neu")
    fader = _fader(flaeche, funktionen[298], "Neu F")
    assert len(H._bedienelemente(flaeche)) == 301
    zeilen = [H.UeberschneidungsHinweis(taste, lambda: [funktionen[299].id]),
              H.UeberschneidungsHinweis(fader, lambda: [funktionen[298].id],
                                        subjekt="Fader", haelt_selbst=lambda: True)]
    try:
        for zeile, was in zip(zeilen, ("Taste im Solo-Frame", "Fader")):
            zeiten = []
            for _ in range(5):
                t0 = time.perf_counter()
                zeile.neu_berechnen()
                zeiten.append(time.perf_counter() - t0)
            assert zeile.treffer, "die Messung soll echte Treffer rechnen"
            beste = min(zeiten) * 1000.0
            print(f"\nENG-39 Leistung ({was}): {beste:.1f} ms (beste von 5), "
                  f"{len(zeile.treffer)} Treffer, 300 Funktionen, 301 Bedienelemente")
            assert beste < 250.0, f"{was}: {beste:.1f} ms"
        t0 = time.perf_counter()
        ids, gegenueber, _haltend = H.konsolen_beziehungen([flaeche])
        dauer = (time.perf_counter() - t0) * 1000.0
        print(f"ENG-39 Leistung (Beziehungen fuer „Prioritäten“): {dauer:.1f} ms, "
              f"{len(ids)} Funktionen")
        assert len(ids) == 300 and dauer < 250.0, f"{dauer:.1f} ms"
    finally:
        for zeile in zeilen:
            zeile.deleteLater()
        _app().processEvents()

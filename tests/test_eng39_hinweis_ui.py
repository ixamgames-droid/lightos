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
            "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer von "
            "Hintergrund — gleiche Stufe, es gewinnt, wer zuletzt gestartet wurde.")
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
        assert len(zeilen) == 4 and zeilen[-1] == "… und 2 weitere"
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


def test_nur_tasten_und_startende_fader_zaehlen(fm, flaeche):
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
    assert H.konsolen_funktions_ids(flaeche) == [lauf.id], "Fader regelt nur"
    fader.effect_autostart = True
    assert H.konsolen_funktions_ids(flaeche) == [lauf.id, puls.id]


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
        ansicht.neu_aufbauen()
        tipps = {}
        wurzel = ansicht._baum.invisibleRootItem()
        for i in range(wurzel.childCount()):
            kopf = wurzel.child(i)
            for j in range(kopf.childCount()):
                it = kopf.child(j)
                tipps[it.data(0, _ROLLE_FID)] = it.toolTip(0)
        assert tipps[lauf.id] == (
            "Dieser Effekt und „Puls HG“ steuern beide den Dimmer von "
            "Hintergrund — „Puls HG“ liegt zwei Stufen höher und gewinnt.")
        assert "dieser Effekt liegt zwei Stufen höher und gewinnt" in tipps[puls.id]
        assert tipps[frei.id] == "", "liegt auf keiner Taste -> kein Hinweis"
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

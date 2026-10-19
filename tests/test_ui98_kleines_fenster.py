"""UI-98 — bei 1000×640 nichts abgeschnitten oder übereinander.

Befund (Sichtprüfung im Sandkasten, Demo-Show):

* Programmer-Werkzeugleiste: „Alles lösche“, „arb-Werkzeug.“, „itions-Werkzeu“ —
  eine starre ``QHBoxLayout`` quetschte die Knöpfe unter ihre Wunschbreite.
* Playback, Feld „Optionen“: „Loop: AUS“ verdeckte „Modus:“, die
  Modus-Auswahl war unten abgeschnitten (rechte Spalte zu niedrig).
* Executor-Leiste: zehn Executoren mit fester Breite 110 passten nicht
  nebeneinander — ⚙ über dem Nachbarnamen, Ex 10 rechts abgeschnitten.
* Bei 1440×900 großer Leerraum zwischen „Executor-Leiste:“ und den Executoren.

Die Größen entsprechen dem Platz, den die Ansichten im Hauptfenster bei
1000×640 bzw. 1440×900 bekommen. Das dunkle Theme (``dark.qss``) liegt auf
einem Wirt-Widget, damit Innenabstände wie in der App gelten.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (QApplication, QComboBox, QLabel, QPushButton,
                               QWidget)

#: Platz der Ansicht im Hauptfenster (Breite, Höhe) je Fenstergröße —
#: gemessen im Sandkasten (Menü, Bereichsleiste, Unterreiter, Befehlszeile
#: und Statusleiste abgezogen).
KLEIN = (1000, 480)
GROSS = (1440, 740)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _qss() -> str:
    return (ROOT / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")


def _im_wirt(view: QWidget, groesse: tuple[int, int]) -> QWidget:
    app = _app()
    # Ohne Layout im Wirt: wie im Hauptfenster bekommt die Ansicht genau den
    # Platz — ein Wirt-Layout würde das Fenster stattdessen auf die
    # Mindestgröße der Ansicht aufziehen und den Fehler verdecken.
    wirt = QWidget()
    wirt.setStyleSheet(_qss())
    view.setParent(wirt)
    wirt.resize(*groesse)
    view.setGeometry(0, 0, *groesse)
    wirt.show()
    for _ in range(5):
        app.processEvents()
    return wirt


def _neu_groesse(wirt: QWidget, view: QWidget, groesse: tuple[int, int]) -> None:
    wirt.resize(*groesse)
    view.setGeometry(0, 0, *groesse)
    for _ in range(5):
        _app().processEvents()


def _rect_in(w: QWidget, bezug: QWidget) -> QRect:
    return QRect(w.mapTo(bezug, w.rect().topLeft()), w.size())


def _text_passt(b: QPushButton) -> bool:
    """Breite reicht für den Text (Wunschbreite des Knopfs nach Stylesheet)."""
    return b.width() >= b.sizeHint().width()


# ── Programmer ────────────────────────────────────────────────────────────────

@pytest.fixture
def programmer(tmp_path, monkeypatch):
    _app()
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    view = pv.ProgrammerView()
    yield view
    if shiboken6.isValid(view):
        view.close()


def _zeilen(knoepfe) -> int:
    """Anzahl Zeilen; Knöpfe unterschiedlicher Höhe stehen in einer Zeile
    leicht versetzt (zentriert), deshalb mit Toleranz zählen."""
    ys = sorted(_rect_in(b, b.window()).y() for b in knoepfe)
    return 1 + sum(1 for a, b in zip(ys, ys[1:]) if b - a > 8)


_LEISTE = ("Hervorheben", "Abdunkeln", "Kopieren", "Einfügen", "Rückgängig",
           "Wiederholen", "Farb-Werkzeug...", "Positions-Werkzeug...",
           "Fächer...", "?")


def _toolbar_knoepfe(view) -> list[QPushButton]:
    """Die Knöpfe der Werkzeugleiste — über ihre Beschriftung gefunden, damit
    der Test auch gegen den alten Aufbau (Gegenprobe) läuft."""
    knoepfe = [b for b in view.findChildren(QPushButton)
               if b.text() in _LEISTE and b.isVisibleTo(view)]
    return knoepfe + [view._btn_clear, view._btn_layout]


@pytest.mark.parametrize("groesse", [KLEIN, GROSS])
def test_programmer_werkzeugleiste_ungekuerzt_und_ohne_ueberlappung(programmer, groesse):
    wirt = _im_wirt(programmer, groesse)
    knoepfe = _toolbar_knoepfe(programmer)
    texte = {b.text() for b in knoepfe}
    assert {"Farb-Werkzeug...", "Positions-Werkzeug...", "Fächer..."} <= texte
    flaeche = programmer.rect()
    rects = []
    for b in knoepfe:
        assert _text_passt(b), f"„{b.text()}“ gekürzt: {b.width()} < {b.sizeHint().width()}"
        r = _rect_in(b, programmer)
        assert flaeche.contains(r), f"„{b.text()}“ ragt aus der Ansicht: {r}"
        rects.append((b.text(), r))
    for i, (ta, ra) in enumerate(rects):
        for tb, rb in rects[i + 1:]:
            assert not ra.intersects(rb), f"„{ta}“ überlappt „{tb}“"
    wirt.close()


def test_programmer_werkzeugleiste_bricht_um_statt_zu_quetschen(programmer):
    """Bei 1000 px reicht eine Zeile nicht — die Leiste wird zweizeilig, ist
    aber bei 1440 px wieder einzeilig."""
    wirt = _im_wirt(programmer, KLEIN)
    zeilen_klein = _zeilen(_toolbar_knoepfe(programmer)[:-1])
    _neu_groesse(wirt, programmer, GROSS)
    zeilen_gross = _zeilen(_toolbar_knoepfe(programmer)[:-1])
    assert zeilen_klein >= 2
    assert zeilen_gross == 1
    wirt.close()


_WERKZEUGE = ("Farb-Werkzeug...", "Positions-Werkzeug...", "Fächer...")


def _mitte_y(b: QPushButton, bezug: QWidget) -> int:
    return _rect_in(b, bezug).center().y()


def test_programmer_werkzeugleiste_zeilen_mittig_ausgerichtet(programmer):
    """Gegenprüfung: Bearbeiten-Knöpfe (niedriger) standen oben bündig und
    damit höher als die Werkzeug-Knöpfe derselben Zeile."""
    wirt = _im_wirt(programmer, GROSS)
    flow = [b for b in _toolbar_knoepfe(programmer) if b.text() not in ("?",)
            and b is not programmer._btn_layout]
    mitten = {b.text(): _mitte_y(b, programmer) for b in flow}
    assert max(mitten.values()) - min(mitten.values()) <= 1, mitten
    wirt.close()


def test_programmer_werkzeug_gruppe_bricht_nur_gemeinsam_um(programmer):
    """Gegenprüfung: bei 1000 px stand „Farb-Werkzeug...“ in Zeile 1,
    „Positions-Werkzeug...“ und „Fächer...“ in Zeile 2."""
    wirt = _im_wirt(programmer, KLEIN)
    for breite in range(760, 1500, 10):
        _neu_groesse(wirt, programmer, (breite, KLEIN[1]))
        wz = [b for b in _toolbar_knoepfe(programmer) if b.text() in _WERKZEUGE]
        assert len(wz) == 3
        mitten = {b.text(): _mitte_y(b, programmer) for b in wz}
        assert max(mitten.values()) - min(mitten.values()) <= 1, (breite, mitten)
    wirt.close()


def test_loeschen_knopf_mindestbreite_mit_fetter_schrift(programmer):
    b = programmer._btn_clear
    f = QFont(b.font())
    f.setBold(True)
    fm = QFontMetrics(f)
    for n in (0, 99):
        text = programmer._clear_button_labels(n)[0]
        assert b.minimumWidth() >= fm.horizontalAdvance(text) + 20, text


# ── Playback ──────────────────────────────────────────────────────────────────

@pytest.fixture
def playback():
    _app()
    from src.core.app_state import get_state
    from src.ui.views.playback_view import PlaybackView
    get_state()
    view = PlaybackView()
    yield view
    if shiboken6.isValid(view):
        view.close()


def test_executoren_passen_bei_1000_nebeneinander(playback):
    wirt = _im_wirt(playback, KLEIN)
    exe = playback._executors_widgets
    assert len(exe) == 10
    rects = [_rect_in(e, playback) for e in exe]
    for e, r in zip(exe, rects):
        # Ganz sichtbar: nicht vom Elternteil (Leiste/Ansicht) beschnitten.
        sichtbar = e.visibleRegion().boundingRect()
        assert sichtbar == e.rect(), f"Ex {e._slot} abgeschnitten: {sichtbar} ≠ {e.rect()}"
        assert playback.rect().contains(r), f"Ex {e._slot} ragt aus der Ansicht: {r}"
        # ⚙ liegt im eigenen Executor (vorher über dem Nachbarnamen).
        assert r.contains(_rect_in(e._btn_cfg, playback))
        for b in e._fn_buttons:
            # sizeHint enthält den Innenabstand aus dem Stylesheet — die
            # reine Textbreite + Pauschale bemerkte abgeschnittene Tasten nicht.
            assert _text_passt(b), (b.text(), b.width(), b.sizeHint().width())
    for a, b in zip(rects, rects[1:]):
        assert not a.intersects(b)
    wirt.close()


def test_executor_mindestbreite_aus_schrift(playback):
    e = playback._executors_widgets[0]
    f = QFont(e._fn_buttons[0].font())
    f.setPixelSize(10)
    f.setBold(True)
    fm = QFontMetrics(f)
    assert e.mindestbreite() >= 3 * fm.horizontalAdvance("GO")
    assert e.mindestbreite() >= fm.horizontalAdvance("— Leer —")
    assert e.minimumWidth() == e.mindestbreite()


def test_executor_leiste_scrollt_statt_zu_ueberlappen_wenn_zu_schmal(playback):
    """Mindestgröße unterschritten: die Leiste scrollt, nichts liegt
    übereinander, und die Bildlaufleiste verdeckt keine Tasten."""
    wirt = _im_wirt(playback, (700, 480))
    leiste = playback._exec_scroll
    assert leiste.scrollt()
    inhalt = leiste.widget()
    assert leiste.viewport().height() >= inhalt.minimumSizeHint().height()
    rects = [e.geometry() for e in playback._executors_widgets]
    for a, b in zip(rects, rects[1:]):
        assert not a.intersects(b)
    # Bei Mindestbreite bleiben die Tasten ungekürzt.
    for e in playback._executors_widgets:
        assert e.width() == e.mindestbreite()
        for b in e._fn_buttons:
            assert _text_passt(b), (b.text(), b.width(), b.sizeHint().width())
    wirt.close()


def test_executor_mindestbreite_reicht_fuer_alle_tastenbeschriftungen(playback):
    """Jede mögliche Belegung (GO/◀/■/FL) passt bei Mindestbreite — gemessen
    mit dem echten Tasten-Stylesheet, nicht nur mit der Textbreite."""
    wirt = _im_wirt(playback, KLEIN)
    e = playback._executors_widgets[0]
    b = e._fn_buttons[0]
    alt_text, alt_style = b.text(), b.styleSheet()
    breit = 0
    for text in e.BTN_LABELS.values():
        b.setText(text)
        for style in (e._fn_buttons[1].styleSheet(), alt_style):
            b.setStyleSheet(style)
            breit = max(breit, b.sizeHint().width())
    b.setText(alt_text)
    b.setStyleSheet(alt_style)
    m = e.layout().contentsMargins()
    tasten = 3 * breit + 2 * e._btn_row.spacing() + m.left() + m.right()
    assert e.mindestbreite() >= tasten, (e.mindestbreite(), tasten)
    wirt.close()


def test_langer_cuelisten_name_macht_executor_nicht_breiter(playback):
    """Gegenprüfung: ein 40 Zeichen langer Cuelisten-Name darf die
    Executor-Auswahl nicht aufziehen — sonst überlappen die Executoren bei
    1000 px bzw. Ex 10 fällt rechts heraus."""
    from src.core.app_state import get_state
    from src.core.engine.cue_stack import CueStack
    state = get_state()
    lang = CueStack("Sehr langer Cuelisten-Name für die Prüfung")
    assert len(lang.name) >= 40
    state.cue_stacks.append(lang)
    ex = state.playback_engine.get_executor(1)
    alt = ex.stack
    try:
        ex.stack = lang
        playback._refresh_executors()
        wirt = _im_wirt(playback, KLEIN)
        exe = playback._executors_widgets
        assert exe[0]._combo.currentText() == lang.name
        rects = [_rect_in(w, playback) for w in exe]
        for w, r in zip(exe, rects):
            assert w.visibleRegion().boundingRect() == w.rect(), f"Ex {w._slot}"
            assert playback.rect().contains(r), f"Ex {w._slot} ragt heraus: {r}"
        for a, b in zip(rects, rects[1:]):
            assert not a.intersects(b)
        assert not playback._exec_scroll.scrollt()
        wirt.close()
    finally:
        ex.stack = alt
        state.cue_stacks.remove(lang)


@pytest.mark.parametrize("groesse", [KLEIN, GROSS])
def test_optionen_loop_und_modus_ueberlappen_nicht(playback, groesse):
    wirt = _im_wirt(playback, groesse)
    rechts = playback._btn_loop.parentWidget().parentWidget()   # Optionen → Spalte
    # Die rechte Spalte wird nie unter ihre Mindesthöhe gequetscht — reicht
    # der Platz nicht, scrollt sie.
    assert rechts.height() >= rechts.minimumSizeHint().height()
    modus = [l for l in rechts.findChildren(QLabel) if l.text() == "Modus:"]
    assert len(modus) == 1
    loop = _rect_in(playback._btn_loop, rechts)
    lbl = _rect_in(modus[0], rechts)
    combo = playback._combo_mode
    assert isinstance(combo, QComboBox)
    rc = _rect_in(combo, rechts)
    assert not loop.intersects(lbl)
    assert not loop.intersects(rc)
    assert combo.height() >= combo.minimumSizeHint().height()
    assert rechts.rect().contains(rc)
    wirt.close()


def test_kein_leerraum_ueber_der_executor_leiste_bei_1440(playback):
    wirt = _im_wirt(playback, GROSS)
    titel = [l for l in playback.findChildren(QLabel) if l.text() == "Executor-Leiste:"]
    assert len(titel) == 1
    t = titel[0]
    # Die Beschriftung ist nicht höher als nötig, die Executoren folgen direkt.
    assert t.height() <= t.sizeHint().height() + 4
    ex1 = _rect_in(playback._executors_widgets[0], playback)
    abstand = ex1.top() - (t.y() + t.height())
    assert 0 <= abstand <= 20, abstand
    # Die Executoren enden unten an der Ansicht (kein Loch darunter).
    unten = playback.height() - ex1.bottom()
    assert unten <= 24, unten
    wirt.close()

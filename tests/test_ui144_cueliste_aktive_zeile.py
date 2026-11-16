"""UI-144: die laufende Cue der VC-Cueliste ist wieder farbig hinterlegt.

Seit UI-121 markiert ``VCCueList._markiere`` die laufende Cue nur noch per
``QListWidgetItem.setBackground`` (die Liste hat keine Auswahl mehr). Unter dem
App-Stylesheet (``assets/themes/dark.qss`` gestaltet ``QListWidget::item``)
malt Qt diesen Pinsel nicht — die Zeile war nur noch fett. Die Tests pruefen
deshalb PIXEL, und zwar MIT dem Stylesheet wie im Hauptfenster (ohne
Stylesheet trat der Fehler nicht auf). Dazu die Stichprobe: die Farb- und die
Dimmer-Sequenz-Liste hatten denselben Fehler (Schrittfarbe verschwand).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import Qt                                        # noqa: E402
from PySide6.QtGui import QColor                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget     # noqa: E402

from src.core.paths import programm_datei                            # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402

_app = QApplication.instance() or QApplication([])

import sys                                                           # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

BLAU = QColor("#1f6feb")


def _qss(touch: bool = False) -> str:
    with open(programm_datei("assets", "themes", "dark.qss"), encoding="utf-8") as f:
        qss = f.read()
    if touch:
        qss += "\n" + touch_keyboard.touch_qss()
    return qss


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt_touch = touch_keyboard.is_touch_mode()
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)


class _Cue:
    def __init__(self, n):
        self.number = float(n)
        self.label = f"Cue {n}"


class _Stack:
    def __init__(self, n=3):
        self.cues = [_Cue(i + 1) for i in range(n)]
        self.current_index = 0

    def go_to(self, nummer):
        pass


class _Ex:
    def __init__(self):
        self.stack = _Stack()


def _haupt(touch=False) -> QWidget:
    """Fenster mit dem App-Stylesheet, so wie ``MainWindow._apply_theme`` es setzt."""
    w = QWidget()
    w.setStyleSheet(_qss(touch))
    QVBoxLayout(w)
    w.resize(360, 420)
    return w


def _cueliste(touch=False):
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    haupt = _haupt(touch)
    c = VCCueList()
    c._refresh_timer.stop()
    ex = _Ex()
    c._executor = lambda: ex
    haupt.layout().addWidget(c)
    haupt.show()
    c._refresh()
    QApplication.processEvents()
    return haupt, c, ex


def _nah(a: QColor, b: QColor, tol=12) -> bool:
    return (abs(a.red() - b.red()) <= tol and abs(a.green() - b.green()) <= tol
            and abs(a.blue() - b.blue()) <= tol)


def _zeilenfarben(lw) -> list[QColor]:
    """Bildpunkt je Zeile: rechts in der Zeile, abseits des Textes."""
    QApplication.processEvents()
    bild = lw.viewport().grab().toImage()
    farben = []
    for r in range(lw.count()):
        rect = lw.visualItemRect(lw.item(r))
        farben.append(bild.pixelColor(rect.right() - 6, rect.center().y()))
    return farben


def _blaue_zeilen(c) -> list[int]:
    return [i for i, f in enumerate(_zeilenfarben(c._cue_list)) if _nah(f, BLAU)]


def test_laufende_cue_mit_app_stylesheet_blau():
    _h, c, _ex = _cueliste()
    assert c._cue_list.count() == 3
    assert c.aktive_zeile() == 0
    assert _blaue_zeilen(c) == [0]
    # weisse, fette Schrift wie bisher
    it = c._cue_list.item(0)
    assert it.font().bold()
    assert it.foreground().color() == QColor("#ffffff")
    assert not c._cue_list.item(1).font().bold()


def test_markierung_wandert_nach_go():
    _h, c, ex = _cueliste()
    ex.stack.current_index = 1
    c._refresh()
    assert c.aktive_zeile() == 1
    assert _blaue_zeilen(c) == [1]
    ex.stack.current_index = 2
    c._refresh()
    assert _blaue_zeilen(c) == [2]
    # die alte Zeile ist wieder normal (Schrift und Farbe)
    alt = c._cue_list.item(1)
    assert not alt.font().bold()
    assert alt.data(Qt.ItemDataRole.ForegroundRole) is None


def test_index_minus_eins_keine_zeile_markiert():
    _h, c, ex = _cueliste()
    ex.stack.current_index = -1
    c._refresh()
    assert c.aktive_zeile() == -1
    assert _blaue_zeilen(c) == []


def test_nach_neuaufbau_steht_markierung_wieder():
    _h, c, ex = _cueliste()
    ex.stack.current_index = 1
    c._refresh()
    ex.stack.cues[1].label = "Umbenannt"       # CDX-72: Signatur aendert sich
    c._refresh()
    assert "Umbenannt" in c._cue_list.item(1).text()
    assert c.aktive_zeile() == 1
    assert _blaue_zeilen(c) == [1]


def test_touch_stylesheet_markiert_ebenfalls():
    touch_keyboard.setze_touch_modus(True)
    _h, c, ex = _cueliste(touch=True)
    ex.stack.current_index = 2
    c._refresh()
    assert _blaue_zeilen(c) == [2]


def test_popout_fenster_markiert_ebenfalls():
    """Popout: die Liste wandert in ein eigenes Fenster (Kind des Hauptfensters)."""
    haupt, c, ex = _cueliste()
    pop = QWidget(haupt, Qt.WindowType.Window)
    QVBoxLayout(pop).addWidget(c)
    pop.resize(320, 380)
    pop.show()
    ex.stack.current_index = 1
    c._refresh()
    QApplication.processEvents()
    assert _blaue_zeilen(c) == [1]


def test_liste_bleibt_ohne_auswahl():
    from PySide6.QtWidgets import QListWidget
    _h, c, _ex = _cueliste()
    assert c._cue_list.selectionMode() == QListWidget.SelectionMode.NoSelection


# ── Stichprobe: Farb-/Dimmer-Sequenz-Liste (gleicher Fehler) ────────────────

class _Seq:
    def __init__(self, entries):
        self.entries = entries
        self.active_index = 0

    def __len__(self):
        return len(self.entries)


def _seq_liste(cls, entries):
    haupt = _haupt()
    w = cls()
    haupt.layout().addWidget(w)
    haupt.show()
    w.set_sequence(_Seq(entries))
    QApplication.processEvents()
    return haupt, w


def test_farbsequenz_zeigt_schrittfarbe_mit_stylesheet():
    from src.ui.widgets.color_sequence_editor import ColorSequenceEditor
    _h, w = _seq_liste(ColorSequenceEditor,
                       [((255, 0, 0), True), ((0, 255, 0), True), ((0, 0, 255), False)])
    farben = _zeilenfarben(w._list)
    # Zeile 0 ist die aktuelle (Auswahl des Themes), Zeile 1 traegt ihre Farbe
    assert _nah(farben[1], QColor(0, 255, 0))
    # ausgeschalteter Schritt bekommt keine Farbe
    assert not _nah(farben[2], QColor(0, 0, 255))


def test_dimmersequenz_zeigt_stufe_mit_stylesheet():
    from src.ui.widgets.dimmer_sequence_editor import DimmerSequenceEditor
    _h, w = _seq_liste(DimmerSequenceEditor, [(200, True), (60, True)])
    farben = _zeilenfarben(w._list)
    assert _nah(farben[1], QColor(60, 60, 60), tol=4)

"""UI-97: E/A → MIDI bei kleinem Fenster (1000×640).

Vorher lagen im Feld „MIDI-Geräte“ Auswahlfelder, Knöpfe, Häkchen und Status
übereinander, die Mapping-Tabelle schrumpfte auf ihre Kopfzeile und die
Schnell-Vorlagen-Knöpfe verschwanden. Jetzt scrollt die Seite.

Nachgestellt wird das Hauptfenster, das der Seite weniger Platz gibt, als ihr
Inhalt mindestens braucht: die View hängt OHNE Layout in einem Host fester
Größe (wie im Tab des Hauptfensters wird sie so unter ihre Mindestgröße
gedrückt). Kein echtes MIDI-Gerät — dieselben Attrappen wie test_midi_view.
"""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGroupBox, QLabel, QPushButton,
    QScrollArea, QWidget)

from src.ui.views import midi_view as midi_ui
from test_midi_view import _FakeMidi, _FakeMtcReader, _FakeState
from _qt_lifecycle import destroy_all_top_level_widgets


@pytest.fixture(autouse=True)
def _keine_restfenster():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# 1000×640 = ganzes Fenster; 940×470 ≈ Platz der Seite im Hauptfenster
# bei 1000×640 (Navigation, Sub-Tabs und Statusleiste gehen ab).
GROESSEN = [(1000, 640), (940, 470)]


def _view_im_host(monkeypatch, w, h):
    _app()
    monkeypatch.setattr(midi_ui, "get_midi_manager", lambda: _FakeMidi())
    monkeypatch.setattr(midi_ui, "get_state", lambda: _FakeState())
    monkeypatch.setattr(midi_ui, "get_mtc_reader", lambda: _FakeMtcReader())
    host = QWidget()
    host.resize(w, h)
    view = midi_ui.MidiView(host)
    view.setGeometry(0, 0, w, h)
    host.show()
    for _ in range(5):
        _app().processEvents()
    return host, view


def _geraete_box(view) -> QGroupBox:
    for box in view.findChildren(QGroupBox):
        if box.title() == "MIDI-Geräte":
            return box
    raise AssertionError("Gruppe „MIDI-Geräte“ fehlt")


def _knopf(view, text) -> QPushButton:
    for b in view.findChildren(QPushButton):
        if b.text() == text:
            return b
    raise AssertionError(f"Knopf „{text}“ fehlt")


@pytest.mark.parametrize("w,h", GROESSEN)
def test_geraete_felder_haben_mindesthoehe_und_ueberlappen_nicht(monkeypatch, w, h):
    host, view = _view_im_host(monkeypatch, w, h)
    box = _geraete_box(view)
    felder = [c for c in box.findChildren(QWidget)
              if isinstance(c, (QComboBox, QPushButton, QCheckBox, QLabel))
              and c.isVisibleTo(box)]
    assert len(felder) >= 9, [f.text() if hasattr(f, "text") else f for f in felder]
    rechtecke = []
    for f in felder:
        mind = f.minimumSizeHint().height()
        assert f.height() >= mind, (
            f"{type(f).__name__} „{getattr(f, 'text', lambda: '')()}“ "
            f"nur {f.height()} px hoch, braucht {mind}")
        rechtecke.append((f, QRect(f.mapTo(box, f.rect().topLeft()), f.size())))
    for i, (a, ra) in enumerate(rechtecke):
        for b, rb in rechtecke[i + 1:]:
            assert not ra.intersects(rb), (
                f"überlappen: {getattr(a, 'text', lambda: '')()!r} / "
                f"{getattr(b, 'text', lambda: '')()!r}")


@pytest.mark.parametrize("w,h", GROESSEN)
def test_tabelle_zeigt_mindestens_drei_zeilen(monkeypatch, w, h):
    host, view = _view_im_host(monkeypatch, w, h)
    t = view._map_table
    zeilen = t.verticalHeader().defaultSectionSize()
    platz = t.viewport().height()
    assert platz >= 3 * zeilen, f"Tabelle hat nur {platz} px für Zeilen (< 3×{zeilen})"


@pytest.mark.parametrize("w,h", GROESSEN)
def test_schnell_vorlagen_erreichbar(monkeypatch, w, h):
    host, view = _view_im_host(monkeypatch, w, h)
    scroll = view.findChild(QScrollArea)
    assert scroll is not None, "MIDI-Seite hat keinen Scrollbereich"
    for text in ("CC1-10 → Executor-Fader 1-10", "Note 0-9 → Executor GO 1-10"):
        b = _knopf(view, text)
        assert b.height() >= b.minimumSizeHint().height(), f"„{text}“ gequetscht"
        scroll.ensureWidgetVisible(b)
        _app().processEvents()
        assert not b.visibleRegion().isEmpty(), f"„{text}“ auch per Scrollen nicht sichtbar"
        assert b.visibleRegion().boundingRect().height() >= b.minimumSizeHint().height()


def test_seite_nutzt_grosses_fenster_ohne_scrollen(monkeypatch):
    """Gegenstück: bei 1440×900 passt alles, kein senkrechter Rollbalken."""
    host, view = _view_im_host(monkeypatch, 1440, 900)
    scroll = view.findChild(QScrollArea)
    assert scroll is not None
    assert not scroll.verticalScrollBar().isVisible()


def test_spaltenkoepfe_deutsch_mit_tooltips(monkeypatch):
    host, view = _view_im_host(monkeypatch, 1440, 900)
    t = view._map_table
    koepfe = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert koepfe == ["Name", "Ziel", "Typ", "Kanal", "Daten 1",
                      "Modus", "An", "Aus", "Port"]
    for c in range(t.columnCount()):
        assert t.horizontalHeaderItem(c).toolTip().strip(), koepfe[c]

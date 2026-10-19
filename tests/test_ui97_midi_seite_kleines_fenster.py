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
    QScrollArea, QSplitter, QWidget)

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


# 1380×730 ≈ Platz der Seite im Hauptfenster bei 1440×900 (gleicher Abzug
# für Navigation, Sub-Tabs und Statusleiste wie bei 940×470).
SEITE_1440x900 = (1380, 730)


def test_seite_nutzt_grosses_fenster_ohne_scrollen(monkeypatch):
    """Gegenstück: bei 1440×900 passt alles, kein senkrechter Rollbalken —
    auch die letzte Zeile (MSC-Hinweis) liegt im sichtbaren Bereich."""
    host, view = _view_im_host(monkeypatch, *SEITE_1440x900)
    scroll = view.findChild(QScrollArea)
    assert scroll is not None
    inhalt = scroll.widget()
    assert inhalt.minimumSizeHint().height() <= SEITE_1440x900[1], (
        f"Inhalt braucht {inhalt.minimumSizeHint().height()} px, "
        f"Seite hat {SEITE_1440x900[1]}")
    assert not scroll.verticalScrollBar().isVisible()
    assert scroll.verticalScrollBar().maximum() == 0
    for b in (view._btn_tmpl_faders, view._btn_tmpl_notes):
        assert b.visibleRegion().boundingRect().height() == b.height()


@pytest.mark.parametrize("w,h", GROESSEN + [SEITE_1440x900])
def test_splitter_klappt_die_tabelle_nicht_ein(monkeypatch, w, h):
    """Den senkrechten Splitter kann man nicht auf null zuziehen."""
    host, view = _view_im_host(monkeypatch, w, h)
    splitter = view.findChild(QSplitter)
    assert splitter is not None
    assert not splitter.childrenCollapsible()
    splitter.setSizes([10_000, 0])
    _app().processEvents()
    t = view._map_table
    assert t.height() >= t.minimumHeight() > 0
    assert t.viewport().height() >= 3 * t.verticalHeader().defaultSectionSize()
    splitter.setSizes([0, 10_000])
    _app().processEvents()
    geraete = _geraete_box(view)
    assert geraete.height() >= geraete.minimumSizeHint().height()


def test_feedback_texte_sagen_an_aus(monkeypatch):
    """Spaltenköpfe „An“/„Aus“ — Tooltip und Dialoge nennen dasselbe."""
    host, view = _view_im_host(monkeypatch, *SEITE_1440x900)
    assert _knopf(view, "Feedback...").toolTip() == "LED-Farben für An/Aus (Velocity) setzen"
    fragen = []

    def _get_int(_parent, titel, text, *a, **k):
        fragen.append((titel, text))
        return 0, True
    monkeypatch.setattr(midi_ui.QInputDialog, "getInt", _get_int)
    mapping = midi_ui.MidiMapping(name="x", msg_type="note_on", channel=1, data1=5)
    view._prompt_feedback_values(mapping)   # nur die Abfrage, keine Mapper-Daten
    assert fragen, "Feedback-Dialog nicht erreicht"
    for titel, text in fragen:
        assert "ON" not in titel + text and "OFF" not in titel + text, (titel, text)


def test_spaltenkoepfe_deutsch_mit_tooltips(monkeypatch):
    host, view = _view_im_host(monkeypatch, 1440, 900)
    t = view._map_table
    koepfe = [t.horizontalHeaderItem(c).text() for c in range(t.columnCount())]
    assert koepfe == ["Name", "Ziel", "Typ", "Kanal", "Daten 1",
                      "Modus", "An", "Aus", "Port"]
    for c in range(t.columnCount()):
        assert t.horizontalHeaderItem(c).toolTip().strip(), koepfe[c]

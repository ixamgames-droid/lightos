"""UI-137: Funde aus dem Klick-Test der Oberflaeche (Maus und Touch).

1. Virtuelle Konsole, „Alle löschen" in der Bearbeiten-Leiste loeschte alle
   Widgets sofort — ohne Rueckfrage und ohne Rueckgaengig-Stand.
2. STOP ALL/BLACKOUT: rote Schrift auf dunkelrotem Grund in 11 px, schlecht
   lesbar; beide Knoepfe klebten aneinander.
3. TAP war im Touch-Modus abgeschnitten („TAF").

Rueckfragen werden ueber eine Attrappe beantwortet, nie ueber einen echten
modalen Dialog. Hauptfenster mit Wegwerf-Daten aus conftest.
"""
from __future__ import annotations

import os
import re
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtGui import QFontMetrics                               # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

from src.ui import touch_keyboard                                    # noqa: E402
from src.ui.views import virtual_console_view as vcv                 # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas                 # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_WURZEL = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt_touch = touch_keyboard.is_touch_mode()
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)


# ── 1. Alle loeschen ────────────────────────────────────────────────────────

def _konsole(n=3):
    c = VCCanvas()
    c.resize(1200, 800)
    for i in range(n):
        c._add_widget("VCButton", QPoint(40 + i * 200, 40))
    c.set_edit_mode(True)
    c._undo_stack.clear()
    c._undo_marken.clear()
    ansicht = types.SimpleNamespace(_edit_mode=True, _canvas=c)
    return ansicht, c


def _anzahl(c) -> int:
    QApplication.processEvents()
    return len([w for w in c.findChildren(VCWidget) if w.parent() is c])


def test_alle_loeschen_abbrechen_loescht_nichts(monkeypatch):
    ansicht, c = _konsole(3)
    fragen = []
    monkeypatch.setattr(vcv, "_frage_alle_loeschen",
                        lambda parent, n: fragen.append(n) or False, raising=False)
    vcv.VirtualConsoleView._clear_all(ansicht)
    assert fragen == [3]
    assert _anzahl(c) == 3


def test_alle_loeschen_bestaetigt_mit_rueckgaengig(monkeypatch):
    ansicht, c = _konsole(3)
    monkeypatch.setattr(vcv, "_frage_alle_loeschen", lambda parent, n: True,
                        raising=False)
    vcv.VirtualConsoleView._clear_all(ansicht)
    assert _anzahl(c) == 0
    assert c.can_undo() if hasattr(c, "can_undo") else c._undo_stack
    c.undo()
    assert _anzahl(c) == 3


def test_alle_loeschen_leer_ohne_rueckfrage(monkeypatch):
    ansicht, c = _konsole(0)
    fragen = []
    monkeypatch.setattr(vcv, "_frage_alle_loeschen",
                        lambda parent, n: fragen.append(n) or False, raising=False)
    vcv.VirtualConsoleView._clear_all(ansicht)
    assert fragen == []


@pytest.mark.parametrize("touch", [False, True])
def test_rueckfrage_texte_vorgabe_und_touch_hoehe(touch):
    touch_keyboard.setze_touch_modus(touch)
    box = vcv._alle_loeschen_box(None, 5)
    assert "Alle 5 Elemente der Virtuellen Konsole löschen?" in box.text()
    texte = {b.text(): b for b in box.buttons()}
    assert set(texte) == {"Löschen", "Abbrechen"}
    assert box.defaultButton() is texte["Abbrechen"]
    assert box.escapeButton() is texte["Abbrechen"]
    if touch:
        for b in box.buttons():
            assert b.minimumHeight() >= 44
    box.deleteLater()


def test_knopf_alle_loeschen_abgesetzt():
    quelle = (_WURZEL / "src/ui/views/virtual_console_view.py").read_text(encoding="utf-8")
    i = quelle.index('btn_clear = QPushButton("Alle löschen")')
    block = quelle[i:i + 600]
    m = re.search(r"margin:\s*0\s+(\d+)px", block)
    assert m and int(m.group(1)) >= 8


# ── 2. STOP ALL / BLACKOUT lesbar ──────────────────────────────────────────

def _lum(hexfarbe: str) -> float:
    h = hexfarbe.lstrip("#")
    kan = []
    for k in (h[0:2], h[2:4], h[4:6]):
        v = int(k, 16) / 255
        kan.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * kan[0] + 0.7152 * kan[1] + 0.0722 * kan[2]


def _kontrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _regel(selektor: str) -> str:
    qss = (_WURZEL / "assets/themes/dark.qss").read_text(encoding="utf-8")
    m = re.search(re.escape(selektor) + r"\s*\{([^}]*)\}", qss)
    assert m, selektor
    return m.group(1)


@pytest.mark.parametrize("selektor", ["QPushButton#blackoutBtn",
                                      "QPushButton#blackoutBtn:checked"])
def test_sicherheitsknoepfe_kontrast(selektor):
    regel = _regel(selektor)
    grund = _regel("QPushButton#blackoutBtn")
    farbe = re.search(r"(?<![-\w])color:\s*(#[0-9a-fA-F]{6})", regel).group(1)
    flaechen = re.findall(r"#[0-9a-fA-F]{6}",
                          re.search(r"background[^;]*;", regel, re.S).group(0))
    assert flaechen
    for f in flaechen:
        assert _kontrast(farbe, f) >= 4.5, (selektor, farbe, f)
    px = int(re.search(r"font-size:\s*(\d+)px", grund).group(1))
    assert px >= 13
    assert "font-weight: bold" in grund


# ── Hauptfenster (Kopfleiste) ──────────────────────────────────────────────

def _fenster(touch: bool):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=touch)
    w._hw_timer.stop()
    w.resize(1440, 900)
    w.show()
    for _ in range(5):
        QApplication.processEvents()
    return w


@pytest.mark.parametrize("touch", [False, True])
def test_kopfleiste_stop_blackout_abstand_und_tap(touch):
    w = _fenster(touch)
    try:
        stop, bo = w._btn_stop_all, w._btn_blackout
        abstand = bo.mapTo(w, QPoint(0, 0)).x() - (stop.mapTo(w, QPoint(0, 0)).x()
                                                   + stop.width())
        assert abstand >= 6, abstand
        # Groesse der Sicherheitsknoepfe nicht kleiner als vorher
        assert stop.width() >= 78 and bo.width() >= 88
        assert stop.height() >= 26 and bo.height() >= 26

        tap = w._btn_tap
        tap.ensurePolished()
        text_b = QFontMetrics(tap.font()).horizontalAdvance("TAP")
        assert text_b + 8 <= tap.width(), (text_b, tap.width())
        assert tap.sizeHint().width() <= tap.width(), (tap.sizeHint(), tap.width())
    finally:
        w.hide()
        w.deleteLater()
        QApplication.processEvents()


def test_rueckfrage_typ():
    # _alle_loeschen_box liefert eine echte QMessageBox (nicht ausgefuehrt)
    box = vcv._alle_loeschen_box(None, 2)
    assert isinstance(box, QMessageBox)
    box.deleteLater()


# Nachbesserung nach Pruefung: die Reiternamen wie vor UI-137 (gemessen am
# Stand vor UI-137). TAP polierte ohne Eltern mit dem Stil-Minimum (80 px) und
# kuerzte im Touch-Modus „Bühne“ zu „Büh…“ (1280 px) und „Patchen“ zu „Patch“
# (1440 px).
_NAMEN_VORHER = {
    (False, 1280): ["Bühne", "Patch", "Prog", "VC", "Desk", "Play", "E/A", "BPM"],
    (False, 1366): ["Bühne", "Patchen", "Prog", "VC", "Desk", "Playback", "E/A", "BPM"],
    (False, 1440): ["Bühne", "Patchen", "Programmer", "Virtual Console", "Simple Desk",
                    "Playback", "E/A", "BPM"],
    (True, 1280): ["Bühne", "Patch", "Prog", "VC", "Desk", "Play", "E/A", "BPM"],
    (True, 1366): ["Bühne", "Patch", "Prog", "VC", "Desk", "Play", "E/A", "BPM"],
    (True, 1440): ["Bühne", "Patchen", "Prog", "VC", "Desk", "Play", "E/A", "BPM"],
}


@pytest.mark.parametrize("touch", [False, True])
def test_reiternamen_wie_vorher_und_tap_schmal(touch):
    w = _fenster(touch)
    try:
        assert w._btn_tap.width() == 48
        for breite in (1280, 1366, 1440):
            w.resize(breite, 900)
            for _ in range(10):
                QApplication.processEvents()
            namen = [b.text() for b in w._section_btns]
            assert namen == _NAMEN_VORHER[(touch, breite)], (breite, namen)
    finally:
        w.hide()
        w.deleteLater()
        QApplication.processEvents()

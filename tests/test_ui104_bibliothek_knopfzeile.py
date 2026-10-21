"""UI-104 — Programmer, Bibliothek rechts: zweite Knopfzeile ganz sichtbar.

Befund (Sitzung D, Windows; im Sandkasten nachgestellt): In der Knopfleiste
der Bibliothek („Speichern“ … „Löschen“, „↻“) war die zweite Zeile unten
4 px abgeschnitten, „↻“ war nur 24 px breit und nur als „:“ zu erkennen.

Ursache: ``setFixedHeight(24)``/``setFixedSize(24, 24)`` gegen das dunkle
Theme (``min-height: 22px`` + ``padding: 4px 10px`` + Rahmen = 32 px). Das
Stylesheet hob die Mindesthöhe auf 32, die Höchsthöhe blieb 24; das
Flow-Layout plante 32-px-Zeilen, ``QWidgetItem`` mittete die 24-px-Vorgabe
darin und setzte die Knöpfe so 4 px tiefer — die zweite Zeile ragte 4 px aus
der Leiste. Die feste Breite 24 ließ hinter 2×10 px Innenabstand vom
Zeichen „↻“ nur einen Strich übrig.

Geprüft wird bei den Ansichtsgrößen für 1000×640 und 1440×900 (wie UI-98);
125/150 % (``QT_SCALE_FACTOR``) ändern die logischen Maße nicht und wurden
im Sandkasten per Bild geprüft.
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
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

KLEIN = (1000, 480)
GROSS = (1440, 740)
_LEISTE = ("Speichern", "Ordner +", "Anwenden", "Chase +", "Löschen", "↻")


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _qss() -> str:
    return (ROOT / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")


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


def _im_wirt(view: QWidget, groesse: tuple[int, int]) -> QWidget:
    app = _app()
    wirt = QWidget()
    wirt.setStyleSheet(_qss())
    view.setParent(wirt)
    wirt.resize(*groesse)
    view.setGeometry(0, 0, *groesse)
    wirt.show()
    for _ in range(6):
        app.processEvents()
    return wirt


def _knoepfe(panel: QWidget) -> dict[str, QPushButton]:
    return {b.text(): b for b in panel.findChildren(QPushButton)
            if b.text() in _LEISTE}


def _rect_in(w: QWidget, bezug: QWidget) -> QRect:
    return QRect(w.mapTo(bezug, w.rect().topLeft()), w.size())


@pytest.mark.parametrize("groesse", [KLEIN, GROSS])
def test_knopfzeilen_ganz_in_der_leiste(programmer, groesse):
    wirt = _im_wirt(programmer, groesse)
    panel = programmer._snap_file_panel
    knoepfe = _knoepfe(panel)
    assert set(knoepfe) == set(_LEISTE)
    leiste = knoepfe["Löschen"].parentWidget()
    # Bei 320 px Bibliotheksbreite bricht die Leiste zweizeilig um.
    ys = {b.y() for b in knoepfe.values()}
    assert len(ys) >= 2, ys
    for text, b in knoepfe.items():
        r = _rect_in(b, leiste)
        assert leiste.rect().contains(r), (
            f"„{text}“ ragt aus der Leiste: {r.getRect()} in "
            f"{leiste.rect().getRect()}")
        # Nichts verdeckt den Knopf: der Baum beginnt erst darunter.
        baum = _rect_in(panel._tree, panel)
        assert not _rect_in(b, panel).intersects(baum), text
    wirt.close()


@pytest.mark.parametrize("groesse", [KLEIN, GROSS])
def test_knoepfe_nicht_unter_wunschgroesse(programmer, groesse):
    """Keine feste Höhe/Breite unter dem, was Theme und Schrift brauchen."""
    wirt = _im_wirt(programmer, groesse)
    for text, b in _knoepfe(programmer._snap_file_panel).items():
        assert b.height() >= b.sizeHint().height(), (text, b.height())
        assert b.width() >= b.sizeHint().width(), (text, b.width())
        assert b.maximumHeight() >= b.sizeHint().height(), text
        assert b.minimumHeight() <= b.maximumHeight(), text
    wirt.close()


def test_aktualisieren_knopf_mindestens_32_px_und_zeichen_passt(programmer):
    wirt = _im_wirt(programmer, KLEIN)
    b = _knoepfe(programmer._snap_file_panel)["↻"]
    fm = QFontMetrics(b.font())
    assert b.width() >= 32, b.width()
    # Innenabstand 2×10 + Rahmen 2×1 aus dark.qss plus das Zeichen selbst.
    assert b.width() >= fm.horizontalAdvance("↻") + 22, b.width()
    assert b.minimumWidth() >= 32
    assert b.toolTip() == "Aktualisieren"
    wirt.close()


def test_mindesthoehe_aus_fontmetrics():
    """Auch ohne Theme: Mindesthöhe folgt der Schrift (größere Schrift bei
    125/150 % oder Touch-QSS -> höherer Knopf), kein festes Höchstmaß."""
    _app()
    from PySide6.QtGui import QFont
    from src.ui.views.snap_file_panel import _knopf_mindestmass
    for punkt in (9, 14, 20):
        b = QPushButton("↻")
        f = QFont(b.font())
        f.setPointSize(punkt)
        b.setFont(f)
        _knopf_mindestmass(b, symbol=True)
        fm = b.fontMetrics()
        assert b.minimumHeight() >= fm.height() + 8, punkt
        assert b.minimumWidth() >= max(32, fm.horizontalAdvance("↻") + 22), punkt
        assert b.maximumHeight() > 1000 and b.maximumWidth() > 1000, punkt


# ── Gegenprüfung: Touch-Modus und Snapshots-Ansicht ─────────────────────────
# Unter der Touch-QSS (Knöpfe 52 px hoch) und schmaler Bibliothek bricht die
# Leiste in viele Zeilen um. FlowLayout.minimumSize() meldete nur die Größe
# des größten Einzelknopfs; jenseits des QSplitter wird heightForWidth nicht
# weitergereicht, das Eltern-Layout staucht die Leiste also unter ihre
# Zeilenhöhe — „↻“ wurde zum Strich über dem Baumkopf, „Löschen“ ragte in
# den Baum.

def _touch_qss() -> str:
    from src.ui.main_window import MainWindow

    class _Attrappe(QWidget):
        _touch_mode = True

    a = _Attrappe()
    MainWindow._apply_theme(a)
    qss = a.styleSheet()
    a.deleteLater()
    assert "Touch-Mode Override" in qss
    return qss


@pytest.fixture
def snapshots_view():
    _app()
    from src.ui.views.snapshots_view import SnapshotsView
    view = SnapshotsView()
    yield view
    if shiboken6.isValid(view):
        view.close()


@pytest.mark.parametrize("groesse", [(1000, 500), (1100, 560), (1440, 760)])
def test_touch_snapshots_leiste_nicht_gestaucht(snapshots_view, groesse):
    app = _app()
    wirt = QWidget()
    wirt.setStyleSheet(_touch_qss())
    snapshots_view.setParent(wirt)
    wirt.resize(*groesse)
    snapshots_view.setGeometry(0, 0, *groesse)
    wirt.show()
    for _ in range(10):
        app.processEvents()
    panel = snapshots_view._snap_file_panel
    knoepfe = _knoepfe(panel)
    assert set(knoepfe) == set(_LEISTE)
    leiste = knoepfe["Löschen"].parentWidget()
    baum = _rect_in(panel._tree, panel)
    for text, b in knoepfe.items():
        assert b.height() >= b.minimumHeight(), (text, b.height())
        r = _rect_in(b, leiste)
        assert leiste.rect().contains(r), (
            f"„{text}“ ragt aus der Leiste: {r.getRect()} in "
            f"{leiste.rect().getRect()} ({groesse})")
        assert not _rect_in(b, panel).intersects(baum), (text, groesse)
    wirt.close()


def test_flowlayout_mindesthoehe_folgt_umbruch():
    """FlowLayout meldet bei bekannter Breite die umbrochene Höhe als
    Mindesthöhe — nicht nur die Höhe des größten Einzelknopfs."""
    app = _app()
    from src.ui.widgets.flow_layout import FlowLayout
    wirt = QWidget()
    fl = FlowLayout(wirt, margin=0, h_spacing=4, v_spacing=4)
    for t in _LEISTE:
        b = QPushButton(t)
        b.setFixedSize(80, 30)
        fl.addWidget(b)
    wirt.resize(90, 400)
    wirt.show()
    app.processEvents()
    fl.setGeometry(QRect(0, 0, 90, 400))
    # Sechs Zeilen à 30 px + 5×4 px Abstand.
    assert fl.heightForWidth(90) == 200
    assert fl.minimumSize().height() >= 200, fl.minimumSize()
    wirt.close()


def test_touch_snapshots_bibliothek_zwei_knoepfe_je_zeile(snapshots_view):
    """Snapshots-Ansicht: das 12-spaltige Raster darf die Bibliothek nicht auf
    Knopfbreite drücken (sechs Zeilen à 52 px unter Touch-QSS)."""
    app = _app()
    wirt = QWidget()
    wirt.setStyleSheet(_touch_qss())
    snapshots_view.setParent(wirt)
    wirt.resize(1000, 500)
    snapshots_view.setGeometry(0, 0, 1000, 500)
    wirt.show()
    for _ in range(10):
        app.processEvents()
    knoepfe = _knoepfe(snapshots_view._snap_file_panel)
    zeilen = {b.y() for b in knoepfe.values()}
    assert len(zeilen) <= 3, sorted(zeilen)
    wirt.close()

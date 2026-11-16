"""UI-141 Fund 10 (Klick-Test 16.11.2026): Fixture-Gruppen bei 1280x800 im
Touch-Modus.

Die linke Spalte (Gruppenwahl, sechs Knoepfe, „Matrizen zusammenlegen…",
Geraetebaum, vier weitere Knoepfe) war ein festes 260 px breites QVBoxLayout
ohne Bildlauf. Bei 800 px Bildschirmhoehe reicht der Platz nicht fuer die
Touch-Hoehen (QSS ``min-height: 38px``) — Qt quetschte die Knoepfe unter ihre
Mindesthoehe, sie lagen uebereinander und „Matrizen zusammenlegen…" ueberdeckte
die Ueberschrift des Baums. „Weiß-Segmente einzeln → Raster ▾" passte mit
Touch-Innenabstand nicht in 260 px und wurde links abgeschnitten.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                          # noqa: E402
from PySide6.QtWidgets import (                                        # noqa: E402
    QAbstractButton, QApplication, QLabel, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets               # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(QApplication.instance())


def _hauptfenster_qss(touch: bool) -> str:
    from src.ui.main_window import MainWindow
    fang: dict = {}
    fake = SimpleNamespace(_touch_mode=touch, setStyleSheet=lambda q: fang.setdefault("q", q))
    MainWindow._apply_theme(fake)
    return fang["q"]


def _gruppen_ansicht(touch: bool, hoehe: int):
    tk.setze_touch_modus(touch)
    from src.ui.views.fixture_group_view import FixtureGroupView
    host = QWidget()
    host.setStyleSheet(_hauptfenster_qss(touch))
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    v = FixtureGroupView()
    lay.addWidget(v)
    # 1280x800-Bildschirm: Menue, Kopfleiste, Unterreiter, Befehlszeile und
    # Statuszeile lassen dem Reiter rund 585 px (gemessen im Klick-Test-Bild).
    host.setFixedSize(1280, hoehe)
    host.show()
    for _ in range(3):
        QApplication.processEvents()
    return host, v


def _linke_knoepfe(v):
    """Alle sichtbaren Knoepfe der linken Spalte (links vom Raster)."""
    grenze = v._grid_widget.mapTo(v, v._grid_widget.rect().topLeft()).x()
    out = []
    for b in v.findChildren(QAbstractButton):
        if not b.isVisible():
            continue
        pos = b.mapTo(v, b.rect().topLeft())
        if pos.x() < grenze:
            out.append(b)
    return out


def _rechteck(w, bezug):
    p = w.mapTo(bezug, w.rect().topLeft())
    r = w.rect()
    r.moveTopLeft(p)
    return r


@pytest.mark.parametrize("touch,hoehe", [(True, 585), (False, 585), (True, 440)])
def test_knoepfe_ueberlappen_nicht_und_behalten_ihre_hoehe(touch, hoehe):
    host, v = _gruppen_ansicht(touch, hoehe)
    knoepfe = _linke_knoepfe(v)
    assert len(knoepfe) >= 11, [b.text() for b in knoepfe]
    # Bezug = der gemeinsame Inhalt (auch wenn er in einer Bildlaufflaeche liegt)
    bezug = v
    for b in knoepfe:
        assert b.height() >= b.minimumSizeHint().height(), (
            b.text(), b.height(), b.minimumSizeHint().height())
        if touch:
            assert b.height() >= 44 - 6, (b.text(), b.height())   # QSS 38 + Rahmen
    for i, a in enumerate(knoepfe):
        for b in knoepfe[i + 1:]:
            ra, rb = _rechteck(a, bezug), _rechteck(b, bezug)
            assert not ra.intersects(rb), (a.text(), ra, b.text(), rb)
    # „Matrizen zusammenlegen…" ueberdeckt die Baum-Ueberschrift nicht mehr
    titel = [lab for lab in v.findChildren(QLabel)
             if lab.text().startswith("Fixtures (drag")][0]
    merge = [b for b in knoepfe if "Matrizen" in b.text()][0]
    assert not _rechteck(merge, bezug).intersects(_rechteck(titel, bezug))
    # Die Spalte wird nicht rechts von der Bildlaufleiste angeschnitten
    sc = v._left_scroll
    assert sc.viewport().width() >= sc.widget().width(), (
        sc.viewport().width(), sc.widget().width())
    # Der Geraetebaum bleibt benutzbar (nicht auf null gequetscht)
    assert v._fixture_list.height() >= 120, v._fixture_list.height()


@pytest.mark.parametrize("touch", [True, False])
def test_beschriftungen_passen_in_die_knoepfe(touch):
    host, v = _gruppen_ansicht(touch, 585)
    for b in _linke_knoepfe(v):
        assert b.sizeHint().width() <= b.width(), (b.text(), b.sizeHint().width(), b.width())


def test_weiss_knopf_heisst_weiter_wie_in_der_anleitung():
    """Die Anleitungen nennen den Knopf woertlich — der Text bleibt gleich,
    im Touch-Modus darf er nur umbrechen."""
    host, v = _gruppen_ansicht(True, 585)
    from src.core.group_cells import ACHSE_WEISS
    txt = " ".join(v._btn_achse[ACHSE_WEISS].text().split())
    assert txt == "Weiß-Segmente einzeln → Raster ▾"

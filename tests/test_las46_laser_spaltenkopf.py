"""LAS-46 — Laser-Reiter: Kopf der Spalte „Vorschau & Position“ ganz lesbar.

Sichtprobe (Windows 11, 100/125/150 %): Ueberschrift „VORSCHAU & POSITIO…“
und Hinweis „zeigt den ersten von 2 Laser…“ teilten sich eine Zeile in der
280 px breiten Spalte; beide Labels bekamen 138 px, brauchten aber 143–152 px.
Jetzt steht der Hinweis unter der Ueberschrift und darf umbrechen.

Geprueft wird die benoetigte Textbreite (QFontMetrics.horizontalAdvance)
gegen die tatsaechliche Label-Breite — auch mit Schrift x1.5 als Ersatz fuer
150 % Skalierung. Offscreen, keine Show-DB, kein DMX-Interface.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402

import test_las34_laser_tab as T  # noqa: E402

_HINWEISE = ("ziehen zum Verschieben", "zeigt den ersten von 2 Lasern",
             "zeigt den ersten von 12 Lasern")


def _ganz_lesbar(lbl: QLabel) -> None:
    """Jeder Text muss ganz in sein Label passen: einzeilig die volle
    Textbreite, mit Umbruch jedes Wort und die noetige Hoehe."""
    fm = QFontMetrics(lbl.font())
    text = lbl.text()
    if lbl.wordWrap():
        for wort in text.split():
            assert fm.horizontalAdvance(wort) <= lbl.width(), (text, wort)
        assert lbl.height() >= lbl.heightForWidth(lbl.width()), text
    else:
        assert fm.horizontalAdvance(text) <= lbl.width(), (
            text, fm.horizontalAdvance(text), lbl.width())


def _kopf_labels(v):
    return [lbl for lbl in v._lage_box.findChildren(QLabel)
            if lbl.text() and lbl.text().upper() == lbl.text()
            and len(lbl.text()) > 3] + [v._lbl_lage_hinweis]


@pytest.mark.parametrize("faktor", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("hinweis", _HINWEISE)
def test_spaltenkopf_ganz_lesbar(monkeypatch, faktor, hinweis):
    v, _st = T._view(monkeypatch, [T._FX(1, T._el400()),
                                   T._FX(2, T._el400())])
    labels = _kopf_labels(v)
    assert [l.text() for l in labels][0] == "VORSCHAU & POSITION"
    # Der echte Resync-Pfad setzt den Hinweis (n = 2), erst dann ueberschreiben.
    assert v._lbl_lage_hinweis.text() == "zeigt den ersten von 2 Lasern"
    px = round(11 * faktor)
    for lbl in labels:
        lbl.setStyleSheet(lbl.styleSheet().replace("font-size:11px",
                                                   f"font-size:{px}px"))
    v._lbl_lage_hinweis.setText(hinweis)
    v.resize(1400, 900)
    v.show()
    for _ in range(3):
        T._app().processEvents()
    assert v._lage_box.width() == v._lage_box.maximumWidth()   # Spalte fest
    for lbl in labels:
        assert lbl.font().pixelSize() == px
        _ganz_lesbar(lbl)
    v.close()

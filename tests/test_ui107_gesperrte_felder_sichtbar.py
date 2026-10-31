"""UI-107 — gesperrte Zahlenfelder sehen im dunklen Design gesperrt aus.

Befund (Bildpruefung DOC-76): Im Ausgabe-Dialog, Kasten „Fernsteuerung (Pult
steuert LightOS)", waren die gesperrten Felder „Executor" (Ziel Grand Master)
und „Schwelle" (Ziel Fader/Grand Master) pixelgleich mit den freien — Grund
#555555 (85,85,85), weisse Schrift. Die Anleitung (Schritt 4) verspricht dort
„ausgegraut".

Ursache: ``assets/themes/dark.qss`` hatte fuer ``QLineEdit`` eine
``:disabled``-Regel, fuer ``QSpinBox``/``QDoubleSpinBox`` aber keine. Die
Grundregel (Hintergrund, Schrift, Rahmen) galt damit auch im gesperrten
Zustand unveraendert.

Geprueft wird gerendert (``grab()`` offscreen) mit dem echten Theme: Grund,
Rahmen und hellste Schriftfarbe eines gesperrten Felds gegen ein freies.
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
from PySide6.QtWidgets import (QApplication, QDoubleSpinBox, QLineEdit,
                               QSpinBox, QVBoxLayout, QWidget)

QSS = ROOT / "assets" / "themes" / "dark.qss"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _fenster():
    fenster = QWidget()
    fenster.setStyleSheet(QSS.read_text(encoding="utf-8"))
    QVBoxLayout(fenster)
    fenster.resize(300, 200)
    return fenster


def _merkmale(app, w):
    """(Grund, Rahmen, hellste Schrift) eines gerenderten Felds."""
    app.processEvents()
    img = w.grab().toImage()
    h = img.height()
    # Grund = haeufigste Farbe im Innern, nicht ein fester Pixel: je nach
    # Schrift des Rechners (CI) traf (2, h/2) sonst einen Buchstaben.
    from collections import Counter
    grund = Counter(img.pixelColor(x, y).getRgb()[:3]
                    for x in range(3, img.width() - 3)
                    for y in range(3, h - 3)).most_common(1)[0][0]
    rahmen = img.pixelColor(0, h // 2).getRgb()[:3]
    hellste = max(img.pixelColor(x, y).lightness()
                  for x in range(3, img.width() // 2)
                  for y in range(2, h - 2))
    return grund, rahmen, hellste


def _paar(app, cls, wert):
    fenster = _fenster()
    frei, gesperrt = cls(), cls()
    for w in (frei, gesperrt):
        if isinstance(w, QLineEdit):
            w.setText(str(wert))
        else:
            w.setRange(0, 999)
            w.setValue(wert)
        w.setFixedSize(120, 28)
        fenster.layout().addWidget(w)
    gesperrt.setEnabled(False)
    fenster.show()
    return fenster, frei, gesperrt


def _pruefe_ausgegraut(m_frei, m_gesperrt):
    g_frei, r_frei, s_frei = m_frei
    g_ges, r_ges, s_ges = m_gesperrt
    assert g_ges != g_frei, ("Grund gleich", g_frei)
    assert sum(g_ges) < sum(g_frei), ("gesperrt nicht dunkler", g_frei, g_ges)
    assert r_ges != r_frei, ("Rahmen gleich", r_frei)
    # Schrift deutlich gedimmt (frei: weiss)
    assert s_frei > 200, s_frei
    assert s_ges < s_frei - 80, ("Schrift nicht gedimmt", s_frei, s_ges)


@pytest.mark.parametrize("cls,wert", [(QSpinBox, 888), (QDoubleSpinBox, 88.8),
                                      (QLineEdit, "888")])
def test_gesperrtes_feld_sieht_gesperrt_aus(app, cls, wert):
    fenster, frei, gesperrt = _paar(app, cls, wert)
    try:
        _pruefe_ausgegraut(_merkmale(app, frei), _merkmale(app, gesperrt))
    finally:
        fenster.close()
        fenster.deleteLater()


def test_freies_feld_unveraendert(app):
    # Gegenprobe: das freie Feld behaelt Grund #555555 und weisse Schrift.
    fenster, frei, _ = _paar(app, QSpinBox, 888)
    try:
        grund, _, hellste = _merkmale(app, frei)
        assert grund == (0x55, 0x55, 0x55)
        assert hellste > 240
    finally:
        fenster.close()
        fenster.deleteLater()


def test_fernsteuerung_gesperrte_felder_ausgegraut(app, tmp_path):
    # Der Fundort: Ziel Grand Master sperrt Executor und Schwelle,
    # Ziel GO laesst beide frei.
    from src.core.dmx.fernsteuerung import ZIEL_GM, ZIEL_GO, Zuordnung
    from src.ui.widgets.dmx_fernsteuerung_box import (SP_EXEC, SP_SCHWELLE,
                                                      FernsteuerungBox)
    fenster = _fenster()
    box = FernsteuerungBox(fenster, pfad=str(tmp_path / "fs.json"))
    fenster.layout().addWidget(box)
    fenster.resize(900, 420)
    fenster.show()
    try:
        box.zeile_hinzu(Zuordnung(ziel=ZIEL_GO))
        box.zeile_hinzu(Zuordnung(ziel=ZIEL_GM))
        app.processEvents()
        for sp in (SP_EXEC, SP_SCHWELLE):
            frei = box.tabelle.cellWidget(0, sp)
            gesperrt = box.tabelle.cellWidget(1, sp)
            assert frei.isEnabled() and not gesperrt.isEnabled()
            _pruefe_ausgegraut(_merkmale(app, frei), _merkmale(app, gesperrt))
    finally:
        fenster.close()
        fenster.deleteLater()


def test_fernsteuerung_umschalten_zur_laufzeit(app, tmp_path):
    # Ziel im laufenden Dialog umstellen: GO -> Grand Master graut aus,
    # zurueck auf GO zeigt das Feld wieder wie ein freies.
    from src.core.dmx.fernsteuerung import ZIEL_GM, ZIEL_GO, Zuordnung
    from src.ui.widgets.dmx_fernsteuerung_box import (SP_EXEC, SP_ZIEL,
                                                      FernsteuerungBox)
    fenster = _fenster()
    box = FernsteuerungBox(fenster, pfad=str(tmp_path / "fs.json"))
    fenster.layout().addWidget(box)
    fenster.resize(900, 420)
    fenster.show()
    try:
        box.zeile_hinzu(Zuordnung(ziel=ZIEL_GO))
        box.zeile_hinzu(Zuordnung(ziel=ZIEL_GO))
        app.processEvents()
        referenz = box.tabelle.cellWidget(0, SP_EXEC)
        feld = box.tabelle.cellWidget(1, SP_EXEC)
        combo = box.tabelle.cellWidget(1, SP_ZIEL)
        m_frei = _merkmale(app, referenz)
        assert _merkmale(app, feld) == m_frei
        combo.setCurrentIndex(combo.findData(ZIEL_GM))
        assert not feld.isEnabled()
        _pruefe_ausgegraut(m_frei, _merkmale(app, feld))
        combo.setCurrentIndex(combo.findData(ZIEL_GO))
        assert feld.isEnabled()
        assert _merkmale(app, feld) == m_frei
    finally:
        fenster.close()
        fenster.deleteLater()

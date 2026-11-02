"""QA-109: zwei Rote des Windows-Gates vom 01.11.2026 — der Mechanismus,
plattformunabhaengig geprueft.

**Executor-Leiste (test_ui98_kleines_fenster).** ``ExecutorWidget`` setzte
seine Mindestbreite einmal im Konstruktor. Da hat die Taste aber noch die
Schrift OHNE Stylesheet; die aus ``dark.qss`` bekommt sie erst beim Polieren.
Unter Windows sind die beiden verschieden breit (ohne Stil „Sans Serif“, mit
Stil „Roboto Condensed“, das fehlt -> Arial): „— Leer —“ 43 -> 48 px,
Mindestbreite 89 statt 92 — die Leiste war 3 px zu schmal. Unter Linux fallen
beide auf dieselbe Ersatzschrift, dort war nichts zu sehen. Hier wird deshalb
nicht eine Schrift gemessen, sondern geprueft, dass die Mindestbreite dem
Messwert NACH dem Polieren folgt.

**Schmale Kiosk-Zeile (test_vcb47_banner_einklappen_haerte).** Die Zeile
„Probenmodus“ im Kiosk hatte kein Polster oben/unten und war damit genau eine
Schriftzeile hoch: unter Windows (Arial, 9 px) 10 px, der Waechter verlangt
12. Jetzt wird das Polster aus der WIRKLICHEN Schrift so bemessen, dass
``KLEIN_MIN_HOEHE`` erreicht wird — wo die Schrift reicht, bleibt es 0.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _lauf(n=3):
    for _ in range(n):
        _app().processEvents()


# ── Executor-Leiste ─────────────────────────────────────────────────────────

@pytest.fixture
def executor():
    _app()
    from src.core.app_state import get_state
    from src.ui.views.playback_view import ExecutorWidget
    w = ExecutorWidget(1, get_state())
    yield w
    w.close()
    w.deleteLater()
    _lauf(1)


def test_mindestbreite_wird_beim_ersten_anzeigen_neu_gemessen(executor, monkeypatch):
    gebaut = executor.minimumWidth()
    assert gebaut == executor.mindestbreite()
    # beim Polieren aendert sich die Schrift -> der Messwert ist ein anderer
    monkeypatch.setattr(executor, "mindestbreite", lambda: gebaut + 7)
    executor.show()
    _lauf()
    assert executor.minimumWidth() == gebaut + 7


def test_mindestbreite_folgt_einem_neuen_stylesheet(executor, monkeypatch):
    executor.show()
    _lauf()
    jetzt = executor.minimumWidth()
    monkeypatch.setattr(executor, "mindestbreite", lambda: jetzt + 25)
    executor.setStyleSheet("QPushButton { font-weight: bold; }")
    _lauf()
    assert executor.minimumWidth() == jetzt + 25
    assert executor.maximumWidth() == max(110, jetzt + 25)


# ── schmale Kiosk-Zeile ─────────────────────────────────────────────────────

@pytest.fixture
def banner():
    app = _app()
    from src.ui.ausgabe_banner import AusgabeBanner
    eltern = QWidget()
    # wie dark.qss unter Windows: „Roboto Condensed“ fehlt dort -> Arial
    eltern.setStyleSheet('QWidget { font-family: "Roboto Condensed", Arial; }')
    eltern.resize(900, 400)
    stapel = QStackedWidget(eltern)
    stapel.setGeometry(0, 40, 900, 360)
    stapel.addWidget(QWidget())
    b = AusgabeBanner(eltern)
    b.ueberlagere(stapel)
    eltern.show()
    app.processEvents()
    yield b
    eltern.hide()
    eltern.deleteLater()
    _lauf(1)


def _probe_klein(b):
    from src.ui.ausgabe_banner import ART_PROBE, BannerZustand
    b.zeige(BannerZustand(ART_PROBE, "Probenmodus — es wird kein DMX gesendet",
                          "", klein=True))
    _lauf(2)


def test_schmale_kiosk_zeile_ist_mindestens_12_px_hoch(banner):
    _probe_klein(banner)
    assert banner.isVisible()
    assert banner.height() >= 12, banner.height()


@pytest.mark.parametrize("min_h", [24, 40])
def test_die_mindesthoehe_wird_mit_der_echten_schrift_erreicht(banner, monkeypatch, min_h):
    import src.ui.ausgabe_banner as ab
    monkeypatch.setattr(ab, "KLEIN_MIN_HOEHE", min_h)
    _probe_klein(banner)
    # so viel Polster wie noetig, nicht mehr (ungerader Rest: +1 px)
    assert min_h <= banner.height() <= min_h + 1, banner.height()


def test_reicht_die_schrift_bleibt_das_polster(banner, monkeypatch):
    import src.ui.ausgabe_banner as ab
    monkeypatch.setattr(ab, "KLEIN_MIN_HOEHE", 0)
    assert banner._mit_mindesthoehe(ab._STIL_KLEIN) is ab._STIL_KLEIN


def test_volle_banner_bleiben_unveraendert(banner):
    """Nur die schmale Zeile bekommt die Mindesthoehe; Stoerung/Probe im
    Hauptfenster behalten ihr Polster aus ``_STIL``."""
    import src.ui.ausgabe_banner as ab
    banner.zeige(ab.BannerZustand(ab.ART_PROBE, "Probenmodus", ""))
    _lauf(2)
    assert banner._polster[0] is ab._STIL[ab.ART_PROBE]

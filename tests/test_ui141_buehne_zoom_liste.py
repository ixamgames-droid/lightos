"""UI-141 Fund 18 (Klick-Test 16.11.2026): Buehne — Geraeteliste, Zoom-Leiste,
Uebersichtskarte und das Einpassen.

1. Geraeteliste: CDX-74 haelt das ``[NNN]``-Praefix schon ganz und kuerzt nur
   den Namen. Im Touch-Modus blieben fuer den Text aber nur ~98 px — typische
   Namen wie „LED-Bar 1" passten nur ohne jede Reserve fuer breitere
   Ersatzschriften. Die Spalte ist am Finger jetzt breiter.
2. Einpassen (QOL-05): der Zoom wurde nur aus den Geraete-MITTELPUNKTEN und der
   vollen Sichtflaeche berechnet. Bei einem kompakten Rig (Mega Arena: 17 m
   breit = 340 Welt-px) ergab das 333 % (Touch) bzw. 344 % (Maus) — die
   aeusseren Geraete ragten ueber den Rand, und Zoom-Leiste und Karte lagen
   ueber Laser 4 / MH 6. Jetzt zaehlen Geraetegroesse und die von Leiste und
   Karte belegte Flaeche unten mit.
3. Die Zoom-Leiste laesst sich einklappen (Ziel am Finger 44 px), der Zustand
   bleibt gemerkt.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                          # noqa: E402
from PySide6.QtCore import QPoint, QRectF                              # noqa: E402
from PySide6.QtTest import QTest                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget      # noqa: E402

from src.ui import touch_keyboard as tk                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets               # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

#: Reserve fuer breitere Ersatzschriften (wie test_cdx74_buehne_liste).
RESERVE = 24


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    import src.ui.views.live_view as LV
    monkeypatch.setattr(LV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(LV, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    pfad = tmp_path / "ui_prefs.json"
    return lambda: json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


def _ruhe(n=6):
    for _ in range(n):
        QApplication.processEvents()


def _tipp(widget, p: QPoint | None = None):
    p = p if p is not None else widget.rect().center()
    QTest.touchEvent(widget, _DEV).press(0, p, widget).commit()
    QTest.touchEvent(widget, _DEV).release(0, p, widget).commit()
    QApplication.processEvents()


def _hauptfenster_qss(touch: bool) -> str:
    from src.ui.main_window import MainWindow
    fang: dict = {}
    fake = SimpleNamespace(_touch_mode=touch, setStyleSheet=lambda q: fang.setdefault("q", q))
    MainWindow._apply_theme(fake)
    return fang["q"]


def _live(touch: bool, breite=1920, hoehe=900, labels=None):
    tk.setze_touch_modus(touch)
    from src.ui.views.live_view import LiveView
    host = QWidget()
    host.setStyleSheet(_hauptfenster_qss(touch))
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lv = LiveView()
    lay.addWidget(lv)
    if labels is not None:
        fx = [SimpleNamespace(fid=i + 1, universe=1, address=i + 1, label=lab,
                              fixture_type="PAR") for i, lab in enumerate(labels)]
        lv._state.get_patched_fixtures = lambda: list(fx)
    host.setFixedSize(breite, hoehe)
    host.show()
    _ruhe(8)
    if labels is not None:
        lv._refresh_fixture_list()
        _ruhe()
    return host, lv


# ── 1. Geraeteliste ─────────────────────────────────────────────────────────

def test_touch_liste_zeigt_typische_namen_mit_reserve():
    from test_cdx74_buehne_liste import _textflaeche
    namen = ["LED-Bar 1", "MH-ZQ 1", "Spider 4"] + [f"PAR {i}" for i in range(30)]
    host, lv = _live(True, labels=namen)
    try:
        t = lv._fixture_list
        assert t.verticalScrollBar().isVisible()
        for i in range(3):
            it = t.topLevelItem(0).child(i)
            opt, flaeche = _textflaeche(t, it)
            breite = opt.fontMetrics.horizontalAdvance(it.text(0))
            assert flaeche.width() >= breite + RESERVE, (it.text(0), flaeche.width(), breite)
            assert t.itemDelegate().angezeigter_text(opt, flaeche.width()) == it.text(0)
    finally:
        lv._state.__dict__.pop("get_patched_fixtures", None)


def test_maus_liste_bleibt_schmal():
    """Die Maus-Bedienung behaelt ihre Zeichenflaeche."""
    host, lv = _live(False)
    assert lv._left_panel.width() == 190


# ── 2. Einpassen ────────────────────────────────────────────────────────────

def _mega_arena_rig():
    """Grundriss wie tools/build_mega_arena_2026.py (Meter, x/z)."""
    from src.core.stage.coords import world3d_to_live
    punkte = []
    for x in (-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0):
        punkte += [(x, 2.6), (x, 3.4), (x, -2.6)]
    for z in (-1.0, 2.0, 5.5):
        punkte += [(-8.5, z), (8.5, z)]
    return {i: world3d_to_live(x, z) for i, (x, z) in enumerate(punkte)}


def _bildschirm_rechteck(lv, pos):
    c = lv._canvas
    r = c._fixture_size * 0.6 * c.zoom          # Glyph-Radius (wie der Treffertest)
    p = c.mapTo(lv._scroll.viewport(), QPoint(int(pos[0] * c.zoom), int(pos[1] * c.zoom)))
    return QRectF(p.x() - r, p.y() - r, 2 * r, 2 * r)


@pytest.mark.parametrize("touch", [True, False])
@pytest.mark.parametrize("minimap", [True, False])
def test_einpassen_kein_geraet_am_rand_oder_unter_zoom_leiste(prefs, touch, minimap):
    host, lv = _live(touch)
    lv._btn_minimap.setChecked(minimap)
    _ruhe()
    lv._canvas._positions = _mega_arena_rig()
    lv._fit_2d_to_fixtures(force=True)
    _ruhe()
    vp = lv._scroll.viewport()
    sicht = QRectF(0, 0, vp.width(), vp.height())
    belegt = [QRectF(lv._zoom_overlay.geometry())]
    if minimap:
        belegt.append(QRectF(lv._minimap.geometry()))
    assert lv._canvas.zoom > 1.0               # ein kompaktes Rig wird weiterhin gross
    for fid, pos in lv._canvas._positions.items():
        r = _bildschirm_rechteck(lv, pos)
        assert sicht.contains(r), (fid, r, sicht, lv._canvas.zoom)
        for b in belegt:
            assert not b.intersects(r), (fid, r, b, lv._canvas.zoom)


# ── 3. Zoom-Leiste einklappen ───────────────────────────────────────────────

def test_zoom_leiste_einklappen_am_finger_und_gemerkt(prefs):
    # Offscreen-Bildschirm ist 800x600: der Finger trifft nur innerhalb davon.
    host, lv = _live(True, 790, 560)
    zo = lv._zoom_overlay
    knopf = lv._btn_zoom_klapp
    assert knopf.isVisible()
    assert min(knopf.width(), knopf.height()) >= 44
    breit = zo.width()
    _tipp(knopf)
    _ruhe()
    assert not lv._zoom_slider.isVisible()
    for b in (lv._btn_zoom_out, lv._btn_zoom_in, lv._btn_fit):
        assert not b.isVisible()
    assert zo.width() < breit, (zo.width(), breit)
    assert zo.width() <= knopf.width() + 30, (zo.width(), knopf.width())
    assert min(knopf.width(), knopf.height()) >= 44
    vp = lv._scroll.viewport()
    assert zo.geometry().right() < vp.width() and zo.geometry().bottom() < vp.height()
    assert prefs()["live_view_zoom_leiste"] == {"eingeklappt": True}

    # Neustart: bleibt eingeklappt; Aufklappen bringt alles zurueck.
    host2, lv2 = _live(True, 790, 560)
    assert not lv2._zoom_slider.isVisible()
    _tipp(lv2._btn_zoom_klapp)
    _ruhe()
    for b in (lv2._btn_zoom_out, lv2._btn_zoom_in, lv2._btn_fit):
        assert b.isVisible()
    assert prefs()["live_view_zoom_leiste"] == {"eingeklappt": False}


def test_zoom_leiste_maus_knopf_klein_und_klickbar(prefs):
    host, lv = _live(False)
    knopf = lv._btn_zoom_klapp
    assert knopf.isVisible() and knopf.height() <= 34
    knopf.click()
    _ruhe()
    assert not lv._zoom_slider.isVisible()
    knopf.click()
    _ruhe()
    assert lv._zoom_slider.isVisible() and lv._zoom_slider.width() == 200

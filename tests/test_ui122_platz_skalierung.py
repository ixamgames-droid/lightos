"""UI-122: Platz bei hoher Skalierung (Touch-Audit 11.11.2026, D-04/D-08/C-07)
und Nachtrag aus der Pruefung von UI-120 (Kopfleiste mit ``--touch``).

* **D-04** 3D-Werkzeugleiste: brauchte ~1990 px, der Rest lag hinter dem 12 px
  schmalen Erweiterungsknopf. Jetzt bricht sie um — kein Erweiterungsknopf,
  jeder Knopf liegt ganz in der Leiste und ist am Finger zu treffen.
* **D-08** Live-Ansicht bei 250 %: Seitenspalten und Minimap lassen sich
  ausblenden (gemerkt in ``ui_prefs.json``), das Zoom-Overlay wird kompakt
  und ragt nicht mehr aus der Flaeche; −, + und ⤢ bleiben.
* **C-07** Ausgabe-Dialog: alle sechs Reiter nebeneinander, keine Pfeile —
  breiter geoeffnet, bei schmalem Bildschirm Kurznamen.
* **Nachtrag**: Sektionsknoepfe bei Platzmangel mit Kurznamen statt drei „P…“.

Hohe Skalierung wird echt simuliert: ein Unterprozess mit ``QT_SCALE_FACTOR=2.5``
und einem 1600×900-Offscreen-Bildschirm (logisch 640×360) fuehrt die
``Skaliert``-Tests dieser Datei aus. Im Hauptprozess laufen dieselben Messungen
bei kleiner Fensterbreite. Finger ueber ``QTest.touchEvent``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QToolButton, QWidget,
)

from src.ui import touch_keyboard as tk                              # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()
_WURZEL = Path(__file__).resolve().parent.parent
_SKALIERT = os.environ.get("UI122_SKALIERT") == "1"

# Touch-Regel des Hauptfensters fuer Reiter (main_window.py, --touch).
_HAUPTFENSTER_REITER_TOUCH = (
    "QTabBar::tab { min-height: 40px; padding: 8px 16px; font-size: 13px; }\n")


def _warte(bedingung, sekunden=5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return bool(bedingung())


def _ruhe(n=6):
    for _ in range(n):
        QApplication.processEvents()


def _tipp(widget, p: QPoint | None = None):
    p = p if p is not None else widget.rect().center()
    QTest.touchEvent(widget, _DEV).press(0, p, widget).commit()
    QTest.touchEvent(widget, _DEV).release(0, p, widget).commit()
    QApplication.processEvents()


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as PV
    import src.ui.views.live_view as LV
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    monkeypatch.setattr(LV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(LV, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    pfad = tmp_path / "ui_prefs.json"
    return lambda: json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


# ── D-04: 3D-Werkzeugleiste ─────────────────────────────────────────────────

class _AnsichtOhneWebEngine(QWidget):
    def page(self):
        return MagicMock()

    def settings(self):
        return MagicMock()


def _viz_fenster(monkeypatch, breite: int):
    import src.ui.visualizer.visualizer_window as VW
    monkeypatch.setattr(VW, "QWebEngineView", _AnsichtOhneWebEngine)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_channel", lambda self: None)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_service_target",
                        lambda self: None)
    w = VW.VisualizerWindow()
    w._bridge = MagicMock()
    w.resize(breite, 700)
    w.show()
    _ruhe(8)
    return w


def _leiste_pruefen(w):
    tb, leiste = w._toolbar, w._toolbar_leiste
    ext = [b for b in tb.findChildren(QToolButton)
           if b.objectName() == "qt_toolbar_ext_button" and b.isVisible()]
    assert not ext, "kein Erweiterungsknopf der Werkzeugleiste"
    assert leiste.geometry().right() < tb.width()
    assert leiste.geometry().bottom() < tb.height()
    teile = [c for c in leiste.children() if isinstance(c, QWidget) and c.isVisible()]
    assert len(teile) >= 15
    for c in teile:
        g = c.geometry()
        assert g.left() >= 0 and g.top() >= 0, c
        assert g.right() < leiste.width() and g.bottom() < leiste.height(), \
            f"{c} {g} ausserhalb {leiste.size()}"
    knoepfe = [b for b in leiste.findChildren(QToolButton) if b.isVisible()]
    # Speichern, Neu, Löschen, Kamera, Neu laden, Alle entfernen,
    # Sperrzonen, Ausrichten, Andocken
    assert len(knoepfe) == 9, [b.text() for b in knoepfe]
    for b in knoepfe:
        assert b.width() >= b.sizeHint().width(), b.text()    # Text nie gekuerzt
    return knoepfe


@pytest.mark.parametrize("breite", [1600, 640])
def test_d04_werkzeugleiste_bricht_um_ohne_erweiterungsknopf(prefs, monkeypatch, breite):
    w = _viz_fenster(monkeypatch, breite)
    _leiste_pruefen(w)
    # Die 3D-Ansicht bleibt darunter, nicht von der Leiste verdeckt.
    assert w.centralWidget().geometry().top() >= w._toolbar.geometry().bottom()


def test_d04_maus_breites_fenster_eine_zeile(prefs, monkeypatch):
    w = _viz_fenster(monkeypatch, 2300)
    knoepfe = _leiste_pruefen(w)
    zeilen = {b.mapTo(w._toolbar_leiste, QPoint(0, 0)).y() for b in knoepfe}
    assert len(zeilen) == 1, "bei genug Platz bleibt die Leiste einzeilig"
    assert w._toolbar.height() < 80


def test_d04_touch_ziele_und_finger_tipp_in_der_letzten_zeile(prefs, monkeypatch):
    tk.setze_touch_modus(True)
    w = _viz_fenster(monkeypatch, 640)
    knoepfe = _leiste_pruefen(w)
    for b in knoepfe:
        assert b.height() >= 44 and b.width() >= 44, (b.text(), b.size())
    for feld in (w._combo_view, w._combo_edit, w._combo_stage):
        assert feld.height() >= 42
    andocken = next(b for b in knoepfe if b.defaultAction() is w._act_dock)
    # Am schmalen Fenster liegt der Knopf in einer unteren Zeile — frueher
    # hinter dem Erweiterungsknopf.
    assert andocken.mapTo(w._toolbar_leiste, QPoint(0, 0)).y() > 0
    vorher = w._act_dock.isChecked()
    _tipp(andocken)
    assert _warte(lambda: w._act_dock.isChecked() != vorher)
    _tipp(andocken)
    assert _warte(lambda: w._act_dock.isChecked() == vorher)


# ── D-08: Live-Ansicht ──────────────────────────────────────────────────────

def _live(breite: int, hoehe: int = 432):
    from src.ui.views.live_view import LiveView
    lv = LiveView()
    lv.resize(breite, hoehe)
    lv.show()
    _ruhe(8)
    return lv


def _overlay_pruefen(lv, touch: bool):
    vp = lv._scroll.viewport()
    zo = lv._zoom_overlay
    assert _warte(lambda: zo.geometry().right() < vp.width()
                  and zo.geometry().left() >= 0), (zo.geometry(), vp.size())
    assert zo.geometry().bottom() < vp.height()
    for b in (lv._btn_zoom_out, lv._btn_zoom_in, lv._btn_fit):
        assert b.isVisible(), b.text()
        g = b.geometry()
        assert g.right() < zo.width() and g.bottom() < zo.height(), b.text()
        if touch:
            assert min(b.width(), b.height()) >= 44, b.text()


@pytest.mark.parametrize("touch", [False, True])
def test_d08_zoom_overlay_passt_bei_250_prozent(prefs, touch):
    tk.setze_touch_modus(touch)
    lv = _live(640)      # 1600 px bei 250 % = 640 px logisch
    assert lv.width() == 640, "Ansicht darf nicht breiter als das Fenster werden"
    _overlay_pruefen(lv, touch)


def test_d08_maus_breit_unveraendert(prefs):
    tk.setze_touch_modus(False)
    lv = _live(1600, 800)
    assert lv._zoom_titel.isVisible() and lv._zoom_slider.isVisible()
    assert lv._zoom_slider.width() == 200
    assert lv._lbl_zoom.isVisible()
    assert lv._left_panel.isVisible() and lv._right_panel.isVisible()
    assert lv._minimap.isVisible()
    # Aktionsleiste einzeilig
    leiste = lv._aktionsleiste
    ys = {b.geometry().top() for b in (lv._btn_multi, lv._btn_view3d, lv._btn_minimap)}
    assert len(ys) == 1, ys
    assert leiste.height() < 60


def test_d08_spalten_und_minimap_am_finger_aus_und_gemerkt(prefs):
    tk.setze_touch_modus(True)
    lv = _live(768)
    vp_vorher = lv._scroll.viewport().width()
    for b in (lv._btn_spalte_links, lv._btn_spalte_rechts, lv._btn_minimap):
        assert min(b.width(), b.height()) >= 44 or b.height() >= 34, b.text()
        assert b.geometry().bottom() < lv._aktionsleiste.height()
    _tipp(lv._btn_spalte_links)
    assert _warte(lambda: not lv._left_panel.isVisible())
    _tipp(lv._btn_spalte_rechts)
    assert _warte(lambda: not lv._right_panel.isVisible())
    _tipp(lv._btn_minimap)
    assert _warte(lambda: not lv._minimap.isVisible())
    assert _warte(lambda: lv._scroll.viewport().width() >= vp_vorher + 400), \
        (vp_vorher, lv._scroll.viewport().width())
    # Ohne Minimap sitzt das Overlay unten, und jetzt passt auch der Regler.
    vp = lv._scroll.viewport()
    assert _warte(lambda: lv._zoom_overlay.geometry().bottom() >= vp.height() - 20)
    assert lv._zoom_slider.isVisible()
    _overlay_pruefen(lv, True)
    assert prefs()["live_view_spalten"] == {"links": False, "rechts": False,
                                            "minimap": False}

    # Neue Ansicht (Neustart): Zustand kommt wieder.
    lv2 = _live(768)
    assert not lv2._left_panel.isVisible()
    assert not lv2._right_panel.isVisible()
    assert not lv2._minimap.isVisible()
    assert not lv2._btn_spalte_links.isChecked()

    _tipp(lv2._btn_spalte_links)
    assert _warte(lambda: lv2._left_panel.isVisible())
    assert prefs()["live_view_spalten"]["links"] is True


def test_d08_zurueck_aus_3d_respektiert_minimap_schalter(prefs):
    lv = _live(1200, 700)
    lv._btn_minimap.setChecked(False)
    _ruhe()
    lv._viz3d = MagicMock()          # keine echte WebEngine
    lv._set_view_3d(False)
    _ruhe()
    assert not lv._minimap.isVisible()
    lv._btn_minimap.setChecked(True)
    _ruhe()
    assert lv._minimap.isVisible()


# ── C-07: Ausgabe-Dialog ────────────────────────────────────────────────────

@pytest.fixture
def ausgabe(tmp_path, monkeypatch):
    import serial.tools.list_ports
    import src.ui.widgets.output_config as oc
    monkeypatch.setattr(serial.tools.list_ports, "comports", lambda *a, **k: [])
    monkeypatch.setattr(oc, "_UNIV_CONFIG_PATH", str(tmp_path / "universes.json"))
    oc._save_universe_config([{"num": 1, "name": "Main", "output": "Disabled",
                               "patch": ""}])
    from src.core.app_state import get_state
    state = get_state()
    om = state.output_manager
    for name in ("add_enttec", "add_sacn", "add_artnet", "remove_output"):
        monkeypatch.setattr(om, name, lambda *a, **k: None)
    monkeypatch.setattr(state, "apply_output_config", lambda *a, **k: None)
    monkeypatch.setattr(oc, "QMessageBox", mock.MagicMock())
    return oc


def _dialog(oc, touch: bool, platz: int | None = None, monkeypatch=None):
    eltern = QWidget()
    if touch:
        tk.setze_touch_modus(True)
        eltern.setStyleSheet(_HAUPTFENSTER_REITER_TOUCH + tk.touch_qss())
    if platz is not None:
        monkeypatch.setattr(oc.OutputConfigDialog, "_verfuegbare_breite",
                            lambda self: platz)
    d = oc.OutputConfigDialog(eltern)
    d.eltern_halten = eltern          # sonst raeumt der GC Eltern + Dialog ab
    d.show()
    _ruhe(6)
    return d


def _reiter_pruefen(d):
    tabs = d._tabs
    bar = tabs.tabBar()
    assert bar.count() == 6
    for i in range(6):
        r = bar.tabRect(i)
        assert r.left() >= 0 and r.right() < bar.width(), (bar.tabText(i), r, bar.width())
        assert bar.tabRect(i).width() >= bar.tabSizeHint(i).width(), bar.tabText(i)
    pfeile = [b for b in bar.findChildren(QToolButton) if b.isVisible()]
    assert not pfeile, "keine Reiter-Bildlaufpfeile"
    assert not tabs.usesScrollButtons()
    return [bar.tabText(i) for i in range(6)]


@pytest.mark.parametrize("touch", [False, True])
def test_c07_alle_reiter_sichtbar_volle_namen(ausgabe, monkeypatch, touch):
    d = _dialog(ausgabe, touch, platz=1600, monkeypatch=monkeypatch)
    texte = _reiter_pruefen(d)
    assert texte == ["Enttec Pro USB", "uDMX (USB)", "Art-Net", "sACN (E1.31)",
                     "DMX-Eingang", "Universen"]


def test_c07_schmaler_bildschirm_kurznamen_und_finger(ausgabe, monkeypatch):
    d = _dialog(ausgabe, True, platz=640, monkeypatch=monkeypatch)
    texte = _reiter_pruefen(d)
    assert texte == ["Enttec", "uDMX", "Art-Net", "sACN", "DMX-Eingang", "Universen"]
    bar = d._tabs.tabBar()
    assert bar.tabToolTip(0) == "Enttec Pro USB"
    assert d.width() <= 640
    for i in range(6):
        assert bar.tabRect(i).height() >= 44
    # Finger auf „Universen“ und „DMX-Eingang“ (frueher nur ueber die Pfeile).
    # Zwei Tipps kurz nacheinander waeren sonst ein Doppelklick.
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        for i in (5, 4):
            QTest.qWait(20)
            _tipp(bar, bar.tabRect(i).center())
            assert _warte(lambda: d._tabs.currentIndex() == i), (i, d._tabs.currentIndex())
    finally:
        hints.setMouseDoubleClickInterval(alt)


# ── Nachtrag: Kopfleiste mit --touch bei 1280/1440 px ───────────────────────

@pytest.mark.parametrize("breite", [1280, 1440])
def test_nachtrag_sektionen_unterscheidbar_mit_touch(breite):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=True)
    w._hw_timer.stop()
    w.resize(breite, 900)
    w.show()
    _ruhe(8)
    texte = [b.text() for b in w._section_btns]
    # Kein Knopf ist nur „P…“; die Anfaenge sind eindeutig.
    anfaenge = [t.rstrip("…")[:2] for t in texte]
    assert len(set(anfaenge)) == len(anfaenge), texte
    assert not [t for t in texte if len(t.rstrip("…")) < 2], texte
    # Volle Namen bleiben im Tooltip.
    assert w._section_btns[2].toolTip() == "Programmer"
    for b in w._section_btns:
        assert b.width() >= 44 and b.height() >= 48, (b.text(), b.size())
    w.hide()
    w.deleteLater()


def test_nachtrag_kurzname_statt_p_punkte():
    from src.ui.main_window import SectionButton
    b = SectionButton("Programmer", "#FFD700", "Prog")
    b.show()
    voll = b.sizeHint().width()
    b.resize(voll, b.sizeHint().height())
    assert b.text() == "Programmer"
    b.resize(voll - 30, b.sizeHint().height())
    assert b.text() == "Prog"
    b.setFixedWidth(b.fontMetrics().horizontalAdvance("Prog") + 8)
    QApplication.processEvents()
    assert b.text().startswith("Pr"), b.text()
    assert b.icon().isNull(), "zu schmal fuer Symbol + Kurzname: Symbol faellt weg"
    assert b.sizeHint().width() == voll, "Wunschbreite bleibt stabil"
    b.setFixedWidth(voll)
    QApplication.processEvents()
    assert b.text() == "Programmer" and not b.icon().isNull()
    ohne = SectionButton("Programmer", "#FFD700")
    ohne.show()
    ohne.resize(voll - 30, ohne.sizeHint().height())
    assert ohne.text().endswith("…")     # ohne Kurzname wie bisher


# ── Echte 250 %: Unterprozess mit QT_SCALE_FACTOR ───────────────────────────

@pytest.mark.skipif(_SKALIERT, reason="laeuft schon im Unterprozess")
def test_bei_echter_skalierung_250_prozent(tmp_path):
    cfg = tmp_path / "bildschirm.json"
    cfg.write_text(json.dumps({"screens": [{
        "name": "S", "x": 0, "y": 0, "width": 1600, "height": 900,
        "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}), encoding="utf-8")
    env = dict(os.environ)
    env.update(QT_QPA_PLATFORM=f"offscreen:configfile={cfg}",
               QT_SCALE_FACTOR="2.5", UI122_SKALIERT="1")
    env.pop("PYTEST_ADDOPTS", None)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(Path(__file__)), "-k", "skaliert"],
        cwd=str(_WURZEL), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    assert " passed" in r.stdout and "skipped" not in r.stdout.split("\n")[-2], r.stdout[-800:]


_nur_skaliert = pytest.mark.skipif(not _SKALIERT, reason="nur im 250-%-Unterprozess")


@_nur_skaliert
def test_skaliert_bildschirm_ist_640_logisch():
    s = _app.primaryScreen()
    assert s.devicePixelRatio() == pytest.approx(2.5)
    assert s.availableGeometry().width() == 640


@_nur_skaliert
@pytest.mark.parametrize("touch", [False, True])
def test_skaliert_d04_werkzeugleiste(prefs, monkeypatch, touch):
    tk.setze_touch_modus(touch)
    w = _viz_fenster(monkeypatch, 640)
    _leiste_pruefen(w)


@_nur_skaliert
@pytest.mark.parametrize("touch", [False, True])
def test_skaliert_d08_live(prefs, touch):
    tk.setze_touch_modus(touch)
    lv = _live(640, 340)
    _overlay_pruefen(lv, touch)


@_nur_skaliert
def test_skaliert_c07_ausgabe(ausgabe):
    d = _dialog(ausgabe, True)
    texte = _reiter_pruefen(d)
    assert "Universen" in texte and "DMX-Eingang" in texte
    assert d.frameGeometry().right() < 640

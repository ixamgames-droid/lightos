"""UI-83: Multitouch-Gesten — Halten + Antippen, Zwei-Finger-Bankwechsel,
Drei-Finger-Tippen, Gesten-Uebersicht mit Schaltern.

Geprueft mit echtem Touch-Ablauf: ``QTest.touchEvent`` mit mehreren
Touchpunkten, Qt erzeugt aus dem ersten Finger die Maus, der Anwendungsfilter
aus UI-110 (``ziehen_scrollen``) haengt wie in der App dazwischen. Gewartet
wird nur auf Mindestzeiten (erster Finger liegt ``HALTEN_MIN_S``) bzw. auf
Bedingungen. Einstellungen nur in ``tmp_path``.
"""
from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget  # noqa: E402

from src.ui import gesten_prefs                                      # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    f.gesten = gesten_prefs.GestenSchalter()
    f.drei_finger_rueckruf = None
    yield
    f.gesten = gesten_prefs.GestenSchalter()
    f.drei_finger_rueckruf = None
    f._halten = None
    f._wisch = None
    f._geste = None
    destroy_all_top_level_widgets(_app)


def _filter():
    return zs.einrichten(_app)


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)


def _warte_bis(bedingung, s: float = 3.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


def _halten_antippen(w, halt: QPoint, tipps, warten: bool = True, los: bool = True):
    """Finger 0 auf ``halt``, (Mindestzeit), dann je Tipp einen weiteren
    Finger auf- und absetzen; zuletzt Finger 0 los. Der erste Druck beginnt
    ein neues Klick-Paar (kein Doppelklick mit dem Druck davor)."""
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        QTest.touchEvent(w, _DEV).press(0, halt, w).commit()
        QApplication.processEvents()
    finally:
        hints.setMouseDoubleClickInterval(alt)
    if warten:
        _warte(zs.HALTEN_MIN_S + 0.05)
    for i, p in enumerate(tipps, start=1):
        QTest.touchEvent(w, _DEV).move(0, halt, w).press(i, p, w).commit()
        QApplication.processEvents()
        QTest.touchEvent(w, _DEV).move(0, halt, w).release(i, p, w).commit()
        QApplication.processEvents()
    if los:
        QTest.touchEvent(w, _DEV).release(0, halt, w).commit()
        QApplication.processEvents()


# ── (d) Einstellungen ────────────────────────────────────────────────────────

def test_prefs_vorgabe_und_rundweg(tmp_path):
    pfad = str(tmp_path / "ui_prefs.json")
    s = gesten_prefs.laden(pfad)
    assert s == gesten_prefs.GestenSchalter()
    assert s.drei_finger == "aus", "Drei-Finger-Tippen ist ab Werk aus"
    assert all(getattr(s, k) for k, _t, _e in gesten_prefs.UEBERSICHT)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump({"viz_strobe_mode": "soft"}, f)
    s.halten_antippen = False
    s.drei_finger = "programmer_leeren"
    assert gesten_prefs.speichern(s, pfad)
    daten = json.load(open(pfad, encoding="utf-8"))
    assert daten["viz_strobe_mode"] == "soft", "fremde Abschnitte bleiben"
    neu = gesten_prefs.laden(pfad)
    assert neu.halten_antippen is False and neu.drei_finger == "programmer_leeren"


def test_prefs_unbekannte_werte_und_kaputte_datei(tmp_path):
    pfad = str(tmp_path / "ui_prefs.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump({"touch_gesten": {"drei_finger": "blackout", "lang_menue": "ja"}}, f)
    s = gesten_prefs.laden(pfad)
    assert s.drei_finger == "aus" and s.lang_menue is True
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("{kaputt")
    assert not gesten_prefs.speichern(gesten_prefs.GestenSchalter(), pfad)
    assert open(pfad, encoding="utf-8").read() == "{kaputt", "nicht ueberschrieben"


def test_drei_finger_nie_eine_sicherheitsaktion():
    verboten = ("black", "stop", "go", "not", "laser", "sperr", "lock", "estop")
    for wert, text in gesten_prefs.DREI_FINGER_AKTIONEN:
        for v in verboten:
            assert v not in wert.lower().replace("programmer", ""), wert
        assert "BLACKOUT" not in text.upper() and "STOP" not in text.upper()


def test_dialog_uebersicht_und_uebernehmen(tmp_path):
    from src.ui.widgets.gesten_dialog import GestenDialog
    pfad = str(tmp_path / "ui_prefs.json")
    d = GestenDialog(pfad=pfad)
    assert set(d.schalter) == {k for k, _t, _e in gesten_prefs.UEBERSICHT}
    werte = [d.drei.itemData(i) for i in range(d.drei.count())]
    assert werte == list(gesten_prefs.DREI_FINGER_WERTE)
    assert d.drei.currentData() == "aus"
    d.schalter["zwei_finger_bank"].setChecked(False)
    d.drei.setCurrentIndex(d.drei.findData("page_naechste"))
    d.uebernehmen()
    f = _filter()
    assert f.gesten.zwei_finger_bank is False and f.gesten.drei_finger == "page_naechste"
    gespeichert = gesten_prefs.laden(pfad)
    assert gespeichert.zwei_finger_bank is False
    assert gespeichert.drei_finger == "page_naechste"


def test_main_window_drei_finger_nur_harmlose_aktionen():
    from src.ui.main_window import MainWindow
    log = []
    fenster = SimpleNamespace(
        _kiosk_mode=False,
        _global_clear_programmer=lambda: log.append("leeren"),
        _page_next=lambda: log.append("weiter"),
        _page_prev=lambda: log.append("zurueck"),
        statusBar=lambda: SimpleNamespace(showMessage=lambda *a: None))
    for a in ("programmer_leeren", "page_naechste", "page_vorherige", "blackout",
              "stop_all", "aus"):
        MainWindow._drei_finger_aktion(fenster, a)
    assert log == ["leeren", "weiter", "zurueck"]
    fenster._kiosk_mode = True
    MainWindow._drei_finger_aktion(fenster, "programmer_leeren")
    assert log == ["leeren", "weiter", "zurueck"], "im Kiosk nie"
    # Pruefung: Touch-Lock (Display-only) sperrt auch das Drei-Finger-Tippen
    from src.ui.virtualconsole.vc_widget import VCWidget
    fenster._kiosk_mode = False
    VCWidget.input_locked = True
    try:
        MainWindow._drei_finger_aktion(fenster, "programmer_leeren")
    finally:
        VCWidget.input_locked = False
    assert log == ["leeren", "weiter", "zurueck"], "bei Touch-Lock nie"


# ── (a) Halten + Antippen: 2D-Buehne ─────────────────────────────────────────

@pytest.fixture
def buehne():
    from src.ui.views.live_view import StageCanvas
    c = StageCanvas()
    fx = [SimpleNamespace(fid=i, universe=1, address=i, label=f"PAR-{i}", fixture_type="PAR")
          for i in (1, 2, 3)]
    c._state.get_patched_fixtures = lambda: list(fx)
    c.world_w, c.world_h = 1200, 800
    c.set_zoom(1.0)
    c.snap_enabled = False
    area = QScrollArea()
    area.setWidgetResizable(False)
    area.setWidget(c)
    area.resize(520, 420)
    area.show()
    QTest.qWaitForWindowExposed(area)
    QApplication.processEvents()
    c._positions = {1: (100.0, 100.0), 2: (300.0, 100.0), 3: (300.0, 300.0)}
    c.uebernommen = []
    c._verschiebung_uebernehmen = lambda fids: c.uebernommen.append(list(fids))
    c._selected_fids = []
    menues = []
    c.context_menu_requested.connect(lambda fid, p: menues.append(fid))
    try:
        yield SimpleNamespace(c=c, area=area, vp=area.viewport(), menues=menues)
    finally:
        c._state.__dict__.pop("get_patched_fixtures", None)


def test_buehne_halten_antippen_waehlt_mehrere(buehne):
    b = buehne
    _halten_antippen(b.vp, QPoint(100, 100), [QPoint(300, 100), QPoint(300, 300)])
    assert sorted(b.c._selected_fids) == [1, 2, 3]
    assert b.c._positions == {1: (100.0, 100.0), 2: (300.0, 100.0), 3: (300.0, 300.0)}
    assert b.c.uebernommen == [] and b.menues == []
    assert b.c._pinch is None and abs(b.c.zoom - 1.0) < 1e-6, "kein Pinch"
    assert not _filter().halten_laeuft
    # nochmal: Antippen nimmt wieder heraus, gehaltenes bleibt
    _halten_antippen(b.vp, QPoint(100, 100), [QPoint(300, 100)])
    assert sorted(b.c._selected_fids) == [1, 3]


def test_buehne_halten_ersetzt_fremde_auswahl(buehne):
    b = buehne
    b.c._selected_fids = [3]
    _halten_antippen(b.vp, QPoint(100, 100), [QPoint(300, 100)])
    assert sorted(b.c._selected_fids) == [1, 2]


def test_buehne_zwei_finger_zugleich_bleibt_pinch(buehne):
    """Beide Finger sofort: Pinch wie bisher, keine Auswahl."""
    b = buehne
    _halten_antippen(b.vp, QPoint(100, 100), [QPoint(300, 100)], warten=False)
    assert b.c._selected_fids == []
    assert not _filter().halten_laeuft


def test_buehne_halten_abgeschaltet(buehne):
    b = buehne
    _filter().gesten.halten_antippen = False
    _halten_antippen(b.vp, QPoint(100, 100), [QPoint(300, 100)])
    assert 2 not in b.c._selected_fids


def test_buehne_gewischter_zweiter_finger_ist_kein_antippen(buehne):
    b = buehne
    vp = b.vp
    h = QPoint(100, 100)
    QTest.touchEvent(vp, _DEV).press(0, h, vp).commit()
    QApplication.processEvents()
    _warte(zs.HALTEN_MIN_S + 0.05)
    QTest.touchEvent(vp, _DEV).move(0, h, vp).press(1, QPoint(300, 100), vp).commit()
    for x in (330, 360, 400):
        QTest.touchEvent(vp, _DEV).move(0, h, vp).move(1, QPoint(x, 100), vp).commit()
    QTest.touchEvent(vp, _DEV).move(0, h, vp).release(1, QPoint(400, 100), vp).commit()
    QTest.touchEvent(vp, _DEV).release(0, h, vp).commit()
    QApplication.processEvents()
    assert b.c._selected_fids == [1]


# ── (a) Halten + Antippen: VC im Bearbeiten-Modus ───────────────────────────

@pytest.fixture
def vc():
    from src.ui.views.virtual_console_view import GrowingScrollArea
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_slider import SliderMode
    canvas = VCCanvas()
    knoepfe = []
    for x in (20, 160, 300):
        b = canvas._add_widget("VCButton", QPoint(x, 20))
        b.resize(100, 80)
        b.action = ButtonAction.FLASH
        b._trigger = lambda an: None
        knoepfe.append(b)
    s = canvas._add_widget("VCSlider", QPoint(440, 20))
    s.mode = SliderMode.SPEED
    s.resize(60, 260)
    area = GrowingScrollArea()
    area.setWidget(canvas)
    area.resize(1300, 900)          # VC passt ganz: kein waagerechter Bildlauf
    area.show()
    QTest.qWaitForWindowExposed(area)
    canvas.set_edit_mode(False)
    QApplication.processEvents()
    start_bank = canvas.active_bank
    try:
        yield SimpleNamespace(canvas=canvas, b=knoepfe, s=s, area=area, vp=area.viewport())
    finally:
        if canvas.active_bank != start_bank:
            canvas.zwei_finger_wischen(start_bank - canvas.active_bank)
            QApplication.processEvents()


def _mitte(v, w) -> QPoint:
    return w.mapTo(v.vp, w.rect().center())


def test_vc_bearbeiten_halten_antippen(vc):
    v = vc
    v.canvas.set_edit_mode(True)
    lagen = [QPoint(w.geometry().topLeft()) for w in v.b]
    _halten_antippen(v.vp, _mitte(v, v.b[0]), [_mitte(v, v.b[1]), _mitte(v, v.b[2])])
    assert v.canvas.ausgewaehlte() == v.b
    assert [QPoint(w.geometry().topLeft()) for w in v.b] == lagen, "nichts verschoben"
    # Antippen nimmt heraus
    _halten_antippen(v.vp, _mitte(v, v.b[0]), [_mitte(v, v.b[2])])
    assert v.canvas.ausgewaehlte() == v.b[:2]


def test_vc_spielbetrieb_kein_halten_antippen(vc):
    v = vc
    _halten_antippen(v.vp, _mitte(v, v.b[0]), [_mitte(v, v.b[1])])
    assert v.canvas.ausgewaehlte() == []
    assert not any(getattr(w, "_selected", False) for w in v.b)


# ── (b) Zwei Finger waagerecht = Bank blaettern ──────────────────────────────

def _zwei_wisch(v, a0: QPoint, b0: QPoint, d: QPoint, schritte: int = 6):
    vp = v.vp
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QApplication.processEvents()
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        QTest.touchEvent(vp, _DEV).move(0, a0 + d * (i / schritte), vp) \
            .move(1, b0 + d * (i / schritte), vp).commit()
        QApplication.processEvents()
    QTest.touchEvent(vp, _DEV).release(0, a0 + d, vp).move(1, b0 + d, vp).commit()
    QTest.touchEvent(vp, _DEV).release(1, b0 + d, vp).commit()
    QApplication.processEvents()


def test_vc_zwei_finger_waagerecht_blaettert_bank(vc):
    v = vc
    b0 = v.canvas.active_bank
    _zwei_wisch(v, QPoint(500, 500), QPoint(650, 500), QPoint(-200, 0))
    assert _warte_bis(lambda: v.canvas.active_bank == b0 + 1), v.canvas.active_bank
    _zwei_wisch(v, QPoint(300, 500), QPoint(450, 500), QPoint(200, 0))
    assert _warte_bis(lambda: v.canvas.active_bank == b0)


def test_vc_zwei_finger_senkrecht_oder_kurz_kein_bankwechsel(vc):
    v = vc
    b0 = v.canvas.active_bank
    _zwei_wisch(v, QPoint(500, 400), QPoint(650, 400), QPoint(0, 200))
    _zwei_wisch(v, QPoint(500, 500), QPoint(650, 500), QPoint(-40, 0))
    _warte(0.05)
    assert v.canvas.active_bank == b0


def test_vc_finger_auf_bedienelement_kein_bankwechsel(vc):
    v = vc
    b0 = v.canvas.active_bank
    _zwei_wisch(v, _mitte(v, v.s), QPoint(700, 500), QPoint(-200, 0))
    _zwei_wisch(v, QPoint(700, 500), _mitte(v, v.b[1]), QPoint(-200, 0))
    _warte(0.05)
    assert v.canvas.active_bank == b0


def test_vc_bankwechsel_abgeschaltet(vc):
    v = vc
    b0 = v.canvas.active_bank
    _filter().gesten.zwei_finger_bank = False
    _zwei_wisch(v, QPoint(500, 500), QPoint(650, 500), QPoint(-200, 0))
    _warte(0.05)
    assert v.canvas.active_bank == b0


def test_vc_touch_lock_kein_bankwechsel(vc):
    """Pruefung: Touch-Lock (Display-only) — der Finger blaettert auch die
    Bank (Executor-Page) nicht um."""
    from src.ui.virtualconsole.vc_widget import VCWidget
    v = vc
    b0 = v.canvas.active_bank
    VCWidget.input_locked = True
    try:
        _zwei_wisch(v, QPoint(500, 500), QPoint(650, 500), QPoint(-200, 0))
        _warte(0.05)
        assert v.canvas.active_bank == b0
    finally:
        VCWidget.input_locked = False


def test_vc_waagerechter_bildlauf_moeglich_bleibt_bildlauf(vc):
    """Kann die Flaeche noch nach rechts scrollen, schaltet der Wisch nach
    links die Bank nicht um."""
    v = vc
    v.area.resize(500, 400)
    QApplication.processEvents()
    assert v.area.horizontalScrollBar().maximum() > 0
    b0 = v.canvas.active_bank
    _zwei_wisch(v, QPoint(300, 300), QPoint(420, 300), QPoint(-200, 0))
    _warte(0.05)
    assert v.canvas.active_bank == b0


# ── (c) Drei-Finger-Tippen ───────────────────────────────────────────────────

@pytest.fixture
def flaeche():
    w = QWidget()
    w.resize(600, 400)
    knopf = QPushButton("Knopf", w)
    knopf.setGeometry(450, 300, 120, 60)
    w.show()
    QTest.qWaitForWindowExposed(w)
    log = []
    _filter().drei_finger_rueckruf = log.append
    return SimpleNamespace(w=w, knopf=knopf, log=log)


def _drei(w, punkte, d=QPoint(0, 0), spaet: float = 0.0):
    t = QTest.touchEvent(w, _DEV)
    for i, p in enumerate(punkte[:2]):
        t.press(i, p, w)
    t.commit()
    QApplication.processEvents()
    if spaet:
        _warte(spaet)
    t = QTest.touchEvent(w, _DEV)
    for i, p in enumerate(punkte[:2]):
        t.move(i, p, w)
    t.press(2, punkte[2], w).commit()
    QApplication.processEvents()
    if not d.isNull():
        t = QTest.touchEvent(w, _DEV)
        for i, p in enumerate(punkte):
            t.move(i, p + d, w)
        t.commit()
    t = QTest.touchEvent(w, _DEV)
    for i, p in enumerate(punkte):
        t.release(i, p + d, w)
    t.commit()
    QApplication.processEvents()


_DREI = [QPoint(100, 100), QPoint(160, 110), QPoint(220, 100)]


def test_drei_finger_vorgabe_aus(flaeche):
    _drei(flaeche.w, _DREI)
    _warte(0.05)
    assert flaeche.log == []


def test_drei_finger_loest_gewaehlte_aktion_aus(flaeche):
    _filter().gesten.drei_finger = "programmer_leeren"
    _drei(flaeche.w, _DREI)
    assert _warte_bis(lambda: flaeche.log == ["programmer_leeren"]), flaeche.log


def test_drei_finger_nicht_bei_bewegung_knopf_oder_spaet(flaeche):
    _filter().gesten.drei_finger = "programmer_leeren"
    _drei(flaeche.w, _DREI, d=QPoint(60, 0))
    _drei(flaeche.w, _DREI[:2] + [QPoint(500, 330)])            # dritter auf Knopf
    _drei(flaeche.w, _DREI, spaet=zs.DREI_FENSTER_S + 0.1)
    _warte(0.05)
    assert flaeche.log == []


def test_zwei_finger_sind_kein_drei_finger(flaeche):
    _filter().gesten.drei_finger = "programmer_leeren"
    w = flaeche.w
    QTest.touchEvent(w, _DEV).press(0, _DREI[0], w).press(1, _DREI[1], w).commit()
    QTest.touchEvent(w, _DEV).release(0, _DREI[0], w).release(1, _DREI[1], w).commit()
    _warte(0.05)
    assert flaeche.log == []

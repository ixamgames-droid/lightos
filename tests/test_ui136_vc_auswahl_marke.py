"""UI-136 (1): sichtbare Auswahl in der VC — fuer JEDEN Widget-Typ gleich.

Eine Ueberlagerung der Flaeche (``vc_auswahl_marke.AuswahlMarke``) malt fuer
jedes gewaehlte Widget einen kraeftigen Rahmen in der Akzentfarbe mit dunkler
Kontur, eine leichte Toenung und ein Haken-Abzeichen; bei mehreren einen
Zaehler. Geprueft an echten Pixeln (offscreen ``grab``) fuer Taste, Fader,
Label, Farbkachel, XY-Pad, Raum-Pad und ein Widget im Kasten; dazu: Maus und
Finger gehen durch die Ueberlagerung, im Spielbetrieb ist sie weg, ohne
Auswahl kostet sie nichts, sie folgt Verschieben/Groesse/Bank.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtGui import QColor                                     # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.ui.virtualconsole import vc_auswahl_marke as am             # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas                 # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

TYPEN = ["VCButton", "VCSlider", "VCLabel", "VCColor", "VCXYPad", "VCRaumPad"]


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _flaeche():
    c = VCCanvas()
    c.resize(1300, 800)
    ws = {}
    for i, t in enumerate(TYPEN):
        w = c._add_widget(t, QPoint(40 + i * 200, 80))
        w.resize(160, 180)
        ws[t] = w
    fr = c._add_widget("VCFrame", QPoint(40, 400))
    fr.resize(320, 240)
    kind = c._add_widget("VCButton", QPoint(0, 0))
    fr.add_child_to_page(kind, 0)
    kind.move(40, 60)
    kind.resize(120, 90)
    ws["Kasten-Kind"] = kind
    ws["VCFrame"] = fr
    c.set_edit_mode(True)
    c.show()
    QTest.qWaitForWindowExposed(c)
    QApplication.processEvents()
    return c, ws


def _warte_marke(c):
    for _ in range(20):
        QApplication.processEvents()
    m = c.auswahl_marke()
    m.auffrischen()
    QApplication.processEvents()
    return m


def _nah(farbe: QColor, ziel: QColor, tol: int = 40) -> bool:
    return (abs(farbe.red() - ziel.red()) <= tol and abs(farbe.green() - ziel.green()) <= tol
            and abs(farbe.blue() - ziel.blue()) <= tol)


def _pixel(c, p: QPoint) -> QColor:
    img = c.grab().toImage()
    dpr = img.devicePixelRatio() or 1.0
    return img.pixelColor(int(p.x() * dpr), int(p.y() * dpr))


@pytest.mark.parametrize("typ", TYPEN + ["Kasten-Kind"])
def test_jeder_typ_zeigt_kraeftige_markierung(typ):
    c, ws = _flaeche()
    w = ws[typ]
    r = c._lage(w)
    b = am.rahmen_dicke()
    links = QPoint(r.x() + 1 + b // 2, r.center().y())
    vorher = _pixel(c, links)
    w._selected = True
    m = _warte_marke(c)
    assert m.isVisible() and m.gewaehlt() == [w]
    nachher = _pixel(c, links)
    assert _nah(nachher, am.AKZENT), (typ, nachher.name(), vorher.name())
    # dunkle Kontur ganz aussen
    assert _pixel(c, QPoint(r.x(), r.center().y())).lightness() < 60
    # Haken-Abzeichen oben links: Akzent-Kreis
    d = 22 if am.touch_aktiv() else 16
    kreis = QPoint(r.x() + b + 2 + d // 2 + d // 4, r.y() + b + 2 + d // 5)
    assert _nah(_pixel(c, kreis), am.AKZENT, 60), typ
    # Toenung: Mitte veraendert sich gegen vorher
    w._selected = False
    _warte_marke(c)
    assert not m.isVisible()
    assert _pixel(c, links) == vorher


def test_rahmen_mindestens_drei_pixel_touch_vier(monkeypatch):
    assert am.rahmen_dicke() in (3, 4)
    monkeypatch.setattr(am, "touch_aktiv", lambda: True)
    assert am.rahmen_dicke() == 4
    monkeypatch.setattr(am, "touch_aktiv", lambda: False)
    assert am.rahmen_dicke() == 3


def test_helle_widgets_bekommen_dunkle_kontur():
    c, ws = _flaeche()
    w = ws["VCLabel"]
    w.set_background_color(QColor("#ffffff"))
    w._selected = True
    _warte_marke(c)
    r = c._lage(w)
    assert _pixel(c, QPoint(r.x(), r.center().y())).lightness() < 60
    assert _nah(_pixel(c, QPoint(r.x() + 2, r.center().y())), am.AKZENT)


def test_mehrfachauswahl_zaehler_und_toolbar():
    c, ws = _flaeche()
    for t in ("VCButton", "VCSlider", "Kasten-Kind"):
        ws[t]._selected = True
    m = _warte_marke(c)
    assert m.zaehler_text() == "3 gewählt"
    lage = m.zaehler_lage()
    assert not lage.isEmpty()
    assert _nah(_pixel(c, QPoint(lage.x() + 1, lage.center().y())), am.AKZENT, 70)
    ws["VCSlider"]._selected = False
    _warte_marke(c)
    assert m.zaehler_text() == "2 gewählt"
    ws["Kasten-Kind"]._selected = False
    _warte_marke(c)
    assert m.zaehler_text() == ""


def test_ueberlagerung_laesst_maus_durch_und_childat():
    c, ws = _flaeche()
    w = ws["VCButton"]
    w._selected = True
    m = _warte_marke(c)
    assert m.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    mitte = c._lage(w).center()
    assert c.childAt(mitte) is not m
    leer = QPoint(1250, 30)
    assert c.childAt(leer) is None, "freie Flaeche bleibt frei (Rahmen, Wischen)"
    # Klick auf ein anderes Widget waehlt dieses (Maus kommt an)
    s = ws["VCSlider"]
    # ueber das Fenster, wie eine echte Maus (Qt sucht das Ziel selbst)
    QTest.mouseClick(c.windowHandle(), Qt.MouseButton.LeftButton, pos=c._lage(s).center())
    _warte_marke(c)
    assert m.gewaehlt() == [s]


def test_folgt_verschieben_groesse_und_kasten():
    c, ws = _flaeche()
    kind, fr = ws["Kasten-Kind"], ws["VCFrame"]
    kind._selected = True
    m = _warte_marke(c)
    alt = m.rechtecke()[0]
    fr.move(fr.x() + 50, fr.y() + 10)
    QApplication.processEvents()
    assert m.rechtecke()[0].topLeft() == alt.topLeft() + QPoint(50, 10)
    kind.resize(150, 100)
    QApplication.processEvents()
    assert m.rechtecke()[0].size().width() == 150
    # an der Kastengrenze beschnitten
    kind.move(250, 60)
    QApplication.processEvents()
    r = m.rechtecke()[0]
    assert r.right() <= c._lage(fr).right()


def test_spielbetrieb_unsichtbar_und_ohne_auswahl_nichts_beobachtet():
    c, ws = _flaeche()
    m = _warte_marke(c)
    assert not m.isVisible() and m._beobachtet == []
    ws["VCXYPad"]._selected = True
    _warte_marke(c)
    assert m.isVisible() and m._beobachtet
    c.set_edit_mode(False)
    _warte_marke(c)
    assert not m.isVisible() and m._beobachtet == []


def test_bankwechsel_nimmt_markierung_mit():
    c, ws = _flaeche()
    w = ws["VCButton"]
    w.bank = 0
    c._apply_bank_visibility()
    w._selected = True
    m = _warte_marke(c)
    assert m.gewaehlt() == [w]
    c.set_active_bank(1)
    _warte_marke(c)
    assert m.gewaehlt() == [] and not m.isVisible()


def test_neues_widget_liegt_nicht_ueber_der_markierung():
    c, ws = _flaeche()
    ws["VCButton"]._selected = True
    m = _warte_marke(c)
    c._add_widget("VCButton", QPoint(900, 500))
    _warte_marke(c)
    kinder = [k for k in c.children() if hasattr(k, "isWidgetType") and k.isWidgetType()]
    assert kinder[-1] is m or kinder.index(m) > max(
        i for i, k in enumerate(kinder) if k.__class__.__name__.startswith("VC"))


def test_alt_show_laedt_unveraendert():
    """Abwaertskompatibel: eine Alt-Show (ohne neue Felder) laedt, die Marke
    speichert nichts."""
    alt = {"widgets": [{"type": "VCButton", "caption": "Rot", "x": 10, "y": 10,
                        "w": 80, "h": 60, "bank": -1}]}
    c = VCCanvas()
    c.from_dict(alt)
    assert [w.caption for w in c.alle_widgets()] == ["Rot"]
    w = c.alle_widgets()[0]
    w._selected = True
    d = c.to_dict()
    assert "vc_ausgewaehlt" not in str(d) and "_selected" not in str(d)

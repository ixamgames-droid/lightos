"""VCB-52: Befunde aus dem Live-Klicktest 23.11. in der Virtual Console.

1. Pixelraster: 'Sicher?' faellt nach Ablauf sichtbar zurueck, Anzeige und
   Tipp passen zusammen.
2. Pixelraster-Werkzeugleiste: Beschriftungen passen in Standardgroesse,
   Tooltips je Knopf, Touch weiter >= 44 px.
3. Langer Rahmen-Name wird hinten mit … gekuerzt.
4. Inspector zeigt nach Umbenennen im Rahmen-Dialog den neuen Namen.
5. Neue Elemente ueberdecken keine vorhandenen; im Rahmen zaehlt die
   Klickstelle.
6. Menue 'Widget hinzufügen' mit deutschen Namen wie die Werkzeugleiste.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics, QMouseEvent           # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QWidget  # noqa: E402

from src.ui import touch_keyboard                                    # noqa: E402
from src.ui.virtualconsole import vc_pixelraster as vp               # noqa: E402
from src.ui.virtualconsole.vc_frame import VCFrame                   # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt_touch = touch_keyboard.is_touch_mode()
    alt_lock = VCWidget.input_locked
    touch_keyboard.setze_touch_modus(False)
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    VCWidget.input_locked = alt_lock
    destroy_all_top_level_widgets(_app)


def _maus(w, typ, pos: QPoint):
    knopf = Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), knopf, knoepfe,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _klick(w, pos):
    _maus(w, QEvent.Type.MouseButtonPress, pos)
    _maus(w, QEvent.Type.MouseButtonRelease, pos)


def _warte_bis(bedingung, sekunden: float) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        QTest.qWait(20)
    return bedingung()


def _raster(w=315, h=240):
    eltern = QWidget()
    eltern.resize(w + 40, h + 40)
    p = vp.VCPixelraster("PAR-Reihe malen")
    p.setParent(eltern)
    p.resize(w, h)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    QApplication.processEvents()
    return p


# ── 1: Loeschen-Rueckfrage laeuft sichtbar ab ───────────────────────────────

def test_sicher_faellt_nach_ablauf_zurueck_und_anzeige_stimmt(monkeypatch):
    monkeypatch.setattr(vp, "LOESCHEN_SCHARF_S", 0.2)
    p = _raster()
    p.pixel = {"0,0": "#ff0000"}
    gemalt = []
    orig = p._knopf_text

    def _merke(k, t):
        text = orig(k, t)
        if k == "loeschen":
            gemalt.append(text)
        return text
    p._knopf_text = _merke
    pos = p.knopf_rechtecke()["loeschen"].center()
    _klick(p, pos)
    assert p.loeschen_scharf()
    assert _warte_bis(lambda: gemalt and gemalt[-1] == "Sicher?", 3.0)
    # Ablauf: die GEZEICHNETE Anzeige muss von selbst zurueckspringen
    # (vorher wurde nach Ablauf nicht neu gezeichnet -> 'Sicher?' blieb stehen)
    assert _warte_bis(lambda: gemalt[-1] == "Löschen", 3.0), gemalt[-3:]
    assert not p.loeschen_scharf()
    assert p._knopf_text("loeschen", "Löschen") == "Löschen"
    # Tipp auf das wieder angezeigte 'Löschen' macht nur scharf, loescht nicht
    _klick(p, pos)
    assert p.pixel == {"0,0": "#ff0000"} and p.loeschen_scharf()
    # solange 'Sicher?' steht, loescht der Tipp
    _klick(p, pos)
    assert p.pixel == {} and not p.loeschen_scharf()


def test_loeschen_braucht_weiter_zwei_tipps():
    p = _raster()
    p.pixel = {"1,0": "#00ff00"}
    pos = p.knopf_rechtecke()["loeschen"].center()
    _klick(p, pos)
    assert p.pixel, "ein Tipp allein loescht nie"


# ── 2: Werkzeugleiste lesbar ────────────────────────────────────────────────

def _passt_alles(p):
    f = QFont(p.font())
    f.setPixelSize(14 if touch_keyboard.is_touch_mode() else 12)
    fm = QFontMetrics(f)
    r = p.knopf_rechtecke()
    for k, t in vp.KNOEPFE:
        if k == "farbe":
            continue
        for text in {t, p._knopf_text(k, t), "Sicher?" if k == "loeschen" else t,
                     "Abruf 1/1" if k == "abruf" else t}:
            assert fm.horizontalAdvance(text) <= r[k].width() - 4, (k, text, r[k].width())


def test_beschriftungen_passen_in_standardgroesse():
    p = _raster(315, 240)
    _passt_alles(p)


def test_jeder_knopf_hat_tooltip():
    assert set(vp.KNOPF_HILFE) == {k for k, _t in vp.KNOEPFE}


def test_touch_beschriftung_und_44_px():
    touch_keyboard.setze_touch_modus(True)
    p = _raster(315, 300)
    for k, q in p.knopf_rechtecke().items():
        assert q.width() >= 44 and q.height() >= 44, (k, q)
    _passt_alles(p)


# ── 3: Langer Rahmen-Name ───────────────────────────────────────────────────

def test_langer_rahmenname_hinten_mit_ellipse():
    f = VCFrame("Solo Farben - ein sehr langer Rahmenname zum Testen der Kopfzeile")
    f.resize(260, 160)
    t = f.kopf_text()
    assert t.startswith("Solo Farben") and t.endswith("…")
    kurz = VCFrame("Extras")
    kurz.resize(260, 160)
    assert kurz.kopf_text() == "Extras"


# ── 4: Inspector nach Umbenennen ────────────────────────────────────────────

def test_inspector_zeigt_neuen_namen_nach_dialog(monkeypatch):
    from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
    f = VCFrame("Frame")
    panel = VCInspectorPanel()
    panel.bind(f)
    assert "Frame" in panel._subtitle.text()

    def _dialog(self):
        self.caption = "Extras"
    monkeypatch.setattr(VCFrame, "_open_properties", _dialog)
    panel._open_modal(f)
    assert panel._subtitle.text() == "„Extras“"


# ── 5: Platzierung ──────────────────────────────────────────────────────────

def _view():
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    v.resize(1200, 800)
    v._btn_edit.setChecked(True)
    return v


def test_werkzeugleiste_legt_nicht_uebereinander():
    v = _view()
    for wtype in ("VCPixelraster", "VCPixelraster", "VCFrame", "VCButton"):
        v._add_widget(wtype)
    ws = [w for w in v._canvas.findChildren(
        VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)]
    assert len(ws) == 4
    for i, a in enumerate(ws):
        for b in ws[i + 1:]:
            assert not a.geometry().intersects(b.geometry()), (a, b)


def test_rahmen_menue_nutzt_klickstelle_und_deutsche_namen(monkeypatch):
    eltern = QWidget()
    eltern.resize(500, 400)
    f = VCFrame("Kasten")
    f.setParent(eltern)
    f.resize(400, 300)
    f.set_edit_mode(True)
    eltern.show()
    QApplication.processEvents()
    gesehen = {}

    class _Menue(QMenu):
        def exec(self, *_a, **_k):
            unter = [m for m in self.findChildren(QMenu)
                     if m.title() == "Widget hinzufügen"][0]
            gesehen["namen"] = [a.text() for a in unter.actions()]
            return [a for a in unter.actions() if a.data() == "VCButton"][0]
    import src.ui.virtualconsole.vc_frame as vf
    monkeypatch.setattr(vf, "QMenu", _Menue)
    klick = QPoint(20, 200)
    f._show_context_menu(f.mapToGlobal(klick))
    kinder = f.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kinder) == 1
    k = kinder[0]
    assert abs(k.x() - klick.x()) <= 16 and abs(k.y() - klick.y()) <= 16, k.pos()
    namen = gesehen["namen"]
    for deutsch in ("Fader", "Cueliste", "Farbe", "Effekt-Farben", "Chase-Liste"):
        assert deutsch in namen
    for englisch in ("Slider", "CueList", "Color", "ColorList", "SongInfo", "EffectColors"):
        assert englisch not in namen


def test_rahmen_zweites_element_ueberdeckt_erstes_nicht():
    f = VCFrame("Kasten")
    f.resize(400, 300)
    f.set_edit_mode(True)
    a = f._add_child_widget("VCButton")
    b = f._add_child_widget("VCButton")
    assert not a.geometry().intersects(b.geometry())
    cr = f._content_rect()
    assert cr.contains(b.geometry())


def test_alte_show_mit_rahmen_laedt_unveraendert():
    """Gespeicherte Lagen bleiben, wie sie sind (auch uebereinander)."""
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    alt = {"widgets": [
        {"type": "VCButton", "x": 40, "y": 40, "w": 80, "h": 60, "caption": "A"},
        {"type": "VCButton", "x": 40, "y": 40, "w": 80, "h": 60, "caption": "B"},
        {"type": "VCFrame", "x": 200, "y": 40, "w": 260, "h": 160,
         "caption": "Solo Farben - ein sehr langer Rahmenname"},
    ]}
    c.from_dict(alt)
    ws = c.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    lagen = sorted((w.caption, w.x(), w.y()) for w in ws)
    assert ("A", 40, 40) in lagen and ("B", 40, 40) in lagen
    assert any(w.caption.startswith("Solo") for w in ws)

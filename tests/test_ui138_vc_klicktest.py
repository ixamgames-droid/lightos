"""UI-138: Klick-Test der Virtuellen Konsole — fuenf Funde.

1. Tastenbeschriftungen wurden abgeschnitten („PAR egenboge", „uflic"): die
   Schrift wird jetzt schrittweise bis 7 pt kleiner, ein zu langes Wort bricht
   mit Bindestrich um, die letzte Zeile endet notfalls mit „…" und der Volltext
   steht im Tooltip. Gemessen an echten Pixeln: kein Zeichen ausserhalb der
   Taste, drei Tastengroessen, Maus und Touch. Kurze Texte bleiben wie bisher,
   die gespeicherte Show bleibt unberuehrt, gesucht wird je Taste nur einmal.
2. Auswahlmarke: der Haken sitzt auf der Ecke (halb ausserhalb), der Zaehler
   „3 gewählt" steht im Knopf „Ausrichten" statt auf der Nachbartaste.
3. Demo-Show MEGA ARENA: der Generator prueft Label-Ueberlappungen selbst
   (laufen tut er in test_tool7/test_qa84/...; hier nur die Naht im Quelltext).
4. VC-Werkzeugleiste: im Touch-Modus 12-px-Schrift statt 10 px; bei 1280 px
   bleibt die Spielbetrieb-Leiste einzeilig, mit der Maus aendert sich nichts.
5. Einheitlich „MIDI Lernen" statt „MIDI Teach…" im Rechtsklick-Menue.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt         # noqa: E402
from PySide6.QtGui import QFontMetricsF, QHelpEvent                  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QToolTip    # noqa: E402

from src.ui import touch_keyboard                                    # noqa: E402
from src.ui.virtualconsole import vc_button as vb                    # noqa: E402
from src.ui.virtualconsole import vc_auswahl_marke as am             # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas                 # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GROESSEN = [(72, 72), (120, 48), (48, 48)]
LANGE = ["PAR Regenbogen", "Aufblitzen Spider", "Donaudampfschifffahrt",
         "Programmer leeren und Effekte stoppen", "Farbwechsel Regenbogenmuster"]


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt_touch = touch_keyboard.is_touch_mode()
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)


def _warten(n=8):
    for _ in range(n):
        QApplication.processEvents()


def _taste(caption, w, h):
    c = VCCanvas()
    c.resize(400, 300)
    b = c._add_widget("VCButton", QPoint(40, 40))
    b.caption = caption
    b.resize(w, h)
    c.show()
    _warten()
    return c, b


def _bild(b):
    b.update()
    _warten(3)
    return b.grab().toImage()


def _diff_rahmen(a, b) -> QRect | None:
    """Umrechteck aller Pixel, die sich zwischen zwei Bildern unterscheiden."""
    dpr = a.devicePixelRatio() or 1.0
    xs, ys = [], []
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return QRect(int(min(xs) / dpr), int(min(ys) / dpr),
                 int((max(xs) - min(xs)) / dpr) + 1, int((max(ys) - min(ys)) / dpr) + 1)


# ── Fund 1: Beschriftung einpassen ───────────────────────────────────────────

@pytest.mark.parametrize("touch", [False, True], ids=["maus", "touch"])
@pytest.mark.parametrize("w,h", GROESSEN)
@pytest.mark.parametrize("text", LANGE)
def test_lange_beschriftung_passt_ins_rechteck(text, w, h, touch):
    touch_keyboard.setze_touch_modus(touch)
    f, t, flags, _gek = vb.beschriftung_einpassen(text, w, h)
    assert f.pointSizeF() >= 7.0
    br = QFontMetricsF(f).boundingRect(QRectF(0, 0, w, h), flags, t)
    assert br.width() <= w and br.height() <= h + 0.5, (text, w, h, t, br)
    if not flags & Qt.TextFlag.TextWordWrap:          # selbst umbrochen
        for zeile in t.split("\n"):
            assert QFontMetricsF(f).horizontalAdvance(zeile) <= w, (text, zeile)


@pytest.mark.parametrize("touch", [False, True], ids=["maus", "touch"])
@pytest.mark.parametrize("w,h", GROESSEN)
def test_kein_zeichen_ausserhalb_der_taste_pixel(w, h, touch):
    touch_keyboard.setze_touch_modus(touch)
    for text in ("Regenbogenfarbwechsel", "PAR Regenbogen Farbwechsel Aufblitzen"):
        c, b = _taste("", w, h)
        leer = _bild(b)
        b.caption = text
        voll = _bild(b)
        r = _diff_rahmen(leer, voll)
        assert r is not None, "Text wurde gar nicht gezeichnet"
        # Die Flaeche der Taste beginnt 2 px innen; dort beschneidet der Maler.
        # Text, der bis an diese Kante reicht, wurde abgeschnitten.
        innen = QRect(3, 3, w - 6, h - 6)
        assert innen.contains(r), (text, w, h, r)
        c.close()


def test_kurzer_text_bleibt_wie_bisher():
    for text in ("GO", "Tap", "MH Rot", "Licht An"):
        f, t, flags, gek = vb.beschriftung_einpassen(text, 72, 72)
        assert f.pointSizeF() == 9.0 and f.bold() and f.family() == "Segoe UI"
        assert t == text and not gek
        assert flags == Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap


def test_kuerzung_mit_auslassung_und_tooltip():
    c, b = _taste("Donaudampfschifffahrtsgesellschaftskapitaensmuetze und mehr", 48, 40)
    _bild(b)
    assert b.beschriftung_gekuerzt()
    _f, t, _fl = b._beschriftung(QRect(0, 0, 48, 40), b.caption)
    assert t.endswith("…") or "-\n" in t
    assert b.beschriftung_tooltip().startswith(b.caption)
    ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), b.mapToGlobal(QPoint(5, 5)))
    assert b.event(ev)
    assert QToolTip.text().startswith(b.caption) or not QToolTip.isVisible()
    QToolTip.hideText()
    # eigener Tooltip (z. B. tote Bindung) bleibt erhalten und steht dahinter
    b.setToolTip("Hinweis")
    assert b.beschriftung_tooltip().endswith("Hinweis")


def test_ungekuerzt_kein_eigener_tooltip():
    c, b = _taste("GO", 72, 72)
    _bild(b)
    assert not b.beschriftung_gekuerzt()


def test_show_bleibt_unberuehrt():
    c, b = _taste("PAR Regenbogen Farbwechsel", 48, 48)
    vorher = b.to_dict()
    _bild(b)
    assert b.to_dict() == vorher
    assert b.caption == "PAR Regenbogen Farbwechsel"


def test_schriftgroesse_wird_zwischengespeichert(monkeypatch):
    c, b = _taste("PAR Regenbogen", 56, 56)
    _bild(b)
    aufrufe = []
    echt = vb.beschriftung_einpassen

    def zaehlen(*a, **k):
        aufrufe.append(a[0])
        return echt(*a, **k)

    monkeypatch.setattr(vb, "beschriftung_einpassen", zaehlen)
    for _ in range(4):
        b.repaint()
    assert aufrufe == []
    b.caption = "Neuer Text"
    b.repaint()
    b.repaint()
    assert aufrufe == ["Neuer Text"]
    b.resize(90, 56)
    _bild(b)
    assert len(aufrufe) == 2


def test_alte_show_laedt_und_zeichnet():
    """Abwaertskompatibel: ein Tasten-Dict ohne neue Felder (wie aus einer
    alten Show) laedt, zeichnet und speichert unveraendert."""
    alt = {"type": "VCButton", "caption": "Lauflicht Regenbogen", "x": 10, "y": 10,
           "w": 56, "h": 56, "bank": 0}
    c = VCCanvas()
    c.resize(300, 200)
    b = c._add_widget("VCButton", QPoint(10, 10))
    b.apply_dict(alt)
    c.show()
    _bild(b)
    d = b.to_dict()
    assert d["caption"] == "Lauflicht Regenbogen" and d["w"] == 56 and d["h"] == 56


# ── Fund 2: Auswahlmarke ─────────────────────────────────────────────────────

def _flaeche_mit_auswahl(n=3):
    c = VCCanvas()
    c.resize(900, 500)
    ws = []
    for i in range(n):
        w = c._add_widget("VCButton", QPoint(80 + i * 130, 120))
        w.resize(120, 80)
        w.caption = "BLACKOUT"
        ws.append(w)
    c.set_edit_mode(True)
    c.show()
    _warten()
    for w in ws:
        w._selected = True
    _warten(20)
    m = c.auswahl_marke()
    m.auffrischen()
    _warten()
    return c, ws, m


@pytest.mark.parametrize("touch", [False, True], ids=["maus", "touch"])
def test_haken_sitzt_auf_der_ecke_nicht_auf_der_beschriftung(touch):
    touch_keyboard.setze_touch_modus(touch)
    c, ws, m = _flaeche_mit_auswahl(1)
    r = c._lage(ws[0])
    d = 22 if touch else 16
    k = am.AuswahlMarke.haken_kreis(r, d)
    assert k.center().toPoint() == r.topLeft()
    # hoechstens ein Viertel liegt auf dem Widget
    innen = k.intersected(QRectF(r))
    assert innen.width() <= d / 2 + 0.5 and innen.height() <= d / 2 + 0.5
    # der Teil ausserhalb ist wirklich gemalt (Akzentfarbe)
    img = c.grab().toImage()
    dpr = img.devicePixelRatio() or 1.0
    p = QPoint(r.x() - d // 4, r.y() - d // 4)
    farbe = img.pixelColor(int(p.x() * dpr), int(p.y() * dpr))
    assert abs(farbe.red() - am.AKZENT.red()) < 60 and abs(farbe.green() - am.AKZENT.green()) < 60
    # die Beschriftung (Mitte bis knapp an den Rahmen) bleibt frei vom Haken
    b = am.rahmen_dicke()
    text_bereich = QRectF(r.x() + b + 2, r.y() + d / 2 + 1, r.width() - 2 * b - 4, r.height() / 2)
    assert not k.intersects(text_bereich)


def test_kein_zaehler_auf_der_flaeche():
    c, ws, m = _flaeche_mit_auswahl(3)
    assert m.zaehler_text() == "3 gewählt"
    assert not hasattr(m, "zaehler_lage")
    # unter der Auswahl (dort lag der Zaehler) bleibt die Flaeche unbemalt
    box = c._lage(ws[0]).united(c._lage(ws[-1]))
    img = c.grab().toImage()
    dpr = img.devicePixelRatio() or 1.0
    y = box.bottom() + 12
    for x in range(box.left(), box.left() + 80, 4):
        f = img.pixelColor(int(x * dpr), int(y * dpr))
        assert not (abs(f.red() - am.AKZENT.red()) < 40 and abs(f.green() - am.AKZENT.green()) < 40), x


def _ansicht(breite=1600):
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    v.resize(breite, 800)
    v.show()
    _warten()
    return v


def test_zaehler_steht_im_knopf_ausrichten_und_breite_bleibt():
    v = _ansicht()
    v._btn_edit.setChecked(True)
    _warten()
    k = v._btn_ausrichten
    assert k.text() == "Ausrichten ▾"
    breite = k.width()
    c = v._canvas
    a = c._add_widget("VCButton", QPoint(40, 40))
    b = c._add_widget("VCButton", QPoint(300, 40))
    d = c._add_widget("VCButton", QPoint(500, 40))
    c.auswahl_setzen([a, b, d])
    _warten()
    assert k.text() == "Ausrichten · 3 gewählt ▾"
    assert k.width() == breite, "Leiste darf beim Waehlen nicht umbrechen (VCB-47)"
    assert k.width() >= k.sizeHint().width() - 1, "Text abgeschnitten"
    c.auswahl_setzen([a])
    _warten()
    assert k.text() == "Ausrichten ▾"
    c.auswahl_setzen([a, b])
    v._btn_edit.setChecked(False)
    _warten()
    assert k.text() == "Ausrichten ▾"


# ── Fund 3: Generator prueft Label-Ueberlappung ─────────────────────────────

def test_generator_hat_label_selbstpruefung():
    with open(os.path.join(REPO, "tools", "build_mega_arena_2026.py"), encoding="utf-8") as f:
        src = f.read()
    assert "Label-Ueberlappung" in src
    assert "def _label_hoehe" in src
    assert "ROW_STEP" in src and "- 16," not in src


# ── Fund 4: Leistenschrift ───────────────────────────────────────────────────

def _leisten_knoepfe(v):
    return [b for b in v._toolbar_widget.findChildren(QPushButton) if b.isVisible()]


def test_touch_leiste_lesbare_schrift():
    from src.ui.views import virtual_console_view as vcv
    touch_keyboard.setze_touch_modus(True)
    v = _ansicht(1280)
    assert vcv._tb_schrift() >= 12
    for b in _leisten_knoepfe(v):
        assert "font-size:10px" not in b.styleSheet(), b.text()
    assert v._btn_midi_learn.fontInfo().pixelSize() >= 12


def test_maus_leiste_unveraendert():
    from src.ui.views import virtual_console_view as vcv
    touch_keyboard.setze_touch_modus(False)
    v = _ansicht(1280)
    assert vcv._tb_schrift() == 10
    assert "font-size:10px" in v._btn_midi_learn.styleSheet()
    assert "padding:0 8px" in v._btn_midi_learn.styleSheet()
    assert v._btn_edit.width() == 90


@pytest.mark.parametrize("touch", [False, True], ids=["maus", "touch"])
def test_spielbetrieb_leiste_1280_einzeilig_nichts_abgeschnitten(touch):
    touch_keyboard.setze_touch_modus(touch)
    v = _ansicht(1280)
    bs = _leisten_knoepfe(v)
    assert len({b.y() for b in bs}) == 1, [(b.text(), b.y()) for b in bs]
    tb = v._toolbar_widget
    for b in bs:
        assert b.geometry().right() <= tb.width(), b.text()
        assert b.width() >= b.sizeHint().width() - 1, (b.text(), b.width(), b.sizeHint())
    if touch:
        assert all(b.height() >= 44 for b in bs), [(b.text(), b.height()) for b in bs]
    v._btn_edit.setChecked(True)
    _warten()
    for b in _leisten_knoepfe(v):
        assert b.geometry().right() <= tb.width(), b.text()
        assert b.width() >= b.sizeHint().width() - 1, (b.text(), b.width(), b.sizeHint())


# ── Fund 5: Benennung ────────────────────────────────────────────────────────

def test_kontextmenue_heisst_midi_lernen():
    c, b = _taste("X", 72, 72)
    c.set_edit_mode(True)
    menue = b._baue_kontextmenue()
    texte = [a.text() for a in menue.actions()]
    assert "🎹 MIDI Lernen..." in texte
    assert not any("Teach" in t for t in texte), texte


def test_lern_dialog_titel():
    import inspect
    from src.ui.widgets.midi_teach_dialog import MidiTeachDialog
    sig = inspect.signature(MidiTeachDialog.__init__)
    assert sig.parameters["title"].default == "MIDI Lernen"

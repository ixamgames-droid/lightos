"""UI-126: Mehrfachauswahl von VC-Widgets im Bearbeiten-Modus.

Maus: Strg/Umschalt-Klick nimmt dazu/heraus, ein Rahmen auf der freien
Flaeche waehlt alles, was er beruehrt. Finger: Umschalter „Mehrfach" in der
Werkzeugleiste (nur im Touch-Modus sichtbar), dann schaltet jeder Tipp ein
Widget um. Gemeinsam verschieben (Raster je Widget), ausrichten/verteilen,
loeschen — je ein Rueckgaengig-Schritt. Inspector zeigt die Auswahl. Der
Spielbetrieb bleibt unveraendert. Finger ueber ``QTest.touchEvent``.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QWidget       # noqa: E402

from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole.vc_canvas import VCCanvas                 # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_STRG = Qt.KeyboardModifier.ControlModifier
_UMSCH = Qt.KeyboardModifier.ShiftModifier
_KEIN = Qt.KeyboardModifier.NoModifier


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    alt_touch = touch_keyboard.is_touch_mode()
    alt_lock = VCWidget.input_locked
    alt_dk = QApplication.styleHints().mouseDoubleClickInterval()
    yield
    QApplication.styleHints().setMouseDoubleClickInterval(alt_dk)
    touch_keyboard.setze_touch_modus(alt_touch)
    VCWidget.input_locked = alt_lock
    destroy_all_top_level_widgets(_app)


def _flaeche(n=3, edit=True):
    from src.ui.virtualconsole.vc_button import VCButton
    c = VCCanvas()
    c.resize(1200, 800)
    ws = []
    for i in range(n):
        b = c._add_widget("VCButton", QPoint(40 + i * 200, 40 + i * 64))
        assert isinstance(b, VCButton)
        b.resize(120, 60)
        ws.append(b)
    c.set_edit_mode(edit)
    c.show()
    QApplication.processEvents()
    c._undo_stack.clear()
    c._undo_marken.clear()
    return c, ws


def _maus(w, typ, pos: QPoint, mod=_KEIN):
    knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), knopf, knoepfe, mod)
    QApplication.sendEvent(w, ev)


def _klick(w, mod=_KEIN, pos=None):
    pos = pos or QPoint(w.width() // 2, w.height() // 2)
    _maus(w, QEvent.Type.MouseButtonPress, pos, mod)
    _maus(w, QEvent.Type.MouseButtonRelease, pos, mod)
    QApplication.processEvents()


def _maus_zug(w, start: QPoint, ende: QPoint, mod=_KEIN, schritte=5):
    _maus(w, QEvent.Type.MouseButtonPress, start, mod)
    for i in range(1, schritte + 1):
        _maus(w, QEvent.Type.MouseMove, start + (ende - start) * (i / schritte), mod)
    _maus(w, QEvent.Type.MouseButtonRelease, ende, mod)
    QApplication.processEvents()


def _tipp(w, pos=None):
    pos = pos or QPoint(w.width() // 2, w.height() // 2)
    # Erster Tipp mit 1 ms Doppelklick-Fenster: jeder Tipp beginnt ein neues
    # Klick-Paar (sonst wird der zweite Tipp auf dasselbe Widget ein Doppelklick).
    QApplication.styleHints().setMouseDoubleClickInterval(1)
    QTest.touchEvent(w, _DEV).press(0, pos, w).commit()
    QApplication.processEvents()
    QTest.touchEvent(w, _DEV).release(0, pos, w).commit()
    QApplication.processEvents()
    QTest.qWait(5)


def _finger_zug(w, start: QPoint, ende: QPoint, schritte=8):
    QTest.touchEvent(w, _DEV).press(0, start, w).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        QTest.touchEvent(w, _DEV).move(0, start + (ende - start) * (i / schritte), w).commit()
        QApplication.processEvents()
    QTest.touchEvent(w, _DEV).release(0, ende, w).commit()
    QApplication.processEvents()


# ── Maus: Strg/Umschalt-Klick ────────────────────────────────────────────────

def test_maus_strg_klick_nimmt_dazu_und_heraus():
    c, (a, b, d) = _flaeche()
    _klick(a)
    assert c.ausgewaehlte() == [a]
    _klick(b, _STRG)
    assert c.ausgewaehlte() == [a, b]
    _klick(d, _UMSCH)
    assert c.ausgewaehlte() == [a, b, d]
    _klick(b, _STRG)
    assert c.ausgewaehlte() == [a, d], "zweiter Strg-Klick nimmt heraus"


def test_maus_klick_ohne_taste_ersetzt_wie_bisher():
    c, (a, b, d) = _flaeche()
    _klick(a)
    _klick(b, _STRG)
    _klick(d)
    assert c.ausgewaehlte() == [d]
    # Klick auf ein Widget der Auswahl ohne Bewegung: nur noch dieses
    _klick(a, _STRG)
    _klick(b, _STRG)
    assert c.ausgewaehlte() == [a, b, d]
    _klick(a)
    assert c.ausgewaehlte() == [a]


def test_maus_klick_ins_leere_hebt_auswahl_auf():
    c, (a, b, _d) = _flaeche()
    _klick(a)
    _klick(b, _STRG)
    _klick(c, pos=QPoint(1100, 700))
    assert c.ausgewaehlte() == []
    assert not a._selected and not b._selected


# ── Maus: Auswahlrahmen ──────────────────────────────────────────────────────

def test_maus_rahmen_waehlt_beruehrte_widgets():
    c, (a, b, d) = _flaeche()
    # Rahmen von links oben bis in das zweite Widget hinein
    _maus_zug(c, QPoint(10, 10), QPoint(250, 120))
    assert c.ausgewaehlte() == [a, b]
    assert c._rahmen is None, "Rahmen ist nach dem Loslassen weg"
    # Strg + Rahmen nimmt dazu
    _maus_zug(c, QPoint(1150, 500), QPoint(500, 150), _STRG)
    assert c.ausgewaehlte() == [a, b, d]
    # neuer Rahmen ohne Taste ersetzt
    _maus_zug(c, QPoint(1150, 500), QPoint(500, 150))
    assert c.ausgewaehlte() == [d]


def test_maus_kleiner_zug_ist_kein_rahmen():
    c, (a, _b, _d) = _flaeche()
    _klick(a)
    _maus_zug(c, QPoint(1100, 700), QPoint(1101, 701), schritte=1)
    assert c.ausgewaehlte() == []


# ── Gemeinsam verschieben ────────────────────────────────────────────────────

def test_gemeinsam_ziehen_mit_raster_ein_rueckgaengig_schritt():
    c, (a, b, d) = _flaeche()
    c.set_snap_to_grid(True)
    _klick(a)
    _klick(b, _STRG)
    pa, pb, pd = a.pos(), b.pos(), d.pos()
    mitte = QPoint(60, 30)
    _maus_zug(a, mitte, mitte + QPoint(37, 21))
    assert a.pos() != pa and b.pos() != pb
    assert d.pos() == pd, "nicht gewaehltes Widget bleibt"
    for w in (a, b):
        assert w.x() % 8 == 0 and w.y() % 8 == 0, "Raster je Widget"
    assert (a.pos() - pa) == (b.pos() - pb), "gleicher Versatz"
    assert len(c._undo_stack) == 1
    assert c.ausgewaehlte() == [a, b], "Auswahl bleibt nach dem Zug"
    c.undo()
    lage = {w.widget_id: w.pos() for w in c.alle_widgets()}
    assert lage[a.widget_id] == pa and lage[b.widget_id] == pb


def test_gemeinsam_ziehen_staucht_nicht_am_rand():
    c, (a, b, _d) = _flaeche()
    _klick(a)
    _klick(b, _STRG)
    abstand = b.pos() - a.pos()
    _maus_zug(a, QPoint(60, 30), QPoint(60 - 500, 30 - 500))
    assert a.pos() == QPoint(0, 0)
    assert b.pos() - a.pos() == abstand


def test_kasten_inhalt_wandert_nicht_doppelt():
    c, (a,) = _flaeche(1)
    fr = c._add_widget("VCFrame", QPoint(400, 300))
    fr.resize(300, 200)
    kind = c._add_widget("VCButton", QPoint(0, 0))
    kind.setParent(fr)
    kind.move(20, 40)
    kind.resize(80, 40)
    kind.set_edit_mode(True)
    fr.set_edit_mode(True)
    kind.show()
    QApplication.processEvents()
    fr._selected = kind._selected = a._selected = True
    gruppe = c.gruppe_fuer_zug()
    assert [w for w, _r in gruppe] == [a, fr]
    c.gruppe_ziehen(gruppe, QPoint(16, 8))
    assert kind.pos() == QPoint(20, 40), "Inhalt bleibt im Kasten an seinem Platz"


# ── Ausrichten / Verteilen ───────────────────────────────────────────────────

def _drei_gewaehlt():
    c, ws = _flaeche()
    c.auswahl_setzen(ws)
    return c, ws


@pytest.mark.parametrize("art", ["links", "rechts", "oben", "unten"])
def test_ausrichten(art):
    c, (a, b, d) = _drei_gewaehlt()
    b.resize(160, 90)
    assert c.auswahl_ausrichten(art)
    ws = (a, b, d)
    if art == "links":
        assert len({w.x() for w in ws}) == 1 and a.x() == 40
    elif art == "rechts":
        assert len({w.x() + w.width() for w in ws}) == 1
    elif art == "oben":
        assert len({w.y() for w in ws}) == 1 and a.y() == 40
    else:
        assert len({w.y() + w.height() for w in ws}) == 1
    assert len(c._undo_stack) == 1, "ein Rueckgaengig-Schritt"
    c.undo()
    assert {w.pos().x() for w in c.alle_widgets()} == {40, 240, 440}


def test_verteilen_gleiche_abstaende():
    c, (a, b, d) = _drei_gewaehlt()
    b.move(300, b.y())               # ungleiche Luecken
    d.move(700, d.y())
    assert c.auswahl_ausrichten("waagerecht")
    l1 = b.x() - (a.x() + a.width())
    l2 = d.x() - (b.x() + b.width())
    assert abs(l1 - l2) <= 1
    assert a.x() == 40 and d.x() == 700, "aeussere bleiben stehen"
    b.move(b.x(), 110)
    c.auswahl_setzen([a, b, d])
    assert c.auswahl_ausrichten("senkrecht")
    o1 = b.y() - (a.y() + a.height())
    o2 = d.y() - (b.y() + b.height())
    assert abs(o1 - o2) <= 1


def test_verteilen_braucht_drei_und_ausrichten_zwei():
    c, (a, b, _d) = _flaeche()
    c.auswahl_setzen([a])
    assert not c.auswahl_ausrichten("links")
    c.auswahl_setzen([a, b])
    assert not c.auswahl_ausrichten("waagerecht")
    assert c.auswahl_ausrichten("oben")


def test_ausrichten_mit_raster():
    c, (a, b, _d) = _flaeche()
    a.move(43, 41)
    c.set_snap_to_grid(True)
    c.auswahl_setzen([a, b])
    c.auswahl_ausrichten("links")
    assert a.x() % 8 == 0 and b.x() == a.x()


# ── Loeschen ─────────────────────────────────────────────────────────────────

def test_gemeinsam_loeschen_ein_schritt_rueckgaengig():
    c, (a, b, d) = _flaeche()
    kennung_d = d.widget_id
    c.auswahl_setzen([a, b])
    assert c.auswahl_loeschen() == 2
    QApplication.processEvents()
    assert [w.widget_id for w in c.alle_widgets()] == [kennung_d]
    assert len(c._undo_stack) == 1
    c.undo()
    assert len(c.alle_widgets()) == 3


def test_kontextmenue_bietet_auswahl_an():
    c, (a, b, d) = _flaeche()
    c.auswahl_setzen([a, b])
    menue = a._baue_kontextmenue()
    texte = [act.text() for act in menue.actions()]
    assert "Auswahl (2 Elemente)" in texte
    unter = next(act.menu() for act in menue.actions()
                 if act.text() == "Auswahl (2 Elemente)")
    namen = [x.text() for x in unter.actions() if x.text()]
    assert "⇤ Links ausrichten" in namen and "Auswahl löschen (2)" in namen
    # nicht gewaehltes Widget: Menue wie bisher
    assert "Auswahl (2 Elemente)" not in [x.text() for x in d._baue_kontextmenue().actions()]


# ── Finger: Umschalter „Mehrfach" ────────────────────────────────────────────

def test_finger_ohne_mehrfach_ersetzt_wie_bisher():
    c, (a, b, _d) = _flaeche()
    _tipp(a)
    _tipp(b)
    assert c.ausgewaehlte() == [b]


def test_finger_mehrfach_tipp_schaltet_um_und_zug_verschiebt_alle():
    c, (a, b, d) = _flaeche()
    c.set_mehrfach_modus(True)
    _tipp(a)
    _tipp(b)
    assert c.ausgewaehlte() == [a, b]
    _tipp(d)
    _tipp(d)
    assert c.ausgewaehlte() == [a, b], "zweiter Tipp nimmt heraus"
    pa, pb = a.pos(), b.pos()
    _finger_zug(b, QPoint(60, 30), QPoint(60 + 80, 30 + 40))
    assert a.pos() - pa == b.pos() - pb != QPoint(0, 0)
    assert c.ausgewaehlte() == [a, b], "Zug nimmt nichts heraus"
    assert len(c._undo_stack) == 1


def test_finger_wisch_ins_leere_hebt_auswahl_nicht_auf():
    c, (a, b, _d) = _flaeche()
    c.set_mehrfach_modus(True)
    _tipp(a)
    _tipp(b)
    _finger_zug(c, QPoint(1100, 700), QPoint(1100, 500))
    assert c.ausgewaehlte() == [a, b]


# ── Spielbetrieb unveraendert ────────────────────────────────────────────────

def test_spielbetrieb_keine_auswahl():
    c, (a, b, _d) = _flaeche(edit=False)
    c.set_mehrfach_modus(True)
    pa = a.pos()
    _klick(a, _STRG)
    _klick(b, _STRG)
    _maus_zug(c, QPoint(10, 10), QPoint(600, 400))
    assert c.ausgewaehlte() == []
    assert not a._selected and not b._selected
    assert c._rahmen is None
    assert a.pos() == pa
    assert not c.mehrfach_additiv(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, _STRG))


# ── Inspector und Werkzeugleiste ─────────────────────────────────────────────

def test_inspector_mehrfach_bank_und_loeschen():
    from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
    c, (a, b, d) = _flaeche()
    insp = VCInspectorPanel()
    insp.bind_mehrfach([a, b], c)
    assert insp.ist_mehrfach()
    assert insp._title.text() == "Mehrfachauswahl"
    assert "2" in insp._subtitle.text()
    cb = insp._scroll.widget().findChild(QComboBox, "vc_inspector_mehrfach_bank")
    assert cb is not None and cb.minimumHeight() >= 36
    assert cb.currentData() == 0, "neue Widgets liegen auf der sichtbaren Bank"
    cb.setCurrentIndex(cb.findData(-1))
    assert a.bank == -1 and b.bank == -1 and d.bank == 0
    assert len(c._undo_stack) == 1, "ein Rueckgaengig-Schritt fuer alle"
    c.auswahl_setzen([a, b])
    assert insp._btn_loeschen.isEnabled()
    assert "2" in insp._btn_loeschen.text()
    assert insp.loesche_gewaehltes()
    QApplication.processEvents()
    assert len(c.alle_widgets()) == 1
    # danach wieder Einzel-Inspector
    insp.bind(d)
    assert not insp.ist_mehrfach() and insp._btn_loeschen.text() == "🗑 Löschen"


def test_inspector_einzeln_bleibt_wie_bisher():
    from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
    c, (a, _b, _d) = _flaeche()
    insp = VCInspectorPanel()
    insp.bind_mehrfach([a], c)
    assert not insp.ist_mehrfach()
    assert insp._widget is a


def _ansicht():
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    v.resize(1600, 900)
    v.show()
    QApplication.processEvents()
    return v


def test_ansicht_maus_kein_mehrfach_knopf_aber_ausrichten():
    v = _ansicht()
    v._btn_edit.setChecked(True)
    QApplication.processEvents()
    assert not v._btn_mehrfach.isVisible(), "Maus: Strg/Umschalt statt Knopf"
    assert v._btn_ausrichten.isVisible() and not v._btn_ausrichten.isEnabled()
    c = v._canvas
    a = c._add_widget("VCButton", QPoint(40, 40))
    b = c._add_widget("VCButton", QPoint(300, 40))
    c.auswahl_setzen([a, b])
    assert v._btn_ausrichten.isEnabled()
    assert v._inspector.ist_mehrfach()
    menue = v.ausrichten_menue()
    assert any(x.text() == "⤒ Oben ausrichten" for x in menue.actions())
    c.auswahl_setzen([a])
    assert not v._btn_ausrichten.isEnabled()
    assert not v._inspector.ist_mehrfach()
    v._btn_edit.setChecked(False)
    assert not v._btn_ausrichten.isVisible()


def test_ansicht_touch_mehrfach_knopf_zielgroesse():
    touch_keyboard.setze_touch_modus(True)
    v = _ansicht()
    v._btn_edit.setChecked(True)
    QApplication.processEvents()
    k = v._btn_mehrfach
    assert k.isVisible()
    assert k.height() >= 44 and k.width() >= 44, (k.width(), k.height())
    # (die umgebrochene Touch-Leiste ragt im Offscreen-Bildschirm ueber den
    # Rand — der Knopf wird darum direkt geklickt; der Finger-Ablauf auf der
    # Flaeche steht oben)
    k.click()
    assert k.isChecked() and v._canvas.mehrfach_modus
    assert k.text() == "Mehrfach ✓"
    v._btn_edit.setChecked(False)
    assert not k.isChecked() and not v._canvas.mehrfach_modus
    assert not k.isVisible()

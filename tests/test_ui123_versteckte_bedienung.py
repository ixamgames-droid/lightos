"""UI-123: versteckte Bedienung sichtbar machen (Touch-Audit 11.11.2026).

Befunde A-09 (Doppelklick als einziger Weg), A-15 (anklickbare Etiketten in
der Kopfleiste sehen aus wie Text), C-08 (Farbfilter-Namen nur im Tooltip),
C-15 (Erklaerungen nur im Tooltip) und D-13 (3D: Geraetename nur beim
Maus-Verweilen).

Geprueft mit echtem Touch-Ablauf: ``QTest.touchEvent``, Qt erzeugt die Maus
daraus, der Anwendungsfilter aus UI-110 haengt wie in der App dazwischen.
Gewartet wird auf Bedingungen, nicht auf feste Zeiten. Die 3D-Regeln laufen
ueber node (ohne GPU/Browser) wie in ``test_ui115_flaechen_touch.py``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent                        # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk                              # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.widgets.mehrfach_knopf import TOUCH_HOEHE                # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    vorher = tk.is_touch_mode()
    yield
    f._abbrechen()
    f._menue_aus()
    f._tipp_aus(schild=True)
    f._menue_schlucken = False
    _OFFEN.clear()
    tk.setze_touch_modus(vorher)
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def touch():
    tk.setze_touch_modus(True)
    yield
    tk.setze_touch_modus(False)


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)


def _warte_bis(bedingung, s: float = 5.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return bool(bedingung())


def _sichtbar_machen(w) -> None:
    x = w.parentWidget()
    while x is not None:
        if isinstance(x, QScrollArea):
            x.ensureWidgetVisible(w)
            QApplication.processEvents()
            return
        x = x.parentWidget()


def _druck(w, p: QPoint) -> None:
    # ueber das Fenster (wie UI-120): ein Widget ausserhalb des kleinen
    # offscreen-Bildschirms bekaeme sonst keinen Druck
    win = w.window()
    QTest.touchEvent(win, _DEV).press(0, w.mapTo(win, p), win).commit()
    QApplication.processEvents()


def _zug(w, p: QPoint) -> None:
    win = w.window()
    QTest.touchEvent(win, _DEV).move(0, w.mapTo(win, p), win).commit()
    QApplication.processEvents()


def _los(w, p: QPoint) -> None:
    win = w.window()
    QTest.touchEvent(win, _DEV).release(0, w.mapTo(win, p), win).commit()
    QApplication.processEvents()


def _tipp(w, p: QPoint | None = None) -> None:
    _sichtbar_machen(w)
    p = w.rect().center() if p is None else p
    _druck(w, p)
    _los(w, p)


def _schild_text() -> str:
    s = zs.einrichten(_app).tipp_schild
    return s.text() if s is not None and s.isVisible() else ""


def _lang_halten(w, p: QPoint | None = None) -> QPoint:
    """Finger aufsetzen und liegen lassen, bis die Lang-Druck-Zeit sicher um
    ist (Bedingung: Zeitgeber abgelaufen — kein enger Timer)."""
    f = zs.einrichten(_app)
    p = w.rect().center() if p is None else p
    _druck(w, p)
    t0 = time.monotonic()
    _warte_bis(lambda: time.monotonic() - t0 > zs.LANG_MENUE_S
               and not f._tipp_timer.isActive() and not f._menue_timer.isActive())
    return p


_OFFEN: list = []


def _fenster(*kinder, scroll: bool = False):
    if scroll:
        top = QScrollArea()
        top.setWidgetResizable(True)
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        for k in kinder:
            lay.addWidget(k)
        lay.addWidget(QLabel("\n".join(f"Zeile {i}" for i in range(120))))
        top.setWidget(inhalt)
    else:
        top = QWidget()
        lay = QVBoxLayout(top)
        for k in kinder:
            lay.addWidget(k)
    top.resize(360, 260)
    _OFFEN.append(top)          # sonst raeumt Python das Fenster gleich ab
    top.show()
    QTest.qWaitForWindowExposed(top)
    QApplication.processEvents()
    return top


class _Zaehler:
    def __init__(self):
        self.n = 0

    def __call__(self, *_a):
        self.n += 1


# ── C-15: langes Druecken zeigt die Erklaerung ───────────────────────────────

def test_lang_druck_auf_etikett_zeigt_erklaerung():
    lab = QLabel("Rate")
    lab.setMinimumHeight(60)
    lab.setToolTip("Wie schnell der Effekt läuft (Zyklen je Minute).")
    _fenster(lab, scroll=True)
    p = _lang_halten(lab)
    assert "Zyklen je Minute" in _schild_text(), "Erklaerung erscheint, waehrend der Finger liegt"
    _los(lab, p)
    # bleibt nach dem Loslassen stehen (zum Lesen), Zeitgeber laeuft
    assert _schild_text()
    assert zs.einrichten(_app).tipp_schild._aus.isActive()
    # Schild ueber dem Finger, gut lesbar
    schild = zs.einrichten(_app).tipp_schild
    finger = lab.mapToGlobal(p)
    g = schild.geometry()
    assert not g.adjusted(-20, -20, 20, 20).contains(finger), "Finger verdeckt das Schild nicht"
    if finger.y() - g.height() - 40 > schild.screen().availableGeometry().top():
        assert g.bottom() < finger.y(), "Platz oben: Schild liegt ueber dem Finger"
    assert schild.font().pixelSize() >= 15 or schild.fontInfo().pixelSize() >= 15
    # ein neuer Druck schliesst es
    _tipp(lab, p)
    assert not _schild_text()


def test_lang_druck_auf_knopf_loest_immer_aus():
    """Sicherheit: wer einen Knopf (BLACKOUT, STOP ALL, GO) lange haelt,
    bekommt die Aktion — nie stattdessen eine Erklaerung."""
    b = QPushButton("Rate")
    b.setMinimumHeight(60)
    b.setToolTip("Wie schnell der Effekt läuft (Zyklen je Minute).")
    klick = _Zaehler()
    b.clicked.connect(klick)
    _fenster(b, scroll=True)
    p = _lang_halten(b)
    assert not _schild_text(), "auf Knoepfen keine Erklaerung"
    _los(b, p)
    assert klick.n == 1, "Loslassen nach langem Druck loest den Knopf aus"


def test_kurzer_tipp_zeigt_nichts_und_klickt():
    b = QPushButton("Rate")
    b.setToolTip("Erklaerung")
    klick = _Zaehler()
    b.clicked.connect(klick)
    _fenster(b)
    _tipp(b)
    _warte(zs.LANG_MENUE_S + 0.2)
    assert klick.n == 1 and not _schild_text()


def test_lang_druck_auf_beschriftung():
    lbl = QLabel("Phase")
    lbl.setMinimumHeight(50)
    lbl.setToolTip("Versatz zwischen den Geräten in Grad.")
    _fenster(lbl, scroll=True)
    p = _lang_halten(lbl)
    assert "Versatz" in _schild_text()
    _los(lbl, p)
    assert _schild_text()


def test_erklaerung_vom_vorfahren():
    """Qt reicht die Frage an die Eltern weiter — wie beim Maus-Verweilen."""
    rahmen = QWidget()
    rahmen.setToolTip("Gruppe: Chaser-Schritte")
    lay = QVBoxLayout(rahmen)
    innen = QLabel("Schritt")
    innen.setMinimumHeight(50)
    lay.addWidget(innen)
    _fenster(rahmen)
    p = _lang_halten(innen)
    assert "Chaser-Schritte" in _schild_text()
    _los(innen, p)


def test_menue_hat_vorrang():
    b = QPushButton("M")
    b.setMinimumHeight(60)
    b.setToolTip("darf nicht erscheinen")
    menue = _Zaehler()
    b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    b.customContextMenuRequested.connect(menue)
    _fenster(b)
    assert not zs.lang_druck_tooltip_moeglich(b)
    p = _lang_halten(b)
    _los(b, p)
    assert menue.n == 1 and not _schild_text()


def test_bewegung_bricht_ab():
    b = QPushButton("B")
    b.setMinimumSize(250, 60)
    b.setToolTip("Erklaerung")
    _fenster(b)
    p = b.rect().center()
    _druck(b, p)
    _zug(b, p + QPoint(60, 0))
    _warte(zs.LANG_MENUE_S + 0.2)
    _los(b, p + QPoint(60, 0))
    assert not _schild_text()


def test_ohne_tooltip_wie_bisher():
    b = QPushButton("ohne")
    b.setMinimumHeight(60)
    klick = _Zaehler()
    b.clicked.connect(klick)
    _fenster(b)
    p = _lang_halten(b)
    assert b.isDown()
    _los(b, p)
    assert klick.n == 1 and not _schild_text()


def test_nie_bei_halte_taste_wiederholtaste_liste_und_eigener_flaeche():
    halte = QPushButton("FLASH")
    halte.setToolTip("x")
    halte.pressed.connect(lambda: None)
    wdh = QPushButton("+")
    wdh.setToolTip("x")
    wdh.setAutoRepeat(True)
    liste = QListWidget()
    liste.addItem("eins")
    liste.setToolTip("x")

    class Flaeche(QWidget):
        def mousePressEvent(self, ev):      # noqa: N802
            pass
    flaeche = Flaeche()
    flaeche.setToolTip("x")
    aus = QPushButton("aus")
    aus.setToolTip("x")
    aus.setProperty("lang_druck_tooltip", False)
    _fenster(halte, wdh, liste, flaeche, aus)
    for w in (halte, wdh, liste.viewport(), flaeche, aus):
        assert not zs.lang_druck_tooltip_moeglich(w), w
    # VC im Spielbetrieb
    spiel = QPushButton("VC")
    spiel.setToolTip("x")
    spiel.lang_druck_menue_erlaubt = lambda: False
    assert not zs.lang_druck_tooltip_moeglich(spiel)


def test_eingabefeld_zeigt_erklaerung_druck_bleibt():
    feld = QLineEdit("120")
    feld.setToolTip("Tempo in BPM")
    _fenster(feld)
    p = _lang_halten(feld)
    assert "Tempo" in _schild_text()
    assert not zs.einrichten(_app)._menue_schlucken, "Eingabefeld: Druck wird nicht geloest"
    _los(feld, p)
    assert feld.hasFocus()


def test_maus_unveraendert():
    b = QPushButton("Maus")
    b.setToolTip("Erklaerung")
    klick = _Zaehler()
    b.clicked.connect(klick)
    _fenster(b)
    p = b.rect().center()
    QTest.mousePress(b, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    _warte(zs.LANG_MENUE_S + 0.2)
    QTest.mouseRelease(b, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    assert klick.n == 1 and not _schild_text()


# ── A-09: Doppelklick-only-Aktionen sichtbar ─────────────────────────────────

def _geraete(n=6):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.app_state import get_state
    from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
    from src.core.database.models import FixtureProfile, PatchedFixture
    from src.core.show.show_file import reset_show

    ensure_builtins()
    reset_show()
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == "MH16")).scalars().first())
    state = get_state()
    for fid in range(1, n + 1):
        state.add_fixture(PatchedFixture(
            fid=fid, label=f"MH{fid}", fixture_profile_id=pid, mode_name="16-Kanal",
            universe=1, address=1 + 16 * (fid - 1), channel_count=16,
            fixture_type="moving_head"), undoable=False)
    return state


def test_patch_bearbeiten_knopf_und_menue(touch, monkeypatch):
    import src.ui.views.patch_view as PV
    from src.core.show.show_file import reset_show
    _geraete(3)
    geoeffnet = []

    class _Dialog:
        def __init__(self, _state, fixture, _parent):
            geoeffnet.append(fixture.fid)
            self.result_updates = {}

        def exec(self):
            return 0
    monkeypatch.setattr(PV, "PatchFixtureEditDialog", _Dialog)
    hinweis = []
    monkeypatch.setattr(PV.QMessageBox, "information", lambda *a, **k: hinweis.append(a))
    try:
        pv = PV.PatchView()
        pv.resize(1100, 600)
        pv.show()
        QApplication.processEvents()
        knopf = pv._btn_bearbeiten
        assert knopf.isVisible() and knopf.text() == "Bearbeiten…"
        # ohne Auswahl: Hinweis statt nichts
        pv._table.clearSelection()
        pv._table.setCurrentCell(-1, -1)
        _tipp(knopf)
        assert geoeffnet == [] and len(hinweis) == 1
        zeile = {pv._fid_at_row(r): r for r in range(pv._table.rowCount())}
        pv._table.selectRow(zeile[2])
        _tipp(knopf)
        assert geoeffnet == [2], "Knopf oeffnet den Bearbeiten-Dialog des markierten Geraets"
        # lang druecken -> Kontextmenue mit „Gerät bearbeiten…“ an erster Stelle
        eintraege = pv._kontextmenue_eintraege(zeile[3])
        assert eintraege[0][0] == "Gerät bearbeiten…"
        eintraege[0][1]()
        assert geoeffnet == [2, 3]
        assert zs.lang_druck_menue_moeglich(pv._table.viewport())
    finally:
        reset_show()


def test_programmer_gruppe_addieren_am_finger(touch):
    from src.core.show.show_file import reset_show
    from src.ui.views.programmer_view import ProgrammerView
    state = _geraete(6)
    try:
        v = ProgrammerView()
        v.resize(780, 760)
        v.show()
        QApplication.processEvents()
        knopf = v._btn_gruppe_addieren
        assert knopf.isVisible() and knopf.isCheckable()
        assert knopf.height() >= TOUCH_HOEHE, knopf.height()
        lst = v._group_list
        lst.clear()
        for name, fids in (("G1", [1, 2]), ("G2", [4])):
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, fids)
            it.setData(Qt.ItemDataRole.UserRole + 1, None)
            lst.addItem(it)
        QApplication.processEvents()
        styles = QApplication.styleHints()
        alt = styles.mouseDoubleClickInterval()
        styles.setMouseDoubleClickInterval(1)
        try:
            vp = lst.viewport()

            def tipp_zeile(n):
                _warte(0.01)
                _tipp(vp, lst.visualItemRect(lst.item(n)).center())

            tipp_zeile(0)
            assert sorted(v._editor_fids) == [1, 2]
            tipp_zeile(1)
            assert sorted(v._editor_fids) == [4], "ohne Addieren ersetzt ein Tipp"
            tipp_zeile(0)
            _warte(0.01)
            _tipp(knopf)
            assert knopf.isChecked()
            tipp_zeile(1)
            assert sorted(v._editor_fids) == [1, 2, 4], v._editor_fids
            _warte(0.01)
            _tipp(knopf)
            assert not knopf.isChecked()
            tipp_zeile(1)
            assert sorted(v._editor_fids) == [4]
        finally:
            styles.setMouseDoubleClickInterval(alt)
        texte = [t for t, _ in v._gruppen_menue_eintraege(lst.item(0))]
        assert "＋ Zur Auswahl addieren" in texte
        dict(v._gruppen_menue_eintraege(lst.item(0)))["＋ Zur Auswahl addieren"]()
        assert sorted(v._editor_fids) == [1, 2, 4]
        assert zs.lang_druck_menue_moeglich(lst.viewport())
    finally:
        state.set_selected_cells([])
        reset_show()


def test_snap_anwenden_startet_effekt_stoppt_nie(touch, monkeypatch):
    from PySide6.QtWidgets import QTreeWidgetItem
    from src.ui.views import snap_file_panel as SP

    class _FM:
        def __init__(self):
            self.laeuft = set()

        def is_running(self, fid):
            return fid in self.laeuft

        def start(self, fid):
            self.laeuft.add(fid)

        def stop(self, fid):
            self.laeuft.discard(fid)

        def all(self):
            return []

        def get(self, _fid):
            return None

    fm = _FM()
    panel = SP.SnapFilePanel()
    monkeypatch.setattr(panel, "_fm", lambda: fm)
    panel.resize(500, 600)
    panel.show()
    QApplication.processEvents()
    it = QTreeWidgetItem(panel._tree, ["Effekt"])
    it.setData(0, SP._ROLE_REF, 77)
    it.setData(0, SP._ROLE_KIND, "function")
    panel._tree.clearSelection()
    it.setSelected(True)
    knopf = panel._btn_anwenden
    _tipp(knopf)
    assert fm.laeuft == {77}, "„Anwenden“ startet den markierten Effekt"
    _tipp(knopf)
    assert fm.laeuft == {77}, "noch einmal: bleibt an (Anwenden stoppt live nie)"
    # Stoppen geht ausdruecklich ueber den Doppelklick (wie bisher)
    panel._tree.itemDoubleClicked.emit(it, 0)
    assert fm.laeuft == set()


# ── C-08: Farbfilter-Namen sichtbar ─────────────────────────────────────────

def test_farbfilter_namen_im_feld_und_hoehe(touch):
    from src.ui.widgets.color_picker import COLOR_FILTERS, ColorPicker
    cp = ColorPicker()
    cp.resize(460, 700)
    cp.show()
    idx = next(i for i in range(cp._tabs.count()) if cp._tabs.tabText(i) == "Filter")
    cp._tabs.setCurrentIndex(idx)
    QApplication.processEvents()
    felder = cp._filter_felder
    assert [f.name() for f in felder] == [n for n, *_ in COLOR_FILTERS]
    for f in felder:
        assert f.height() >= 40 and f.width() >= 80, (f.name(), f.size())
    # Name passt ins Feld (Umbruch auf hoechstens zwei Zeilen)
    from PySide6.QtGui import QFont, QFontMetrics
    schrift = QFont(felder[0].font())
    schrift.setPixelSize(11)
    fm = QFontMetrics(schrift)
    for f in felder:
        r = fm.boundingRect(f.rect().adjusted(3, 2, -3, -2),
                            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                            f.name())
        assert r.height() <= f.height() - 4 and r.width() <= f.width() - 6, f.name()
    # Lesbarkeit: dunkle Schrift auf hellem, helle auf dunklem Feld
    weiss = next(f for f in felder if f.name() == "Open White")
    schwarz = next(f for f in felder if f.name() == "Black")
    assert weiss.schriftfarbe().lightness() < 60 and schwarz.schriftfarbe().lightness() > 200
    # kein Feld ragt aus dem sichtbaren Bereich nach rechts (umbrechend)
    seite = felder[0].parentWidget()
    for f in felder:
        assert f.geometry().right() <= seite.width(), f.name()
    # Fingertipp uebernimmt die Farbe
    lemon = next(f for f in felder if f.name() == "Lemon Yellow")
    _tipp(lemon)
    assert cp._color == QColor(255, 255, 0)


def test_farbfilter_wisch_setzt_keine_farbe(touch):
    from src.ui.widgets.color_picker import ColorPicker
    cp = ColorPicker()
    cp.resize(420, 260)          # klein: die Filterseite scrollt
    cp.show()
    idx = next(i for i in range(cp._tabs.count()) if cp._tabs.tabText(i) == "Filter")
    cp._tabs.setCurrentIndex(idx)
    QApplication.processEvents()
    cp.set_color(QColor(1, 2, 3))
    feld = cp._filter_felder[8]
    _sichtbar_machen(feld)
    bereich = cp._tabs.currentWidget()
    vorher = bereich.verticalScrollBar().value()
    assert bereich.verticalScrollBar().maximum() > 0
    p = feld.rect().center()
    _druck(feld, p)
    for i in range(1, 7):
        _zug(feld, p + QPoint(0, -12 * i))
    _los(feld, p + QPoint(0, -72))
    assert cp._color == QColor(1, 2, 3), "ein Wisch ueber die Felder setzt keine Farbe"
    assert bereich.verticalScrollBar().value() != vorher, "der Wisch scrollt"


def test_farbfilter_maus_klick():
    from src.ui.widgets.color_picker import ColorSwatch
    sw = ColorSwatch(QColor(10, 20, 30), "Test")
    farben = []
    sw.clicked.connect(farben.append)
    _fenster(sw)
    p = sw.rect().center()
    QTest.mouseClick(sw, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    assert farben == [QColor(10, 20, 30)]
    # Druck im Feld, Loslassen ausserhalb: kein Klick (wie ein Knopf)
    QTest.mousePress(sw, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(-50, -50).toPointF(),
                     sw.mapToGlobal(QPoint(-50, -50)).toPointF(),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(sw, ev)
    assert len(farben) == 1


# ── A-15: anklickbare Etiketten in der Kopfleiste ────────────────────────────

def _hauptfenster(touch_an: bool):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=touch_an)
    w._hw_timer.stop()
    w.resize(1440, 900)
    w.show()
    for _ in range(5):
        QApplication.processEvents()
    return w


@pytest.mark.parametrize("touch_an", [False, True])
def test_kopfleiste_etiketten_sehen_antippbar_aus(touch_an):
    w = _hauptfenster(touch_an)
    try:
        for lbl in (w._lbl_page, w._lbl_bpm, w._lbl_bpm_mode):
            assert "border:1px solid" in lbl.styleSheet().replace(": ", ":"), lbl.text()
            assert lbl.cursor().shape() == Qt.CursorShape.PointingHandCursor
        if touch_an:
            for lbl in (w._lbl_page, w._lbl_bpm, w._lbl_bpm_mode):
                assert lbl.height() >= TOUCH_HOEHE - 2, (lbl.text(), lbl.height())
                unten = lbl.mapTo(w._section_bar, QPoint(0, lbl.height())).y()
                assert unten <= w._section_bar.height(), lbl.text()
        # nach einem BPM-Wechsel bleibt der Rahmen
        w._update_bpm_label(128.0) if hasattr(w, "_update_bpm_label") else None
        assert "border:1px solid" in w._lbl_bpm.styleSheet()
    finally:
        w.hide()
        w.deleteLater()
        QApplication.processEvents()


def test_kopfleiste_tap_lang_druecken_loest_aus():
    w = _hauptfenster(True)
    try:
        tap = w._btn_tap
        aufrufe = []
        tap.clicked.disconnect()
        tap.clicked.connect(lambda: aufrufe.append(1))
        p = _lang_halten(tap)
        assert not _schild_text(), "Knopf: keine Erklaerung statt Aktion"
        _los(tap, p)
        assert aufrufe == [1], "langes Druecken auf TAP setzt den Beat"
    finally:
        w.hide()
        w.deleteLater()
        QApplication.processEvents()


# ── D-13: 3D — Geraetename nach einem Tipp (reine Regeln ueber node) ─────────

_REGELN = Path(__file__).resolve().parent.parent / "src" / "ui" / "visualizer" / \
    "scene_src" / "interaction" / "touch_regeln.js"


def _node(ausdruck: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node fehlt")
    with tempfile.TemporaryDirectory() as tmp:
        mjs = Path(tmp) / "touch_regeln.mjs"
        shutil.copy(_REGELN, mjs)
        code = (f"import * as R from {json.dumps(mjs.as_uri())};"
                f"console.log(JSON.stringify({ausdruck}));")
        r = subprocess.run([node, "--input-type=module", "-e", code],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


def test_3d_tipp_zeigt_name_regeln():
    erg = _node("[R.tippZeigtName(0, false, false), R.tippZeigtName(R.TIPP_WEG_PX, false, false),"
                " R.tippZeigtName(R.TIPP_WEG_PX + 1, false, false),"
                " R.tippZeigtName(0, true, false), R.tippZeigtName(0, false, true),"
                " R.TIPP_NAME_MS]")
    assert erg[:5] == [True, True, False, False, False]
    assert 2000 <= erg[5] <= 3000, "2-3 s sichtbar"


def test_3d_text_wie_maus_tooltip():
    assert _node("R.geraeteText(7, 'Spot L', 'moving_head', 1, 6.5, -2)") == \
        "[7] Spot L - moving_head  (X:1.0 Y:6.5 Z:-2.0)"
    assert _node("R.geraeteText(3, '', 'par', 0, 0, 0)").startswith("[3] ? - par")


def test_3d_schild_ueber_dem_finger_im_fenster():
    lage = _node("[R.tippLage(500, 400, 200, 30, 1000, 800), R.tippLage(5, 10, 200, 30, 1000, 800),"
                 " R.tippLage(990, 790, 200, 30, 1000, 800)]")
    mitte, oben_links, unten_rechts = lage
    assert mitte["y"] + 30 < 400 and mitte["x"] == 400, "mittig ueber dem Finger"
    assert oben_links["x"] >= 4 and oben_links["y"] > 10, "oben kein Platz: unter den Finger"
    assert unten_rechts["x"] + 200 <= 996 and unten_rechts["y"] + 30 <= 796


def test_3d_touch_js_nutzt_die_regeln():
    quelle = (_REGELN.parent / "touch.js").read_text(encoding="utf-8")
    assert "tippZeigtName(" in quelle and "fingerSchildZeigen(" in quelle
    zeiger = (_REGELN.parent / "pointer.js").read_text(encoding="utf-8")
    assert "geraeteText(" in zeiger, "Maus und Finger zeigen denselben Text"

"""LAS-44 — offene QA-96-Punkte im Laser-Reiter (nach LAS-34).

* QA96-22: Das gelbe Sperrzonen-Abzeichen sah aus wie ein Knopf und reagierte
  nicht. Jetzt oeffnet ein Klick den Planer (LAS-35); fehlt der Planer, klappt
  es die Meldung je Laser auf. Es bleibt NUR ANZEIGE.
* QA96-23: Die Sicherheitsleiste sagte „Laser AN“, obwohl BLACKOUT oder Grand
  Master 0 den Laser dunkel hielten. Jetzt: „Laser AN · durch BLACKOUT dunkel
  gehalten“ bzw. „· durch Grand Master 0 % dunkel gehalten“ — aber nur, wenn
  die gerechnete Ausgabe es belegt; sonst eine Warnung bzw. nur der Grund.
* QA96-46: Bedienelemente mindestens 36 px hoch, im Touch-Modus 46 px.

Dazu die Sicherheits-Zusagen des Reiters im ECHTEN AppState mit echter
Ausgabe-Rechnung (OutputManager ohne Geraet — kein DMX-Interface, kein Laser):
nichts im Reiter loest den NOT-AUS, und Vorschau/Muster/Farbe/Lage schalten
keinen Laser ein, solange BLACKOUT oder NOT-AUS wirken.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox,  # noqa: E402
                               QComboBox, QScrollBar, QSlider)

import test_las34_laser_tab as T  # noqa: E402
from test_las34_laser_tab import echt, _programmer  # noqa: E402,F401

_app = T._app


def _bedienelemente(wurzel):
    out = []
    from PySide6.QtWidgets import QWidget
    for w in wurzel.findChildren(QWidget):
        if not isinstance(w, (QAbstractButton, QSlider, QComboBox,
                              QAbstractSpinBox)):
            continue
        if isinstance(w, QScrollBar):
            continue
        if isinstance(w, QSlider) and w.orientation() != Qt.Orientation.Horizontal:
            continue
        out.append(w)
    return out


def _abzeichen_an(monkeypatch):
    import src.ui.views.laser_view as lv
    monkeypatch.setattr(
        lv, "sperrzonen_hinweis",
        lambda state, fids: ("⚠ Sperrzonen: 1 Hinweis",
                             "Laser 1: kann Zone „Publikum“ erreichen"))


# ── QA96-22: Abzeichen klickbar ─────────────────────────────────────────────

def test_abzeichen_klick_oeffnet_den_planer(monkeypatch):
    import src.ui.visualizer.sperrzonen_planer as planer
    rufe = []
    monkeypatch.setattr(planer, "planer_oeffnen",
                        lambda state, elter=None: rufe.append(state))
    _abzeichen_an(monkeypatch)
    v, st = T._view(monkeypatch, [T._FX(1, T._el400())])
    abz = v._sperrzonen_abzeichen
    assert not abz.isHidden()
    assert abz.cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.mouseClick(abz, Qt.MouseButton.LeftButton)
    assert rufe == [st]
    QTest.keyClick(abz, Qt.Key.Key_Space)             # auch per Tastatur
    assert len(rufe) == 2
    # Nur Anzeige: der Klick schreibt nichts und schaltet nichts.
    assert st.geschrieben == []
    assert st.laser_estop_active is False
    tip = abz.toolTip()
    assert "Klick: Sperrzonen planen…" in tip
    assert "Nur Anzeige" in tip and "Kein Laserschutz" in tip
    assert "Nur Anzeige" in abz.text()


def test_abzeichen_ohne_planer_klappt_die_meldung_auf(monkeypatch):
    import src.ui.views.laser_view as lv
    monkeypatch.setattr(lv, "SPERRZONEN_PLANER_MODUL",
                        "src.ui.visualizer.gibt_es_nicht")
    _abzeichen_an(monkeypatch)
    v, st = T._view(monkeypatch, [T._FX(1, T._el400())])
    assert v._btn_sperrzonen_planen.isHidden()       # kein toter Knopf
    assert not v._btn_sperrzonen_details.isChecked()
    QTest.mouseClick(v._sperrzonen_abzeichen, Qt.MouseButton.LeftButton)
    assert v._btn_sperrzonen_details.isChecked()
    assert "Meldung je Laser" in v._sperrzonen_abzeichen.toolTip()
    assert st.geschrieben == []


# ── QA96-23: Sicherheitsleiste bei BLACKOUT / Grand Master 0 ────────────────

class _Ausgabe:
    """Attrappe der Ausgabe: Blackout, Grand Master, zuletzt gerechneter
    Frame (``None`` = noch keiner)."""
    GM_LASER_AUS_SCHWELLE = 0.01

    def __init__(self):
        self.blackout = False
        self.grand_master = 1.0
        self.frame = bytearray(512)

    def get_display_frame(self, universe):
        return None if self.frame is None else bytes(self.frame)


def _leiste(monkeypatch):
    fx = T._FX(1, T._el400())
    v, st = T._view(monkeypatch, [fx])
    st.output_manager = _Ausgabe()
    T._betriebsart(v, "statisch")
    return v, st, fx


def test_blackout_haelt_dunkel(monkeypatch):
    v, st, fx = _leiste(monkeypatch)
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AN"
    st.output_manager.blackout = True        # Ausgabe: Betriebsart 0 = aus
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AN · durch BLACKOUT dunkel gehalten"
    assert st.geschrieben[-1] == (1, "shutter", 174)  # nur gelesen


def test_grand_master_0_haelt_dunkel(monkeypatch):
    v, st, fx = _leiste(monkeypatch)
    st.output_manager.grand_master = 0.0
    v._update_dmx_estop_label()
    assert (v._lbl_dmx_estop.text()
            == "Laser AN · durch Grand Master 0 % dunkel gehalten")


def test_grand_master_0_ohne_aus_wert_warnt(monkeypatch):
    """Kennt das Profil keinen Aus-Wert, strahlt der Laser bei GM 0 weiter —
    dann darf die Leiste NICHT „dunkel“ sagen."""
    v, st, fx = _leiste(monkeypatch)
    st.output_manager.grand_master = 0.0
    st.output_manager.frame[fx.address - 1] = 174     # Ausgabe weiter „an“
    v._update_dmx_estop_label()
    text = v._lbl_dmx_estop.text()
    assert text == "Laser AN · Grand Master 0 % schaltet ihn nicht ab"
    assert "dunkel" not in text


def test_ohne_gerechnete_ausgabe_nur_der_grund(monkeypatch):
    v, st, fx = _leiste(monkeypatch)
    st.output_manager.frame = None
    st.output_manager.blackout = True
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AN · BLACKOUT"


def test_laser_aus_und_not_aus_ohne_zusatz(monkeypatch):
    v, st, fx = _leiste(monkeypatch)
    st.output_manager.blackout = True
    T._betriebsart(v, "aus")
    assert v._lbl_dmx_estop.text() == "Laser AUS"
    T._betriebsart(v, "statisch")
    v._btn_dmx_estop.click()                 # NOT-AUS geht immer vor
    assert v._lbl_dmx_estop.text().startswith("NOT-AUS aktiv")
    assert "BLACKOUT" not in v._lbl_dmx_estop.text()


# ── QA96-46: Trefferflaechen ────────────────────────────────────────────────

def _alles_aufklappen(v):
    v._btn_muster_alle.setChecked(True)
    v._btn_farbe_alle.setChecked(True)


def test_bedienelemente_mindestens_36_px(monkeypatch):
    v, _st = T._view(monkeypatch, [T._FX(1, T._el400())])
    _alles_aufklappen(v)
    zu_klein = [(type(w).__name__, w.objectName() or w.text()
                 if hasattr(w, "text") else "", w.minimumHeight())
                for w in _bedienelemente(v) if w.minimumHeight() < 36]
    assert zu_klein == []
    # die vier Funde aus QA96-46 einzeln
    assert v._btn_dmx_estop.minimumHeight() >= 36
    assert all(r.schieber.minimumHeight() >= 36 for r in v._sprech.values())
    assert v._btn_muster_alle.minimumHeight() >= 36
    assert v._btn_farbe_alle.minimumHeight() >= 36
    assert all(k.height() >= 36 for k in v._galerie.kacheln)
    assert v._sperrzonen_abzeichen.minimumHeight() >= 36


def test_touch_modus_46_px(monkeypatch):
    import src.ui.touch_keyboard as tk
    monkeypatch.setattr(tk, "_touch_mode", True)
    v, _st = T._view(monkeypatch, [T._FX(1, T._el400())])
    _alles_aufklappen(v)
    zu_klein = [(type(w).__name__, w.minimumHeight())
                for w in _bedienelemente(v) if w.minimumHeight() < 46]
    assert zu_klein == []
    assert v._btn_dmx_estop.minimumHeight() >= 46
    assert v._dmx_safety_box.maximumHeight() >= 46
    assert v._sperrzonen_abzeichen.minimumHeight() >= 46   # klickbar (QA96-22)
    # Farbfelder bleiben quadratisch
    feld = v._farbfelder.felder[0]
    assert feld.minimumWidth() == feld.minimumHeight() == 46
    # … und passen in ihre Spalte (sechs je Zeile statt acht)
    gitter = v._farbfelder._gitter
    spalten = {gitter.getItemPosition(gitter.indexOf(f))[1]
               for f in v._farbfelder.felder}
    assert len(spalten) <= 6
    assert 6 * 46 + 5 * gitter.spacing() <= v._spalte_farbe.maximumWidth()


def test_not_aus_bleibt_im_touch_modus_ganz_sichtbar(monkeypatch):
    """Langer Zustand + Abzeichen + Touch-Schrift: es gibt zuerst Modell/
    Anzahl nach — LASER NOT-AUS und der Zustand werden nie abgeschnitten."""
    import src.ui.touch_keyboard as tk
    monkeypatch.setattr(tk, "_touch_mode", True)
    _abzeichen_an(monkeypatch)
    v, st, fx = _leiste(monkeypatch)
    v.setStyleSheet("QPushButton { min-height: 38px; padding: 6px 14px; "
                    "font-size: 14px; }")
    st.output_manager.blackout = True
    v.resize(1180, 760)
    v.show()
    v._trefferflaechen()
    v._update_dmx_estop_label()
    for _ in range(3):
        _app().processEvents()
    try:
        assert v._lbl_dmx_estop.text().endswith("durch BLACKOUT dunkel gehalten")
        leiste = v._dmx_safety_box
        for w in (v._btn_dmx_estop, v._lbl_dmx_estop, v._sperrzonen_abzeichen):
            assert w.width() >= w.sizeHint().width(), w.objectName()
            assert leiste.rect().contains(w.geometry()), w.objectName()
    finally:
        v.hide()


def test_assistent_knoepfe_im_programmer(echt):
    app, st, pvm, pv, waehle = _programmer(echt)
    try:
        knoepfe = pv._assistent_knoepfe
        assert len(knoepfe) == 7
        assert all(b.minimumHeight() >= 36 for b in knoepfe), [
            (b.text(), b.minimumHeight()) for b in knoepfe]
    finally:
        pv.close()
        pv.deleteLater()
        app.processEvents()


# ── Sicherheit im echten AppState (ohne Geraet, ohne Laser) ─────────────────

@pytest.fixture
def echter_reiter(monkeypatch):
    """Echter AppState (nur die Teile, die Programmer, Render und NOT-AUS
    brauchen) + echter OutputManager OHNE Adapter: es wird nur gerechnet."""
    _app()
    import src.core.app_state as A
    import src.ui.views.laser_view as lv
    import test_las31_notaus_kopfleiste as l31
    from src.core.app_state import AppState
    from src.core.dmx.output_manager import OutputManager

    fx = T._FX(1, T._el400())
    monkeypatch.setattr(A, "get_channels_for_patched", lambda f: f._chans)
    monkeypatch.setattr(lv, "get_channels_for_patched", lambda f: f._chans)
    om = OutputManager()
    om.add_universe(1)
    st = AppState.__new__(AppState)
    st.universes = om.universes
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = l31._FM()
    st._patch_cache = [fx]
    st._prog_lock = threading.RLock()
    st.output_manager = om
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st.base_levels = {}
    st._engine_extra_prev = {}
    st._suppress_emits = True
    st._emit = lambda *a, **k: None
    st._rebuild_render_plan()
    st.get_selected_fids = lambda: [1]
    st.get_patched_fixtures = lambda: [fx]
    monkeypatch.setattr(lv, "get_state", lambda: st)
    # Kein Dialog, kein Planer-Fenster waehrend „alles klicken“.
    monkeypatch.setattr(lv.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    monkeypatch.setattr(lv.LaserView, "_sperrzonen_planer_oeffnen",
                        lambda self: None)
    v = lv.LaserView(follow_selection=False)
    v.refresh_from_selection()

    def betriebsart_ausgabe() -> int:
        st._render_frame(0.025)
        om._send_all()
        return om._display_frame[1][fx.address - 1]

    yield v, st, om, betriebsart_ausgabe
    v.deleteLater()
    _app().processEvents()


def _alles_bedienen(v, ohne_betriebsart: bool):
    """Jede Bedienflaeche des Reiters einmal betaetigen (ausser LASER NOT-AUS
    und, wenn verlangt, der Betriebsart)."""
    for k in list(v._galerie.kacheln):
        QTest.mouseClick(k, Qt.MouseButton.LeftButton)
    for f in list(v._farbfelder.felder):
        f.click()
    v._lage_gezogen(0.9, 0.1)
    v._btn_mitte.click()
    for r in v._sprech.values():
        r.schieber.setValue(r.schieber.maximum())
    seg = set(v._umschalter.segmente) if ohne_betriebsart else set()
    for b in _bedienelemente(v):
        if (b is v._btn_dmx_estop or b in seg
                or not isinstance(b, QAbstractButton)
                or not b.isVisibleTo(v) or not b.isEnabled()):
            continue
        b.click()


def test_nichts_im_reiter_loest_den_not_aus(echter_reiter):
    v, st, om, ausgabe = echter_reiter
    T._betriebsart(v, "statisch")
    assert v._an_bei(ausgabe()) is True
    v._btn_dmx_estop.click()
    assert st.laser_estop_active is True
    _alles_bedienen(v, ohne_betriebsart=False)        # auch die Betriebsart
    for art in ("statisch", "dynamisch", "auto", "musik"):
        T._betriebsart(v, art)
    QTest.mouseClick(v._sperrzonen_abzeichen, Qt.MouseButton.LeftButton)
    assert st.laser_estop_active is True
    assert v._an_bei(ausgabe()) is False
    assert v._lbl_dmx_estop.text().startswith("NOT-AUS aktiv")


def test_muster_und_vorschau_schalten_bei_blackout_nicht_ein(echter_reiter):
    v, st, om, ausgabe = echter_reiter
    T._betriebsart(v, "aus")
    vorher = st.programmer[1]["shutter"]
    om.set_blackout(True)
    _alles_bedienen(v, ohne_betriebsart=True)
    assert st.programmer[1]["shutter"] == vorher      # Betriebsart unberuehrt
    assert v._an_bei(ausgabe()) is False
    # Laser AN gewaehlt, Blackout haelt ihn dunkel — und die Leiste sagt es.
    T._betriebsart(v, "statisch")
    _alles_bedienen(v, ohne_betriebsart=True)
    assert v._an_bei(ausgabe()) is False
    v._update_dmx_estop_label()
    assert (v._lbl_dmx_estop.text()
            == "Laser AN · durch BLACKOUT dunkel gehalten")
    om.set_blackout(False)
    om.set_grand_master(0.0)
    assert v._an_bei(ausgabe()) is False
    v._update_dmx_estop_label()
    assert (v._lbl_dmx_estop.text()
            == "Laser AN · durch Grand Master 0 % dunkel gehalten")


def test_muster_und_vorschau_schalten_bei_not_aus_nicht_ein(echter_reiter):
    v, st, om, ausgabe = echter_reiter
    T._betriebsart(v, "aus")
    v._btn_dmx_estop.click()
    _alles_bedienen(v, ohne_betriebsart=True)
    assert st.laser_estop_active is True
    assert v._an_bei(ausgabe()) is False


def test_scharf_schalten_umgeht_den_not_aus_nicht(monkeypatch):
    """Netzwerk-Laser: „Scharf“ im Reiter wirkt nicht, solange der NOT-AUS
    aktiv ist — er wird nur oben rechts geloest (LAS-36)."""
    v, st = T._view(monkeypatch, [T._FX(1, T._el400(), protocol="etherdream")])
    v._on_estop()
    assert st.laser_estop_active is True and st.lo.armed is False
    v._btn_arm.setChecked(True)
    assert st.lo.armed is False
    assert not v._btn_arm.isChecked()
    st.laser_estop_active = False                     # oben rechts geloest
    v._btn_arm.setChecked(True)
    assert st.lo.armed is True


def test_sperrzonen_bleiben_nur_anzeige_beschriftet(monkeypatch):
    _abzeichen_an(monkeypatch)
    v, _st = T._view(monkeypatch, [T._FX(1, T._el400())])
    for w in (v._sperrzonen_abzeichen, v._btn_sperrzonen_planen,
              v._btn_sperrzonen_details):
        assert "Kein Laserschutz" in w.toolTip(), w.objectName()
    assert "schaltet nicht ab" in v._sperrzonen_abzeichen.text()


# ── Nachtrag Sicherheits-Gegenpruefung (LAS-44) ─────────────────────────────

def test_grand_master_0_haelt_netzwerk_laser_nicht_dunkel(monkeypatch):
    """Gemischte Auswahl DMX + scharfer Ether-Dream-Laser: GM 0 dunkelt den
    Streamer NICHT (nur BLACKOUT/NOT-AUS/unscharf) — die Leiste darf also
    nicht „dunkel gehalten“ melden. Der Platzhalter-Kanal des Netzwerk-
    Lasers (LAS-04) im DMX-Frame zaehlt nicht."""
    el = T._el400()
    v, st = T._view(monkeypatch, [T._FX(1, el),
                                  T._FX(2, el, protocol="etherdream")])
    st.output_manager = _Ausgabe()
    st._laser_output = st.lo
    T._betriebsart(v, "statisch")
    st.lo.armed = True
    st.output_manager.grand_master = 0.0
    v._update_dmx_estop_label()
    text = v._lbl_dmx_estop.text()
    assert "dunkel gehalten" not in text
    assert text == "Laser AN · Grand Master 0 % schaltet ihn nicht ab"
    # BLACKOUT dunkelt auch den Streamer -> hier stimmt „dunkel gehalten“.
    st.output_manager.grand_master = 1.0
    st.output_manager.blackout = True
    v._update_dmx_estop_label()
    assert v._lbl_dmx_estop.text() == "Laser AN · durch BLACKOUT dunkel gehalten"


def test_zwei_dmx_laser_einer_strahlt_weiter(monkeypatch):
    """Ein Laser laut Ausgabe aus, der andere weiter an: nie „dunkel
    gehalten“ — weder bei GM 0 noch bei BLACKOUT."""
    el = T._el400()
    f1, f2 = T._FX(1, el), T._FX(2, el)
    v, st = T._view(monkeypatch, [f1, f2])
    st.output_manager = _Ausgabe()
    T._betriebsart(v, "statisch")
    st.output_manager.frame[f2.address - 1] = 174       # f2 strahlt weiter
    for grund, setzen in (("Grand Master 0 %", ("grand_master", 0.0)),
                          ("BLACKOUT", ("blackout", True))):
        st.output_manager.grand_master = 1.0
        st.output_manager.blackout = False
        setattr(st.output_manager, *setzen)
        v._update_dmx_estop_label()
        text = v._lbl_dmx_estop.text()
        assert "dunkel gehalten" not in text, text
        assert text == f"Laser AN · {grund} schaltet ihn nicht ab"


def test_scharf_tooltip_verschwindet_nach_dem_loesen(monkeypatch):
    v, st = T._view(monkeypatch, [T._FX(1, T._el400(), protocol="etherdream")])
    vorher = v._btn_arm.toolTip()
    v._on_estop()
    v._btn_arm.setChecked(True)                       # verweigert
    assert v._btn_arm.toolTip().startswith("NOT-AUS aktiv")
    st.laser_estop_active = False                     # oben rechts geloest
    v._btn_arm.setChecked(True)
    assert st.lo.armed is True
    assert v._btn_arm.toolTip() == vorher
    assert "NOT-AUS" not in v._btn_arm.toolTip()


def test_kern_verweigert_scharf_bei_not_aus():
    """Der Riegel sitzt im LaserOutputManager — gilt fuer Reiter, VC-/MIDI-
    Taste LASER_ARM und Fernbedienung gleich; der Tick dunkelt zusaetzlich,
    solange der NOT-AUS-Latch steht."""
    import test_laser_etherdream as E
    m, state = E._manager([E._Fx(1)])
    state.programmer[1] = {"shutter": 255}
    state.laser_estop_active = True
    m.set_armed(not m.armed)                          # wie die VC-Taste LASER_ARM
    assert m.armed is False
    m._armed = True                                   # am Riegel vorbei
    m._tick()
    frame = list(m._connections.values())[0].frames[0]
    assert all(p.blanked for p in frame.points)
    state.laser_estop_active = False                  # oben rechts geloest
    assert m.set_armed(True) is True
    m._tick()
    frame = list(m._connections.values())[0].frames[-1]
    assert any(not p.blanked for p in frame.points)

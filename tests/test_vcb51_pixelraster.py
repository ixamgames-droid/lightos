"""VCB-51: VC-Pixelraster — auf eine Kopf-Gruppe live malen.

Abnahme:

* Pinsel malt -> genau die Farbkanaele der getroffenen Zelle (Kopf bzw.
  ganzes Geraet) tragen die Farbe; alle anderen Kanaele bleiben.
* Der Dimmer wird NIE mitgezogen (Farbe und Dimmer getrennt).
* Die Zeichnung liegt mit eigenem Pegel UEBER dem, was darunter laeuft
  (hier: Programmer-Farbe), Pegel 0 / Radierer / Loeschen = wie vorher.
* Aufloesung 2x2 fasst Zellen zusammen, Fuellen faerbt eine Flaeche.
* Merken/Abruf, Speichern/Laden beim Element; eine alte Show ohne das
  Element laedt unveraendert.
* FM-20: eine Gruppe mit Untergruppen-Block wird aufgeloest.
* Touch-Sperre und Bearbeiten-Modus malen nicht; Finger malt; im
  Touch-Modus sind alle Knoepfe >= 44 px.

Echter ``AppState`` mit Wegwerf-Show-DB; die Kanaele kommen aus einer
Test-Kanalliste (``get_channels_for_patched`` umgelenkt) — die
Geraete-Bibliothek wird gar nicht angefasst.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.database.models import FixtureGroup, PatchedFixture    # noqa: E402
from src.core.engine.zeichen_ebene import EBENEN                     # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole.vc_pixelraster import (FUELLEN, RADIERER,  # noqa: E402
                                                  VCPixelraster)
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


def _ch(attr, num, default=0):
    return NS(attribute=attr, channel_number=num, default_value=default,
              highlight_value=255, ranges=[])


#: fid 1: Leiste mit 4 RGB-Koepfen + gemeinsamem Dimmer (Kanal 13)
#: fid 2: RGB-PAR mit eigenem Dimmer (Kanal 4)
KANAELE = {
    1: [c for k in range(4) for c in (_ch("color_r", 3 * k + 1),
                                      _ch("color_g", 3 * k + 2),
                                      _ch("color_b", 3 * k + 3))] + [_ch("dimmer", 13)],
    2: [_ch("color_r", 1), _ch("color_g", 2), _ch("color_b", 3), _ch("dimmer", 4)],
}
ADRESSEN = {1: 1, 2: 20}
DIMMER = {1: 13, 2: 23}


def _kopf_adr(kopf):
    """(r, g, b)-Adressen von Kopf ``kopf`` der Leiste (fid 1)."""
    return (3 * kopf + 1, 3 * kopf + 2, 3 * kopf + 3)


PAR_ADR = (20, 21, 22)


@pytest.fixture
def st(monkeypatch):
    zs.einrichten(_app).aktiv = True
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: list(KANAELE.get(getattr(fx, "fid", None), [])))
    state = A.AppState()
    fd, pfad = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    state.open_show(pfad)
    for fid, addr in ADRESSEN.items():
        state.add_fixture(PatchedFixture(
            fid=fid, label=f"Geraet {fid}", fixture_profile_id=1, mode_name="Std",
            universe=1, address=addr, channel_count=len(KANAELE[fid]),
            fixture_type="led_bar" if fid == 1 else "par"), undoable=False)
    with state._session() as s:
        bar = FixtureGroup(name="Leiste", cols=4, rows=2, positions_json=json.dumps(
            {"0,0": "1:0", "1,0": "1:1", "2,0": "1:2", "3,0": "1:3", "0,1": 2}))
        s.add(bar)
        s.commit()
        uid = bar.uid
        from src.core.group_cells import gruppen_verweis
        s.add(FixtureGroup(name="Ober", cols=1, rows=1,
                           positions_json=json.dumps({"0,0": gruppen_verweis(uid)})))
        s.commit()
    monkeypatch.setattr(A, "get_state", lambda: state)
    if 1 not in state.universes:
        state.universes[1] = state.output_manager.add_universe(1)
    alt_lock = VCWidget.input_locked
    alt_touch = touch_keyboard.is_touch_mode()
    EBENEN.leeren()
    yield state
    EBENEN.leeren()
    VCWidget.input_locked = alt_lock
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)
    try:
        os.remove(pfad)
    except OSError:
        pass


def _raster(gruppe="Leiste", w=380, h=300):
    p = VCPixelraster("Malen")
    p.resize(w, h)
    eltern = QWidget()
    eltern.resize(w + 40, h + 40)
    p.setParent(eltern)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    p.binden(gruppe)
    QApplication.processEvents()
    return p


def _dmx(state):
    state._render_frame(0.0)
    return state.universes[1].get_all()


def _werte(dmx, adressen):
    return tuple(dmx[a - 1] for a in adressen)


def _maus(w, typ, pos: QPoint):
    knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), knopf, knoepfe,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _klick(w, pos):
    _maus(w, QEvent.Type.MouseButtonPress, pos)
    _maus(w, QEvent.Type.MouseButtonRelease, pos)


def _knopf(p, k):
    _klick(p, p.knopf_rechtecke()[k].center())


# ── Zeichnen -> DMX ─────────────────────────────────────────────────────────

def test_pinsel_trifft_genau_den_kopf_und_den_dimmer_nie(st):
    vorher = _dmx(st)
    p = _raster()
    p.set_farbe("#ff8000")
    _klick(p, p.zelle_mitte(1, 0))
    dmx = _dmx(st)
    assert _werte(dmx, _kopf_adr(1)) == (255, 128, 0)
    for kopf in (0, 2, 3):
        assert _werte(dmx, _kopf_adr(kopf)) == _werte(vorher, _kopf_adr(kopf))
    assert _werte(dmx, PAR_ADR) == _werte(vorher, PAR_ADR)
    # Farbe zieht den Dimmer nie mit
    assert dmx[DIMMER[1] - 1] == vorher[DIMMER[1] - 1] == 0
    # ganzes Geraet in Zeile 2
    _klick(p, p.zelle_mitte(0, 1))
    dmx = _dmx(st)
    assert _werte(dmx, PAR_ADR) == (255, 128, 0)
    assert dmx[DIMMER[2] - 1] == 0


def test_mit_der_maus_ziehen_malt_eine_spur(st):
    p = _raster()
    p.set_farbe("#00ff00")
    _maus(p, QEvent.Type.MouseButtonPress, p.zelle_mitte(0, 0))
    _maus(p, QEvent.Type.MouseMove, p.zelle_mitte(1, 0))
    _maus(p, QEvent.Type.MouseMove, p.zelle_mitte(2, 0))
    _maus(p, QEvent.Type.MouseButtonRelease, p.zelle_mitte(2, 0))
    assert set(p.pixel) == {"0,0", "1,0", "2,0"}
    dmx = _dmx(st)
    for kopf in (0, 1, 2):
        assert _werte(dmx, _kopf_adr(kopf)) == (0, 255, 0)
    assert _werte(dmx, _kopf_adr(3)) == (0, 0, 0)


def test_ebene_liegt_ueber_dem_darunter_mit_pegel(st):
    st.set_programmer_value(2, "color_r", 200)
    st.set_programmer_value(2, "color_b", 100)
    unten = _werte(_dmx(st), PAR_ADR)
    assert unten == (200, 0, 100)
    p = _raster()
    p.set_farbe("#00ff00")
    p.malen(0, 1)
    assert _werte(_dmx(st), PAR_ADR) == (0, 255, 0)
    p.set_pegel(0.5)
    assert _werte(_dmx(st), PAR_ADR) == (100, 128, 50)
    p.set_pegel(0.0)
    assert _werte(_dmx(st), PAR_ADR) == unten
    p.set_pegel(1.0)
    p.malen(0, 1, werkzeug=RADIERER)
    assert _werte(_dmx(st), PAR_ADR) == unten
    assert st.get_programmer_value(2, "color_r") == 200, "Programmer unberuehrt"


def test_radierer_und_loeschen_geben_frei(st):
    vorher = _dmx(st)
    p = _raster()
    for c in range(4):
        p.malen(c, 0)
    p.set_werkzeug(RADIERER)
    _klick(p, p.zelle_mitte(2, 0))
    assert "2,0" not in p.pixel
    assert _werte(_dmx(st), _kopf_adr(2)) == _werte(vorher, _kopf_adr(2))
    # Loeschen: erster Tipp macht nur scharf, zweiter leert
    _knopf(p, "loeschen")
    assert p.pixel and p.loeschen_scharf()
    _knopf(p, "loeschen")
    assert p.pixel == {}
    assert _dmx(st) == vorher
    assert EBENEN.ebene(p.widget_id) is None


def test_doppeltipp_auf_loeschen_bestaetigt_nicht(st):
    """Pruefung: ein Doppeltipp (prellender Finger) darf die Rueckfrage nicht
    selbst bestaetigen; erst ein eigener zweiter Tipp loescht."""
    p = _raster()
    p.malen(0, 0)
    pos = p.knopf_rechtecke()["loeschen"].center()
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    _maus(p, QEvent.Type.MouseButtonDblClick, pos)
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    assert p.pixel == {"0,0": "#ff0000"} and p.loeschen_scharf()
    _knopf(p, "loeschen")
    assert p.pixel == {}


def test_aufloesung_und_fuellen(st):
    p = _raster()
    p.set_farbe("#0000ff")
    _knopf(p, "aufloesung")
    assert p.aufloesung == 2
    p.malen(1, 1)
    assert set(p.pixel) == {"0,0", "1,0", "0,1", "1,1"}
    _knopf(p, "aufloesung")
    _knopf(p, "aufloesung")
    assert p.aufloesung == 1, "4x4 -> zurueck auf 1x1"
    p.set_farbe("#ffffff")
    p.set_werkzeug(FUELLEN)
    p.malen(3, 1)
    # leere Flaeche (2,0),(3,0),(2,1),(3,1) weiss, blaue Ecke bleibt
    assert {k for k, v in p.pixel.items() if v == "#ffffff"} == {"2,0", "3,0", "2,1", "3,1"}
    assert p.pixel["0,0"] == "#0000ff"
    assert _werte(_dmx(st), _kopf_adr(3)) == (255, 255, 255)


def test_merken_und_abrufen(st):
    p = _raster()
    p.set_farbe("#ff0000")
    p.malen(0, 0)
    _knopf(p, "merken")
    p.malen(0, 0, werkzeug=RADIERER)
    p.set_farbe("#00ff00")
    p.malen(3, 0)
    _knopf(p, "merken")
    assert len(p.bilder) == 2
    _knopf(p, "abruf")
    assert p.pixel == {"0,0": "#ff0000"}
    assert _werte(_dmx(st), _kopf_adr(0)) == (255, 0, 0)
    assert _werte(_dmx(st), _kopf_adr(3)) == (0, 0, 0)
    _knopf(p, "abruf")
    assert p.pixel == {"3,0": "#00ff00"}


def test_untergruppen_block_wird_aufgeloest(st):
    p = _raster("Ober")
    cols, rows, _pos = p.raster()
    assert (cols, rows) == (4, 2)
    assert p.zellen_ziele()["2,0"] == (1, 2)
    p.malen(2, 0)
    assert _werte(_dmx(st), _kopf_adr(2)) == (255, 0, 0)


def test_ohne_gruppe_und_unbekannte_gruppe_geben_nichts_aus(st):
    vorher = _dmx(st)
    p = _raster("")
    assert not p.malen(0, 0)
    p.binden("gibtsnicht")
    assert not p.malen(0, 0)
    assert _dmx(st) == vorher


# ── Bedienung ───────────────────────────────────────────────────────────────

def test_touch_sperre_und_bearbeiten_malen_nicht(st):
    p = _raster()
    VCWidget.input_locked = True
    _klick(p, p.zelle_mitte(0, 0))
    assert p.pixel == {}
    VCWidget.input_locked = False
    p.set_edit_mode(True)
    _klick(p, p.zelle_mitte(0, 0))
    assert p.pixel == {}
    p.set_edit_mode(False)
    _klick(p, p.zelle_mitte(0, 0))
    assert p.pixel == {"0,0": "#ff0000"}


def test_finger_malt(st):
    p = _raster()
    a, b = p.zelle_mitte(0, 0), p.zelle_mitte(3, 0)
    QTest.touchEvent(p, _DEV).press(0, a, p).commit()
    QApplication.processEvents()
    for i in range(1, 7):
        QTest.touchEvent(p, _DEV).move(0, a + (b - a) * (i / 6), p).commit()
        QApplication.processEvents()
    QTest.touchEvent(p, _DEV).release(0, b, p).commit()
    QApplication.processEvents()
    assert {"0,0", "3,0"} <= set(p.pixel)
    assert p.finger_bedienelement()


def test_touch_modus_mindestens_44_px(st):
    touch_keyboard.setze_touch_modus(True)
    p = _raster(w=300, h=320)
    for k, q in p.knopf_rechtecke().items():
        assert q.width() >= 44 and q.height() >= 44, k
    assert p.pegel_rechteck().width() >= 44
    touch_keyboard.setze_touch_modus(False)
    assert p.knopf_rechtecke()["pinsel"].height() < 44, "Maus bleibt kompakt"


# ── Speichern / Laden ───────────────────────────────────────────────────────

def test_roundtrip_und_entfernen(st):
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    p = _raster()
    p.set_farbe("#123456")
    p.malen(1, 0)
    p.merken()
    p.set_pegel(0.25)
    p.set_aufloesung(4)
    d = json.loads(json.dumps(p.to_dict()))
    q = VCPixelraster()
    q.apply_dict(d)
    assert (q.gruppe, q.pixel, q.bilder, q.pegel, q.aufloesung, q.farbe.name()) == \
        ("Leiste", {"1,0": "#123456"}, [{"1,0": "#123456"}], 0.25, 4, "#123456")
    # kaputte Werte fallen auf Vorgaben
    q.apply_dict({"type": "VCPixelraster", "pixel": {"x": "#fff", "1,1": "keinefarbe"},
                  "pegel": "viel", "aufloesung": 3, "werkzeug": "hammer"})
    assert (q.pixel, q.pegel, q.aufloesung, q.werkzeug) == ({}, 1.0, 1, "pinsel")
    # Canvas: Element loeschen nimmt seine Ebene mit
    c = VCCanvas()
    w = c._add_widget("VCPixelraster", QPoint(10, 10))
    w.binden("Leiste")
    w.malen(0, 0)
    assert EBENEN.ebene(w.widget_id) is not None
    c._clear()
    assert EBENEN.ebene(w.widget_id) is None
    c.deleteLater()
    q.deleteLater()


def test_show_datei_speichern_laden_und_alt_show(monkeypatch):
    """Echte .lshow ueber save_show/load_show (Sandkasten-Show-DB aus conftest)."""
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [])
    from src.core.show import show_file as SF
    from src.core.app_state import get_state
    state = get_state()
    SF.reset_show()
    with tempfile.TemporaryDirectory(prefix="lightos_vcb51_") as tmp:
        alt_pfad = os.path.join(tmp, "alt.lshow")
        state._vc_layout = {"widgets": [
            {"type": "VCXYPad", "caption": "MH", "x": 10, "y": 10, "w": 160, "h": 160,
             "pan": 0.25, "tilt": 0.75, "fixture_ids": [], "mode": "position"}]}
        SF.save_show(alt_pfad)
        with zipfile.ZipFile(alt_pfad) as z:
            alt_vc = json.loads(z.read("show.json"))["virtual_console"]
        ok, msg = SF.load_show(alt_pfad)
        assert ok, msg
        assert get_state()._vc_layout == alt_vc
        assert not EBENEN.aktiv()

        p = VCPixelraster("Malen")
        p.gruppe = "Leiste"
        p.pixel = {"0,0": "#ff0000", "3,1": "#00ff00"}
        p.bilder = [{"1,0": "#0000ff"}]
        p.pegel = 0.5
        neu_pfad = os.path.join(tmp, "neu.lshow")
        state = get_state()
        state._vc_layout = {"widgets": alt_vc["widgets"] + [p.to_dict()]}
        SF.save_show(neu_pfad)
        EBENEN.setzen("fremd", 1.0, {(1, None): (1, 2, 3)})
        ok, msg = SF.load_show(neu_pfad)
        assert ok, msg
        assert EBENEN.ebene("fremd") is None, "Show laden raeumt alte Ebenen ab"
        pr = [w for w in get_state()._vc_layout["widgets"] if w["type"] == "VCPixelraster"]
        assert len(pr) == 1
        q = VCPixelraster()
        q.apply_dict(pr[0])
        assert (q.gruppe, q.pixel, q.bilder, q.pegel) == (
            "Leiste", {"0,0": "#ff0000", "3,1": "#00ff00"}, [{"1,0": "#0000ff"}], 0.5)
        q.vor_entfernen()
        q.deleteLater()
        p.deleteLater()
    SF.reset_show()
    EBENEN.leeren()


def test_ebene_ohne_qt_mischt_nur_farbe():
    """Kern ohne Qt: Kopf-genau, nur color_r/g/b, Pegel gekappt."""
    from src.core.engine.zeichen_ebene import ZeichenEbenen

    class U:
        def __init__(self):
            self.d = [10] * 512

        def get_channel(self, a):
            return self.d[a - 1]

        def set_channel(self, a, v):
            self.d[a - 1] = v

    fx = NS(universe=1, address=1)
    u = U()
    e = ZeichenEbenen()
    e.setzen("x", 7.0, {(1, 1): (200, 100, 0)})
    assert e.ebene("x")[0] == 1.0
    e.anwenden({1: u}, {1: (fx, KANAELE[1])})
    assert u.d[0:3] == [10, 10, 10]
    assert u.d[3:6] == [200, 100, 0]
    assert u.d[12] == 10, "Dimmer bleibt"
    e.setzen("x", 0.0, {(1, 1): (1, 1, 1)})
    assert not e.aktiv()

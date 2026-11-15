"""UI-127 (Teil A): VC-Raum-Pad — den Raum antippen statt Pan/Tilt schieben.

Abnahme laut Auftrag:

* Tipp auf Bodenpunkt P -> jeder Kopf hat exakt die Werte aus
  ``aim_pan_tilt(pos, P, rot)`` (mit Feinkanal: ``aim_pan_tilt_16`` auf
  Grob + Fein), wie das Werkzeug „Zielen" im Visualizer.
* AUS -> weder Pan/Tilt noch Fein dieser Koepfe im Programmer, die Ausgabe ist
  byte-gleich wie vorher; fremde Programmer-Werte bleiben stehen.
* Position Lock AUS -> nach dem Loslassen freigegeben.
* Kopf ohne Position: faehrt nicht mit und ist markiert.
* Show speichern/laden; eine alte Show ohne das Widget laedt unveraendert.
* Touch-Sperre sperrt das Pad, Finger bedient es, im Touch-Modus >= 44 px.

Echter ``AppState`` mit Wegwerf-Show-DB; die Kanaele kommen aus einer
Test-Kanalliste (``get_channels_for_patched`` umgelenkt).
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from types import SimpleNamespace as NS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.core.stage.aim import aim_pan_tilt, aim_pan_tilt_16         # noqa: E402
from src.core.stage.einmessen import aim_kw                          # noqa: E402
from src.core.stage import raum_pad as RP                            # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole.vc_raumpad import VCRaumPad               # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


def _ch(attr, num, default=0):
    return NS(attribute=attr, channel_number=num, default_value=default,
              highlight_value=255, ranges=[])


#: fid -> Kanalliste
KANAELE = {
    # Moving Head mit Feinkanaelen
    1: [_ch("pan", 1, 128), _ch("pan_fine", 2), _ch("tilt", 3, 128),
        _ch("tilt_fine", 4), _ch("dimmer", 5)],
    # Moving Head ohne Feinkanal
    2: [_ch("pan", 1, 128), _ch("tilt", 2, 128), _ch("dimmer", 3)],
    # Moving Head, aber nirgends platziert
    3: [_ch("pan", 1, 128), _ch("tilt", 2, 128), _ch("dimmer", 3)],
    # PAR ohne Pan/Tilt
    4: [_ch("color_r", 1), _ch("color_g", 2), _ch("color_b", 3)],
}
ADRESSEN = {1: 1, 2: 20, 3: 40, 4: 60}
POS = {1: (-2.0, 5.0, -1.0), 2: (3.0, 4.5, 0.5)}
ROT = {1: (0.0, 0.0, 0.0), 2: (0.0, 30.0, 0.0)}


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
            fid=fid, label=f"Kopf {fid}", fixture_profile_id=1, mode_name="Std",
            universe=1, address=addr, channel_count=len(KANAELE[fid]),
            fixture_type="moving_head" if fid != 4 else "par"), undoable=False)
    for fid, p in POS.items():
        state.visualizer_positions[fid] = p
        state.visualizer_rotations[fid] = ROT[fid]
    monkeypatch.setattr(A, "get_state", lambda: state)
    if 1 not in state.universes:
        state.universes[1] = state.output_manager.add_universe(1)
    state._flush_all_to_dmx()
    alt_lock = VCWidget.input_locked
    alt_touch = touch_keyboard.is_touch_mode()
    yield state
    VCWidget.input_locked = alt_lock
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)
    try:
        os.remove(pfad)
    except OSError:
        pass


def _pad(fids=(1, 2, 3, 4), w=320, h=300):
    p = VCRaumPad("Raum")
    p._fixture_ids = list(fids)
    p.resize(w, h)
    eltern = QWidget()
    eltern.resize(w + 40, h + 40)
    p.setParent(eltern)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    QApplication.processEvents()
    return p


def _bytes(state):
    return state.universes[1].get_all()


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


def _px(p, x, z):
    raum = p._raum()
    pad, s = p._abbildung(raum)
    q = p._welt_zu_px(x, z, raum, pad, s)
    return QPoint(round(q.x()), round(q.y()))


def _erwartet(state, fid, ziel):
    f = next(f for f in state.get_patched_fixtures() if f.fid == fid)
    return (aim_pan_tilt(POS[fid], ziel, ROT[fid], **aim_kw(f)),
            aim_pan_tilt_16(POS[fid], ziel, ROT[fid], **aim_kw(f)))


# ── Rechenteil ──────────────────────────────────────────────────────────────

def test_raum_masse_wie_raum_huelle():
    leer = RP.raum_masse({})
    assert (leer.breite, leer.tiefe, leer.hoehe) == (12.0, 12.0, 5.0)
    r = RP.raum_masse({1: (-10, 6, -2), 2: (10, 3, 4)})
    assert r.breite == pytest.approx(28.0) and r.x0 == pytest.approx(-14.0)
    assert r.tiefe == pytest.approx(14.0)
    assert r.hoehe == pytest.approx(10.0)
    assert r.klemme(99, -99) == (r.x1, r.z0)


def test_geraete_ohne_pan_tilt_sind_keine_koepfe():
    assert RP.bewegung(NS(fixture_type="par"), KANAELE[4]) == 0
    assert RP.bewegung(NS(fixture_type="moving_head"), KANAELE[2]) == 1
    bar = [_ch("pan", 1), _ch("tilt", 2), _ch("pan", 3), _ch("tilt", 4)]
    assert RP.bewegung(NS(fixture_type="moving_head"), bar) == 2


# ── Abnahme ─────────────────────────────────────────────────────────────────

def test_tipp_auf_bodenpunkt_setzt_aim_werte(st):
    p = _pad()
    _klick(p, _px(p, 1.0, 2.0))
    assert p.aktiv
    x, z = p.ziel
    ziel = (x, 0.0, z)
    a8, a16 = _erwartet(st, 1, ziel)
    assert st.get_programmer_value(1, "pan") == a16[0] >> 8
    assert st.get_programmer_value(1, "pan_fine") == a16[0] & 0xFF
    assert st.get_programmer_value(1, "tilt") == a16[1] >> 8
    assert st.get_programmer_value(1, "tilt_fine") == a16[1] & 0xFF
    a8, _ = _erwartet(st, 2, ziel)
    assert (st.get_programmer_value(2, "pan"), st.get_programmer_value(2, "tilt")) == a8
    assert st.get_programmer_value(2, "pan_fine") is None, "kein Fein ohne Kanal"
    # Kopf ohne Position faehrt NICHT mit, der PAR schon gar nicht
    assert 3 not in st.programmer and 4 not in st.programmer


def test_zielhoehe_geht_in_die_rechnung(st):
    p = _pad()
    p.ziel = (0.5, 1.0)
    p.hoehe_setzen(1.8)
    p.einschalten()
    a8, _ = _erwartet(st, 2, (0.5, 1.8, 1.0))
    assert (st.get_programmer_value(2, "pan"), st.get_programmer_value(2, "tilt")) == a8
    p.hoehe_setzen(999)
    assert p.hoehe == p._raum().hoehe


def test_aus_gibt_frei_und_ausgabe_byte_gleich(st):
    vorher_bytes = _bytes(st)
    vorher_prog = json.loads(json.dumps({str(k): v for k, v in st.programmer.items()}))
    p = _pad()
    _klick(p, _px(p, -1.0, 3.0))
    assert _bytes(st) != vorher_bytes, "Vorbedingung: das Pad hat etwas bewegt"
    _klick(p, p._zonen()["an"].center())          # AUS
    assert not p.aktiv
    for fid in (1, 2):
        for attr in ("pan", "pan_fine", "tilt", "tilt_fine"):
            assert st.get_programmer_value(fid, attr) is None, (fid, attr)
    assert {str(k): v for k, v in st.programmer.items()} == vorher_prog
    assert _bytes(st) == vorher_bytes


def test_fremde_werte_bleiben(st):
    st.set_programmer_value(1, "dimmer", 200)
    st.set_programmer_value(2, "pan", 40)
    vorher = _bytes(st)
    p = _pad()
    p.ziel_setzen(0.0, 0.0)
    assert st.get_programmer_value(2, "pan") != 40
    p.freigeben()
    assert st.get_programmer_value(1, "dimmer") == 200
    assert st.get_programmer_value(2, "pan") == 40, "Vorwert zurueck, nicht geloescht"
    assert _bytes(st) == vorher


def test_inzwischen_fremd_ueberschrieben_bleibt_stehen(st):
    p = _pad()
    p.ziel_setzen(0.0, 0.0)
    st.set_programmer_value(2, "tilt", 7)          # jemand anderes
    p.freigeben()
    assert st.get_programmer_value(2, "tilt") == 7
    assert st.get_programmer_value(2, "pan") is None


def test_position_lock_aus_gibt_beim_loslassen_frei(st):
    vorher = _bytes(st)
    p = _pad()
    _klick(p, p._zonen()["lock"].center())
    assert p.position_lock is False
    ziel = _px(p, 1.0, 1.0)
    _maus(p, QEvent.Type.MouseButtonPress, ziel)
    assert p.aktiv and st.get_programmer_value(2, "pan") is not None, "gilt solange gedrueckt"
    _maus(p, QEvent.Type.MouseMove, ziel + QPoint(10, 5))
    assert st.get_programmer_value(2, "pan") is not None
    _maus(p, QEvent.Type.MouseButtonRelease, ziel + QPoint(10, 5))
    assert not p.aktiv
    assert st.get_programmer_value(2, "pan") is None
    assert _bytes(st) == vorher
    assert p.ziel is not None, "der Punkt bleibt als Anzeige stehen"


def test_position_lock_an_haelt_nach_loslassen(st):
    p = _pad()
    assert p.position_lock is True
    _klick(p, _px(p, 1.0, 1.0))
    assert p.aktiv and st.get_programmer_value(2, "pan") is not None


def test_kopf_ohne_position_markiert(st):
    p = _pad()
    mit, ohne = p.koepfe()
    assert [m[0] for m in mit] == [1, 2]
    assert [o[0] for o in ohne] == [3]
    p.grab()                                        # malt und setzt den Hinweis
    assert "3" in p.toolTip() and "NICHT" in p.toolTip()


def test_touch_sperre_sperrt_das_pad(st):
    p = _pad()
    VCWidget.input_locked = True
    _klick(p, _px(p, 1.0, 1.0))
    _klick(p, p._zonen()["lock"].center())
    assert not p.aktiv and p.ziel is None and p.position_lock
    assert st.get_programmer_value(2, "pan") is None


def test_bearbeiten_modus_steuert_nicht(st):
    p = _pad()
    p.set_edit_mode(True)
    _klick(p, _px(p, 1.0, 1.0))
    assert p.ziel is None and 2 not in st.programmer


def test_finger_tipp_setzt_ziel(st):
    p = _pad()
    pos = _px(p, -1.0, 1.0)
    QTest.touchEvent(p, _DEV).press(0, pos, p).commit()
    QApplication.processEvents()
    QTest.touchEvent(p, _DEV).release(0, pos, p).commit()
    QApplication.processEvents()
    assert p.aktiv and p.ziel is not None
    assert st.get_programmer_value(2, "pan") is not None


def test_finger_zug_folgt_und_scrollt_nicht(st):
    p = _pad()
    start, ende = _px(p, -3.0, -2.0), _px(p, 3.0, 2.0)
    QTest.touchEvent(p, _DEV).press(0, start, p).commit()
    QApplication.processEvents()
    for i in range(1, 7):
        QTest.touchEvent(p, _DEV).move(0, start + (ende - start) * (i / 6), p).commit()
        QApplication.processEvents()
    QTest.touchEvent(p, _DEV).release(0, ende, p).commit()
    QApplication.processEvents()
    assert p.ziel[0] == pytest.approx(3.0, abs=0.2)
    assert p.ziel[1] == pytest.approx(2.0, abs=0.2)
    assert p.finger_bedienelement()


def test_touch_modus_bedienelemente_mindestens_44px(st):
    touch_keyboard.setze_touch_modus(True)
    p = _pad(w=360, h=340)
    z = p._zonen()
    for name in ("an", "lock", "hoehe"):
        assert z[name].height() >= 44 and z[name].width() >= 44, name
    touch_keyboard.setze_touch_modus(False)
    z = p._zonen()
    assert z["an"].height() < 44, "Maus bleibt kompakt"


def test_bankwechsel_gibt_gehaltenes_ziel_frei(st):
    p = _pad()
    p.position_lock = False
    _maus(p, QEvent.Type.MouseButtonPress, _px(p, 1.0, 1.0))
    assert p.aktiv
    assert p.release_if_held() is True
    assert st.get_programmer_value(2, "pan") is None


# ── Speichern / Laden ───────────────────────────────────────────────────────

def test_dict_rundweg(st):
    p = _pad(fids=[2, 1])
    p.gruppen = ["Movers"]
    p.ziel = (1.25, -0.5)
    p.hoehe = 1.5
    p.position_lock = False
    d = json.loads(json.dumps(p.to_dict()))
    q = VCRaumPad()
    q.apply_dict(d)
    assert (q._fixture_ids, q.gruppen, q.ziel, q.hoehe, q.position_lock) == \
        ([2, 1], ["Movers"], (1.25, -0.5), 1.5, False)
    assert q.aktiv is False, "eine geladene Show schreibt nichts von selbst"
    q.deleteLater()


def test_canvas_kennt_den_typ_und_alte_layouts_bleiben(st):
    from src.ui.virtualconsole.vc_canvas import VCCanvas, WIDGET_REGISTRY
    assert WIDGET_REGISTRY["VCRaumPad"] is VCRaumPad
    alt = {"widgets": [
        {"type": "VCXYPad", "caption": "MH", "x": 10, "y": 10, "w": 160, "h": 160,
         "pan": 0.25, "tilt": 0.75, "fixture_ids": [2], "mode": "position"},
        {"type": "VCButton", "caption": "Go", "x": 200, "y": 10, "w": 80, "h": 60},
    ]}
    c = VCCanvas()
    c.from_dict(json.loads(json.dumps(alt)))
    typen = [w["type"] for w in c.to_dict()["widgets"]]
    assert typen == ["VCXYPad", "VCButton"]
    xy = c.to_dict()["widgets"][0]
    assert (xy["pan"], xy["tilt"], xy["fixture_ids"]) == (0.25, 0.75, [2])
    assert st.programmer == {}, "Laden schreibt nichts in den Programmer"
    # Neues Widget dazu und zurueck
    neu = dict(alt)
    neu["widgets"] = alt["widgets"] + [
        {"type": "VCRaumPad", "caption": "Raum", "x": 300, "y": 10, "w": 260, "h": 240,
         "fixture_ids": [1, 2], "ziel": [0.5, 1.0], "hoehe": 0.0, "position_lock": True}]
    c2 = VCCanvas()
    c2.from_dict(json.loads(json.dumps(neu)))
    rp = [w for w in c2.to_dict()["widgets"] if w["type"] == "VCRaumPad"]
    assert len(rp) == 1 and rp[0]["ziel"] == [0.5, 1.0] and rp[0]["fixture_ids"] == [1, 2]
    assert st.programmer == {}
    c.deleteLater(); c2.deleteLater()


def test_show_datei_speichern_laden_und_alt_show(monkeypatch):
    """Echte .lshow ueber save_show/load_show (Sandkasten-Show-DB aus conftest)."""
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: [])
    from src.core.show import show_file as SF
    from src.core.app_state import get_state
    state = get_state()
    SF.reset_show()
    with tempfile.TemporaryDirectory(prefix="lightos_ui127_") as tmp:
        # Alt-Show: im Test erzeugt, ohne Raum-Pad
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

        pad = VCRaumPad("Raum")
        pad._fixture_ids = [5]
        pad.ziel = (2.0, -1.0)
        pad.hoehe = 0.8
        pad.position_lock = False
        neu_pfad = os.path.join(tmp, "neu.lshow")
        state = get_state()
        state._vc_layout = {"widgets": alt_vc["widgets"] + [pad.to_dict()]}
        SF.save_show(neu_pfad)
        ok, msg = SF.load_show(neu_pfad)
        assert ok, msg
        rp = [w for w in get_state()._vc_layout["widgets"] if w["type"] == "VCRaumPad"]
        assert len(rp) == 1
        q = VCRaumPad()
        q.apply_dict(rp[0])
        assert (q._fixture_ids, q.ziel, q.hoehe, q.position_lock) == ([5], (2.0, -1.0), 0.8, False)
        q.deleteLater()
        pad.deleteLater()
    SF.reset_show()

"""ENG-35 Schritt 4: Spalte „Verdeckt“ im Reiter Prioritäten.

- Sichtbar: das Protokoll ist angefordert und ein 3-Hz-Takt laeuft;
  ausgeblendet oder zerstoert: Protokoll wieder abgegeben, Takt steht.
- Die Spalte sagt „verdeckt von X auf n Geräten“ fuer einen laufenden,
  verdeckten Effekt; leer fuer den Gewinner und fuer nicht laufende Effekte.
"""
from __future__ import annotations

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402
from PySide6.QtCore import QEvent                           # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine import stufen                          # noqa: E402
from src.core.engine.function_manager import get_function_manager  # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)
from src.core.undo import get_undo_stack                    # noqa: E402
from src.ui.views import prioritaeten_view as PV           # noqa: E402

N = 6
AKZENTE = stufen.stufe_fuer_schluessel("akzente").zahl


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""
    fixture_name = ""
    fixture_type = ""

    def __init__(self, fid):
        self.fid = fid
        self.universe = 1
        self.address = 1 + 4 * (fid - 1)
        self.label = f"Lampe {fid}"


PATCH = [_Fx(fid) for fid in range(1, N + 1)]
KANAELE = [_Ch("intensity", 1), _Ch("color_r", 2), _Ch("color_g", 3),
           _Ch("color_b", 4)]


def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fm(monkeypatch):
    _app()
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: KANAELE)
    monkeypatch.setattr(A, "get_state", lambda: types.SimpleNamespace(
        get_patched_fixtures=lambda: list(PATCH)))
    manager = get_function_manager()
    manager.stop_all()
    vorher = {f.id for f in manager.all()}
    zaehler = manager._wg_zaehler
    get_undo_stack().clear()
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if f.id not in vorher:
            manager.remove(f.id)
    get_undo_stack().clear()
    assert manager._wg_zaehler == zaehler, "Ansicht hat das Protokoll nicht abgegeben"


@pytest.fixture
def ansicht(fm):
    v = PV.PrioritaetenView()
    v.resize(1100, 600)
    v.show()
    _app().processEvents()
    yield v
    v.close()
    v.deleteLater()
    _app().processEvents()


def _matrix(fm, name, grid, prio=0):
    m = RgbMatrixInstance(name, cols=len(grid), rows=1, fixture_grid=list(grid),
                          algorithm=RgbAlgorithm.PLAIN, color1=(255, 255, 255))
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    m.priority = prio
    fm.add(m)
    return m


def _zeile(v, fid):
    for it in v._effekt_zeilen():
        if it.data(0, PV._ROLLE_FID) == fid:
            return it
    raise AssertionError(f"Zeile {fid} fehlt")


def test_spalte_verdeckt_steht_im_kopf(ansicht):
    assert ansicht._baum.headerItem().text(PV._SP_VERDECKT) == "Verdeckt"
    assert 250 <= PV.WG_INTERVALL_MS <= 500, "2–4 Hz"


def test_sichtbar_fordert_an_ausblenden_gibt_ab(fm, ansicht):
    start = fm._wg_zaehler
    assert fm.wer_gewinnt_aktiv and ansicht._wg_timer.isActive()
    ansicht.hide()
    _app().processEvents()
    assert fm._wg_zaehler == start - 1 and not ansicht._wg_timer.isActive()
    ansicht.show()
    _app().processEvents()
    assert fm._wg_zaehler == start, "wieder sichtbar: genau eine Anforderung"


def test_zerstoeren_gibt_das_protokoll_ab(fm):
    vorher = fm._wg_zaehler
    v = PV.PrioritaetenView()
    v.show()
    _app().processEvents()
    assert fm._wg_zaehler == vorher + 1
    v.deleteLater()                               # ohne vorheriges hide
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _app().processEvents()
    assert fm._wg_zaehler == vorher


def test_verdeckter_effekt_zeigt_wer_darueber_liegt(fm, ansicht):
    unten = _matrix(fm, "Grundlicht warm", range(1, N + 1))
    oben = _matrix(fm, "Akzent Mitte", (3, 4), prio=AKZENTE)
    still = _matrix(fm, "Steht nur rum", (1, 2))
    fm.start(unten.id)
    fm.start(oben.id)
    ansicht.neu_aufbauen()
    fm.tick({1: Universe(1)}, list(PATCH), 0.02)
    ansicht.verdeckt_nachziehen()
    sp = PV._SP_VERDECKT
    assert _zeile(ansicht, unten.id).text(sp) == \
        "verdeckt von Akzent Mitte auf 2 Geräten"
    assert "gewinnt auf 4 Geräten" in _zeile(ansicht, unten.id).toolTip(sp)
    assert _zeile(ansicht, oben.id).text(sp) == ""
    assert _zeile(ansicht, still.id).text(sp) == ""
    # Akzent aus: im naechsten Frame ist nichts mehr verdeckt.
    fm.stop(oben.id)
    ansicht._laufzustand_nachziehen()
    fm.tick({1: Universe(1)}, list(PATCH), 0.02)
    ansicht.verdeckt_nachziehen()
    assert _zeile(ansicht, unten.id).text(sp) == ""


def test_takt_fuellt_die_spalte(fm, ansicht):
    unten = _matrix(fm, "Grundlicht", range(1, N + 1))
    oben = _matrix(fm, "Blinder", (1,), prio=AKZENTE)
    fm.start(unten.id)
    fm.start(oben.id)
    ansicht.neu_aufbauen()
    fm.tick({1: Universe(1)}, list(PATCH), 0.02)
    ansicht._wg_takt()
    assert _zeile(ansicht, unten.id).text(PV._SP_VERDECKT) == \
        "verdeckt von Blinder auf 1 Gerät"


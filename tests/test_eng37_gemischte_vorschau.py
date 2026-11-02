"""ENG-37: gemischte Vorschau eines Modify-Effekts im Matrix-Editor.

Bisher zeigte die Vorschau eines Modify-Effekts nur seinen BETRAG (Laeufer
bernstein/blau/grau eingefaerbt) — nicht, was am Ende herauskommt. Jetzt zeigt
sie (Vorgabe „Vorschau gemischt") das Grundbild, also das, was darunter laeuft,
mit dem Modify verrechnet.

★ EIN Ort, eine Regel: die Vorschau rechnet nicht selbst. Der Renderer merkt
  sich auf Anforderung das Bild unmittelbar VOR seinem Modify-Gang 4a²b
  (``AppState.grundbild``); ``modify.vorschau_mischen`` verrechnet darauf mit
  denselben Bausteinen wie der Renderer (``modify_posten`` +
  ``posten_anwenden``). Geprueft wird darum: Vorschau == Ausgang, Wert fuer
  Wert, in allen drei Betriebsarten und im Stil Farbe.
"""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.app_state import AppState                     # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.modify import MODIFY_MODES             # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

_app = QApplication.instance() or QApplication([])

N = 8
P40 = 102
DT = 0.02


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []


class _Fx:
    fixture_profile_id = 1
    mode_name = "m"
    channel_count = 4
    protocol = ""
    fixture_name = ""
    fixture_type = ""

    def __init__(self, fid, address, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address


def _adr(i):
    return 1 + 4 * i


_KANAELE = {fid: [_Ch("intensity", 1), _Ch("color_r", 2),
                  _Ch("color_g", 3), _Ch("color_b", 4)]
            for fid in range(1, N + 1)}


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])


def _matrix(name, algo=RgbAlgorithm.PLAIN, style=MatrixStyle.DIMMER,
            color1=(255, 255, 255), **felder):
    m = RgbMatrixInstance(name, cols=N, rows=1,
                          fixture_grid=list(range(1, N + 1)),
                          algorithm=algo, color1=color1)
    m.style = style
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _lauflicht(mode="add", staerke=100, style=MatrixStyle.DIMMER,
               color1=(255, 255, 255)):
    m = _matrix("modify", RgbAlgorithm.CHASE, style=style, color1=color1)
    m.params.update({"runner_count": 2, "after_fade": 0.0,
                     "movement": "normal"})
    m.modify, m.modify_mode, m.modify_strength = True, mode, staerke
    return m


def _zustand(*funktionen):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
        fm.start(f.id)
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.output_manager = types.SimpleNamespace(
        set_gm_address_mask=lambda m: None)
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = [_Fx(fid, _adr(fid - 1)) for fid in range(1, N + 1)]
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st.base_levels = {}
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st._suppress_emits = True
    st._prog_lock = threading.RLock()
    st._rebuild_render_plan()
    return st


def _vorschau(m, st):
    from src.ui.views.rgb_matrix_view import MatrixPreview
    v = MatrixPreview()
    v._timer.stop()
    v.set_matrix(m)
    v._grundbild_quelle = lambda: ((st.grundbild(), st._patch_cache)
                                   if st.grundbild() else None)
    return v


def _ausgang_dimmer(st):
    roh = st.universes[1].get_all()
    return [roh[_adr(i) - 1] for i in range(N)]


def _ausgang_farbe(st):
    roh = st.universes[1].get_all()
    return [tuple(roh[_adr(i) + k] for k in range(3)) for i in range(N)]


# ── Vorschau == Ausgang ──────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("staerke", [100, 50])
def test_vorschau_zeigt_was_am_ausgang_herauskommt(rig, mode, staerke):
    """Unter acht Lampen laeuft ein Dimmer-Effekt auf 40 %, darueber ein
    Modify-Lauflicht. Die gemischte Vorschau zeigt Zelle fuer Zelle genau den
    Dimmerwert, den der Renderer ausgibt — nicht den Modify-Betrag allein."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht(mode, staerke)
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    ausgang = _ausgang_dimmer(st)
    # Gemischt heisst: Lampen ausserhalb des Laeufers stehen auf dem Grundbild.
    assert ausgang.count(P40) == N - 2
    assert len(set(ausgang)) == 2
    v = _vorschau(mod, st)
    try:
        zellen = v.gemischte_zellen()
        assert zellen is not None, "keine gemischte Vorschau"
        assert [z[0] for z in zellen] == ausgang
        assert all(z[0] == z[1] == z[2] for z in zellen)
    finally:
        v.deleteLater()


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_farb_modify_vorschau_gleich_ausgang(rig, mode):
    """Stil RGB: blauer Untergrund, rotes Modify-Lauflicht."""
    unten = _matrix("unten", style=MatrixStyle.RGB, color1=(0, 0, 200))
    mod = _lauflicht(mode, 100, style=MatrixStyle.RGB, color1=(255, 0, 255))
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    ausgang = _ausgang_farbe(st)
    v = _vorschau(mod, st)
    try:
        zellen = v.gemischte_zellen()
        assert zellen is not None
        assert zellen == ausgang
        assert ausgang.count((0, 0, 200)) == N - 2
    finally:
        v.deleteLater()


def test_vorschau_malt_das_ergebnis(rig):
    """Gemalt wird das Ergebnis: eine Lampe ausserhalb des Laeufers steht grau
    auf 40 % — nicht schwarz bzw. bernstein wie bei „nur Modify"."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    ausgang = _ausgang_dimmer(st)
    v = _vorschau(mod, st)
    try:
        v._grid = mod.preview_pixels()
        v._misch = v.gemischte_zellen()
        img = v.grab().toImage()
        idx = ausgang.index(P40)
        cell_w = (v.width() - 10) / N
        x = int(5 + idx * cell_w + cell_w / 2)
        y = v.height() // 2
        c = img.pixelColor(x, y)
        assert (c.red(), c.green(), c.blue()) == (P40, P40, P40)
    finally:
        v.deleteLater()


# ── Umschalter und Rueckfall ────────────────────────────────────────────────


def test_umschalter_nur_modify(rig):
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    v = _vorschau(mod, st)
    try:
        assert v.gemischte_zellen() is not None
        v.set_gemischt(False)
        assert v.gemischte_zellen() is None
        v.set_gemischt(True)
        assert v.gemischte_zellen() is not None
    finally:
        v.deleteLater()


def test_ohne_grundbild_nur_modify(rig):
    """Ohne Anforderung merkt der Renderer nichts (Kosten), und ohne Grundbild
    faellt die Vorschau auf „nur Modify" zurueck."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st._render_frame(DT)
    assert st.grundbild() is None
    v = _vorschau(mod, st)
    try:
        assert v.gemischte_zellen() is None
    finally:
        v.deleteLater()


def test_veraltetes_grundbild_gilt_nicht(rig):
    """Steht der Renderer (Ausgabe angehalten), zeigt die Vorschau nicht ewig
    das letzte Bild als „was darunter laeuft" — wie die Anleitung sagt, faellt
    sie auf „nur Modify" zurueck."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    assert st.grundbild() is not None
    st._grundbild_zeit -= AppState.GRUNDBILD_MAX_ALTER + 1.0
    assert st.grundbild() is None
    v = _vorschau(mod, st)
    try:
        assert v.gemischte_zellen() is None
    finally:
        v.deleteLater()


def test_normaler_effekt_wird_nicht_gemischt(rig):
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    st = _zustand(unten)
    st.grundbild_anfordern()
    st._render_frame(DT)
    v = _vorschau(unten, st)
    try:
        assert v.gemischte_zellen() is None
    finally:
        v.deleteLater()


def test_vorschau_verstellt_den_laufenden_effekt_nicht(rig):
    """Die Vorschau schreibt eine Kopie mit angehaltener Uhr — Phase und
    Laufzustand des (live laufenden) Effekts bleiben unberuehrt."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    schritt, laeuft = mod._step, mod._running
    v = _vorschau(mod, st)
    try:
        for _ in range(3):
            v.gemischte_zellen()
        assert mod._step == schritt
        assert mod._running is laeuft
    finally:
        v.deleteLater()


def test_grundbild_ist_das_bild_vor_dem_modify_gang(rig):
    """Das gemerkte Grundbild enthaelt den Untergrund (40 %), nicht das
    Ergebnis mit dem Modify."""
    unten = _matrix("unten", intensity_min=P40, intensity_max=P40)
    mod = _lauflicht("add")
    st = _zustand(unten, mod)
    st.grundbild_anfordern()
    st._render_frame(DT)
    gb = st.grundbild()[1]
    assert [gb[_adr(i) - 1] for i in range(N)] == [P40] * N
    assert _ausgang_dimmer(st) != [P40] * N


def test_editor_hat_umschalter_in_der_gruppe_modify():
    """Im Editor sitzt der Haken „Vorschau gemischt" (Vorgabe an) in der
    Gruppe „Modify" und schaltet die Vorschau um."""
    from src.core.engine.function_manager import get_function_manager
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    from _qt_lifecycle import destroy_all_top_level_widgets
    a = RgbMatrixView()
    a._add()
    eigene = a._saved
    try:
        cb = a._cb_vorschau_gemischt
        assert cb.isChecked() and a._preview._gemischt
        assert cb.parent() is a._grp_modify
        cb.setChecked(False)
        assert a._preview._gemischt is False
        cb.setChecked(True)
        assert a._preview._gemischt is True
    finally:
        try:
            if eigene is not None:
                get_function_manager().remove(eigene.id)
        except Exception:
            pass
        destroy_all_top_level_widgets(QApplication.instance())


def test_anleitung_nennt_den_umschalter_wie_der_code():
    """Anleitung Dimmer-Matrix §5 beschreibt den Haken mit demselben Namen,
    den der Editor zeigt."""
    import re
    quelle = (ROOT / "src/ui/views/rgb_matrix_view.py").read_text(encoding="utf-8")
    name = re.search(r'_cb_vorschau_gemischt = QCheckBox\("([^"]+)"\)', quelle).group(1)
    doku = (ROOT / "docs/anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md"
            ).read_text(encoding="utf-8")
    abschnitt = doku.split("## 5.", 1)[1].split("\n## ", 1)[0]
    assert f"**{name}**" in abschnitt
    assert "was am Ende herauskommt" in abschnitt

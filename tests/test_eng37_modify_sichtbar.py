"""ENG-37 „Modify sichtbar machen" (Entscheidungen des Projektinhabers vom 19.10.2026).

37-B  Eine VC-Taste (und ein Effekt-Fader), deren Funktion ein Modify-Effekt ist,
      zeigt unten links das Zeichen der Betriebsart — „+" Addieren, „−" Abziehen,
      „◐" Abdunkeln — in den Farben der Editor-Vorschau. Das Zeichen zieht nach,
      wenn Haken oder Betriebsart umgestellt werden; oben rechts (Farb-Badge,
      Gobo) bleibt frei.
37-A  Der Chaser-Editor warnt bei einem Schritt, dessen Funktion (oder ein Kind
      einer Sammlung/Show darin) Modify ist: die Engine gibt ihn dort nicht aus.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import MatrixStyle

_app = QApplication.instance() or QApplication([])

AMBER = (255, 176, 0)
BLAU = (64, 140, 255)
GRAU = (200, 200, 200)


@pytest.fixture
def fm():
    m = get_function_manager()
    angelegt: list[int] = []
    m._eng37s_angelegt = angelegt
    yield m
    for fid in angelegt:
        try:
            m.stop(fid)
            m.remove(fid)
        except Exception:
            pass


def _matrix(fm, name="Modify", style=MatrixStyle.DIMMER, modify=True, mode="add"):
    m = fm.new_rgb_matrix(name)
    fm._eng37s_angelegt.append(m.id)
    m.style = style
    m.modify = modify
    m.modify_mode = mode
    return m


def _treffer(img, x0, y0, x1, y1, rgb, tol=40) -> int:
    n = 0
    for x in range(max(0, x0), min(img.width(), x1)):
        for y in range(max(0, y0), min(img.height(), y1)):
            c = img.pixelColor(x, y)
            if (abs(c.red() - rgb[0]) <= tol and abs(c.green() - rgb[1]) <= tol
                    and abs(c.blue() - rgb[2]) <= tol):
                n += 1
    return n


# ── eine Quelle fuer Zeichen und Farben ─────────────────────────────────────

def test_zeichen_und_farben_der_entscheidung():
    from src.ui.widgets.modify_zeichen import MODIFY_VORSCHAU_RGB, MODIFY_ZEICHEN
    assert MODIFY_ZEICHEN == {"add": "+", "sub": "−", "dim": "◐"}
    assert MODIFY_VORSCHAU_RGB == {"add": AMBER, "sub": BLAU, "dim": GRAU}


@pytest.mark.parametrize("mode,rgb", [("add", AMBER), ("sub", BLAU)])
def test_editor_vorschau_malt_in_denselben_farben(fm, mode, rgb):
    """Die Matrix-Vorschau des Editors faerbt einen Dimmer-Modify genau so ein —
    sonst passen Taste und Editor nicht zusammen."""
    from src.ui.views.rgb_matrix_view import MatrixPreview
    m = _matrix(fm, mode=mode)
    v = MatrixPreview()
    try:
        v._timer.stop()
        v.set_matrix(m)
        v._grid = [(255, 255, 255)] * (m.cols * m.rows)
        img = v.grab().toImage()
        assert _treffer(img, 0, 0, img.width(), img.height(), rgb, tol=2) > 50
    finally:
        v._timer.stop()
        v.deleteLater()


# ── 37-B: VC-Taste ──────────────────────────────────────────────────────────

def _taste(fid):
    from src.ui.virtualconsole.vc_button import ButtonAction, VCButton
    b = VCButton("Läufer über Grund")
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = fid
    return b


def test_taste_kennt_die_betriebsart_und_zieht_nach(fm):
    m = _matrix(fm, mode="add")
    b = _taste(m.id)
    assert b._modify_arten() == ["add"]
    m.modify_mode = "sub"
    assert b._modify_arten() == ["sub"]
    m.modify_mode = "dim"
    assert b._modify_arten() == ["dim"]
    m.modify = False
    assert b._modify_arten() == []
    m.modify = True
    m.style = MatrixStyle.SHUTTER          # Haken ohne Wirkung -> kein Zeichen
    assert b._modify_arten() == []


def test_nur_funktionstasten_zeigen_das_zeichen(fm):
    from src.ui.virtualconsole.vc_button import ButtonAction
    m = _matrix(fm)
    b = _taste(m.id)
    b.action = ButtonAction.FLASH
    assert b._modify_arten() == []
    b.action = ButtonAction.EFFECT_ACTION
    assert b._modify_arten() == ["add"]


def test_normaler_effekt_ohne_zeichen(fm):
    m = _matrix(fm, modify=False)
    assert _taste(m.id)._modify_arten() == []


@pytest.mark.parametrize("mode,rgb", [("add", AMBER), ("sub", BLAU), ("dim", GRAU)])
def test_taste_malt_zeichen_unten_links(fm, mode, rgb):
    m = _matrix(fm, mode=mode)
    b = _taste(m.id)
    b._bg_color = __import__("PySide6.QtGui", fromlist=["QColor"]).QColor("#2d333b")
    img = b.grab().toImage()
    w, h = img.width(), img.height()
    unten_links = _treffer(img, 0, h // 2, w // 3, h, rgb, tol=30)
    oben_rechts = _treffer(img, 2 * w // 3, 0, w, h // 3, rgb, tol=6)
    # Gegenprobe ohne Modify: dieselbe Ecke hat (fast) nichts in der Farbe —
    # Grau steckt allerdings auch im Glanzrand der 3D-Taste, darum die Differenz.
    m.modify = False
    img2 = b.grab().toImage()
    ohne = _treffer(img2, 0, h // 2, w // 3, h, rgb, tol=30)
    assert unten_links - ohne >= 4, (mode, unten_links, ohne)
    if mode != "dim":
        assert ohne == 0
        assert oben_rechts == 0


def test_beschriftung_weicht_dem_zeichen_aus(fm):
    """Ein mehrzeiliger Text endet oberhalb des Zeichens (kein Ueberdecken)."""
    from PySide6.QtGui import QColor
    m = _matrix(fm, mode="add")
    b = _taste(m.id)
    b.caption = "Ein sehr langer Name fuer den Läufer"
    b._bg_color = QColor("#2d333b")
    b._fg_color = QColor("#ff00ff")
    img = b.grab().toImage()
    w, h = img.width(), img.height()
    # Zeichen-Kaestchen: links unten, 16 px hoch, ueber dem 4-px-Streifen.
    assert _treffer(img, 4, h - 27, 22, h - 6, (255, 0, 255), tol=40) == 0
    m.modify = False
    img2 = b.grab().toImage()
    # ohne Zeichen darf der Text dort stehen (Gegenprobe: das Kriterium greift)
    assert _treffer(img2, 0, 0, w, h, (255, 0, 255), tol=40) > 0


# ── 37-B: VC-Fader ──────────────────────────────────────────────────────────

def test_fader_im_effektmodus_zeigt_zeichen(fm):
    from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider
    m = _matrix(fm, mode="sub")
    s = VCSlider("Läufer")
    s.mode = SliderMode.EFFECT_INTENSITY
    s.function_id = m.id
    assert s._modify_arten() == ["sub"]
    img = s.grab().toImage()
    assert _treffer(img, 0, img.height() - 40, 20, img.height() - 16, BLAU, tol=30) >= 4
    s.mode = SliderMode.LEVEL
    assert s._modify_arten() == []
    s.mode = SliderMode.EFFECT_PARAM
    s.function_id = None                      # Rueckfall „aktiver Effekt": nichts
    assert s._modify_arten() == []


# ── Nachziehen in der Konsole ───────────────────────────────────────────────

def test_signatur_aendert_sich_bei_haken_und_betriebsart(fm):
    from src.ui.widgets.modify_zeichen import modify_signatur
    m = _matrix(fm, mode="add")
    a = modify_signatur([m])
    m.modify_mode = "dim"
    b = modify_signatur([m])
    m.modify = False
    c = modify_signatur([m])
    assert a == ((m.id, "add"),) and b == ((m.id, "dim"),) and c == ()


# ── 37-A: Modify in Chaser-Schritten ───────────────────────────────────────

def test_modify_unter_findet_kinder(fm):
    from src.core.engine.show_engine import ShowFunction, ShowTrack
    from src.core.engine.stufen import modify_unter
    mod = _matrix(fm, "Modify-Kind")
    normal = _matrix(fm, "Normal", modify=False)
    coll = fm.new_collection("Sammlung")
    fm._eng37s_angelegt.append(coll.id)
    coll.function_ids = [normal.id, mod.id]
    show = fm.new_show("Zeitleiste")
    fm._eng37s_angelegt.append(show.id)
    spur = ShowTrack()
    spur.add_function(ShowFunction(function_id=coll.id, start_time=0.0, duration=1.0))
    show.tracks.append(spur)
    assert modify_unter(mod, fm.get) == [mod]
    assert modify_unter(normal, fm.get) == []
    assert modify_unter(coll, fm.get) == [mod]
    assert modify_unter(show, fm.get) == [mod]
    # Zyklus (Sammlung enthaelt sich selbst) bricht still ab
    coll.function_ids.append(coll.id)
    assert modify_unter(coll, fm.get) == [mod]


def _editor(fm, *fids):
    from src.core.engine.chaser import ChaserStep
    from src.ui.views.chaser_editor import ChaserEditor
    ch = fm.new_chaser("Chase")
    fm._eng37s_angelegt.append(ch.id)
    for fid in fids:
        ch.steps.append(ChaserStep(function_id=fid, fade_in=0.0, hold=1.0, fade_out=0.0))
    return ChaserEditor(ch)


def test_chaser_editor_warnt_bei_modify_schritt(fm):
    from src.ui.views.chaser_editor import MODIFY_SCHRITT_HINWEIS
    assert MODIFY_SCHRITT_HINWEIS == (
        "Modify-Effekte geben als Chaser-Schritt nichts aus – direkt, in einer "
        "Sammlung oder der Show-Zeitleiste starten")
    mod = _matrix(fm, "Läufer-Modify")
    normal = _matrix(fm, "Grund", modify=False)
    coll = fm.new_collection("Mit Modify")
    fm._eng37s_angelegt.append(coll.id)
    coll.function_ids = [normal.id, mod.id]
    ed = _editor(fm, normal.id, mod.id, coll.id)
    try:
        assert not ed._modify_hinweis.isHidden()
        assert "Schritt 2, 3" in ed._modify_hinweis.text()
        assert MODIFY_SCHRITT_HINWEIS in ed._modify_hinweis.text()
        it_norm, it_mod, it_coll = (ed._table.item(r, 1) for r in range(3))
        assert it_norm.toolTip() == ""
        assert MODIFY_SCHRITT_HINWEIS in it_mod.toolTip()
        assert "Läufer-Modify" in it_coll.toolTip()     # Kind wird genannt
        assert it_mod.foreground().color().name() == "#e3b341"
        # Haken weg -> Hinweis verschwindet beim Neuaufbau
        mod.modify = False
        ed._rebuild_table()
        assert ed._modify_hinweis.isHidden()
        assert ed._table.item(1, 1).toolTip() == ""
    finally:
        ed.deleteLater()


def test_chaser_editor_ohne_modify_still(fm):
    normal = _matrix(fm, "Grund", modify=False)
    ed = _editor(fm, normal.id)
    try:
        assert ed._modify_hinweis.isHidden()
    finally:
        ed.deleteLater()


def test_engine_sperrt_wirklich_was_der_editor_meldet(fm):
    """Der Hinweis beschreibt die echte Sperre: ein Modify-Schritt liefert kein Ziel."""
    from src.core.engine.chaser import Chaser
    mod = _matrix(fm, "Läufer-Modify")
    assert Chaser._render_child_target(mod, [1], {}, fm) == {}


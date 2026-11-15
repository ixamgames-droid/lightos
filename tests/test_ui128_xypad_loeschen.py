"""UI-128: VC-XY-Pad — Knopf „Bereich löschen" / „Pfad löschen" unter dem Pad.

Feld-Modus: Bereich aufziehen aendert Zentrum/Groesse des Ziel-EFX; der Knopf
entfernt den Bereich und stellt genau die Werte von VOR dem ersten Aufziehen
wieder her (nur eigene Aenderungen). Pfad-Modus entsprechend mit Custom-Pfad.
Der Knopf ist im Spielbetrieb bedienbar, die Touch-Sperre sperrt ihn, im
Bearbeiten-Modus loest er nicht aus (dort steht der Befehl im Kontextmenue).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QWidget           # noqa: E402

from src.core.engine.efx import EfxAlgorithm, EfxFixture, EfxInstance  # noqa: E402
from src.core.engine.efx_path import EfxPath                         # noqa: E402
from src.core.engine.function_manager import get_function_manager    # noqa: E402
from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402
from src.ui.virtualconsole.vc_xypad import VCXYPad                   # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

GEO = ("x_offset", "y_offset", "width", "height")


@pytest.fixture
def efx():
    zs.einrichten(_app).aktiv = True
    fm = get_function_manager()
    fm.stop_all()
    vorher = {f.id for f in fm.all()}
    e = EfxInstance("mh")
    e.algorithm = EfxAlgorithm.EIGHT
    e.fixtures = [EfxFixture(fid=5)]
    e.x_offset, e.y_offset, e.width, e.height = 100.0, 140.0, 80.0, 60.0
    fm.add(e)
    alt_lock = VCWidget.input_locked
    alt_touch = touch_keyboard.is_touch_mode()
    yield e
    VCWidget.input_locked = alt_lock
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)
    fm.stop_all()
    for f in list(fm.all()):
        if f.id not in vorher:
            fm.remove(f.id)


def _pad(e, mode="area", w=240, h=240):
    p = VCXYPad("XY")
    p.mode = mode
    p.efx_function_id = e.id
    p.resize(w, h)
    eltern = QWidget()
    eltern.resize(w + 40, h + 40)
    p.setParent(eltern)
    p.move(20, 20)
    eltern.show()
    p._traeger = eltern
    QApplication.processEvents()
    return p


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


def _zug(w, a: QPoint, b: QPoint, schritte=6):
    _maus(w, QEvent.Type.MouseButtonPress, a)
    for i in range(1, schritte + 1):
        _maus(w, QEvent.Type.MouseMove, a + (b - a) * (i / schritte))
    _maus(w, QEvent.Type.MouseButtonRelease, b)


def _pt(p, nx, ny) -> QPoint:
    pr = p._pad_rect()
    return QPoint(round(pr.x() + nx * pr.width()), round(pr.y() + ny * pr.height()))


def _geo(e):
    return tuple(getattr(e, k) for k in GEO)


def _bereich_aufziehen(p):
    _zug(p, _pt(p, 0.6, 0.6), _pt(p, 0.9, 0.85))


# ── Feld-Modus ──────────────────────────────────────────────────────────────

def test_bereich_loeschen_stellt_efx_exakt_wieder_her(efx):
    vorher = _geo(efx)
    p = _pad(efx)
    assert p._loesch_knopf_rect() is None, "ohne Bereich kein Knopf"
    _bereich_aufziehen(p)
    assert p._area is not None and _geo(efx) != vorher
    # ein zweites Aufziehen darf die gemerkten Vorwerte nicht ueberschreiben
    _zug(p, _pt(p, 0.1, 0.1), _pt(p, 0.3, 0.4))
    knopf = p._loesch_knopf_rect()
    assert knopf is not None
    assert not knopf.intersects(p._pad_rect()), "Knopf liegt unter dem Pad"
    _klick(p, knopf.center())
    assert p._area is None
    assert _geo(efx) == vorher
    assert p._loesch_knopf_rect() is None, "Knopf weg"


def test_fremd_geaenderter_wert_bleibt_stehen(efx):
    """Begruendung: der Knopf nimmt nur die EIGENEN Aenderungen zurueck. Hat
    inzwischen ein Fader/die Command-Line die Breite verstellt, bleibt diese
    Bedienung erhalten; die uebrigen Werte gehen auf die Vorwerte."""
    vorher = _geo(efx)
    p = _pad(efx)
    _bereich_aufziehen(p)
    efx.width = 33.0                                  # fremde Bedienung
    assert p.bereich_loeschen()
    assert efx.width == 33.0
    assert (efx.x_offset, efx.y_offset, efx.height) == (vorher[0], vorher[1], vorher[3])


def test_wechsel_des_ziel_efx_merkt_neu(efx):
    fm = get_function_manager()
    e2 = EfxInstance("mh2")
    e2.x_offset, e2.y_offset, e2.width, e2.height = 10.0, 20.0, 30.0, 40.0
    fm.add(e2)
    p = _pad(efx)
    _bereich_aufziehen(p)
    p.efx_function_id = e2.id
    _bereich_aufziehen(p)
    p.bereich_loeschen()
    assert _geo(e2) == (10.0, 20.0, 30.0, 40.0)


# ── Pfad-Modus ──────────────────────────────────────────────────────────────

def test_pfad_loeschen_stellt_vorherigen_pfad_wieder_her(efx):
    alt = EfxPath("Alt", [(0.0, 0.0), (1.0, 1.0)])
    efx.set_custom_path(alt)
    vorher = (efx.algorithm, efx.path_id, json.dumps(efx.path_data), _geo(efx))
    p = _pad(efx, mode="path")
    _zug(p, _pt(p, 0.1, 0.1), _pt(p, 0.9, 0.7))
    assert efx.path_id != alt.id and efx.width == 255.0
    knopf = p._loesch_knopf_rect()
    assert knopf is not None and p.loesch_text() == "Pfad löschen"
    _klick(p, knopf.center())
    assert p._path_pts == []
    assert (efx.algorithm, efx.path_id, json.dumps(efx.path_data), _geo(efx)) == vorher
    assert p._loesch_knopf_rect() is None


def test_pfad_loeschen_zurueck_auf_algorithmus(efx):
    vorher = _geo(efx)
    p = _pad(efx, mode="path")
    _zug(p, _pt(p, 0.2, 0.2), _pt(p, 0.8, 0.8))
    assert efx.algorithm == EfxAlgorithm.CUSTOM
    assert p.pfad_loeschen()
    assert efx.algorithm == EfxAlgorithm.EIGHT
    assert efx.path_id is None and efx.path_data is None
    assert _geo(efx) == vorher


def test_anderswo_gewaehlter_pfad_bleibt(efx):
    p = _pad(efx, mode="path")
    _zug(p, _pt(p, 0.2, 0.2), _pt(p, 0.8, 0.8))
    fremd = EfxPath("Fremd", [(0.0, 1.0), (1.0, 0.0)])
    efx.set_custom_path(fremd)
    p.pfad_loeschen()
    assert efx.path_id == fremd.id


# ── Betriebsarten ───────────────────────────────────────────────────────────

def test_spielbetrieb_bedienbar_touch_sperre_sperrt(efx):
    p = _pad(efx)
    _bereich_aufziehen(p)
    geaendert = _geo(efx)
    VCWidget.input_locked = True
    _klick(p, p._loesch_knopf_rect().center())
    assert p._area is not None and _geo(efx) == geaendert
    VCWidget.input_locked = False
    _klick(p, p._loesch_knopf_rect().center())
    assert p._area is None


def test_sperre_waehrend_des_druecks_loest_nicht_aus(efx):
    p = _pad(efx)
    _bereich_aufziehen(p)
    pos = p._loesch_knopf_rect().center()
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    VCWidget.input_locked = True
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    assert p._area is not None


def test_loslassen_neben_dem_knopf_loest_nicht_aus(efx):
    p = _pad(efx)
    _bereich_aufziehen(p)
    k = p._loesch_knopf_rect()
    _maus(p, QEvent.Type.MouseButtonPress, k.center())
    _maus(p, QEvent.Type.MouseButtonRelease, QPoint(k.center().x(), 30))
    assert p._area is not None


def test_bearbeiten_modus_loest_nicht_aus_kontextmenue_schon(efx, monkeypatch):
    vorher = _geo(efx)
    p = _pad(efx)
    _bereich_aufziehen(p)
    p.set_edit_mode(True)
    _klick(p, p._loesch_knopf_rect().center())
    assert p._area is not None
    menu = QMenu()
    p._extend_context_menu(menu)
    akt = [a for a in menu.actions() if "Bereich löschen" in a.text()]
    assert akt and akt[0].isEnabled()
    akt[0].trigger()
    assert p._area is None and _geo(efx) == vorher


def test_positionsmodus_ohne_knopf_und_ohne_menuepunkt(efx):
    p = _pad(efx, mode="position")
    assert p._pad_rect().bottom() == p.height() - 24 - 1, "Pad wie bisher"
    menu = QMenu()
    p._extend_context_menu(menu)
    assert not any("löschen" in a.text() for a in menu.actions())


# ── Groessen ────────────────────────────────────────────────────────────────

def test_touch_modus_knopf_mindestens_44px(efx):
    touch_keyboard.setze_touch_modus(True)
    p = _pad(efx)
    _bereich_aufziehen(p)
    k = p._loesch_knopf_rect()
    assert k.height() >= 44 and k.width() >= 44
    assert not k.intersects(p._pad_rect())
    assert k.bottom() <= p.height() - 1
    touch_keyboard.setze_touch_modus(False)
    k = p._loesch_knopf_rect()
    assert k.height() < 44, "Maus bleibt kompakt"


def test_maus_pad_flaeche_bleibt_gleich(efx):
    """Mit der Maus passt der Knopf in den bisherigen 24-px-Rand."""
    p = _pad(efx)
    assert p._pad_rect() == p.rect().adjusted(24, 24, -24, -24)


def test_zu_klein_knopf_aus_befehl_im_menue(efx):
    touch_keyboard.setze_touch_modus(True)
    p = _pad(efx, w=200, h=100)
    p._area = (0.2, 0.2, 0.6, 0.6)
    assert p._loesch_knopf_rect() is None
    assert p._pad_rect() == p.rect().adjusted(24, 24, -24, -24)
    menu = QMenu()
    p._extend_context_menu(menu)
    assert any("Bereich löschen" in a.text() and a.isEnabled() for a in menu.actions())


def test_finger_tipp_loescht(efx):
    vorher = _geo(efx)
    touch_keyboard.setze_touch_modus(True)
    p = _pad(efx, w=260, h=260)
    _bereich_aufziehen(p)
    pos = p._loesch_knopf_rect().center()
    QTest.touchEvent(p, _DEV).press(0, pos, p).commit()
    QApplication.processEvents()
    QTest.touchEvent(p, _DEV).release(0, pos, p).commit()
    QApplication.processEvents()
    assert p._area is None and _geo(efx) == vorher


def test_malen_mit_knopf(efx):
    touch_keyboard.setze_touch_modus(True)
    p = _pad(efx)
    _bereich_aufziehen(p)
    assert not p.grab().isNull()


# ── Speichern / Laden ───────────────────────────────────────────────────────

def test_alte_show_mit_area_laedt_unveraendert(efx):
    alt = {"type": "VCXYPad", "caption": "Pad", "x": 0, "y": 0, "w": 200, "h": 200,
           "pan": 0.5, "tilt": 0.5, "pan_attr": "pan", "tilt_attr": "tilt",
           "fixture_ids": [], "mode": "area", "bits16": False,
           "efx_function_id": efx.id, "area": [0.1, 0.2, 0.5, 0.6]}
    p = VCXYPad("x")
    p.apply_dict(json.loads(json.dumps(alt)))
    assert p._area == (0.1, 0.2, 0.5, 0.6)
    assert p.to_dict()["area"] == [0.1, 0.2, 0.5, 0.6]
    # Vorwerte unbekannt -> nur die Markierung geht, der EFX bleibt
    vorher = _geo(efx)
    assert p.bereich_loeschen()
    assert p._area is None and _geo(efx) == vorher


def test_geloeschter_bereich_bleibt_geloescht(efx):
    p = _pad(efx)
    _bereich_aufziehen(p)
    p.bereich_loeschen()
    d = json.loads(json.dumps(p.to_dict()))
    assert "area" not in d
    q = VCXYPad("y")
    q.apply_dict(d)
    assert q._area is None

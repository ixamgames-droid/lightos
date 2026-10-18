"""ENG-38: Der Haken „Modify-Effekt" ist im Matrix-Editor auch fuer die Stile
RGB und RGBW freigeschaltet; Stil Shutter bleibt gesperrt (mit Hinweis).

Die Felder selbst (fester Block, nur ein-/ausgeblendet) prueft
tests/test_eng37_modify_editor.py — hier geht es nur um die Freischaltung,
den Hinweistext, die Vorschau und das Speichern im Stil Farbe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ansicht():
    from PySide6.QtWidgets import QApplication
    from _qt_lifecycle import destroy_all_top_level_widgets
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    _app()
    a = RgbMatrixView()
    a._add()
    assert a._current is not None
    a._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    a._style_combo.setCurrentText("RGB")
    eigene = a._saved
    yield a
    try:
        from src.core.engine.function_manager import get_function_manager
        if eigene is not None:
            get_function_manager().remove(eigene.id)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.mark.parametrize("stil", ["RGB", "RGBW"])
def test_haken_ist_im_stil_farbe_frei(ansicht, stil):
    ansicht._style_combo.setCurrentText(stil)
    assert ansicht._cb_modify.isEnabled()
    assert ansicht._grp_modify.isHidden()
    assert "Farbkanal" in ansicht._cb_modify.toolTip()
    ansicht._cb_modify.setChecked(True)
    assert not ansicht._grp_modify.isHidden()
    assert ansicht._current.modify is True
    assert ansicht._current.modify_wirksam() is True
    assert ansicht._current._farb_modify() is True
    ansicht._modify_mode_combo.setCurrentIndex(
        ansicht._modify_mode_combo.findData("sub"))
    ansicht._modify_strength_spin.setValue(35)
    assert (ansicht._current.modify_mode,
            ansicht._current.modify_strength) == ("sub", 35)


@pytest.mark.parametrize("stil,weiss", [("RGB", False), ("RGBW", True)])
def test_hinweis_nennt_farbkanaele_und_den_dimmer(ansicht, stil, weiss):
    """Farbe und Dimmer bleiben getrennt — das steht im Hinweis der Gruppe."""
    ansicht._style_combo.setCurrentText(stil)
    ansicht._cb_modify.setChecked(True)
    text = ansicht._modify_hint.text()
    for wort in ("Farbkanal einzeln", "Rot, Grün, Blau", "gekappt",
                 "Der Dimmer wird nie angefasst", "dunkle Lampe bleibt dunkel",
                 "Farbrad", "Chaser-Schritt"):
        assert wort in text, wort
    assert ("Weiß" in text) is weiss
    # Der Dimmer-Hinweis („Min ueber 0") gehoert nicht in den Stil Farbe.
    ansicht._imin_spin.setValue(40)
    assert "Grundbetrag" not in ansicht._modify_hint.text()
    ansicht._style_combo.setCurrentText("Dimmer")
    assert "Grundbetrag" in ansicht._modify_hint.text()
    assert "Farbkanal" not in ansicht._modify_hint.text()


def test_stilwechsel_zwischen_dimmer_und_farbe_behaelt_den_haken(ansicht):
    ansicht._cb_modify.setChecked(True)
    for stil in ("RGBW", "Dimmer", "RGB"):
        ansicht._style_combo.setCurrentText(stil)
        assert ansicht._cb_modify.isEnabled() and ansicht._cb_modify.isChecked()
        assert not ansicht._grp_modify.isHidden()
        assert ansicht._current.modify_wirksam() is True


def test_shutter_bleibt_gesperrt_mit_verstaendlichem_hinweis(ansicht):
    ansicht._cb_modify.setChecked(True)
    ansicht._style_combo.setCurrentText("Shutter")
    assert not ansicht._cb_modify.isEnabled()
    assert ansicht._grp_modify.isHidden()
    assert ansicht._current.modify_wirksam() is False
    tip = ansicht._cb_modify.toolTip()
    for wort in ("„Dimmer“", "„RGB“", "„RGBW“", "Shutter", "Stellung",
                 "wirkt nicht"):
        assert wort in tip, wort
    assert "bisher nur" not in tip
    ansicht._style_combo.setCurrentText("RGB")
    assert ansicht._cb_modify.isEnabled()
    assert not ansicht._grp_modify.isHidden()


def test_speichern_und_wiederoeffnen_im_stil_farbe(ansicht):
    ansicht._style_combo.setCurrentText("RGBW")
    ansicht._cb_modify.setChecked(True)
    ansicht._modify_mode_combo.setCurrentIndex(
        ansicht._modify_mode_combo.findData("dim"))
    ansicht._modify_strength_spin.setValue(45)
    assert ansicht._dirty_lbl.text() != ""
    ansicht._save_edit()
    assert ansicht._dirty_lbl.text() == ""
    d = ansicht._saved.to_dict()
    assert (d["style"], d["modify"], d["modify_mode"], d["modify_strength"]) == (
        "RGBW", True, "dim", 45)
    ansicht._select(ansicht._list.currentRow())
    assert ansicht._dirty_lbl.text() == ""
    assert ansicht._style_combo.currentText() == "RGBW"
    assert ansicht._cb_modify.isChecked() and ansicht._cb_modify.isEnabled()
    assert not ansicht._grp_modify.isHidden()
    assert ansicht._modify_mode_combo.currentData() == "dim"
    assert ansicht._modify_strength_spin.value() == 45


def test_farb_matrix_ohne_haken_speichert_ohne_modify_schluessel(ansicht):
    ansicht._save_edit()
    assert not [k for k in ansicht._saved.to_dict() if k.startswith("modify")]


def test_vorschau_zeigt_im_stil_farbe_die_echte_farbe(ansicht):
    """Der Betrag eines Farb-Modify IST seine Farbe — die Vorschau faerbt sie
    nicht nach Betriebsart um (wie im Stil Dimmer), das Zeichen steht in der
    Ecke; Abdunkeln ist schraffiert."""
    from PySide6.QtGui import QColor, QImage
    from src.ui.views import rgb_matrix_view as V
    vorschau = [w for w in ansicht.findChildren(V.QWidget)
                if hasattr(w, "_grid") and hasattr(w, "_matrix")][0]
    vorschau.resize(320, 80)
    m = vorschau._matrix
    m.fixture_grid = list(range(1, m.cols * m.rows + 1))

    def farben():
        vorschau._grid = [(200, 40, 90)] * (m.cols * m.rows)
        img = QImage(vorschau.size(), QImage.Format.Format_RGB32)
        img.fill(QColor("#000000"))
        vorschau.render(img)
        y = vorschau.height() - 12
        return {(c.red(), c.green(), c.blue()) for c in
                (QColor(img.pixel(x, y))
                 for x in range(vorschau.width() // 2 - 12,
                                vorschau.width() // 2 + 12))}

    m.modify = False
    ohne = farben()
    assert (200, 40, 90) in ohne
    m.modify, m.modify_mode = True, "add"
    assert (200, 40, 90) in farben() and (255, 176, 0) not in farben()
    m.modify_mode = "sub"
    assert (200, 40, 90) in farben() and (64, 140, 255) not in farben()
    m.modify_mode = "dim"
    schraffiert = farben()
    assert (200, 40, 90) in schraffiert and (13, 17, 23) in schraffiert


# ── Schweif: gehoert zum Effekt, der Haken stellt ihn nicht um ───────────────

_SCHWEIF_SATZ = ("Bei einem Modify-Effekt zieht auch der Schweif die Veränderung "
                 "nach. Für einen scharfen Läufer den Schweif auf 0 % stellen.")


@pytest.mark.parametrize("stil", ["Dimmer", "RGB", "RGBW"])
def test_haken_laesst_den_schweif_stehen_und_weist_darauf_hin(ansicht, stil):
    """Entscheidung des Betreibers: der Schweif gehoert zum Effekt und wird mit
    verrechnet. Der Haken „Modify-Effekt" setzt ihn NICHT auf 0 % — weder im
    Feld noch im Effekt, weder beim Setzen noch beim Entfernen."""
    ansicht._style_combo.setCurrentText(stil)
    feld = ansicht._param_widgets["after_fade"]
    feld.setValue(45.0)
    assert ansicht._current.params["after_fade"] == 45.0
    assert _SCHWEIF_SATZ not in feld.toolTip()
    ohne = feld.toolTip()
    assert ohne, "Schweif-Feld hat seinen eigenen Tooltip verloren"

    ansicht._cb_modify.setChecked(True)
    feld = ansicht._param_widgets["after_fade"]
    assert feld.value() == 45.0
    assert ansicht._current.params["after_fade"] == 45.0
    assert feld.toolTip() == ohne + "\n" + _SCHWEIF_SATZ
    assert _SCHWEIF_SATZ in ansicht._cb_modify.toolTip()

    ansicht._cb_modify.setChecked(False)
    feld = ansicht._param_widgets["after_fade"]
    assert feld.value() == 45.0
    assert ansicht._current.params["after_fade"] == 45.0
    assert feld.toolTip() == ohne


def test_schweif_hinweis_ueberlebt_den_neuaufbau_der_felder(ansicht):
    """Das Schweif-Feld wird je Algorithmus/Bewegung neu gebaut — der Hinweis
    muss am NEUEN Feld wieder stehen, und im gesperrten Stil nicht."""
    from src.core.engine.rgb_matrix import RgbAlgorithm
    ansicht._cb_modify.setChecked(True)
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.WAVE.value)
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    assert _SCHWEIF_SATZ in ansicht._param_widgets["after_fade"].toolTip()
    ansicht._style_combo.setCurrentText("Shutter")
    feld = ansicht._param_widgets.get("after_fade")
    if feld is not None:
        assert _SCHWEIF_SATZ not in feld.toolTip()
    assert _SCHWEIF_SATZ not in ansicht._cb_modify.toolTip()


def test_schweif_wird_im_modify_mit_verrechnet(monkeypatch):
    """Engine-Seite derselben Entscheidung: hinter dem Laeufer bekommt die
    Lampe im Schweif einen ANTEIL ab, bei Schweif 0 % nichts."""
    import src.core.app_state as A
    from src.core.dmx.universe import Universe
    from src.core.engine.function_manager import FunctionManager
    from src.core.engine.rgb_matrix import (MatrixStyle, RgbAlgorithm,
                                             RgbMatrixInstance)

    class _Ch:
        default_value, ranges = 0, []

        def __init__(self, attribute, nr):
            self.attribute, self.channel_number = attribute, nr

    class _Fx:
        universe = 1

        def __init__(self, fid):
            self.fid, self.address = fid, 1 + (fid - 1) * 3

    kan = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kan)
    patch = [_Fx(i) for i in range(1, 9)]

    def rot_je_lampe(schweif):
        m = RgbMatrixInstance("mod", cols=8, rows=1,
                              fixture_grid=list(range(1, 9)),
                              algorithm=RgbAlgorithm.CHASE, color1=(255, 0, 0))
        m.style = MatrixStyle.RGB
        m.tempo_bus_id = ""
        m.matrix_speed = 0.0
        m.params.update({"runner_count": 1, "runner_width": 1,
                         "movement": "normal", "after_fade": schweif,
                         "offset": 4.0})
        m.modify, m.modify_mode = True, "add"
        fm = FunctionManager()
        fm.add(m)
        fm.start(m.id)
        u = Universe(1)
        fm.tick({1: u}, patch, 0.02)
        roh = u.get_all()
        return [roh[i * 3] for i in range(8)]

    scharf = rot_je_lampe(0.0)
    assert sorted(scharf) == [0] * 7 + [255], scharf
    weich = rot_je_lampe(60.0)
    assert max(weich) == 255
    assert any(0 < v < 255 for v in weich), (
        "kein Anteil im Schweif — der Schweif wird nicht mit verrechnet", weich)

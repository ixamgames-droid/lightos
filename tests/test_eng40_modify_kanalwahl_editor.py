"""ENG-40: Kanalwahl „Wirkt auf" in der Gruppe „Modify" des Matrix-Editors.

* Vorgabe ist „Kanäle der Modify-Farbe" (ENG-38, nichts wird gespeichert).
* Rot, Grün, Blau, Weiß, Amber und UV sind einzeln ankreuzbar; die Zeile gibt
  es nur in den Stilen RGB/RGBW bei gesetztem Haken „Modify-Effekt".
* Der Dimmer steht nicht in der Auswahl — der Hinweis nennt den Stil „Dimmer".
* Speichern, Wiederöffnen, Verwerfen und die Vorschau.

Die Felder sind FEST (nur ein-/ausgeblendet, STAB-38).
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
    a._save_edit()
    eigene = a._saved
    yield a
    try:
        from src.core.engine.function_manager import get_function_manager
        if eigene is not None:
            get_function_manager().remove(eigene.id)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


def _wahl(a):
    return tuple(k for k, cb in a._modify_kanal_cbs.items() if cb.isChecked())


def test_felder_tooltips_und_vorgabe(ansicht):
    from src.core.engine.modify import MODIFY_KANAELE
    a = ansicht
    assert tuple(a._modify_kanal_cbs) == MODIFY_KANAELE
    assert [cb.text() for cb in a._modify_kanal_cbs.values()] == [
        "Rot", "Grün", "Blau", "Weiß", "Amber", "UV"]
    assert a._modify_kanal_label.text() == "Wirkt auf:"
    assert a._cb_modify_standard.text() == "Kanäle der Modify-Farbe"
    assert a._cb_modify_standard.isChecked() and _wahl(a) == ()
    tip = a._cb_modify_standard.toolTip()
    for wort in ("Vorgabe", "Farbe des Modify-Effekts", "Weiß-Kanal",
                 "setzt die Auswahl zurück"):
        assert wort in tip, wort
    for k, cb in a._modify_kanal_cbs.items():
        t = cb.toolTip()
        for wort in (f"„{cb.text()}“", "Lampen ohne diesen Kanal bleiben "
                     "unberührt", "nichts auf andere Kanäle umgerechnet",
                     "Helligkeit des Effekts", "Stil „Dimmer“"):
            assert wort in t, (k, wort)
    # Kein Dimmer in der Auswahl — Farbe und Dimmer bleiben getrennt.
    assert not [cb for cb in a._modify_kanal_cbs.values()
                if "immer" in cb.text()]


@pytest.mark.parametrize("stil,sichtbar", [("RGB", True), ("RGBW", True),
                                          ("Dimmer", False)])
def test_zeile_nur_im_stil_farbe_bei_gesetztem_haken(ansicht, stil, sichtbar):
    a = ansicht
    a._style_combo.setCurrentText(stil)
    assert a._grp_modify.isHidden()          # ohne Haken: ganze Gruppe weg
    a._cb_modify.setChecked(True)
    assert not a._grp_modify.isHidden()
    assert a._modify_kanal_box.isHidden() is (not sichtbar)
    assert a._modify_kanal_label.isHidden() is (not sichtbar)
    a._style_combo.setCurrentText("Shutter")
    assert a._grp_modify.isHidden()


def test_ankreuzen_uebernimmt_und_vorgabe_haken_folgt(ansicht):
    a = ansicht
    a._cb_modify.setChecked(True)
    assert a._current.modify_channels == ()
    a._modify_kanal_cbs["w"].setChecked(True)
    assert a._current.modify_channels == ("w",)
    assert not a._cb_modify_standard.isChecked()
    a._modify_kanal_cbs["r"].setChecked(True)
    assert a._current.modify_channels == ("r", "w")      # feste Reihenfolge
    assert a._current._modify_kanalwahl() == frozenset({"color_r", "color_w"})
    assert a._dirty_lbl.text() != ""
    # Letzten Kanal abwaehlen -> Vorgabe steht wieder.
    a._modify_kanal_cbs["w"].setChecked(False)
    a._modify_kanal_cbs["r"].setChecked(False)
    assert a._cb_modify_standard.isChecked()
    assert a._current.modify_channels == ()


def test_vorgabe_haken_setzt_zurueck_und_laesst_sich_nicht_leer_abwaehlen(ansicht):
    a = ansicht
    a._cb_modify.setChecked(True)
    for k in ("g", "a", "uv"):
        a._modify_kanal_cbs[k].setChecked(True)
    assert a._current.modify_channels == ("g", "a", "uv")
    a._cb_modify_standard.setChecked(True)
    assert _wahl(a) == () and a._current.modify_channels == ()
    # Ohne angekreuzten Kanal gibt es nichts anderes als die Vorgabe.
    a._cb_modify_standard.setChecked(False)
    assert a._cb_modify_standard.isChecked()
    assert a._current.modify_channels == ()


def test_hinweis_nennt_auswahl_und_den_weg_zum_dimmer(ansicht):
    a = ansicht
    a._cb_modify.setChecked(True)
    vorgabe = a._modify_hint.text()
    assert "Stil „Dimmer“" in vorgabe and "Wirkt auf" in vorgabe
    assert "Farbkanal einzeln" in vorgabe
    a._modify_kanal_cbs["w"].setChecked(True)
    a._modify_kanal_cbs["r"].setChecked(True)
    text = a._modify_hint.text()
    for wort in ("Verändert nur: Rot, Weiß.", "Helligkeit des Effekts",
                 "Alle anderen Kanäle bleiben stehen",
                 "Lampen ohne einen angekreuzten Kanal bleiben unberührt",
                 "nichts umgerechnet", "Der Dimmer wird nie angefasst",
                 "Stil „Dimmer“", "Chaser-Schritt"):
        assert wort in text, wort
    assert "Farbkanal einzeln" not in text
    # Im Stil Dimmer bleibt die Auswahl gemerkt, der Hinweis ist der des Dimmers.
    a._style_combo.setCurrentText("Dimmer")
    assert "Verändert nur" not in a._modify_hint.text()
    assert a._current.modify_channels == ("r", "w")
    assert a._current._modify_kanalwahl() == frozenset()
    a._style_combo.setCurrentText("RGBW")
    assert _wahl(a) == ("r", "w")
    assert "Verändert nur: Rot, Weiß." in a._modify_hint.text()


def test_haken_modify_entfernen_behaelt_die_auswahl(ansicht):
    a = ansicht
    a._cb_modify.setChecked(True)
    a._modify_kanal_cbs["b"].setChecked(True)
    a._cb_modify.setChecked(False)
    assert a._current.modify is False
    assert a._current.modify_channels == ("b",)
    a._cb_modify.setChecked(True)
    assert _wahl(a) == ("b",) and not a._modify_kanal_box.isHidden()


def test_speichern_wiederoeffnen_und_verwerfen(ansicht):
    a = ansicht
    a._style_combo.setCurrentText("RGBW")
    a._cb_modify.setChecked(True)
    a._modify_mode_combo.setCurrentIndex(a._modify_mode_combo.findData("sub"))
    a._modify_kanal_cbs["w"].setChecked(True)
    assert a._btn_save.isEnabled()
    a._save_edit()
    assert a._dirty_lbl.text() == ""
    d = a._saved.to_dict()
    assert (d["modify"], d["modify_mode"], d["modify_channels"]) == (
        True, "sub", ["w"])
    # Wiederoeffnen: Felder stehen wie gespeichert, nichts gilt als geaendert.
    a._select(a._list.currentRow())
    assert a._dirty_lbl.text() == ""
    assert _wahl(a) == ("w",) and not a._cb_modify_standard.isChecked()
    # Aendern und VERWERFEN (Rueckgaengig wie bei den uebrigen Feldern).
    a._modify_kanal_cbs["r"].setChecked(True)
    a._modify_kanal_cbs["w"].setChecked(False)
    assert a._current.modify_channels == ("r",) and a._btn_reset.isEnabled()
    a._reset_edit()
    assert _wahl(a) == ("w",) and a._current.modify_channels == ("w",)
    assert a._dirty_lbl.text() == ""
    # Auswahl zuruecksetzen und speichern -> Schluessel verschwindet wieder.
    a._cb_modify_standard.setChecked(True)
    a._save_edit()
    assert "modify_channels" not in a._saved.to_dict()
    assert a._saved.modify_channels == ()


def test_matrix_ohne_auswahl_speichert_ohne_den_schluessel(ansicht):
    ansicht._cb_modify.setChecked(True)
    ansicht._save_edit()
    d = ansicht._saved.to_dict()
    assert d["modify"] is True and "modify_channels" not in d


def test_vorschau_zeigt_die_betroffenen_kanaele(ansicht):
    """Mit Kanalwahl malt die Vorschau die Zelle in der Mischfarbe der
    angekreuzten Kanaele (so hell wie der Betrag); in der Ecke stehen die
    Betriebsart und die Namen."""
    from PySide6.QtGui import QColor, QImage
    from src.ui.views import rgb_matrix_view as V
    assert V.modify_kanal_vorschaufarbe(("r",)) == (255, 0, 0)
    assert V.modify_kanal_vorschaufarbe(("r", "b")) == (255, 0, 255)
    assert V.modify_kanal_vorschaufarbe(("w",)) == (255, 255, 255)
    assert V.modify_kanal_vorschaufarbe(()) == (0, 0, 0)
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

    m.modify, m.modify_mode, m.modify_channels = True, "add", ()
    assert (200, 40, 90) in farben()
    assert vorschau.modify_eckentext() == "+"
    m.modify_channels = ("b",)
    assert (0, 0, 200) in farben() and (200, 40, 90) not in farben()
    assert vorschau.modify_eckentext() == "+ nur Blau"
    m.modify_channels = ("r", "w")
    m.modify_mode = "sub"
    assert (200, 200, 200) in farben()
    assert vorschau.modify_eckentext() == "− nur Rot, Weiß"
    m.modify_mode = "dim"
    schraffiert = farben()
    assert (200, 200, 200) in schraffiert and (13, 17, 23) in schraffiert
    assert vorschau.modify_eckentext() == "◐ nur Rot, Weiß"
    # Stil Dimmer: die Auswahl wirkt nicht und steht nicht in der Ecke.
    from src.core.engine.rgb_matrix import MatrixStyle
    m.style = MatrixStyle.DIMMER
    assert vorschau.modify_eckentext() == "◐"
    m.modify = False
    assert vorschau.modify_eckentext() == ""

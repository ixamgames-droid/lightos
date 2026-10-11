"""UI-78: der EFX-Editor im Programmer schneidet keine Texte ab.

Befund (DOC-60, Bild ``08_efx_verhaeltnis.png``): im Programmer stand im
Auswahlfeld „Gleichmäßig verteilt (Fächer“ und am Haken „jedes 2. Gerät
entgegengesetz“ — beide rechts abgeschnitten.

Ursache: die Formularspalte trug ``setMinimumWidth(280)``. Eine GESETZTE
Mindestbreite ersetzt in Qt die aus dem Inhalt berechnete; 280 lag darunter.
Neben der Vorschau (Verhaeltnis 2:3) bekam die Spalte im Programmer rund
320 px — und nach Abzug der Beschriftungen blieb fuer manches Feld weniger,
als sein Text braucht. Dasselbe Muster an den Knoepfen „+ Aufzeichnen…“ /
„Bearbeiten…“: die selbst gerechnete Mindestbreite lag unter ihrem Hinweis.

Jetzt: die Formulare brechen um (zu breite Felder rutschen unter ihre
Beschriftung), und die Spalte ist nie schmaler als ihr breitestes Feld — bei
sehr schmalem Fenster schiebt der aeussere Scrollbereich.

Der Test rechnet mit keiner festen Pixelzahl: er fragt jedes Bedienelement,
wie breit es fuer seinen Text sein muss, und vergleicht mit der Breite, die
es im Layout bekommt. Das gilt mit jeder Schrift — auch offscreen unter
Windows, wo jedes Zeichen so breit ist wie die Schrift hoch.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402
from PySide6.QtCore import QSize                       # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox,  # noqa: E402
                               QFormLayout, QLabel, QPushButton, QStyle,
                               QStyleOptionComboBox, QVBoxLayout, QWidget)

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

_app = QApplication.instance() or QApplication([])

# Breite der EFX-Seite im Programmer bei 1600 x 900 (Hauptfenster minus
# Seitenleiste und Geraeteliste) — dazu ein schmales und ein breites Fenster.
PROGRAMMER_BREITE = 1030
BREITEN = (700, PROGRAMMER_BREITE, 1400)


@pytest.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _editor(breite: int):
    """EFX-Editor wie im Programmer: eingebettet, mit dem Theme der App."""
    from src.core.paths import programm_datei
    from src.ui.views.efx_view import EfxView

    rahmen = QWidget()
    rahmen.setStyleSheet(
        Path(programm_datei("assets", "themes", "dark.qss")).read_text(encoding="utf-8"))
    lay = QVBoxLayout(rahmen)
    lay.setContentsMargins(0, 0, 0, 0)
    view = EfxView(follow_selection=True)
    lay.addWidget(view)
    rahmen.resize(breite, 560)
    rahmen.show()
    for _ in range(10):
        QApplication.processEvents()
    return rahmen, view


def _spalte(view) -> QWidget:
    """Die Formularspalte links neben der Vorschau."""
    oben = view._editor_body.layout().itemAt(0).layout()
    return oben.itemAt(0).widget()


def _auswahl_noetig(c: QComboBox) -> int:
    """Breite, die das Auswahlfeld fuer seinen LAENGSTEN Eintrag braucht."""
    opt = QStyleOptionComboBox()
    c.initStyleOption(opt)
    fm = c.fontMetrics()
    breiteste = max((fm.horizontalAdvance(c.itemText(i)) for i in range(c.count())),
                    default=0)
    return c.style().sizeFromContents(QStyle.ContentsType.CT_ComboBox, opt,
                                      QSize(breiteste, fm.height()), c).width()


def _zu_schmal(view) -> list[str]:
    """Alle sichtbaren Texte der Formularspalte, die nicht ganz hineinpassen."""
    spalte = _spalte(view)
    befund = []

    def pruefe(w, text, noetig):
        if w.isVisibleTo(spalte) and w.width() < noetig:
            befund.append(f"{type(w).__name__} {text!r}: {w.width()} px, braucht {noetig} px")

    for chk in spalte.findChildren(QCheckBox):
        pruefe(chk, chk.text(), chk.sizeHint().width())
    for btn in spalte.findChildren(QPushButton):
        # Nur Knoepfe mit Text; das Papierkorb-Zeichen hat eine feste Breite.
        if btn.minimumWidth() != btn.maximumWidth():
            pruefe(btn, btn.text(), btn.sizeHint().width())
    for lbl in spalte.findChildren(QLabel):
        if not lbl.wordWrap():
            pruefe(lbl, lbl.text(), lbl.sizeHint().width())
    for combo in spalte.findChildren(QComboBox):
        pruefe(combo, combo.currentText(), _auswahl_noetig(combo))
    return befund


@pytest.mark.parametrize("breite", BREITEN)
def test_alle_texte_der_formularspalte_sind_ganz_lesbar(breite):
    _rahmen, view = _editor(breite)
    befund = _zu_schmal(view)
    assert not befund, (
        f"EFX-Editor bei {breite} px Breite schneidet Texte ab:\n  " + "\n  ".join(befund))


def test_alle_texte_bleiben_beim_ziehen_des_fensters_lesbar():
    """Jede Breite, nicht nur drei: Qt entscheidet den Umbruch eines Feldes ohne
    den Abstand zur Beschriftung mitzurechnen. In dieser 4-px-Luecke blieb ein
    Feld neben der Beschriftung und war um den Abstand zu schmal (nachgemessen:
    Auswahlfeld „Algorithmus“ 166 statt 169 px)."""
    rahmen, view = _editor(640)
    befund: dict[str, int] = {}
    for breite in range(640, 1601, 2):
        rahmen.resize(breite, 560)
        QApplication.processEvents()
        for zeile in _zu_schmal(view):
            befund.setdefault(zeile.split(":")[0], breite)
    assert not befund, "abgeschnitten (Element: erste Fensterbreite):\n  " + "\n  ".join(
        f"{was}: ab {b} px" for was, b in befund.items())


def test_pfadname_des_benutzers_passt_ins_auswahlfeld():
    """Pfadnamen kommen NACH dem ersten Anzeigen dazu — das Feld muss mitwachsen."""
    rahmen, view = _editor(PROGRAMMER_BREITE)
    combo = view._path_combo
    combo.addItem("Welle langsam mit Schlenker")
    combo.setCurrentIndex(combo.count() - 1)
    for _ in range(5):
        QApplication.processEvents()
    assert combo.width() >= _auswahl_noetig(combo), (
        f"Pfad-Auswahl {combo.width()} px, der Name braucht {_auswahl_noetig(combo)} px")
    assert not _zu_schmal(view)


def test_die_gemeldeten_texte_sind_dabei():
    """Gegenprobe: die Pruefung sieht genau die Elemente aus dem Befund."""
    _rahmen, view = _editor(PROGRAMMER_BREITE)
    spalte = _spalte(view)
    assert view._counter_chk.text() == "jedes 2. Gerät entgegengesetzt"
    assert view._phase_mode_combo.findText("Gleichmäßig verteilt (Fächer)") >= 0
    for w in (view._counter_chk, view._mirror_chk, view._phase_mode_combo,
              view._tempo_bus_combo, view._btn_path_new, view._btn_path_edit):
        assert spalte.isAncestorOf(w)
        assert w.isVisibleTo(spalte)


@pytest.mark.parametrize("breite", BREITEN)
def test_spalte_ist_nie_schmaler_als_ihr_inhalt(breite):
    """Die Ursache selbst: keine gesetzte Mindestbreite UNTER der berechneten."""
    _rahmen, view = _editor(breite)
    spalte = _spalte(view)
    noetig = spalte.minimumSizeHint().width()
    assert spalte.width() >= noetig, (
        f"Formularspalte {spalte.width()} px, ihr Inhalt braucht {noetig} px")
    assert spalte.minimumWidth() in (0, noetig) or spalte.minimumWidth() >= noetig, (
        f"gesetzte Mindestbreite {spalte.minimumWidth()} px liegt unter dem Inhalt "
        f"({noetig} px) und ersetzt ihn")


def test_pfad_knoepfe_haben_keine_mindestbreite_unter_ihrem_hinweis():
    _rahmen, view = _editor(PROGRAMMER_BREITE)
    for btn in (view._btn_path_new, view._btn_path_edit):
        gesetzt = btn.minimumWidth()
        assert gesetzt == 0 or gesetzt >= btn.sizeHint().width(), (
            f"{btn.text()!r}: gesetzte Mindestbreite {gesetzt} px liegt unter dem "
            f"Hinweis {btn.sizeHint().width()} px — das Layout darf den Knopf quetschen")


def test_formulare_brechen_um_statt_die_spalte_zu_verbreitern():
    """Ohne Umbruch braeuchte die Spalte Beschriftung PLUS Feld nebeneinander —
    im Programmer waere dann die Vorschau der Verlierer oder es gaebe eine
    waagrechte Schiebeleiste. Mit Umbruch reicht das breiteste Feld."""
    _rahmen, view = _editor(PROGRAMMER_BREITE)
    formulare = _spalte(view).findChildren(QFormLayout)
    assert len(formulare) >= 5
    for f in formulare:
        assert f.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapLongRows


def test_umbruch_gibt_dem_feld_die_ganze_zeile():
    """Verhalten statt Einstellung: passt ein Feld nicht neben seine
    Beschriftung, steht es darunter und ist so breit wie sein Text."""
    _rahmen, view = _editor(700)
    combo = view._phase_mode_combo
    form = combo.parentWidget().layout()
    label = form.labelForField(combo)
    assert combo.width() >= _auswahl_noetig(combo)
    nebeneinander = label.geometry().right() < combo.geometry().left() and \
        abs(label.geometry().center().y() - combo.geometry().center().y()) < combo.height()
    if not nebeneinander:
        assert combo.geometry().top() >= label.geometry().bottom(), (
            "Feld steht weder neben noch unter seiner Beschriftung")

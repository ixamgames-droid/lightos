"""OSC-07: Im Dialog „OSC-Zuordnungen & Rückmeldung" (Reiter Eingang) sind die
Auswahl „Ziel" und der Platzhalter „Name oder Id" in „Funktion" ganz lesbar.

Befund von Sitzung D (Windows, 125/150 %): Die Spalte „Ziel" hatte 10 px
Textflaeche, „Executor-Fader" braucht 85 px; ``ResizeToContents`` mass vor
``setCellWidget`` nur den Kopftext. Wie NET-15 (#1138) kommt die Breite jetzt
aus dem sizeHint einer Mess-Combo mit allen Eintraegen.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionFrame, QWidget

from src.core.osc import osc_zuordnung as oz
from src.core.osc.osc_zuordnung import Konfig, Zuordnung

ROOT = Path(__file__).resolve().parents[1]
_app = QApplication.instance() or QApplication([])


def _platzhalter_flaeche(edit) -> int:
    """Textflaeche des Feldes, unabhaengig von der Hilfe im Dialog gemessen:
    Inhaltsrechteck des Stils abzueglich Textraender und des festen
    Innenrands von QLineEdit (2 px je Seite)."""
    opt = QStyleOptionFrame()
    edit.initStyleOption(opt)
    rect = edit.style().subElementRect(QStyle.SubElement.SE_LineEditContents, opt, edit)
    tm = edit.textMargins()
    return rect.width() - tm.left() - tm.right() - 4


def _pruefe(dlg, gezeigt=True):
    """``gezeigt=False``: Stand direkt nach dem Bau, bevor Qt die Spalten nach dem
    Zeigen nachmisst — das ist der Stand, den Sitzung D unter Windows sah
    (Funktion 75 px, Ziel nur der Kopftext). Dann zaehlt die Spaltenbreite."""
    from src.ui.widgets.osc_einstellungen_dialog import SP_BEREICH, SP_FKT, SP_ZIEL
    kopf = dlg.tabelle.horizontalHeader()
    rand = 1 if dlg.tabelle.showGrid() else 0
    assert dlg.tabelle.rowCount() >= 1
    for r in range(dlg.tabelle.rowCount()):
        for sp in (SP_ZIEL, SP_BEREICH):
            combo = dlg.tabelle.cellWidget(r, sp)
            combo.ensurePolished()
            noetig = combo.sizeHint().width()
            laengster = max(combo.fontMetrics().horizontalAdvance(combo.itemText(i))
                            for i in range(combo.count()))
            assert noetig > laengster
            assert kopf.sectionSize(sp) - rand >= noetig, (r, sp, kopf.sectionSize(sp), noetig)
            if gezeigt:
                assert combo.width() >= noetig, (r, sp, combo.width(), noetig)
        fkt = dlg.tabelle.cellWidget(r, SP_FKT)
        fkt.ensurePolished()
        if not gezeigt:
            fkt.resize(kopf.sectionSize(SP_FKT) - rand, fkt.sizeHint().height())
        text = fkt.fontMetrics().horizontalAdvance(fkt.placeholderText())
        assert fkt.placeholderText() == "Name oder Id"
        assert _platzhalter_flaeche(fkt) >= text, (r, _platzhalter_flaeche(fkt), text)


@pytest.mark.parametrize("px", [12, 15, 18])
@pytest.mark.parametrize("breite", [940, 520])
def test_ziel_und_funktion_ganz_lesbar(tmp_path, px, breite):
    from src.ui.widgets.osc_einstellungen_dialog import OscEinstellungenDialog
    pfad = str(tmp_path / "osc.json")
    oz.speichere_konfig(Konfig(zuordnungen=[
        Zuordnung("/exec/{n}/go", oz.ZIEL_GO)]), pfad)
    fenster = QWidget()
    # Wie in der App: Theme des Hauptfensters (12 px fest); groessere Schrift
    # (Windows-Textskalierung 125/150 %) ueber dieselbe Regel.
    fenster.setStyleSheet(
        (ROOT / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
        + f"\nQWidget {{ font-size: {px}px; }}\n")
    fenster.show()
    _app.processEvents()
    dlg = OscEinstellungenDialog(fenster, pfad=pfad, server_laeuft=True)
    try:
        _pruefe(dlg, gezeigt=False)
        dlg.resize(breite, 520)
        dlg.show()
        _app.processEvents()
        # wie der Bediener: Dialog offen, dann „+ Zuordnung"
        for ziel in (oz.ZIEL_FADER, oz.ZIEL_FKT_UMSCHALTEN):
            dlg.zeile_hinzu(Zuordnung("/a/{n}", ziel))
            _app.processEvents()
        _pruefe(dlg)
        kopf = dlg.tabelle.horizontalHeader()
        if kopf.length() > dlg.tabelle.viewport().width():
            # zu eng: waagerecht rollen statt abschneiden
            assert dlg.tabelle.horizontalScrollBar().maximum() > 0
    finally:
        oz.get_osc_zuordnung().lerne(None)
        oz.anwenden(Konfig())
        dlg.close()
        dlg.deleteLater()
        fenster.close()
        fenster.deleteLater()
        _app.processEvents()


@pytest.mark.parametrize("px", [12, 15, 18])
def test_funktion_eigene_feste_breite(tmp_path, px):
    """Gegenpruefung: „Funktion" darf nicht nur als Nebeneffekt der Ziel/Bereich-
    Breiten lesbar sein (ResizeToContents misst dann zufaellig nach). Die Spalte
    ist fest und mindestens so breit wie ein unabhaengig gemessenes Feld mit dem
    Platzhalter — direkt nach dem Bau, mit und ohne Zeile."""
    from PySide6.QtWidgets import QHeaderView, QLineEdit
    from src.ui.widgets.osc_einstellungen_dialog import OscEinstellungenDialog, SP_FKT
    pfad = str(tmp_path / "osc.json")
    oz.speichere_konfig(Konfig(zuordnungen=[]), pfad)
    fenster = QWidget()
    fenster.setStyleSheet(
        (ROOT / "assets" / "themes" / "dark.qss").read_text(encoding="utf-8")
        + f"\nQWidget {{ font-size: {px}px; }}\n")
    fenster.show()
    _app.processEvents()
    dlg = OscEinstellungenDialog(fenster, pfad=pfad, server_laeuft=True)
    try:
        kopf = dlg.tabelle.horizontalHeader()
        rand = 1 if dlg.tabelle.showGrid() else 0
        assert kopf.sectionResizeMode(SP_FKT) == QHeaderView.ResizeMode.Fixed
        probe = QLineEdit(dlg.tabelle)
        probe.setPlaceholderText("Name oder Id")
        probe.ensurePolished()
        probe.resize(kopf.sectionSize(SP_FKT) - rand, probe.sizeHint().height())
        text = probe.fontMetrics().horizontalAdvance(probe.placeholderText())
        assert _platzhalter_flaeche(probe) >= text, (px, kopf.sectionSize(SP_FKT), text)
        probe.deleteLater()
    finally:
        oz.get_osc_zuordnung().lerne(None)
        oz.anwenden(Konfig())
        dlg.close()
        dlg.deleteLater()
        fenster.close()
        fenster.deleteLater()
        _app.processEvents()

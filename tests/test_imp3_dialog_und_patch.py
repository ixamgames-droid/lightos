"""IMP-3, Teile 1 und 2: nummerierte Namen in Vorschau und Patch, der
Spaltenkopf „Tabelle“ und die Eingabetaste am Knopf „Tabellen-Import ▾“.

Echter ``AppState`` mit eigener Show-Datei unter ``tmp_path``, Dialog
offscreen.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                         # noqa: E402
from PySide6.QtGui import QColor                                      # noqa: E402
from PySide6.QtTest import QTest                                      # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

import src.core.app_state as A                                        # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402
from src.core import patch_tabelle as T                               # noqa: E402
from src.core.database.models import PatchedFixture                   # noqa: E402
from src.core.undo import get_undo_stack                              # noqa: E402
from src.ui.widgets import patch_import_dialog as D                   # noqa: E402

_app = QApplication.instance() or QApplication([])

PAR = "Stage Light ZQ01424"          # Generic, 8-Kanal RGBW


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture(scope="module")
def bib():
    return T.bibliothek_aus_db()


@pytest.fixture
def state(tmp_path):
    stack = get_undo_stack()
    stack.clear()
    st = A.AppState()
    st.open_show(str(tmp_path / "show.db"))
    yield st
    stack.clear()
    try:
        st._show_engine.dispose()
    except Exception:
        pass


def _von_hand(state, bib, name, adresse, fid=None):
    par = bib.finde("Generic", PAR).profil
    state.add_fixture(PatchedFixture(
        fid=fid or state.next_fid(), label=name, fixture_profile_id=par.id,
        mode_name="8-Kanal RGBW", universe=4, address=adresse, channel_count=8,
        manufacturer_name="Generic", fixture_name=PAR, fixture_type="par"),
        undoable=False)


def _text(*namen):
    return ("Name;Hersteller;Profil;Modus;Universum;Adresse\n"
            + "".join(f"{n};Generic;{PAR};8-Kanal RGBW;1;{1 + 8 * i}\n"
                      for i, n in enumerate(namen)))


def _dialog(state, bib, text):
    return D.PatchImportDialog(state, T.lies_tabelle(text), bib, "liste.csv")


def _namen(state):
    return [f.label for f in state.get_patched_fixtures()]


# ── Teil 1: Namen ────────────────────────────────────────────────────────────

def test_vorschau_zeigt_den_neuen_namen_und_den_vermerk(state, bib):
    _von_hand(state, bib, "PAR links", 100)
    dlg = _dialog(state, bib, _text("PAR links", "PAR links", "Solo"))
    name0, name2 = dlg._table.item(0, D.S_NAME), dlg._table.item(2, D.S_NAME)
    assert name0.text() == "PAR links 2"
    assert dlg._table.item(1, D.S_NAME).text() == "PAR links 3"
    assert dlg.status_text(0) == (
        "wird angelegt — Name gab es schon, heißt jetzt „PAR links 2“.")
    assert dlg.status_text(2) == "wird angelegt"
    # gut sichtbar: fett und in der Hinweisfarbe, der Tooltip nennt beide Namen
    assert name0.font().bold() and not name2.font().bold()
    assert name0.foreground().color() == QColor(D.FARBE_UMBENANNT)
    assert "„PAR links“ gab es schon — heißt jetzt „PAR links 2“." == name0.toolTip()
    assert dlg.zaehlerzeile() == (
        "3 Geräte werden angelegt (2 umbenannt, weil es den Namen schon gab)")


def test_anwenden_legt_unter_den_neuen_namen_an(state, bib):
    _von_hand(state, bib, "PAR links", 100)
    _von_hand(state, bib, "PAR links 2", 110)
    dlg = _dialog(state, bib, _text("PAR links", "PAR links", "Solo"))
    dlg._anwenden()
    assert _namen(state) == ["PAR links", "PAR links 2",
                             "PAR links 3", "PAR links 4", "Solo"]
    assert dlg.ergebnis.umbenannt == 2
    meldung = D.meldung_nach_import(dlg.ergebnis)
    assert "2 Geräte haben eine Nummer am Namen bekommen" in meldung
    # ein Rückgängig nimmt alle drei, die von Hand angelegten bleiben
    assert get_undo_stack().undo()
    assert _namen(state) == ["PAR links", "PAR links 2"]


def test_meldung_ohne_umbenannte_bleibt_wie_sie_war(state, bib):
    ergebnis = T.wende_an(state, T.baue_plan(T.lies_tabelle(_text("A", "B")), bib, []), bib)
    assert ergebnis.umbenannt == 0
    assert "Nummer am Namen" not in D.meldung_nach_import(ergebnis)
    eins = T.Ergebnis(fids=[1], zeilen=1, umbenannt=1)
    assert "1 Gerät hat eine Nummer am Namen bekommen" in D.meldung_nach_import(eins)


def test_name_der_zwischen_vorschau_und_anwenden_vergeben_wurde(state, bib):
    """wende_an rechnet gegen den JETZIGEN Patch neu — auch die Namen."""
    plan = T.baue_plan(T.lies_tabelle(_text("Front")), bib, T.belegung_aus_state(state))
    assert plan.zeilen[0].umbenannt == []
    _von_hand(state, bib, "Front", 100)
    ergebnis = T.wende_an(state, plan, bib)
    assert _namen(state) == ["Front", "Front 2"] and ergebnis.umbenannt == 1


def test_wahl_im_dialog_rechnet_die_namen_neu(state, bib):
    """Zeile 1 ist offen (kein Modus genannt) und belegt noch keinen Namen;
    nach der Wahl ist Zeile 1 die erste „Kopf“ und Zeile 2 bekommt die Nummer."""
    mh = "ZQ02001 Mini Moving Head"
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse\n"
            f"Kopf;U King;{mh};;1;1\n"
            f"Kopf;U King;{mh};11-Kanal;1;50\n")
    dlg = _dialog(state, bib, text)
    assert dlg._table.item(1, D.S_NAME).text() == "Kopf"
    assert not dlg._table.item(1, D.S_NAME).font().bold()
    box = dlg._auswahl[0]
    dlg.waehle(0, next(i for i in range(box.count())
                       if box.itemData(i) and box.itemData(i)[1] == "9-Kanal"))
    assert dlg._table.item(0, D.S_NAME).text() == "Kopf"
    assert dlg._table.item(1, D.S_NAME).text() == "Kopf 2"
    assert dlg._table.item(1, D.S_NAME).font().bold()
    assert "(1 umbenannt" in dlg.zaehlerzeile()


# ── Teil 2: Spaltenkopf ──────────────────────────────────────────────────────

def test_kein_spaltenkopf_ist_bei_900_px_beschnitten(state, bib):
    lang = "Ein ziemlich langer Gerätename für die linke Bühnenseite"
    dlg = _dialog(state, bib, _text(lang, lang, "Solo"))
    dlg.show()
    dlg.resize(900, 620)
    _app.processEvents()
    kopf = dlg._table.horizontalHeader()
    for spalte, titel in enumerate(D.SPALTEN):
        assert dlg._table.columnWidth(spalte) >= kopf.sectionSizeHint(spalte), titel
    assert dlg._table.columnWidth(D.S_STATUS) >= D.STATUS_MIN


def test_spaltenkopf_tabelle_ist_kurz_und_erklaert_sich_im_tooltip(state, bib):
    dlg = _dialog(state, bib, _text("A"))
    assert D.SPALTEN[D.S_TABELLE] == "Tabelle"
    for spalte in range(len(D.SPALTEN)):
        tipp = dlg._table.horizontalHeaderItem(spalte).toolTip()
        assert tipp.endswith(".") and len(tipp) > 15, D.SPALTEN[spalte]
    assert "in der Tabelle" in dlg._table.horizontalHeaderItem(D.S_TABELLE).toolTip()


# ── Teil 2: Tastatur am Knopf ────────────────────────────────────────────────

def test_eingabetaste_klappt_das_menue_des_import_knopfs_auf(state, monkeypatch):
    """Im Hauptfenster gehört die Leertaste dem Kürzel GO; der Knopf nimmt
    darum die Eingabetaste an (ein QPushButton tut das außerhalb eines Dialogs
    von sich aus nicht)."""
    import src.ui.views.patch_view as PV
    monkeypatch.setattr(PV, "get_state", lambda: state)
    view = PV.PatchView()
    knopf, menu = view._btn_import, view._btn_import.menu()
    view.show()
    _app.processEvents()
    try:
        for taste in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            assert not menu.isVisible()
            knopf.setFocus()
            QTest.keyClick(knopf, taste)
            _app.processEvents()
            assert menu.isVisible(), taste
            menu.hide()
            _app.processEvents()
        assert "Eingabetaste" in knopf.toolTip()
        assert "Leertaste" not in knopf.toolTip()
    finally:
        menu.hide()


def test_menueknopf_ohne_menue_laesst_die_eingabetaste_durch():
    from src.ui.widgets.menue_knopf import MenueKnopf
    knopf = MenueKnopf("Ohne")
    geklickt = []
    knopf.clicked.connect(lambda: geklickt.append(1))
    knopf.show()
    QTest.keyClick(knopf, Qt.Key.Key_Return)             # wirft nicht
    knopf.setAutoDefault(True)
    QTest.keyClick(knopf, Qt.Key.Key_Return)
    assert geklickt == [1]


def test_anleitung_verspricht_die_leertaste_nicht():
    from pathlib import Path
    wurzel = Path(__file__).resolve().parents[1]
    text = (wurzel / "docs" / "anleitung_patch_gruppen"
            / "ANLEITUNG_PATCH_GRUPPEN.md").read_text(encoding="utf-8")
    start = text.index("### Geräteliste aus einer Tabelle übernehmen")
    abschnitt = text[start:text.index("\n### ", start + 10)]
    assert "Eingabetaste" in abschnitt
    assert "heißt jetzt" in abschnitt and "umbenannt" in abschnitt
    for zeile in abschnitt.splitlines():
        if "Leertaste" in zeile:
            assert "GO" in zeile, zeile

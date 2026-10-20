"""IMP-4: Trifft eine Zeile des Tabellen-Imports mehrere Geräte, steht EIN
zusammengefasster Satz in der Status-Zelle (statt achtmal derselbe Satz), die
volle Liste im Tooltip — und die Zählerzeile zählt ZEILEN mit Überschneidungen.

Kern gegen eine kleine Test-Bibliothek; der Dialog offscreen gegen einen
echten ``AppState`` mit eigener Show-Datei unter ``tmp_path``.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.core import patch_tabelle as T                              # noqa: E402

PAR = T.Profil(1, "Eurolite", "LED PAR-56", "par", (T.Modus("4-Kanal", 4),))
GROSS = T.Profil(2, "Generic", "Grosse Leiste", "led_bar", (T.Modus("32-Kanal", 32),))

#: wie in der Demo-Show: acht PARs mit je 4 Kanälen auf Universum 1, Kanal 1–32
ACHT_PARS = [T.Belegung(f"PAR {n}", 1, 1 + (n - 1) * 4, 4) for n in range(1, 9)]


@pytest.fixture
def bib():
    return T.Bibliothek([PAR, GROSS])


def plan(text, bib, vorhandene=()):
    return T.baue_plan(T.lies_tabelle(text), bib, vorhandene)


def test_acht_vorhandene_werden_ein_satz(bib):
    p = plan("Name;Profil;Adresse\nLeiste;Grosse Leiste;1\n", bib, ACHT_PARS)
    z = p.zeilen[0]
    assert z.status == T.UEBERSCHNEIDUNG and z.geraete == []
    assert z.status_text == (
        "wird nicht angelegt — Überschneidet sich mit 8 vorhandenen Geräten: "
        "„PAR 1“ … „PAR 8“ (Universum 1, Kanal 1 bis 32).")
    assert z.status_text.count("Überschneidet") == 1
    # Tooltip: der Satz und darunter jedes Gerät einzeln
    tipp = z.status_tooltip
    assert tipp.startswith(z.status_text)
    for n in range(1, 9):
        von = 1 + (n - 1) * 4
        assert f"• „PAR {n}“ (Universum 1, Kanal {von} bis {von + 3})" in tipp
    assert p.zaehlerzeile() == "Kein Gerät wird angelegt, 1 Zeile mit Überschneidungen"


def test_reihenfolge_nach_adresse_nicht_nach_patch(bib):
    rueckwaerts = list(reversed(ACHT_PARS))
    z = plan("Profil;Adresse\nGrosse Leiste;1\n", bib, rueckwaerts).zeilen[0]
    assert "„PAR 1“ … „PAR 8“" in z.status_text


def test_zwei_und_drei_werden_aufgezaehlt(bib):
    zwei = plan("Profil;Adresse\nGrosse Leiste;29\n", bib, ACHT_PARS).zeilen[0]
    # Kanal 29–60 trifft PAR 8 (29–32) — nur eins: alter Satz bleibt
    assert "vorhandenen Gerät „PAR 8“ (Universum 1, Kanal 29 bis 32)" in zwei.status_text
    assert zwei.status_tooltip == zwei.status_text
    z = plan("Profil;Adresse\nLED PAR-56;3\n", bib, ACHT_PARS).zeilen[0]
    assert ("mit 2 vorhandenen Geräten: „PAR 1“ und „PAR 2“ "
            "(Universum 1, Kanal 1 bis 8).") in z.status_text
    da = ACHT_PARS[:3]
    z = plan("Profil;Modus;Adresse\nGrosse Leiste;32-Kanal;1\n", bib, da).zeilen[0]
    assert "„PAR 1“, „PAR 2“ und „PAR 3“ (Universum 1, Kanal 1 bis 12)" in z.status_text


def test_einzelner_treffer_unveraendert(bib):
    da = [T.Belegung("Alt", 1, 10, 4)]
    z = plan("Profil;Adresse\nLED PAR-56;9\n", bib, da).zeilen[0]
    assert z.status_text == ("wird nicht angelegt — Überschneidet sich mit dem "
                             "vorhandenen Gerät „Alt“ (Universum 1, Kanal 10 bis 13).")
    assert z.ueberschneidungen == []


def test_mehrere_tabellenzeilen_werden_zusammengefasst(bib):
    p = plan("Name;Profil;Adresse\n"
             "Gross;Grosse Leiste;1\n"
             "A;LED PAR-56;1\n"
             "B;LED PAR-56;5\n"
             "C;LED PAR-56;9\n"
             "D;LED PAR-56;13\n", bib)
    gross = p.zeilen[0]
    assert gross.status == T.UEBERSCHNEIDUNG
    assert "Überschneidet sich mit 4 Zeilen der Tabelle (3 … 6)." in gross.status_text
    assert "• Zeile 4 der Tabelle („B“)" in gross.status_tooltip
    assert p.zeilen[1].status_text.endswith("Überschneidet sich mit Zeile 2 der Tabelle („Gross“).")
    # fünf Zeilen betroffen — gezählt werden Zeilen
    assert p.zaehlerzeile() == "Kein Gerät wird angelegt, 5 Zeilen mit Überschneidungen"


def test_tabellenzeilen_mit_luecke_nennen_die_anzahl(bib):
    """Gegenprüfung: ab vier Zeilen erstes … letztes — die Anzahl muss dabei
    stehen, sonst liest sich „3 … 8“ wie ein lückenloser Bereich, obwohl die
    Zeilen 4 und 6 gar nicht betroffen sind."""
    p = plan("Name;Profil;Adresse\n"
             "Gross;Grosse Leiste;1\n"
             "A;LED PAR-56;1\n"
             "Weit 1;LED PAR-56;400\n"
             "B;LED PAR-56;9\n"
             "Weit 2;LED PAR-56;450\n"
             "C;LED PAR-56;17\n"
             "D;LED PAR-56;29\n", bib)
    gross = p.zeilen[0]
    assert gross.status == T.UEBERSCHNEIDUNG
    assert gross.status_text.endswith(
        "Überschneidet sich mit 4 Zeilen der Tabelle (3 … 8).")
    for nr in (3, 5, 7, 8):
        assert f"• Zeile {nr} der Tabelle" in gross.status_tooltip
    for nr in (4, 6):
        assert f"• Zeile {nr} der Tabelle" not in gross.status_tooltip


def test_vorhandene_und_tabellenzeile_zugleich(bib):
    p = plan("Name;Profil;Adresse\nGross;Grosse Leiste;1\nX;LED PAR-56;30\n",
             bib, ACHT_PARS[:2])
    g = p.zeilen[0]
    assert g.status_text.count("Überschneidet") == 2
    assert "mit 2 vorhandenen Geräten" in g.status_text
    assert "mit Zeile 3 der Tabelle („X“)" in g.status_text
    assert "• Zeile 3 der Tabelle („X“)" in g.status_tooltip


# ── Dialog ───────────────────────────────────────────────────────────────────

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def state(tmp_path):
    import src.core.app_state as A
    from src.core.undo import get_undo_stack
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
    from _qt_lifecycle import destroy_all_top_level_widgets
    destroy_all_top_level_widgets(QApplication.instance())


def test_dialog_status_zelle_und_tooltip(state, bib, monkeypatch):
    from src.ui.widgets import patch_import_dialog as D
    monkeypatch.setattr(T, "belegung_aus_state", lambda _st: list(ACHT_PARS))
    dlg = D.PatchImportDialog(
        state, T.lies_tabelle("Name;Profil;Adresse\nLeiste;Grosse Leiste;1\n"
                              "Frei;LED PAR-56;100\n"),
        bib, "liste.csv")
    assert dlg.status_text(0).count("Überschneidet") == 1
    assert "„PAR 1“ … „PAR 8“ (Universum 1, Kanal 1 bis 32)" in dlg.status_text(0)
    tipp = dlg.status_tooltip(0)
    assert all(f"„PAR {n}“ (Universum 1" in tipp for n in range(1, 9))
    assert dlg.status_tooltip(1) == dlg.status_text(1) == "wird angelegt"
    assert dlg.zaehlerzeile() == "1 Gerät wird angelegt, 1 Zeile mit Überschneidungen"

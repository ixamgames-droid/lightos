"""IMP-3, Teil 1: doppelte Namen werden beim Tabellen-Import nummeriert.

Reiner Kern (kein Qt, kein AppState): ``baue_plan`` gegen eine kleine
Bibliothek. Der Weg bis in den Patch und die Vorschau stehen in
``tests/test_imp3_dialog_und_patch.py``.
"""
from __future__ import annotations

import pytest

from src.core import patch_tabelle as T

DIM = T.Profil(3, "Generic", "Dimmer", "dimmer", (T.Modus("1-Kanal", 1),))


@pytest.fixture
def bib():
    return T.Bibliothek([DIM])


def plan(namen, bib, vorhandene=(), anzahl=None):
    zeilen = ["Name;Profil;Adresse;Anzahl"]
    adresse = 1
    for i, name in enumerate(namen):
        n = (anzahl or {}).get(i, 1)
        zeilen.append(f"{name};Dimmer;{adresse};{n}")
        adresse += n
    da = [T.Belegung(name, 9, 1 + i, 1) for i, name in enumerate(vorhandene)]
    return T.baue_plan(T.lies_tabelle("\n".join(zeilen) + "\n"), bib, da)


def namen(p):
    return [g.name for z in p.zeilen for g in z.geraete]


@pytest.mark.parametrize("name, belegt, erwartet", [
    ("PAR links", {"par links"}, "PAR links 2"),
    ("PAR links", {"par links", "par links 2"}, "PAR links 3"),
    ("PAR links", {"par links", "par links 3"}, "PAR links 2"),
    # abgesetzte Zahl = Zaehler: weiterzaehlen, nicht „PAR 3 2“
    ("PAR 3", {"par 3"}, "PAR 4"),
    ("PAR 3", {"par 3", "par 4", "par 5"}, "PAR 6"),
    ("Spot 01", {"spot 01"}, "Spot 02"),
    ("Spot 09", {"spot 09"}, "Spot 10"),
    # geklebte Zahl = Typbezeichnung: bleibt stehen
    ("PAR64", {"par64"}, "PAR64 2"),
    ("LED-PAR-56", {"led-par-56"}, "LED-PAR-56 2"),
    ("ZQ01424", {"zq01424"}, "ZQ01424 2"),
    # nur eine Zahl als Name
    ("7", {"7"}, "7 2"),
])
def test_naechster_freier_name(name, belegt, erwartet):
    assert T.naechster_freier_name(name, belegt) == erwartet


def test_mehrfach_in_der_tabelle_wird_durchnummeriert(bib):
    p = plan(["PAR links", "PAR links", "PAR links", "Einzeln"], bib)
    assert [z.status for z in p.zeilen] == [T.ANLEGBAR] * 4
    assert namen(p) == ["PAR links", "PAR links 2", "PAR links 3", "Einzeln"]
    assert p.zeilen[0].umbenannt == []
    assert p.zeilen[1].umbenannt == [("PAR links", "PAR links 2")]
    assert p.zeilen[1].status_text == (
        "wird angelegt — Name gab es schon, heißt jetzt „PAR links 2“.")
    assert p.zeilen[1].anzeige_name == "PAR links 2"
    assert p.zeilen[3].status_text == "wird angelegt"


def test_name_im_patch_vorhanden_naechste_freie_nummer(bib):
    p = plan(["PAR links", "par LINKS"], bib,
             vorhandene=["PAR links", "PAR links 2"])
    # Gross/Klein unterscheidet nicht; die Schreibweise der Tabelle bleibt
    assert namen(p) == ["PAR links 3", "par LINKS 4"]
    assert "heißt jetzt „PAR links 3“" in p.zeilen[0].status_text


def test_ausdruecklicher_name_weiter_unten_behaelt_seinen_platz(bib):
    """Erst behalten alle noch freien Namen ihren Platz, dann wird nummeriert:
    das zweite „PAR“ darf dem ausdruecklichen „PAR 2“ den Namen nicht nehmen."""
    p = plan(["PAR", "PAR", "PAR 2"], bib)
    assert namen(p) == ["PAR", "PAR 3", "PAR 2"]
    assert p.zeilen[2].umbenannt == []


def test_anzahl_zeile_gegen_vorhandene_nummern(bib):
    p = plan(["PAR"], bib, vorhandene=["PAR 1", "PAR 2"], anzahl={0: 3})
    assert namen(p) == ["PAR 4", "PAR 5", "PAR 3"]
    z = p.zeilen[0]
    assert len(z.umbenannt) == 2
    assert z.status_text == ("wird angelegt (3 Geräte) — 2 Namen gab es schon, "
                             "die Geräte heißen jetzt „PAR 4“ und „PAR 5“.")
    assert z.anzeige_name == "PAR 4 … PAR 3"


def test_alle_namen_sind_am_ende_verschieden(bib):
    p = plan(["A", "a", "A 2", "A", "A 3", "B 9", "B 9", "B 10"], bib,
             vorhandene=["A", "A 4"])
    alle = [n.casefold() for n in namen(p)] + ["a", "a 4"]
    assert len(set(alle)) == len(alle), namen(p)


def test_zeile_die_nicht_angelegt_wird_belegt_keinen_namen(bib):
    """Eine Zeile mit Fehler reserviert ihren Namen nicht."""
    text = "Name;Profil;Adresse\nPAR;Dimmer;999\nPAR;Dimmer;2\n"
    p = T.baue_plan(T.lies_tabelle(text), bib, [])
    assert [z.status for z in p.zeilen] == [T.FEHLER, T.ANLEGBAR]
    assert p.zeilen[1].geraete[0].name == "PAR" and p.zeilen[1].umbenannt == []
    assert p.zeilen[0].anzeige_name == "PAR"


def test_zaehlerzeile_nennt_die_umbenannten(bib):
    p = plan(["PAR", "PAR", "PAR", "Solo"], bib)
    assert p.zaehler()["umbenannt"] == 2
    assert p.zaehlerzeile() == (
        "4 Geräte werden angelegt (2 umbenannt, weil es den Namen schon gab)")
    assert "umbenannt" not in plan(["A", "B"], bib).zaehlerzeile()


def test_neu_rechnen_zaehlt_nicht_doppelt(bib):
    """``baue_plan`` rechnet bei jeder Wahl neu — Namen wandern dabei nicht."""
    a = plan(["PAR", "PAR"], bib)
    b = T.baue_plan(a.tabelle, bib, [], a.wahl)
    assert namen(a) == namen(b) == ["PAR", "PAR 2"]

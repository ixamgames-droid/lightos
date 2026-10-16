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
    # aufsteigend wie die Adressen — nicht „PAR 4, PAR 5, PAR 3“
    assert namen(p) == ["PAR 3", "PAR 4", "PAR 5"]
    z = p.zeilen[0]
    assert len(z.umbenannt) == 3
    assert z.status_text == ("wird angelegt (3 Geräte) — 3 Namen gab es schon, "
                             "die Geräte heißen jetzt „PAR 3“, „PAR 4“ und „PAR 5“.")
    assert z.anzeige_name == "PAR 3 … PAR 5"


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


# ── Gegenprüfung ─────────────────────────────────────────────────────────────

def _eindeutig(p, vorhandene=()):
    alle = [T.namens_schluessel(n) for n in namen(p)]
    alle += [T.namens_schluessel(n) for n in vorhandene]
    assert len(set(alle)) == len(alle), namen(p)


def test_name_der_erst_durch_die_nummer_kollidiert(bib):
    """„PAR 2“ gibt es schon, „PAR“ steht doppelt: das zweite darf nicht
    „PAR 2“ werden."""
    p = plan(["PAR", "PAR"], bib, vorhandene=["PAR 2"])
    assert namen(p) == ["PAR", "PAR 3"]
    # … und wenn die Kollision aus der Tabelle selbst kommt, in jeder Reihenfolge
    assert namen(plan(["PAR 2", "PAR", "PAR"], bib)) == ["PAR 2", "PAR", "PAR 3"]
    assert namen(plan(["PAR", "PAR", "PAR 2", "PAR 3"], bib)) == [
        "PAR", "PAR 4", "PAR 2", "PAR 3"]
    # weitergezählte Nummer trifft eine vergebene: „PAR 3“ doppelt, „PAR 4“ da
    p = plan(["PAR 3", "PAR 3"], bib, vorhandene=["par 4"])
    assert namen(p) == ["PAR 3", "PAR 5"]


def test_leerzeichen_und_gross_klein_unterscheiden_zwei_namen_nicht(bib):
    vorhandene = ["PAR  links ", " Spot"]
    p = plan(["par LINKS", "PAR links", "SPOT", "Spot  2"], bib, vorhandene=vorhandene)
    assert namen(p) == ["par LINKS 2", "PAR links 3", "SPOT 3", "Spot  2"]
    _eindeutig(p, vorhandene)
    assert T.namens_schluessel("  PAR   Links ") == "par links"


def test_ziffern_am_ende(bib):
    p = plan(["Spot 09", "Spot 09", "Spot 99", "Spot 99", "PAR64", "PAR64",
              "7", "7", "LED 007", "LED 007"], bib)
    assert namen(p) == ["Spot 09", "Spot 10", "Spot 99", "Spot 100",
                        "PAR64", "PAR64 2", "7", "7 2", "LED 007", "LED 008"]
    _eindeutig(p)


def test_ausdruecklicher_name_geht_vor_die_nummern_einer_anzahl_zeile(bib):
    """Die Zeile mit Anzahl erzeugt „PAR 1 … PAR 3“ selbst; ein ausdrücklich
    so genanntes „PAR 2“ (auch weiter unten) behält seinen Namen, die Zeile
    zählt aufsteigend um es herum."""
    p = plan(["PAR", "PAR 2"], bib, anzahl={0: 3})
    assert namen(p) == ["PAR 1", "PAR 3", "PAR 4", "PAR 2"]
    assert p.zeilen[1].umbenannt == []
    # ohne Kollision bleibt die Zeile, wie sie ist
    q = plan(["PAR", "Solo"], bib, anzahl={0: 3})
    assert namen(q) == ["PAR 1", "PAR 2", "PAR 3", "Solo"]
    assert q.zeilen[0].umbenannt == [] and q.zeilen[0].anzeige_name == "PAR"


def test_zwei_anzahl_zeilen_mit_demselben_namen_zaehlen_durch(bib):
    p = plan(["PAR", "PAR"], bib, anzahl={0: 3, 1: 3})
    assert namen(p) == ["PAR 1", "PAR 2", "PAR 3", "PAR 4", "PAR 5", "PAR 6"]


def test_sehr_viele_dubletten_bleiben_eindeutig_und_schnell(bib):
    import time
    viele = T.Bibliothek([DIM])
    zeilen = ["Name;Profil;Universum;Adresse"]
    for i in range(3000):
        zeilen.append(f"PAR;Dimmer;{1 + i // 500};{1 + i % 500}")
    tabelle = T.lies_tabelle("\n".join(zeilen) + "\n")
    t0 = time.perf_counter()
    p = T.baue_plan(tabelle, viele, [T.Belegung("PAR 2", 60, 1, 1)])
    dauer = time.perf_counter() - t0
    assert all(z.status == T.ANLEGBAR for z in p.zeilen)
    n = namen(p)
    assert n[:3] == ["PAR", "PAR 3", "PAR 4"] and n[-1] == "PAR 3001"
    _eindeutig(p, ["PAR 2"])
    assert dauer < 5.0, dauer


def test_merker_ueberspringt_keine_freie_nummer():
    belegt = {"par", "par 2", "par 3", "par 7"}
    merker: dict = {}
    eins = T.naechster_freier_name("PAR", belegt, merker)
    belegt.add(T.namens_schluessel(eins))
    zwei = T.naechster_freier_name("PAR 6", belegt, merker)      # anderer Start
    belegt.add(T.namens_schluessel(zwei))
    drei = T.naechster_freier_name("PAR", belegt, merker)
    assert (eins, zwei, drei) == ("PAR 4", "PAR 8", "PAR 5")

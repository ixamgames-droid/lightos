"""IMP-1: Patch aus einer Tabelle — der Kern ohne Qt.

Lesen (Trennzeichen, Kodierung, Kopfzeile, Adress-Schreibweisen), Zuordnen
(exakt, eindeutig ohne Groß/Klein, mehrdeutig und unbekannt bleiben offen)
und alle Prüfungen. Die Bibliothek ist hier eine kleine, handgebaute Liste —
gegen die echte Bibliothek und einen echten AppState prüft
``test_imp1_patch_tabelle_anwenden.py``.
"""
from __future__ import annotations

import pytest

from src.core import patch_tabelle as T

PAR = T.Profil(1, "Eurolite", "LED PAR-56", "par",
               (T.Modus("3-Kanal RGB", 3), T.Modus("5-Kanal", 5)))
MH = T.Profil(2, "U King", "Mini Moving Head", "moving_head",
              (T.Modus("11-Kanal", 11), T.Modus("9-Kanal", 9)))
DIM = T.Profil(3, "Generic", "Dimmer", "dimmer", (T.Modus("1-Kanal", 1),))
# Derselbe Modellname bei zwei Herstellern:
BAR_A = T.Profil(4, "ADJ", "LED Bar", "led_bar", (T.Modus("Standard", 6),))
BAR_B = T.Profil(5, "Stairville", "LED Bar", "led_bar", (T.Modus("Standard", 8),))
# Zwei Profile, die sich nur in Groß/Klein unterscheiden:
FOG_A = T.Profil(6, "Generic", "Nebel N10", "hazer", (T.Modus("1-Kanal", 1),))
FOG_B = T.Profil(7, "Generic", "NEBEL N10", "hazer", (T.Modus("1-Kanal", 1),))


@pytest.fixture
def bib():
    return T.Bibliothek([PAR, MH, DIM, BAR_A, BAR_B, FOG_A, FOG_B])


def plan(text, bib, vorhandene=(), wahl=None):
    return T.baue_plan(T.lies_tabelle(text), bib, vorhandene, wahl)


# ── Lesen: Trennzeichen ──────────────────────────────────────────────────────

@pytest.mark.parametrize("zeichen", [";", ",", "\t"])
def test_trennzeichen_wird_erkannt(zeichen):
    text = zeichen.join(["Name", "Profil", "Universum", "Adresse"]) + "\n" \
        + zeichen.join(["Front", "Dimmer", "2", "17"]) + "\n"
    tab = T.lies_tabelle(text)
    assert tab.fehler == ""
    assert tab.trennzeichen == zeichen
    z = tab.zeilen[0]
    assert (z.name, z.profil, z.universum, z.adresse) == ("Front", "Dimmer", 2, 17)


def test_komma_im_namen_kippt_keine_semikolon_tabelle():
    tab = T.lies_tabelle("Name;Profil;Adresse\nPAR, links;Dimmer;1\nPAR, rechts;Dimmer;2\n")
    assert tab.trennzeichen == ";"
    assert [z.name for z in tab.zeilen] == ["PAR, links", "PAR, rechts"]


def test_anfuehrungszeichen_schuetzen_das_trennzeichen():
    tab = T.lies_tabelle('Name,Profil,Adresse\n"PAR, links",Dimmer,1\n')
    assert tab.trennzeichen == ","
    assert tab.zeilen[0].name == "PAR, links"


def test_sep_zeile_eines_tabellenprogramms():
    tab = T.lies_tabelle("sep=;\nName;Profil;Adresse\nA;Dimmer;5\n")
    assert tab.fehler == ""
    assert tab.zeilen[0].adresse == 5
    assert tab.zeilen[0].nr == 3            # Zeilennummer wie in der Datei


# ── Lesen: Kodierung ─────────────────────────────────────────────────────────

TEXT_UMLAUT = "Name;Profil;Adresse\nBühne rechts;Dimmer;1\n"


@pytest.mark.parametrize("daten, kodierung", [
    (TEXT_UMLAUT.encode("utf-8"), "UTF-8"),
    (b"\xef\xbb\xbf" + TEXT_UMLAUT.encode("utf-8"), "UTF-8 (mit BOM)"),
    (TEXT_UMLAUT.encode("cp1252"), "Windows-1252"),
    (TEXT_UMLAUT.encode("utf-16"), "UTF-16"),
])
def test_kodierung(tmp_path, daten, kodierung):
    pfad = tmp_path / "liste.csv"
    pfad.write_bytes(daten)
    tab = T.lies_datei(str(pfad))
    assert tab.fehler == ""
    assert tab.kodierung == kodierung
    assert tab.zeilen[0].name == "Bühne rechts"
    assert tab.spalten[T.NAME] == 0         # BOM klebt nicht am ersten Spaltennamen


def test_datei_fehlt_und_xlsx_werden_zu_einem_satz(tmp_path):
    assert "nicht öffnen" in T.lies_datei(str(tmp_path / "gibtsnicht.csv")).fehler
    xlsx = tmp_path / "liste.xlsx"
    xlsx.write_bytes(b"PK\x03\x04irgendwas")
    assert "CSV" in T.lies_datei(str(xlsx)).fehler


# ── Lesen: Kopfzeile und Spalten ─────────────────────────────────────────────

def test_spaltennamen_deutsch_und_englisch():
    de = T.lies_tabelle("Bezeichnung;Hersteller;Gerät;Modus;Univ.;DMX-Adresse;Anzahl;Kanäle\n"
                        "A;Eurolite;LED PAR-56;5-Kanal;2;10;3;5\n")
    en = T.lies_tabelle("Label,Manufacturer,Fixture,Mode,Universe,Address,Count,Channels\n"
                        "A,Eurolite,LED PAR-56,5-Kanal,2,10,3,5\n")
    for tab in (de, en):
        assert tab.fehler == "" and tab.kopfzeile
        z = tab.zeilen[0]
        assert (z.name, z.hersteller, z.profil, z.modus) == \
            ("A", "Eurolite", "LED PAR-56", "5-Kanal")
        assert (z.universum, z.adresse, z.anzahl, z.kanaele) == (2, 10, 3, 5)


def test_spalten_in_beliebiger_reihenfolge_und_unbekannte_spalte():
    tab = T.lies_tabelle("Adresse;Bemerkung;Modell;Name\n7;hinten;Dimmer;Rampe\n")
    z = tab.zeilen[0]
    assert (z.adresse, z.profil, z.name) == (7, "Dimmer", "Rampe")
    assert any("Bemerkung" in h for h in tab.hinweise)


def test_fehlende_pflichtspalte_ist_ein_fehler_der_ganzen_tabelle():
    tab = T.lies_tabelle("Name;Profil;Universum\nA;Dimmer;1\n")
    assert "„Adresse“" in tab.fehler and tab.zeilen == []
    tab = T.lies_tabelle("Name;Adresse\nA;1\n")
    assert "„Profil“" in tab.fehler


def test_optionale_spalten_duerfen_fehlen(bib):
    p = plan("Profil;Adresse\nDimmer;9\n", bib)
    z = p.zeilen[0]
    assert z.status == T.ANLEGBAR
    assert z.geraete == [T.Geraet("Dimmer", 1, 9, 1)]   # Name = Profil, Universum 1


def test_ohne_kopfzeile_vier_und_drei_spalten():
    tab = T.lies_tabelle("Front;Dimmer;2;17\nBack;Dimmer;2;18\n")
    assert not tab.kopfzeile and tab.fehler == ""
    assert [(z.name, z.universum, z.adresse) for z in tab.zeilen] == \
        [("Front", 2, 17), ("Back", 2, 18)]
    assert any("Keine Kopfzeile" in h for h in tab.hinweise)
    tab = T.lies_tabelle("Front;Dimmer;2.17\n")
    assert (tab.zeilen[0].universum, tab.zeilen[0].adresse) == (2, 17)


def test_ohne_kopfzeile_und_unklare_spaltenzahl_wird_abgelehnt():
    tab = T.lies_tabelle("Front;Eurolite;Dimmer;8ch;2;17\n")
    assert "Kopfzeile" in tab.fehler and tab.zeilen == []


def test_leerzeilen_und_kommentare_werden_uebersprungen():
    tab = T.lies_tabelle("\n\nName;Profil;Adresse\n\n;;\nA;Dimmer;1\n# später\n\nB;Dimmer;2\n\n")
    assert [z.name for z in tab.zeilen] == ["A", "B"]
    assert [z.nr for z in tab.zeilen] == [6, 9]


def test_leere_tabelle_und_nur_kopfzeile():
    assert "leer" in T.lies_tabelle("  \n\n").fehler
    assert "keine Geräte" in T.lies_tabelle("Name;Profil;Adresse\n").fehler


# ── Lesen: Adresse und Universum ─────────────────────────────────────────────

@pytest.mark.parametrize("zelle, erwartet", [
    ("101", (None, 101)), ("2.101", (2, 101)), ("2/101", (2, 101)),
    ("2:101", (2, 101)), (" 3 / 7 ", (3, 7)),
])
def test_adress_schreibweisen(zelle, erwartet):
    z = T.lies_tabelle(f"Profil;Adresse\nDimmer;{zelle}\n").zeilen[0]
    assert (z.universum, z.adresse) == erwartet and z.fehler == []


@pytest.mark.parametrize("zelle", ["", "abc", "1,5", "2.101.3", "-4"])
def test_unlesbare_adresse_ist_ein_zeilenfehler(zelle, bib):
    p = plan(f"Profil\tAdresse\nDimmer\t{zelle}\n", bib)
    assert p.zeilen[0].status == T.FEHLER
    assert "Adresse" in p.zeilen[0].status_text


def test_universum_spalte_und_punkt_schreibweise():
    z = T.lies_tabelle("Profil;Universum;Adresse\nDimmer;U3;4\n").zeilen[0]
    assert z.universum == 3
    z = T.lies_tabelle("Profil;Universum;Adresse\nDimmer;2;2.101\n").zeilen[0]
    assert (z.universum, z.adresse, z.fehler) == (2, 101, [])
    z = T.lies_tabelle("Profil;Universum;Adresse\nDimmer;1;2.101\n").zeilen[0]
    assert z.fehler and "widerspricht" in z.fehler[0]


# ── Zuordnung ────────────────────────────────────────────────────────────────

def test_exakter_treffer(bib):
    f = bib.finde("Eurolite", "LED PAR-56")
    assert (f.profil, f.art) == (PAR, T.EXAKT)
    assert bib.finde("", "LED PAR-56").profil is PAR
    assert bib.finde("", "Eurolite LED PAR-56").profil is PAR   # Hersteller im Namen


def test_eindeutig_ohne_gross_klein_und_leerzeichen(bib):
    f = bib.finde("eurolite", " led  par-56 ")
    assert (f.profil, f.art) == (PAR, T.UNSCHARF)
    assert bib.finde("", "LEDPAR-56").profil is PAR
    assert bib.finde("", "minimovinghead").art == T.UNSCHARF


def test_unscharfer_treffer_steht_als_hinweis_in_der_zeile(bib):
    p = plan("Profil;Modus;Adresse\nled par-56;5-Kanal;1\n", bib)
    assert p.zeilen[0].status == T.ANLEGBAR
    assert "Groß-/Kleinschreibung" in p.zeilen[0].status_text


def test_nur_aehnlich_bleibt_offen_mit_vorschlag(bib):
    f = bib.finde("", "LED PAR 56")          # Leerzeichen statt Bindestrich
    assert f.profil is None and f.art == T.OFFEN
    assert f.vorschlaege and f.vorschlaege[0] is PAR
    f = bib.finde("", "Moving Head")         # Teil eines Namens
    assert f.profil is None and MH in f.vorschlaege


def test_mehrdeutig_bleibt_offen(bib):
    f = bib.finde("", "LED Bar")             # zwei Hersteller
    assert f.profil is None and set(f.vorschlaege) == {BAR_A, BAR_B}
    assert "verschiedene Hersteller" in f.grund
    assert bib.finde("Stairville", "LED Bar").profil is BAR_B   # mit Hersteller eindeutig
    f = bib.finde("", "nebel n10")           # zwei Profile, nur Groß/Klein verschieden
    assert f.profil is None and set(f.vorschlaege) == {FOG_A, FOG_B}
    assert bib.finde("", "NEBEL N10").profil is FOG_B           # exakt geht vor


def test_falscher_hersteller_ist_kein_treffer(bib):
    f = bib.finde("Cameo", "LED PAR-56")
    assert f.profil is None and PAR in f.vorschlaege


def test_unbekannt_bleibt_offen_ohne_vorschlag(bib):
    f = bib.finde("", "Quantum Wash XJ9000")
    assert f.profil is None and f.vorschlaege == ()
    assert "kein ähnliches" in f.grund
    p = plan("Profil;Adresse\nQuantum Wash XJ9000;1\n", bib)
    assert p.zeilen[0].status == T.OFFEN and p.anlegbare() == []


def test_offene_zeile_wird_nie_angelegt_auch_nicht_mit_bestem_vorschlag(bib):
    p = plan("Profil;Adresse\nLED PAR 56;1\n", bib)
    z = p.zeilen[0]
    assert z.status == T.OFFEN and z.profil is None and z.geraete == []
    assert z.status_text.startswith("offen — ")


def test_modus_exakt_lose_und_ueber_kanalzahl():
    assert T.finde_modus(PAR, "5-Kanal")[0].kanaele == 5
    assert T.finde_modus(PAR, "3-kanal rgb")[0].kanaele == 3
    assert T.finde_modus(MH, "9ch")[0].name == "9-Kanal"
    assert T.finde_modus(MH, "11 Kanäle")[0].name == "11-Kanal"
    assert T.finde_modus(MH, "", kanaele=9)[0].name == "9-Kanal"
    assert T.finde_modus(DIM)[0].name == "1-Kanal"      # nur ein Modus


def test_modus_fehlt_oder_unbekannt_bleibt_offen(bib):
    modus, grund = T.finde_modus(PAR)
    assert modus is None and "2 Modi" in grund          # nie „der erste“
    modus, grund = T.finde_modus(PAR, "Turbo")
    assert modus is None and "„Turbo“" in grund
    assert T.finde_modus(PAR, "", kanaele=7)[0] is None
    p = plan("Profil;Adresse\nLED PAR-56;1\n", bib)
    assert p.zeilen[0].status == T.OFFEN and p.zeilen[0].profil is PAR


def test_wahl_macht_eine_offene_zeile_anlegbar(bib):
    text = "Name;Profil;Adresse\nA;LED PAR 56;1\nB;LED PAR-56;10\n"
    assert [z.status for z in plan(text, bib).zeilen] == [T.OFFEN, T.OFFEN]
    p = plan(text, bib, wahl={0: (PAR.id, "5-Kanal"), 1: (PAR.id, "3-Kanal RGB")})
    assert [z.status for z in p.zeilen] == [T.ANLEGBAR, T.ANLEGBAR]
    assert [z.kanaele for z in p.zeilen] == [5, 3]
    assert p.zeilen[0].art == T.GEWAEHLT


def test_wahl_die_es_nicht_gibt_zaehlt_nicht(bib):
    p = plan("Profil;Adresse\nLED PAR 56;1\n", bib, wahl={0: (999, "x")})
    assert p.zeilen[0].status == T.OFFEN
    p = plan("Profil;Adresse\nLED PAR 56;1\n", bib, wahl={0: (PAR.id, "gibt es nicht")})
    assert p.zeilen[0].status == T.OFFEN


# ── Prüfungen ────────────────────────────────────────────────────────────────

def test_anzahl_mit_fortlaufender_adresse(bib):
    p = plan("Name;Profil;Modus;Universum;Adresse;Anzahl\nPAR;LED PAR-56;5-Kanal;2;11;4\n", bib)
    z = p.zeilen[0]
    assert z.status == T.ANLEGBAR
    assert [(g.name, g.universum, g.adresse) for g in z.geraete] == \
        [("PAR 1", 2, 11), ("PAR 2", 2, 16), ("PAR 3", 2, 21), ("PAR 4", 2, 26)]
    assert "4 Geräte" in z.status_text
    assert p.zaehler()["geraete"] == 4


@pytest.mark.parametrize("anzahl", ["0", "x", "-2", "9999"])
def test_anzahl_ungueltig(anzahl, bib):
    p = plan(f"Profil;Adresse;Anzahl\nDimmer;1;{anzahl}\n", bib)
    assert p.zeilen[0].status == T.FEHLER and "Anzahl" in p.zeilen[0].status_text


@pytest.mark.parametrize("adresse", ["0", "513", "1000"])
def test_adresse_ausserhalb_1_bis_512(adresse, bib):
    p = plan(f"Profil;Adresse\nDimmer;{adresse}\n", bib)
    assert p.zeilen[0].status == T.FEHLER
    assert "1 bis 512" in p.zeilen[0].status_text


def test_adresse_512_geht_fuer_ein_einkanal_geraet(bib):
    assert plan("Profil;Adresse\nDimmer;512\n", bib).zeilen[0].status == T.ANLEGBAR


def test_geraet_passt_nicht_ins_universum(bib):
    p = plan("Profil;Modus;Adresse\nLED PAR-56;5-Kanal;509\n", bib)
    assert p.zeilen[0].status == T.FEHLER
    assert "über Kanal 512 hinaus" in p.zeilen[0].status_text
    assert plan("Profil;Modus;Adresse\nLED PAR-56;5-Kanal;508\n", bib).zeilen[0].status == T.ANLEGBAR


def test_anzahl_laeuft_ueber_das_universum_hinaus_dann_gar_nichts(bib):
    p = plan("Profil;Modus;Adresse;Anzahl\nLED PAR-56;5-Kanal;500;3\n", bib)
    z = p.zeilen[0]
    assert z.status == T.FEHLER and z.geraete == []
    assert "Gerät 3 von 3" in z.status_text


@pytest.mark.parametrize("universum", ["0", "33", "99"])
def test_universum_ausserhalb(universum, bib):
    p = plan(f"Profil;Universum;Adresse\nDimmer;{universum};1\n", bib)
    assert p.zeilen[0].status == T.FEHLER
    assert f"Universum {universum} gibt es nicht" in p.zeilen[0].status_text


def test_universum_grenze_wie_im_dialog_geraet_hinzufuegen():
    from src.ui.widgets import fixture_browser as B
    assert (T.UNIVERSUM_MIN, T.UNIVERSUM_MAX) == (B._UNIVERSE_MIN, B._UNIVERSE_MAX)


def test_ueberschneidung_mit_vorhandenem_patch(bib):
    da = [T.Belegung("Alt", 1, 10, 4)]
    p = plan("Name;Profil;Modus;Adresse\nNeu;LED PAR-56;5-Kanal;9\n", bib, da)
    z = p.zeilen[0]
    assert z.status == T.UEBERSCHNEIDUNG and z.geraete == []
    assert "vorhandenen Gerät „Alt“" in z.status_text
    assert "Kanal 10 bis 13" in z.status_text
    # direkt davor und direkt dahinter passt
    for adresse in (5, 14):
        p = plan(f"Profil;Modus;Adresse\nLED PAR-56;5-Kanal;{adresse}\n", bib, da)
        assert p.zeilen[0].status == T.ANLEGBAR
    # anderes Universum stört nicht
    p = plan("Profil;Modus;Adresse\nLED PAR-56;5-Kanal;2.9\n", bib, da)
    assert p.zeilen[0].status == T.ANLEGBAR


def test_netzwerk_geraet_belegt_keine_dmx_kanaele(bib):
    da = [T.Belegung("Laser", 1, 1, 20, belegt_dmx=False)]
    assert plan("Profil;Adresse\nDimmer;5\n", bib, da).zeilen[0].status == T.ANLEGBAR


def test_ueberschneidung_zweier_tabellenzeilen_trifft_beide(bib):
    p = plan("Name;Profil;Modus;Adresse\n"
             "A;LED PAR-56;5-Kanal;1\n"
             "B;LED PAR-56;5-Kanal;4\n"
             "C;LED PAR-56;5-Kanal;20\n", bib)
    assert [z.status for z in p.zeilen] == [T.UEBERSCHNEIDUNG, T.UEBERSCHNEIDUNG, T.ANLEGBAR]
    assert "Zeile 3 der Tabelle („B“)" in p.zeilen[0].status_text
    assert "Zeile 2 der Tabelle („A“)" in p.zeilen[1].status_text


def test_anzahl_ueberschneidet_sich_nicht_mit_sich_selbst_aber_mit_anderen(bib):
    p = plan("Name;Profil;Modus;Adresse;Anzahl\n"
             "A;LED PAR-56;5-Kanal;1;3\n"
             "B;Dimmer;;15;1\n"
             "C;Dimmer;;16;1\n", bib)
    assert [z.status for z in p.zeilen] == [T.UEBERSCHNEIDUNG, T.UEBERSCHNEIDUNG, T.ANLEGBAR]


def test_offene_und_fehlerhafte_zeilen_blockieren_keine_adressen(bib):
    p = plan("Name;Profil;Modus;Adresse\n"
             "A;LED PAR-56;;1\n"              # offen (kein Modus)
             "B;Dimmer;;600\n"                # Fehler
             "C;Dimmer;;1\n", bib)
    assert [z.status for z in p.zeilen] == [T.OFFEN, T.FEHLER, T.ANLEGBAR]
    # … wird die offene gewählt, zeigt sich die Überschneidung
    p = plan("Name;Profil;Modus;Adresse\nA;LED PAR-56;;1\nC;Dimmer;;1\n", bib,
             wahl={0: (PAR.id, "5-Kanal")})
    assert [z.status for z in p.zeilen] == [T.UEBERSCHNEIDUNG, T.UEBERSCHNEIDUNG]


def test_doppelte_namen_sind_kein_hindernis_und_werden_nummeriert(bib):
    """IMP-3: frueher nur ein Hinweis (beide hiessen gleich), jetzt bekommt
    der zweite eine Nummer — Einzelheiten in tests/test_imp3_namen.py."""
    da = [T.Belegung("Front", 3, 1, 1)]
    p = plan("Name;Profil;Adresse\nFront;Dimmer;1\nSeite;Dimmer;2\nseite;Dimmer;3\nEinzeln;Dimmer;4\n",
             bib, da)
    assert [z.status for z in p.zeilen] == [T.ANLEGBAR] * 4
    assert [z.geraete[0].name for z in p.zeilen] == ["Front 2", "Seite", "seite 2", "Einzeln"]
    assert "heißt jetzt „Front 2“" in p.zeilen[0].status_text
    assert p.zeilen[1].umbenannt == [] and p.zeilen[3].umbenannt == []
    assert p.zeilen[3].hinweise == []


def test_tabellenfehler_geht_vor_offen(bib):
    p = plan("Profil;Adresse\nQuantum Wash;abc\n", bib)
    assert p.zeilen[0].status == T.FEHLER


def test_kanalzahl_der_tabelle_weicht_ab_ist_hinweis(bib):
    p = plan("Profil;Modus;Adresse;Kanäle\nLED PAR-56;5-Kanal;1;6\n", bib)
    assert p.zeilen[0].status == T.ANLEGBAR
    assert "nennt 6 Kanäle" in p.zeilen[0].status_text


# ── Zähler ───────────────────────────────────────────────────────────────────

def test_zaehlerzeile(bib):
    p = plan("Name;Profil;Modus;Adresse;Anzahl\n"
             "A;LED PAR-56;5-Kanal;1;2\n"     # 2 Geräte
             "B;Dimmer;;100;1\n"              # 1 Gerät
             "C;Unbekannt XYZ 123;;200;1\n"   # offen
             "D;LED PAR-56;;210;1\n"          # offen (Modus)
             "E;Dimmer;;300;1\n"              # Überschneidung mit F
             "F;Dimmer;;300;1\n"
             "G;Dimmer;;0;1\n", bib)          # Fehler
    assert p.zaehler() == {"geraete": 3, "umbenannt": 0, T.OFFEN: 2,
                           T.UEBERSCHNEIDUNG: 2, T.FEHLER: 1}
    assert p.zaehlerzeile() == \
        "3 Geräte werden angelegt, 2 offen, 2 Überschneidungen, 1 mit Fehler"


def test_zaehlerzeile_einzahl_und_nichts(bib):
    assert plan("Profil;Adresse\nDimmer;1\n", bib).zaehlerzeile() == "1 Gerät wird angelegt"
    assert plan("Profil;Adresse\nNix Da 42;1\n", bib).zaehlerzeile() == \
        "Kein Gerät wird angelegt, 1 offen"


# ── Vorlage ──────────────────────────────────────────────────────────────────

def test_vorlage_laesst_sich_wieder_einlesen(tmp_path):
    pfad = tmp_path / "vorlage.csv"
    T.schreibe_vorlage(str(pfad))
    roh = pfad.read_bytes()
    assert roh.startswith(b"\xef\xbb\xbf") and b"\r\n" in roh
    tab = T.lies_datei(str(pfad))
    assert tab.fehler == "" and tab.hinweise == []
    assert tab.trennzeichen == ";" and len(tab.zeilen) == 2
    assert all(z.fehler == [] for z in tab.zeilen)
    assert tab.zeilen[0].anzahl == 4


def test_aehnlichkeitssuche_bleibt_bei_grosser_bibliothek_schnell():
    import time
    viele = [T.Profil(i, f"Hersteller {i % 40}", f"Modell {i} Wash Beam Spot",
                      modi=(T.Modus("Standard", 8),)) for i in range(2500)]
    bib = T.Bibliothek(viele)
    start = time.perf_counter()
    for i in range(20):
        bib.finde("", f"Model {i} Wash Beam")
    assert time.perf_counter() - start < 6.0


# ── Gegenprüfung: nichts still umdeuten, nichts werfen ───────────────────────

@pytest.mark.parametrize("universum", ["-1", "-3", "+2", "1-2", "1.5", "2 (alt)", "#-2"])
def test_universum_mit_vorzeichen_oder_rechenzeichen_ist_ein_fehler(universum):
    """„-1“ wurde als Universum 1 gelesen und die Zeile angelegt."""
    z = T.lies_tabelle(f"Profil;Universum;Adresse\nDimmer;{universum};4\n").zeilen[0]
    assert z.universum is None
    assert z.fehler == [f"Das Universum „{universum}“ ist keine Zahl."]


@pytest.mark.parametrize("universum, erwartet", [
    ("2", 2), ("U2", 2), ("Univ. 2", 2), ("Universum 2", 2), ("Linie#3", 3)])
def test_universum_mit_wort_davor(universum, erwartet):
    z = T.lies_tabelle(f"Profil;Universum;Adresse\nDimmer;{universum};4\n").zeilen[0]
    assert (z.universum, z.fehler) == (erwartet, [])


def test_riesiges_feld_wird_zum_satz_statt_zur_ausnahme():
    """Ein Feld über der Größengrenze des CSV-Lesers warf schon beim Erkennen
    des Trennzeichens — im Programm wäre das ein Fehlerdialog statt eines Satzes."""
    tab = T.lies_tabelle("Name;Profil;Adresse\n" + "X" * 200_000 + ";Dimmer;1\n")
    assert tab.zeilen == [] and tab.fehler.startswith("Die Tabelle lässt sich nicht lesen")

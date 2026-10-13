"""ENG-39 Kern: wann ueberschneiden sich zwei Effekte — und wer gewinnt?

Treffer nur bei gemeinsamem Geraet UND gleichem Baustein. Dieselbe Geraeteart
auf anderen Geraeten ist kein Treffer, Farbe gegen Dimmer auch nicht (getrennte
Kanaele). Stufen gleich / hoeher / tiefer ergeben den Satz, wer gewinnt.
"""
import types

import pytest

from src.core.engine import stufen
from src.core.engine import ueberschneidung as U
from src.core.engine.function_manager import FunctionManager
from src.core.engine.rgb_matrix import MatrixStyle

AKZENTE = stufen.stufe_fuer_schluessel("akzente").zahl
STROBE = stufen.stufe_fuer_schluessel("strobe_blinder").zahl
NOTFALL = stufen.stufe_fuer_schluessel("notfall").zahl
GRUNDLICHT = stufen.stufe_fuer_schluessel("grundlicht").zahl

HINTERGRUND = [1, 2, 3, 4]
HIMMEL = [5, 6, 7, 8]


@pytest.fixture
def fm():
    return FunctionManager()


def _matrix(fm, name, geraete, stil=MatrixStyle.DIMMER, stufe=0, dimmer=False):
    m = fm.new_rgb_matrix(name)
    m.style = stil
    m.drive_intensity = dimmer
    m.fixture_grid = list(geraete)
    m.priority = stufe
    return m


def _suche(fm, eigene, andere, **mehr):
    return U.ueberschneidungen(
        eigene, andere, aufloesen=fm.get,
        geraete_von=lambda f: fm.affected_fids(f.id), **mehr)


# ── Treffer / kein Treffer ───────────────────────────────────────────────────

def test_gemeinsame_geraete_und_gleicher_baustein_ist_ein_treffer(fm):
    a = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    b = _matrix(fm, "Puls HG", HINTERGRUND)
    (t,) = _suche(fm, a, [b])
    assert t.andere is b and t.eigene is a
    assert t.bausteine == (stufen.DIMMER,)
    assert t.geraete == frozenset(HINTERGRUND)
    assert t.verhaeltnis == U.GLEICH and t.gewinner is None


def test_gleiche_geraeteart_aber_andere_geraete_ist_kein_treffer(fm):
    a = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    b = _matrix(fm, "Lauflicht Himmel", HIMMEL)
    assert _suche(fm, a, [b]) == []


def test_farbe_gegen_dimmer_auf_denselben_geraeten_ist_kein_treffer(fm):
    """Fachregel: Farbe und Dimmer sind getrennt."""
    farbe = _matrix(fm, "Regenbogen", HINTERGRUND, MatrixStyle.RGB)
    dimmer = _matrix(fm, "Lauflicht HG", HINTERGRUND, MatrixStyle.DIMMER)
    assert _suche(fm, farbe, [dimmer]) == []
    assert _suche(fm, dimmer, [farbe]) == []


def test_farb_matrix_die_den_dimmer_mittreibt_trifft_den_dimmer_effekt(fm):
    farbe = _matrix(fm, "Regenbogen", HINTERGRUND, MatrixStyle.RGB, dimmer=True)
    dimmer = _matrix(fm, "Lauflicht HG", HINTERGRUND, MatrixStyle.DIMMER)
    (t,) = _suche(fm, farbe, [dimmer])
    assert t.bausteine == (stufen.DIMMER,), "nur der Dimmer kollidiert"


def test_teilweise_gemeinsame_geraete_zaehlen_nur_die_gemeinsamen(fm):
    a = _matrix(fm, "A", [1, 2, 3, 4])
    b = _matrix(fm, "B", [3, 4, 5, 6])
    (t,) = _suche(fm, a, [b])
    assert t.geraete == frozenset({3, 4}) and t.geraete_text == "von 2 Geräten"


def test_szene_wird_je_geraet_gelesen_nicht_ueber_alles_vereint(fm):
    """Dimmer an Lampe 1, Farbe an Lampe 2 — ein Farb-Effekt NUR auf Lampe 1
    kollidiert nicht (die grobe Vereinigung waere ein Fehlalarm)."""
    s = fm.new_scene("Gemischt")
    s.set_value(1, 1, 255)          # Lampe 1: Dimmer
    s.set_value(2, 2, 255)          # Lampe 2: Farbe
    tabelle = {(1, 1): "intensity", (2, 2): "color_r"}
    nach = lambda f, k: tabelle.get((f, k))
    farbe_1 = _matrix(fm, "Farbe L1", [1], MatrixStyle.RGB)
    farbe_2 = _matrix(fm, "Farbe L2", [2], MatrixStyle.RGB)
    assert _suche(fm, s, [farbe_1], kanal_attribut=nach) == []
    (t,) = _suche(fm, s, [farbe_2], kanal_attribut=nach)
    assert t.bausteine == (stufen.FARBE,) and t.geraete == frozenset({2})


def test_szene_ohne_kanal_auskunft_meldet_nichts(fm):
    s = fm.new_scene("Unklar")
    s.set_value(1, 1, 255)
    assert _suche(fm, s, [_matrix(fm, "D", [1])]) == []


def test_sonstiges_und_unbekanntes_melden_nichts(fm):
    a = _matrix(fm, "Shutter A", HINTERGRUND, MatrixStyle.SHUTTER)
    b = _matrix(fm, "Shutter B", HINTERGRUND, MatrixStyle.SHUTTER)
    assert _suche(fm, a, [b]) == [], "„Sonstiges“ ist zu grob fuer eine Aussage"

    skript = types.SimpleNamespace(id=900, name="Skript", is_script=True,
                                   priority=0)
    assert U.ueberschneidungen(
        skript, [a], geraete_von=lambda f: HINTERGRUND) == []


def test_dieselbe_funktion_und_doppelte_zaehlen_nicht(fm):
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    assert _suche(fm, a, [a]) == []
    assert len(_suche(fm, a, [b, b, a])) == 1


def test_ohne_geraete_auskunft_wird_nicht_geraten(fm):
    a = _matrix(fm, "A", HINTERGRUND)
    b = _matrix(fm, "B", HINTERGRUND)
    assert U.ueberschneidungen(a, [b], aufloesen=fm.get) == []


# ── Stufen: wer gewinnt ──────────────────────────────────────────────────────

def test_gleiche_stufe_sagt_zuletzt_gestartet_gewinnt(fm):
    a = _matrix(fm, "Puls", HINTERGRUND)
    b = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    (t,) = _suche(fm, a, [b], gruppen=[("Hintergrund", HINTERGRUND)])
    assert t.satz() == (
        "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer der Gruppe "
        "„Hintergrund“ — gleiche Stufe, es gewinnt, wer zuletzt gestartet wurde.")


def test_andere_liegt_eine_stufe_hoeher_und_gewinnt(fm):
    a = _matrix(fm, "Lauflicht HG", HINTERGRUND, stufe=AKZENTE)
    b = _matrix(fm, "Blinder", HINTERGRUND, stufe=STROBE)
    (t,) = _suche(fm, a, [b], gruppen=[("Hintergrund", HINTERGRUND)])
    assert t.verhaeltnis == U.DIESE_TIEFER and t.gewinner is b
    assert t.stufen_abstand == 1
    assert t.satz().endswith("— „Blinder“ liegt eine Stufe höher und gewinnt.")


def test_diese_liegt_hoeher_und_gewinnt_mit_richtiger_stufenzahl(fm):
    a = _matrix(fm, "Notlicht", HINTERGRUND, stufe=NOTFALL)
    b = _matrix(fm, "Grund", HINTERGRUND, stufe=GRUNDLICHT)
    (t,) = _suche(fm, a, [b])
    assert t.verhaeltnis == U.DIESE_HOEHER and t.gewinner is a
    assert t.stufen_abstand == 4
    assert t.satz().endswith("— diese Taste liegt vier Stufen höher und gewinnt.")
    assert t.satz("Effekt").startswith("Dieser Effekt und „Grund“")
    assert "dieser Effekt liegt vier Stufen höher" in t.satz("Effekt")


def test_eigene_zahl_nennt_beide_namen_statt_einer_stufenzahl(fm):
    a = _matrix(fm, "Alt", HINTERGRUND, stufe=10)       # eigene Zahl
    b = _matrix(fm, "Normal", HINTERGRUND, stufe=0)
    (t,) = _suche(fm, b, [a])
    assert t.verhaeltnis == U.DIESE_TIEFER and t.stufen_abstand is None
    assert t.satz().endswith(
        "— „Alt“ liegt höher (eigene Zahl (10) über Effekte) und gewinnt.")


def test_reihenfolge_verlieren_vor_gleich_vor_gewinnen(fm):
    """Seit der Sichtprobe: zuerst, wogegen man verliert (vorher stand der
    Gleichstand vorn)."""
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=AKZENTE)
    unten = _matrix(fm, "Unten", HINTERGRUND, stufe=0)
    oben = _matrix(fm, "Oben", HINTERGRUND, stufe=STROBE)
    gleich = _matrix(fm, "Gleich", HINTERGRUND, stufe=AKZENTE)
    namen = [t.andere.name for t in _suche(fm, ich, [unten, oben, gleich])]
    assert namen == ["Oben", "Gleich", "Unten"]


# ── Geraete in Worten ────────────────────────────────────────────────────────

def test_gruppenname_nur_wenn_die_gemeinsamen_geraete_genau_die_gruppe_sind():
    gruppen = [("Hintergrund", HINTERGRUND), ("Himmel", HIMMEL)]
    assert U.geraete_text(HINTERGRUND, gruppen) == "der Gruppe „Hintergrund“"
    assert U.geraete_text([1, 2, 3], gruppen) == "von 3 Geräten", "Teilmenge"
    assert U.geraete_text([1, 2, 3, 4, 5], gruppen) == "von 5 Geräten", "mehr"
    assert U.geraete_text(HINTERGRUND) == "von 4 Geräten"


def test_ein_einzelnes_geraet_heisst_beim_namen():
    assert (U.geraete_text([7], geraete_name=lambda f: "Spot links")
            == "des Geräts „Spot links“")
    assert U.geraete_text([7]) == "eines Geräts"
    assert U.geraete_text([7], [("Solo", [7])]) == "der Gruppe „Solo“"
    assert U.geraete_text([1, 2, 3]) == "von 3 Geräten"


def test_mehrere_bausteine_werden_aufgezaehlt(fm):
    a = _matrix(fm, "A", HINTERGRUND, MatrixStyle.RGB, dimmer=True)
    b = _matrix(fm, "B", HINTERGRUND, MatrixStyle.RGB, dimmer=True)
    (t,) = _suche(fm, a, [b])
    assert t.bausteine == (stufen.DIMMER, stufen.FARBE)
    assert "steuern beide den Dimmer und die Farbe von 4 Geräten" in t.satz()


# ── Modify (ENG-37, falls vorhanden) ─────────────────────────────────────────

def test_modify_effekt_ersetzt_nichts_nur_neutraler_satz(fm):
    a = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    b = _matrix(fm, "Abdunkler", HINTERGRUND, stufe=STROBE)
    b.modify = True                 # Feld aus ENG-37, hier nur als Attribut
    (t,) = _suche(fm, a, [b])
    assert t.verhaeltnis == U.MODIFY and t.gewinner is None
    satz = t.satz()
    assert "gewinnt" not in satz and "ersetzt nichts" in satz
    assert "„Abdunkler“ ist ein Modify-Effekt" in satz
    (r,) = _suche(fm, b, [a])
    assert "diese Taste startet einen Modify-Effekt" in r.satz()


def test_modify_saetze_stehen_hinter_den_echten_treffern(fm):
    ich = _matrix(fm, "Ich", HINTERGRUND)
    mod = _matrix(fm, "Aaa Modify", HINTERGRUND)
    mod.modify = True
    echt = _matrix(fm, "Zzz Echt", HINTERGRUND)
    assert [t.andere.name for t in _suche(fm, ich, [mod, echt])] == [
        "Zzz Echt", "Aaa Modify"]


# ── Behaelter ────────────────────────────────────────────────────────────────

def test_bei_sammlung_zaehlt_der_behaelter_mit_seiner_stufe(fm):
    """Das Mitglied steht auf „Notfall“, die Sammlung auf „Effekte“ — es zaehlt
    die Sammlung (ENG-35: Mitglieder laufen auf der Stufe des Behaelters)."""
    mitglied = _matrix(fm, "Mitglied", HINTERGRUND, stufe=NOTFALL)
    farbe = _matrix(fm, "Farbe", HIMMEL, MatrixStyle.RGB)
    paket = fm.new_collection("Paket")
    paket.function_ids = [mitglied.id, farbe.id]
    andere = _matrix(fm, "Lauflicht HG", HINTERGRUND, stufe=AKZENTE)
    (t,) = _suche(fm, paket, [andere])
    assert t.eigene is paket and t.bausteine == (stufen.DIMMER,)
    assert t.geraete == frozenset(HINTERGRUND), "Himmel traegt nur Farbe"
    assert t.verhaeltnis == U.DIESE_TIEFER, "Stufe der Sammlung, nicht des Mitglieds"
    (r,) = _suche(fm, andere, [paket])
    assert r.andere is paket and r.verhaeltnis == U.DIESE_HOEHER


def test_chaser_vereint_seine_schritte(fm):
    a = _matrix(fm, "Schritt A", [1, 2])
    b = _matrix(fm, "Schritt B", [3, 4])
    lauf = fm.new_chaser("Lauf")
    lauf.add_step(a.id)
    lauf.add_step(b.id)
    andere = _matrix(fm, "Puls", [4, 9])
    (t,) = _suche(fm, lauf, [andere])
    assert t.geraete == frozenset({4})


def test_behaelter_mit_totem_mitglied_bricht_nicht(fm):
    paket = fm.new_collection("Paket")
    paket.function_ids = [99999, _matrix(fm, "M", HINTERGRUND).id]
    andere = _matrix(fm, "Puls", HINTERGRUND)
    assert len(_suche(fm, paket, [andere])) == 1


# ── Hinweiszeilen ────────────────────────────────────────────────────────────

def test_hoechstens_drei_ausgeschrieben_dann_und_n_weitere(fm):
    ich = _matrix(fm, "Ich", HINTERGRUND)
    andere = [_matrix(fm, f"Effekt {i}", HINTERGRUND) for i in range(5)]
    zeilen = U.hinweis_zeilen(_suche(fm, ich, andere))
    assert len(zeilen) == 4
    assert all(z.startswith("Diese Taste und „Effekt") for z in zeilen[:3])
    assert zeilen[3] == ("… und 2 weitere Überschneidungen: bei 2 entscheidet, "
                         "wer zuletzt gestartet wurde.")
    assert len(U.hinweis_zeilen(_suche(fm, ich, andere[:3]))) == 3
    assert U.hinweis_zeilen([]) == []


def test_mehrere_eigene_funktionen_nennen_die_eigene_beim_namen(fm):
    ich = _matrix(fm, "Mein Puls", HINTERGRUND)
    b = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    (zeile,) = U.hinweis_zeilen(_suche(fm, ich, [b]), nenne_eigene=True)
    assert zeile.startswith("Diese Taste („Mein Puls“) und „Lauflicht HG“")


def test_die_rechnung_veraendert_keine_funktion(fm):
    a = _matrix(fm, "A", HINTERGRUND, stufe=AKZENTE)
    b = _matrix(fm, "B", HINTERGRUND)
    vorher = (a.to_dict(), b.to_dict())
    _suche(fm, a, [b])[0].satz()
    assert (a.to_dict(), b.to_dict()) == vorher


# ── Nachtrag Sichtprobe: Reihenfolge, Verlierer nie abgeschnitten, Wortlaut ──

def test_verlierer_zuerst_dann_gleichstand_dann_gewinne(fm):
    """Die Zeile beginnt mit dem, wogegen die Taste verliert — nicht mehr
    alphabetisch ueber alles."""
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=AKZENTE)
    andere = [
        _matrix(fm, "Aaa Grundlicht", HINTERGRUND),                 # ich gewinne
        _matrix(fm, "Bbb Gleich", HINTERGRUND, stufe=AKZENTE),      # Gleichstand
        _matrix(fm, "Zzz Strobe", HINTERGRUND, stufe=STROBE),       # ich verliere
        _matrix(fm, "Yyy Notfall", HINTERGRUND, stufe=NOTFALL),     # ich verliere
        _matrix(fm, "Abc Gleich", HINTERGRUND, stufe=AKZENTE),      # Gleichstand
    ]
    treffer = _suche(fm, ich, andere)
    assert [t.andere.name for t in treffer] == [
        "Yyy Notfall", "Zzz Strobe", "Abc Gleich", "Bbb Gleich", "Aaa Grundlicht"]
    assert [t.verhaeltnis for t in treffer] == [
        U.DIESE_TIEFER, U.DIESE_TIEFER, U.GLEICH, U.GLEICH, U.DIESE_HOEHER]
    # hinweis_zeilen sortiert selbst — auch eine unsortierte Liste.
    zeilen = U.hinweis_zeilen(list(reversed(treffer)))
    assert "„Yyy Notfall“ liegt" in zeilen[0] and "„Zzz Strobe“ liegt" in zeilen[1]
    assert "„Abc Gleich“" in zeilen[2]
    assert zeilen[3] == ("… und 2 weitere Überschneidungen: bei 1 entscheidet, "
                         "wer zuletzt gestartet wurde; gegen 1 gewinnt diese Taste.")


def test_der_verlierer_fall_verschwindet_nie_hinter_und_n_weitere(fm):
    """Sichtprobe: drei Eintraege alphabetisch, dann „… und 3 weitere“ — und
    genau der Effekt, gegen den die Taste verliert, stand nicht mehr da."""
    ich = _matrix(fm, "Ich", HINTERGRUND)
    gleiche = [_matrix(fm, f"Effekt {i}", HINTERGRUND) for i in range(5)]
    staerker = _matrix(fm, "Zzz Blinder", HINTERGRUND, stufe=STROBE)
    zeilen = U.hinweis_zeilen(_suche(fm, ich, gleiche + [staerker]))
    assert "„Zzz Blinder“ liegt zwei Stufen höher und gewinnt." in zeilen[0]
    assert len(zeilen) == 4
    assert zeilen[-1] == ("… und 3 weitere Überschneidungen: bei 3 entscheidet, "
                          "wer zuletzt gestartet wurde.")


def test_mehr_verlierer_als_drei_stehen_alle_da(fm):
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=GRUNDLICHT)
    staerker = [_matrix(fm, f"Stark {i}", HINTERGRUND, stufe=STROBE)
                for i in range(5)]
    schwach = _matrix(fm, "Aaa Schwach", HINTERGRUND, stufe=GRUNDLICHT)
    zeilen = U.hinweis_zeilen(_suche(fm, ich, staerker + [schwach]))
    assert len(zeilen) == 6, "fuenf Verlierer ausgeschrieben + eine Restzeile"
    assert all(f"„Stark {i}“ liegt" in zeilen[i] for i in range(5))
    assert zeilen[-1] == ("… und 1 weitere Überschneidung: bei 1 entscheidet, "
                          "wer zuletzt gestartet wurde.")


def test_sehr_viele_verlierer_die_restzeile_sagt_es_ausdruecklich(fm):
    """Ueber ``MAX_VERLIERER_AUSGESCHRIEBEN`` hinaus fasst die Zeile zusammen —
    nennt dann aber, dass die Taste gegen die uebrigen ebenfalls verliert."""
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=GRUNDLICHT)
    n = U.MAX_VERLIERER_AUSGESCHRIEBEN + 3
    staerker = [_matrix(fm, f"Stark {i:02d}", HINTERGRUND, stufe=AKZENTE)
                for i in range(n)]
    gleich = _matrix(fm, "Gleich", HINTERGRUND, stufe=GRUNDLICHT)
    treffer = _suche(fm, ich, staerker + [gleich])
    zeilen = U.hinweis_zeilen(treffer)
    assert len(zeilen) == U.MAX_VERLIERER_AUSGESCHRIEBEN + 1
    assert zeilen[-1] == ("… und 4 weitere Überschneidungen: gegen 3 verliert "
                          "diese Taste; bei 1 entscheidet, wer zuletzt gestartet "
                          "wurde.")
    # Vollstaendig (Tooltip): jeder Treffer ein Satz, keine Restzeile.
    alle = U.hinweis_zeilen(treffer, hoechstens=None)
    assert len(alle) == n + 1 and not any(z.startswith("…") for z in alle)
    assert alle[:len(zeilen) - 1] == zeilen[:-1]


def test_restzeile_fuer_die_ansicht_spricht_vom_effekt(fm):
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=STROBE)
    schwach = [_matrix(fm, f"Schwach {i}", HINTERGRUND) for i in range(4)]
    zeilen = U.hinweis_zeilen(_suche(fm, ich, schwach), "Effekt")
    assert zeilen[-1] == ("… und 1 weitere Überschneidung: gegen 1 gewinnt "
                          "dieser Effekt.")


def test_namen_von_gruppe_und_geraet_stehen_in_anfuehrungszeichen(fm):
    """Sichtprobe: „… den Dimmer von Alle PAR“ klang holprig."""
    a = _matrix(fm, "Puls", HINTERGRUND)
    b = _matrix(fm, "Lauflicht", HINTERGRUND)
    (t,) = _suche(fm, a, [b], gruppen=[("Alle PAR", HINTERGRUND)])
    assert "steuern beide den Dimmer der Gruppe „Alle PAR“ — " in t.satz()
    assert "von Alle PAR" not in t.satz()
    c = _matrix(fm, "Solo A", [7])
    d = _matrix(fm, "Solo B", [7])
    (t,) = _suche(fm, c, [d], geraete_name=lambda fid: "Spot links")
    assert "steuern beide den Dimmer des Geräts „Spot links“ — " in t.satz()
    (t,) = _suche(fm, c, [d])
    assert "steuern beide den Dimmer eines Geräts — " in t.satz()
    d.modify = True
    (t,) = _suche(fm, c, [d], gruppen=[("Vorne", [7])])
    assert "fassen beide den Dimmer der Gruppe „Vorne“ an — " in t.satz()


# ── Nachtrag: Fader zaehlen immer mit ────────────────────────────────────────

def test_fader_ohne_stopp_bei_null_steht_als_eigener_satz_dahinter(fm):
    """Liegt der ANDERE Effekt auf einem Fader ohne „bei 0 wirklich stoppen“,
    sagt der Hinweis ausdruecklich, dass er bei 0 weiterlaeuft."""
    a = _matrix(fm, "Puls HG", HINTERGRUND)
    b = _matrix(fm, "Lauflicht HG", HINTERGRUND)
    (ohne,) = _suche(fm, a, [b])
    assert not ohne.andere_haelt and not ohne.eigene_haelt
    assert "am Laufen" not in ohne.satz()
    (t,) = _suche(fm, a, [b], haltend=[b.id])
    assert t.andere_haelt and not t.eigene_haelt
    assert t.satz() == (
        ohne.satz() + " Ein Fader hält „Lauflicht HG“ auch bei 0 am Laufen — "
        "der Effekt belegt die Geräte dann weiter.")
    assert U.hinweis_zeilen([t]) == [t.satz()], "keine Zusatzzeile fuer den anderen"


def test_eigener_effekt_am_fader_ohne_stopp_bekommt_eine_zeile_fuer_alle(fm):
    """Der Satz ueber den EIGENEN Effekt steht einmal am Ende — nicht hinter
    jeder Ueberschneidung wieder."""
    ich = _matrix(fm, "Wash", HINTERGRUND)
    andere = [_matrix(fm, f"E{i}", HINTERGRUND) for i in range(5)]
    treffer = _suche(fm, ich, andere, haltend={ich.id})
    assert all(t.eigene_haelt and not t.andere_haelt for t in treffer)
    assert all("am Laufen" not in t.satz("Fader") for t in treffer)
    fader = U.hinweis_zeilen(treffer, "Fader")
    assert fader[0].startswith("Dieser Fader und „E0“ steuern beide den Dimmer ")
    assert fader[-2].startswith("… und 2 weitere Überschneidungen: ")
    assert "Taste" not in "".join(fader)
    assert fader[-1] == U.HALTE_SATZ_FADER == (
        "Dieser Fader hält den Effekt auch bei 0 am Laufen — er belegt die "
        "Geräte dann weiter.")
    assert sum("am Laufen" in z for z in fader) == 1
    assert U.hinweis_zeilen(treffer, "Effekt", hoechstens=None)[-1] == (
        "Ein Fader hält diesen Effekt auch bei 0 am Laufen — er belegt die "
        "Geräte dann weiter.")
    assert U.hinweis_zeilen(treffer, "Taste")[-1] == (
        "Ein Fader hält „Wash“ auch bei 0 am Laufen — der Effekt belegt die "
        "Geräte dann weiter.")
    assert U.hinweis_zeilen([], "Fader") == [], "ohne Ueberschneidung kein Satz"


def test_fader_als_subjekt_sagt_wer_gewinnt(fm):
    ich = _matrix(fm, "Wash", HINTERGRUND)
    stark = _matrix(fm, "Blinder", HINTERGRUND, stufe=STROBE)
    (t,) = _suche(fm, ich, [stark])
    assert t.satz("Fader") == (
        "Dieser Fader und „Blinder“ steuern beide den Dimmer von 4 Geräten — "
        "„Blinder“ liegt zwei Stufen höher und gewinnt.")
    (u,) = _suche(fm, stark, [ich])
    assert u.satz("Fader").endswith("dieser Fader liegt zwei Stufen höher und gewinnt.")

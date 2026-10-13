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
    assert t.geraete == frozenset({3, 4}) and t.geraete_text == "2 Geräten"


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
        "Diese Taste und „Lauflicht HG“ steuern beide den Dimmer von "
        "Hintergrund — gleiche Stufe, es gewinnt, wer zuletzt gestartet wurde.")


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


def test_reihenfolge_gleich_vor_verlieren_vor_gewinnen(fm):
    ich = _matrix(fm, "Ich", HINTERGRUND, stufe=AKZENTE)
    unten = _matrix(fm, "Unten", HINTERGRUND, stufe=0)
    oben = _matrix(fm, "Oben", HINTERGRUND, stufe=STROBE)
    gleich = _matrix(fm, "Gleich", HINTERGRUND, stufe=AKZENTE)
    namen = [t.andere.name for t in _suche(fm, ich, [unten, oben, gleich])]
    assert namen == ["Gleich", "Oben", "Unten"]


# ── Geraete in Worten ────────────────────────────────────────────────────────

def test_gruppenname_nur_wenn_die_gemeinsamen_geraete_genau_die_gruppe_sind():
    gruppen = [("Hintergrund", HINTERGRUND), ("Himmel", HIMMEL)]
    assert U.geraete_text(HINTERGRUND, gruppen) == "Hintergrund"
    assert U.geraete_text([1, 2, 3], gruppen) == "3 Geräten", "Teilmenge"
    assert U.geraete_text([1, 2, 3, 4, 5], gruppen) == "5 Geräten", "mehr"
    assert U.geraete_text(HINTERGRUND) == "4 Geräten"


def test_ein_einzelnes_geraet_heisst_beim_namen():
    assert U.geraete_text([7], geraete_name=lambda f: "Spot links") == "„Spot links“"
    assert U.geraete_text([7]) == "1 Gerät"
    assert U.geraete_text([7], [("Solo", [7])]) == "Solo"


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
    assert zeilen[3] == "… und 2 weitere"
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

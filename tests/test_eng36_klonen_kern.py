"""ENG-36: Klonen — der Kern (Plan, Übersetzung, Rückweg, Sicherung).

Die Show wird hier im Test gebaut: echter ``AppState`` mit eigener Show-DB,
eigene Snap-Bibliothek, eigener Paletten- und Funktions-Verwalter. Nur die
Kanal-Auflösung ist ersetzt (sechs kleine Gerätetypen).
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import color_utils as C                                # noqa: E402
from src.core.engine.cue import Cue                                  # noqa: E402
from src.core.engine.cue_stack import CueStack                       # noqa: E402
from src.core.engine.efx import EfxFixture                           # noqa: E402
from src.core.engine.palette import Palette, PaletteType             # noqa: E402
from src.core.engine.sequence import SequenceStep                    # noqa: E402
from src.core.show import klonen as K                                # noqa: E402
from src.core.show import sicherungen as S                           # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402

from _eng36_show import (CMY, DIM, RAD, RGB, RGB_OHNE_DIMMER, RGBW,  # noqa: E402
                         kanal as _kanal, show_fixture)


@pytest.fixture
def show(tmp_path, monkeypatch):
    yield from show_fixture(tmp_path, monkeypatch)


def _kennzeichen(plan, bereich=None):
    return [e.kennzeichen for e in plan.eintraege
            if bereich is None or e.bereich == bereich]


# ── Paare ───────────────────────────────────────────────────────────────────

def test_eine_quelle_auf_viele_und_paarweise():
    assert K.paare_bilden([1], [5, 6, 7]) == [(1, 5), (1, 6), (1, 7)]
    assert K.paare_bilden([1, 2], [11, 12]) == [(1, 11), (2, 12)]


def test_ungleiche_anzahl_ist_eine_klare_meldung():
    with pytest.raises(K.KlonFehler, match="2 Quellen und 3 Ziele"):
        K.paare_bilden([1, 2], [5, 6, 7])
    with pytest.raises(K.KlonFehler, match="zugleich Quelle und Ziel"):
        K.paare_bilden([1], [1, 2])
    with pytest.raises(K.KlonFehler, match="Kein Ziel"):
        K.paare_bilden([1], [])


def test_ohne_wahl_von_hinzufuegen_oder_ersetzen_kein_plan(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    with pytest.raises(K.KlonFehler, match="Hinzufügen oder Ersetzen"):
        show.plane([1], [2], wie=None)


def test_unbekanntes_geraet(show):
    show.patch(1, RGB)
    with pytest.raises(K.KlonFehler, match="nicht gepatcht"):
        show.plane([1], [9])


# ── Übersetzung ─────────────────────────────────────────────────────────────

def _geraete(show):
    return K._geraete(show.state)


def test_rgb_nach_rgbw_und_zurueck(show):
    show.patch(1, RGB)
    show.patch(2, RGBW)
    g = _geraete(show)
    hin = K.uebersetze_werte({"color_r": 255, "color_g": 255, "color_b": 255},
                             g[1], g[2])
    assert hin.uebersetzt == {"color_r": 0, "color_g": 0, "color_b": 0,
                              "color_w": 255}, "der Weißanteil wandert auf Weiß"
    assert not hin.gleich and not hin.weg
    orange = K.uebersetze_werte({"color_r": 255, "color_g": 128, "color_b": 0},
                                g[1], g[2])
    assert orange.uebersetzt == {"color_r": 255, "color_g": 128, "color_b": 0,
                                 "color_w": 0}
    zurueck = K.uebersetze_werte(
        {"color_r": 100, "color_g": 0, "color_b": 0, "color_w": 155}, g[2], g[1])
    assert zurueck.uebersetzt == {"color_r": 255, "color_g": 155, "color_b": 155}


def test_rgb_nach_cmy_und_zurueck(show):
    show.patch(1, RGB)
    show.patch(3, CMY)
    g = _geraete(show)
    hin = K.uebersetze_werte({"color_r": 255, "color_g": 0, "color_b": 0}, g[1], g[3])
    assert hin.uebersetzt == {"cmy_c": 0, "cmy_m": 255, "cmy_y": 255}
    zurueck = K.uebersetze_werte({"cmy_c": 0, "cmy_m": 255, "cmy_y": 255}, g[3], g[1])
    assert zurueck.uebersetzt == {"color_r": 255, "color_g": 0, "color_b": 0}


def test_cmy_schreibrichtung_nur_auf_wunsch():
    """Bestehende Aufrufer (Matrix, Farbwähler) sehen kein neues Verhalten."""
    kanaele = [_kanal(1, "cmy_c"), _kanal(2, "cmy_m"), _kanal(3, "cmy_y")]
    assert C.color_attrs_for_fixture(kanaele, (255, 0, 0)) == {}
    assert C.color_attrs_for_fixture(kanaele, (255, 0, 0), cmy=True) == {
        "cmy_c": 0, "cmy_m": 255, "cmy_y": 255}


def test_farbrad_nur_ungefaehr_und_nur_benannte_plaetze(show):
    show.patch(1, RGB)
    show.patch(5, RAD)
    g = _geraete(show)
    rot = K.uebersetze_werte({"color_r": 250, "color_g": 20, "color_b": 20}, g[1], g[5])
    assert rot.uebersetzt == {"color_wheel": 14}
    assert "ungefähr" in rot.texte[0]
    # Farbrad → Mischung: über die Farbe des Platzes
    blau = K.uebersetze_werte({"color_wheel": 25}, g[5], g[1])
    assert blau.uebersetzt == dict(zip(("color_r", "color_g", "color_b"),
                                       C.hex_to_rgb(C.color_word_hex("Blau"))))
    # Platz ohne Farbwort: fällt weg, es wird nicht geraten
    ohne = K.uebersetze_werte({"color_wheel": 35}, g[5], g[1])
    assert not ohne.werte and ohne.weg[0][0] == "color_wheel"


def test_geraet_ohne_farbe_farbe_faellt_weg_dimmer_bleibt_dimmer(show):
    show.patch(1, RGB)
    show.patch(4, DIM)
    g = _geraete(show)
    u = K.uebersetze_werte({"intensity": 200, "color_r": 255}, g[1], g[4])
    assert u.werte == {"intensity": 200}
    assert u.weg == [("color_r", "Ziel hat keine Farbe")]


def test_farb_werte_bringen_nie_einen_dimmer_mit(show):
    """★ Farbe und Dimmer bleiben getrennt — in jeder Farb-Richtung."""
    for fid, typ in ((1, RGB), (2, RGBW), (3, CMY), (5, RAD), (6, RGB_OHNE_DIMMER)):
        show.patch(fid, typ)
    g = _geraete(show)
    farben = {1: {"color_r": 255, "color_g": 255, "color_b": 255},
              2: {"color_w": 255}, 3: {"cmy_c": 0, "cmy_m": 0, "cmy_y": 0},
              5: {"color_wheel": 5}, 6: {"color_r": 255}}
    for q, werte in farben.items():
        for z in g:
            if z == q:
                continue
            u = K.uebersetze_werte(werte, g[q], g[z])
            assert not (set(u.werte) & {"intensity", "dimmer", "master"}), (q, z, u.werte)
    # … und umgekehrt: ein Dimmerwert färbt nichts
    u = K.uebersetze_werte({"intensity": 255}, g[1], g[2])
    assert u.werte == {"dimmer": 255}


def test_bewegung_und_kopfwerte_fallen_bei_anderem_typ_weg(show):
    show.patch(3, CMY)
    show.patch(5, RAD)
    g = _geraete(show)
    u = K.uebersetze_werte({"pan": 10, "tilt": 20, "intensity": 9,
                            "color_r#1": 7}, g[3], g[5])
    assert u.werte == {"intensity": 9}
    gruende = dict(u.weg)
    assert gruende["pan"] == K.GRUND_SPAETER and gruende["tilt"] == K.GRUND_SPAETER
    assert gruende["color_r#1"] == K.GRUND_KOPF


def test_unbekannter_farbkanal_verschwindet_nicht_still(show):
    show.patch(1, RGB)
    show.patch(2, RGBW)
    g = _geraete(show)
    u = K.uebersetze_werte({"color_temperature": 90, "color_r": 1}, g[1], g[2])
    assert "color_temperature" in dict(u.weg)


def test_gleicher_typ_alles_eins_zu_eins(show):
    show.patch(3, CMY)
    show.patch(4, CMY)
    g = _geraete(show)
    werte = {"pan": 10, "tilt": 20, "cmy_c": 3, "intensity": 9, "pan#1": 4}
    u = K.uebersetze_werte(werte, g[3], g[4])
    assert u.gleich == werte and not u.uebersetzt and not u.weg


# ── Snaps: hinzufügen / ersetzen ────────────────────────────────────────────

def test_snap_hinzufuegen_laesst_vorhandenen_wert_ersetzen_ueberschreibt(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.patch(3, RGB)
    rot = show.snaps.add_snap("Rot", "", {
        1: {"color_r": 255, "color_g": 0},
        2: {"color_r": 7, "color_b": 99},          # das Ziel tut hier schon etwas
        3: {"color_r": 1}})
    anderer = show.snaps.add_snap("Ohne Quelle", "", {2: {"color_r": 5}})

    plan = show.plane([1], [2], wie=K.HINZUFUEGEN, bereiche=[K.BEREICH_SNAPS])
    assert rot.values[2] == {"color_r": 7, "color_b": 99}, "Plan schreibt nichts"
    assert K.BLEIBT in _kennzeichen(plan)
    plan.anwenden(show.state)
    assert rot.values[2] == {"color_r": 7, "color_b": 99, "color_g": 0}
    plan.zuruecknehmen(show.state)
    assert rot.values[2] == {"color_r": 7, "color_b": 99}

    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    assert [e.art for e in plan.eintraege if e.schritte] == ["ersetzt"]
    plan.anwenden(show.state)
    assert rot.values[2] == {"color_r": 255, "color_b": 99, "color_g": 0}, \
        "color_b hat die Quelle nicht — es bleibt stehen"
    assert rot.values[3] == {"color_r": 1}, "unbeteiligtes Gerät unberührt"
    assert anderer.values == {2: {"color_r": 5}}, \
        "wo die Quelle nicht vorkommt, wird nichts angefasst"
    plan.zuruecknehmen(show.state)
    assert rot.values[2] == {"color_r": 7, "color_b": 99}


def test_farb_snap_zwischen_typen_ohne_dimmer(show):
    show.patch(1, RGB)
    show.patch(2, RGBW)
    snap = show.snaps.add_snap("Weiß", "", {1: {"color_r": 255, "color_g": 255,
                                               "color_b": 255}})
    plan = show.plane([1], [2], bereiche=[K.BEREICH_SNAPS])
    assert _kennzeichen(plan) == [K.UEBERSETZT]
    plan.anwenden(show.state)
    assert snap.values[2] == {"color_r": 0, "color_g": 0, "color_b": 0, "color_w": 255}
    assert "dimmer" not in snap.values[2]


def test_hinweis_wenn_quelle_keinen_dimmer_hat(show):
    show.patch(6, RGB_OHNE_DIMMER)
    show.patch(2, RGBW)
    plan = show.plane([6], [2])
    assert any("hat keinen Dimmer" in h and "getrennt" in h for h in plan.hinweise)
    assert any("verschiedene Gerätetypen" in h for h in plan.hinweise)


def test_rueckgaengig_laesst_spaetere_handarbeit_stehen(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.patch(3, RGB)
    snap = show.snaps.add_snap("Rot", "", {1: {"color_r": 255, "color_g": 10}})
    plan = show.plane([1], [2], bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    snap.values[3] = {"color_b": 44}             # später: anderes Gerät von Hand
    snap.values[2]["color_g"] = 77               # später: am Ziel von Hand
    plan.zuruecknehmen(show.state)
    assert snap.values[3] == {"color_b": 44}
    assert snap.values[1] == {"color_r": 255, "color_g": 10}
    assert snap.values[2] == {"color_g": 77}, \
        "nur der geklonte Eintrag geht, die Handarbeit bleibt"


# ── Snapshots, Cues, Sequenzen, Paletten, Grundwerte ────────────────────────

def test_snapshot_cue_sequenz_palette_grundwerte(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    st = show.state
    st._snapshots_data = [{"name": "A", "values": {"1": {"color_r": 9}}, "ignored": []}]
    stack = CueStack("Haupt")
    cue = Cue(number=1, label="eins", values={1: {"color_r": 200, "intensity": 50}})
    cue.attr_delays = {1: {"color_r": 0.5}}
    stack.cues.append(cue)
    st.cue_stacks = [stack]
    seq = st.function_manager.new_sequence("Lauf")
    seq.bound_fixtures = [1]
    seq.steps = [SequenceStep(values={"1": {"color_g": 1}}),
                 SequenceStep(values={"1": {"color_g": 2}})]
    pal = Palette(name="Meins", type=PaletteType.COLOR, values={"color_r": 1})
    pal.fixture_values = {1: {"color_r": 33}}
    show.paletten._palettes.append(pal)
    st.base_levels = {1: {"intensity": 255}}

    plan = show.plane([1], [2])
    assert set(_kennzeichen(plan)) == {K.UNVERAENDERT}
    assert plan.aenderungen == 5
    plan.anwenden(st)
    assert st._snapshots_data[0]["values"]["2"] == {"color_r": 9}
    assert cue.values[2] == {"color_r": 200, "intensity": 50}
    assert cue.attr_delays[2] == {"color_r": 0.5}
    assert [s.values["2"] for s in seq.steps] == [{"color_g": 1}, {"color_g": 2}]
    assert seq.bound_fixtures == [1, 2]
    assert pal.fixture_values[2] == {"color_r": 33}
    assert st.base_levels[2] == {"intensity": 255}
    plan.zuruecknehmen(st)
    assert st._snapshots_data[0]["values"] == {"1": {"color_r": 9}}
    assert cue.values == {1: {"color_r": 200, "intensity": 50}}
    assert cue.attr_delays == {1: {"color_r": 0.5}}
    assert [s.values for s in seq.steps] == [{"1": {"color_g": 1}}, {"1": {"color_g": 2}}]
    assert seq.bound_fixtures == [1]
    assert pal.fixture_values == {1: {"color_r": 33}}
    assert st.base_levels == {1: {"intensity": 255}}


def test_haekchen_begrenzen_die_bereiche(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.snaps.add_snap("Rot", "", {1: {"color_r": 255}})
    show.state.base_levels = {1: {"intensity": 255}}
    plan = show.plane([1], [2], bereiche=[K.BEREICH_GRUNDWERTE])
    assert {e.bereich for e in plan.eintraege} == {K.BEREICH_GRUNDWERTE}


# ── Szene: Kanalnummern ─────────────────────────────────────────────────────

def test_szene_nach_kanalnummer_zwischen_zwei_typen(show):
    """RGB-PAR (K1 Dimmer, K2–4 RGB) → RGBW-PAR (K1 Dimmer, K2–5 RGBW)."""
    show.patch(1, RGB)
    show.patch(2, RGBW)
    sz = show.state.function_manager.new_scene("Weiß")
    for ch, val in ((1, 180), (2, 255), (3, 255), (4, 255)):
        sz.set_value(1, ch, val)
    vorher = sz.to_dict()
    plan = show.plane([1], [2], bereiche=[K.BEREICH_SNAPS])
    assert sz.to_dict() == vorher
    assert set(_kennzeichen(plan)) == {K.UNVERAENDERT, K.UEBERSETZT}
    plan.anwenden(show.state)
    ziel = {sv.channel: sv.value for sv in sz.values if sv.fixture_id == 2}
    assert ziel == {1: 180, 2: 0, 3: 0, 4: 0, 5: 255}
    plan.zuruecknehmen(show.state)
    assert sz.to_dict() == vorher


def test_szene_gleicher_typ_kanal_fuer_kanal(show):
    show.patch(3, CMY)
    show.patch(4, CMY)
    sz = show.state.function_manager.new_scene("Pos")
    sz.set_value(3, 5, 11)
    sz.set_value(3, 6, 22)
    sz.set_value(4, 5, 99)
    plan = show.plane([3], [4], wie=K.HINZUFUEGEN, bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert {sv.channel: sv.value for sv in sz.values if sv.fixture_id == 4} == {5: 99, 6: 22}
    plan.zuruecknehmen(show.state)
    plan = show.plane([3], [4], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert {sv.channel: sv.value for sv in sz.values if sv.fixture_id == 4} == {5: 11, 6: 22}


# ── Mitgliedschaften ────────────────────────────────────────────────────────

def test_gruppe_ans_ende_und_neben_die_quelle(show):
    for fid in (1, 2, 3, 9):
        show.patch(fid, RGB)
    gid = show.gruppe("Front", {"0,0": 1, "1,0": 2, "2,0": 3}, cols=4, rows=1)
    fremd = show.gruppe("Ohne Quelle", {"0,0": 2}, cols=4, rows=1)
    roh_vorher = show.gruppe_lesen(gid)

    plan = show.plane([1], [9], bereiche=[K.BEREICH_GRUPPEN])
    assert show.gruppe_lesen(gid) == roh_vorher, "Plan schreibt nichts"
    assert [e.objekt for e in plan.eintraege] == ["Gruppe „Front“"]
    plan.anwenden(show.state)
    assert show.gruppe_lesen(gid) == (4, 1, {"0,0": 1, "1,0": 2, "2,0": 3, "3,0": 9})
    assert show.state.group_fids_by_name("Front") == [1, 2, 3, 9]
    assert show.gruppe_lesen(fremd) == (4, 1, {"0,0": 2})
    plan.zuruecknehmen(show.state)
    assert show.gruppe_lesen(gid) == roh_vorher

    plan = show.plane([1], [9], bereiche=[K.BEREICH_GRUPPEN], position=K.POS_NEBEN)
    plan.anwenden(show.state)
    assert show.state.group_fids_by_name("Front") == [1, 9, 2, 3]
    plan.zuruecknehmen(show.state)
    assert show.gruppe_lesen(gid) == roh_vorher


def test_gruppe_waechst_wenn_voll_und_ziel_schon_dabei_bleibt(show):
    for fid in (1, 2, 9):
        show.patch(fid, RGB)
    gid = show.gruppe("Voll", {"0,0": 1, "1,0": 2}, cols=2, rows=1)
    plan = show.plane([1], [9], bereiche=[K.BEREICH_GRUPPEN])
    plan.anwenden(show.state)
    assert show.gruppe_lesen(gid) == (2, 2, {"0,0": 1, "1,0": 2, "0,1": 9})
    nochmal = show.plane([1], [9], bereiche=[K.BEREICH_GRUPPEN])
    assert _kennzeichen(nochmal) == [K.BLEIBT] and nochmal.aenderungen == 0


def test_gruppe_kopfzellen_gleicher_typ_und_anderer_typ(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.patch(3, DIM)
    gid = show.gruppe("Köpfe", {"0,0": "1:0", "1,0": "1:1"}, cols=4, rows=1)
    plan = show.plane([1], [2], bereiche=[K.BEREICH_GRUPPEN])
    plan.anwenden(show.state)
    assert show.gruppe_lesen(gid)[2] == {"0,0": "1:0", "1,0": "1:1",
                                         "2,0": "2:0", "3,0": "2:1"}
    plan.zuruecknehmen(show.state)
    plan = show.plane([1], [3], bereiche=[K.BEREICH_GRUPPEN])
    assert _kennzeichen(plan) == [K.UEBERSETZT]
    plan.anwenden(show.state)
    assert show.gruppe_lesen(gid)[2] == {"0,0": "1:0", "1,0": "1:1", "2,0": "3"}


def test_matrix_raster_ans_ende_neben_und_rueckweg(show):
    for fid in (1, 2, 3, 9):
        show.patch(fid, RGB)
    m = show.state.function_manager.new_rgb_matrix("Lauflicht")
    m.cols, m.rows, m.fixture_grid = 3, 1, [1, 2, 3]
    m.snapshot_preset()
    vorher = m.to_dict()

    plan = show.plane([1], [9], bereiche=[K.BEREICH_EFFEKTE])
    assert m.to_dict() == vorher
    plan.anwenden(show.state)
    assert (m.cols, m.rows, m.fixture_grid) == (4, 1, [1, 2, 3, 9])
    assert m._preset["fixture_grid"] == [1, 2, 3, 9], "Live-Rückfall kennt das Ziel"
    plan.zuruecknehmen(show.state)
    assert m.to_dict() == vorher, "byte-gleich wie vor dem Klonen"

    plan = show.plane([1], [9], bereiche=[K.BEREICH_EFFEKTE], position=K.POS_NEBEN)
    plan.anwenden(show.state)
    assert (m.cols, m.fixture_grid) == (4, [1, 9, 2, 3])
    # später von Hand: ein anderes Gerät getauscht → Rückweg nimmt nur das Ziel
    m.fixture_grid[3] = 2
    plan.zuruecknehmen(show.state)
    assert m.fixture_grid == [1, None, 2, 2] and m.cols == 4


def test_matrix_zweidimensional_luecke_fuellen_sonst_neue_zeile(show):
    for fid in (1, 2, 3, 8, 9):
        show.patch(fid, RGB)
    m = show.state.function_manager.new_rgb_matrix("Fläche")
    m.cols, m.rows, m.fixture_grid = 2, 2, [1, 2, 3, None]
    plan = show.plane([1], [8, 9], bereiche=[K.BEREICH_EFFEKTE])
    plan.anwenden(show.state)
    assert (m.cols, m.rows, m.fixture_grid) == (2, 3, [1, 2, 3, 8, 9])
    plan.zuruecknehmen(show.state)
    assert (m.cols, m.rows, m.fixture_grid) == (2, 2, [1, 2, 3, None])


def test_matrix_kopfzellen(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.patch(4, DIM)
    m = show.state.function_manager.new_rgb_matrix("Köpfe")
    m.cols, m.rows = 2, 1
    m.fixture_grid, m.head_grid = [1, 1], [0, 1]
    plan = show.plane([1], [2], bereiche=[K.BEREICH_EFFEKTE])
    plan.anwenden(show.state)
    assert (m.fixture_grid, m.head_grid, m.cols) == ([1, 1, 2, 2], [0, 1, 0, 1], 4)
    plan.zuruecknehmen(show.state)
    plan = show.plane([1], [4], bereiche=[K.BEREICH_EFFEKTE])
    assert _kennzeichen(plan) == [K.UEBERSETZT]
    plan.anwenden(show.state)
    assert (m.fixture_grid, m.head_grid, m.cols) == ([1, 1, 4], [0, 1, None], 3)


def test_bewegungs_effekt_faecher_und_ziel_ohne_pan_tilt(show):
    show.patch(3, CMY)
    show.patch(4, CMY)
    show.patch(5, RAD)
    show.patch(1, RGB)
    efx = show.state.function_manager.new_efx("Kreis")
    efx.fixtures = [EfxFixture(fid=3, start_offset=0.25), EfxFixture(fid=4)]
    vorher = efx.to_dict()
    plan = show.plane([3], [5, 1], bereiche=[K.BEREICH_EFFEKTE])
    assert _kennzeichen(plan) == [K.UNVERAENDERT, K.FAELLT_WEG]
    assert "2 → 3 Ziele" in plan.eintraege[0].text
    alte = list(efx.fixtures)
    plan.anwenden(show.state)
    assert [(x.fid, x.start_offset) for x in efx.fixtures] == [(3, 0.25), (4, 0.0), (5, 0.25)]
    assert efx.fixtures[:2] == alte, "vorhandene Ziele bleiben dieselben Objekte"
    plan.zuruecknehmen(show.state)
    assert efx.to_dict() == vorher


def test_effekt_geraeteliste_und_konsole(show):
    for fid in (3, 4, 1):
        show.patch(fid, CMY if fid != 1 else RGB)
    car = show.state.function_manager.new_carousel("Karussell")
    car.fixture_ids = [3]
    show.state._vc_layout = {"widgets": [
        {"type": "VCButton", "caption": "BO links", "blackout_fids": [3]},
        {"type": "VCFrame", "caption": "Rahmen", "children": [
            {"type": "VCXYPad", "caption": "Pad", "fixture_ids": [3],
             "pan_attr": "pan", "tilt_attr": "tilt"}]},
        {"type": "VCButton", "caption": "BO global", "blackout_fids": []}]}
    vorher = json.dumps(show.state._vc_layout, sort_keys=True)

    plan = show.plane([3], [4, 1],
                      bereiche=[K.BEREICH_EFFEKTE, K.BEREICH_KONSOLE])
    assert json.dumps(show.state._vc_layout, sort_keys=True) == vorher
    plan.anwenden(show.state)
    assert car.fixture_ids == [3, 4, 1]
    w = show.state._vc_layout["widgets"]
    assert w[0]["blackout_fids"] == [3, 4, 1]
    assert w[1]["children"][0]["fixture_ids"] == [3, 4], "RGB-PAR hat kein Pan/Tilt"
    assert w[2]["blackout_fids"] == []
    assert K.FAELLT_WEG in _kennzeichen(plan, K.BEREICH_KONSOLE)
    plan.zuruecknehmen(show.state)
    assert car.fixture_ids == [3]
    assert json.dumps(show.state._vc_layout, sort_keys=True) == vorher


def test_konsole_rueckweg_fasst_ein_anderes_element_nicht_an(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    show.state._vc_layout = {"widgets": [
        {"type": "VCButton", "caption": "BO", "blackout_fids": [1]}]}
    plan = show.plane([1], [2], bereiche=[K.BEREICH_KONSOLE])
    plan.anwenden(show.state)
    # das Layout wurde inzwischen umgebaut: an der Stelle steht etwas anderes
    show.state._vc_layout = {"widgets": [
        {"type": "VCButton", "caption": "Neu", "blackout_fids": [1, 2]}]}
    plan.zuruecknehmen(show.state)
    assert show.state._vc_layout["widgets"][0]["blackout_fids"] == [1, 2]


# ── 1 → viele, paarweise ────────────────────────────────────────────────────

def test_eins_auf_viele_und_paarweise_im_ganzen(show):
    for fid in (1, 2, 11, 12, 13):
        show.patch(fid, RGB)
    snap = show.snaps.add_snap("Zwei", "", {1: {"color_r": 10}, 2: {"color_r": 20}})
    plan = show.plane([1], [11, 12, 13], bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert [snap.values[f] for f in (11, 12, 13)] == [{"color_r": 10}] * 3
    assert plan.label == "Klonen 1 → 11–13"
    plan.zuruecknehmen(show.state)
    plan = show.plane([1, 2], [11, 12], bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert (snap.values[11], snap.values[12]) == ({"color_r": 10}, {"color_r": 20})
    assert 13 not in snap.values


# ── Ein Rückgängig-Schritt ──────────────────────────────────────────────────

def test_ein_rueckgaengig_schritt_im_verlauf(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    snap = show.snaps.add_snap("Rot", "", {1: {"color_r": 255}})
    gid = show.gruppe("Front", {"0,0": 1})
    show.state.base_levels = {1: {"intensity": 255}}
    stack = get_undo_stack()
    gerufen = []
    plan = show.plane([1], [2])
    assert K.anwenden_mit_rueckweg(show.state, plan,
                                   danach=lambda p: gerufen.append(p)) == 3
    assert stack.undo_label() == "Klonen 1 → 2" and len(stack._undo) == 1
    assert stack.undo()
    assert snap.values == {1: {"color_r": 255}}
    assert show.gruppe_lesen(gid)[2] == {"0,0": 1}
    assert show.state.base_levels == {1: {"intensity": 255}}
    assert stack.redo()
    assert snap.values[2] == {"color_r": 255}
    assert show.gruppe_lesen(gid)[2] == {"0,0": 1, "1,0": 2}
    assert len(gerufen) == 3


# ── Show bleibt konsistent, alte Shows bleiben byte-gleich ──────────────────

def _show_bloecke(show) -> str:
    st = show.state
    return json.dumps({
        "functions": st.function_manager.to_dict(),
        "snaps": show.snaps.to_dict(),
        "paletten": show.paletten.to_dict(),
        "cues": [[c.to_dict() for c in s.cues] for s in st.cue_stacks],
        "base_levels": {str(k): v for k, v in st.base_levels.items()},
        "vc": st._vc_layout, "snapshots": st._snapshots_data,
        "gruppen": [(g["name"], show.gruppe_lesen(g["id"]))
                    for g in st.list_fixture_groups()],
    }, sort_keys=True, default=str)


def _volle_show(show):
    for fid, typ in ((1, RGB), (2, RGBW), (3, CMY), (4, CMY)):
        show.patch(fid, typ)
    st = show.state
    show.snaps.add_snap("Rot", "", {1: {"color_r": 255, "intensity": 200},
                                    3: {"pan": 5, "cmy_c": 9}})
    show.gruppe("Front", {"0,0": 1, "1,0": 3})
    m = st.function_manager.new_rgb_matrix("M")
    m.cols, m.rows, m.fixture_grid = 2, 1, [1, 3]
    efx = st.function_manager.new_efx("E")
    efx.fixtures = [EfxFixture(fid=3)]
    sz = st.function_manager.new_scene("S")
    sz.set_value(1, 2, 255)
    sz.set_value(3, 5, 77)
    st.base_levels = {1: {"intensity": 255}}
    st._vc_layout = {"widgets": [{"type": "VCButton", "caption": "BO",
                                  "blackout_fids": [1, 3]}]}
    st._snapshots_data = [{"name": "A", "values": {"3": {"tilt": 1}}, "ignored": []}]


def test_planen_schreibt_nichts_und_rueckweg_ist_byte_gleich(show):
    _volle_show(show)
    vorher = _show_bloecke(show)
    plan = show.plane([1, 3], [2, 4], wie=K.ERSETZEN, position=K.POS_NEBEN)
    assert _show_bloecke(show) == vorher, "der Plan ist eine reine Rechnung"
    assert plan.zaehler()[K.UNVERAENDERT] and plan.zaehler()[K.UEBERSETZT]
    plan.anwenden(show.state)
    assert _show_bloecke(show) != vorher
    plan.zuruecknehmen(show.state)
    assert _show_bloecke(show) == vorher


def test_show_pruefung_meldet_nach_dem_klonen_nichts_neues(show):
    from src.core.capability.validate import validate_show_dict
    _volle_show(show)

    def befunde():
        st = show.state
        d = {"functions": st.function_manager.to_dict().get("functions", []),
             "virtual_console": st._vc_layout,
             "patch": [{"fid": f.fid, "address": f.address, "universe": f.universe,
                        "channel_count": f.channel_count}
                       for f in st.get_patched_fixtures()]}
        return sorted(str(x) for x in validate_show_dict(d))

    vorher = befunde()
    show.plane([1, 3], [2, 4]).anwenden(show.state)
    assert befunde() == vorher
    # jede Szenen-Kanalnummer des Ziels liegt in seinem Kanalbereich
    anzahl = {f.fid: f.channel_count for f in show.state.get_patched_fixtures()}
    for f in show.state.function_manager.all():
        for sv in getattr(f, "values", []) if hasattr(f, "set_value") else []:
            assert 1 <= sv.channel <= anzahl[sv.fixture_id]


# ── Sicherung ───────────────────────────────────────────────────────────────

def test_sicherung_vor_dem_klonen_wird_angelegt(tmp_path, monkeypatch):
    ordner = tmp_path / "LightOS"
    ordner.mkdir()
    monkeypatch.setattr(S, "app_data_dir", lambda: str(ordner))
    from src.core.show import show_file as SF
    geschrieben = []

    def _save(pfad):
        geschrieben.append(pfad)
        with open(pfad, "wb") as f:
            f.write(b"show")

    monkeypatch.setattr(SF, "save_show", _save)
    try:
        pfad = K.sicherung_anlegen("Abend")
        assert pfad and os.path.isfile(pfad) and geschrieben == [pfad]
        eintraege = S.liste_sicherungen("Abend")
        assert [(e.anlass, e.anlass_text) for e in eintraege] == [
            (S.ANLASS_VOR_KLONEN, "vor dem Klonen")]
    finally:
        S.warte_bis_fertig()


def test_sicherung_scheitert_still(monkeypatch):
    from src.core.show import show_file as SF

    def _kaputt(_pfad):
        raise OSError("voll")

    monkeypatch.setattr(SF, "save_show", _kaputt)
    assert K.sicherung_anlegen("Abend") is None

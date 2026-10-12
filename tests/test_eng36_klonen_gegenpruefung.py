"""ENG-36: Klonen — Befunde der Gegenprüfung.

1. Farbe zwischen verschiedenen Typen: übersetzt wird nur eine VOLLSTÄNDIGE
   Farbe, und dann als Ganzes. Ein Teilwert (einzelne Farbkanäle) geht nur auf
   den gleichnamigen Kanal, der Rest des Ziels bleibt.
2. Eine Quelle auf viele Ziele „neben die Quelle": die Ziele stehen in der
   gewählten Reihenfolge hinter der Quelle, nicht umgekehrt — in jeder Liste.
3. Randfälle: Rückgängig nach gelöschter Gruppe, Quelle = Ziel, Ziel schon
   Mitglied.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy.orm import Session                                   # noqa: E402

from src.core.database.models import FixtureGroup                    # noqa: E402
from src.core.engine.efx import EfxFixture                           # noqa: E402
from src.core.engine.sequence import SequenceStep                    # noqa: E402
from src.core.show import klonen as K                                # noqa: E402

from _eng36_show import CMY, RGB, RGBW, show_fixture                 # noqa: E402


@pytest.fixture
def show(tmp_path, monkeypatch):
    yield from show_fixture(tmp_path, monkeypatch)


def _farb_show(show, quelle: dict, ziel: dict | None, zieltyp=RGBW):
    show.patch(1, RGB)
    show.patch(2, zieltyp)
    werte = {1: dict(quelle)}
    if ziel is not None:
        werte[2] = dict(ziel)
    return show.snaps.add_snap("Farbe", "", werte)


def _zeilen(plan, kennzeichen):
    return [e.text for e in plan.eintraege if e.kennzeichen == kennzeichen]


# ── 1. Farbe: voll / Teilwert × Ersetzen / Hinzufügen ───────────────────────

VOLL = {"color_r": 255, "color_g": 0, "color_b": 0}
ZIEL = {"color_g": 99, "color_w": 50}


def test_volle_farbe_ersetzen_ersetzt_die_farbe_als_ganzes(show):
    snap = _farb_show(show, VOLL, ZIEL)
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    assert [e.kennzeichen for e in plan.eintraege] == [K.UEBERSETZT]
    assert "Farbe wird als Ganzes ersetzt" in plan.eintraege[0].text
    assert plan.eintraege[0].art == "ersetzt"
    plan.anwenden(show.state)
    assert snap.values[2] == {"color_r": 255, "color_g": 0, "color_b": 0,
                              "color_w": 0}, "dieselbe Farbe im Farbsystem des Ziels"
    plan.zuruecknehmen(show.state)
    assert snap.values[2] == ZIEL


def test_volle_farbe_hinzufuegen_ueberschreibt_keinen_wert_des_ziels(show):
    snap = _farb_show(show, VOLL, ZIEL)
    plan = show.plane([1], [2], wie=K.HINZUFUEGEN, bereiche=[K.BEREICH_SNAPS])
    assert {e.kennzeichen for e in plan.eintraege} == {K.UEBERSETZT, K.BLEIBT}
    assert "Farbe wird als Ganzes übersetzt" in _zeilen(plan, K.UEBERSETZT)[0]
    assert "Ganzes ersetzt" not in _zeilen(plan, K.UEBERSETZT)[0]
    plan.anwenden(show.state)
    assert snap.values[2] == {"color_g": 99, "color_w": 50,
                              "color_r": 255, "color_b": 0}
    plan.zuruecknehmen(show.state)
    assert snap.values[2] == ZIEL


def test_teilwert_ersetzen_nur_der_gleichnamige_kanal(show):
    """Der Befund: aus „Rot 255" wurde Grün 0, Blau 0, Weiß 0."""
    snap = _farb_show(show, {"color_r": 255},
                      {"color_r": 7, "color_g": 99, "color_w": 50})
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    assert [e.kennzeichen for e in plan.eintraege] == [K.UNVERAENDERT]
    assert "Ganzes" not in plan.eintraege[0].text
    plan.anwenden(show.state)
    assert snap.values[2] == {"color_r": 255, "color_g": 99, "color_w": 50}, \
        "Grün und Weiß des Ziels bleiben — es wird nichts gelöscht"
    plan.zuruecknehmen(show.state)
    assert snap.values[2] == {"color_r": 7, "color_g": 99, "color_w": 50}


def test_teilwert_hinzufuegen_nur_was_fehlt(show):
    snap = _farb_show(show, {"color_r": 255, "color_g": 5}, ZIEL)
    plan = show.plane([1], [2], wie=K.HINZUFUEGEN, bereiche=[K.BEREICH_SNAPS])
    assert {e.kennzeichen for e in plan.eintraege} == {K.UNVERAENDERT, K.BLEIBT}
    plan.anwenden(show.state)
    assert snap.values[2] == {"color_g": 99, "color_w": 50, "color_r": 255}
    plan.zuruecknehmen(show.state)
    assert snap.values[2] == ZIEL


@pytest.mark.parametrize("wie", [K.ERSETZEN, K.HINZUFUEGEN])
def test_teilwert_ohne_gleichnamigen_kanal_faellt_weg(show, wie):
    """Quelle Rot, Ziel CMY: aus einem einzelnen Kanal wird keine Farbe."""
    ziel = {"cmy_c": 9, "cmy_m": 8}
    snap = _farb_show(show, {"color_r": 255}, ziel, zieltyp=CMY)
    plan = show.plane([1], [2], wie=wie, bereiche=[K.BEREICH_SNAPS])
    assert [e.kennzeichen for e in plan.eintraege] == [K.FAELLT_WEG]
    assert "Rot" in plan.eintraege[0].text
    assert "keine vollständige Farbe" in plan.eintraege[0].text
    assert plan.aenderungen == 0
    plan.anwenden(show.state)
    assert snap.values[2] == ziel


def test_volle_farbe_nach_cmy_setzt_alle_drei(show):
    snap = _farb_show(show, VOLL, {"cmy_c": 9}, zieltyp=CMY)
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert snap.values[2] == {"cmy_c": 0, "cmy_m": 255, "cmy_y": 255}


def test_teilwert_cmy_und_volle_cmy_farbe(show):
    show.patch(1, CMY)
    show.patch(2, RGB)
    show.patch(3, CMY)                     # anderes Profil erzwingen: Modus
    g = K._geraete(show.state)
    teil = K.uebersetze_werte({"cmy_c": 200}, g[1], g[2])
    assert not teil.werte and teil.weg == [("cmy_c", K.GRUND_TEILWERT)]
    voll = K.uebersetze_werte({"cmy_c": 0, "cmy_m": 255, "cmy_y": 255}, g[1], g[2])
    assert voll.uebersetzt == {"color_r": 255, "color_g": 0, "color_b": 0}


def test_teilwert_in_einer_szene_laesst_die_anderen_kanaele(show):
    """Szenen speichern Kanalnummern — dieselbe Regel."""
    show.patch(1, RGB)                     # K1 Dimmer, K2–4 RGB
    show.patch(2, RGBW)                    # K1 Dimmer, K2–5 RGBW
    sz = show.state.function_manager.new_scene("Nur Rot")
    sz.set_value(1, 2, 255)
    sz.set_value(2, 3, 99)
    sz.set_value(2, 5, 50)
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert {sv.channel: sv.value for sv in sz.values if sv.fixture_id == 2} \
        == {3: 99, 5: 50, 2: 255}
    plan.zuruecknehmen(show.state)
    assert {sv.channel: sv.value for sv in sz.values if sv.fixture_id == 2} \
        == {3: 99, 5: 50}


def test_farbe_bringt_auch_nach_der_neuen_regel_keinen_dimmer(show):
    snap = _farb_show(show, VOLL, None)
    plan = show.plane([1], [2], wie=K.ERSETZEN, bereiche=[K.BEREICH_SNAPS])
    plan.anwenden(show.state)
    assert "dimmer" not in snap.values[2] and "intensity" not in snap.values[2]


# ── 2. Eine Quelle auf viele, „neben die Quelle": Reihenfolge ───────────────

ZIELE = [2, 3, 4, 5]
SOLL = [1, 2, 3, 4, 5, 9]


def _geraete(show, typ=RGB):
    for fid in (1, 9, *ZIELE):
        show.patch(fid, typ)


def test_reihenfolge_gruppe_einzeilig(show):
    _geraete(show)
    gid = show.gruppe("Front", {"0,0": 1, "1,0": 9}, cols=2, rows=1)
    vorher = show.gruppe_lesen(gid)
    plan = show.plane([1], ZIELE, bereiche=[K.BEREICH_GRUPPEN], position=K.POS_NEBEN)
    assert all("neben die Quelle" in e.text for e in plan.eintraege)
    plan.anwenden(show.state)
    assert show.state.group_fids_by_name("Front") == SOLL
    assert show.gruppe_lesen(gid)[0] == 6
    plan.zuruecknehmen(show.state)
    assert show.gruppe_lesen(gid) == vorher


def test_reihenfolge_gruppe_raster_und_vorschau_stimmt(show):
    """Im mehrzeiligen Raster ist rechts nur EINE Zelle frei: das erste Ziel
    kommt daneben, das zweite ans Ende — und die Vorschau sagt genau das."""
    for fid in (1, 2, 3, 8, 9):
        show.patch(fid, RGB)
    gid = show.gruppe("Raster", {"0,0": 1, "2,0": 9, "0,1": 8}, cols=3, rows=2)
    plan = show.plane([1], [2, 3], bereiche=[K.BEREICH_GRUPPEN],
                      position=K.POS_NEBEN)
    assert "neben die Quelle" in plan.eintraege[0].text
    assert "kein Platz" in plan.eintraege[1].text
    plan.anwenden(show.state)
    assert show.gruppe_lesen(gid)[2] == {"0,0": 1, "1,0": 2, "2,0": 9,
                                         "0,1": 8, "1,1": 3}


def test_reihenfolge_matrix_raster(show):
    _geraete(show)
    m = show.state.function_manager.new_rgb_matrix("Lauflicht")
    m.cols, m.rows, m.fixture_grid = 2, 1, [1, 9]
    m.snapshot_preset()
    vorher = m.to_dict()
    plan = show.plane([1], ZIELE, bereiche=[K.BEREICH_EFFEKTE], position=K.POS_NEBEN)
    assert [e.text.rsplit(" ", 1)[-1] for e in plan.eintraege] \
        == ["3×1", "4×1", "5×1", "6×1"], "die Vorschau zählt mit"
    plan.anwenden(show.state)
    assert (m.cols, m.rows, m.fixture_grid) == (6, 1, SOLL)
    plan.zuruecknehmen(show.state)
    assert m.to_dict() == vorher


def test_reihenfolge_bewegungs_effekt(show):
    _geraete(show, CMY)
    efx = show.state.function_manager.new_efx("Kreis")
    efx.fixtures = [EfxFixture(fid=1, start_offset=0.25), EfxFixture(fid=9)]
    vorher = efx.to_dict()
    plan = show.plane([1], ZIELE, bereiche=[K.BEREICH_EFFEKTE], position=K.POS_NEBEN)
    assert "5 → 6 Ziele" in plan.eintraege[-1].text
    plan.anwenden(show.state)
    assert [x.fid for x in efx.fixtures] == SOLL
    plan.zuruecknehmen(show.state)
    assert efx.to_dict() == vorher


def test_reihenfolge_effekt_geraeteliste_konsole_und_sequenz(show):
    _geraete(show, CMY)
    st = show.state
    car = st.function_manager.new_carousel("Karussell")
    car.fixture_ids = [1, 9]
    st._vc_layout = {"widgets": [
        {"type": "VCButton", "caption": "BO", "blackout_fids": [1, 9]},
        {"type": "VCXYPad", "caption": "Pad", "fixture_ids": [1, 9],
         "pan_attr": "pan", "tilt_attr": "tilt"}]}
    seq = st.function_manager.new_sequence("Lauf")
    seq.bound_fixtures = [1, 9]
    seq.steps = [SequenceStep(values={"1": {"pan": 1}})]
    vc_vorher = json.dumps(st._vc_layout, sort_keys=True)

    plan = show.plane([1], ZIELE, position=K.POS_NEBEN, bereiche=[
        K.BEREICH_EFFEKTE, K.BEREICH_KONSOLE, K.BEREICH_CUES])
    plan.anwenden(st)
    assert car.fixture_ids == SOLL
    assert st._vc_layout["widgets"][0]["blackout_fids"] == SOLL
    assert st._vc_layout["widgets"][1]["fixture_ids"] == SOLL
    assert seq.bound_fixtures == SOLL
    plan.zuruecknehmen(st)
    assert car.fixture_ids == [1, 9] and seq.bound_fixtures == [1, 9]
    assert json.dumps(st._vc_layout, sort_keys=True) == vc_vorher


def test_reihenfolge_ans_ende_und_paarweise_unveraendert(show):
    _geraete(show)
    gid = show.gruppe("Front", {"0,0": 1, "1,0": 9}, cols=2, rows=1)
    plan = show.plane([1], ZIELE, bereiche=[K.BEREICH_GRUPPEN])
    plan.anwenden(show.state)
    assert show.state.group_fids_by_name("Front") == [1, 9, 2, 3, 4, 5]
    plan.zuruecknehmen(show.state)
    # paarweise: jedes Ziel neben SEINE Quelle
    plan = show.plane([1, 9], [2, 3], bereiche=[K.BEREICH_GRUPPEN],
                      position=K.POS_NEBEN)
    plan.anwenden(show.state)
    assert show.state.group_fids_by_name("Front") == [1, 2, 9, 3]
    assert show.gruppe_lesen(gid)[0] == 4


# ── 3. Randfälle ────────────────────────────────────────────────────────────

def test_rueckgaengig_nach_geloeschter_gruppe(show):
    for fid in (1, 2):
        show.patch(fid, RGB)
    gid = show.gruppe("Front", {"0,0": 1})
    bleibt = show.gruppe("Bleibt", {"0,0": 1})
    snap = show.snaps.add_snap("Rot", "", {1: {"color_r": 255}})
    plan = show.plane([1], [2])
    plan.anwenden(show.state)
    with Session(show.state._show_engine) as s:
        s.delete(s.get(FixtureGroup, gid))
        s.commit()
    plan.zuruecknehmen(show.state)          # darf nicht werfen
    with Session(show.state._show_engine) as s:
        assert s.get(FixtureGroup, gid) is None, "die Gruppe kommt nicht zurück"
    assert show.gruppe_lesen(bleibt)[2] == {"0,0": 1}
    assert snap.values == {1: {"color_r": 255}}


def test_quelle_gleich_ziel_wird_abgelehnt(show):
    show.patch(1, RGB)
    show.patch(2, RGB)
    with pytest.raises(K.KlonFehler, match="zugleich Quelle und Ziel"):
        show.plane([1], [1])
    with pytest.raises(K.KlonFehler, match="zugleich Quelle und Ziel"):
        show.plane([1, 2], [2, 1])


def test_ziel_schon_mitglied_bleibt_wo_es_ist(show):
    for fid in (1, 2, 3):
        show.patch(fid, CMY)
    gid = show.gruppe("Front", {"0,0": 2, "1,0": 1})
    m = show.state.function_manager.new_rgb_matrix("M")
    m.cols, m.rows, m.fixture_grid = 2, 1, [2, 1]
    efx = show.state.function_manager.new_efx("E")
    efx.fixtures = [EfxFixture(fid=2), EfxFixture(fid=1)]
    car = show.state.function_manager.new_carousel("C")
    car.fixture_ids = [2, 1]
    for wie in (K.HINZUFUEGEN, K.ERSETZEN):
        plan = show.plane([1], [2], wie=wie, position=K.POS_NEBEN)
        assert {e.kennzeichen for e in plan.eintraege} == {K.BLEIBT}
        assert plan.aenderungen == 0
        plan.anwenden(show.state)
        assert show.gruppe_lesen(gid)[2] == {"0,0": 2, "1,0": 1}
        assert m.fixture_grid == [2, 1] and car.fixture_ids == [2, 1]
        assert [x.fid for x in efx.fixtures] == [2, 1]


def test_typ_hinweis_ein_satz_fuer_alle_paare(show):
    show.patch(1, RGB)
    show.patch(7, RGB)
    for fid in (2, 3, 4):
        show.patch(fid, RGBW)
    plan = show.plane([1], [2, 3, 4, 7])
    satz = plan.typ_hinweis
    assert satz.startswith("Verschiedene Gerätetypen (1 → 2–4)")
    for wort in ("Bewegung", "Gobo", "Optik", "Shutter", "Werte einzelner Köpfe"):
        assert wort in satz
    assert "NICHT" in satz
    assert show.plane([1], [7]).typ_hinweis == ""

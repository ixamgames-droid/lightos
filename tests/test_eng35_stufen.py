"""ENG-35: Prioritaeten-Stufen — Abbildung Stufe <-> Zahl, alte Shows,
Reihenfolge im Engine-Merge und die Erkennung der Bausteine.

Die Stufen sind nur Namen ueber ``Function.priority``; der Engine-Merge
(``FunctionManager.tick``) bleibt unveraendert. Diese Datei haelt fest, dass
das so ist — und dass die Zahl 10 der Kanal-Kopplung auf keine Stufe faellt.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.core.dmx.universe import Universe
from src.core.engine import stufen
from src.core.engine.function_manager import FunctionManager


# ── Abbildung ────────────────────────────────────────────────────────────────

def test_fuenf_feste_stufen_in_aufsteigender_staerke():
    assert [s.name for s in stufen.STUFEN] == [
        "Grundlicht", "Effekte", "Akzente", "Strobe & Blinder", "Notfall"]
    zahlen = [s.zahl for s in stufen.STUFEN]
    assert zahlen == sorted(zahlen) and len(set(zahlen)) == 5
    assert zahlen == [-20, 0, 20, 40, 60]


def test_effekte_ist_null_und_die_vorgabe():
    assert stufen.STUFE_VORGABE.name == "Effekte"
    assert stufen.STUFE_VORGABE.zahl == 0
    assert stufen.stufen_name(0) == "Effekte"


@pytest.mark.parametrize("stufe", stufen.STUFEN)
def test_stufe_zu_zahl_und_zurueck(stufe):
    assert stufen.stufe_fuer_zahl(stufe.zahl) is stufe
    assert stufen.stufe_fuer_schluessel(stufe.schluessel) is stufe
    assert stufen.stufen_name(stufe.zahl) == stufe.name


@pytest.mark.parametrize("zahl", [-99, -10, -1, 1, 5, 7, 10, 30, 99])
def test_zahl_ohne_stufe_heisst_eigene_zahl(zahl):
    assert stufen.stufe_fuer_zahl(zahl) is None
    assert stufen.stufen_name(zahl) == f"eigene Zahl ({zahl})"


def test_kaputte_zahl_ist_effekte():
    assert stufen.zahl_von("x") == 0
    assert stufen.zahl_von(None) == 0
    assert stufen.stufen_name("x") == "Effekte"


def test_naechste_stufe_auch_von_einer_eigenen_zahl_aus():
    assert stufen.naechste_stufe(0, +1).name == "Akzente"
    assert stufen.naechste_stufe(0, -1).name == "Grundlicht"
    assert stufen.naechste_stufe(60, +1) is None
    assert stufen.naechste_stufe(-20, -1) is None
    # eigene Zahl 10 liegt zwischen „Effekte“ und „Akzente“
    assert stufen.naechste_stufe(10, +1).name == "Akzente"
    assert stufen.naechste_stufe(10, -1).name == "Effekte"
    assert stufen.naechste_stufe(99, -1).name == "Notfall"
    assert stufen.naechste_stufe(99, +1) is None


def test_kanal_kopplung_faellt_auf_keine_stufe():
    """Die Kanal-Kopplung wird fest mit 10 angelegt (sie liest den Ausgang der
    Bewegungs-Effekte). Diese Zahl darf nicht als „Akzente“ erscheinen."""
    from src.ui.widgets.mapped_channel_editor import KANAL_KOPPLUNG_ZAHL
    assert KANAL_KOPPLUNG_ZAHL == 10
    assert stufen.stufe_fuer_zahl(KANAL_KOPPLUNG_ZAHL) is None
    effekte = stufen.STUFE_VORGABE.zahl
    akzente = stufen.stufe_fuer_schluessel("akzente").zahl
    assert effekte < KANAL_KOPPLUNG_ZAHL < akzente


# ── alte Shows ───────────────────────────────────────────────────────────────

def _kleine_show() -> FunctionManager:
    fm = FunctionManager()
    fm.new_scene("Rot")
    fm.new_chaser("Lauf")
    fm.new_collection("Paket")
    fm.new_sequence("Folge")
    fm.new_efx("Kreis")
    fm.new_rgb_matrix("Matrix")
    return fm


def test_alte_show_bleibt_byte_gleich():
    """Laden und wieder speichern aendert kein Byte, solange niemand eine
    Stufe waehlt — auch nicht bei Zahlen, die auf keine Stufe passen."""
    fm = _kleine_show()
    alle = fm.all()
    alle[0].priority = 7          # eigene Zahl aus einer alten Show
    alle[1].priority = 10
    alle[2].priority = -3
    vorher = json.dumps(fm.to_dict(), sort_keys=True, ensure_ascii=False)
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(vorher))
    nachher = json.dumps(fm2.to_dict(), sort_keys=True, ensure_ascii=False)
    assert nachher == vorher
    assert [f.priority for f in fm2.all()][:3] == [7, 10, -3]


def test_show_ohne_stufen_speichert_weiter_nur_die_zahl():
    fm = _kleine_show()
    for fd in fm.to_dict()["functions"]:
        assert fd["priority"] == 0
        assert not any("stufe" in k.lower() for k in fd), fd.keys()


def test_stufe_wird_als_zahl_gespeichert_und_wiedererkannt():
    fm = _kleine_show()
    f = fm.all()[0]
    f.priority = stufen.stufe_fuer_schluessel("strobe_blinder").zahl
    fm2 = FunctionManager()
    fm2.from_dict(fm.to_dict())
    geladen = [g for g in fm2.all() if g.name == f.name][0]
    assert stufen.stufe_von(geladen).name == "Strobe & Blinder"


# ── Reihenfolge im Engine-Merge ──────────────────────────────────────────────

class _Schreiber:
    def __init__(self, fid, wert, priority=0):
        self.id = fid
        self._wert = wert
        self.is_running = True
        self.intensity = 1.0
        self.priority = priority

    def start(self):
        self.is_running = True

    def stop(self):
        self.is_running = False

    def write(self, universes, patch_cache, dt, registry):
        universes[1].set_channel(1, self._wert)


def _lauf(spezis):
    """spezis: (fid, wert, stufen-schluessel) in START-Reihenfolge -> Kanal 1."""
    fm = FunctionManager()
    for fid, wert, schluessel in spezis:
        zahl = stufen.stufe_fuer_schluessel(schluessel).zahl
        fm._functions[fid] = _Schreiber(fid, wert, zahl)
    for fid, _w, _s in spezis:
        fm.start(fid)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    return u[1].get_channel(1)


_NAMEN = [s.schluessel for s in stufen.STUFEN]


@pytest.mark.parametrize("unten,oben", [
    (_NAMEN[i], _NAMEN[j]) for i in range(5) for j in range(i + 1, 5)])
def test_hoehere_stufe_gewinnt_egal_wer_zuerst_startet(unten, oben):
    assert _lauf([(1, 50, unten), (2, 200, oben)]) == 200
    assert _lauf([(2, 200, oben), (1, 50, unten)]) == 200


@pytest.mark.parametrize("schluessel", _NAMEN)
def test_gleiche_stufe_zuletzt_gestartet_gewinnt(schluessel):
    assert _lauf([(1, 50, schluessel), (2, 200, schluessel)]) == 200
    assert _lauf([(2, 200, schluessel), (1, 50, schluessel)]) == 50


def test_eigene_zahl_ordnet_sich_zwischen_den_stufen_ein():
    fm = FunctionManager()
    fm._functions[1] = _Schreiber(1, 10, 0)       # Effekte
    fm._functions[2] = _Schreiber(2, 20, 10)      # eigene Zahl (Kanal-Kopplung)
    fm._functions[3] = _Schreiber(3, 30, 20)      # Akzente
    for fid in (3, 2, 1):
        fm.start(fid)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    assert u[1].get_channel(1) == 30
    fm.stop(3)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    assert u[1].get_channel(1) == 20


def test_kinder_einer_sammlung_laufen_auf_der_stufe_der_sammlung():
    """Befund, kein Wunsch: Sammlung/Chaser/Show schreiben ihre Mitglieder im
    EIGENEN Durchlauf. Die Stufe eines Mitglieds zaehlt dort nicht — nur die
    des Behaelters. (Bewusst nicht in ENG-35 umgebaut.)"""
    notfall = stufen.stufe_fuer_schluessel("notfall").zahl
    grundlicht = stufen.stufe_fuer_schluessel("grundlicht").zahl

    def lauf(stufe_der_sammlung):
        fm = FunctionManager()
        # Mitglied mit hoechster Stufe, das Kanal 1 = 200 schreibt …
        mitglied = _Schreiber(901, 200, notfall)
        mitglied.is_running = False
        fm._functions[901] = mitglied
        sammlung = fm.new_collection("Paket")
        sammlung.function_ids = [901]
        sammlung.priority = stufe_der_sammlung
        # … und ein einzelner Effekt auf „Effekte“, der 50 schreibt.
        fm._functions[902] = _Schreiber(902, 50, 0)
        fm.start(902)
        fm.start(sammlung.id)
        u = {1: Universe(1)}
        fm.tick(u, [], 0.02)
        return u[1].get_channel(1)

    assert lauf(grundlicht) == 50, (
        "die Sammlung liegt auf Grundlicht — ihr Notfall-Mitglied gewinnt "
        "nicht gegen einen Effekt der Stufe Effekte")
    # Gegenprobe: das Mitglied schreibt wirklich — mit der Sammlung auf
    # „Akzente“ gewinnt es.
    assert lauf(stufen.stufe_fuer_schluessel("akzente").zahl) == 200


# ── Bausteine ────────────────────────────────────────────────────────────────

def test_bausteine_matrix_nach_stil():
    fm = FunctionManager()
    from src.core.engine.rgb_matrix import MatrixStyle
    m = fm.new_rgb_matrix("M")
    m.style = MatrixStyle.RGB
    m.drive_intensity = False
    assert stufen.bausteine_von(m).text() == "Farbe"
    m.drive_intensity = True
    assert stufen.bausteine_von(m).text() == "Dimmer · Farbe"
    m.style = MatrixStyle.DIMMER
    assert stufen.bausteine_von(m).text() == "Dimmer"
    m.style = MatrixStyle.SHUTTER
    assert stufen.bausteine_von(m).text() == "Sonstiges"


def test_bausteine_bewegung_und_leere_bewegung():
    from src.core.engine.efx import EfxFixture
    fm = FunctionManager()
    e = fm.new_efx("Kreis")
    e.fixtures = []
    assert stufen.bausteine_von(e).text() == "—"
    e.fixtures = [EfxFixture(fid=1)]
    assert stufen.bausteine_von(e).text() == "Bewegung"


def test_bausteine_bewegung_mit_offenem_strahl_schreibt_den_dimmer():
    """Codex-Review #1087 (CDX-59): „Dimmer/Shutter öffnen“ setzt
    ``intensity = 255`` — Ueberschneidungs-Hinweis und Prioritaeten-Uebersicht
    muessen den Dimmer-Konflikt kennen."""
    from src.core.engine.efx import EfxFixture
    fm = FunctionManager()
    e = fm.new_efx("Kreis offen")
    e.fixtures = [EfxFixture(fid=1)]
    e.open_beam = True
    assert stufen.bausteine_von(e).text() == "Dimmer · Bewegung"
    e.fixtures = []
    assert stufen.bausteine_von(e).text() == "—", "ohne Geraete schreibt sie nichts"


def test_bausteine_szene_nur_mit_kanal_auskunft():
    fm = FunctionManager()
    s = fm.new_scene("Rot")
    s.set_value(1, 1, 255)
    s.set_value(1, 2, 255)
    ohne = stufen.bausteine_von(s)
    assert ohne.unbekannt and ohne.text() == "unbekannt"
    tabelle = {(1, 1): "intensity", (1, 2): "color_r"}
    mit = stufen.bausteine_von(s, kanal_attribut=lambda f, k: tabelle.get((f, k)))
    assert not mit.unbekannt and mit.text() == "Dimmer · Farbe"
    halb = stufen.bausteine_von(
        s, kanal_attribut=lambda f, k: "pan" if k == 1 else None)
    assert halb.unbekannt and halb.text() == "Bewegung · unbekannt"


def test_bausteine_shutter_ist_kein_dimmer():
    assert stufen.baustein_fuer_attribut("shutter") == stufen.SONSTIGES
    assert stufen.baustein_fuer_attribut("strobe") == stufen.SONSTIGES
    assert stufen.baustein_fuer_attribut("intensity#1") == stufen.DIMMER
    assert stufen.baustein_fuer_attribut("gobo_wheel") == stufen.GOBO
    assert stufen.baustein_fuer_attribut("color_w") == stufen.FARBE
    assert stufen.baustein_fuer_attribut("tilt_fine") == stufen.BEWEGUNG


def test_bausteine_sammlung_vereint_ihre_mitglieder():
    from src.core.engine.rgb_matrix import MatrixStyle
    fm = FunctionManager()
    m = fm.new_rgb_matrix("M")
    m.style = MatrixStyle.DIMMER
    e = fm.new_efx("Kreis")
    from src.core.engine.efx import EfxFixture
    e.fixtures = [EfxFixture(fid=1)]
    c = fm.new_collection("Paket")
    c.function_ids = [m.id, e.id]
    assert stufen.bausteine_von(c, fm.get).text() == "Dimmer · Bewegung"
    c.function_ids = [m.id, 99999]          # totes Mitglied -> ehrlich unbekannt
    b = stufen.bausteine_von(c, fm.get)
    assert b.unbekannt and "Dimmer" in b.text()
    assert stufen.bausteine_von(c).unbekannt       # ohne Aufloeser nicht raten


def test_bausteine_skript_ist_unbekannt_audio_schreibt_nichts():
    fm = FunctionManager()
    a = fm.new_audio("Ton")
    assert stufen.bausteine_von(a).text() == "—"

    class _Skript:
        is_script = True
    assert stufen.bausteine_von(_Skript()).text() == "unbekannt"


def test_modify_kennzeichen_ohne_eng37_nie_wahr():
    """Ohne ENG-37 gibt es kein Feld ``modify`` — nichts darf brechen."""
    fm = FunctionManager()
    m = fm.new_rgb_matrix("M")
    if not hasattr(m, "modify"):
        assert stufen.ist_modify(m) is False

    class _Modify:
        modify = True

        def modify_wirksam(self):
            return True

    class _NurHaken:
        modify = True

        def modify_wirksam(self):
            return False

    assert stufen.ist_modify(_Modify()) is True
    assert stufen.ist_modify(_NurHaken()) is False
    assert stufen.ist_modify(object()) is False

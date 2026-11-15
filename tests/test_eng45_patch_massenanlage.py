"""ENG-45: viele Geräte auf einmal anlegen ist nicht mehr quadratisch.

Gemessen (backlog.d/ENG-45.md): innerhalb von ``patch_sammeln`` lud
``add_fixture`` je Gerät die GANZE Geräteliste aus der Show-DB neu
(``_reload_patch_cache``), ``remove_fixture`` beim Rückgängig ebenso — 2000
Geräte: 2001 Neuladungen und ~2 Mio. geladene Zeilen je Richtung. Jetzt wird
im Sammelweg nur die eine Zeile nachgetragen bzw. ausgetragen; der volle
Neuaufbau läuft wie bisher EINMAL am Ende.

Geprüft wird über ZÄHLER, nicht über die Uhr (QA-71): Neuladungen,
vollständige Tabellen-Abfragen und geladene Zeilen wachsen nicht mehr mit der
Gerätezahl. Und: das Ergebnis ist exakt dasselbe wie auf dem alten Weg —
Patch, Adressen, Nummern, Positionen, Kopf-Gruppen, Render-Plan und
Rückgängig-Stand, an 50 Geräten mit Mehrkopf-Balken, Doppel-Tilt-Spider und
einem Netzwerk-Laser auf Platzhalter-Adresse (ENG-20b).

Echter ``AppState`` mit eigener Show-Datei unter ``tmp_path``, frisch
geseedete Bibliothek (``_fixture_quelle.frische_library``).
"""
from __future__ import annotations

import contextlib
import json
import os
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                       # noqa: E402
from src.core import patch_tabelle as T                              # noqa: E402
from src.core.database.models import FixtureGroup, PatchedFixture    # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from _fixture_quelle import frische_library                          # noqa: E402

PAR = "Stage Light ZQ01424"          # Generic, 8-Kanal RGBW (liefert LightOS mit)
HERST = "ENG45-Testwerk"
BAR = "ENG45 Test-Balken"            # 6 Köpfe RGB = 18 Kanäle
SPIDER = "ENG45 Spider"              # QLC+-Spider: pan+tilt, 2 Farbbänke
LASER = "ENG45 Netz-Laser"


class _Fall:
    """Träger für ``frische_library`` (sammelt die Aufräum-Aufrufe)."""

    def __init__(self):
        self.aufraeumen = []

    def addCleanup(self, f):
        self.aufraeumen.append(f)


def _profil(name, kurz, typ, modus, kanaele):
    return {"manufacturer": HERST, "short_mfr": "ENG45", "name": name,
            "short_name": kurz, "fixture_type": typ, "source": "user",
            "modes": [{"name": modus, "channel_count": len(kanaele),
                       "channels": [{"name": n, "attribute": a}
                                    for n, a in kanaele]}]}


@pytest.fixture(scope="module")
def bib():
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile
    fall = _Fall()
    motor = frische_library(fall)
    try:
        balken = [(f"{c} {k}", a) for k in range(1, 7)
                  for c, a in (("Rot", "color_r"), ("Grün", "color_g"),
                               ("Blau", "color_b"))]
        spider = [("Motor 1", "pan"), ("Motor 2", "tilt"),
                  ("Rot 1", "color_r"), ("Grün 1", "color_g"), ("Blau 1", "color_b"),
                  ("Rot 2", "color_r"), ("Grün 2", "color_g"), ("Blau 2", "color_b"),
                  ("Dimmer", "dimmer")]
        laser = [("Betriebsart", "macro"), ("Muster", "laser_bank"),
                 ("X", "laser_x"), ("Y", "laser_y"), ("Farbe", "laser_color")]
        fdb.create_user_profile(_profil(BAR, "ENG45BAR", "led_bar",
                                        "18 Channel Mode", balken), engine=motor)
        sid = fdb.create_user_profile(_profil(SPIDER, "ENG45SPIDER", "moving_head",
                                              "9 Channel", spider), engine=motor)
        fdb.create_user_profile(_profil(LASER, "ENG45LASER", "laser",
                                        "DMX Mode", laser), engine=motor)
        # Doppel-Tilt erkennt LightOS nur bei QLC+-Importen (fixture_db).
        with Session(motor) as s:
            s.get(FixtureProfile, sid).source = "qlcplus"
            s.commit()
        A.clear_channel_cache()
        b = T.bibliothek_aus_db()
        assert b.finde("Generic", PAR).profil is not None
        assert b.finde(HERST, BAR).profil is not None
        yield b
    finally:
        A.clear_channel_cache()
        for f in reversed(fall.aufraeumen):
            f()


def _oeffne(pfad):
    get_undo_stack().clear()
    st = A.AppState()
    st.open_show(str(pfad))
    return st


def _schliesse(st):
    get_undo_stack().clear()
    try:
        st._show_engine.dispose()
    except Exception:
        pass


@pytest.fixture
def state(tmp_path):
    st = _oeffne(tmp_path / "show.db")
    yield st
    _schliesse(st)


def _par_tabelle(n: int) -> str:
    """n PARs, 64 je Universum."""
    zeilen = ["Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl"]
    u = 1
    while n > 0:
        k = min(64, n)
        zeilen.append(f"PAR {u};Generic;{PAR};8-Kanal RGBW;{u};1;{k}")
        n, u = n - k, u + 1
    return "\n".join(zeilen) + "\n"


def _plan(state, bib, text):
    plan = T.baue_plan(T.lies_tabelle(text), bib, T.belegung_aus_state(state))
    assert all(z.status == T.ANLEGBAR for z in plan.zeilen), \
        [z.status_text for z in plan.zeilen]
    return plan


class Zaehler:
    """Zählt während eines Blocks: volle Neuladungen der Geräteliste, Abfragen
    der GANZEN Patch-Tabelle (ohne WHERE), alle Abfragen, geladene Geräte-
    Zeilen und Resyncs der View-Registry."""

    def __init__(self, state, monkeypatch):
        from sqlalchemy import event
        self.werte = {}
        self._null()
        orig = state._reload_patch_cache

        def neu_laden():
            self.werte["neuladen"] += 1
            return orig()
        monkeypatch.setattr(state, "_reload_patch_cache", neu_laden)
        orig_resync = state._view_registry.resync_all

        def resync():
            self.werte["resync"] += 1
            return orig_resync()
        monkeypatch.setattr(state._view_registry, "resync_all", resync)

        def abfrage(conn, cursor, sql, params, context, executemany):
            self.werte["sql"] += 1
            klein = sql.lower()
            if ("from patched_fixtures" in klein and "where" not in klein
                    and "max(" not in klein):
                self.werte["ganze_tabelle"] += 1

        def geladen(ziel, context):
            self.werte["zeilen"] += 1
        event.listen(state._show_engine, "before_cursor_execute", abfrage)
        event.listen(PatchedFixture, "load", geladen)
        self._weg = lambda: (
            event.remove(state._show_engine, "before_cursor_execute", abfrage),
            event.remove(PatchedFixture, "load", geladen))

    def _null(self):
        self.werte.update(neuladen=0, resync=0, sql=0, ganze_tabelle=0, zeilen=0)

    def nimm(self) -> dict:
        w = dict(self.werte)
        self._null()
        return w

    def ende(self):
        self._weg()


def _massen_lauf(tmp_path, bib, monkeypatch, n):
    st = _oeffne(tmp_path / f"zaehl_{n}.db")
    z = Zaehler(st, monkeypatch)
    try:
        plan = _plan(st, bib, _par_tabelle(n))
        z.nimm()
        erg = T.wende_an(st, plan, bib)
        assert erg.geraete == n and not erg.fehler
        anlegen = z.nimm()
        assert get_undo_stack().undo()
        assert st.get_patched_fixtures() == []
        rueck = z.nimm()
        assert get_undo_stack().redo()
        assert len(st.get_patched_fixtures()) == n
        wieder = z.nimm()
        return anlegen, rueck, wieder
    finally:
        z.ende()
        _schliesse(st)


# ── Zähler: nichts wächst mehr mit der Gerätezahl (statt Wanduhr) ────────────

def test_zaehler_wachsen_nicht_mit_der_geraetezahl(tmp_path, bib, monkeypatch):
    klein, gross = 40, 160
    l_klein = _massen_lauf(tmp_path, bib, monkeypatch, klein)
    l_gross = _massen_lauf(tmp_path, bib, monkeypatch, gross)
    for name, a, b in zip(("anlegen", "rückgängig", "wiederholen"), l_klein, l_gross):
        # EIN voller Neuaufbau am Ende — vorher einer je Gerät (+1)
        assert a["neuladen"] == b["neuladen"] == 1, (name, a, b)
        # die ganze Tabelle wird nicht mehr je Gerät gelesen
        assert a["ganze_tabelle"] == b["ganze_tabelle"] <= 2, (name, a, b)
        # je Gerät gleich viele Abfragen: genau linear, höchstens 5 je Gerät
        je = (b["sql"] - a["sql"]) / (gross - klein)
        assert je == int(je) and je <= 5, (name, a, b)
        assert a["sql"] - je * klein == b["sql"] - je * gross, (name, a, b)
        # geladene Geräte-Zeilen linear (vorher ~n²/2: bei 160 rund 13 000)
        assert b["zeilen"] <= 2 * gross + 2, (name, b)
        # die View-Registry wird auf diesem Weg gar nicht angefasst
        assert a["resync"] == b["resync"] == 0, (name, a, b)


def test_einzel_anlegen_bleibt_der_alte_weg(state, bib, monkeypatch):
    """Ein Gerät im Patch-Dialog (ohne Sammeln): voller Neuaufbau wie immer."""
    z = Zaehler(state, monkeypatch)
    try:
        nachtragen = []
        monkeypatch.setattr(state, "_patch_cache_nachtragen",
                            lambda fid: nachtragen.append(fid))
        fid = state.add_fixture(_par(bib, 1, 1))
        assert z.nimm()["neuladen"] == 1 and nachtragen == []
        assert [f.fid for f in state.get_patched_fixtures()] == [fid]
        assert sorted(state._fix_index) == [fid]           # Render-Plan sofort
        state.remove_fixture(fid)
        assert z.nimm()["neuladen"] == 1
        assert state.get_patched_fixtures() == [] and state._fix_index == {}
    finally:
        z.ende()


# ── Gleichheit: alter Weg / neuer Weg an 50 Geräten ─────────────────────────

def _par(bib, fid, adresse, name="X", universum=1):
    par = bib.finde("Generic", PAR).profil
    return PatchedFixture(
        fid=fid, label=name, fixture_profile_id=par.id, mode_name="8-Kanal RGBW",
        universe=universum, address=adresse, channel_count=8,
        manufacturer_name="Generic", fixture_name=PAR, fixture_type="par")


def _gemischte_tabelle() -> str:
    """49 Geräte: 40 PARs, 4 Mehrkopf-Balken, 5 Doppel-Tilt-Spider."""
    return ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"PAR;Generic;{PAR};8-Kanal RGBW;1;1;40\n"
            f"Balken;{HERST};{BAR};18 Channel Mode;2;1;4\n"
            f"Spider;{HERST};{SPIDER};9 Channel;2;200;5\n")


def _netz_laser(state, bib):
    """ENG-20b: Netzwerk-Laser mit Platzhalter-Adresse MITTEN auf den PARs."""
    p = bib.finde(HERST, LASER).profil
    return PatchedFixture(
        fid=state.next_fid(), label="Netz-Laser", fixture_profile_id=p.id,
        mode_name="DMX Mode", universe=1, address=1, channel_count=5,
        manufacturer_name=HERST, fixture_name=LASER, fixture_type="laser",
        protocol="etherdream", net_host="192.0.2.10")


def _massenschritt(state, bib):
    """Der Massenweg: Tabellen-Import + ein weiteres Gerät, EIN Schritt."""
    stack = get_undo_stack()
    with state.patch_sammeln(), stack.gruppe("Massen", rahmen=state.patch_sammeln):
        erg = T.wende_an(state, _plan(state, bib, _gemischte_tabelle()), bib)
        assert erg.geraete == 49 and not erg.fehler, erg.fehler
        state.add_fixture(_netz_laser(state, bib))


def _alter_weg(state):
    """Den Stand VOR ENG-45 nachstellen: im Sammelweg je Gerät die ganze
    Liste neu laden und linear suchen (kein Index)."""
    state._patch_cache_nachtragen = lambda fid: state._reload_patch_cache()
    state._patch_cache_austragen = lambda fid: state._reload_patch_cache()
    state._sammel_index = lambda: None


def _bild(state):
    from sqlalchemy import select
    with state._session() as s:
        gruppen = [(g.name, g.cols, g.rows, g.positions_json, g.folder)
                   for g in s.execute(select(FixtureGroup).order_by(FixtureGroup.id)).scalars()]
        db = [state._fixture_to_dict(f) for f in s.execute(
            select(PatchedFixture).order_by(PatchedFixture.fid)).scalars()]
    stack = get_undo_stack()
    return {
        "patch": [state._fixture_to_dict(f) for f in state.get_patched_fixtures()],
        "db": db,
        "gruppen": gruppen,
        "positionen": dict(state.visualizer_positions),
        "plan": (sorted(state._fix_index),
                 {u: sorted(a) for u, a in state._patched_set.items()},
                 {u: sorted(a) for u, a in state._laser_estop_addrs.items()},
                 sorted(state._laser_fids)),
        "universen": sorted(state.universes),
        "undo": ([c.label for c in stack._undo], [c.label for c in stack._redo]),
    }


def test_ergebnis_gleicht_dem_alten_weg_an_50_geraeten(tmp_path, bib):
    bilder = {}
    for weg in ("alt", "neu"):
        st = _oeffne(tmp_path / f"{weg}.db")
        try:
            # ein Altbestand, damit Adressen und Nummern weiterzählen
            st.add_fixture(_par(bib, 1, 400, "Bestand"), undoable=False)
            if weg == "alt":
                _alter_weg(st)
            hinweise = []
            st.subscribe(lambda e, d=None: hinweise.append(d) if e == "hinweis" else None)
            stack = get_undo_stack()
            folge = []
            _massenschritt(st, bib)
            folge.append(_bild(st))
            assert stack.undo()
            folge.append(_bild(st))
            assert stack.redo()
            folge.append(_bild(st))
            assert stack.undo()
            folge.append(_bild(st))
            bilder[weg] = (folge, hinweise)
        finally:
            _schliesse(st)
    alt, neu = bilder["alt"], bilder["neu"]
    assert neu == alt
    nach_anlegen = alt[0][0]
    assert len(nach_anlegen["patch"]) == 51
    assert nach_anlegen["patch"] == nach_anlegen["db"]
    assert sum(1 for f in nach_anlegen["patch"] if f["spider_dual_tilt"]) == 5
    laser = [f for f in nach_anlegen["patch"] if f["protocol"] == "etherdream"]
    assert len(laser) == 1 and (laser[0]["universe"], laser[0]["address"]) == (1, 1)
    # der Platzhalter belegt keinen DMX-Kanal, die PARs ab 1 stehen trotzdem
    assert [f["address"] for f in nach_anlegen["patch"]
            if f["label"].startswith("PAR")][:2] == [1, 9]
    # Kopf-Gruppen: 4 Balken + 5 Spider (zwei Farbbaenke)
    assert len([g for g in nach_anlegen["gruppen"] if g[4] == "Multi-Head"]) == 9
    assert nach_anlegen["undo"][0][-1] == "Massen"
    # Rückgängig: nur der Altbestand bleibt
    assert [f["label"] for f in alt[0][1]["patch"]] == ["Bestand"]


def test_fid_waechter_findet_eine_verwaiste_zeile_auch_im_sammelweg(state, bib):
    """FLD-FID unverändert: steht eine Nummer nur in der DB (Cache/DB-
    Desync), weicht das neue Gerät aus — die Abfrage fragt jetzt nur nach
    dieser einen Nummer."""
    state.add_fixture(_par(bib, 1, 1), undoable=False)
    with state._session() as s:                       # Waise an der DB vorbei
        s.add(_par(bib, 2, 100, "Waise"))
        s.commit()
    with state.patch_sammeln():
        fid = state.add_fixture(_par(bib, 2, 200, "Neu"))
        assert fid != 2 and fid == 3
        # ein Gerät auf eine im Cache belegte Nummer weicht ebenfalls aus
        fid2 = state.add_fixture(_par(bib, 1, 300, "Neu2"))
        assert fid2 == 4
    labels = {f.fid: f.label for f in state.get_patched_fixtures()}
    assert labels == {1: "X", 2: "Waise", 3: "Neu", 4: "Neu2"}


def test_liste_im_block_bleibt_sortiert_und_wird_nie_veraendert(state, bib):
    """Andere Threads lesen ``_patch_cache`` ohne Sperre: im Sammelweg wird
    immer eine NEUE Liste gesetzt, nach fid sortiert wie beim Neuladen."""
    state.add_fixture(_par(bib, 5, 1), undoable=False)
    state.add_fixture(_par(bib, 9, 20), undoable=False)
    with state.patch_sammeln():
        alt = state._patch_cache
        alt_inhalt = list(alt)
        state.add_fixture(_par(bib, 7, 40))               # mitten hinein
        state.add_fixture(_par(bib, 12, 60))              # ans Ende
        assert alt == alt_inhalt and state._patch_cache is not alt
        assert [f.fid for f in state.get_patched_fixtures()] == [5, 7, 9, 12]
        vorher = state._patch_cache
        state.remove_fixture(9)
        assert [f.fid for f in vorher] == [5, 7, 9, 12]
        assert [f.fid for f in state.get_patched_fixtures()] == [5, 7, 12]
        assert state.next_fid() == 13
        assert state._fix_index.keys() == {5, 9}           # Plan erst am Ende
    assert sorted(state._fix_index) == [5, 7, 12]
    assert state._patch_sammel_idx is None


def test_viele_loeschen_in_der_patch_ansicht_baut_einmal_neu(state, bib, monkeypatch):
    """Patch-Ansicht, mehrere Zeilen markiert, „Löschen“: EIN patch_changed,
    EIN Neuaufbau; jedes Gerät bleibt ein eigener Rückgängig-Schritt."""
    import src.ui.views.patch_view as PV
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    with state.patch_sammeln():
        for i in range(30):
            state.add_fixture(_par(bib, i + 1, 1 + 8 * i, f"P{i}"), undoable=False)
    monkeypatch.setattr(PV, "get_state", lambda: state)
    view = PV.PatchView()
    view._refresh() if hasattr(view, "_refresh") else None
    assert view._table.rowCount() == 30
    view._table.selectAll()
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    ereignisse = []
    state.subscribe(lambda e, d=None: ereignisse.append(e))
    z = Zaehler(state, monkeypatch)
    try:
        get_undo_stack().clear()
        view._delete_selected()
        w = z.nimm()
    finally:
        z.ende()
    assert state.get_patched_fixtures() == [] and state._fix_index == {}
    assert ereignisse.count("patch_changed") == 1
    assert w["neuladen"] == 1 and w["ganze_tabelle"] <= 2
    assert len(get_undo_stack()._undo) == 30
    assert get_undo_stack().undo()
    assert [f.label for f in state.get_patched_fixtures()] == ["P29"]
    view.deleteLater()


# ── Abwärtskompatibel: eine Alt-Show laden, danach massenhaft anlegen ───────

def test_alt_show_laden_und_massenanlage_daneben(tmp_path, state, bib, monkeypatch):
    from src.core.show import show_file
    monkeypatch.setattr(A, "_state", state, raising=False)
    state.add_fixture(_par(bib, 1, 1, "Alt A"), undoable=False)
    state.add_fixture(_par(bib, 2, 9, "Alt B"), undoable=False)
    datei = tmp_path / "alt.lshow"
    show_file.save_show(str(datei))
    # Alt-Show nachstellen: Felder, die es früher nicht gab, fehlen
    with zipfile.ZipFile(datei) as zf:
        daten = json.loads(zf.read("show.json").decode("utf-8"))
    for eintrag in daten["patch"]:
        for neu in ("head_mode", "protocol", "net_host", "pixel_order",
                    "element_rotation", "element_flip"):
            eintrag.pop(neu, None)
    daten.pop("erstellt_mit", None)
    alt_datei = tmp_path / "alt_ohne_neue_felder.lshow"
    with zipfile.ZipFile(alt_datei, "w") as zf:
        zf.writestr("show.json", json.dumps(daten))
    show_file.reset_show()
    ok, meldung = show_file.load_show(str(alt_datei))
    assert ok, meldung
    geladen = [state._fixture_to_dict(f) for f in state.get_patched_fixtures()]
    assert [(f["label"], f["address"], f["protocol"], f["head_mode"])
            for f in geladen] == [("Alt A", 1, "dmx", "auto"), ("Alt B", 9, "dmx", "auto")]
    get_undo_stack().clear()
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"PAR;Generic;{PAR};8-Kanal RGBW;1;17;30\n")
    erg = T.wende_an(state, _plan(state, bib, text), bib)
    assert erg.geraete == 30
    assert [f.address for f in state.get_patched_fixtures()][2] == 17
    assert get_undo_stack().undo()
    assert [state._fixture_to_dict(f) for f in state.get_patched_fixtures()] == geladen

"""IMP-3, Teil 3: der Tabellen-Import baut den Patch EINMAL neu auf.

Echter ``AppState`` mit eigener Show-Datei unter ``tmp_path`` (wie
``test_imp1_patch_tabelle_anwenden``). Geprüft wird ``state.patch_sammeln()``
selbst und der Import darüber: ein ``patch_changed`` je Import, Rückgängig und
Wiederholen; dasselbe Ergebnis wie auf dem alten Weg (ein Neuaufbau je Gerät);
ein importierter Laser steht am Ende im Render-Plan (NOT-AUS/Blackout).
"""
from __future__ import annotations

import contextlib
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A                                       # noqa: E402
from src.core import patch_tabelle as T                              # noqa: E402
from src.core.database.models import FixtureGroup, PatchedFixture    # noqa: E402
from src.core.undo import UndoStack, get_undo_stack                  # noqa: E402

PAR = "Stage Light ZQ01424"          # Generic, 8-Kanal RGBW
MH = "ZQ02001 Mini Moving Head"      # U King, 11-Kanal
LASER = "Galaxian 3D"                # American DJ, Typ laser, „DMX Mode“ (5)
BAR = "Mega Tri Bar"                 # American DJ, Mehrkopf: „54 Channel Mode“


@pytest.fixture(scope="module")
def bib():
    return T.bibliothek_aus_db()


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


class Mithoerer:
    def __init__(self, state):
        self.ereignisse: list[str] = []
        state.subscribe(lambda ereignis, daten=None: self.ereignisse.append(ereignis))

    def zahl(self, ereignis: str) -> int:
        return self.ereignisse.count(ereignis)

    def leeren(self):
        self.ereignisse.clear()


def _tabelle(n: int = 12) -> str:
    """n PARs, dazu ein Moving Head, ein Mehrkopf-Balken und ein Laser."""
    return ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"PAR;Generic;{PAR};8-Kanal RGBW;1;1;{n}\n"
            f"Kopf;U King;{MH};11-Kanal;2;1;1\n"
            f"Balken;American DJ;{BAR};54 Channel Mode;2;100;2\n"
            f"Laser;American DJ;{LASER};DMX Mode;3;10;1\n")


def _plan(state, bib, text):
    plan = T.baue_plan(T.lies_tabelle(text), bib, T.belegung_aus_state(state))
    assert all(z.status == T.ANLEGBAR for z in plan.zeilen), \
        [z.status_text for z in plan.zeilen]
    return plan


def _bild(state):
    """Was am Ende im Patch steht — in der Reihenfolge der Geräteliste."""
    return [(f.fid, f.label, f.fixture_profile_id, f.mode_name, f.universe,
             f.address, f.channel_count, bool(f.spider_dual_tilt))
            for f in state.get_patched_fixtures()]


def _gruppen(state):
    from sqlalchemy import select
    with state._session() as s:
        return [(g.id, g.name, g.cols, g.rows, g.positions_json, g.folder)
                for g in s.execute(select(FixtureGroup).order_by(FixtureGroup.id)).scalars()]


def _plan_bild(state):
    """Der Render-Plan, soweit er sich vergleichen lässt."""
    return (sorted(state._fix_index),
            {u: sorted(a) for u, a in state._patched_set.items()},
            {u: sorted(a) for u, a in state._laser_estop_addrs.items()},
            sorted(state._laser_fids))


def _ohne_sammeln(state):
    """Den alten Weg nachstellen: kein Sammeln, ein Neuaufbau je Gerät."""
    state.patch_sammeln = contextlib.nullcontext


# ── Der Import: ein patch_changed je Import / Rückgängig / Wiederholen ───────

def test_import_sendet_patch_changed_genau_einmal(state, bib):
    ohr = Mithoerer(state)
    ergebnis = T.wende_an(state, _plan(state, bib, _tabelle()), bib)
    assert ergebnis.geraete == 16 and not ergebnis.fehler
    assert ohr.zahl("patch_changed") == 1
    assert ohr.zahl("group_changed") <= 1
    # der Laser-Hinweis und andere Ereignisse sind nicht verschluckt
    assert len(state.get_patched_fixtures()) == 16


def test_rueckgaengig_und_wiederholen_senden_je_einmal(state, bib):
    T.wende_an(state, _plan(state, bib, _tabelle()), bib)
    davor = _bild(state)
    gruppen_davor = _gruppen(state)
    stack = get_undo_stack()
    ohr = Mithoerer(state)

    assert stack.undo()
    assert ohr.zahl("patch_changed") == 1 and ohr.zahl("group_changed") <= 1
    assert state.get_patched_fixtures() == [] and _gruppen(state) == []
    assert _plan_bild(state) == ([], {}, {}, [])

    ohr.leeren()
    assert stack.redo()
    assert ohr.zahl("patch_changed") == 1 and ohr.zahl("group_changed") <= 1
    assert _bild(state) == davor
    assert [g[1:] for g in _gruppen(state)] == [g[1:] for g in gruppen_davor]

    ohr.leeren()
    assert stack.undo()
    assert ohr.zahl("patch_changed") == 1
    assert state.get_patched_fixtures() == []


def test_ergebnis_gleicht_dem_alten_weg(tmp_path, bib):
    """Adressen, Namen, Reihenfolge, Nummern, Kopf-Gruppen (mit ihren IDs),
    Render-Plan und die übrigen Ereignisse: wie mit einem Neuaufbau je Gerät."""
    bilder = []
    for weg in ("alt", "neu"):
        st = _oeffne(tmp_path / f"{weg}.db")
        try:
            if weg == "alt":
                _ohne_sammeln(st)
            ohr = Mithoerer(st)
            T.wende_an(st, _plan(st, bib, _tabelle()), bib)
            hinweise = ohr.zahl("hinweis")
            bild = [_bild(st), _gruppen(st), _plan_bild(st), hinweise]
            get_undo_stack().undo()
            bild.append([_bild(st), _gruppen(st), _plan_bild(st)])
            get_undo_stack().redo()
            bild.append([_bild(st), [g[1:] for g in _gruppen(st)], _plan_bild(st)])
            bilder.append((bild, ohr.zahl("patch_changed")))
        finally:
            _schliesse(st)
    (alt, alt_n), (neu, neu_n) = bilder
    assert neu == alt
    assert alt[1], "die Tabelle soll mindestens eine Kopf-Gruppe erzeugen"
    assert alt_n == 3 * 16 and neu_n == 3          # Import, Rückgängig, Wiederholen


# ── Sicherheit: der Render-Plan ist am Ende aktuell ──────────────────────────

def test_importierter_laser_ist_sofort_in_not_aus_und_blackout_erfasst(state, bib):
    assert not state._laser_fids
    ergebnis = T.wende_an(state, _plan(state, bib, _tabelle(3)), bib)
    laser = next(f for f in state.get_patched_fixtures() if f.label == "Laser")
    assert laser.fid in ergebnis.fids
    assert laser.fid in state._laser_fids
    assert set(range(10, 15)) <= set(state._laser_estop_addrs[3])
    assert set(state._fix_index) == set(ergebnis.fids)
    # … und nach dem Rückgängig wieder draußen
    get_undo_stack().undo()
    assert not state._laser_fids and not state._laser_estop_addrs.get(3)


def test_laser_hinweis_kommt_im_sammelweg_weiter_je_geraet(state, bib):
    ohr = Mithoerer(state)
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"Laser;American DJ;{LASER};DMX Mode;1;1;2\n")
    hinweise = []
    state.subscribe(lambda e, d=None: hinweise.append(d) if e == "hinweis" else None)
    T.wende_an(state, _plan(state, bib, text), bib)
    assert ohr.zahl("patch_changed") == 1
    assert len(state._laser_fids) == 2
    # „hinweis“ gehört nicht zu den gesammelten Ereignissen
    assert "hinweis" not in state._PATCH_SAMMEL_EREIGNISSE
    assert ohr.zahl("hinweis") == len(hinweise)


# ── patch_sammeln() selbst ───────────────────────────────────────────────────

def _par(state, bib, fid, adresse, name="X"):
    par = bib.finde("Generic", PAR).profil
    return PatchedFixture(
        fid=fid, label=name, fixture_profile_id=par.id, mode_name="8-Kanal RGBW",
        universe=1, address=adresse, channel_count=8, manufacturer_name="Generic",
        fixture_name=PAR, fixture_type="par")


def test_im_block_stimmt_die_geraeteliste_der_plan_erst_am_ende(state, bib):
    ohr = Mithoerer(state)
    with state.patch_sammeln():
        state.add_fixture(_par(state, bib, 1, 1))
        state.add_fixture(_par(state, bib, state.next_fid(), 9))
        assert [f.fid for f in state.get_patched_fixtures()] == [1, 2]
        assert state._fix_index == {} and ohr.zahl("patch_changed") == 0
    assert sorted(state._fix_index) == [1, 2]
    assert ohr.zahl("patch_changed") == 1


def test_verschachtelt_baut_und_sendet_nur_die_aeusserste_ebene(state, bib):
    ohr = Mithoerer(state)
    with state.patch_sammeln():
        with state.patch_sammeln():
            state.add_fixture(_par(state, bib, 1, 1))
        assert ohr.zahl("patch_changed") == 0 and state._fix_index == {}
        state.add_fixture(_par(state, bib, 2, 9))
    assert ohr.zahl("patch_changed") == 1 and sorted(state._fix_index) == [1, 2]
    assert state._patch_sammel_tiefe == 0 and state._patch_sammel_thread is None


def test_ausnahme_im_block_baut_und_sendet_trotzdem(state, bib):
    ohr = Mithoerer(state)
    with pytest.raises(RuntimeError):
        with state.patch_sammeln():
            state.add_fixture(_par(state, bib, 1, 1))
            raise RuntimeError("mittendrin")
    assert ohr.zahl("patch_changed") == 1
    assert sorted(state._fix_index) == [1] and state._patch_sammel_tiefe == 0
    # danach arbeitet der Einzelweg wieder wie immer
    state.add_fixture(_par(state, bib, 2, 9))
    assert ohr.zahl("patch_changed") == 2 and sorted(state._fix_index) == [1, 2]


def test_block_ohne_patch_aenderung_baut_und_sendet_nichts(state, monkeypatch):
    ohr = Mithoerer(state)
    gebaut = []
    monkeypatch.setattr(state, "_rebuild_render_plan", lambda: gebaut.append(1))
    with state.patch_sammeln():
        state._emit("hinweis", "geht sofort durch")
        assert ohr.ereignisse == ["hinweis"]
    assert gebaut == [] and ohr.ereignisse == ["hinweis"]


def test_ereignis_mit_daten_und_fremder_thread_gehen_sofort_durch(state):
    ohr = Mithoerer(state)
    with state.patch_sammeln():
        state._emit("group_changed", {"id": 7})          # mit Daten: sofort
        assert ohr.zahl("group_changed") == 1
        state.notify_groups_changed()                    # ohne Daten: gemerkt
        assert ohr.zahl("group_changed") == 1

        def fremd():
            assert not state._patch_sammelt()
            state._emit("patch_changed")
        t = threading.Thread(target=fremd)
        t.start()
        t.join(5)
        assert ohr.zahl("patch_changed") == 1
    assert ohr.zahl("group_changed") == 2
    assert ohr.zahl("patch_changed") == 1                # im Block nichts gemerkt


def test_ausnahme_mitten_im_import_hinterlaesst_konsistenten_zustand(state, bib, monkeypatch):
    """Das dritte Gerät lässt sich nicht anlegen: der Rest steht im Patch UND
    im Render-Plan, es gab ein patch_changed, und EIN Rückgängig nimmt alles."""
    echt = state.add_fixture
    rufe = []

    def add(fixture, undoable=True):
        rufe.append(fixture.label)
        if len(rufe) == 3:
            raise RuntimeError("Datenbank weg")
        return echt(fixture, undoable)

    monkeypatch.setattr(state, "add_fixture", add)
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse\n"
            + "".join(f"P{i};Generic;{PAR};8-Kanal RGBW;1;{1 + 8 * i}\n" for i in range(5)))
    ohr = Mithoerer(state)
    ergebnis = T.wende_an(state, _plan(state, bib, text), bib)
    assert ergebnis.geraete == 4 and len(ergebnis.fehler) == 1
    assert "P2" in ergebnis.fehler[0]
    assert [f.label for f in state.get_patched_fixtures()] == ["P0", "P1", "P3", "P4"]
    assert sorted(state._fix_index) == sorted(ergebnis.fids)
    assert ohr.zahl("patch_changed") == 1
    assert state._patch_sammel_tiefe == 0
    assert get_undo_stack().undo()
    assert state.get_patched_fixtures() == [] and state._fix_index == {}


def test_ausnahme_die_den_import_abbricht(state, bib, monkeypatch):
    """Wirft etwas, das wende_an NICHT abfängt (hier: next_fid), ist der
    Zustand trotzdem geschlossen: Plan aktuell, ein patch_changed, ein Schritt."""
    echt = state.next_fid
    rufe = []

    def next_fid():
        rufe.append(1)
        if len(rufe) == 3:
            raise KeyboardInterrupt()
        return echt()

    monkeypatch.setattr(state, "next_fid", next_fid)
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse\n"
            + "".join(f"P{i};Generic;{PAR};8-Kanal RGBW;1;{1 + 8 * i}\n" for i in range(5)))
    ohr = Mithoerer(state)
    with pytest.raises(KeyboardInterrupt):
        T.wende_an(state, _plan(state, bib, text), bib)
    assert [f.label for f in state.get_patched_fixtures()] == ["P0", "P1"]
    assert sorted(state._fix_index) == [f.fid for f in state.get_patched_fixtures()]
    assert ohr.zahl("patch_changed") == 1 and state._patch_sammel_tiefe == 0
    assert get_undo_stack().undo() and state.get_patched_fixtures() == []


# ── Rückgängig-Gruppe mit Rahmen ─────────────────────────────────────────────

def test_undo_gruppe_legt_den_rahmen_um_rueckgaengig_und_wiederholen():
    stack = UndoStack()
    spur = []

    @contextlib.contextmanager
    def rahmen():
        spur.append("auf")
        try:
            yield
        finally:
            spur.append("zu")

    with stack.gruppe("Zwei", rahmen=rahmen):
        for i in (1, 2):
            stack.push_simple(f"T{i}", lambda: None, lambda i=i: spur.append(f"u{i}"))
    assert spur == []                                    # der Block selbst: kein Rahmen
    stack.undo()
    assert spur == ["auf", "u2", "u1", "zu"]
    spur.clear()
    stack.redo()
    assert spur == ["auf", "zu"]


# ── Laufzeit ─────────────────────────────────────────────────────────────────

def test_sechzig_geraete_deutlich_schneller_als_einzeln(tmp_path, bib):
    """60 Geräte: gesammelt deutlich schneller als mit einem Neuaufbau je
    Gerät. Verglichen wird im selben Lauf (die Maschine ist für beide gleich
    schnell), dazu eine großzügige feste Grenze."""
    text = ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"PAR;Generic;{PAR};8-Kanal RGBW;1;1;60\n")
    dauer = {}
    for weg in ("alt", "neu"):
        st = _oeffne(tmp_path / f"{weg}.db")
        try:
            if weg == "alt":
                _ohne_sammeln(st)
            plan = _plan(st, bib, text)
            t0 = time.perf_counter()
            ergebnis = T.wende_an(st, plan, bib)
            dauer[weg] = time.perf_counter() - t0
            assert ergebnis.geraete == 60 and len(st._fix_index) == 60
        finally:
            _schliesse(st)
    print(f"\n60 Geräte: einzeln {dauer['alt']:.2f} s, gesammelt {dauer['neu']:.2f} s")
    assert dauer["neu"] < dauer["alt"] * 0.75, dauer
    assert dauer["neu"] < 20.0, dauer

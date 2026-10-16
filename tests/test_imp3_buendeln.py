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


# ── Gegenprüfung: der Ausgabe-Thread WÄHREND des Sammelns ────────────────────
#
# Die Geräteliste wechselt im Block sofort, der Render-Plan erst am Ende. Der
# Renderer gab den Funktionen die NEUE Liste, rechnete aber mit dem ALTEN Plan:
# eine laufende Funktion, die ein gerade angelegtes Gerät kennt (Wiederholen
# eines Imports, wiedervergebene Gerätenummer), schrieb dessen Adressen — für
# den alten Plan „nicht gepatcht“, also über den Roh-Kanal-Weg hinaus aufs
# Kabel, an der NOT-AUS-Maske vorbei (die kennt den neuen Laser noch nicht).

def _alles_voll(universen, patch, dt):
    """Stellvertreter für eine laufende Funktion, die JEDES Gerät der
    übergebenen Geräteliste auf allen Kanälen voll aufdreht."""
    for fx in patch:
        su = universen.get(fx.universe)
        if su is None:
            continue
        for k in range(int(fx.channel_count)):
            su.set_channel(fx.address + k, 255)


def _laser(state, bib, fid, adresse, universum=3):
    profil = bib.finde("American DJ", LASER).profil
    return PatchedFixture(
        fid=fid, label="Laser", fixture_profile_id=profil.id,
        mode_name="DMX Mode", universe=universum, address=adresse,
        channel_count=5, manufacturer_name="American DJ",
        fixture_name=LASER, fixture_type="laser")


def _live(state, universum, adresse, anzahl):
    daten = state.universes[universum].get_all()
    return list(daten[adresse - 1:adresse - 1 + anzahl])


def test_laser_bleibt_im_not_aus_dunkel_auch_mitten_im_sammeln(state, bib, monkeypatch):
    monkeypatch.setattr(state.function_manager, "tick", _alles_voll)
    state.add_fixture(_par(state, bib, 1, 1))
    state.set_laser_estop(True)
    with state.patch_sammeln():
        state.add_fixture(_laser(state, bib, state.next_fid(), 10))
        state.add_fixture(_par(state, bib, state.next_fid(), 9))
        state._render_frame(0.02)          # ein Frame mitten im Sammeln
        assert _live(state, 3, 10, 5) == [0] * 5
        # der neue PAR gibt noch nichts aus, der alte läuft unverändert weiter
        assert _live(state, 1, 9, 8) == [0] * 8
        assert _live(state, 1, 1, 8) == [255] * 8
    state._render_frame(0.02)
    assert state.laser_estop_active
    assert _live(state, 3, 10, 5) == [0] * 5          # NOT-AUS deckt den Laser
    assert _live(state, 1, 9, 8) == [255] * 8         # der neue PAR ist jetzt da


def test_jeder_frame_waehrend_des_imports_haelt_den_laser_dunkel(state, bib, monkeypatch):
    """Der ganze Import, nach JEDEM angelegten Gerät ein Frame — und dasselbe
    beim Rückgängig und Wiederholen."""
    monkeypatch.setattr(state.function_manager, "tick", _alles_voll)
    state.set_laser_estop(True)
    hell: list = []
    echt_add, echt_weg = state.add_fixture, state.remove_fixture

    def _pruefe():
        state._render_frame(0.02)
        uni = state.universes.get(3)
        if uni is not None and any(uni.get_all()[9:14]):
            hell.append(list(uni.get_all()[9:14]))

    def add(*a, **k):
        try:
            return echt_add(*a, **k)
        finally:
            _pruefe()

    def weg(*a, **k):
        try:
            return echt_weg(*a, **k)
        finally:
            _pruefe()

    monkeypatch.setattr(state, "add_fixture", add)
    monkeypatch.setattr(state, "remove_fixture", weg)
    T.wende_an(state, _plan(state, bib, _tabelle(3)), bib)
    _pruefe()
    get_undo_stack().undo()
    _pruefe()
    get_undo_stack().redo()
    _pruefe()
    assert state.laser_estop_active and hell == []


def test_im_sammeln_geloeschtes_geraet_ist_danach_aus_der_ausgabe(state, bib, monkeypatch):
    monkeypatch.setattr(state.function_manager, "tick", _alles_voll)
    state.add_fixture(_par(state, bib, 1, 1))
    state.add_fixture(_par(state, bib, 2, 9))
    state._render_frame(0.02)
    assert _live(state, 1, 1, 16) == [255] * 16
    with state.patch_sammeln():
        state.remove_fixture(2)
        state._render_frame(0.02)
        # im Block gilt Plan UND Geräteliste des alten Stands — zusammen
        assert _live(state, 1, 1, 16) == [255] * 16
    assert _live(state, 1, 9, 8) == [0] * 8           # schon vor dem nächsten Frame
    state._render_frame(0.02)
    assert _live(state, 1, 1, 8) == [255] * 8
    assert _live(state, 1, 9, 8) == [0] * 8
    assert 2 not in state._fix_index


def test_ausserhalb_des_sammelns_bekommen_funktionen_die_geraeteliste_selbst(state, bib, monkeypatch):
    """Der Renderer reicht immer die Geräteliste des geltenden Plans durch.
    Ohne Sammeln ist sie inhaltlich dieselbe wie ``_patch_cache`` und nach
    jedem Einzelaufruf sofort aktuell — auch nach einem beendeten (und einem
    geplatzten) Sammelblock."""
    gesehen = []
    monkeypatch.setattr(state.function_manager, "tick",
                        lambda universen, patch, dt: gesehen.append(patch))

    def gleich_der_geraeteliste():
        state._render_frame(0.02)
        assert gesehen[-1] is state._plan_patch
        assert len(gesehen[-1]) == len(state._patch_cache)
        assert all(a is b for a, b in zip(gesehen[-1], state._patch_cache))

    state.add_fixture(_par(state, bib, 1, 1))
    gleich_der_geraeteliste()
    state.add_fixture(_par(state, bib, 4, 25))
    gleich_der_geraeteliste()
    state.remove_fixture(4)
    gleich_der_geraeteliste()
    with state.patch_sammeln():
        state.add_fixture(_par(state, bib, 2, 9))
        state._render_frame(0.02)
        assert [f.fid for f in gesehen[-1]] == [1]
    gleich_der_geraeteliste()
    with pytest.raises(RuntimeError):
        with state.patch_sammeln():
            state.add_fixture(_par(state, bib, 3, 17))
            raise RuntimeError("mitten im Block")
    gleich_der_geraeteliste()
    assert [f.fid for f in gesehen[-1]] == [1, 2, 3]


def test_scheitert_der_neuaufbau_am_ende_rendert_der_alte_plan_stimmig_weiter(state, bib, monkeypatch):
    """Wirft der eine Neuaufbau beim Verlassen, bleiben Plan UND Geräteliste
    des Plans alt: eine laufende Funktion schreibt den importierten Laser
    nicht, er bleibt im NOT-AUS dunkel — auch in allen Frames danach."""
    monkeypatch.setattr(state.function_manager, "tick", _alles_voll)
    state.add_fixture(_par(state, bib, 1, 1))
    state.set_laser_estop(True)
    echt = state._rebuild_render_plan

    def kaputt(*a, **k):
        raise RuntimeError("Neuaufbau gescheitert")

    monkeypatch.setattr(state, "_rebuild_render_plan", kaputt)
    with pytest.raises(RuntimeError):
        with state.patch_sammeln():
            state.add_fixture(_laser(state, bib, state.next_fid(), 10))
    assert state._patch_sammel_tiefe == 0
    assert [f.fid for f in state._plan_patch] == [1]
    for _ in range(3):
        state._render_frame(0.02)
        assert _live(state, 3, 10, 5) == [0] * 5
        assert _live(state, 1, 1, 8) == [255] * 8
    # der nächste gelungene Neuaufbau bringt Plan und Liste zusammen nach
    monkeypatch.setattr(state, "_rebuild_render_plan", echt)
    state._reload_patch_cache()
    state._render_frame(0.02)
    assert state.laser_estop_active
    assert [f.fid for f in state._plan_patch] == [f.fid for f in state._patch_cache]
    assert _live(state, 3, 10, 5) == [0] * 5


def test_echter_ausgabe_thread_waehrend_import_rueckgaengig_wiederholen(state, bib, monkeypatch):
    """Ein Thread rendert pausenlos, während importiert, zurückgenommen und
    wiederholt wird: kein Fehler im Renderer, der Laser im NOT-AUS nie hell."""
    monkeypatch.setattr(state.function_manager, "tick", _alles_voll)
    state.set_laser_estop(True)
    stopp = threading.Event()
    fehler: list = []
    hell: list = []
    frames = [0]

    def ausgabe():
        while not stopp.is_set():
            try:
                state._render_frame(0.02)
                frames[0] += 1
                uni = state.universes.get(3)
                if uni is not None and any(uni.get_all()[9:14]):
                    hell.append(list(uni.get_all()[9:14]))
            except Exception as e:                     # pragma: no cover
                fehler.append(repr(e))

    faden = threading.Thread(target=ausgabe, daemon=True)
    faden.start()
    try:
        T.wende_an(state, _plan(state, bib, _tabelle(12)), bib)
        time.sleep(0.05)
        get_undo_stack().undo()
        time.sleep(0.05)
        get_undo_stack().redo()
        time.sleep(0.05)
    finally:
        stopp.set()
        faden.join(timeout=10)
    assert not faden.is_alive() and frames[0] > 0
    assert fehler == [] and hell == []
    assert state._patch_sammel_tiefe == 0
    assert [f.fid for f in state._plan_patch] == [f.fid for f in state._patch_cache]


def test_einzelaufruf_ausserhalb_des_sammelns_wie_vorher(state, bib):
    """Wer ``add_fixture``/``remove_fixture`` ohne Sammelblock ruft, bekommt
    je Aufruf EIN ``patch_changed`` und sofort den fertigen Plan."""
    ohr = Mithoerer(state)
    plan_im_ereignis: list = []
    state.subscribe(lambda e, d=None: plan_im_ereignis.append(sorted(state._fix_index))
                    if e == "patch_changed" else None)
    state.add_fixture(_par(state, bib, 1, 1))
    assert ohr.zahl("patch_changed") == 1 and sorted(state._fix_index) == [1]
    state.add_fixture(_laser(state, bib, 2, 10))
    assert ohr.zahl("patch_changed") == 2 and 2 in state._laser_fids
    state.remove_fixture(1)
    assert ohr.zahl("patch_changed") == 3 and sorted(state._fix_index) == [2]
    assert get_undo_stack().undo()
    assert ohr.zahl("patch_changed") == 4 and sorted(state._fix_index) == [1, 2]
    assert plan_im_ereignis == [[1], [1, 2], [2], [1, 2]]


# ── Zweite Prüfung: der Direkt-Schreibweg des Programmers ────────────────────
#
# ``set_programmer_value`` und ``clear_programmer`` schreiben die Kanäle eines
# Geräts sofort ins Live-Universum. Nahm dieser Weg das Gerät aus der
# Geräteliste statt aus dem geltenden Plan, gingen die Werte eines gerade
# importierten Lasers hinaus: seine Adressen stehen noch in keinem Span und in
# keiner NOT-AUS-Maske, der nächste Frame überschreibt sie also nicht.

def _attribute(state, fid):
    fx = next(f for f in state.get_patched_fixtures() if f.fid == fid)
    return [c.attribute for c in A.get_channels_for_patched(fx)]


def test_programmer_wert_auf_neuen_laser_im_sammeln_bleibt_im_not_aus_dunkel(state, bib):
    state.set_laser_estop(True)
    with state.patch_sammeln():
        fid = state.next_fid()
        state.add_fixture(_laser(state, bib, fid, 10))
        for attribut in _attribute(state, fid):
            state.set_programmer_value(fid, attribut, 200)
        direkt = _live(state, 3, 10, 5)
        state._render_frame(0.02)
        im_block = _live(state, 3, 10, 5)
        not_aus_im_block = state.laser_estop_active
    state._render_frame(0.02)
    assert not_aus_im_block and state.laser_estop_active
    assert direkt == [0] * 5 and im_block == [0] * 5
    assert _live(state, 3, 10, 5) == [0] * 5


def test_programmer_leeren_im_sammeln_schreibt_keine_defaults_neuer_geraete(state, bib):
    """Ein Profil mit Kanal-Default ungleich 0: ``clear_programmer`` darf den
    Default eines Geräts, das der Plan noch nicht kennt, nicht hinausschreiben."""
    state.set_laser_estop(True)
    with state.patch_sammeln():
        fid = state.next_fid()
        state.add_fixture(_laser(state, bib, fid, 10))
        fx = next(f for f in state.get_patched_fixtures() if f.fid == fid)
        kanaele = A.get_channels_for_patched(fx)
        alt = [c.default_value for c in kanaele]
        try:
            for c in kanaele:
                c.default_value = 77
            assert [c.default_value
                    for c in A.get_channels_for_patched(fx)] == [77] * 5
            state.clear_programmer()
            direkt = _live(state, 3, 10, 5)
            state._render_frame(0.02)
            im_block = _live(state, 3, 10, 5)
        finally:
            for c, wert in zip(kanaele, alt):
                c.default_value = wert
    assert direkt == [0] * 5 and im_block == [0] * 5


def test_programmer_wert_auf_im_sammeln_umadressierten_laser(state, bib):
    """Der Plan kennt den Laser noch auf der alten Adresse: dorthin geht der
    Wert (vom NOT-AUS gedeckt), die neue Adresse bleibt unberührt. Der Wert
    kommt hier ohne ``set_programmer_value`` in den Programmer — das löste bei
    einem dem Plan bekannten Laser den NOT-AUS (gewollt, anderes Thema)."""
    fid = state.next_fid()
    state.add_fixture(_laser(state, bib, fid, 10))
    state.set_laser_estop(True)
    with state.patch_sammeln():
        assert state.update_fixture(fid, address=100)
        with state._prog_lock:
            state.programmer.setdefault(fid, {}).update(
                {attribut: 200 for attribut in _attribute(state, fid)})
        state._flush_programmer_to_dmx(fid)
        direkt = _live(state, 3, 100, 5)
        state._render_frame(0.02)
        im_block = _live(state, 3, 100, 5) + _live(state, 3, 10, 5)
    state._render_frame(0.02)
    assert state.laser_estop_active
    assert direkt == [0] * 5 and im_block == [0] * 10
    assert _live(state, 3, 100, 5) + _live(state, 3, 10, 5) == [0] * 10


def test_programmer_schreibt_ausserhalb_des_sammelns_sofort_wie_vorher(state, bib):
    """Außerhalb des Blocks sind Plan und Geräteliste deckungsgleich: der Wert
    steht ohne Frame sofort im Live-Universum, ``clear_programmer`` setzt die
    Defaults."""
    state.add_fixture(_par(state, bib, 1, 1))
    state.add_fixture(_par(state, bib, 2, 9))
    attribut = _attribute(state, 2)[0]
    state.set_programmer_value(2, attribut, 123)
    assert _live(state, 1, 9, 1) == [123]
    assert _live(state, 1, 1, 8) == [0] * 8
    state.clear_programmer()
    assert _live(state, 1, 9, 1) == [0]


def test_scheitert_schon_der_erste_neuaufbau_rechnen_funktionen_mit_dem_leeren_plan(
        tmp_path, bib, monkeypatch):
    """IMP-3, Gegenprüfung: ein frischer ``AppState`` hat einen leeren Plan —
    auch seine Geräteliste (``_plan_patch``) ist dann leer, nicht „noch
    keine“. Scheitert schon der erste Neuaufbau (Show laden), bekamen die
    Funktionen sonst ``_patch_cache`` mit dem Laser zum leeren Plan: seine
    Adressen gingen als Roh-Kanäle an beiden NOT-AUS-Ebenen vorbei hinaus."""
    pfad = tmp_path / "show.db"
    st = _oeffne(pfad)
    st.add_fixture(_laser(st, bib, 1, 10))
    _schliesse(st)

    st = A.AppState()
    try:
        def kaputt(*a, **k):
            raise RuntimeError("Neuaufbau gescheitert")

        monkeypatch.setattr(st, "_rebuild_render_plan", kaputt)
        with pytest.raises(RuntimeError):
            st.open_show(str(pfad))
        assert [f.fid for f in st._patch_cache] == [1]
        assert st._fix_index == {}
        st.set_laser_estop(True)
        monkeypatch.setattr(st.function_manager, "tick", _alles_voll)
        for _ in range(2):
            st._render_frame(0.02)
            assert _live(st, 3, 10, 5) == [0] * 5
        with st.patch_sammeln():       # auch der Block hält die leere Liste
            st._render_frame(0.02)
            assert _live(st, 3, 10, 5) == [0] * 5
    finally:
        _schliesse(st)


# ── Codex-Review #1093: Neuaufbau am Ende scheitert ─────────────────────────

def _end_neuaufbau_scheitert(state, monkeypatch):
    """``_reload_patch_cache`` wirft nur beim EINEN Neuaufbau am Ende
    (Tiefe schon 0); im Block (leichter Weg) laeuft es normal."""
    echt = state._reload_patch_cache

    def neu_laden():
        if getattr(state, "_patch_sammel_tiefe", 0) == 0:
            raise RuntimeError("Render-Plan kaputt")
        return echt()
    monkeypatch.setattr(state, "_reload_patch_cache", neu_laden)


def test_scheiternder_end_neuaufbau_steht_im_ergebnis(state, bib, monkeypatch):
    """Die Geraete und der Rueckgaengig-Schritt sind schon angelegt — die
    Ausnahme darf das nicht verschweigen: sie steht im Ergebnis."""
    plan = _plan(state, bib, _tabelle(3))
    _end_neuaufbau_scheitert(state, monkeypatch)
    erg = T.wende_an(state, plan, bib)
    assert erg.geraete == 3 + 1 + 2 + 1
    assert any("Neuaufbau" in f and "Render-Plan kaputt" in f for f in erg.fehler)
    assert len(state.get_patched_fixtures()) == erg.geraete
    assert get_undo_stack().can_undo()


def test_dialog_schliesst_mit_ergebnis_statt_offen_zu_bleiben(state, bib, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from src.ui.widgets import patch_import_dialog as D
    QApplication.instance() or QApplication([])
    _end_neuaufbau_scheitert(state, monkeypatch)
    dlg = D.PatchImportDialog(state, T.lies_tabelle(_tabelle(2)), bib, "liste.csv")
    try:
        dlg._anwenden()
        assert dlg.ergebnis is not None, "Dialog blieb ohne Ergebnis offen"
        assert dlg.ergebnis.fehler
    finally:
        dlg.deleteLater()
    # Scheitert schon das Anlegen (nichts angelegt): Meldung, Dialog bleibt.
    meldungen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: meldungen.append(a[2])))
    monkeypatch.setattr(T, "wende_an", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("Datenbank weg")))
    frei = ("Name;Hersteller;Profil;Modus;Universum;Adresse;Anzahl\n"
            f"Neu;Generic;{PAR};8-Kanal RGBW;4;1;1\n")
    dlg2 = D.PatchImportDialog(state, T.lies_tabelle(frei), bib, "liste.csv")
    assert dlg2.plan.anlegbare(), "Vorbedingung"
    try:
        dlg2._anwenden()
        assert dlg2.ergebnis is None
        assert meldungen and "nichts" in meldungen[0] and "Datenbank weg" in meldungen[0]
    finally:
        dlg2.deleteLater()

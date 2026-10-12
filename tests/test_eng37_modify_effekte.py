"""ENG-37: Modify-Effekte — verrechnen statt setzen (Matrix, Stil Dimmer).

Ein Modify-Effekt setzt seine Kanaele nicht, er wird mit dem verrechnet, was
darunter laeuft:

    Addieren   unten + Betrag * Staerke
    Abziehen   unten - Betrag * Staerke
    Abdunkeln  unten * (1 - Betrag * Staerke)

Gekappt bei 0 und 100 %. Wo der Modify-Effekt nichts ausgibt (Lauflicht: Lampe
ist nicht dran), bleibt das Darunterliegende unveraendert.

Das Beispiel des Betreibers, durchgerechnet (Dimmer-Matrix-Anleitung, Abschnitt 5): unten
steht ein Dimmer-Effekt auf 40 %, darueber ein Modify-Lauflicht mit zwei
Laeufern auf acht Lampen.

Geprueft wird hier die Engine (Rechnung, Sammeln im FunctionManager,
Show-Format, Konsolen-Parameter, Renderer). Seit dem spaeten Rechengang gilt:
Modify rechnet auf das FERTIGE Bild — auch auf Werte, die kein Effekt
geschrieben hat (Ruhewert, Snap), und auf Effekte hoeherer Prioritaet. Die
Schichten darueber (Master, Blackout, NOT-AUS), Sammlungen und Chaser-Schritte
prueft test_eng37_modify_fertiges_bild.py, den Editor
test_eng37_modify_editor.py.
"""
from __future__ import annotations

import json
import os
import random
import sys
import threading
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.modify import (                        # noqa: E402
    MODIFY_MODES, modify_wert, normalize_mode, normalize_strength)
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

N = 8                 # acht Lampen, je ein Dimmer-Kanal auf Adresse 1..8
P40 = 102             # 40 % von 255
DT = 0.02


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []


class _Fx:
    def __init__(self, fid, address, universe=1):
        self.fid = fid
        self.universe = universe
        self.address = address


@pytest.fixture
def rig(monkeypatch):
    """Acht Dimmer-Lampen: fid 1..8 auf Adresse 1..8."""
    kanaele = {fid: [_Ch("intensity", 1)] for fid in range(1, N + 1)}
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: kanaele[fx.fid])
    return [_Fx(fid, fid) for fid in range(1, N + 1)]


def _matrix(name, algo=RgbAlgorithm.PLAIN, **felder) -> RgbMatrixInstance:
    m = RgbMatrixInstance(name, cols=N, rows=1,
                          fixture_grid=list(range(1, N + 1)),
                          algorithm=algo, color1=(255, 255, 255))
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""          # frei laufend: Schritt haengt nur an dt
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _pegel(wert=P40) -> RgbMatrixInstance:
    """Unter-Effekt: alle acht Lampen fest auf ``wert``."""
    return _matrix("unten", intensity_min=wert, intensity_max=wert)


def _lauflicht(mode="add", staerke=100, **felder) -> RgbMatrixInstance:
    """Modify-Lauflicht: zwei Laeufer, harte Kante, kein Schweif."""
    m = _matrix("modify", RgbAlgorithm.CHASE, **felder)
    m.params.update({"runner_count": 2, "after_fade": 0.0, "fade": 0.0,
                     "movement": "normal"})
    m.modify = True
    m.modify_mode = mode
    m.modify_strength = staerke
    return m


def _spion(m):
    """Merkt sich, was ``m`` in seinem letzten write() ausgegeben hat."""
    orig = m.write
    m.ausgabe = None

    def write(universes, patch_cache, dt, reg=None):
        orig(universes, patch_cache, dt, reg)
        m.ausgabe = list(universes[1].get_all()[:N])
    m.write = write
    return m


def _tick(fm, rig, dt=DT, mit_protokoll=True):
    """Ein Frame wie im Renderer: frisches Scratch, Schreibprotokoll an."""
    u = Universe(1)
    if mit_protokoll:
        u.begin_write_log()
    fm.tick({1: u}, rig, dt)
    geschrieben = u.end_write_log() if mit_protokoll else set()
    return list(u.get_all()[:N]), geschrieben


def _fm(*funktionen, start=None):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in (start if start is not None else funktionen):
        fm.start(f.id)
    return fm


def _aktiv(m):
    """Lampen-Indizes, auf denen der Modify-Effekt gerade voll an ist."""
    return [i for i, w in enumerate(m.ausgabe) if w == 255]


# ── Die Rechnung selbst ──────────────────────────────────────────────────────


@pytest.mark.parametrize("mode, u, w, s, soll", [
    ("add", 102, 255, 1.0, 255),     # 40 + 100 = 140 -> gekappt auf 100
    ("add", 102, 255, 0.5, 230),     # 40 + 50 = 90
    ("add", 102, 0, 1.0, 102),       # Lampe nicht dran -> unveraendert
    ("add", 0, 200, 1.0, 200),       # nichts darunter -> wie ein normaler Effekt
    ("sub", 102, 255, 1.0, 0),       # 40 - 100 -> gekappt auf 0
    ("sub", 102, 255, 0.5, 0),       # 40 - 50 -> gekappt auf 0
    ("sub", 200, 100, 1.0, 100),
    ("sub", 102, 0, 1.0, 102),
    ("dim", 102, 255, 1.0, 0),       # um 100 % dunkler
    ("dim", 102, 255, 0.5, 51),      # halbe Helligkeit
    ("dim", 200, 255, 0.25, 150),
    ("dim", 102, 0, 1.0, 102),
])
def test_rechnung_je_betriebsart(mode, u, w, s, soll):
    assert modify_wert(mode, u, w, s) == soll


def test_betrag_null_ist_in_allen_arten_neutral():
    for mode in MODIFY_MODES:
        for u in (0, 1, 102, 254, 255):
            for s in (0.0, 0.3, 1.0):
                assert modify_wert(mode, u, 0, s) == u
    # Staerke 0 ebenfalls
    for mode in MODIFY_MODES:
        assert modify_wert(mode, 102, 255, 0.0) == 102


def test_normalisieren():
    assert normalize_mode("SUB") == "sub"
    assert normalize_mode("quatsch") == "add"
    assert normalize_mode(None) == "add"
    assert normalize_strength(150) == 100
    assert normalize_strength(-3) == 0
    assert normalize_strength("x") == 100
    assert normalize_strength(49.6) == 50


# ── (2) Das Beispiel des Betreibers ──────────────────────────────────────────


@pytest.mark.parametrize("mode, staerke, soll_aktiv", [
    ("add", 100, 255), ("sub", 100, 0), ("dim", 100, 0),
    ("add", 50, 230), ("sub", 50, 0), ("dim", 50, 51),
])
def test_beispiel_fester_pegel_40_prozent(rig, mode, staerke, soll_aktiv):
    unten = _pegel()
    mod = _spion(_lauflicht(mode, staerke))
    fm = _fm(unten, mod)
    bild, _ = _tick(fm, rig)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2, mod.ausgabe
    assert sorted(set(mod.ausgabe)) == [0, 255], "Lauflicht ohne Schweif erwartet"
    for i in range(N):
        if i in aktiv:
            assert bild[i] == soll_aktiv, (i, bild)
        else:
            assert bild[i] == P40, (i, bild)      # exakt der Wert darunter


def test_beispiel_naechster_schritt_die_naechsten_zwei(rig):
    """Der Laeufer wandert: danach sind die NAECHSTEN zwei Lampen dran, die
    vorigen stehen wieder exakt auf dem Wert darunter."""
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    fm = _fm(unten, mod)
    gesehen = []
    for _ in range(400):
        bild, _ = _tick(fm, rig, dt=0.05)
        aktiv = tuple(_aktiv(mod))
        assert len(aktiv) == 2
        assert bild == [255 if i in aktiv else P40 for i in range(N)]
        if not gesehen or gesehen[-1] != aktiv:
            gesehen.append(aktiv)
        if len(gesehen) >= 3:
            break
    assert len(gesehen) >= 3, f"Lauflicht ist nicht gewandert: {gesehen}"
    a, b = gesehen[0], gesehen[1]
    assert set(a).isdisjoint(b), (a, b)
    assert sorted((i + 1) % N for i in a) == sorted(b), (a, b)


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_beispiel_ueber_funkeln(rig, mode):
    """Unten laeuft „Funkeln" (Random/Sparkle) mit wechselnden Werten."""
    random.seed(37)
    unten = _spion(_matrix("funkeln", RgbAlgorithm.RANDOM))
    unten.params.update({"mode": "sparkle"})
    mod = _spion(_lauflicht(mode))
    fm = _fm(unten, mod)
    verschiedene = set()
    for _ in range(60):
        bild, _ = _tick(fm, rig, dt=0.05)
        u = unten.ausgabe
        verschiedene.update(u)
        aktiv = _aktiv(mod)
        assert len(aktiv) == 2
        for i in range(N):
            if i in aktiv:
                soll = {"add": 255 if u[i] + 255 > 255 else u[i] + 255,
                        "sub": 0, "dim": 0}[mode]
                assert bild[i] == soll, (mode, i, u, bild)
            else:
                assert bild[i] == u[i], (mode, i, u, bild)
    assert len(verschiedene) > 1, "Funkeln hat sich nicht bewegt — Test prueft nichts"


def test_schweif_wird_anteilig_verrechnet(rig):
    """Zwischenwerte des Modify-Effekts (Schweif) wirken anteilig."""
    unten = _pegel()
    mod = _spion(_lauflicht("sub"))
    mod.params.update({"runner_count": 1, "after_fade": 0.6, "fade": 0.6})
    fm = _fm(unten, mod)
    zwischen = False
    for _ in range(80):
        bild, _ = _tick(fm, rig, dt=0.05)
        for i, w in enumerate(mod.ausgabe):
            assert bild[i] == modify_wert("sub", P40, w, 1.0)
            zwischen = zwischen or 0 < w < 255
    assert zwischen, "kein Schweif-Zwischenwert gesehen — Test prueft nichts"


# ── (3) Reihenfolge ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_startreihenfolge_ist_egal(rig, mode):
    bilder = []
    for zuerst_modify in (False, True):
        unten = _pegel()
        mod = _spion(_lauflicht(mode))
        fm = _fm(unten, mod, start=(mod, unten) if zuerst_modify else (unten, mod))
        bild, _ = _tick(fm, rig)
        bilder.append(bild)
        assert len(_aktiv(mod)) == 2
    assert bilder[0] == bilder[1]
    assert bilder[0] != [P40] * N           # der Modify hat gewirkt


def test_modify_wirkt_auch_auf_effekt_hoeherer_prioritaet(rig):
    """Modify rechnet auf das FERTIGE Bild: ein normaler Effekt hoeherer
    Layer-Prioritaet gewinnt gegen den Effekt darunter — und der Modify
    verrechnet sich dann mit dem Gewinner."""
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    oben = _pegel(30)
    oben.priority = 5
    fm = _fm(unten, mod, oben, start=(oben, unten, mod))
    bild, _ = _tick(fm, rig)
    assert len(_aktiv(mod)) == 2
    assert bild == [255 if i in _aktiv(mod) else 30 for i in range(N)]


def test_modify_hoeherer_prioritaet_verrechnet_alles_darunter(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    mod.priority = 5
    fm = _fm(unten, mod, start=(mod, unten))
    bild, _ = _tick(fm, rig)
    assert bild == [255 if i in _aktiv(mod) else P40 for i in range(N)]


# ── (4) Zwei Modify-Effekte gleichzeitig ─────────────────────────────────────


def test_zwei_modify_wirken_nacheinander_in_startreihenfolge(rig):
    """Addieren 50 % und Abziehen 100 % auf denselben Lampen. Definiert:
    nacheinander in Start-Reihenfolge, jeder kappt fuer sich.

      erst +50 %, dann −100 %:  40 → 90 → 0
      erst −100 %, dann +50 %:  40 →  0 → 50
    """
    ergebnis = {}
    for name in ("add_zuerst", "sub_zuerst"):
        unten = _pegel()
        add = _spion(_lauflicht("add", 50))
        sub = _spion(_lauflicht("sub", 100))
        folge = (add, sub) if name == "add_zuerst" else (sub, add)
        # der Unter-Effekt wird ZULETZT gestartet — er laeuft trotzdem darunter
        fm = _fm(unten, add, sub, start=folge + (unten,))
        bild, _ = _tick(fm, rig)
        assert _aktiv(add) == _aktiv(sub)
        ergebnis[name] = (bild, _aktiv(add))
    bild, aktiv = ergebnis["add_zuerst"]
    assert bild == [0 if i in aktiv else P40 for i in range(N)]
    bild, aktiv = ergebnis["sub_zuerst"]
    assert bild == [128 if i in aktiv else P40 for i in range(N)]


# ── (5) Modify allein, ohne Effekt darunter ──────────────────────────────────


def test_addieren_allein_wirkt_wie_ein_normaler_effekt(rig):
    mod = _spion(_lauflicht("add"))
    bild, geschrieben = _tick(_fm(mod), rig)
    normal = _lauflicht("add")
    normal.modify = False
    bild_normal, geschrieben_normal = _tick(_fm(normal), rig)
    assert bild == bild_normal
    assert sorted(bild) == [0] * 6 + [255] * 2
    # … aber er TREIBT nur, was er aendert: die zwei Lampen unter dem Laeufer.
    # Ein normaler Effekt schreibt alle acht (auch die dunklen).
    assert geschrieben == {i + 1 for i in _aktiv(mod)}
    assert geschrieben_normal == set(range(1, N + 1))


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_und_abdunkeln_allein_schreiben_nichts(rig, mode):
    mod = _spion(_lauflicht(mode))
    bild, geschrieben = _tick(_fm(mod), rig)
    assert len(_aktiv(mod)) == 2            # der Effekt selbst laeuft
    assert bild == [0] * N
    assert geschrieben == set(), "Abziehen/Abdunkeln allein darf nichts treiben"


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_wirkt_auf_das_was_im_bild_steht(rig, mode):
    """Modify rechnet auf das fertige Bild — auch auf einen Wert, den kein
    Effekt geschrieben hat (Ruhewert, Snap). Unter dem Laeufer wird abgezogen,
    daneben bleibt der Wert exakt stehen."""
    mod = _spion(_lauflicht(mode))
    fm = _fm(mod)
    u = Universe(1)
    u.set_range(1, bytes([200] * N))        # Ruhewerte
    u.begin_write_log()
    fm.tick({1: u}, rig, DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert u.end_write_log() == {i + 1 for i in aktiv}
    assert list(u.get_all()[:N]) == [0 if i in aktiv else 200 for i in range(N)]


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_greift_auf_alle_lampen_des_modify_effekts(rig, mode):
    """Unter-Effekt nur auf Lampe 1–4; Lampen 5–8 haben einen Ruhewert. Der
    Modify-Effekt ist auf allen acht voll dran -> alle acht werden dunkel."""
    unten = _pegel()
    unten.fixture_grid = [1, 2, 3, 4, None, None, None, None]
    mod = _lauflicht(mode)
    mod.algorithm = RgbAlgorithm.PLAIN       # alle acht Lampen voll dran
    fm = _fm(unten, mod)
    u = Universe(1)
    u.set_range(1, bytes([200] * N))
    u.begin_write_log()
    fm.tick({1: u}, rig, DT)
    assert u.end_write_log() == set(range(1, N + 1))
    assert list(u.get_all()[:N]) == [0] * N


def test_ohne_schreibprotokoll_entscheidet_der_wert(rig):
    """Direkter tick() ohne Protokoll (z. B. Werkzeuge): Abziehen rechnet auf
    dem, was im Universum steht, und stuerzt nicht ab."""
    unten = _pegel()
    mod = _spion(_lauflicht("sub"))
    bild, _ = _tick(_fm(unten, mod), rig, mit_protokoll=False)
    assert bild == [0 if i in _aktiv(mod) else P40 for i in range(N)]


# ── (6) Effekt-Helligkeit und Huellkurve skalieren die Staerke ───────────────


def test_effekt_helligkeit_skaliert_die_staerke_nicht_das_darunter(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    mod.intensity = 0.5
    bild, _ = _tick(_fm(unten, mod), rig)
    aktiv = _aktiv(mod)
    # 40 % + 100 % * 0,5 = 90 %; das Darunterliegende bleibt bei 40 % (nicht 20 %)
    assert bild == [230 if i in aktiv else P40 for i in range(N)]


def test_effekt_helligkeit_null_ist_wirkungslos(rig):
    for mode in MODIFY_MODES:
        unten = _pegel()
        mod = _lauflicht(mode)
        mod.intensity = 0.0
        bild, _ = _tick(_fm(unten, mod), rig)
        assert bild == [P40] * N


def test_effekt_helligkeit_mal_staerke(rig):
    unten = _pegel(200)
    mod = _spion(_lauflicht("dim", 50))
    mod.intensity = 0.5
    bild, _ = _tick(_fm(unten, mod), rig)
    aktiv = _aktiv(mod)
    # um 50 % * 0,5 = 25 % dunkler: 200 -> 150
    assert bild == [150 if i in aktiv else 200 for i in range(N)]


def test_einblendzeit_blendet_die_staerke_ein(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("sub"))
    mod.matrix_speed = 0.0                  # Laeufer steht, nur die Huellkurve laeuft
    mod.env_fade_in = 1.0
    fm = _fm(unten, mod)
    verlauf = []
    for _ in range(30):
        bild, _ = _tick(fm, rig, dt=0.05)
        aktiv = _aktiv(mod)
        assert [bild[i] for i in range(N) if i not in aktiv] == [P40] * 6
        verlauf.append(bild[aktiv[0]])
    assert verlauf[0] > 0, "Abziehen darf nicht hart einsetzen"
    assert verlauf == sorted(verlauf, reverse=True)
    assert verlauf[-1] == 0


def test_ausblendzeit_laesst_das_darunter_weich_zurueckkommen(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("sub"))
    mod.matrix_speed = 0.0
    mod.env_fade_out = 1.0
    fm = _fm(unten, mod)
    bild, _ = _tick(fm, rig, dt=0.05)
    aktiv = _aktiv(mod)
    assert bild[aktiv[0]] == 0
    fm.stop(mod.id)                         # leitet nur das Ausblenden ein
    verlauf = []
    for _ in range(40):
        bild, _ = _tick(fm, rig, dt=0.05)
        verlauf.append(bild[aktiv[0]])
        assert [bild[i] for i in range(N) if i not in aktiv] == [P40] * 6
    assert verlauf == sorted(verlauf)
    assert any(0 < v < P40 for v in verlauf), verlauf   # weich, kein Sprung
    assert verlauf[-1] == P40
    assert not fm.is_running(mod.id)


# ── (7) Stopp ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_nach_dem_stopp_laeuft_das_darunter_unveraendert(rig, mode):
    unten = _pegel()
    mod = _lauflicht(mode)
    fm = _fm(unten, mod)
    bild, _ = _tick(fm, rig)
    assert bild != [P40] * N
    fm.stop(mod.id)
    bild, geschrieben = _tick(fm, rig)
    assert bild == [P40] * N
    assert geschrieben == set(range(1, N + 1))
    assert fm.is_running(unten.id)


# ── (8) Geteilter Dimmer / Kinder ────────────────────────────────────────────


def test_geteilter_dimmer_wird_nur_einmal_verrechnet(monkeypatch):
    """Zwei Zellen (Koepfe) desselben Geraets teilen EINEN Dimmer-Kanal: der
    Modify-Effekt addiert einmal, nicht je Zelle."""
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: [_Ch("intensity", 1)])
    rig = [_Fx(1, 1)]
    unten = RgbMatrixInstance("unten", cols=2, rows=1, fixture_grid=[1, 1],
                              algorithm=RgbAlgorithm.PLAIN, color1=(255, 255, 255))
    unten.style = MatrixStyle.DIMMER
    unten.tempo_bus_id = ""
    unten.intensity_min = unten.intensity_max = 50
    mod = RgbMatrixInstance("mod", cols=2, rows=1, fixture_grid=[1, 1],
                            algorithm=RgbAlgorithm.PLAIN, color1=(255, 255, 255))
    mod.style = MatrixStyle.DIMMER
    mod.tempo_bus_id = ""
    mod.modify, mod.modify_mode, mod.modify_strength = True, "add", 20
    fm = _fm(unten, mod)
    u = Universe(1)
    fm.tick({1: u}, rig, DT)
    assert u.get_channel(1) == 50 + 51       # 20 % von 255 = 51, einmal


def test_modify_als_kind_einer_collection(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    fm = FunctionManager()
    fm.add(unten)
    fm.add(mod)
    col = fm.new_collection("Sammlung")
    col.function_ids = [unten.id, mod.id]
    fm.start(col.id)
    bild, _ = _tick(fm, rig)
    assert bild == [255 if i in _aktiv(mod) else P40 for i in range(N)]


def test_normales_kind_einer_collection_schreibt_unveraendert(rig):
    a, b = _pegel(60), _pegel(90)
    fm = FunctionManager()
    fm.add(a)
    fm.add(b)
    col = fm.new_collection("Sammlung")
    col.function_ids = [a.id, b.id]
    fm.start(col.id)
    bild, _ = _tick(fm, rig)
    assert bild == [90] * N                  # letzter Schreiber gewinnt, wie bisher


# ── Schritt 1: nur Stil Dimmer ───────────────────────────────────────────────


def test_haken_bei_farb_stil_bleibt_ein_normaler_effekt(monkeypatch):
    """Steht der Haken bei Stil RGB, wird NICHT verrechnet — Farbe und Dimmer
    bleiben getrennt, und der Effekt laeuft wie ohne Haken."""
    kan = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kan)
    rig = [_Fx(1, 1)]

    def bild(haken):
        m = RgbMatrixInstance("rgb", cols=1, rows=1, fixture_grid=[1],
                              algorithm=RgbAlgorithm.PLAIN, color1=(200, 100, 50))
        m.tempo_bus_id = ""
        m.modify = haken
        m.modify_mode = "sub"
        assert m.modify_wirksam() is False
        u = Universe(1)
        u.set_range(1, bytes([10, 10, 10]))
        _fm(m).tick({1: u}, rig, DT)
        return list(u.get_all()[:3])
    assert bild(True) == bild(False) == [200, 100, 50]


def test_andere_funktionstypen_verrechnen_nicht():
    from src.core.engine.scene import Scene
    s = Scene("Szene")
    s.modify = True
    assert s.modify_wirksam() is False


# ── (1) Ohne Haken exakt wie bisher ──────────────────────────────────────────

_BASIS_SCHLUESSEL = [
    "id", "name", "type", "intensity", "speed", "folder", "priority",
    "env_fade_in", "env_fade_out", "env_curve", "tempo_bus_id",
    "tempo_multiplier", "phase_offset", "sync_group", "align_on_start",
]


def test_to_dict_ohne_haken_hat_keine_neuen_schluessel():
    from src.core.engine.function import Function
    d = Function.to_dict(_matrix("m"))
    assert list(d) == _BASIS_SCHLUESSEL
    assert not [k for k in _matrix("m").to_dict() if k.startswith("modify")]


def test_to_dict_schreibt_nur_abweichungen():
    m = _matrix("m")
    m.modify = True
    d = m.to_dict()
    assert d["modify"] is True
    assert "modify_mode" not in d and "modify_strength" not in d
    m.modify_mode, m.modify_strength = "dim", 60
    d = m.to_dict()
    assert (d["modify"], d["modify_mode"], d["modify_strength"]) == (True, "dim", 60)
    # Haken raus: Art und Staerke bleiben gemerkt
    m.modify = False
    d = m.to_dict()
    assert "modify" not in d
    assert (d["modify_mode"], d["modify_strength"]) == ("dim", 60)


def _alt_show() -> dict:
    """Funktionsliste, wie sie eine Show VOR ENG-37 enthielt (ohne die neuen
    Schluessel) — mehrere Typen, alle vier Matrix-Stile."""
    fm = FunctionManager()
    for stil in MatrixStyle:
        m = fm.new_rgb_matrix(f"Matrix {stil.value}")
        m.style = stil
        m.fixture_grid = [1, 2, None, 4]
        m.cols, m.rows = 4, 1
        m.params.update({"runner_count": 2})
    sz = fm.new_scene("Szene")
    ch = fm.new_chaser("Chaser")
    col = fm.new_collection("Sammlung")
    col.function_ids = [sz.id, ch.id]
    fm.new_efx("Bewegung")
    fm.new_sequence("Sequenz")
    d = json.loads(json.dumps(fm.to_dict()))
    for fd in d["functions"]:
        assert not [k for k in fd if k.startswith("modify")], fd["name"]
    return d


def test_alte_show_laedt_und_speichert_byte_gleich():
    alt = _alt_show()
    vorher = json.dumps(alt, ensure_ascii=False, indent=1)
    fm = FunctionManager()
    fm.from_dict(json.loads(vorher))
    assert len(fm.all()) == len(alt["functions"])
    for f in fm.all():
        assert f.modify is False and f.modify_mode == "add"
        assert f.modify_strength == 100
        assert f.modify_wirksam() is False
    nachher = json.dumps(fm.to_dict(), ensure_ascii=False, indent=1)
    assert nachher.encode("utf-8") == vorher.encode("utf-8")
    # … und ein zweiter Durchgang ebenfalls
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(nachher))
    assert json.dumps(fm2.to_dict(), ensure_ascii=False, indent=1) == vorher


def test_show_mit_modify_laedt_und_speichert_gleich():
    fm = FunctionManager()
    m = fm.new_rgb_matrix("Modify")
    m.style = MatrixStyle.DIMMER
    m.modify, m.modify_mode, m.modify_strength = True, "sub", 35
    text = json.dumps(fm.to_dict())
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(text))
    m2 = fm2.all()[0]
    assert (m2.modify, m2.modify_mode, m2.modify_strength) == (True, "sub", 35)
    assert m2.modify_wirksam() is True
    assert json.dumps(fm2.to_dict()) == text


def test_kaputte_werte_in_der_show_fallen_auf_die_vorgabe():
    fm = FunctionManager()
    m = fm.new_rgb_matrix("Modify")
    d = fm.to_dict()
    d["functions"][0].update({"modify": 1, "modify_mode": "xyz",
                              "modify_strength": "viel"})
    fm2 = FunctionManager()
    fm2.from_dict(d)
    m2 = fm2.all()[0]
    assert (m2.modify, m2.modify_mode, m2.modify_strength) == (True, "add", 100)


def test_entwurf_und_preset_behalten_die_kennzeichnung():
    """Editor-Entwurf = from_dict(to_dict()); Ruecksetzen = apply_dict(Preset)."""
    m = _matrix("m")
    m.modify, m.modify_mode, m.modify_strength = True, "dim", 70
    entwurf = RgbMatrixInstance.from_dict(m.to_dict())
    assert (entwurf.modify, entwurf.modify_mode, entwurf.modify_strength) == (
        True, "dim", 70)
    assert entwurf.to_dict() == m.to_dict()
    # Haken im Entwurf entfernt und gespeichert -> am Original wirklich weg
    entwurf.modify = False
    entwurf.modify_mode, entwurf.modify_strength = "add", 100
    m.apply_dict(entwurf.to_dict())
    assert (m.modify, m.modify_mode, m.modify_strength) == (False, "add", 100)


_ALGOS = [RgbAlgorithm.PLAIN, RgbAlgorithm.CHASE, RgbAlgorithm.WIPE,
          RgbAlgorithm.WAVE, RgbAlgorithm.FILL, RgbAlgorithm.STROBE,
          RgbAlgorithm.CHECKER, RgbAlgorithm.BREATHE, RgbAlgorithm.RADAR]


@pytest.mark.parametrize("algo", _ALGOS, ids=[a.value for a in _ALGOS])
@pytest.mark.parametrize("variante", ["vorgabe", "art_gemerkt"])
def test_dmx_ohne_haken_wie_bisher(rig, algo, variante):
    """Alt = der Effekt schreibt direkt ins Universum (der Weg vor ENG-37).
    Neu = derselbe Effekt ueber den FunctionManager. Ohne Haken identisch —
    auch wenn Art/Staerke von einem frueheren Haken noch gemerkt sind."""
    alt = _matrix("alt", algo)
    neu = _matrix("neu", algo)
    if variante == "art_gemerkt":
        neu.modify_mode, neu.modify_strength = "sub", 30
    unten = _pegel(77)
    alt.start()
    fm = _fm(unten, neu)
    bewegt = set()
    for _ in range(40):
        ua = Universe(1)
        ua.set_range(1, bytes([77] * N))
        alt.write({1: ua}, rig, 0.05, {})
        bild, _ = _tick(fm, rig, dt=0.05)
        assert bild == list(ua.get_all()[:N]), algo.value
        bewegt.add(tuple(bild))
    if algo not in (RgbAlgorithm.PLAIN, RgbAlgorithm.CHECKER, RgbAlgorithm.WIPE):
        assert len(bewegt) > 1, f"{algo.value} bewegt sich nicht — Test prueft nichts"


def test_effekt_helligkeit_normaler_effekt_unveraendert(rig):
    """Der bisherige Weg „Ergebnis skalieren" gilt ohne Haken weiter."""
    m = _pegel(255)
    m.intensity = 0.5
    bild, _ = _tick(_fm(m), rig)
    assert bild == [127] * N


def test_tick_reihenfolge_ohne_modify_wie_bisher(rig):
    """Gleiche Prioritaet: Start-Reihenfolge entscheidet, kein Hoechstwert."""
    a, b = _pegel(200), _pegel(50)
    bild, _ = _tick(_fm(a, b), rig)
    assert bild == [50] * N
    bild, _ = _tick(_fm(a, b, start=(b, a)), rig)
    assert bild == [200] * N


# ── Konsole: Regler-Parameter ────────────────────────────────────────────────


def test_parameterliste_ohne_haken_unveraendert():
    m = _matrix("m", RgbAlgorithm.CHASE)
    schluessel = [s.key for s in m.list_params()]
    assert "modify_strength" not in schluessel and "modify_mode" not in schluessel
    m.modify = True
    mit = [s.key for s in m.list_params()]
    assert [k for k in mit if not k.startswith("modify")] == schluessel
    m.style = MatrixStyle.RGB                # Haken bei Farbe: nicht wirksam
    assert not [s.key for s in m.list_params() if s.key.startswith("modify")]


def test_modify_staerke_als_regler_parameter():
    from src.core.engine import effect_live
    fm = FunctionManager()
    m = _lauflicht("add")
    fm.add(m)
    spec = {s.key: s for s in m.list_params()}
    st = spec["modify_strength"]
    assert (st.label, st.kind, st.min, st.max, st.default) == (
        "Modify-Stärke", "int", 0, 100, 100)
    assert st.mappable and st.live_editable
    assert spec["modify_mode"].kind == "select"
    assert tuple(spec["modify_mode"].options) == MODIFY_MODES
    assert m.set_param("modify_strength", 42) and m.get_param("modify_strength") == 42
    assert m.set_param("modify_strength", 400) and m.modify_strength == 100
    assert m.set_param("modify_mode", "dim") and m.get_param("modify_mode") == "dim"
    assert m.set_param("modify_mode", "kaputt") is False and m.modify_mode == "dim"


def test_regler_stellt_die_staerke_live(rig):
    unten = _pegel()
    mod = _spion(_lauflicht("add"))
    fm = _fm(unten, mod)
    mod.set_param("modify_strength", 50)
    bild, _ = _tick(fm, rig)
    assert bild == [230 if i in _aktiv(mod) else P40 for i in range(N)]
    mod.set_param("modify_strength", 0)
    bild, _ = _tick(fm, rig)
    assert bild == [P40] * N


def test_anzeige_namen_der_betriebsarten():
    from src.ui.virtualconsole.vc_effect_meta import option_label
    assert [option_label(m, "modify_mode") for m in MODIFY_MODES] == [
        "Addieren", "Abziehen", "Abdunkeln"]


def test_parameter_sind_dem_faehigkeiten_abgleich_bekannt():
    from src.core.capability.reflect import _UNIVERSAL_MATRIX_PARAMS
    assert {"modify_strength", "modify_mode"} <= _UNIVERSAL_MATRIX_PARAMS


# ── Renderer: Modify rechnet auf das fertige Bild (auch Snaps/Programmer) ────


def _zustand(monkeypatch, fm, default=0):
    """Schlanker AppState (Muster test_matrix_dimmer_master) mit ECHTEM
    FunctionManager und den acht Dimmer-Lampen."""
    from src.core.app_state import AppState
    kanaele = {fid: [_Ch("intensity", 1, default)] for fid in range(1, N + 1)}
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele[fx.fid])
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = [_Fx(fid, fid) for fid in range(1, N + 1)]
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    st._rebuild_render_plan()
    return st


def _ausgabe(st):
    return list(st.universes[1].get_all()[:N])


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_wirkt_auf_programmer_werte(monkeypatch, mode):
    """Snap-/Programmer-Dimmer auf 50 %: unter dem Laeufer wird abgezogen,
    alle anderen Lampen bleiben exakt auf dem Snap-Wert."""
    mod = _spion(_lauflicht(mode))
    st = _zustand(monkeypatch, _fm(mod))
    st.programmer = {fid: {"intensity": 128} for fid in range(1, N + 1)}
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert _ausgabe(st) == [0 if i in aktiv else 128 for i in range(N)]


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_wirkt_auf_ruhewerte(monkeypatch, mode):
    mod = _spion(_lauflicht(mode))
    st = _zustand(monkeypatch, _fm(mod), default=200)
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert _ausgabe(st) == [0 if i in aktiv else 200 for i in range(N)]


def test_addieren_besitzt_den_dimmer_nicht(monkeypatch):
    """Ein Addieren-Modify ist KEIN Besitzer des Dimmers: der Programmer-/
    Snap-Dimmer darunter zaehlt weiter, der Laeufer legt obendrauf. Ohne Haken
    (normaler Dimmer-Effekt) gehoert der Dimmer dem Effekt wie bisher."""
    mod = _spion(_lauflicht("add"))
    st = _zustand(monkeypatch, _fm(mod))
    st.programmer = {fid: {"intensity": 128} for fid in range(1, N + 1)}
    st._render_frame(DT)
    aktiv = _aktiv(mod)
    assert len(aktiv) == 2
    assert _ausgabe(st) == [255 if i in aktiv else 128 for i in range(N)]

    normal = _lauflicht("add")
    normal.modify = False
    st = _zustand(monkeypatch, _fm(normal))
    st.programmer = {fid: {"intensity": 128} for fid in range(1, N + 1)}
    st._render_frame(DT)
    assert sorted(_ausgabe(st)) == [0] * 6 + [255] * 2


def test_renderer_beispiel_mit_effekt_darunter(monkeypatch):
    unten = _pegel()
    mod = _spion(_lauflicht("sub"))
    st = _zustand(monkeypatch, _fm(unten, mod))
    st._render_frame(DT)
    assert _ausgabe(st) == [0 if i in _aktiv(mod) else P40 for i in range(N)]

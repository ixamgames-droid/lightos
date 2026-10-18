"""ENG-37: „Schrittweite“ des Lauflichts (Chase) — ``params["runner_step"]``.

Wunsch des Betreibers: „bei zwei Lampen 100 % dazu, danach bei den naechsten
zwei“ — also 1+2, dann 3+4, 5+6, 7+8. Mit „Laeufer-Breite“ 2 allein wandert
der Laeufer nur um EINE Lampe (1+2 → 2+3), mit „Laeufer-Anzahl“ 2 stehen zwei
Laeufer vier Lampen auseinander.

Festgelegt (rgb_matrix.py, ``_render_chase``):

* Vorgabe 1 = wie bisher, fuer jede Show byte- und bildgleich. 0 = „wie Breite“.
* Schrittweite > 1: die Reihe ist in Bloecke geteilt, Block j beginnt bei
  Lampe j x Schrittweite; je Runde ceil(Laenge / Schrittweite) Schritte.
  Der Laeufer belegt „Breite“ Lampen ab dem Blockanfang und steht zwischen
  zwei Schritten still.
* Rueckwaerts: dieselben Bloecke in umgekehrter Folge, Start auf Lampe 1.
* Ping-Pong: Bloecke hin und zurueck, am Rand abgeschnitten.
* Mehrere Laeufer: jeder weitere um Laenge/Anzahl versetzt.
* Schweif: raeumlich, an der Hinterkante des Blocks, springt mit.
* Ring-Bewegungen (center_out/outside_in): Schrittweite wirkt nicht.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

N = 8
P40 = 102


def _lauf(n=N, richtung="forward", stil=MatrixStyle.DIMMER, rows=1, **params):
    m = RgbMatrixInstance("lauf", cols=n, rows=rows,
                          fixture_grid=list(range(1, n * rows + 1)),
                          algorithm=RgbAlgorithm.CHASE, color1=(255, 255, 255))
    m.style = stil
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    m.direction = richtung
    m.params.update({"after_fade": 0.0})
    m.params.update(params)
    return m


def _bild(m, schritt):
    """Helligkeit je Lampe in Prozent beim Schritt ``schritt``."""
    return [round(max(c) * 100 / 255) for c in m._render(float(schritt))]


def _an(m, schritt):
    """Nummern (1-basiert) der voll leuchtenden Lampen."""
    return [i + 1 for i, v in enumerate(_bild(m, schritt)) if v == 100]


# ── Das Beispiel des Betreibers ──────────────────────────────────────────────


def test_zwei_lampen_dann_die_naechsten_zwei():
    m = _lauf(runner_width=2, runner_step=2)
    assert [_an(m, s) for s in range(9)] == [
        [1, 2], [3, 4], [5, 6], [7, 8], [1, 2], [3, 4], [5, 6], [7, 8], [1, 2]]
    # zwischen zwei Schritten steht der Laeufer still
    assert _bild(m, 1.0) == _bild(m, 1.5) == _bild(m, 1.99)
    assert _bild(m, 1.99) != _bild(m, 2.0)


def test_wie_breite_ist_schrittweite_null():
    for breite in (1, 2, 3, 4):
        a = _lauf(runner_width=breite, runner_step=0)
        b = _lauf(runner_width=breite, runner_step=breite)
        for s in range(20):
            assert _bild(a, s) == _bild(b, s)
    assert [_an(_lauf(runner_width=4, runner_step=0), s) for s in range(3)] == [
        [1, 2, 3, 4], [5, 6, 7, 8], [1, 2, 3, 4]]


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0
        self.ranges = []


class _Fx:
    def __init__(self, fid):
        self.fid = fid
        self.universe = 1
        self.address = fid


@pytest.fixture
def rig(monkeypatch):
    kanaele = {fid: [_Ch("intensity", 1)] for fid in range(1, N + 1)}
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele[fx.fid])
    return [_Fx(fid) for fid in range(1, N + 1)]


def _spion(m):
    orig = m.write
    m.ausgabe = None

    def write(universes, patch_cache, dt, reg=None):
        orig(universes, patch_cache, dt, reg)
        m.ausgabe = list(universes[1].get_all()[:N])
    m.write = write
    return m


def _modify(**params):
    m = _lauf(**params)
    m.modify, m.modify_mode, m.modify_strength = True, "add", 100
    return m


def _folge(fm, rig, frames, dt=0.25):
    """Bilder Frame fuer Frame; aufeinanderfolgende gleiche zusammengefasst."""
    folge = []
    for _ in range(frames):
        u = Universe(1)
        fm.tick({1: u}, rig, dt)
        bild = list(u.get_all()[:N])
        if not folge or folge[-1] != bild:
            folge.append(bild)
    return folge


def test_beispiel_addieren_ueber_40_prozent(rig):
    """8 Lampen, Breite 2, Schrittweite 2, Addieren 100 % ueber 40 %:
    Schritt 1 = 100 100 40 40 40 40 40 40, Schritt 2 = 40 40 100 100 40 … ."""
    unten = RgbMatrixInstance("unten", cols=N, rows=1,
                              fixture_grid=list(range(1, N + 1)),
                              algorithm=RgbAlgorithm.PLAIN, color1=(255, 255, 255))
    unten.style = MatrixStyle.DIMMER
    unten.tempo_bus_id = ""
    unten.intensity_min = unten.intensity_max = P40
    mod = _modify(runner_width=2, runner_step=2)
    fm = FunctionManager()
    for f in (unten, mod):
        fm.add(f)
        fm.start(f.id)
    folge = _folge(fm, rig, 36)                # 9 Schritte zu je 4 Frames
    prozent = [[round(v * 100 / 255) for v in bild] for bild in folge]
    assert prozent[:5] == [
        [100, 100, 40, 40, 40, 40, 40, 40],
        [40, 40, 100, 100, 40, 40, 40, 40],
        [40, 40, 40, 40, 100, 100, 40, 40],
        [40, 40, 40, 40, 40, 40, 100, 100],
        [100, 100, 40, 40, 40, 40, 40, 40],
    ]
    assert folge[1] == [P40, P40, 255, 255, P40, P40, P40, P40]


def test_beispiel_addieren_ueber_funkeln(rig):
    """Dasselbe ueber einem echten Funkeln (Random): unter dem Laeufer-Paar
    100 %, ueberall sonst in JEDEM Frame exakt der Wert des Funkelns."""
    unten = _spion(RgbMatrixInstance(
        "funkeln", cols=N, rows=1, fixture_grid=list(range(1, N + 1)),
        algorithm=RgbAlgorithm.RANDOM, color1=(255, 255, 255)))
    unten.style = MatrixStyle.DIMMER
    unten.tempo_bus_id = ""
    mod = _spion(_modify(runner_width=2, runner_step=2))
    fm = FunctionManager()
    for f in (unten, mod):
        fm.add(f)
        fm.start(f.id)
    paare, werte = [], set()
    for _ in range(80):
        u = Universe(1)
        fm.tick({1: u}, rig, 0.25)
        bild = list(u.get_all()[:N])
        an = [i for i, w in enumerate(mod.ausgabe) if w == 255]
        assert len(an) == 2 and an[1] == an[0] + 1 and an[0] % 2 == 0
        for i in range(N):
            assert bild[i] == (255 if i in an else unten.ausgabe[i])
        if not paare or paare[-1] != an:
            paare.append(an)
        werte.add(tuple(unten.ausgabe))
    assert paare[:5] == [[0, 1], [2, 3], [4, 5], [6, 7], [0, 1]]
    assert len(werte) > 1, "Funkeln hat sich nicht bewegt — Test prueft nichts"


# ── Vorgabe 1 = wie bisher ───────────────────────────────────────────────────


_KOMBIS = [
    {}, {"runner_width": 2}, {"runner_width": 3, "runner_count": 2},
    {"runner_count": 4}, {"after_fade": 30.0}, {"after_fade": 60.0, "runner_width": 2},
    {"movement": "bounce"}, {"movement": "bounce", "runner_width": 2},
    {"movement": "center_out"}, {"movement": "outside_in", "runner_width": 2},
    {"invert": True}, {"axis": "V"}, {"axis": "Diag", "runner_width": 2},
    {"dimmer_cycle": True}, {"color_cycle": True},
]


@pytest.mark.parametrize("params", _KOMBIS, ids=[json.dumps(k) for k in _KOMBIS])
@pytest.mark.parametrize("richtung", ["forward", "reverse"])
def test_schrittweite_eins_ist_wie_ohne_angabe(params, richtung):
    for stil in (MatrixStyle.DIMMER, MatrixStyle.RGB):
        ohne = _lauf(richtung=richtung, stil=stil, rows=2, **params)
        mit = _lauf(richtung=richtung, stil=stil, rows=2, runner_step=1, **params)
        for k in range(120):
            s = k * 0.17
            assert ohne._render(s) == mit._render(s)


def test_bild_bei_schrittweite_eins_festgenagelt():
    """Der bisherige Lauf, als Zahlen festgehalten (Breite 2: der Laeufer
    zieht die zweite Lampe HINTER sich her und laeuft um)."""
    m = _lauf(runner_width=2)
    assert [_an(m, s) for s in range(4)] == [[1, 8], [1, 2], [2, 3], [3, 4]]
    m = _lauf(runner_width=1, runner_count=2)
    assert [_an(m, s) for s in range(3)] == [[1, 5], [2, 6], [3, 7]]
    m = _lauf(movement="bounce")
    assert [_an(m, s) for s in range(9)] == [
        [1], [2], [3], [4], [5], [6], [7], [8], [7]]


def test_show_ohne_schrittweite_speichert_byte_gleich():
    m = _lauf(runner_width=2)
    d = m.to_dict()
    assert "runner_step" not in d["params"]
    fm = FunctionManager()
    fm.add(m)
    vorher = json.dumps(fm.to_dict(), sort_keys=True)
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(vorher))
    assert json.dumps(fm2.to_dict(), sort_keys=True) == vorher
    assert "runner_step" not in vorher


def test_show_mit_schrittweite_laedt_und_speichert():
    m = _lauf(runner_width=2, runner_step=2)
    fm = FunctionManager()
    fm.add(m)
    text = json.dumps(fm.to_dict(), sort_keys=True)
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(text))
    m2 = next(iter(fm2._functions.values()))
    assert m2.params["runner_step"] == 2
    assert [_an(m2, s) for s in range(3)] == [[1, 2], [3, 4], [5, 6]]
    assert json.dumps(fm2.to_dict(), sort_keys=True) == text


# ── Zusammenspiel ────────────────────────────────────────────────────────────


def test_rueckwaerts():
    m = _lauf(richtung="reverse", runner_width=2, runner_step=2)
    assert [_an(m, s) for s in range(6)] == [
        [1, 2], [7, 8], [5, 6], [3, 4], [1, 2], [7, 8]]
    # Schrittweite 1 startet rueckwaerts ebenfalls auf Lampe 1
    assert _an(_lauf(richtung="reverse"), 0) == [1]


def test_ping_pong():
    m = _lauf(movement="bounce", runner_width=2, runner_step=2)
    assert [_an(m, s) for s in range(8)] == [
        [1, 2], [3, 4], [5, 6], [7, 8], [5, 6], [3, 4], [1, 2], [3, 4]]


def test_ping_pong_schneidet_am_rand_ab():
    """8 Lampen, Schrittweite 3, Breite 3: Bloecke 1–3, 4–6, 7–8 (kein Umlauf)."""
    m = _lauf(movement="bounce", runner_width=3, runner_step=3)
    assert [_an(m, s) for s in range(5)] == [
        [1, 2, 3], [4, 5, 6], [7, 8], [4, 5, 6], [1, 2, 3]]


def test_ping_pong_ein_einziger_block():
    m = _lauf(movement="bounce", runner_width=2, runner_step=8)
    assert [_an(m, s) for s in range(3)] == [[1, 2]] * 3


def test_mehrere_laeufer():
    m = _lauf(runner_width=1, runner_step=2, runner_count=2)
    assert [_an(m, s) for s in range(3)] == [[1, 5], [3, 7], [1, 5]]
    m = _lauf(runner_width=2, runner_step=2, runner_count=2)
    assert [_an(m, s) for s in range(3)] == [
        [1, 2, 5, 6], [3, 4, 7, 8], [1, 2, 5, 6]]


def test_mehrere_laeufer_rueckwaerts():
    m = _lauf(richtung="reverse", runner_width=2, runner_step=2, runner_count=2)
    assert [_an(m, s) for s in range(3)] == [
        [1, 2, 5, 6], [3, 4, 7, 8], [1, 2, 5, 6]]


def test_laenge_nicht_teilbar_beginnt_jede_runde_vorn():
    """8 Lampen, Schrittweite 3: Bloecke ab Lampe 1, 4, 7 — dann wieder 1.
    Im normalen Lauf ist die Reihe ein Ring: der letzte Block laeuft um."""
    m = _lauf(runner_width=2, runner_step=3)
    assert [_an(m, s) for s in range(4)] == [[1, 2], [4, 5], [7, 8], [1, 2]]
    m = _lauf(runner_width=3, runner_step=3)
    assert [_an(m, s) for s in range(4)] == [
        [1, 2, 3], [4, 5, 6], [1, 7, 8], [1, 2, 3]]


def test_schweif_liegt_hinter_dem_block_und_springt_mit():
    """Breite 2, Schrittweite 2, Schweif 50 % (= 4 Lampen): der Schweif faellt
    ueber die eben verlassenen Lampen ab — raeumlich, an der Hinterkante.
    (Wie bei Schrittweite 1 beginnt der Schweif mit 100 % auf der ersten Lampe
    hinter dem Laeufer und faellt dann je Lampe gleichmaessig.)"""
    m = _lauf(runner_width=2, runner_step=2, after_fade=50.0)
    assert _bild(m, 1) == [75, 100, 100, 100, 0, 0, 25, 50]
    assert _bild(m, 2) == [25, 50, 75, 100, 100, 100, 0, 0]
    assert _bild(m, 2) == _bild(m, 2.9), "Schweif laeuft zwischen Schritten nach"
    # Schrittweite groesser als Breite: auch die uebersprungenen Lampen
    # (nie voll an) liegen im Schweif.
    m = _lauf(runner_width=1, runner_step=3, after_fade=50.0)
    assert _bild(m, 1) == [50, 75, 100, 100, 0, 0, 0, 25]


def test_schweif_rueckwaerts_haengt_auf_der_anderen_seite():
    m = _lauf(richtung="reverse", runner_width=2, runner_step=2, after_fade=50.0)
    # Schritt 2: Block 5+6, gekommen von 7+8 -> Schweif auf 7, 8, 1, 2
    assert _bild(m, 2) == [50, 25, 0, 0, 100, 100, 100, 75]


def test_schweif_null_ist_harte_kante():
    m = _lauf(runner_width=2, runner_step=2, after_fade=0.0)
    for s in range(8):
        assert sorted(_bild(m, s)) == [0] * 6 + [100] * 2


def test_ring_bewegungen_ignorieren_die_schrittweite():
    for bewegung in ("center_out", "outside_in"):
        a = _lauf(movement=bewegung, runner_width=2)
        b = _lauf(movement=bewegung, runner_width=2, runner_step=4)
        for k in range(60):
            assert a._render(k * 0.3) == b._render(k * 0.3)


def test_invertieren():
    m = _lauf(runner_width=2, runner_step=2, invert=True)
    assert _bild(m, 1) == [100, 100, 0, 0, 100, 100, 100, 100]


def test_senkrechte_achse():
    m = RgbMatrixInstance("v", cols=2, rows=4, fixture_grid=list(range(1, 9)),
                          algorithm=RgbAlgorithm.CHASE, color1=(255, 255, 255))
    m.params.update({"axis": "V", "after_fade": 0.0,
                     "runner_width": 2, "runner_step": 2})
    assert _an(m, 0) == [1, 2, 3, 4]         # Zeile 1+2
    assert _an(m, 1) == [5, 6, 7, 8]         # Zeile 3+4
    assert _an(m, 2) == [1, 2, 3, 4]


def test_dimmerwert_pro_runde_zaehlt_in_schritten():
    """Eine Runde hat bei Schrittweite 2 auf acht Lampen vier Schritte — der
    Dimmerwert wechselt nach vier, nicht nach acht Schritten."""
    m = _lauf(runner_width=2, runner_step=2, dimmer_cycle=True)
    stufen = m.dimmer_levels.enabled_levels()
    assert len(stufen) >= 2 and stufen[0] != stufen[1]

    def wert(s):
        return max(max(c) for c in m._render(float(s)))
    assert [wert(s) for s in range(4)] == [stufen[0]] * 4
    assert [wert(s) for s in range(4, 8)] == [stufen[1]] * 4


def test_unlesbare_schrittweite_ist_eins():
    for kaputt in ("viel", None, -3):
        m = _lauf(runner_width=2, runner_step=kaputt)
        if kaputt == -3:                      # <= 0 heisst „wie Breite“
            assert _an(m, 1) == [3, 4]
        else:
            assert _an(m, 1) == _an(_lauf(runner_width=2), 1)


# ── Konsole ──────────────────────────────────────────────────────────────────


def test_konsolen_parameter():
    m = _lauf()
    spec = {s.key: s for s in m.list_params()}
    assert "runner_step" in spec
    s = spec["runner_step"]
    assert (s.label, s.kind, s.default, s.min, s.max) == (
        "Schrittweite", "int", 1, 0, 16)
    assert m.get_param("runner_step") is None      # ungesetzt, wie Laeufer-Breite
    assert m.set_param("runner_step", 2) and m.params["runner_step"] == 2
    assert m.get_param("runner_step") == 2
    assert m.set_param("runner_step", 99) and m.params["runner_step"] == 16
    assert m.set_param("runner_step", -5) and m.params["runner_step"] == 0


def test_konsolen_parameter_nur_bei_linearer_bewegung():
    for bewegung, da in (("normal", True), ("bounce", True),
                         ("center_out", False), ("outside_in", False)):
        m = _lauf(movement=bewegung)
        assert ("runner_step" in [s.key for s in m.list_params()]) is da
    for stil in (MatrixStyle.RGB, MatrixStyle.RGBW, MatrixStyle.SHUTTER):
        assert "runner_step" in [s.key for s in _lauf(stil=stil).list_params()]
    andere = RgbMatrixInstance("w", cols=N, rows=1, algorithm=RgbAlgorithm.WIPE)
    assert "runner_step" not in [s.key for s in andere.list_params()]

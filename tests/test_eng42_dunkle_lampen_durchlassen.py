"""ENG-42: Echter Läufer über einem Untergrund — Haken „Dunkle Lampen durchlassen“.

Ein normales Dimmer-Lauflicht schreibt für JEDE seiner Lampen einen Wert, auch
0 für die gerade dunklen, und verdeckt damit einen Effekt darunter vollständig.
Mit dem Haken (nur Stil Dimmer) schreibt es nur Lampen mit einem Wert über 0 —
genau gesetzt, wie ein normaler Effekt in seiner Stufe (KEIN Modify, der
addiert). Die dunklen schreibt es gar nicht: sie stehen in keinem
Schreib-Protokoll, besitzen keinen Dimmer, die automatische Grundhelligkeit
und Snap-/Programmer-Dimmer greifen dort wie ohne den Effekt.

Das Beispiel des Betreibers: Untergrund 40 %, Läufer 70 % -> genau 70 % auf
den Läufer-Lampen, 40 % auf den übrigen.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
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
from src.core.engine.rgb_matrix import (                    # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

N = 8                 # acht Lampen, je ein Dimmer-Kanal auf Adresse 1..8
P40 = 102             # 40 % von 255
P70 = 178             # 70 % von 255
DT = 0.02
OBEN = 20             # Stufe des Läufers (über dem Untergrund, Stufe 0)


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
    kanaele = {fid: [_Ch("intensity", 1)] for fid in range(1, N + 1)}
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: kanaele[fx.fid])
    return [_Fx(fid, fid) for fid in range(1, N + 1)]


def _matrix(name, algo=RgbAlgorithm.PLAIN, **felder) -> RgbMatrixInstance:
    m = RgbMatrixInstance(name, cols=N, rows=1,
                          fixture_grid=list(range(1, N + 1)),
                          algorithm=algo, color1=(255, 255, 255))
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""
    m.matrix_speed = 1.0
    for k, v in felder.items():
        setattr(m, k, v)
    return m


def _pegel(wert=P40) -> RgbMatrixInstance:
    return _matrix("unten", intensity_min=wert, intensity_max=wert)


def _laeufer(durchlassen=True, schweif=0.0, **felder) -> RgbMatrixInstance:
    """Lauflicht mit zwei Läufern auf 70 %, Stufe über dem Untergrund."""
    m = _matrix("läufer", RgbAlgorithm.CHASE, intensity_max=P70, **felder)
    m.params.update({"runner_count": 2, "after_fade": schweif, "fade": 0.0,
                     "movement": "normal"})
    m.priority = OBEN
    m.dunkle_durchlassen = durchlassen
    return m


def _spion(m):
    """Merkt sich, was ``m`` allein ausgeben würde (eigene Lampenwerte)."""
    orig = m.write
    m.ausgabe = None

    def write(universes, patch_cache, dt, reg=None):
        orig(universes, patch_cache, dt, reg)
        # Was der Effekt wirklich ausgibt — gerendert aus demselben Schritt.
        m.ausgabe = [m._dimmer_output(px) for px in m._render(m._step)][:N]
    m.write = write
    return m


def _tick(fm, rig, dt=DT):
    u = Universe(1)
    u.begin_write_log()
    fm.tick({1: u}, rig, dt)
    return list(u.get_all()[:N]), u.end_write_log()


def _fm(*funktionen, start=None):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in (start if start is not None else funktionen):
        fm.start(f.id)
    return fm


def _hell(m):
    return [i for i, w in enumerate(m.ausgabe) if w > 0]


# ── Das Beispiel des Betreibers ──────────────────────────────────────────────


@pytest.mark.parametrize("reihenfolge", ["unten_zuerst", "laeufer_zuerst"])
def test_untergrund_40_laeufer_70_genau(rig, reihenfolge):
    unten = _pegel()
    lauf = _spion(_laeufer())
    start = (unten, lauf) if reihenfolge == "unten_zuerst" else (lauf, unten)
    fm = _fm(unten, lauf, start=start)
    gesehen = set()
    for _ in range(30):
        bild, _ = _tick(fm, rig, dt=0.1)
        hell = _hell(lauf)
        assert len(hell) == 2, lauf.ausgabe
        assert bild == [P70 if i in hell else P40 for i in range(N)], bild
        gesehen.add(tuple(hell))
    assert len(gesehen) > 1, "Läufer bewegt sich nicht — Test prüft nichts"


def test_ohne_haken_unveraendert_verdeckt(rig):
    """Gegenprobe: ohne Haken verdeckt das Lauflicht den Untergrund wie bisher."""
    unten = _pegel()
    lauf = _spion(_laeufer(durchlassen=False))
    fm = _fm(unten, lauf)
    bild, _ = _tick(fm, rig)
    hell = _hell(lauf)
    assert bild == [P70 if i in hell else 0 for i in range(N)]


@pytest.mark.parametrize("algo", [RgbAlgorithm.PLAIN, RgbAlgorithm.CHASE,
                                  RgbAlgorithm.WAVE, RgbAlgorithm.STROBE,
                                  RgbAlgorithm.FILL, RgbAlgorithm.CHECKER])
def test_ohne_haken_byte_gleich_zum_direkten_schreiben(rig, algo):
    """Ohne Haken: Ausgabe über den FunctionManager identisch zum direkten
    write() — auch wenn der Haken in einem anderen Stil gemerkt ist."""
    alt = _matrix("alt", algo)
    neu = _matrix("neu", algo)
    alt.start()
    fm = _fm(_pegel(77), neu)
    for _ in range(25):
        ua = Universe(1)
        ua.set_range(1, bytes([77] * N))
        alt.write({1: ua}, rig, 0.05, {})
        bild, _ = _tick(fm, rig, dt=0.05)
        assert bild == list(ua.get_all()[:N]), algo.value


def test_laeufer_auf_niedrigerer_stufe_bleibt_unten(rig):
    """Der Haken ändert nichts an der Stufe: liegt der Untergrund höher,
    gewinnt er überall (er schreibt jede Lampe)."""
    unten = _pegel()
    unten.priority = OBEN + 10
    lauf = _laeufer()
    bild, _ = _tick(_fm(unten, lauf), rig)
    assert bild == [P40] * N


# ── Schweif, Ein-/Ausblendung, Effekt-Helligkeit ─────────────────────────────


def test_schweif_lampen_zaehlen_als_hell(rig):
    unten = _pegel()
    lauf = _spion(_laeufer(schweif=30.0))
    fm = _fm(unten, lauf)
    zwischen = dunkel = 0
    for _ in range(40):
        bild, _ = _tick(fm, rig, dt=0.07)
        for i in range(N):
            w = lauf.ausgabe[i]
            assert bild[i] == (w if w > 0 else P40), (i, bild, lauf.ausgabe)
            if 0 < w < P70:
                zwischen += 1
            elif w == 0:
                dunkel += 1
    assert zwischen > 0, "kein Schweif gerendert — Test prüft nichts"
    assert dunkel > 0, "keine dunkle Lampe — Test prüft nichts"


def _paar(rig, **felder):
    """Zwei identische Läufer — mit und ohne Haken — je über dem Untergrund."""
    mit = _spion(_laeufer(**felder))
    ohne = _spion(_laeufer(durchlassen=False, **felder))
    return (_fm(_pegel(), mit), mit), (_fm(_pegel(), ohne), ohne)


def test_einblenden_wie_beim_normalen_effekt(rig):
    (fm_m, mit), (fm_o, ohne) = _paar(rig, matrix_speed=0.0, env_fade_in=1.0)
    verlauf = []
    for _ in range(30):
        b_m, _ = _tick(fm_m, rig, dt=0.05)
        b_o, _ = _tick(fm_o, rig, dt=0.05)
        hell = _hell(mit)
        assert len(hell) == 2
        assert [b_m[i] for i in hell] == [b_o[i] for i in hell]
        assert [b_m[i] for i in range(N) if i not in hell] == [P40] * 6
        verlauf.append(b_m[hell[0]])
    assert verlauf[0] < P70 and verlauf[-1] == P70
    assert verlauf == sorted(verlauf)


def test_ausblenden_wie_beim_normalen_effekt(rig):
    (fm_m, mit), (fm_o, ohne) = _paar(rig, matrix_speed=0.0, env_fade_out=1.0)
    _tick(fm_m, rig)
    _tick(fm_o, rig)
    hell = _hell(mit)
    fm_m.stop(mit.id)
    fm_o.stop(ohne.id)
    verlauf = []
    for _ in range(40):
        b_m, _ = _tick(fm_m, rig, dt=0.05)
        b_o, _ = _tick(fm_o, rig, dt=0.05)
        assert [b_m[i] for i in range(N) if i not in hell] == [P40] * 6
        if fm_o.is_running(ohne.id):
            assert [b_m[i] for i in hell] == [b_o[i] for i in hell]
        verlauf.append(b_m[hell[0]])
    assert verlauf[0] < P70
    assert not fm_m.is_running(mit.id)
    assert verlauf[-1] == P40          # danach wieder der Untergrund


def test_effekt_helligkeit_wie_beim_normalen_effekt(rig):
    (fm_m, mit), (fm_o, ohne) = _paar(rig)
    mit.intensity = ohne.intensity = 0.5
    b_m, _ = _tick(fm_m, rig)
    b_o, _ = _tick(fm_o, rig)
    hell = _hell(mit)
    assert [b_m[i] for i in hell] == [int(P70 * 0.5)] * 2
    assert [b_m[i] for i in hell] == [b_o[i] for i in hell]
    assert [b_m[i] for i in range(N) if i not in hell] == [P40] * 6


def test_min_ueber_null_laesst_nichts_durch(rig):
    """„Wert über 0“ ist wörtlich: steht Min über 0, ist keine Lampe dunkel."""
    lauf = _laeufer(intensity_min=30)
    bild, _ = _tick(_fm(_pegel(), lauf), rig)
    assert P40 not in bild and sorted(set(bild)) == [30, P70]


# ── Schreib-Protokoll ────────────────────────────────────────────────────────


@pytest.mark.parametrize("helligkeit", [1.0, 0.5])   # schneller und priv-Pfad
def test_protokoll_nur_helle_lampen(rig, helligkeit):
    lauf = _spion(_laeufer())
    lauf.intensity = helligkeit
    _, geschrieben = _tick(_fm(lauf), rig)
    assert geschrieben == {i + 1 for i in _hell(lauf)}
    ohne = _laeufer(durchlassen=False)
    ohne.intensity = helligkeit
    _, geschrieben = _tick(_fm(ohne), rig)
    assert geschrieben == set(range(1, N + 1))


def test_andere_stile_ignorieren_den_haken(monkeypatch):
    """Nur Stil Dimmer: im Stil RGB bleibt ein gesetzter Haken wirkungslos."""
    kan = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kan)
    rig3 = [_Fx(fid, (fid - 1) * 3 + 1) for fid in range(1, N + 1)]
    bilder = []
    for haken in (False, True):
        m = _laeufer(durchlassen=haken)
        m.style = MatrixStyle.RGB
        assert m._dunkle_durchlassen() is False
        u = Universe(1)
        u.begin_write_log()
        _fm(m).tick({1: u}, rig3, DT)
        bilder.append((list(u.get_all()[:3 * N]), u.end_write_log()))
    assert bilder[0] == bilder[1]


def test_modify_ignoriert_den_haken(rig):
    """Gegenprüfung: bei Modify wirkt ein gemerkter Haken nicht (wie Tooltip
    und Anleitung sagen). Zwei Zellen auf EINEM Gerät: mit wirkendem Haken
    schriebe nur die helle Zelle — der Modify-Betrag änderte sich."""
    from src.core.engine.modify import modify_posten
    ergebnisse = []
    for haken in (False, True):
        m = RgbMatrixInstance("mod", cols=2, rows=1, fixture_grid=[1, 1],
                              algorithm=RgbAlgorithm.CHASE,
                              color1=(255, 255, 255))
        m.style = MatrixStyle.DIMMER
        m.tempo_bus_id = ""
        m.matrix_speed = 1.0
        m.params.update({"runner_count": 1, "after_fade": 0.0, "fade": 0.0,
                         "movement": "normal"})
        m.modify = True
        m.dunkle_durchlassen = haken
        assert m._dunkle_durchlassen() is False
        m.start()
        ergebnisse.append([modify_posten(m, [1], rig[:1], DT)
                           for _ in range(6)])
    assert ergebnisse[0] == ergebnisse[1]


# ── Renderer: Besitz, Grundhelligkeit, Snap-Dimmer ───────────────────────────


def _zustand(monkeypatch, fm, kanaele=None, adressen=None):
    from src.core.app_state import AppState
    kanaele = kanaele or {fid: [_Ch("intensity", 1)] for fid in range(1, N + 1)}
    adressen = adressen or {fid: fid for fid in range(1, N + 1)}
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele[fx.fid])
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = [_Fx(fid, adressen[fid]) for fid in range(1, N + 1)]
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


def _ausgabe(st, n=N):
    return list(st.universes[1].get_all()[:n])


def test_renderer_beispiel(monkeypatch):
    lauf = _spion(_laeufer())
    st = _zustand(monkeypatch, _fm(_pegel(), lauf))
    st._render_frame(DT)
    hell = _hell(lauf)
    assert _ausgabe(st) == [P70 if i in hell else P40 for i in range(N)]


@pytest.mark.parametrize("haken", [True, False])
def test_dimmer_besitz_nur_auf_hellen_lampen(monkeypatch, haken):
    """Programmer-/Snap-Dimmer 50 %: mit Haken gehören die dunklen Lampen dem
    Programmer, die hellen dem Läufer (genau 70 %). Ohne Haken (Gegenprobe)
    besitzt der Effekt alle Dimmer — die dunklen bleiben 0."""
    lauf = _spion(_laeufer(durchlassen=haken))
    st = _zustand(monkeypatch, _fm(lauf))
    st.programmer = {fid: {"intensity": 128} for fid in range(1, N + 1)}
    st._render_frame(DT)
    hell = _hell(lauf)
    rest = 128 if haken else 0
    assert _ausgabe(st) == [P70 if i in hell else rest for i in range(N)]


@pytest.mark.parametrize("haken", [True, False])
def test_grundhelligkeit_auf_dunklen_lampen(monkeypatch, haken):
    """Farbe aus dem Programmer, Dimmer von niemandem getrieben -> automatische
    Grundhelligkeit. Mit Haken greift sie auf den dunklen Lampen (der Läufer
    besitzt sie nicht); ohne Haken bleiben sie dunkel wie bisher."""
    kanaele = {fid: [_Ch("intensity", 1), _Ch("color_r", 2),
                     _Ch("color_g", 3), _Ch("color_b", 4)]
               for fid in range(1, N + 1)}
    adressen = {fid: (fid - 1) * 4 + 1 for fid in range(1, N + 1)}
    lauf = _spion(_laeufer(durchlassen=haken))
    st = _zustand(monkeypatch, _fm(lauf), kanaele, adressen)
    st.programmer = {fid: {"color_r": 255, "color_g": 0, "color_b": 0}
                     for fid in range(1, N + 1)}
    st._render_frame(DT)
    hell = _hell(lauf)
    bild = _ausgabe(st, 4 * N)
    dimmer = [bild[i * 4] for i in range(N)]
    rest = 255 if haken else 0
    assert dimmer == [P70 if i in hell else rest for i in range(N)], dimmer
    assert [bild[i * 4 + 1] for i in range(N)] == [255] * N


def test_snap_dimmer_uebersteuerung(monkeypatch):
    """Snap-Dimmer 200 mit Übersteuerung: auf den hellen Lampen übersteuert er
    den Läufer wie bei jedem Effekt, auf den dunklen gilt er ohnehin."""
    lauf = _spion(_laeufer())
    st = _zustand(monkeypatch, _fm(_pegel(), lauf))
    st.programmer = {fid: {"intensity": 200} for fid in range(1, N + 1)}
    st.snap_dimmer_override = {fid: {"intensity": 200} for fid in range(1, N + 1)}
    st._render_frame(DT)
    assert _ausgabe(st) == [200] * N
    # Ohne Übersteuerung multipliziert der Programmer nur dort, wo kein
    # Effekt den Dimmer besitzt — die hellen Lampen bleiben genau 70 %.
    st.snap_dimmer_override = {}
    st.programmer = {}
    st._render_frame(DT)
    hell = _hell(lauf)
    assert _ausgabe(st) == [P70 if i in hell else P40 for i in range(N)]


# ── Show-Format ──────────────────────────────────────────────────────────────


def test_to_dict_nur_bei_gesetztem_haken():
    m = _matrix("m")
    assert "dunkle_durchlassen" not in m.to_dict()
    m.dunkle_durchlassen = True
    assert m.to_dict()["dunkle_durchlassen"] is True
    m.dunkle_durchlassen = False
    assert "dunkle_durchlassen" not in m.to_dict()


def _alt_show() -> dict:
    fm = FunctionManager()
    for stil in MatrixStyle:
        m = fm.new_rgb_matrix(f"Matrix {stil.value}")
        m.style = stil
        m.fixture_grid = [1, 2, None, 4]
        m.cols, m.rows = 4, 1
        m.params.update({"runner_count": 2})
    fm.new_scene("Szene")
    fm.new_chaser("Chaser")
    d = json.loads(json.dumps(fm.to_dict()))
    for fd in d["functions"]:
        assert "dunkle_durchlassen" not in fd
    return d


def test_alte_show_byte_gleich():
    vorher = json.dumps(_alt_show(), ensure_ascii=False, indent=1)
    fm = FunctionManager()
    fm.from_dict(json.loads(vorher))
    for f in fm.all():
        if isinstance(f, RgbMatrixInstance):
            assert f.dunkle_durchlassen is False
    nachher = json.dumps(fm.to_dict(), ensure_ascii=False, indent=1)
    assert nachher.encode("utf-8") == vorher.encode("utf-8")


def test_show_mit_haken_roundtrip():
    fm = FunctionManager()
    m = fm.new_rgb_matrix("Läufer")
    m.style = MatrixStyle.DIMMER
    m.dunkle_durchlassen = True
    text = json.dumps(fm.to_dict())
    fm2 = FunctionManager()
    fm2.from_dict(json.loads(text))
    m2 = fm2.all()[0]
    assert m2.dunkle_durchlassen is True and m2._dunkle_durchlassen() is True
    assert json.dumps(fm2.to_dict()) == text


def test_entwurf_und_preset():
    m = _laeufer()
    entwurf = RgbMatrixInstance.from_dict(m.to_dict())
    assert entwurf.dunkle_durchlassen is True
    entwurf.dunkle_durchlassen = False
    m.apply_dict(entwurf.to_dict())      # Haken im Editor entfernt + gespeichert
    assert m.dunkle_durchlassen is False


# ── Leistung im 44-Hz-Takt ───────────────────────────────────────────────────


def _messen(monkeypatch, haken, frames=300):
    """Zeit je write() einer 48-Lampen-Dimmer-Matrix (Mittel aus 3 Läufen,
    bester Lauf)."""
    n = 48
    kanaele = [_Ch("intensity", 1)]
    monkeypatch.setattr(A, "get_channels_for_patched", lambda fx: kanaele)
    rig = [_Fx(fid, fid) for fid in range(1, n + 1)]
    m = RgbMatrixInstance("mess", cols=n, rows=1,
                          fixture_grid=list(range(1, n + 1)),
                          algorithm=RgbAlgorithm.CHASE)
    m.style = MatrixStyle.DIMMER
    m.tempo_bus_id = ""
    m.params.update({"runner_count": 4, "after_fade": 30.0})
    m.dunkle_durchlassen = haken
    m.start()
    u = {1: Universe(1)}
    for _ in range(30):
        m.write(u, rig, 1 / 44, {})
    beste = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        for _ in range(frames):
            m.write(u, rig, 1 / 44, {})
        beste = min(beste, (time.perf_counter() - t0) / frames)
    return beste


def test_leistung_haken_aus_und_an(monkeypatch):
    # Abwechselnd messen und je den besten Lauf nehmen: nacheinander gemessen
    # kippte der Vergleich auf der CI, wenn die Maschine zwischen den beiden
    # Bloecken langsamer wurde (25.10.2026: 874 us gegen 492 us).
    aus = an = float("inf")
    for _ in range(4):
        aus = min(aus, _messen(monkeypatch, False, frames=150))
        an = min(an, _messen(monkeypatch, True, frames=150))
    print(f"\nENG-42 write() 48 Lampen: Haken aus {aus * 1e6:.1f} us, "
          f"an {an * 1e6:.1f} us je Frame (44 Hz-Budget 22727 us)")
    # Mit Haken werden dunkle Lampen übersprungen — nie deutlich teurer.
    assert an < aus * 1.5 + 50e-6
    assert aus < 0.01           # weit unter dem Frame-Budget

"""ENG-43: Bewegung (EFX) als Modify-Effekt — VERSATZ in Grad auf Pan/Tilt.

Regel (src/core/engine/modify.py, AppState._render_frame 4a²b): ein EFX mit
Haken „Modify-Effekt" setzt keine Position, sondern verschiebt die FERTIGE
Pan/Tilt-Position jedes Ziels um seine Figur (groesster Ausschlag =
``modify_versatz_grad``). Geprueft wird:

1. Umrechnung Grad -> DMX je Geraet ueber dessen Schwenk-/Neigebereich,
   16 Bit mit Fine (kein Sprung am Uebertrag), 8 Bit ohne Fine, Kappung an
   den Grenzen (kein Umschlag), ``invert_pan``/``invert_tilt``/``swap``.
2. Gegenprobe: Versatz auf dem DRAHT == Orientierung der verschobenen
   MODELL-Position (``apply_pan_tilt_orientation``) fuer alle Flag-Kombis.
3. Im Renderer: Addieren/Abziehen, Staerke, Effekt-Helligkeit, Dimmer
   unberuehrt, Grand Master/NOT-AUS danach.
4. SICHERHEIT: Laser werden nie verschoben (Sperrzonen sind nur Anzeige und
   sitzen nicht im Render-Pfad); der Laser-NOT-AUS greift weiter.
5. Show-Format: Alt-Shows byte-gleich, Felder nur bei Abweichung.
6. Konsolen-Parameter nur mit Haken.
"""
from __future__ import annotations

import itertools
import json
import os
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
from src.core.app_state import (AppState,                   # noqa: E402
                                apply_pan_tilt_orientation)
from src.core.dmx.universe import Universe                  # noqa: E402
from src.core.engine import stufen                          # noqa: E402
from src.core.engine.efx import (EfxAlgorithm, EfxFixture,  # noqa: E402
                                 EfxInstance, MODIFY_VERSATZ_VORGABE)
from src.core.engine.function_manager import FunctionManager  # noqa: E402
from src.core.engine.modify import (BewegungsPosten,        # noqa: E402
                                    bewegung_eintraege, ist_modify,
                                    posten_anwenden, verschiebe_wert)

DT = 0.02
MOVER, MOVER8, LASER = 1, 2, 3


class _Ch:
    def __init__(self, attribute, channel_number, default=0):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = default
        self.ranges = []
        self.name = attribute


class _Fx:
    fixture_profile_id = None
    mode_name = "m"
    protocol = ""
    fixture_name = ""
    label = ""

    def __init__(self, fid, address, ftype="", pan=540, tilt=270, **flags):
        self.fid = fid
        self.universe = 1
        self.address = address
        self.fixture_type = ftype
        self.pan_range_deg = pan
        self.tilt_range_deg = tilt
        self.channel_count = 5
        for k, v in flags.items():
            setattr(self, k, v)


_MOVER_KANAELE = [_Ch("pan", 1), _Ch("pan_fine", 2), _Ch("tilt", 3),
                  _Ch("tilt_fine", 4), _Ch("intensity", 5)]
_KANAELE = {
    MOVER: _MOVER_KANAELE,
    MOVER8: [_Ch("pan", 1), _Ch("tilt", 2), _Ch("intensity", 3)],
    # ein Laser mit Pan/Tilt-Spiegeln (gibt es) — Typ „laser"
    LASER: [_Ch("intensity", 1), _Ch("pan", 2), _Ch("tilt", 3), _Ch("shutter", 4)],
}
ADR = {MOVER: 1, MOVER8: 20, LASER: 100}


def _patch():
    return [_Fx(MOVER, ADR[MOVER]), _Fx(MOVER8, ADR[MOVER8]),
            _Fx(LASER, ADR[LASER], ftype="laser")]


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: _KANAELE[fx.fid])
    return _patch()


# ── (1) Umrechnung ───────────────────────────────────────────────────────────


def test_16bit_uebertrag_ohne_sprung():
    # 127/250 + 10 Schritte = 128/4 — Grob und Fein GEMEINSAM
    assert verschiebe_wert(127, 250, 10 / 65535) == (128, 4)
    assert verschiebe_wert(128, 4, -10 / 65535) == (127, 250)
    # schrittweise ueber den Uebertrag: streng monoton, nie ein Sprung > 1 Schritt
    alt = (127 << 8) | 200
    for k in range(1, 120):
        g, f = verschiebe_wert(127, 200, k / 65535)
        neu = (g << 8) | f
        assert neu - alt == 1
        alt = neu


def test_kappung_kein_umschlag():
    assert verschiebe_wert(250, 0, 0.5) == (255, 255)
    assert verschiebe_wert(3, 10, -0.5) == (0, 0)
    assert verschiebe_wert(250, None, 0.5) == (255, None)
    assert verschiebe_wert(3, None, -0.5) == (0, None)


def test_grad_nach_dmx_je_geraetebereich():
    fx540 = _Fx(MOVER, 1, pan=540, tilt=270)
    e = bewegung_eintraege(fx540, _MOVER_KANAELE, 54.0, 27.0)
    assert sorted(e) == sorted([(1, 1, 2, 0.1), (1, 3, 4, 0.1)])
    fx360 = _Fx(MOVER, 1, pan=360, tilt=180)
    e = dict(((g, a) for _u, g, _f, a in
              bewegung_eintraege(fx360, _MOVER_KANAELE, 36.0, 18.0)))
    assert e == {1: pytest.approx(0.1), 3: pytest.approx(0.1)}
    # 20 Grad auf 540 Grad Schwenk ab Mitte 128/0
    g, f = verschiebe_wert(128, 0, 20 / 540)
    assert (g << 8 | f) == round(128 * 256 + 20 / 540 * 65535)


def test_ohne_bereich_gilt_vorgabe():
    fx = _Fx(MOVER, 1, pan=0, tilt=None)
    e = {g: a for _u, g, _f, a in bewegung_eintraege(fx, _MOVER_KANAELE, 54, 27)}
    assert e == {1: pytest.approx(0.1), 3: pytest.approx(0.1)}


def test_8bit_geraet_ohne_fine():
    fx = _Fx(MOVER8, 20)
    e = bewegung_eintraege(fx, _KANAELE[MOVER8], 54.0, 0.0)
    assert e == [(1, 20, None, pytest.approx(0.1))]


@pytest.mark.parametrize("swap,inv_pan,inv_tilt",
                         list(itertools.product((False, True), repeat=3)))
def test_gegenprobe_orientierung(swap, inv_pan, inv_tilt):
    """Versatz auf dem DRAHT == Orientierung der verschobenen MODELL-Position.

    Gleiche Bereiche auf beiden Achsen, damit Tausch die Grad-Umrechnung
    nicht aendert; geprueft wird Vorzeichen und Zielkanal."""
    fx = _Fx(MOVER, 1, pan=360, tilt=360, swap_pan_tilt=swap,
             invert_pan=inv_pan, invert_tilt=inv_tilt)
    for (p16, t16, dp, dt_) in ((30000, 20000, 9.0, -4.5),
                                (40000, 50000, -18.0, 36.0)):
        modell = {"pan": p16 >> 8, "pan_fine": p16 & 255,
                  "tilt": t16 >> 8, "tilt_fine": t16 & 255}
        draht = apply_pan_tilt_orientation(fx, modell)
        u = Universe(1)
        for attr, adr in (("pan", 1), ("pan_fine", 2), ("tilt", 3),
                          ("tilt_fine", 4)):
            u.set_channel(adr, draht[attr])
        posten_anwenden([BewegungsPosten(
            bewegung_eintraege(fx, _MOVER_KANAELE, dp, dt_))], {1: u})
        p2 = p16 + round(dp / 360 * 65535)
        t2 = t16 + round(dt_ / 360 * 65535)
        soll = apply_pan_tilt_orientation(
            fx, {"pan": p2 >> 8, "pan_fine": p2 & 255,
                 "tilt": t2 >> 8, "tilt_fine": t2 & 255})
        ist = u.get_all()
        for achse, adr in (("pan", 1), ("tilt", 3)):
            # Rundung auf dem Draht vs. im Modell: hoechstens 1 Fine-Schritt
            soll16 = soll[achse] << 8 | soll[f"{achse}_fine"]
            ist16 = ist[adr - 1] << 8 | ist[adr]
            assert abs(soll16 - ist16) <= 1, (achse, swap, inv_pan, inv_tilt)


def test_swap_nimmt_bereich_des_physischen_kanals():
    fx = _Fx(MOVER, 1, pan=540, tilt=270, swap_pan_tilt=True)
    e = {g: a for _u, g, _f, a in bewegung_eintraege(fx, _MOVER_KANAELE, 27.0, 0)}
    # logischer Pan landet auf dem Tilt-Kanal (3) und rechnet mit 270 Grad
    assert e == {3: pytest.approx(0.1)}


def test_kopf_ziel_nur_dieser_kopf():
    chans = [_Ch("pan", 1), _Ch("tilt", 2), _Ch("pan", 3), _Ch("tilt", 4)]
    fx = _Fx(MOVER, 1)
    alle = {g for _u, g, _f, _a in bewegung_eintraege(fx, chans, 54, 27)}
    assert alle == {1, 2, 3, 4}
    kopf1 = {g for _u, g, _f, _a in bewegung_eintraege(fx, chans, 54, 27, head=1)}
    assert kopf1 == {3, 4}


# ── (4) Sicherheit: Laser nie verschieben ────────────────────────────────────


@pytest.mark.parametrize("fx,chans", [
    (_Fx(LASER, 100, ftype="laser"), _KANAELE[LASER]),
    (_Fx(LASER, 100), [_Ch("pan", 1), _Ch("laser_x", 2)]),
    (_Fx(LASER, 100, fixture_name="Showlaser RGB"), _KANAELE[MOVER8]),
])
def test_laser_bekommt_keinen_versatz(fx, chans):
    assert bewegung_eintraege(fx, chans, 30.0, 30.0) == []


def test_laser_achsen_werden_nie_verschoben(rig):
    """Ein EFX-Ziel mit laser_x/laser_y-Achsen bekommt keinen Posten — auch
    nicht auf einem Geraet, das nicht als Laser erkannt wird."""
    e = _modify_efx([MOVER])
    e.fixtures[0].pan_attr, e.fixtures[0].tilt_attr = "laser_x", "laser_y"
    from src.core.engine.modify import modify_posten
    e._running = True
    assert modify_posten(e, {1: Universe(1)}, rig, DT) is None
    # Gegenstueck: mit pan/tilt-Achsen entsteht ein Posten
    e.fixtures[0].pan_attr, e.fixtures[0].tilt_attr = "pan", "tilt"
    assert modify_posten(e, {1: Universe(1)}, rig, DT) is not None


def test_sperrzonen_sitzen_nicht_im_render_pfad():
    """Beleg fuer die Sicherheitsentscheidung: die Sperrzonen (LAS-32) sind
    reine Anzeige — weder Renderer noch Ausgabe importieren sie. Darum darf
    ein Bewegungs-Versatz Laser gar nicht erst anfassen."""
    import inspect
    quelle = inspect.getsource(AppState._render_frame)
    assert "sperrzon" not in quelle.lower()
    om = (ROOT / "src/core/dmx/output_manager.py").read_text(encoding="utf-8")
    assert "sperrzon" not in om.lower()
    # Reihenfolge: Modify (4a²b) vor Laser-NOT-AUS (4d)
    assert quelle.index("4a²b") < quelle.index("4d. UXT-12")


# ── (3) Renderer ─────────────────────────────────────────────────────────────


def _basis(fids, pan=128.0, tilt=100.0):
    """Normaler EFX ohne Ausschlag: setzt die Position (Pan/Tilt mit Fine)."""
    e = EfxInstance("basis")
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.width = e.height = 0.0
    e.x_offset, e.y_offset = pan, tilt
    e.tempo_bus_id = ""
    e.speed_hz = 0.0
    return e


def _modify_efx(fids, mode="add", staerke=100, grad=20.0):
    """Modify-Kreis, steht bei Phase 0: Ausschlag (+1, 0) -> +grad Pan."""
    e = EfxInstance("versatz")
    e.fixtures = [EfxFixture(fid=f) for f in fids]
    e.width = e.height = 100.0
    e.algorithm = EfxAlgorithm.CIRCLE
    e.tempo_bus_id = ""
    e.speed_hz = 0.0
    e.modify, e.modify_mode, e.modify_strength = True, mode, staerke
    e.modify_versatz_grad = grad
    return e


def _fm(*funktionen):
    fm = FunctionManager()
    for f in funktionen:
        fm.add(f)
    for f in funktionen:
        fm.start(f.id)
    return fm


def _zustand(fm, om=None):
    st = AppState.__new__(AppState)
    if om is not None:
        st.universes = {1: om.add_universe(1)}
        st.output_manager = om
    else:
        st.universes = {1: Universe(1)}
        st.output_manager = types.SimpleNamespace(
            set_gm_address_mask=lambda m: None)
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    st._patch_cache = _patch()
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st.selected_fids = []
    st.programmer_focus = None
    st.base_levels = {}
    st.laser_estop_active = False
    st._laser_estop_addrs = {}
    st._laser_fids = frozenset()
    st._suppress_emits = True
    st._prog_lock = threading.RLock()
    st._rebuild_render_plan()
    return st


def _pan16(st, adr=1):
    roh = st.universes[1].get_all()
    return roh[adr - 1] << 8 | roh[adr]


def test_ist_modify_nur_mit_haken():
    e = EfxInstance("x")
    assert not ist_modify(e) and not stufen.ist_modify(e)
    e.modify = True
    assert ist_modify(e) and stufen.ist_modify(e)


@pytest.mark.parametrize("mode,vz", [("add", 1), ("sub", -1)])
@pytest.mark.parametrize("staerke", [100, 50])
def test_versatz_auf_fertige_position(rig, mode, vz, staerke):
    st = _zustand(_fm(_basis([MOVER]), _modify_efx([MOVER], mode, staerke)))
    st._render_frame(DT)
    unten = 128 << 8
    soll = round(unten + vz * (20.0 * staerke / 100) / 540 * 65535)
    assert abs(_pan16(st) - soll) <= 1
    # Tilt: Ausschlag 0 bei Phase 0 -> unveraendert
    assert st.universes[1].get_channel(3) == 100


def test_ohne_modify_bleibt_position(rig):
    st = _zustand(_fm(_basis([MOVER])))
    st._render_frame(DT)
    assert _pan16(st) == 128 << 8


def test_effekt_helligkeit_skaliert_den_versatz(rig):
    m = _modify_efx([MOVER])
    m.intensity = 0.5
    st = _zustand(_fm(_basis([MOVER]), m))
    st._render_frame(DT)
    assert abs(_pan16(st) - round((128 << 8) + 10 / 540 * 65535)) <= 1


def test_8bit_geraet_im_renderer(rig):
    st = _zustand(_fm(_basis([MOVER8]), _modify_efx([MOVER8], grad=54.0)))
    st._render_frame(DT)
    assert st.universes[1].get_channel(ADR[MOVER8]) == 128 + round(0.1 * 255)


def test_kappung_im_renderer(rig):
    st = _zustand(_fm(_basis([MOVER], pan=250.0), _modify_efx([MOVER], grad=180)))
    st._render_frame(DT)
    assert st.universes[1].get_all()[0:2] == bytes([255, 255])
    st = _zustand(_fm(_basis([MOVER], pan=5.0),
                      _modify_efx([MOVER], mode="sub", grad=180)))
    st._render_frame(DT)
    assert st.universes[1].get_all()[0:2] == bytes([0, 0])


def test_dimmer_bleibt_unberuehrt(rig):
    b = _basis([MOVER])
    b.open_beam = True
    st = _zustand(_fm(b, _modify_efx([MOVER])))
    st._render_frame(DT)
    assert st.universes[1].get_channel(5) == 255
    st = _zustand(_fm(_basis([MOVER]), _modify_efx([MOVER])))
    st._render_frame(DT)
    assert st.universes[1].get_channel(5) == 0


def test_figur_bewegt_sich_und_bleibt_im_versatz(rig):
    m = _modify_efx([MOVER], grad=20.0)
    m.speed_hz = 1.0
    st = _zustand(_fm(_basis([MOVER]), m))
    werte = set()
    for _ in range(60):
        st._render_frame(DT)
        werte.add(_pan16(st))
    grenze = 20 / 540 * 65535 + 2
    assert len(werte) > 10
    assert all(abs(w - (128 << 8)) <= grenze for w in werte)


def test_laser_bleibt_stehen_und_not_aus_greift(rig):
    """Basis-Bewegung auf Mover UND Laser, Modify auf beide: nur der Mover
    verschiebt sich. Mit NOT-AUS ist der Laser ganz dunkel."""
    b = _basis([MOVER, LASER])
    st = _zustand(_fm(b, _modify_efx([MOVER, LASER], grad=90)))
    st._render_frame(DT)
    laser_pan = st.universes[1].get_channel(ADR[LASER] + 1)
    assert laser_pan == 128, "Bewegungs-Modify hat den Laser verschoben"
    assert _pan16(st) != 128 << 8
    st.laser_estop_active = True
    st._laser_estop_addrs = {1: list(range(ADR[LASER], ADR[LASER] + 4))}
    st._render_frame(DT)
    assert st.universes[1].get_all()[ADR[LASER] - 1:ADR[LASER] + 3] == bytes(4)


def test_chaser_schritt_bleibt_gesperrt(rig):
    """Wie ENG-37: ein Modify-Effekt als Chaser-Schritt gibt nichts aus."""
    from src.core.engine.chaser import Chaser
    m = _modify_efx([MOVER])
    m._running = True
    assert Chaser._render_child_target(m, {1: Universe(1)}, rig, None) == {}


# ── (5) Show-Format ──────────────────────────────────────────────────────────


def test_alt_show_byte_gleich():
    e = EfxInstance("alt")
    e.fixtures = [EfxFixture(fid=1)]
    d = e.to_dict()
    assert not any(k.startswith("modify") for k in d)
    e2 = EfxInstance.from_dict(json.loads(json.dumps(d)))
    assert json.dumps(e2.to_dict(), sort_keys=True) == json.dumps(d, sort_keys=True)
    assert e2.modify is False
    assert e2.modify_versatz_grad == MODIFY_VERSATZ_VORGABE


def test_modify_felder_roundtrip():
    e = _modify_efx([1], mode="sub", staerke=40, grad=33.5)
    d = e.to_dict()
    assert d["modify"] is True and d["modify_mode"] == "sub"
    assert d["modify_strength"] == 40 and d["modify_versatz_grad"] == 33.5
    e2 = EfxInstance.from_dict(json.loads(json.dumps(d)))
    assert (e2.modify, e2.modify_mode, e2.modify_strength,
            e2.modify_versatz_grad) == (True, "sub", 40, 33.5)


def test_unlesbare_felder_fallen_auf_vorgabe():
    e = EfxInstance.from_dict({"modify": True, "modify_mode": "dim",
                               "modify_strength": "x",
                               "modify_versatz_grad": 9999})
    assert e.modify_mode == "add" and e.modify_strength == 100
    assert e.modify_versatz_grad == 180.0


# ── (6) Konsole ──────────────────────────────────────────────────────────────


def test_konsolen_parameter_nur_mit_haken():
    e = EfxInstance("k")
    keys = {p.key for p in e.list_params()}
    assert not any(k.startswith("modify") for k in keys)
    e.modify = True
    keys = {p.key for p in e.list_params()}
    assert {"modify_strength", "modify_mode", "modify_versatz_grad"} <= keys
    assert e.set_param("modify_strength", 150) and e.modify_strength == 100
    assert e.set_param("modify_versatz_grad", -5) and e.modify_versatz_grad == 0
    assert not e.set_param("modify_mode", "dim")
    assert e.set_param("modify_mode", "sub") and e.get_param("modify_mode") == "sub"


def test_show_lader_begrenzt_modify_art_auf_bewegung():
    """Gegenpruefung: Der allgemeine Show-Lader (FunctionManager.from_dict)
    darf das von EfxInstance.from_dict bereinigte modify_mode nicht wieder auf
    „dim" setzen — eine Bewegung kennt nur Addieren/Abziehen."""
    e = EfxInstance("lader")
    e.modify = True
    fm = FunctionManager()
    fm._functions[e.id] = e
    d = json.loads(json.dumps(fm.to_dict()))
    eintrag = next(x for x in d["functions"] if x.get("id") == e.id)
    eintrag["modify_mode"] = "dim"
    fm2 = FunctionManager()
    fm2.from_dict(d)
    e2 = fm2._functions[e.id]
    assert e2.modify_mode in ("add", "sub")
    assert e2.get_param("modify_mode") in ("add", "sub")
    # get_param schuetzt auch, falls der Wert anderweitig ungueltig wird.
    e2.modify_mode = "dim"
    assert e2.get_param("modify_mode") == "add"

"""ENG-37: Modify-Effekt NUR ueber einen Fader der Virtuellen Konsole bedienen.

Wunsch: „Wenn der Fader auf 0 ist, ist der Effekt aus. Setze ich den Fader auf
irgendeinen Wert, ist er aktiv — ohne dass ich ihn extra per Taste aktivieren
muss." Dafuer gibt es am Fader den Haken „Effekt An/Aus (EFFECT-Modi): bei 0
wirklich stoppen" (``effect_autostart``).

Geprueft wird mit einer ECHTEN VCSlider-Instanz (offscreen) und dem ECHTEN
Renderer (``AppState._render_frame``) ueber einem Dimmer-Effekt auf 40 %:

1. Modus Effekt-Helligkeit + Haken: 0 = gestoppt und Bild exakt wie ohne den
   Effekt; 50 % / 100 % = laeuft mit halber / voller Staerke; zurueck auf 0.
2. Modus Effekt-Parameter „Modify-Staerke" + Haken: 0 = aus.
3. Ohne Haken: der Fader regelt nur, An/Aus bleibt bei der Taste.
4. Taste und Fader auf demselben Effekt: die Taste zeigt den Laufzustand.
5. Ein-/Ausblendzeit: der Untergrund springt nie; Fader wieder auf waehrend
   des Ausblendens startet neu.
6. Show laden / Bankwechsel (Pickup): ein gespeicherter Faderwert > 0 startet
   nichts — erst die erste Bewegung des Faders.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                               # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402

import src.core.app_state as A                              # noqa: E402
from src.core.engine.function_manager import get_function_manager  # noqa: E402
from src.core.engine.modify import MODIFY_MODES, modify_wert  # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton  # noqa: E402
from src.ui.virtualconsole.vc_slider import SliderMode, VCSlider  # noqa: E402

import test_eng37_modify_fertiges_bild as B                 # noqa: E402

N, P40, DT = B.N, B.P40, B.DT
OHNE = [P40] * N          # das Bild ohne den Modify-Effekt
H50 = 128                 # Faderwert „50 %" (128 von 255)


@pytest.fixture
def buehne(monkeypatch):
    """Untergrund 40 % laeuft, Modify-Lauflicht ist angelegt aber AUS.
    Liefert ``bau(mode, **felder) -> (st, fm, mod)`` auf dem EINEN
    FunctionManager, den auch Fader und Taste benutzen."""
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(A, "get_channels_for_patched",
                        lambda fx: B._KANAELE[fx.fid])
    monkeypatch.setattr(VCSlider, "soft_takeover", False)
    fm = get_function_manager()
    fm.stop_all()
    angelegt, widgets = [], []

    def bau(mode="add", **felder):
        unten = B._pegel()
        mod = B._lauflicht(mode)
        for k, v in felder.items():
            setattr(mod, k, v)
        for f in (unten, mod):
            fm.add(f)
            angelegt.append(f)
        fm.start(unten.id)
        return B._zustand(fm), fm, mod

    bau.widgets = widgets
    yield bau
    fm.stop_all()
    for f in angelegt:
        fm.remove(f.id)
    for w in widgets:
        w.deleteLater()


def _fader(buehne, mod, modus=SliderMode.EFFECT_INTENSITY, autostart=True,
           **felder):
    s = VCSlider("Modify")
    s.mode = modus
    s.function_id = mod.id
    s.effect_autostart = autostart
    for k, v in felder.items():
        setattr(s, k, v)
    buehne.widgets.append(s)
    return s


def _taste(buehne, mod):
    b = VCButton("Modify")
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = mod.id
    buehne.widgets.append(b)
    return b


def _bild(st, frames=1):
    for _ in range(frames):
        st._render_frame(DT)
    return B._dimmer(st)


def _soll(mode, mod, s):
    aktiv = B._aktiv(mod)
    assert len(aktiv) == 2
    return B._soll(mode, P40, aktiv, s)


def test_vergleichsbild_ohne_den_effekt(buehne):
    st, fm, mod = buehne()
    assert _bild(st, 3) == OHNE == [102] * 8


# ── (1) Effekt-Helligkeit + „bei 0 wirklich stoppen" ─────────────────────────


#          Art    50 %  100 %   (Laeufer ueber 40 % = 102)
ECHT = {"add": (230, 255), "sub": (0, 0), "dim": (51, 0)}


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_helligkeits_fader_allein_schaltet_und_regelt(buehne, mode):
    st, fm, mod = buehne(mode)
    s = _fader(buehne, mod)

    s.value = 0
    assert not fm.is_running(mod.id)
    assert _bild(st, 3) == OHNE

    s.value = H50                                   # 50 %
    assert fm.is_running(mod.id)
    bild = _bild(st)
    assert bild == _soll(mode, mod, H50 / 255.0)
    assert sorted(set(bild)) == sorted({P40, ECHT[mode][0]})

    s.value = 255                                   # 100 %
    assert fm.is_running(mod.id)
    bild = _bild(st)
    assert bild == _soll(mode, mod, 1.0)
    assert sorted(set(bild)) == sorted({P40, ECHT[mode][1]})

    s.value = 0                                     # zurueck: wirklich aus
    assert not fm.is_running(mod.id)
    assert fm.running_ids().count(mod.id) == 0
    for _ in range(5):
        assert _bild(st) == OHNE


def test_kleinster_faderwert_startet_schon(buehne):
    st, fm, mod = buehne("add")
    s = _fader(buehne, mod)
    s.value = 1
    assert fm.is_running(mod.id)
    assert _bild(st) == _soll("add", mod, 1 / 255.0)   # 102 + 1 = 103
    assert max(_bild(st)) == 103


def test_zwei_modify_effekte_an_einem_fader(buehne):
    st, fm, mod = buehne("add")
    zwei = B._lauflicht("sub")
    fm.add(zwei)
    try:
        s = _fader(buehne, mod, function_ids=[zwei.id])
        s.value = 200
        assert fm.is_running(mod.id) and fm.is_running(zwei.id)
        s.value = 0
        assert not fm.is_running(mod.id) and not fm.is_running(zwei.id)
        assert _bild(st, 2) == OHNE
    finally:
        fm.stop(zwei.id)
        fm.remove(zwei.id)


# ── (2) Effekt-Parameter „Modify-Staerke" + Haken ────────────────────────────


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_staerke_fader_allein_schaltet_und_regelt(buehne, mode):
    st, fm, mod = buehne(mode)
    s = _fader(buehne, mod, SliderMode.EFFECT_PARAM,
               param_key="modify_strength")

    s.value = 0
    assert not fm.is_running(mod.id)
    assert mod.modify_strength == 0
    assert _bild(st, 3) == OHNE

    s.value = H50
    assert fm.is_running(mod.id)
    assert mod.modify_strength == 50                # ganze Prozent
    assert mod.intensity == 1.0                     # Helligkeit unberuehrt
    assert _bild(st) == _soll(mode, mod, 0.5)

    s.value = 255
    assert mod.modify_strength == 100
    assert _bild(st) == _soll(mode, mod, 1.0)

    s.value = 0
    assert not fm.is_running(mod.id)
    assert _bild(st, 3) == OHNE


# ── (3) Ohne Haken: der Fader regelt nur ─────────────────────────────────────


def test_ohne_haken_startet_und_stoppt_der_fader_nichts(buehne):
    st, fm, mod = buehne("add")
    s = _fader(buehne, mod, autostart=False)
    b = _taste(buehne, mod)

    s.value = 200                                   # regelt nur
    assert not fm.is_running(mod.id)
    assert _bild(st, 2) == OHNE

    b._trigger(True)                                # Taste an
    b._trigger(False)
    assert fm.is_running(mod.id)
    assert _bild(st) == _soll("add", mod, 200 / 255.0)

    s.value = 0                                     # runtergeregelt, laeuft weiter
    assert fm.is_running(mod.id)
    assert b._function_running()
    assert _bild(st, 2) == OHNE

    s.value = H50
    assert _bild(st) == _soll("add", mod, H50 / 255.0)

    b._trigger(True)                                # Taste aus
    b._trigger(False)
    assert not fm.is_running(mod.id)
    assert _bild(st, 2) == OHNE


# ── (4) Taste + Fader auf demselben Effekt ───────────────────────────────────


def test_taste_zeigt_was_der_fader_tut(buehne):
    st, fm, mod = buehne("add")
    s = _fader(buehne, mod)
    b = _taste(buehne, mod)
    assert not b._function_running()

    s.value = 90                                    # Fader startet
    assert b._function_running()                    # Taste leuchtet
    s.value = 0                                     # Fader stoppt
    assert not b._function_running()                # Taste aus

    s.value = 90
    b._trigger(True)                                # Taste stoppt bei offenem Fader
    b._trigger(False)
    assert not fm.is_running(mod.id) and not b._function_running()
    assert _bild(st, 2) == OHNE
    s.value = 91                                    # naechste Bewegung: wieder an
    assert b._function_running()

    s.value = 0
    b._trigger(True)                                # Taste startet bei Fader 0:
    b._trigger(False)                               # laeuft, Staerke 0
    assert b._function_running()
    assert _bild(st, 2) == OHNE
    s.value = 255                                   # Fader holt ihn hoch
    assert _bild(st) == _soll("add", mod, 1.0)


# ── (5) Ein-/Ausblendzeit ────────────────────────────────────────────────────


def _untergrund_steht(bild, mod):
    aktiv = B._aktiv(mod)
    for i in range(N):
        if i not in aktiv:
            assert bild[i] == P40, f"Untergrund springt: Lampe {i + 1} = {bild[i]}"
    return [bild[i] for i in aktiv]


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_einblendzeit_beim_start_ueber_den_fader(buehne, mode):
    st, fm, mod = buehne(mode, env_fade_in=0.5)
    s = _fader(buehne, mod)
    s.value = 255
    ziel = modify_wert(mode, P40, 255, 1.0)
    verlauf = []
    for _ in range(40):                             # 0,8 s
        laeufer = _untergrund_steht(_bild(st), mod)
        assert len(set(laeufer)) == 1
        verlauf.append(laeufer[0])
    assert verlauf[0] != ziel                       # beginnt nicht mit vollem Schlag
    assert abs(verlauf[0] - P40) <= 12              # sondern nahe am Untergrund
    assert verlauf[-1] == ziel
    richtung = sorted(verlauf, reverse=(ziel < P40))
    assert verlauf == richtung                      # ohne Ruecksprung


def test_ausblendzeit_fader_auf_null_ist_sofort_dunkel_dann_gestoppt(buehne):
    """Effekt-Helligkeit 0 heisst Staerke 0: der Modify-Effekt ist sofort weg,
    blendet (unsichtbar) aus und ist danach wirklich gestoppt."""
    st, fm, mod = buehne("add", env_fade_out=0.3)
    s = _fader(buehne, mod)
    b = _taste(buehne, mod)
    s.value = 255
    _bild(st, 3)
    s.value = 0
    assert _bild(st) == OHNE                        # kein Nachleuchten
    assert b._function_running()                    # blendet noch aus
    for _ in range(25):                             # 0,5 s > 0,3 s
        assert _bild(st) == OHNE
    assert not fm.is_running(mod.id)
    assert not b._function_running()


def test_ausblendzeit_ist_ueber_den_tempo_fader_sichtbar_und_sprungfrei(buehne):
    """Am Tempo-Fader bleibt die Helligkeit stehen — hier sieht man die
    Ausblendzeit: der Laeufer faellt auf den Untergrund, der steht exakt."""
    st, fm, mod = buehne("add", env_fade_out=0.4)
    s = _fader(buehne, mod, SliderMode.EFFECT_SPEED)
    s.value = 120
    assert fm.is_running(mod.id)
    assert max(_bild(st, 3)) == 255
    s.value = 0
    verlauf = []
    for _ in range(30):
        bild = _bild(st)
        if not fm.is_running(mod.id):
            assert bild == OHNE
            break
        verlauf.append(max(_untergrund_steht(bild, mod)))
    assert not fm.is_running(mod.id)
    assert len(verlauf) >= 15
    assert verlauf == sorted(verlauf, reverse=True) and verlauf[-1] < verlauf[0]
    assert _bild(st, 2) == OHNE


def test_fader_wieder_auf_waehrend_des_ausblendens_startet_neu(buehne):
    """Vorher blendete der Effekt zu Ende aus und blieb aus, obwohl der Fader
    wieder oben stand."""
    st, fm, mod = buehne("add", env_fade_out=0.3)
    s = _fader(buehne, mod)
    s.value = 255
    _bild(st, 3)
    s.value = 0
    _bild(st, 5)                                    # mitten im Ausblenden
    assert fm.is_running(mod.id) and mod._releasing
    s.value = 255
    assert not mod._releasing
    for _ in range(40):                             # weit ueber die 0,3 s hinaus
        bild = _bild(st)
    assert fm.is_running(mod.id)
    assert bild == _soll("add", mod, 1.0)


def test_normaler_effekt_startet_waehrend_des_ausblendens_ebenfalls_neu(buehne):
    st, fm, mod = buehne("add", env_fade_out=0.3)
    mod.modify = False                              # ganz normaler Dimmer-Effekt
    s = _fader(buehne, mod)
    s.value = 255
    _bild(st, 3)
    s.value = 0
    _bild(st, 5)
    assert fm.is_running(mod.id) and mod._releasing
    s.value = 255
    _bild(st, 40)
    assert fm.is_running(mod.id)


# ── (6) Show laden / Bankwechsel ─────────────────────────────────────────────


def _geladen(buehne, quelle):
    neu = VCSlider("geladen")
    buehne.widgets.append(neu)
    neu.apply_dict(quelle.to_dict())
    return neu


@pytest.mark.parametrize("normal", [False, True])
def test_show_laden_mit_gespeichertem_faderwert_startet_nichts(buehne, normal):
    """Bestand fuer normale Effekte = Verhalten fuer Modify: der gespeicherte
    Faderwert wird beim Laden nur ANGEZEIGT, nicht angewandt."""
    st, fm, mod = buehne("add")
    if normal:
        mod.modify = False
    alt = _fader(buehne, mod)
    alt.value = 200
    fm.stop(mod.id)                                 # frisch geladene Show: alles aus
    mod.intensity = 1.0
    neu = _geladen(buehne, alt)
    assert neu.value == 200 and neu.effect_autostart is True
    assert neu.mode == SliderMode.EFFECT_INTENSITY and neu.function_id == mod.id
    assert not fm.is_running(mod.id)                # laeuft NICHT von selbst
    assert mod.intensity == 1.0                     # und wurde nicht verstellt
    if not normal:
        assert _bild(st, 3) == OHNE
    neu.value = 201                                 # erste Bewegung: an
    assert fm.is_running(mod.id)
    assert mod.intensity == pytest.approx(201 / 255.0)


def _cc(val, data1=10, ch=1):
    return types.SimpleNamespace(msg_type="cc", channel=ch, data1=data1,
                                 data2=val)


def test_bankwechsel_mit_pickup_startet_erst_beim_abholen(buehne, monkeypatch):
    st, fm, mod = buehne("add")
    alt = _fader(buehne, mod, midi_cc=10, midi_ch=1)
    alt.value = 200
    fm.stop(mod.id)
    s = _geladen(buehne, alt)
    monkeypatch.setattr(VCSlider, "soft_takeover", True)
    s.arm_pickup()                                  # Bank-/Seitenwechsel
    assert not fm.is_running(mod.id)
    s.handle_midi(_cc(0))                           # Hardware steht unten
    s.handle_midi(_cc(40))                          # noch weit weg vom Wert
    assert s.value == 200 and not fm.is_running(mod.id)
    assert _bild(st, 2) == OHNE
    s.handle_midi(_cc(101))                         # kreuzt 200 -> abgeholt
    assert not s._pickup_armed
    assert fm.is_running(mod.id)
    assert _bild(st) == _soll("add", mod, s.value / 255.0)
    s.handle_midi(_cc(0))                           # ab jetzt normal: 0 = aus
    assert not fm.is_running(mod.id)
    assert _bild(st, 2) == OHNE


def test_ohne_pickup_wirkt_die_erste_midi_bewegung_sofort(buehne):
    st, fm, mod = buehne("add")
    s = _fader(buehne, mod, midi_cc=10, midi_ch=1)
    s.handle_midi(_cc(64))
    assert fm.is_running(mod.id)
    s.handle_midi(_cc(0))
    assert not fm.is_running(mod.id)

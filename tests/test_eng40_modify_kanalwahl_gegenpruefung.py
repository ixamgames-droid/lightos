"""ENG-40, Gegenpruefung: Kanalwahl eines Farb-Modify an den Raendern.

Ergaenzt ``test_eng40_modify_kanalwahl.py`` um die Faelle, die dort fehlten:

* Grenzen 0/255 und Staerke 0 %/100 % je Betriebsart und je Kanal,
* mehrere Modify-Effekte uebereinander (verschiedene Kanalwahl, Reihenfolge),
* Feinkanaele (16 Bit) und fremde Farbkanaele (CMY, Farbrad, Shutter),
* Geraet ohne Dimmer, Geraet nur mit Weiss (Tunable White),
* gemischte Schreibweisen und unbekannte Namen im gespeicherten Feld,
* die Kanalmenge wird nicht in jedem Frame neu gebaut (ENG-30).

Gemessen werden DMX-Werte nach dem echten ``FunctionManager.tick``.
"""
from __future__ import annotations

import os
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                    # noqa: E402

import src.core.app_state as AS                                  # noqa: E402
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.modify import (                             # noqa: E402
    MODIFY_KANAELE, MODIFY_KANAL_ATTR, MODIFY_MODES, modify_wert,
    normalize_channels)
from src.core.engine.rgb_matrix import (                         # noqa: E402
    MatrixStyle, RgbAlgorithm, RgbMatrixInstance)

FARBSTILE = [MatrixStyle.RGB, MatrixStyle.RGBW]
ALLE = ("intensity", "color_r", "color_g", "color_b", "color_w",
        "color_a", "color_uv")


def _ch(attr, nr):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr)


def _fx(kanaele):
    return N(fid=1, universe=1, address=1, fixture_type="par",
             fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))


def _matrix(wahl, mode="add", staerke=100, farbe=(255, 255, 255),
            stil=MatrixStyle.RGB):
    m = RgbMatrixInstance("ENG40G", cols=1, rows=1, fixture_grid=[1],
                          algorithm=RgbAlgorithm.PLAIN, color1=farbe)
    m.style = stil
    m.tempo_bus_id = ""
    m.modify, m.modify_mode, m.modify_strength = True, mode, staerke
    m.modify_channels = tuple(wahl)
    return m


def _lauf(monkeypatch, attrs, matrizen, darunter):
    """Ein Frame aller ``matrizen`` ueber dem Bild ``darunter`` (ein Wert fuer
    alle Kanaele oder ein Dict je Attribut) -> ``{attribut: wert}``."""
    kanaele = [_ch(a, i + 1) for i, a in enumerate(attrs)]
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    fm = FunctionManager()
    for m in matrizen:
        fm.add(m)
        fm.start(m.id)
    uni = Universe(1)
    for c in kanaele:
        uni.set_channel(c.channel_number, darunter[c.attribute]
                        if isinstance(darunter, dict) else darunter)
    fm.tick({1: uni}, [_fx(kanaele)], 0.02)
    roh = uni.get_all()
    return {c.attribute: roh[c.channel_number - 1] for c in kanaele}


# ── Grenzen und Staerke ──────────────────────────────────────────────────────

@pytest.mark.parametrize("stil", FARBSTILE)
@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("kanal", MODIFY_KANAELE)
@pytest.mark.parametrize("unten", [0, 1, 128, 254, 255])
@pytest.mark.parametrize("staerke", [0, 1, 50, 100])
def test_grenzen_und_staerke_je_kanal(monkeypatch, stil, mode, kanal, unten,
                                      staerke):
    """Der gewaehlte Kanal folgt genau der Modify-Formel und bleibt in 0..255;
    alle anderen Kanaele — der Dimmer zuerst — bleiben auf dem Wert darunter."""
    bild = _lauf(monkeypatch, ALLE, [_matrix([kanal], mode, staerke, stil=stil)],
                 unten)
    ziel = MODIFY_KANAL_ATTR[kanal]
    for attr, wert in bild.items():
        if attr == ziel:
            assert wert == modify_wert(mode, unten, 255, staerke / 100.0)
            assert 0 <= wert <= 255
        else:
            assert wert == unten, (attr, wert)
    if staerke == 0:
        assert bild[ziel] == unten


@pytest.mark.parametrize("mode", ["sub", "dim"])
def test_abziehen_und_abdunkeln_hellen_nie_auf(monkeypatch, mode):
    for unten in (0, 7, 200, 255):
        bild = _lauf(monkeypatch, ALLE,
                     [_matrix(list(MODIFY_KANAELE), mode, 100)], unten)
        assert all(w <= unten for w in bild.values()), (unten, bild)
        assert bild["intensity"] == unten


# ── Mehrere Modify-Effekte uebereinander ─────────────────────────────────────

def test_zwei_modify_effekte_mit_verschiedener_kanalwahl(monkeypatch):
    """„Nur Weiss abziehen" und „nur Rot addieren" gleichzeitig: jeder trifft
    seinen Kanal, keiner den des anderen, der Dimmer bleibt."""
    unten = {"intensity": 77, "color_r": 30, "color_g": 60, "color_b": 250,
             "color_w": 180, "color_a": 90, "color_uv": 120}
    bild = _lauf(monkeypatch, ALLE,
                 [_matrix(["w"], "sub", 50, stil=MatrixStyle.RGBW),
                  _matrix(["r"], "add", 100)], unten)
    erwartet = dict(unten)
    erwartet["color_w"] = modify_wert("sub", 180, 255, 0.5)
    erwartet["color_r"] = 255
    assert bild == erwartet


def test_zwei_modify_effekte_auf_demselben_kanal_wirken_nacheinander(
        monkeypatch):
    """Addieren und Abdunkeln auf demselben Kanal: der zweite rechnet auf dem
    Ergebnis des ersten (Reihenfolge = Reihenfolge im FunctionManager)."""
    a = _matrix(["g"], "add", 40)
    b = _matrix(["g"], "dim", 50)
    bild = _lauf(monkeypatch, ALLE, [a, b], 100)
    nach_a = modify_wert("add", 100, 255, 0.4)
    assert bild["color_g"] == modify_wert("dim", nach_a, 255, 0.5)
    assert {k: v for k, v in bild.items() if k != "color_g"} == {
        k: 100 for k in ALLE if k != "color_g"}


def test_kanalwahl_und_vorgabe_uebereinander(monkeypatch):
    """Ein Modify ohne Auswahl (rote Farbe, ENG-38) und einer mit „nur Blau"."""
    bild = _lauf(monkeypatch, ALLE,
                 [_matrix((), "add", 100, farbe=(100, 0, 0)),
                  _matrix(["b"], "sub", 100)], 50)
    assert bild == {"intensity": 50, "color_r": 150, "color_g": 50,
                    "color_b": 0, "color_w": 50, "color_a": 50,
                    "color_uv": 50}


# ── Geraete-Sonderfaelle ─────────────────────────────────────────────────────

@pytest.mark.parametrize("stil", FARBSTILE)
@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_feinkanal_und_fremde_kanaele_bleiben_stehen(monkeypatch, stil, mode):
    """16-Bit-Geraet mit CMY, Farbrad und Shutter: nur der Grobkanal der
    Auswahl wird verrechnet. Feinkanaele, Dimmer, Dimmer-Fein, CMY, Farbrad
    und Shutter bleiben."""
    attrs = ("intensity", "intensity_fine", "color_r", "color_r_fine",
             "color_g", "color_g_fine", "color_b", "color_b_fine",
             "color_w", "color_w_fine", "cmy_c", "cmy_m", "cmy_y",
             "color_wheel", "shutter", "dimmer", "master")
    bild = _lauf(monkeypatch, attrs,
                 [_matrix(["r", "w"], mode, 100, stil=stil)], 100)
    neu = modify_wert(mode, 100, 255, 1.0)
    for attr, wert in bild.items():
        assert wert == (neu if attr in ("color_r", "color_w") else 100), attr


@pytest.mark.parametrize("stil", FARBSTILE)
def test_geraet_nur_mit_weiss_ohne_dimmer(monkeypatch, stil):
    """Tunable White (zwei Weiss-Kanaele, keine Farbe, kein Dimmer): „nur
    Weiss" verrechnet beide, „nur Rot" laesst das Geraet stehen."""
    attrs = ("color_w", "color_w")
    kanaele = [_ch(a, i + 1) for i, a in enumerate(attrs)]
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    for wahl, erwartet in ((["w"], [160, 160]), (["r"], [60, 60])):
        fm = FunctionManager()
        m = _matrix(wahl, "add", 100, farbe=(100, 0, 0), stil=stil)
        fm.add(m)
        fm.start(m.id)
        uni = Universe(1)
        uni.set_channel(1, 60)
        uni.set_channel(2, 60)
        fm.tick({1: uni}, [_fx(kanaele)], 0.02)
        assert list(uni.get_all()[:2]) == erwartet, wahl


def test_rgb_geraet_ohne_dimmer_nur_gewaehlter_kanal(monkeypatch):
    attrs = ("color_r", "color_g", "color_b")
    bild = _lauf(monkeypatch, attrs, [_matrix(["g"], "sub", 100)], 200)
    assert bild == {"color_r": 200, "color_g": 0, "color_b": 200}


# ── Gespeichertes Feld ───────────────────────────────────────────────────────

@pytest.mark.parametrize("roh,erwartet", [
    (["W", " r "], ("r", "w")),
    (["w", "lime"], ("w",)),            # unbekannter Name faellt weg
    (["lime", "color_w", 7, None], ()),
    ({"w": True}, ("w",)),
    (5, ()), (True, ()), ("w;UV", ("w", "uv")),
    (["w", "w", "w"], ("w",)),
    ([["w"]], ()),
])
def test_normalize_channels_raender(roh, erwartet):
    assert normalize_channels(roh) == erwartet


def test_unbekannte_namen_veraendern_das_bild_nicht_anders_als_die_vorgabe(
        monkeypatch):
    """Nur unbekannte Namen im Feld = Vorgabe (ENG-38), byte-gleich."""
    unten = {a: 40 for a in ALLE}
    for stil in FARBSTILE:
        for mode in MODIFY_MODES:
            a = _lauf(monkeypatch, ALLE,
                      [_matrix((), mode, 70, (200, 90, 10), stil)], unten)
            b = _lauf(monkeypatch, ALLE,
                      [_matrix(("lime", "x"), mode, 70, (200, 90, 10), stil)],
                      unten)
            assert a == b


# ── Render-Weg (ENG-30) ──────────────────────────────────────────────────────

def test_kanalmenge_wird_nicht_je_frame_neu_gebaut():
    """Die Menge der Kanal-Attribute haengt nur an der Auswahl. Solange die
    sich nicht aendert, liefert der Render-Weg dasselbe Objekt; nach einer
    Aenderung (auch am selben Objekt vorbei) sofort die neue Menge."""
    m = _matrix(["w", "r"])
    erste = m._modify_kanalwahl()
    assert erste == frozenset({"color_r", "color_w"})
    assert m._modify_kanalwahl() is erste
    m.modify_channels = ("b",)
    assert m._modify_kanalwahl() == frozenset({"color_b"})
    m.modify_channels = ["g"]                 # Liste statt Tupel (Alt-Aufrufer)
    assert m._modify_kanalwahl() == frozenset({"color_g"})
    m.modify_channels = ()
    assert m._modify_kanalwahl() == frozenset()
    m.modify_channels = ("uv",)
    m.style = MatrixStyle.DIMMER              # im Stil Dimmer wirkt sie nicht
    assert m._modify_kanalwahl() == frozenset()
    m.style = MatrixStyle.RGB
    assert m._modify_kanalwahl() == frozenset({"color_uv"})
    m.modify = False
    assert m._modify_kanalwahl() == frozenset()

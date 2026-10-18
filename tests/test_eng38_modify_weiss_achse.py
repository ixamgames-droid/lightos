"""ENG-38: Farb-Modify auf der WEISS-ACHSE und auf Kopf-Zellen.

Luecke aus der Gegenpruefung: ``RgbMatrixInstance._weiss_achse_schreiben`` und
der Kopf-Pfad (``head_grid``) waren fuer den Modify-Betrieb angepasst, aber von
keinem Test gehalten — beide Stellen liessen sich zuruecknehmen, ohne dass ein
Test rot wurde.

Regel (dieselbe wie in ``write``): ein Farb-Modify schreibt nur Farbkanaele.

* Eigene Weiss-Segmente (``weiss_grid``) verrechnen ``color_w`` — der Dimmer
  wird nie geschrieben, auch nicht bei „Dimmer mitziehen" und auch nicht ueber
  den Rueckfall bei mehreren Dimmer-Kanaelen (FM-46).
* Die Effekt-Helligkeit steckt in der STAERKE; das Weiss wird nicht zusaetzlich
  in der Matrix skaliert (sonst wirkte sie quadratisch).
* Eine Kopf-Zelle verrechnet nur die Farbkanaele IHRES Kopfes; der geteilte
  Master bleibt stehen.

Gemessen wird das Endergebnis nach dem echten ``FunctionManager.tick``.
"""
from __future__ import annotations

import os
from types import SimpleNamespace as N

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                    # noqa: E402

import src.core.app_state as AS                                  # noqa: E402
from src.core.dmx.universe import Universe                       # noqa: E402
from src.core.engine.function_manager import FunctionManager    # noqa: E402
from src.core.engine.modify import MODIFY_MODES, modify_wert     # noqa: E402
from src.core.engine.rgb_matrix import MatrixStyle, RgbMatrixInstance  # noqa: E402

DIMMER_DARUNTER = 77
FARBE_DARUNTER = 100


def _ch(attr, nr):
    return N(attribute=attr, channel_number=nr, default_value=0,
             highlight_value=255, ranges=[], name=attr)


def _geraet(n_dimmer):
    """``n_dimmer`` Dimmer, vier RGB-Koepfe, zwei eigene Weiss-Segmente."""
    kanaele = [_ch("intensity", i + 1) for i in range(n_dimmer)]
    nr = n_dimmer + 1
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            kanaele.append(_ch(a, nr))
            nr += 1
    kanaele += [_ch("color_w", nr), _ch("color_w", nr + 1)]
    return kanaele


def _lauf(monkeypatch, kanaele, matrix):
    """Ein Vollweiss-Frame des Modify-Effekts ueber einem vorbelegten Bild
    (Dimmer 77, alle Farbkanaele 100) -> Rohwerte je Attribut."""
    monkeypatch.setattr(AS, "get_channels_for_patched", lambda fx: kanaele)
    fx = N(fid=1, universe=1, address=1, fixture_type="led_bar",
           fixture_profile_id=1, mode_name="m", channel_count=len(kanaele))
    matrix._render = lambda phase: [(255, 255, 255)] * 2
    fm = FunctionManager()
    fm.add(matrix)
    fm.start(matrix.id)
    uni = Universe(1)
    for c in kanaele:
        uni.set_channel(c.channel_number, DIMMER_DARUNTER
                        if c.attribute == "intensity" else FARBE_DARUNTER)
    fm.tick({1: uni}, [fx], 0.02)
    roh = uni.get_all()

    def werte(attr):
        return [roh[c.channel_number - 1] for c in kanaele if c.attribute == attr]
    return werte


def _matrix(stil, mode, *, drive, inten, farbzellen):
    mx = RgbMatrixInstance(name="ENG38-W")
    mx.style = stil
    mx.cols, mx.rows = 2, 1
    mx.fixture_grid = [1, None] if farbzellen else [None, None]
    mx.head_grid = [None, None]
    mx.weiss_grid = [None, (1, 0)] if farbzellen else [(1, 0), (1, 1)]
    mx.drive_intensity = drive
    mx.intensity = inten
    mx.modify, mx.modify_mode, mx.modify_strength = True, mode, 100
    return mx


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("stil", [MatrixStyle.RGB, MatrixStyle.RGBW])
@pytest.mark.parametrize("drive", [False, True])
@pytest.mark.parametrize("n_dimmer", [1, 2])
def test_weiss_segmente_verrechnen_ohne_den_dimmer(monkeypatch, mode, stil,
                                                   drive, n_dimmer):
    """Nur Weiss-Zellen: ``color_w`` wird verrechnet, Dimmer und RGB bleiben."""
    werte = _lauf(monkeypatch, _geraet(n_dimmer),
                  _matrix(stil, mode, drive=drive, inten=0.5, farbzellen=False))
    assert werte("intensity") == [DIMMER_DARUNTER] * n_dimmer
    # Effekt-Helligkeit 0,5 = Staerke 0,5 — genau einmal, nicht quadratisch.
    assert werte("color_w") == [modify_wert(mode, FARBE_DARUNTER, 255, 0.5)] * 2
    for attr in ("color_r", "color_g", "color_b"):
        assert werte(attr) == [FARBE_DARUNTER] * 4


@pytest.mark.parametrize("mode", MODIFY_MODES)
@pytest.mark.parametrize("drive", [False, True])
def test_farb_und_weiss_zelle_gemischt(monkeypatch, mode, drive):
    """Farbzelle (ganzes Geraet) + eine Weiss-Zelle: beide verrechnen ihre
    Kanaele, das nicht belegte Weiss-Segment und die Dimmer bleiben stehen."""
    werte = _lauf(monkeypatch, _geraet(2),
                  _matrix(MatrixStyle.RGB, mode, drive=drive, inten=1.0,
                          farbzellen=True))
    neu = modify_wert(mode, FARBE_DARUNTER, 255, 1.0)
    assert werte("intensity") == [DIMMER_DARUNTER] * 2
    for attr in ("color_r", "color_g", "color_b"):
        assert werte(attr) == [neu] * 4
    assert werte("color_w") == [neu, FARBE_DARUNTER]


@pytest.mark.parametrize("mode", MODIFY_MODES)
def test_kopf_zelle_verrechnet_nur_ihren_kopf(monkeypatch, mode):
    """``head_grid``: die Zelle trifft die Farbkanaele von Kopf 2 — die anderen
    Koepfe und der geteilte Master (auch bei „Dimmer mitziehen") bleiben."""
    kanaele = [_ch("intensity", 1)]
    nr = 2
    for _ in range(4):
        for a in ("color_r", "color_g", "color_b"):
            kanaele.append(_ch(a, nr))
            nr += 1
    mx = RgbMatrixInstance(name="ENG38-K")
    mx.style = MatrixStyle.RGB
    mx.cols, mx.rows = 2, 1
    mx.fixture_grid = [1, None]
    mx.head_grid = [2, None]
    mx.drive_intensity = True
    mx.modify, mx.modify_mode, mx.modify_strength = True, mode, 100
    werte = _lauf(monkeypatch, kanaele, mx)
    neu = modify_wert(mode, FARBE_DARUNTER, 255, 1.0)
    assert werte("intensity") == [DIMMER_DARUNTER]
    for attr in ("color_r", "color_g", "color_b"):
        assert werte(attr) == [FARBE_DARUNTER] * 2 + [neu, FARBE_DARUNTER]

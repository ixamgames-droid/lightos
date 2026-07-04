"""FM-2: generalisierter Multi-Head-Payload in visualizer_service._build_fixture_payload.
Prueft (a) Spider-Regression (2 Koepfe, byte-identisch), (b) N-Kopf-Bar mit pro-Kopf
Pan/Tilt/Farbe (4 Koepfe), (c) Einzel-Fixture ohne heads-Array, (d) pro-Kopf-Pan-Fallback."""
from types import SimpleNamespace

from src.ui.visualizer.visualizer_service import _build_fixture_payload, _multihead_count


def _fx(fid=7):
    return SimpleNamespace(fid=fid)


def test_single_head_no_heads_array():
    attrs = {"color_r": 255, "color_g": 0, "color_b": 0, "intensity": 200, "pan": 128, "tilt": 128}
    p = _build_fixture_payload(_fx(), attrs)
    assert "heads" not in p
    assert p["r"] == 255 and p["intensity"] == 200 and p["pan"] == 128


def test_spider_regression_two_heads():
    # Spider: zwei RGBW-Banks + zwei Tilts (tilt + tilt#1). head_count MUSS 2 sein.
    attrs = {
        "intensity": 255, "pan": 100, "tilt": 40,
        "color_r": 255, "color_g": 0, "color_b": 0, "color_w": 0,
        "color_r#1": 0, "color_g#1": 0, "color_b#1": 255, "color_w#1": 0,
        "tilt#1": 210,
    }
    assert _multihead_count(attrs) == 2
    p = _build_fixture_payload(_fx(), attrs)
    heads = p["heads"]
    assert len(heads) == 2
    assert heads[0]["cr"] == 255 and heads[0]["cb"] == 0 and heads[0]["tilt"] == 40
    assert heads[1]["cb"] == 255 and heads[1]["cr"] == 0 and heads[1]["tilt"] == 210
    # weisses w wird additiv auf r/g/b gelegt (wie bisher)
    assert heads[0]["r"] == 255 and heads[1]["b"] == 255


def test_spider_pan_as_tilt_fallback():
    # Spider ohne tilt#1, aber mit pan -> pan wird Bar-0-Tilt (Alt-Verhalten bleibt).
    attrs = {"intensity": 255, "pan": 77, "tilt": 190,
             "color_r": 10, "color_r#1": 20}
    p = _build_fixture_payload(_fx(), attrs)
    heads = p["heads"]
    assert len(heads) == 2
    assert heads[0]["tilt"] == 77 and heads[1]["tilt"] == 190  # pan->Bar0, tilt->Bar1


def test_four_head_mover_bar_per_head_pan_tilt():
    # 4er-Mover-Bar: pro Kopf color_r/pan/tilt -> head_count 4, jeweils eigener Pan/Tilt.
    attrs = {"intensity": 255, "pan": 10, "tilt": 20, "color_r": 1,
             "color_r#1": 2, "pan#1": 11, "tilt#1": 21,
             "color_r#2": 3, "pan#2": 12, "tilt#2": 22,
             "color_r#3": 4, "pan#3": 13, "tilt#3": 23}
    assert _multihead_count(attrs) == 4
    p = _build_fixture_payload(_fx(), attrs)
    heads = p["heads"]
    assert len(heads) == 4
    for h in range(4):
        assert heads[h]["cr"] == h + 1
        assert heads[h]["pan"] == 10 + h
        assert heads[h]["tilt"] == 20 + h


def test_four_head_par_bar_color_only():
    # 4er-PAR-Bar: nur pro Kopf color -> 4 Koepfe, pan faellt auf Basis-Pan zurueck.
    attrs = {"intensity": 255, "pan": 128, "tilt": 128, "color_r": 5,
             "color_r#1": 6, "color_r#2": 7, "color_r#3": 8}
    p = _build_fixture_payload(_fx(), attrs)
    heads = p["heads"]
    assert len(heads) == 4
    assert [h["cr"] for h in heads] == [5, 6, 7, 8]
    assert all(h["pan"] == 128 for h in heads)   # Fallback auf Basis-Pan

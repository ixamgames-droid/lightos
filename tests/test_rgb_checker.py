"""F1: CHECKER (Schachbrett/Wechsel) RGB-Matrix-Algorithmus.

Reiner Render-Test (kein Qt, keine Fixtures noetig) — prueft das raeumliche
A/B/A/B-Muster, 'rot-aus', Kachelgroesse und das Pro-Beat-Umschalten (Blinken).
"""
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, ColorSequence

RED, BLUE, OFF = (255, 0, 0), (0, 0, 255), (0, 0, 0)


def _checker(colors, cols, blink=True, tile=1, p=0.0):
    m = RgbMatrixInstance("chk", cols=cols, rows=1)
    m.algorithm = RgbAlgorithm.CHECKER
    m.colors = ColorSequence([tuple(c) for c in colors])
    m.params = {"tile": tile, "blink": blink}
    return m._render(p)


def test_checker_alternates_two_colors():
    assert _checker([RED, BLUE], 6, blink=False, p=0.0) == [RED, BLUE, RED, BLUE, RED, BLUE]


def test_checker_red_off():
    assert _checker([RED, OFF], 6, blink=False, p=0.0) == [RED, OFF, RED, OFF, RED, OFF]


def test_checker_blink_swaps_each_beat():
    p0 = _checker([RED, BLUE], 6, blink=True, p=0.0)
    p1 = _checker([RED, BLUE], 6, blink=True, p=1.0)
    assert p0[0] == RED and p1[0] == BLUE   # nach einem Beat getauscht
    assert p0 != p1


def test_checker_tile_groups_two():
    # tile=2: col//2 -> 0,0,1,1,2,2,3,3 -> rot,rot,blau,blau,rot,rot,blau,blau
    assert _checker([RED, BLUE], 8, blink=False, tile=2, p=0.0) == \
        [RED, RED, BLUE, BLUE, RED, RED, BLUE, BLUE]


def test_checker_no_blink_is_static_over_time():
    assert _checker([RED, BLUE], 6, blink=False, p=0.0) == _checker([RED, BLUE], 6, blink=False, p=5.0)


def test_checker_three_colors_cycle():
    GREEN = (0, 255, 0)
    px = _checker([RED, BLUE, GREEN], 6, blink=False, p=0.0)
    assert px == [RED, BLUE, GREEN, RED, BLUE, GREEN]


def test_checker_in_algo_meta_and_dropdown():
    # CHECKER muss in der Algorithmus-Meta auftauchen (sonst nicht im Editor waehlbar)
    from src.core.engine.rgb_matrix_meta import ALGO_META
    assert RgbAlgorithm.CHECKER in ALGO_META
    meta = ALGO_META[RgbAlgorithm.CHECKER]
    assert meta.colors >= 2 and meta.sequence is True
    keys = {p.key for p in meta.params}
    assert {"tile", "blink"} <= keys

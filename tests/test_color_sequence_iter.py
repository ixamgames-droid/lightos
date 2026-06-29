"""DEMO-05: ColorSequence ist iterierbar und indexierbar.

``list(seq)`` liefert alle Farb-Tupel ``(r,g,b)`` (konsistent mit ``len()``),
``seq[i]`` indexiert mit normaler Listen-Semantik (inkl. negativer Indizes).
"""
from src.core.engine.rgb_matrix import ColorSequence


def test_color_sequence_iterates_all_colors():
    seq = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])

    assert list(seq) == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    assert [c for c in seq] == [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    assert len(list(seq)) == len(seq)


def test_color_sequence_indexing():
    seq = ColorSequence([(255, 0, 0), (0, 255, 0), (0, 0, 255)])

    assert seq[0] == (255, 0, 0)
    assert seq[1] == (0, 255, 0)
    assert seq[-1] == (0, 0, 255)

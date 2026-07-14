"""BPM-05: ``BpmTimeline.from_dict`` erzwingt die Invariante ``downbeats ⊆ beats``.

Ein korrupter/veralteter Cache kann Downbeats enthalten, die in keinem Beat des
Grids vorkommen (beide Listen werden unabhaengig sortiert). ``beat_phase_at``
zaehlt dann falsche Beats seit dem Downbeat → falsches ``beat_in_bar``. ``from_dict``
muss die Downbeats beim Laden auf die Schnittmenge mit den Beats reduzieren.
"""
from src.core.audio.offline_timeline import BpmTimeline


def _beats(n, step=500, start=0):
    return [start + i * step for i in range(n)]


def test_from_dict_reduces_downbeats_to_subset_of_beats():
    beats = _beats(8, step=500)          # 0,500,...,3500
    # Downbeats: zwei echte (0, 2000) + zwei die NICHT im Grid liegen (123, 999).
    d = {
        "v": 2,
        "beats_ms": beats,
        "downbeats_ms": [999, 0, 2000, 123],
        "beats_per_bar": 4,
    }
    tl = BpmTimeline.from_dict(d)
    beat_set = set(tl.beats_ms)
    assert all(x in beat_set for x in tl.downbeats_ms), "downbeats muss Teilmenge von beats sein"
    # Die echten Downbeats bleiben erhalten, die Fremdlinge fliegen raus.
    assert tl.downbeats_ms == [0, 2000]


def test_from_dict_valid_downbeats_unchanged():
    beats = _beats(8, step=500)
    downs = [0, 2000]
    tl = BpmTimeline.from_dict({"beats_ms": beats, "downbeats_ms": downs, "beats_per_bar": 4})
    assert tl.downbeats_ms == [0, 2000]
    assert set(tl.downbeats_ms) <= set(tl.beats_ms)


def test_from_dict_all_downbeats_bogus_are_discarded():
    beats = _beats(4, step=500)          # 0,500,1000,1500
    # Kein einziger Downbeat liegt im Grid → sauber verwerfen.
    tl = BpmTimeline.from_dict({"beats_ms": beats, "downbeats_ms": [7, 42, 9999], "beats_per_bar": 4})
    assert tl.downbeats_ms == []
    # Grid bleibt nutzbar; beat_phase_at faellt auf i//bpb zurueck (konsistent).
    res = tl.beat_phase_at(1000)
    assert res is not None
    bar_index, beat_in_bar, phase01 = res
    assert beat_in_bar == 2 % 4  # Beat-Index 2 (1000ms) → beat_in_bar 2


def test_from_dict_downbeats_without_beats_discarded():
    tl = BpmTimeline.from_dict({"downbeats_ms": [0, 2000], "beats_per_bar": 4})
    assert tl.beats_ms == []
    assert tl.downbeats_ms == []


def test_beat_phase_consistent_after_validation():
    """Nach der Bereinigung liefert beat_phase_at korrektes beat_in_bar."""
    beats = _beats(9, step=500)          # 0..4000, Downbeats bei 0 und 2000 (bpb=4)
    d = {
        "beats_ms": beats,
        # 1234 ist ein Fremd-Downbeat; ohne Bereinigung wuerde er die Bar-Zaehlung stoeren.
        "downbeats_ms": [0, 1234, 2000],
        "beats_per_bar": 4,
    }
    tl = BpmTimeline.from_dict(d)
    assert set(tl.downbeats_ms) <= set(tl.beats_ms)
    # Beat bei 2500ms = Index 5; letzter Downbeat davor = 2000 (Index 4) → beat_in_bar 1.
    bar_index, beat_in_bar, _ = tl.beat_phase_at(2500)
    assert beat_in_bar == 1


def test_roundtrip_to_dict_from_dict_preserves_valid_grid():
    beats = _beats(8, step=500)
    tl0 = BpmTimeline(beats_ms=beats, downbeats_ms=[0, 2000], beats_per_bar=4)
    tl1 = BpmTimeline.from_dict(tl0.to_dict())
    assert tl1.beats_ms == beats
    assert tl1.downbeats_ms == [0, 2000]

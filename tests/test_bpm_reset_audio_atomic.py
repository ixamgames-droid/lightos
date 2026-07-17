"""A3D-17 (Atomarität): set_bpm() schreibt `_bpm` + abgeleitetes `_source` unter
dem Lock, konsistent mit dem reset()-Lock (BPM-04).

Vorher schrieb set_bpm() `_bpm`/`_source` OHNE Lock — ein (oft aus dem Audio-Thread
kommender) set_bpm konnte den unter dem Lock nullenden reset() überholen und einen
inkonsistenten Zustand hinterlassen (`_bpm>0` bei `_source='off'`). Jetzt nehmen
BEIDE Seiten den Lock, sodass die Serialisierung wirklich greift.

(NICHT hier: ob ein manuelles '0'/reset laufende AUTO-Quellen — Audio/OS2L/Timeline/
File/TempoBus — dauerhaft überstimmen soll. Das ist eine offene Verhaltensfrage,
BACKLOG A3D-17b.)
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode


def _fresh():
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.set_locked(False)
    mgr._audio_active = False
    mgr.set_bounds(60, 200)
    return mgr


def test_set_bpm_zero_sets_source_off_atomically():
    # set_bpm(0) leitet _source='off' ab — _bpm UND _source zusammen unter dem Lock.
    mgr = _fresh()
    mgr.set_manual_bpm(130.0)
    assert mgr.bpm == 130.0
    mgr.set_bpm(0)
    assert mgr.bpm == 0.0
    assert mgr.current_source == "off"       # nie _bpm=0 bei _source!='off'
    mgr.reset()


def test_set_bpm_positive_keeps_pair_consistent():
    mgr = _fresh()
    mgr.set_mode(BpmMode.AUTO)
    mgr._audio_active = True
    mgr._apply_detected_bpm(140.0)
    assert mgr.bpm == 140.0
    assert mgr.current_source == "audio"     # positiver Wert -> Quelle bleibt gesetzt
    mgr.reset()


def test_reset_leaves_consistent_off_state():
    mgr = _fresh()
    mgr.set_mode(BpmMode.AUTO)
    mgr._audio_active = True
    mgr._apply_detected_bpm(128.0)
    assert mgr.bpm > 0
    mgr.reset()
    # reset nullt _bpm UND _source zusammen unter dem Lock -> konsistent, nicht torn.
    assert mgr.bpm == 0.0
    assert mgr.current_source == "off"
    mgr.reset()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))

"""CDX-14: `_source` + `_bpm` atomar unter EINEM Lock-Hold in set_bpm().

Frueher setzten die internen Quellen (`_set_manual`, `request_bpm`,
`_apply_detected_bpm`) `_source` in einem SEPARATEN Lock-Fenster und riefen
DANACH `set_bpm(bpm)` (zweites Lock-Fenster) auf. Ein `reset()` dazwischen
(setzt `_source='off'`, `_bpm=0` unter dem Lock) hinterliess einen
inkonsistenten Zustand `_bpm>0` bei `_source='off'`. Seit CDX-14 nimmt
set_bpm() eine optionale `source` und schreibt Quelle + Wert (+ abgeleitetes
'off') unter EINEM Hold — die drei Aufrufer reichen `source` jetzt atomar durch.

Deterministischer Regressionstest ohne Timing-Wettlauf: eine instrumentierte
Lock-Huelle ruft nach der ERSTEN Lock-Freigabe waehrend des getesteten Aufrufs
EINMAL synchron `reset()` — genau der 'Gap', in den der Reset frueher schluepfte.
- Neuer Code: set_bpm schreibt Quelle+Wert unter EINEM Hold, der injizierte
  reset() faellt also GANZ HINTER die atomare Schreiboperation -> Endzustand
  konsistent (0/'off'), Invariante haelt.
- Alter Code (separater `_source`-Write vor set_bpm): der reset() faellt in den
  Gap -> danach setzt set_bpm nur noch `_bpm=120` (source=None) -> `_bpm=120`
  bei `_source='off'` -> die Invariante bricht und der Test schlaegt fehl.
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
    mgr.set_mode(BpmMode.AUTO)
    return mgr


class _ResetInjectingLock:
    """Delegiert an den echten RLock; feuert nach der ersten .release()/__exit__
    waehrend des getesteten Aufrufs EINMAL synchron reset() (der 'Gap' der alten
    Race). reset() nimmt denselben echten Lock ueber diese Huelle — ist er zu dem
    Zeitpunkt wirklich frei, laeuft der Reset voll durch."""

    def __init__(self, mgr, real_lock):
        self._mgr = mgr
        self._real = real_lock
        self.fired = False

    def acquire(self, *a, **k):
        return self._real.acquire(*a, **k)

    def release(self):
        self._real.release()
        if not self.fired:
            self.fired = True
            self._mgr.reset()

    def __enter__(self):
        self._real.acquire()
        return self

    def __exit__(self, *a):
        self.release()
        return False


def _run_with_injected_reset(mgr, apply_bpm):
    real = mgr._lock
    mgr._lock = _ResetInjectingLock(mgr, real)
    try:
        apply_bpm()
    finally:
        mgr._lock = real


def _assert_consistent(mgr):
    # Kern-Invariante: nie ein positiver Wert bei ausgeschalteter Quelle.
    assert not (mgr.bpm > 0 and mgr.current_source == "off"), (
        f"CDX-14-Race: _bpm={mgr.bpm} bei _source={mgr.current_source!r}"
    )


def test_request_bpm_reset_in_gap_stays_consistent():
    mgr = _fresh()
    _run_with_injected_reset(mgr, lambda: mgr.request_bpm(120.0, "os2l"))
    _assert_consistent(mgr)
    mgr.reset()


def test_set_manual_reset_in_gap_stays_consistent():
    mgr = _fresh()
    _run_with_injected_reset(mgr, lambda: mgr.set_manual_bpm(150.0))
    _assert_consistent(mgr)
    mgr.reset()


def test_apply_detected_reset_in_gap_stays_consistent():
    mgr = _fresh()
    mgr._audio_active = True
    _run_with_injected_reset(mgr, lambda: mgr._apply_detected_bpm(128.0))
    _assert_consistent(mgr)
    mgr.reset()


def test_set_bpm_source_kwarg_sets_pair_atomically():
    # Vertrag: set_bpm(bpm, source=...) setzt Quelle UND Wert zusammen.
    mgr = _fresh()
    mgr.set_bpm(144.0, source="file")
    assert mgr.bpm == 144.0
    assert mgr.current_source == "file"
    mgr.reset()


def test_set_bpm_without_source_preserves_source():
    # Abwaertskompatibel: ohne source bleibt die Quelle unveraendert (Alt-Verhalten
    # der externen Aufrufer os2l-Fallback/chaser/tempo_bus). 0 leitet weiter 'off' ab.
    mgr = _fresh()
    mgr.set_bpm(120.0, source="file")
    assert mgr.current_source == "file"
    mgr.set_bpm(130.0)
    assert mgr.bpm == 130.0
    assert mgr.current_source == "file"
    mgr.set_bpm(0)
    assert mgr.current_source == "off"
    mgr.reset()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))

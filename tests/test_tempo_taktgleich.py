"""Stufe 1 — Per-Effekt „taktgleich" (align_on_start) + zuverlaessiger Bus-Start.

Deckt ab:
- align_on_start: Default True, Serialisierung, Round-Trip, Alt-Show (kein Key) -> True.
- bus_for_effect: leere id -> Free-Run/None, feste A-D werden erzeugt, Aliase -> Default.
- Frische Groove: stoppt der letzte Bus-Effekt, rastet ein neu gestarteter Effekt auf
  einen SAUBEREN Downbeat (jetzt) ein statt auf einem uralten, stehengebliebenen
  gemeinsamen Ursprung (der Stale-Origin-Bug, der Chaser/Sequenzen „zufaellig" starten liess).
- Laufende Groove: ein dazukommender Effekt teilt den Ursprung (bleibt phasengleich).
- align_on_start=False: ankert bewusst auf die eigene Position (frei), trotz Auto-Sync.
- Chaser: ein gesetzter Tempo-Bus schaltet den alten audio_triggered-Pfad exklusiv ab.
- Sequence: beats_per_step ist jetzt ein echtes, persistentes Feld (Parity mit Chaser).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.sequence import Sequence


@pytest.fixture(autouse=True)
def _clean():
    reset_tempo_bus_manager()
    get_function_manager().from_dict({"functions": []})   # leert + stoppt alles
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    mgr = get_bpm_manager()
    mgr.set_locked(False)
    mgr.reset()
    get_tempo_bus_manager().set_auto_sync(False)


def _matrix(fm, name, bus_id, mult=1.0):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.CHASE
    m.tempo_bus_id = bus_id
    m.tempo_multiplier = mult
    return m


# ── align_on_start: Feld + Serialisierung + Alt-Show-Default ────────────────────
def test_align_on_start_defaults_true_and_serializes():
    fm = get_function_manager()
    m = fm.new_rgb_matrix("M")
    assert m.align_on_start is True
    assert m.to_dict()["align_on_start"] is True
    m.align_on_start = False
    assert m.to_dict()["align_on_start"] is False


def test_align_on_start_roundtrip_and_old_show_default():
    fm = get_function_manager()
    m = _matrix(fm, "M", "Global")
    base = m.to_dict()
    fd_false = dict(base); fd_false["id"] = 40001; fd_false["align_on_start"] = False
    fd_old = dict(base);   fd_old["id"] = 40002;   fd_old.pop("align_on_start", None)
    fm.from_dict({"functions": [fd_false, fd_old]})
    assert fm.get(40001).align_on_start is False, "explizit False muss erhalten bleiben"
    assert fm.get(40002).align_on_start is True, "Alt-Show ohne Key -> taktgleich (True)"


# ── bus_for_effect: leere id = Free-Run, feste A-D werden erzeugt ────────────────
def test_bus_for_effect_resolution_and_lazy_fixed_bus():
    tbm = get_tempo_bus_manager()
    assert tbm.bus_for_effect("") is None
    assert tbm.bus_for_effect("   ") is None
    assert tbm.bus_for_effect(None) is None
    assert tbm.bus_for_effect("Global") is tbm.get("default")
    assert tbm.bus_for_effect("default") is tbm.get("default")
    a = tbm.bus_for_effect("A")
    assert a is not None and a.bus_id == "A"
    assert tbm.bus_for_effect("A") is a, "feste Buses muessen idempotent aufgeloest werden"
    assert tbm.bus_for_effect("KeinBus") is None


# ── Kern-Fix: frische Groove rastet auf sauberen Downbeat ein (Stale-Origin) ─────
def test_fresh_groove_reanchors_to_clean_downbeat():
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    tbm.set_auto_sync(True); mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    a = _matrix(fm, "A", "Global"); a.start()       # erster: Ursprung = 0
    assert abs(a._beat_anchor) < 1e-9
    d.advance_frame(2.65)                            # Bus laeuft 5.3 Beats weiter
    a.stop()                                         # Bus jetzt leer
    b = _matrix(fm, "B", "Global"); b.start()        # frische Groove -> Downbeat = jetzt
    pos = d.position()
    assert abs(b._beat_anchor - pos) < 1e-6, "frische Groove nicht auf sauberem Downbeat"
    assert b._beat_anchor > 1.0, "Ursprung blieb am uralten 0 haengen (Stale-Origin-Bug)"


def test_running_groove_keeps_shared_origin():
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    tbm.set_auto_sync(True); mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    a = _matrix(fm, "A", "Global"); a.start()        # Ursprung = 0
    d.advance_frame(2.65)
    b = _matrix(fm, "B", "Global"); b.start()        # A laeuft -> teilt Ursprung
    assert abs(b._beat_anchor - a._beat_anchor) < 1e-9, "laufende Groove: Ursprung nicht geteilt"
    assert abs(b._beat_anchor) < 1e-9


def test_align_off_starts_at_own_zero_even_with_auto_sync():
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    tbm.set_auto_sync(True); mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    a = _matrix(fm, "A", "Global"); a.start()        # Ursprung = 0
    d.advance_frame(2.65)
    c = _matrix(fm, "C", "Global"); c.align_on_start = False; c.start()
    pos = d.position()
    assert abs(c._beat_anchor - pos) < 1e-6, "frei: muss auf eigene Position ankern"
    assert abs(a._beat_anchor) < 1e-9, "frei-Start darf den gemeinsamen Ursprung nicht aendern"


# ── Chaser: Bus schaltet den alten audio_triggered-Pfad exklusiv ab ─────────────
def test_chaser_setting_bus_disables_audio_triggered():
    fm = get_function_manager()
    c = fm.new_chaser("C")
    c.audio_triggered = True
    assert c.set_param("tempo_bus_id", "A") is True
    assert c.tempo_bus_id == "A"
    assert c.audio_triggered is False, "bus-gebundener Chaser darf nicht doppelt per Beat zaehlen"
    c.audio_triggered = True
    c.set_param("tempo_bus_id", "")                   # Free-Run laesst audio_triggered unberuehrt
    assert c.audio_triggered is True


# ── Sequence: beats_per_step ist ein echtes, persistentes Feld ──────────────────
def test_sequence_beats_per_step_field_and_persist():
    fm = get_function_manager()
    s = fm.new_sequence("S")
    assert s.beats_per_step == 1
    s.beats_per_step = 2
    d = s.to_dict()
    assert d["beats_per_step"] == 2
    assert Sequence.from_dict(d).beats_per_step == 2
    d2 = dict(d); d2.pop("beats_per_step", None)
    assert Sequence.from_dict(d2).beats_per_step == 1, "Alt-Show ohne Key -> Default 1"

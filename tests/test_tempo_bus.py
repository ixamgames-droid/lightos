"""Unit-Tests fuer ``src.core.engine.tempo_bus`` (Tempo-Buses).

Alles deterministisch: keine ``sleep``s, keine Abhaengigkeit vom BPM-Daemon-Thread.
Die Beat-Position wird ausschliesslich ueber ``advance_frame`` getrieben; wo echte
Zeit noetig waere (``tap()``), wird ``tempo_bus.time.monotonic`` gemonkeypatcht.

Isolations-Vertrag (dieses Projekt hat eine Historie von Singleton-Leak-Flakies):
Eine autouse-Fixture setzt VOR und NACH jedem Test den TempoBus-Singleton sowie den
globalen BPMManager zurueck -> sauberer globaler Zustand, keine geleakten
Beat-Callbacks.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Etabliertes Muster (vgl. test_fade_curve.py): den verschachtelten Projekt-Root
# auf sys.path legen, damit ``import src.core...`` auch beim Einzel-Datei-Lauf greift.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from src.core.engine import tempo_bus as tb
from src.core.engine.tempo_bus import (
    TempoBus,
    TempoBusManager,
    get_tempo_bus_manager,
    reset_tempo_bus_manager,
)
from src.core.engine.bpm_manager import get_bpm_manager


# ── Isolation ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_tempo_state():
    """Frischer TempoBus-Singleton + sauberer globaler BPMManager pro Test.

    Vor UND nach jedem Test: Singleton verwerfen (meldet Default-Bus beim
    BPMManager ab) und den globalen BPMManager ausschalten (stoppt seinen Thread,
    leert Tap-Historie). Verhindert geleakte Beat-Callbacks ueber die Suite.
    """
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


# ── 1: Manueller Bus integriert Phase aus BPM ────────────────────────────────────

def test_manual_bus_120bpm_integrates_position():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(120)
    assert bus.bpm == pytest.approx(120.0)

    # 120 BPM == 2 Beats/s. 5 * 0.1s = 0.5s -> genau 1 Beat.
    for _ in range(5):
        bus.advance_frame(0.1)
    assert bus.position() == pytest.approx(1.0, abs=1e-9)


def test_manual_bus_quarter_beat_phase():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(120)
    # 0.25s bei 120 BPM (2 Beats/s) -> 0.5 Beats.
    bus.advance_frame(0.25)
    bpm, count, phase, pos = bus.snapshot()
    assert count == 0
    assert phase == pytest.approx(0.5, abs=1e-9)
    assert pos == pytest.approx(0.5, abs=1e-9)


# ── 2: Phasen-Wrap + Beat-Count ueber mehrere Beats ──────────────────────────────

def test_phase_wraps_and_beat_count_increments():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(120)
    # 1.0s bei 120 BPM -> exakt 2 Beats: count=2, phase~0.
    bus.advance_frame(1.0)
    bpm, count, phase, pos = bus.snapshot()
    assert count == 2
    assert phase == pytest.approx(0.0, abs=1e-9)
    assert pos == pytest.approx(2.0, abs=1e-9)


def test_phase_stays_in_unit_interval_across_many_frames():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(150)
    for _ in range(37):
        bus.advance_frame(0.073)
        _, _, phase, _ = bus.snapshot()
        assert 0.0 <= phase < 1.0


# ── 3: reset_phase nullt count + phase ───────────────────────────────────────────

def test_reset_phase_zeros_count_and_phase():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(120)
    bus.advance_frame(0.9)  # count/phase deutlich != 0
    assert bus.position() > 0.0
    bus.reset_phase()
    bpm, count, phase, pos = bus.snapshot()
    assert count == 0
    assert phase == pytest.approx(0.0)
    assert pos == pytest.approx(0.0)


# ── 4: bpm == 0 bedeutet AUS (keine Bewegung) ────────────────────────────────────

def test_bpm_zero_never_advances():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    # Nie gesetzt -> default 0.
    for _ in range(5):
        bus.advance_frame(0.2)
    assert bus.position() == pytest.approx(0.0)

    # Explizit auf 0 (aus) gesetzt -> immer noch keine Bewegung.
    bus.set_bpm(120)
    bus.advance_frame(0.1)
    assert bus.position() > 0.0
    bus.set_bpm(0)
    pos_before = bus.position()
    for _ in range(5):
        bus.advance_frame(0.2)
    assert bus.position() == pytest.approx(pos_before)


# ── 5: tap() — kontrollierte monotonic-Sequenz -> ~120 BPM, source=="tap" ─────────

class _FakeClock:
    """Gibt eine kontrollierte, aufsteigende Zeitsequenz zurueck.

    Wichtig: ``tb.time`` / ``bm.time`` SIND das globale ``time``-Modul — ein Patch
    von ``monotonic`` wirkt prozessweit (auch in Hintergrund-Threads wie MidiDispatch).
    Darum darf der Fake NIE ``StopIteration`` werfen: nach Verbrauch der geplanten
    Werte gibt er einfach den letzten Wert zurueck (Tap-Aufrufe im Test ziehen die
    Werte der Reihe nach; fremde Threads sehen den letzten Stand)."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0

    def monotonic(self):
        if self._i < len(self._values):
            v = self._values[self._i]
            self._i += 1
            return v
        return self._values[-1] if self._values else 0.0


def test_tap_converges_to_120_bpm(monkeypatch):
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")

    # Fuenf Taps mit konstantem 0.5s-Abstand -> vier 0.5s-Intervalle -> 120 BPM.
    clock = _FakeClock([0.0, 0.5, 1.0, 1.5, 2.0])
    monkeypatch.setattr(tb.time, "monotonic", clock.monotonic)

    result = None
    for _ in range(5):
        result = bus.tap()

    assert bus.source == "tap"
    assert result == pytest.approx(120.0, abs=1e-6)
    assert bus.bpm == pytest.approx(120.0, abs=1e-6)


def test_tap_parity_with_bpm_manager(monkeypatch):
    """Gleiche Mittelungs-Mathematik wie ``BPMManager.tap`` (Mittel der Intervalle)."""
    seq = [0.0, 0.4, 0.8, 1.3, 1.7]  # Intervalle: .4 .4 .5 .4 -> avg .425

    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    monkeypatch.setattr(tb.time, "monotonic", _FakeClock(seq).monotonic)
    bus_bpm = None
    for _ in range(5):
        bus_bpm = bus.tap()

    bpm_mgr = get_bpm_manager()
    import src.core.engine.bpm_manager as bm
    monkeypatch.setattr(bm.time, "monotonic", _FakeClock(seq).monotonic)
    glob_bpm = None
    for _ in range(5):
        glob_bpm = bpm_mgr.tap()

    assert bus_bpm == pytest.approx(glob_bpm, abs=1e-6)


# ── 6: Default-Bus proxyt den globalen BPMManager ────────────────────────────────

def test_default_bus_identity_and_lookup():
    mgr = get_tempo_bus_manager()
    default = mgr.get(TempoBusManager.DEFAULT_BUS)
    assert default is not None
    assert default.source == "bpm_global"
    # "" und None liefern denselben Default-Bus.
    assert mgr.get("") is default
    assert mgr.get(None) is default
    assert mgr.get("default") is default
    # Unbekannt -> None.
    assert mgr.get("nope") is None


def test_default_bus_advances_with_global_bpm_then_stops():
    mgr = get_tempo_bus_manager()
    default = mgr.get(TempoBusManager.DEFAULT_BUS)
    assert default.position() == pytest.approx(0.0)

    get_bpm_manager().set_bpm(120)  # 2 Beats/s
    # Einen kleinen Frame treiben; Wallclock << 0.5s -> der BPM-Timer-Thread
    # feuert in dieser Zeit keinen Beat, der re-ankern wuerde.
    mgr.advance_frame(0.1)
    pos_running = default.position()
    assert pos_running == pytest.approx(0.2, abs=0.02)

    # Globalen BPM ausschalten -> Default-Bus steht (effektive BPM 0).
    get_bpm_manager().reset()
    pos_after_reset = default.position()
    mgr.advance_frame(0.2)
    mgr.advance_frame(0.2)
    assert default.position() == pytest.approx(pos_after_reset)


def test_default_set_bpm_forwards_to_global():
    mgr = get_tempo_bus_manager()
    default = mgr.get(TempoBusManager.DEFAULT_BUS)
    default.set_bpm(140)
    assert get_bpm_manager().bpm == pytest.approx(140.0)


# ── 7: Externe Quelle (TempoSource) ──────────────────────────────────────────────

class _FakeSource:
    """TempoSource ohne kontinuierliche beat_phase: BPM + register_beat."""

    def __init__(self, bpm: float):
        self._bpm = bpm
        self._cb = None

    def current_bpm(self) -> float:
        return self._bpm

    def register_beat(self, cb):
        self._cb = cb

    def fire_beat(self, ts: float = 0.0):
        assert self._cb is not None
        self._cb(ts)


class _FakePhaseSource(_FakeSource):
    """TempoSource MIT fixer kontinuierlicher beat_phase()."""

    def __init__(self, bpm: float, phase: float):
        super().__init__(bpm)
        self._phase = phase

    def beat_phase(self):
        return self._phase


def test_external_source_without_phase_integrates_and_reanchors():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("E")
    src = _FakeSource(bpm=120.0)
    bus.attach_source(src)
    assert bus.source == "external"

    # Ohne beat_phase() -> Phase wird aus current_bpm() integriert.
    bus.advance_frame(0.25)  # 0.5 Beats
    _, count0, phase0, _ = bus.snapshot()
    assert count0 == 0
    assert phase0 == pytest.approx(0.5, abs=1e-9)

    # Beat-Callback re-ankert: count +1, phase -> 0.
    src.fire_beat(ts=1.0)
    _, count1, phase1, _ = bus.snapshot()
    assert count1 == 1
    assert phase1 == pytest.approx(0.0)


def test_external_source_with_phase_override():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("E")
    src = _FakePhaseSource(bpm=120.0, phase=0.37)
    bus.attach_source(src)

    bus.advance_frame(0.25)  # wuerde sonst 0.5 integrieren
    _, _, phase, _ = bus.snapshot()
    # Kontinuierliche Quelle -> Bus lockt exakt auf den Override (mod 1).
    assert phase == pytest.approx(0.37)

    # Auch ein Override > 1 wird mod 1 uebernommen.
    src._phase = 2.6
    bus.advance_frame(0.1)
    _, _, phase2, _ = bus.snapshot()
    assert phase2 == pytest.approx(0.6, abs=1e-9)


def test_detach_source_reverts_to_manual():
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("E")
    bus.attach_source(_FakeSource(120.0))
    assert bus.source == "external"
    bus.detach_source()
    assert bus.source == "manual"


# ── 8: Persistenz ────────────────────────────────────────────────────────────────

def test_manager_to_dict_excludes_default_and_round_trips():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("A").set_bpm(120)
    mgr.ensure_bus("B").set_bpm(96)

    data = mgr.to_dict()
    ids = {d["bus_id"] for d in data}
    assert ids == {"A", "B"}            # Default-Bus NICHT enthalten
    assert TempoBusManager.DEFAULT_BUS not in ids

    # In frischen Manager laden.
    reset_tempo_bus_manager()
    mgr2 = get_tempo_bus_manager()
    mgr2.load_dict(data)
    assert {b.bus_id for b in mgr2.named_buses()} == {"A", "B"}
    assert mgr2.get("A").bpm == pytest.approx(120.0)
    assert mgr2.get("B").bpm == pytest.approx(96.0)
    # Default ueberlebt und ist weiterhin bpm_global.
    default = mgr2.get(TempoBusManager.DEFAULT_BUS)
    assert default is not None
    assert default.source == "bpm_global"


def test_bus_to_dict_from_dict_round_trip():
    bus = TempoBus("X", source="manual")
    bus.set_bpm(133)
    d = bus.to_dict()
    assert d == {"bus_id": "X", "source": "manual", "bpm": pytest.approx(133.0)}

    restored = TempoBus.from_dict(d)
    assert restored.bus_id == "X"
    assert restored.source == "manual"
    assert restored.bpm == pytest.approx(133.0)


def test_load_dict_replaces_named_buses_keeps_default():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("OLD").set_bpm(100)
    mgr.load_dict([{"bus_id": "NEW", "source": "manual", "bpm": 80}])
    ids = {b.bus_id for b in mgr.named_buses()}
    assert ids == {"NEW"}               # OLD entfernt
    assert mgr.get(TempoBusManager.DEFAULT_BUS) is not None


# ── 9: remove_bus — Default geschuetzt, benannte entfernbar ───────────────────────

def test_remove_bus_default_is_noop_named_removed():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("A").set_bpm(120)
    default = mgr.get(TempoBusManager.DEFAULT_BUS)

    # Default ist geschuetzt -> No-op.
    mgr.remove_bus(TempoBusManager.DEFAULT_BUS)
    assert mgr.get(TempoBusManager.DEFAULT_BUS) is default

    # Benannter Bus wird entfernt.
    mgr.remove_bus("A")
    assert mgr.get("A") is None
    assert mgr.get(TempoBusManager.DEFAULT_BUS) is default

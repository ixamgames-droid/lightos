"""Beweist die neue Tempo-Bus Phasen-Synchronisation fuer EFX, Chaser und Sequence.

Kern der Garantie (docs/TEMPO_SYNC_PLAN.md): ein zeitbasierter Effekt, der auf
einem Tempo-Bus haengt, leitet seine Render-Position aus der Bus-POSITION ab
statt aus privat akkumuliertem ``dt`` — damit koppeln mehrere Effekte auf demselben
Bus exakt (×1 / ×2 / ÷2 …), unabhaengig von Frame-Jitter und Startzeitpunkt:

  effect_pos = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset   [Beats]

- EFX (``EfxInstance._sync_from_bus`` im ``_advance``): bildet effect_pos auf
  ``_phase`` (forward/backward loop, bounce-Dreieck, one-shot-Klemme) bzw.
  ``_rand_progress`` (RANDOM) ab.
- Chaser (``Chaser._advance_from_bus`` zuerst in ``write``): 1 Step je
  ``beats_per_step`` Beats, durch ``tempo_multiplier`` skaliert.
- Sequence (``Sequence._bus_steps_to_advance``): Anzahl Step-Advances dieses Frames.

Es werden echte Zahlen geprueft (pytest.approx). Es wird NICHT geschlafen — alles
laeuft ueber ``mgr.advance_frame(dt)`` + direkte Methodenaufrufe. Strikt nur dieses
Test-File; ``src/`` wird nicht angefasst.
"""
from __future__ import annotations

import pytest

from src.core.engine.tempo_bus import (get_tempo_bus_manager,
                                        reset_tempo_bus_manager)
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.efx import EfxInstance, EfxFixture, EfxAlgorithm
from src.core.engine.chaser import Chaser, ChaserStep
from src.core.engine.sequence import Sequence, SequenceStep
from src.core.engine.function import RunOrder, Direction


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Dieses Projekt hat bekannte Singleton-Leak-Flakies (Beat-Callbacks sammeln
    sich an). Vor UND nach jedem Test den Tempo-Bus-Manager + BPM-Manager nullen."""
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _bus_at_120(bus_id: str = "A"):
    """Manueller Bus @120 BPM. position() waechst um 2*dt Beats pro advance_frame."""
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus(bus_id, source="manual")
    bus.set_bpm(120.0)
    assert bus.bpm == pytest.approx(120.0)
    return mgr, bus


def _advance_bus_to(mgr, bus, target_beats: float, frames: int = 50):
    """Faehrt die Bus-Position in gleichmaessigen Frames auf ~target_beats.
    120 BPM -> 1 Beat = 0.5 s. dt pro Frame = (target/2)/frames."""
    total_seconds = target_beats / 2.0   # 120 BPM => beats = 2*seconds
    dt = total_seconds / frames
    for _ in range(frames):
        mgr.advance_frame(dt)
    return bus.position()


def _make_efx(bus_id="A", algo=EfxAlgorithm.CIRCLE, direction="forward",
              loop=True, mult=1.0, off=0.0, anchor=0.0):
    e = EfxInstance("E")
    e.algorithm = algo
    e.fixtures = [EfxFixture(fid=1)]
    e.direction = direction
    e.loop = loop
    e.tempo_bus_id = bus_id
    e.tempo_multiplier = mult
    e.phase_offset = off
    e._beat_anchor = anchor
    e._running = True
    e._phase = 0.0
    e._rand_progress = 0.0
    return e


# ════════════════════════════════════════════════════════════════════════════
# EFX
# ════════════════════════════════════════════════════════════════════════════

def test_efx_forward_loop_synced():
    """1. forward loop: _phase = effect_pos % 1. Nach 1 Beat -> 0.0, bei 0.5 Beat
    -> 0.5; mult=2 bei 0.5 Beat -> 1.0%1 = 0.0."""
    mgr, bus = _bus_at_120("A")

    # mult=1, bei 0.5 Beat -> _phase ~ 0.5
    e = _make_efx("A", mult=1.0)
    _advance_bus_to(mgr, bus, 0.5)
    e._advance(0.0)
    assert bus.position() == pytest.approx(0.5, abs=1e-9)
    assert e._phase == pytest.approx(0.5, abs=1e-9)

    # weiter auf 1.0 Beat -> _phase ~ 1.0 % 1 = 0.0
    _advance_bus_to(mgr, bus, 0.5)   # +0.5 Beat -> Position 1.0
    assert bus.position() == pytest.approx(1.0, abs=1e-9)
    e._advance(0.0)
    assert e._phase == pytest.approx(0.0, abs=1e-9)

    # mult=2: bei Bus-Position 0.5 ist effect_pos = 1.0 -> _phase = 0.0
    reset_tempo_bus_manager()
    mgr2, bus2 = _bus_at_120("A")
    e2 = _make_efx("A", mult=2.0)
    _advance_bus_to(mgr2, bus2, 0.5)
    assert bus2.position() == pytest.approx(0.5, abs=1e-9)
    e2._advance(0.0)
    assert e2._phase == pytest.approx(0.0, abs=1e-9)


def test_efx_backward_loop_synced():
    """2. backward loop: _phase = (-effect_pos) % 1."""
    mgr, bus = _bus_at_120("A")
    e = _make_efx("A", direction="backward", mult=1.0)

    _advance_bus_to(mgr, bus, 0.3)   # effect_pos = 0.3
    e._advance(0.0)
    assert bus.position() == pytest.approx(0.3, abs=1e-9)
    # (-0.3) % 1 == 0.7
    assert e._phase == pytest.approx((-0.3) % 1.0, abs=1e-9)
    assert e._phase == pytest.approx(0.7, abs=1e-9)


def test_efx_bounce_synced():
    """3. bounce: Dreieck 0->1->0 ueber 2 Beats. effect_pos 0,0.5,1,1.5,2 ->
    _phase 0,0.5,1,0.5,0."""
    expected = {0.0: 0.0, 0.5: 0.5, 1.0: 1.0, 1.5: 0.5, 2.0: 0.0}
    for pos_target, want in expected.items():
        reset_tempo_bus_manager()
        mgr, bus = _bus_at_120("A")
        e = _make_efx("A", direction="bounce", loop=True, mult=1.0)
        if pos_target > 0.0:
            _advance_bus_to(mgr, bus, pos_target)
        assert bus.position() == pytest.approx(pos_target, abs=1e-9)
        e._advance(0.0)
        assert e._phase == pytest.approx(want, abs=1e-9), (
            f"bounce bei effect_pos {pos_target}: erwartet {want}, war {e._phase}")


def test_efx_one_shot_synced_clamps():
    """4. one-shot (loop=False, direction != bounce): forward klemmt auf 1.0,
    backward auf 0.0 nach >1 Beat — wrappt NIE."""
    # forward: nach 1.7 Beats min(1.0, 1.7) = 1.0
    mgr, bus = _bus_at_120("A")
    e = _make_efx("A", direction="forward", loop=False, mult=1.0)
    _advance_bus_to(mgr, bus, 1.7)
    e._advance(0.0)
    assert e._phase == pytest.approx(1.0, abs=1e-9)
    # noch weiter -> bleibt geklemmt (kein Wrap auf 0.7)
    _advance_bus_to(mgr, bus, 1.0)   # Position 2.7
    e._advance(0.0)
    assert e._phase == pytest.approx(1.0, abs=1e-9)

    # backward: nach 1.7 Beats max(0.0, 1 - 1.7) = 0.0
    reset_tempo_bus_manager()
    mgr2, bus2 = _bus_at_120("A")
    b = _make_efx("A", direction="backward", loop=False, mult=1.0)
    _advance_bus_to(mgr2, bus2, 1.7)
    b._advance(0.0)
    assert b._phase == pytest.approx(0.0, abs=1e-9)
    # weiter -> bleibt 0.0
    _advance_bus_to(mgr2, bus2, 1.0)
    b._advance(0.0)
    assert b._phase == pytest.approx(0.0, abs=1e-9)

    # vor einem Beat (0.4): forward _phase = 0.4 (noch nicht geklemmt)
    reset_tempo_bus_manager()
    mgr3, bus3 = _bus_at_120("A")
    f = _make_efx("A", direction="forward", loop=False, mult=1.0)
    _advance_bus_to(mgr3, bus3, 0.4)
    f._advance(0.0)
    assert f._phase == pytest.approx(0.4, abs=1e-9)


def test_efx_one_shot_bounce_synced_holds():
    """4b. one-shot bounce (loop=False, direction="bounce"): EIN Dreieck 0->1->0
    ueber 2 Beats, danach bei 0.0 GEHALTEN — schwingt NICHT endlos weiter.
    effect_pos 0,0.5,1,1.5,2,3,4 -> _phase 0,0.5,1,0.5,0,0,0.
    Kern: bei effect_pos 3.0 und 4.0 ist _phase 0.0 (gehalten), nicht oszillierend."""
    expected = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (1.5, 0.5),
                (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
    for pos_target, want in expected:
        reset_tempo_bus_manager()
        mgr, bus = _bus_at_120("A")
        e = _make_efx("A", algo=EfxAlgorithm.CIRCLE, direction="bounce",
                      loop=False, mult=1.0, anchor=0.0)
        if pos_target > 0.0:
            _advance_bus_to(mgr, bus, pos_target)
        assert bus.position() == pytest.approx(pos_target, abs=1e-9)
        e._advance(0.0)
        assert e._phase == pytest.approx(want, abs=1e-6), (
            f"one-shot bounce bei effect_pos {pos_target}: erwartet {want}, "
            f"war {e._phase}")


def test_efx_one_shot_forward_negative_offset_clamps():
    """4c. one-shot forward mit negativem phase_offset: _phase = clamp(effect_pos, 0, 1).
    Bei Start (effect_pos ~ -0.3) MUSS _phase 0.0 sein — nicht negativ, nicht auf 0.7
    gewrappt. Spaeter (effect_pos ~ 0.5) -> 0.2; ab effect_pos >= 1.3 -> 1.0."""
    mgr, bus = _bus_at_120("A")
    e = _make_efx("A", algo=EfxAlgorithm.CIRCLE, direction="forward",
                  loop=False, mult=1.0, off=-0.3, anchor=0.0)

    # Bus-Position ~ 0 -> effect_pos ~ -0.3 -> geklemmt auf 0.0 (NICHT -0.3 / 0.7).
    mgr.advance_frame(0.0)
    e._advance(0.0)
    assert bus.position() == pytest.approx(0.0, abs=1e-9)
    assert e._phase == 0.0

    # Bus auf 0.5 Beat -> effect_pos = 0.5 - 0.3 = 0.2 -> _phase ~ 0.2.
    _advance_bus_to(mgr, bus, 0.5)
    assert bus.position() == pytest.approx(0.5, abs=1e-9)
    e._advance(0.0)
    assert e._phase == pytest.approx(0.2, abs=1e-6)

    # Bus auf 1.6 Beat -> effect_pos = 1.6 - 0.3 = 1.3 >= 1 -> geklemmt auf 1.0.
    _advance_bus_to(mgr, bus, 1.1)   # +1.1 -> Position 1.6
    assert bus.position() == pytest.approx(1.6, abs=1e-9)
    e._advance(0.0)
    assert e._phase == 1.0


def test_efx_random_synced():
    """5. RANDOM: _rand_progress = effect_pos (forward) bzw. -effect_pos (backward)."""
    mgr, bus = _bus_at_120("A")
    e = _make_efx("A", algo=EfxAlgorithm.RANDOM, direction="forward", mult=1.0)
    _advance_bus_to(mgr, bus, 1.25)   # effect_pos = 1.25
    e._advance(0.0)
    assert bus.position() == pytest.approx(1.25, abs=1e-9)
    assert e._rand_progress == pytest.approx(1.25, abs=1e-9)

    reset_tempo_bus_manager()
    mgr2, bus2 = _bus_at_120("A")
    b = _make_efx("A", algo=EfxAlgorithm.RANDOM, direction="backward", mult=1.0)
    _advance_bus_to(mgr2, bus2, 1.25)
    b._advance(0.0)
    assert b._rand_progress == pytest.approx(-1.25, abs=1e-9)


def test_efx_free_run_byte_identity():
    """6. Free-Run (kein Bus): _advance fuettert den ALTEN dt-Pfad —
    forward loop _phase = (Sum speed_hz*speed*dt) % 1, byte-identisch."""
    e = EfxInstance("F")
    e.fixtures = [EfxFixture(fid=1)]
    e.algorithm = EfxAlgorithm.CIRCLE
    e.direction = "forward"
    e.loop = True
    e.tempo_bus_id = ""                  # bewusste Abwahl des Global-Defaults
    assert e.tempo_bus_id == ""
    e.speed_hz = 0.7
    e.speed = 1.5                         # Function-Master
    e._running = True
    e._phase = 0.0

    dts = [0.01, 0.033, 0.05, 0.007, 0.1, 0.02, 0.066]
    expected = 0.0
    for dt in dts:
        e._advance(dt)
        delta = e.speed_hz * max(0.0, float(e.speed)) * dt
        expected = (expected + delta) % 1.0
    # Identische Float-Operationsreihenfolge -> exakt gleich.
    assert e._phase == expected


def test_efx_sync_phase():
    """7. sync_phase(): synced -> _beat_anchor == bus.position(); free -> _phase reset."""
    mgr, bus = _bus_at_120("A")
    e = _make_efx("A", mult=1.0)
    _advance_bus_to(mgr, bus, 0.7)
    pos = bus.position()
    assert abs(pos - round(pos)) > 0.1   # wirklich fraktional
    e.sync_phase()
    assert e._beat_anchor == pytest.approx(pos)
    # Direkt danach: local_beats ~ 0 -> _phase ~ 0
    e._advance(0.0)
    assert e._phase == pytest.approx(0.0, abs=1e-9)

    # Free-Run: sync_phase setzt _phase / _rand_progress zurueck.
    f = EfxInstance("free")
    f.algorithm = EfxAlgorithm.RANDOM
    f.tempo_bus_id = ""
    f._phase = 0.42
    f._rand_progress = 3.3
    f.sync_phase()
    assert f._phase == pytest.approx(0.0)
    assert f._rand_progress == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════════════════
# Chaser
# ════════════════════════════════════════════════════════════════════════════

def _make_chaser(bus_id="A", mult=1.0, beats_per_step=1, n_steps=4, anchor=0.0):
    c = Chaser("C")
    c.run_order = RunOrder.Loop
    c.direction = Direction.Forward
    c.steps = [ChaserStep(function_id=100 + i, hold=1.0) for i in range(n_steps)]
    c.beats_per_step = beats_per_step
    c.tempo_bus_id = bus_id
    c.tempo_multiplier = mult
    c._beat_anchor = anchor
    c._running = True
    c._step_idx = 0
    c._synced_target_prev = None
    return c


def _drive_chaser_bus(c, mgr, bus, target_beats, frames=60):
    """Treibt Bus + Chaser-Bus-Stepping in gleichmaessigen Frames und sammelt
    den Verlauf der _step_idx-Werte (je Frame nach dem Advance)."""
    total_seconds = target_beats / 2.0
    dt = total_seconds / frames
    idxs = []
    for _ in range(frames):
        mgr.advance_frame(dt)
        # function_registry=None: _render_and_blend ist no-op, aber das Stepping
        # (das hier getestet wird) laeuft trotzdem ueber _advance_from_bus.
        handled = c._advance_from_bus({}, [], None, dt * c.speed)
        assert handled is True
        idxs.append(c._step_idx)
    return idxs


def test_chaser_synced_one_step_per_beat():
    """8. mult=1, beats_per_step=1: genau ein Step-Advance pro Beat (Loop, 4 Steps)."""
    mgr, bus = _bus_at_120("A")
    c = _make_chaser("A", mult=1.0, beats_per_step=1, n_steps=4)

    # Start bei Step 0; nach genau 1 Beat -> Step 1, 2 Beats -> 2, 3 -> 3, 4 -> 0 (loop).
    _drive_chaser_bus(c, mgr, bus, 1.0)
    assert bus.position() == pytest.approx(1.0, abs=1e-9)
    assert c._step_idx == 1
    _drive_chaser_bus(c, mgr, bus, 1.0)
    assert c._step_idx == 2
    _drive_chaser_bus(c, mgr, bus, 1.0)
    assert c._step_idx == 3
    _drive_chaser_bus(c, mgr, bus, 1.0)   # 4 Beats total -> Loop-Wrap auf 0
    assert c._step_idx == 0


def test_chaser_synced_multiplier():
    """9. mult=2 -> zwei Advances pro Beat; mult=0.5 -> ein Advance je 2 Beats."""
    # mult=2: nach 1 Beat sind 2 Steps gelaufen (0 -> 2).
    mgr, bus = _bus_at_120("A")
    c2 = _make_chaser("A", mult=2.0, beats_per_step=1, n_steps=8)
    _drive_chaser_bus(c2, mgr, bus, 1.0)
    assert bus.position() == pytest.approx(1.0, abs=1e-9)
    assert c2._step_idx == 2
    _drive_chaser_bus(c2, mgr, bus, 1.0)   # 2 Beats -> 4 Steps
    assert c2._step_idx == 4

    # mult=0.5: nach 1 Beat noch KEIN Advance, erst nach 2 Beats.
    reset_tempo_bus_manager()
    mgr2, bus2 = _bus_at_120("A")
    c05 = _make_chaser("A", mult=0.5, beats_per_step=1, n_steps=8)
    _drive_chaser_bus(c05, mgr2, bus2, 1.0)
    assert c05._step_idx == 0
    _drive_chaser_bus(c05, mgr2, bus2, 1.0)   # 2 Beats -> effect 1.0 -> 1 Advance
    assert bus2.position() == pytest.approx(2.0, abs=1e-9)
    assert c05._step_idx == 1


def test_chaser_free_run_and_audio_unchanged():
    """10. Free-Run (kein Bus): zeitbasiertes Stepping unveraendert; audio_triggered
    schaltet per trigger_next_step() weiter."""
    # Free-Run, zeitbasiert: total_duration = fade_in+hold+fade_out = 0+0.5+0 = 0.5 s.
    c = Chaser("free")
    c.run_order = RunOrder.Loop
    c.steps = [ChaserStep(function_id=1, hold=0.5),
               ChaserStep(function_id=2, hold=0.5)]
    c.tempo_bus_id = ""                  # bewusste Abwahl des Global-Defaults
    assert c.tempo_bus_id == ""
    c._running = True
    c._step_idx = 0
    # Unter der Step-Dauer: kein Advance.
    c.write({}, [], 0.4, None)
    assert c._step_idx == 0
    # Ueber die Step-Dauer hinaus (kumuliert 0.4+0.2 = 0.6 >= 0.5): Advance auf 1.
    c.write({}, [], 0.2, None)
    assert c._step_idx == 1

    # audio_triggered: nur ein Beat-Trigger schaltet weiter.
    a = Chaser("audio")
    a.run_order = RunOrder.Loop
    a.audio_triggered = True
    a.beats_per_step = 1
    a.steps = [ChaserStep(function_id=1, hold=1.0),
               ChaserStep(function_id=2, hold=1.0)]
    a._running = True
    a._on_start()
    assert a._step_idx == 0
    # Ohne Trigger: ein langer Frame bewegt nichts.
    a.write({}, [], 5.0, None)
    assert a._step_idx == 0
    # Ein Beat -> pending advance -> naechster write schaltet weiter.
    a.trigger_next_step()
    a.write({}, [], 0.01, None)
    assert a._step_idx == 1


def test_chaser_on_start_anchors_no_spurious_jump():
    """11. _on_start mit laufendem Bus: _beat_anchor = bus.position(), Step 0,
    und der erste Frame (Position ~ anchor) springt NICHT spontan weiter."""
    mgr, bus = _bus_at_120("A")
    # Bus auf eine fraktionale Position fahren, BEVOR der Chaser startet.
    _advance_bus_to(mgr, bus, 1.3)
    pos = bus.position()

    c = Chaser("C")
    c.run_order = RunOrder.Loop
    c.steps = [ChaserStep(function_id=100 + i, hold=1.0) for i in range(4)]
    c.beats_per_step = 1
    c.tempo_bus_id = "A"
    c.tempo_multiplier = 1.0
    c._running = True
    c._on_start()
    assert c._beat_anchor == pytest.approx(pos)
    assert c._step_idx == 0
    assert c._synced_target_prev is None

    # Erster Bus-Frame ohne Fortschritt (dt=0): local_beats ~ 0 -> kein Step-Sprung.
    mgr.advance_frame(0.0)
    c._advance_from_bus({}, [], None, 0.0)
    assert c._step_idx == 0
    # Auch ein winziger Frame (< 1 Beat) springt nicht.
    _drive_chaser_bus(c, mgr, bus, 0.5)
    assert c._step_idx == 0
    # Erst der naechste GANZE Beat ab dem Anker schaltet auf Step 1.
    _drive_chaser_bus(c, mgr, bus, 0.5)   # nun +1.0 Beat ab Anker
    assert c._step_idx == 1


# ════════════════════════════════════════════════════════════════════════════
# Sequence
# ════════════════════════════════════════════════════════════════════════════

def _make_sequence(bus_id="A", mult=1.0, beats_per_step=1, n_steps=4, anchor=0.0):
    sq = Sequence("S")
    sq.run_order = RunOrder.Loop
    sq.direction = Direction.Forward
    sq.steps = [SequenceStep(values={}, fade_in=0.0, hold=1.0) for _ in range(n_steps)]
    sq.beats_per_step = beats_per_step   # neues Feld (Default 1 in _bus_steps_to_advance)
    sq.tempo_bus_id = bus_id
    sq.tempo_multiplier = mult
    sq._beat_anchor = anchor
    sq._running = True
    sq._step_idx = 0
    sq._synced_target_prev = None
    return sq


def _drive_seq_bus(sq, mgr, bus, target_beats, frames=60):
    """Treibt Bus + Sequence-Bus-Stepping (direkt ueber _bus_steps_to_advance,
    so wie write() es nutzt) und wendet die Advances auf _step_idx an."""
    total_seconds = target_beats / 2.0
    dt = total_seconds / frames
    n = len(sq.steps)
    for _ in range(frames):
        mgr.advance_frame(dt)
        adv = sq._bus_steps_to_advance()
        assert adv is not None        # bus-synchron
        for _ in range(adv):
            sq._step_idx = (sq._step_idx + 1) % n
    return sq._step_idx


def test_sequence_synced_steps():
    """12. synced default (mult=1) -> ein Step pro Beat; mult=2 -> zwei pro Beat."""
    # default mult=1
    mgr, bus = _bus_at_120("A")
    sq = _make_sequence("A", mult=1.0, beats_per_step=1, n_steps=4)
    _drive_seq_bus(sq, mgr, bus, 1.0)
    assert bus.position() == pytest.approx(1.0, abs=1e-9)
    assert sq._step_idx == 1
    _drive_seq_bus(sq, mgr, bus, 2.0)   # +2 Beats -> +2 Steps -> idx 3
    assert sq._step_idx == 3

    # mult=2
    reset_tempo_bus_manager()
    mgr2, bus2 = _bus_at_120("A")
    sq2 = _make_sequence("A", mult=2.0, beats_per_step=1, n_steps=8)
    _drive_seq_bus(sq2, mgr2, bus2, 1.0)
    assert bus2.position() == pytest.approx(1.0, abs=1e-9)
    assert sq2._step_idx == 2          # 1 Beat * ×2 = 2 Steps


def test_sequence_free_run_unchanged():
    """13. Free-Run (kein Bus): _bus_steps_to_advance -> None -> Zeit-Pfad
    (Advance bei _step_elapsed >= total_duration), unveraendert."""
    sq = Sequence("free")
    sq.run_order = RunOrder.Loop
    sq.steps = [SequenceStep(values={}, fade_in=0.0, hold=0.5, fade_out=0.0),
                SequenceStep(values={}, fade_in=0.0, hold=0.5, fade_out=0.0)]
    sq.tempo_bus_id = ""                 # bewusste Abwahl des Global-Defaults
    assert sq.tempo_bus_id == ""
    assert sq._bus_steps_to_advance() is None   # frei -> Zeit-Pfad

    sq._running = True
    sq._step_idx = 0
    # total_duration je Step = 0.5 s. Unter der Dauer: kein Advance.
    sq.write({}, [], 0.4, None)
    assert sq._step_idx == 0
    # Ueber die Dauer hinaus (0.4 + 0.2 = 0.6 >= 0.5): Advance auf Step 1.
    sq.write({}, [], 0.2, None)
    assert sq._step_idx == 1


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))

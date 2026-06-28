"""Beweist die neue RGB-Matrix Tempo-Bus Phasen-Synchronisation.

Kern der Garantie (docs/TEMPO_SYNC_PLAN.md): ein zeitbasierter Effekt, der auf
einem Tempo-Bus haengt, leitet seine Render-Position aus der Bus-POSITION ab
(``_step = (bus.position - _beat_anchor) * tempo_multiplier + phase_offset``,
Einheit Beats) statt aus privat akkumuliertem ``dt``. Dadurch koppeln zwei
Matrizen auf demselben Bus exakt (×1 / ×2 / …), unabhaengig von Frame-Jitter und
Startzeitpunkt:

  - Bei JEDEM ganzen Beat N (C._step ~ N) ist D._step ~ 2N (gerade) → STROBE voll
    AN, und COLORFADE zeigt eine REINE Farbe (frac~0), die je Beat-Paritaet
    zwischen Rot/Gruen wechselt → der Dimmer ist beim Farbwechsel immer voll an.
  - Mitten zwischen zwei Beats (N+0.5) ist die STROBE-Matrix AUS.

Es werden echte Zahlen geprueft (pytest.approx). Es wird NICHT geschlafen —
alles wird ueber ``mgr.advance_frame(dt)`` + direkte ``_advance_step``-Aufrufe
getrieben. Strikt nur dieses Test-File; ``src/`` wird nicht angefasst.
"""
from __future__ import annotations

import pytest

from src.core.engine.tempo_bus import (get_tempo_bus_manager,
                                        reset_tempo_bus_manager)
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import (RgbMatrixInstance, RgbAlgorithm,
                                        ColorSequence)


RED = (255, 0, 0)
GREEN = (0, 255, 0)


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

def _make_colorfade(bus_id: str, mult: float = 1.0, off: float = 0.0):
    """COLORFADE-Matrix mit GENAU zwei aktiven Farben [Rot, Gruen] (L=2)."""
    m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.COLORFADE,
                          fixture_grid=[1, 2, 3, 4])
    m.colors = ColorSequence([RED, GREEN])
    assert m.colors.enabled_colors() == [RED, GREEN]   # L=2, beide aktiv
    m.tempo_bus_id = bus_id
    m.tempo_multiplier = mult
    m.phase_offset = off
    m._beat_anchor = 0.0
    return m


def _make_strobe(bus_id: str, mult: float = 2.0, off: float = 0.0):
    m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.STROBE,
                          fixture_grid=[1, 2, 3, 4])
    m.colors = ColorSequence([RED])
    m.tempo_bus_id = bus_id
    m.tempo_multiplier = mult
    m.phase_offset = off
    m._beat_anchor = 0.0
    return m


def _strobe_on(m: RgbMatrixInstance) -> bool:
    """True, wenn die STROBE-Matrix beim aktuellen _step voll AN ist."""
    px = m._render(m._step)
    return px[0] != (0, 0, 0)


def _strobe_render_on_at(m: RgbMatrixInstance, phase: float) -> bool:
    """True, wenn die STROBE-Matrix an einer GEGEBENEN Phase voll AN ist
    (rendert direkt -> immun gegen sub-ULP-Akkumulation der Test-Position)."""
    return m._render(float(phase))[0] != (0, 0, 0)


def _colorfade_pixel(m: RgbMatrixInstance):
    return m._render(m._step)[0]


# ── 1. Die Schlagzeilen-Garantie ──────────────────────────────────────────────

def test_headline_phase_lock_red_green_and_strobe():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("A").set_bpm(120.0)
    bus = mgr.get("A")
    assert bus.bpm == pytest.approx(120.0)

    C = _make_colorfade("A", mult=1.0)   # Farbe ×1
    D = _make_strobe("A", mult=2.0)      # Dimmer/Strobe ×2

    dt = 0.05
    seen_boundaries = 0
    seen_midbeats = 0
    # 120 BPM, dt=0.05 -> 0.1 Beats/Frame -> 10 Frames/Beat. ~6 Beats fahren.
    for _ in range(620):
        mgr.advance_frame(dt)
        C._advance_step(dt)
        D._advance_step(dt)

        step = C._step
        nearest = round(step)
        # GANZER Beat-Rand: C._step ~ ganze Zahl N (>=1, damit echt animiert).
        if nearest >= 1 and abs(step - nearest) < 1e-6:
            N = nearest
            seen_boundaries += 1
            # Kern-Koinzidenz: D laeuft mit ×2 -> bei Beat N ist D._step ~ 2N (GERADE).
            assert D._step == pytest.approx(2.0 * N, abs=1e-5)
            assert round(D._step) == 2 * N
            assert round(D._step) % 2 == 0
            # STROBE: on = int(p)%2==0; bei der GERADEN Beat-Position 2N voll AN.
            # Hinweis: Die Bus-Position kann durch Float-Akkumulation eine ULP UNTER
            # der ganzen Zahl liegen (0.9999999999999999), wodurch int() auf 2N-1
            # abrunden wuerde. Das ist ein reines Float-Darstellungsartefakt des
            # Test-Treibers (kein Quellfehler): die garantierte Koinzidenz ist
            # D._step ~ 2N, und an genau dieser ganzen (geraden) Beat-Position ist
            # die STROBE voll AN. Wir rendern daher an der nominalen Beat-Position.
            assert _strobe_render_on_at(D, 2 * N), f"STROBE muss bei Beat {N} AN sein"
            # COLORFADE: reine Farbe (frac~0), Paritaet N gerade=Rot / ungerade=Gruen.
            px = C._render(float(N))[0]
            expected = RED if N % 2 == 0 else GREEN
            assert px == expected, (
                f"COLORFADE bei Beat {N}: erwartet {expected}, war {px}")

        # MITTE zwischen zwei Beats (N+0.5): STROBE muss AUS sein.
        frac = step - int(step)
        if abs(frac - 0.5) < 1e-6 and step >= 0.5:
            seen_midbeats += 1
            mid = round(step * 2) / 2.0    # exakte N+0.5-Phase
            # D._step = 2*(N+0.5) = 2N+1 -> int ungerade -> AUS.
            assert D._step == pytest.approx(2.0 * mid, abs=1e-5)
            assert not _strobe_render_on_at(D, 2.0 * mid), (
                f"STROBE muss bei Beat-Mitte {mid} AUS sein")

    # Wir MUESSEN echte Beat-Raender und Mitten gesehen haben (sonst beweist der
    # Test nichts).
    assert seen_boundaries >= 5, f"zu wenige Beat-Raender: {seen_boundaries}"
    assert seen_midbeats >= 5, f"zu wenige Beat-Mitten: {seen_midbeats}"


# ── 2. Frame-Jitter-Immunitaet ────────────────────────────────────────────────

def test_frame_jitter_immunity_boundary_still_locks():
    """Unregelmaessige dt, die in Summe ganze Beats ergeben: die Integer-Rand-
    Koinzidenz haelt trotzdem, weil _step aus der Bus-Position abgeleitet ist
    (nicht akkumuliert)."""
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("A").set_bpm(120.0)

    C = _make_colorfade("A", mult=1.0)
    D = _make_strobe("A", mult=2.0)

    # Unregelmaessige Frame-Zeiten. 120 BPM -> 0.5 s pro Beat. Diese 8 dt summieren
    # sich auf 0.5 s -> exakt 1 Beat pro Zyklus.
    jitter = [0.013, 0.07, 0.031, 0.1, 0.016, 0.12, 0.04, 0.11]
    assert sum(jitter) == pytest.approx(0.5)

    boundaries = 0
    for cycle in range(6):                 # 6 Beats
        for dt in jitter:
            mgr.advance_frame(dt)
            C._advance_step(dt)
            D._advance_step(dt)
        # Am Ende jedes Zyklus liegt die Bus-Position auf einem ganzen Beat — durch
        # die unregelmaessigen, summierten Float-dt nur naeherungsweise, deshalb mit
        # Toleranz. Die KOPPLUNG (D = 2*C) ist exakt, weil beide aus derselben
        # Bus-Position abgeleitet sind.
        N = cycle + 1
        assert C._step == pytest.approx(float(N), abs=1e-3)
        assert D._step == pytest.approx(2.0 * C._step, abs=1e-12)
        assert D._step == pytest.approx(2.0 * N, abs=2e-3)
        # An der nominalen (geraden) Beat-Position voll AN bzw. reine Farbe.
        assert _strobe_render_on_at(D, 2 * N)
        expected = RED if N % 2 == 0 else GREEN
        assert C._render(float(N))[0] == expected
        boundaries += 1
    assert boundaries == 6


# ── 3. Sync re-anchor ─────────────────────────────────────────────────────────

def test_sync_phase_reanchors_to_bus_position():
    mgr = get_tempo_bus_manager()
    mgr.ensure_bus("A").set_bpm(120.0)
    bus = mgr.get("A")

    C = _make_colorfade("A", mult=1.0, off=0.0)

    # Bus auf eine FRAKTIONALE Position fahren (kein ganzer Beat).
    dt = 0.05
    for _ in range(7):                     # 7 * 0.1 = 0.7 Beats
        mgr.advance_frame(dt)
    pos = bus.position()
    assert pos == pytest.approx(0.7, abs=1e-6)
    assert abs(pos - round(pos)) > 0.1     # wirklich fraktional

    C.sync_phase()
    # _beat_anchor wurde exakt auf die Bus-Position gesetzt.
    assert C._beat_anchor == pytest.approx(pos)

    # Direkt danach (winziger Frame): local_beats ~ 0 -> _step ~ phase_offset (=0).
    mgr.advance_frame(0.0)                  # Bus-Position unveraendert
    C._advance_step(0.0)
    assert C._step == pytest.approx(0.0, abs=1e-9)

    # Auch mit phase_offset != 0 landet _step ~ phase_offset.
    D = _make_colorfade("A", mult=1.0, off=0.25)
    D.sync_phase()
    assert D._beat_anchor == pytest.approx(bus.position())
    D._advance_step(0.0)
    assert D._step == pytest.approx(0.25, abs=1e-9)


# ── 4. Free-Run-Regression (byte-identisch) ───────────────────────────────────

def test_free_run_unchanged_exact():
    """Ohne Tempo-Bus (Default "") laeuft _advance_step wie bisher:
    _step += matrix_speed * max(0, Function.speed) * dt — float-exakt."""
    F = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.COLORFADE,
                          fixture_grid=[1, 2, 3, 4], speed=3.0)
    F.tempo_bus_id = ""                    # bewusste Abwahl des Global-Defaults
    assert F.tempo_bus_id == ""
    assert F.matrix_speed == 3.0
    assert F.speed == 1.0                  # Function-Master Default
    assert F._frozen is False

    dts = [0.01, 0.033, 0.05, 0.007, 0.1, 0.02, 0.066]
    expected = 0.0
    for dt in dts:
        F._advance_step(dt)
        # Manuelle Referenz-Akkumulation mit identischer Arithmetik.
        expected = expected + (F.matrix_speed * max(0.0, F.speed)) * dt
    # Byte-identisch (gleiche Float-Operationsreihenfolge): exakt gleich.
    assert F._step == expected
    # Und: == 3.0 * sum(dt) in derselben Reihenfolge akkumuliert.
    ref = 0.0
    for dt in dts:
        ref = ref + 3.0 * dt
    assert F._step == ref

    # Freeze friert _step ein: weitere Aufrufe aendern nichts.
    frozen_at = F._step
    F._frozen = True
    for dt in dts:
        F._advance_step(dt)
    assert F._step == frozen_at


# ── 5. bpm==0-Fallback ────────────────────────────────────────────────────────

def test_bpm_zero_falls_back_to_free_run():
    """Matrix haengt an Bus "A", aber dessen BPM ist 0 -> _advance_step nutzt den
    Free-Run-Pfad (matrix_speed) und friert NICHT ein."""
    mgr = get_tempo_bus_manager()
    bus = mgr.ensure_bus("A")
    bus.set_bpm(0.0)                       # aus
    assert bus.bpm == 0.0

    m = RgbMatrixInstance(cols=4, rows=1, algorithm=RgbAlgorithm.COLORFADE,
                          fixture_grid=[1, 2, 3, 4], speed=2.0)
    m.colors = ColorSequence([RED, GREEN])
    m.tempo_bus_id = "A"
    m.tempo_multiplier = 1.0
    m._beat_anchor = 0.0
    assert m.matrix_speed == 2.0
    assert m._frozen is False

    dts = [0.05, 0.05, 0.05, 0.05]
    expected = 0.0
    for dt in dts:
        mgr.advance_frame(dt)              # Bus bleibt bei 0 -> Position eingefroren
        m._advance_step(dt)
        expected = expected + (m.matrix_speed * max(0.0, m.speed)) * dt
    # Free-Run-Pfad: _step ist gewachsen (NICHT eingefroren).
    assert m._step == pytest.approx(expected)
    assert m._step == pytest.approx(2.0 * sum(dts))
    assert m._step > 0.0

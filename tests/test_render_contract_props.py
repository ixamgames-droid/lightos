"""QA-14: Property-basierte Render-Vertrags-Tests (hypothesis).

Prueft die drei zentralen Invarianten aus ``docs/OUTPUT_MERGE_CONTRACT.md`` NICHT
an einzelnen Beispielen, sondern ueber generierte Szenarien (Kanalwerte 0..255,
Start-Reihenfolgen, Anzahl Funktionen):

  * WP-6  — Funktions-Kanalschutz: ein von einer Funktion (Matrix/EFX) getriebener
            Nicht-Intensitaets-Kanal wird vom Programmer-/Intensitaets-LTP NICHT
            ueberschrieben.
  * EE-02 — Programmer-Dimmer wirkt MULTIPLIKATIV auf die (ersatzweise) Intensitaet
            eines laufenden Effekts (out = base*prog/255), nie additiv.
  * LTP   — auf einem gemeinsamen Kanal gewinnt die ZULETZT gestartete Funktion.

Degradiert sauber (skip), falls hypothesis fehlt — siehe importorskip am Kopf.
Setup-Muster (AppState.__new__, Fake-Fixtures/FunctionManager, Universe) gespiegelt
aus tests/test_render_frame.py + tests/test_dimmer_master.py.
"""
import os
import threading
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.engine.function_manager import FunctionManager


# ── Fakes (Fixture / Kanal / raw-schreibender FunctionManager) ──────────────────
class _Ch:
    def __init__(self, attr, num, default=0):
        self.attribute = attr
        self.channel_number = num
        self.default_value = default


class _Fx:
    def __init__(self, fid, universe, address):
        self.fid = fid
        self.universe = universe
        self.address = address


class _RawFM:
    """Fake-FunctionManager: schreibt einen einzelnen Rohkanal (simuliert einen
    laufenden Effekt/Matrix, der genau diese Adresse treibt)."""
    def __init__(self, addr=None, val=0):
        self.addr = addr
        self.val = val

    def tick(self, universes, patch_cache, dt):
        if self.addr is not None and 1 in universes:
            universes[1].set_channel(self.addr, self.val)


def _make_state(chans, fm):
    """AppState ohne __init__ (kein DB/Thread), von Hand verdrahtet — 1 Fixture
    @ Universe 1, Adresse 1. Gespiegelt aus tests/test_dimmer_master.py."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = fm
    fx = _Fx(1, 1, 1)
    st._fix_index = {1: (fx, chans)}
    addrs = [fx.address + ch.channel_number - 1 for ch in chans]
    default = bytearray(512)
    for ch in chans:
        default[fx.address + ch.channel_number - 2] = ch.default_value
    st._default_frame = {1: bytes(default)}
    st._commit_spans = {1: [(min(addrs), len(addrs))]}
    st._patched_set = {1: frozenset(addrs)}
    st._engine_extra_prev = {}
    st._patch_cache = [fx]
    st.submaster_level = 1.0
    st.fixture_dimmers = {}
    st._prog_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


# ── WP-6: Funktions-Kanalschutz ────────────────────────────────────────────────
@settings(max_examples=200, deadline=None)
@given(
    func_val=st.integers(min_value=1, max_value=255),   # >0 -> als func-driven erkannt
    prog_val=st.integers(min_value=0, max_value=255),
    prog_inten=st.integers(min_value=0, max_value=255),
)
def test_wp6_function_channel_protected(func_val, prog_val, prog_inten):
    """Treibt eine Funktion einen Farb-(Nicht-Intensitaets-)Kanal, darf der
    Programmer diesen Kanal NICHT ueberschreiben — egal welchen Farbwert oder
    welche Intensitaet die Programmer-/Intensitaets-Quelle daneben setzt."""
    chans = [_Ch("intensity", 1, 0), _Ch("color_r", 2, 0)]
    color_addr = 2
    st = _make_state(chans, _RawFM(addr=color_addr, val=func_val))
    # Programmer will dieselbe Farbe (+ Intensitaet) setzen -> muss abprallen.
    st.programmer = {1: {"color_r": prog_val, "intensity": prog_inten}}
    st._render_frame(0.02)
    assert st.universes[1].get_channel(color_addr) == func_val


# ── EE-02: Programmer-Dimmer multipliziert (nie additiv) ───────────────────────
@settings(max_examples=200, deadline=None)
@given(
    base=st.integers(min_value=1, max_value=255),        # Effekt treibt die (Farb-)Intensitaet
    prog_inten=st.integers(min_value=0, max_value=255),  # Programmer-Dimmer
)
def test_ee02_programmer_dimmer_multiplies(base, prog_inten):
    """Ein laufender Effekt treibt die (ersatzweise) Intensitaet eines color-only
    Fixtures; der Programmer-Dimmer skaliert sie MULTIPLIKATIV: out = base*prog/255.
    Nie additiv (out <= base, nie base+prog)."""
    chans = [_Ch("color_r", 1, 0)]   # color-only: Intensitaet wirkt auf die Farbe
    addr = 1
    st = _make_state(chans, _RawFM(addr=addr, val=base))
    st.programmer = {1: {"intensity": prog_inten}}
    st._render_frame(0.02)
    out = st.universes[1].get_channel(addr)
    expected = int(base * (prog_inten / 255.0))
    assert out == expected
    assert out <= base                              # multiplikativ dimmt nur herunter
    assert out != base + prog_inten or prog_inten == 0   # niemals additiv


# ── LTP: zuletzt gestartete Funktion gewinnt ───────────────────────────────────
@settings(max_examples=200, deadline=None)
@given(
    order=st.lists(
        st.tuples(st.integers(min_value=1, max_value=9999),
                  st.integers(min_value=0, max_value=255)),
        min_size=1, max_size=6, unique_by=lambda t: t[0],
    )
)
def test_ltp_last_started_wins(order):
    """Mehrere Funktionen schreiben denselben Kanal; nach LTP schreibt die zuletzt
    gestartete zuletzt und gewinnt — unabhaengig von der (Hash-)Reihenfolge der
    Funktions-IDs."""
    class _WriterFunc:
        def __init__(self, value):
            self._value = value
            self.is_running = True
            self.intensity = 1.0

        def start(self):
            self.is_running = True

        def stop(self):
            self.is_running = False

        def write(self, universes, patch_cache, dt, registry):
            universes[1].set_channel(1, self._value)

    fm = FunctionManager()
    for fid, val in order:
        fm._functions[fid] = _WriterFunc(val)
    for fid, _ in order:
        fm.start(fid)
    u = {1: Universe(1)}
    fm.tick(u, [], 0.02)
    assert u[1].get_channel(1) == order[-1][1]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))

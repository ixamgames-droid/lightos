"""Persistence round-trip tests for the new tempo-sync serialization.

Beweist, dass die vier neuen Tempo-Felder auf der :class:`Function`-Basis
(``tempo_bus_id``, ``tempo_multiplier``, ``phase_offset``, ``sync_group``) sowie
die benannten Tempo-Buses sowohl über den Funktions-Loader
(:meth:`FunctionManager.from_dict`) als auch über die volle Show-Datei
(``save_show`` / ``load_show`` / ``reset_show``) verlustfrei round-trippen.

Setup folgt conftest.py + test_show_file.py: separate Show-DB (LIGHTOS_SHOW_DB),
kein Output-Thread. Hier zusätzlich eine eigene, EINDEUTIGE Temp-DB, damit der
volle Save/Load auf der echten AppState laufen kann, ohne andere Tests/eine
laufende App zu berühren.
"""
from __future__ import annotations

import os
import tempfile

# MUSS vor dem ersten app_state-Import gesetzt sein (siehe conftest.py). Eine
# EINDEUTIGE Datei nur für diesen Test, damit der echte FunctionManager-/Patch-
# Zustand frei mutiert werden kann.
os.environ["LIGHTOS_NO_OUTPUT_THREAD"] = "1"
os.environ["LIGHTOS_SHOW_DB"] = os.path.join(
    tempfile.gettempdir(), "tempo_persist_test.db")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")

import pytest

from src.core.engine.scene import Scene
from src.core.engine.function_manager import FunctionManager
from src.core.engine.tempo_bus import (
    get_tempo_bus_manager,
    reset_tempo_bus_manager,
    TempoBusManager,
)
from src.core.engine.bpm_manager import get_bpm_manager


# Nicht-Default-Werte für die vier serialisierten Tempo-Felder.
_NON_DEFAULT = {
    "tempo_bus_id": "A",
    "tempo_multiplier": 2.5,
    "phase_offset": 0.75,
    "sync_group": "grp1",
}


@pytest.fixture(autouse=True)
def _reset_tempo_singletons():
    """Vor UND nach jedem Test die Tempo-Singletons neu aufsetzen.

    ``reset_tempo_bus_manager`` meldet den Default-Bus beim globalen BPMManager
    ab (sonst sammeln sich über die Suite Beat-Callbacks an — bekannte Flaky-
    Quelle), ``get_bpm_manager().reset()`` schaltet die globale BPM aus.
    """
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


# ── 1. Funktions-Feld-Round-Trip über den Loader ─────────────────────────────

def test_function_tempo_fields_roundtrip_through_loader():
    """Scene mit nicht-Default-Tempo-Feldern → to_dict() → frischer
    FunctionManager.from_dict() → gleiche vier Werte, _beat_anchor == 0.0."""
    sc = Scene("Tempo-Szene")
    sc.tempo_bus_id = _NON_DEFAULT["tempo_bus_id"]
    sc.tempo_multiplier = _NON_DEFAULT["tempo_multiplier"]
    sc.phase_offset = _NON_DEFAULT["phase_offset"]
    sc.sync_group = _NON_DEFAULT["sync_group"]

    d = sc.to_dict()
    # to_dict() emittiert die vier Felder direkt.
    assert d["tempo_bus_id"] == "A"
    assert d["tempo_multiplier"] == 2.5
    assert d["phase_offset"] == 0.75
    assert d["sync_group"] == "grp1"
    # _beat_anchor ist privat und darf NICHT serialisiert werden.
    assert "_beat_anchor" not in d

    fm = FunctionManager()
    fm.from_dict({"functions": [d]})
    loaded = fm.all()
    assert len(loaded) == 1
    f = loaded[0]
    assert f.tempo_bus_id == "A"
    assert f.tempo_multiplier == 2.5
    assert f.phase_offset == 0.75
    assert f.sync_group == "grp1"
    # Privater Anker startet immer bei 0.0 (nicht aus dem Dict geladen).
    assert f._beat_anchor == 0.0


# ── 2. Abwärtskompatibilität: Alt-Show ohne Tempo-Keys ───────────────────────

def test_function_tempo_fields_backward_compat_defaults():
    """Ein Funktions-Dict OHNE die vier Tempo-Keys (alte Show) → Defaults."""
    old = {
        "id": 4242,
        "name": "Alt-Szene",
        "type": "Scene",
        "values": [],
        # bewusst KEINE tempo_*-Keys
    }
    # Sicherstellen, dass die Keys wirklich fehlen.
    for key in _NON_DEFAULT:
        assert key not in old

    fm = FunctionManager()
    fm.from_dict({"functions": [old]})
    loaded = fm.all()
    assert len(loaded) == 1
    f = loaded[0]
    assert f.tempo_bus_id == ""
    assert f.tempo_multiplier == 1.0
    assert f.phase_offset == 0.0
    assert f.sync_group == ""
    assert f._beat_anchor == 0.0


# ── 3. Voller Show-Save/Load mit Tempo-Feldern UND Tempo-Buses ───────────────

def test_full_show_save_load_roundtrips_tempo(tmp_path):
    """Echte AppState: Funktion mit nicht-Default-Tempo-Feldern + zwei benannte
    Buses A(128)/B(90) speichern, reset_show() (alles weg, Default bleibt), dann
    load_show() → Funktion + Buses wiederhergestellt, Default-Bus intakt."""
    from src.core.app_state import get_state
    from src.core.show import show_file

    state = get_state()
    # Sauberer Ausgangspunkt — eine evtl. von vorigen Tests befüllte Show leeren.
    show_file.reset_show()

    fm = state.function_manager
    sc = fm.new_scene("Tempo-Show-Szene")
    sc.tempo_bus_id = _NON_DEFAULT["tempo_bus_id"]
    sc.tempo_multiplier = _NON_DEFAULT["tempo_multiplier"]
    sc.phase_offset = _NON_DEFAULT["phase_offset"]
    sc.sync_group = _NON_DEFAULT["sync_group"]
    fn_id = sc.id

    tbm = get_tempo_bus_manager()
    tbm.ensure_bus("A").set_bpm(128)
    tbm.ensure_bus("B").set_bpm(90)

    path = os.path.join(str(tmp_path), "tempo_roundtrip.lshow")
    show_file.save_show(path)

    # ── reset_show(): Funktion + benannte Buses verschwinden, Default bleibt ──
    show_file.reset_show()
    assert fm.get(fn_id) is None, "Funktion sollte nach reset_show() weg sein"
    tbm = get_tempo_bus_manager()
    assert tbm.get("A") is None
    assert tbm.get("B") is None
    assert tbm.named_buses() == []
    default = tbm.get(TempoBusManager.DEFAULT_BUS)
    assert default is not None, "Default-Bus muss nach reset_show() existieren"
    assert default.source == "bpm_global"

    # ── load_show(): Funktion + Buses wiederhergestellt ──
    ok, msg = show_file.load_show(path)
    assert ok, msg

    fm = state.function_manager
    loaded = fm.get(fn_id)
    assert loaded is not None, "geladene Funktion fehlt"
    assert loaded.tempo_bus_id == "A"
    assert loaded.tempo_multiplier == 2.5
    assert loaded.phase_offset == 0.75
    assert loaded.sync_group == "grp1"

    tbm = get_tempo_bus_manager()
    bus_a = tbm.get("A")
    bus_b = tbm.get("B")
    assert bus_a is not None and bus_a.bpm == 128.0
    assert bus_b is not None and bus_b.bpm == 90.0
    # Der Default-Bus existiert weiterhin und proxyt den globalen BPMManager.
    default = tbm.get(TempoBusManager.DEFAULT_BUS)
    assert default is not None
    assert default.source == "bpm_global"


# ── 4. to_dict() schließt den reservierten Default-Bus aus ───────────────────

def test_tempo_buses_to_dict_excludes_default():
    """to_dict() darf nie einen Bus mit id 'default' enthalten — auch wenn
    daneben benannte Buses existieren."""
    tbm = get_tempo_bus_manager()
    # Default existiert per Konstruktion.
    assert tbm.get(TempoBusManager.DEFAULT_BUS) is not None
    tbm.ensure_bus("A").set_bpm(120)
    tbm.ensure_bus("B").set_bpm(140)

    dumped = tbm.to_dict()
    ids = [entry.get("bus_id") for entry in dumped]
    assert TempoBusManager.DEFAULT_BUS not in ids
    # Die benannten Buses sind aber enthalten.
    assert set(ids) == {"A", "B"}

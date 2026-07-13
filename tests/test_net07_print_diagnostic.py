"""CDX-01: Die NET-07-Warnung ("Eingang auf nicht gepatchtem out_univ") in
``apply_input_merge`` gibt ihre Diagnose via ``print(f"[app_state] ...")`` aus —
gemaess Projekt-Konvention (KEIN logging-Modul). Wir pruefen, dass genau EINE
solche Print-Zeile pro out_univ erscheint UND der ``input_unconfigured``-Zaehler
steigt. Fake-State-Muster wie test_input_unconfigured_universe.py."""
import os
import threading
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.core.app_state as A
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.sync import get_sync


def _make_state():
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}                # NUR Universe 1 gepatcht
    st.input_layer = {}
    st.input_merge_modes = {}
    st.input_last_seen = {}
    st.input_unconfigured = {}
    st._input_lock = threading.RLock()
    st.output_manager = types.SimpleNamespace(set_gm_address_mask=lambda m: None)
    return st


def test_net07_prints_app_state_diagnostic_no_logging(capsys):
    st = _make_state()
    # Universe 5 ist NICHT gepatcht -> stille Verwerfung, Diagnose als print.
    st.apply_input_merge(5, bytes([1]), "HTP")

    out = capsys.readouterr().out
    assert "[app_state]" in out
    assert "5" in out
    # Zaehler wurde gesetzt (dropped-because-unconfigured).
    assert st.input_unconfigured.get(5) == 1


def test_net07_prints_once_per_out_univ(capsys):
    st = _make_state()
    st.apply_input_merge(5, bytes([1]), "HTP")
    st.apply_input_merge(5, bytes([1]), "HTP")
    st.apply_input_merge(5, bytes([1]), "HTP")

    lines = [l for l in capsys.readouterr().out.splitlines()
             if "[app_state]" in l and "5" in l]
    # EINMAL warnen, aber Zaehler zaehlt jeden Frame.
    assert len(lines) == 1
    assert st.input_unconfigured[5] == 3


def test_app_state_module_has_no_logging():
    # Die Datei nutzt kein logging-Modul mehr (CDX-01).
    assert not hasattr(A, "_log")
    assert not hasattr(A, "logging")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

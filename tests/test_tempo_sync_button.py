"""Sync-Knopf + Auto-Sync: Effekte unterschiedlicher Geschwindigkeit sollen auf
demselben Schlag beginnen.

Behebt den Matching-Bug in TempoBus.sync() (verglich tempo_bus_id per String mit
bus_id -> der Alias "Global"/""/"default" griff nie) und ergaenzt Auto-Sync
(gemeinsamer Beat-Raster-Ursprung)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm


@pytest.fixture(autouse=True)
def _clean():
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    mgr = get_bpm_manager()
    mgr.set_locked(False)
    mgr.reset()
    get_tempo_bus_manager().set_auto_sync(False)


def _matrix(fm, name, bus_id, mult):
    m = fm.new_rgb_matrix(name)
    m.algorithm = RgbAlgorithm.CHASE
    m.tempo_bus_id = bus_id
    m.tempo_multiplier = mult
    return m


# ── Bugfix: sync() re-ankert Effekte, die ueber Alias an den Default-Bus gebunden sind ──
def test_sync_reanchors_global_alias_effects():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    fm = get_function_manager()
    tbm.ensure_bus("A")                       # echter, anderer Bus
    a = _matrix(fm, "A", "Global", 1.0); a._beat_anchor = 1.0
    b = _matrix(fm, "B", "", 0.5);       b._beat_anchor = 2.0
    c = _matrix(fm, "C", "A", 1.0);      c._beat_anchor = 3.0
    d = tbm.get("default")
    d.sync()                                  # re-ankert alle Default-Effekte auf position()
    pos = d.position()
    assert a._beat_anchor == pos, "Global-Alias nicht re-ankert (Bug)"
    assert b._beat_anchor == pos, "'' -Alias nicht re-ankert (Bug)"
    assert c._beat_anchor == 3.0, "Effekt auf anderem Bus faelschlich re-ankert"


# ── Kernbeweis: ×1 und ×0.5 beginnen nach Sync auf demselben Schlag ────────────
def test_sync_makes_different_speeds_start_together():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    a = _matrix(fm, "A", "Global", 1.0)
    b = _matrix(fm, "B", "Global", 0.5)
    a.start(); d.advance_frame(0.7); b.start(); d.advance_frame(0.7)
    a._advance_step(0.0); b._advance_step(0.0)
    assert abs(a._step - b._step) > 1e-6, "Vorbedingung: ohne Sync verschiedene Phase erwartet"
    d.sync()                                   # SYNC-Knopf
    a._advance_step(0.0); b._advance_step(0.0)
    assert abs(a._step) < 1e-6 and abs(b._step) < 1e-6, "nach Sync nicht beide am Zyklusstart"
    assert abs(a._step - b._step) < 1e-6, "nach Sync nicht auf demselben Schlag"


# ── Auto-Sync: gemeinsamer Ursprung, egal wann gestartet ───────────────────────
def test_auto_sync_shares_origin_across_time():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    tbm.set_auto_sync(True)
    d.advance_frame(0.5)
    o1 = d.take_anchor()                        # erster Effekt: legt Ursprung fest
    d.advance_frame(0.5)
    o2 = d.take_anchor()                        # spaeterer Effekt: uebernimmt Ursprung
    assert abs(o1 - o2) < 1e-9, "Auto-Sync: spaeterer Effekt nicht am gemeinsamen Ursprung"


def test_no_auto_sync_anchor_follows_position():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    d = tbm.get("default")
    tbm.set_auto_sync(False)                    # bewusste Abwahl
    a1 = d.take_anchor()
    d.advance_frame(0.5)
    a2 = d.take_anchor()
    assert a2 > a1, "ohne Auto-Sync soll der Anker der Position folgen (altes Verhalten)"


def test_auto_sync_persists_in_grandmaster_dict():
    reset_tempo_bus_manager()
    tbm = get_tempo_bus_manager()
    tbm.set_auto_sync(True)
    blob = tbm.grandmaster_to_dict()
    assert blob.get("auto_sync") is True
    tbm.set_auto_sync(False)
    tbm.load_grandmaster(blob)
    assert tbm.auto_sync is True


def test_auto_sync_button_action_exists():
    from src.ui.virtualconsole.vc_button import ButtonAction, BUTTON_ACTION_LABELS
    assert ButtonAction.AUTO_SYNC
    assert ButtonAction.AUTO_SYNC in {a for a, _ in BUTTON_ACTION_LABELS}


# ── BPM-Manager-Tab: fester Auto-Sync-Toggle + „Jetzt synchronisieren" ──────────
def test_bpm_view_auto_sync_toggle_drives_and_reflects_manager():
    reset_tempo_bus_manager()
    from src.ui.views.bpm_manager_view import BpmManagerView
    tbm = get_tempo_bus_manager()
    tbm.set_auto_sync(False)
    view = BpmManagerView()
    try:
        assert view._chk_auto_sync.isChecked() is False   # spiegelt Aus-Zustand
        view._chk_auto_sync.setChecked(True)              # User-Toggle treibt Manager
        assert tbm.auto_sync is True
        view._chk_auto_sync.setChecked(False)
        assert tbm.auto_sync is False
        # umgekehrt: Backend-Zustand wird beim Refresh gespiegelt (ohne Echo)
        tbm.set_auto_sync(True)
        view._refresh_speeds()
        assert view._chk_auto_sync.isChecked() is True
    finally:
        view.deleteLater()


def test_bpm_view_sync_now_reanchors_all_buses():
    reset_tempo_bus_manager()
    from src.ui.views.bpm_manager_view import BpmManagerView
    tbm = get_tempo_bus_manager(); fm = get_function_manager(); mgr = get_bpm_manager()
    view = BpmManagerView()
    try:
        mgr.set_manual_bpm(120.0)
        d = tbm.get("default")
        a = _matrix(fm, "A", "Global", 1.0)
        b = _matrix(fm, "B", "Global", 0.5)
        a.start(); d.advance_frame(0.7); b.start(); d.advance_frame(0.7)
        a._advance_step(0.0); b._advance_step(0.0)
        assert abs(a._step - b._step) > 1e-6, "Vorbedingung: ohne Sync verschiedene Phase"
        view._on_sync_now()                                # Button „Jetzt synchronisieren"
        a._advance_step(0.0); b._advance_step(0.0)
        assert abs(a._step) < 1e-6 and abs(b._step) < 1e-6, "sync-now: nicht beide am Zyklusstart"
    finally:
        view.deleteLater()

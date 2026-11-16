"""CDX-75 (2): Block loeschen im Show-Manager stoppt das laufende Kind.

Bis CDX-75 entfernte ``block_loeschen`` den Block nur aus der Spur. Lief er
gerade, erfasste ihn danach weder ``Show.write`` (Stop am Blockende) noch
``Show._on_stop`` — das Kind blieb als laufend markiert, ohne gerendert zu
werden (falsches Knopf-/LED-Feedback, kein Stop-Aufraeumen).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _aufraeumen():
    from src.core.undo import get_undo_stack
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    vorher = {f.id for f in fm.all()}
    get_undo_stack().clear()
    yield
    get_undo_stack().clear()
    for f in list(fm.all()):
        if f.id not in vorher:
            f.stop()
            fm.remove(f.id)
    destroy_all_top_level_widgets(_app)


def _aufbau(zweiter_block_gleiches_kind: bool = False):
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.show_engine import Show, ShowFunction
    from src.ui.views import show_manager_view as smv
    fm = get_function_manager()
    kind = fm.new_scene("CDX-75 Kind")
    show = Show("CDX-75")
    spur = show.add_track("S1")
    block = ShowFunction(function_id=kind.id, start_time=0.0, duration=10.0)
    spur.add_function(block)
    zweiter = None
    if zweiter_block_gleiches_kind:
        spur2 = show.add_track("S2")
        zweiter = ShowFunction(function_id=kind.id, start_time=0.0, duration=10.0)
        spur2.add_function(zweiter)
    show.recalc_duration()
    view = smv.ShowManagerView()
    view._load_show(show)
    # Show starten und einen Takt rechnen: der Block startet sein Kind.
    show.start()
    show.write({}, [], 0.1, {kind.id: kind})
    assert kind.is_running and block._started and not block._stopped
    return view, show, block, zweiter, kind


def test_loeschen_eines_laufenden_blocks_stoppt_das_kind():
    view, show, block, _z, kind = _aufbau()
    assert view._timeline.block_loeschen(block)
    assert not kind.is_running, "geloeschter Block laesst sein Kind weiterlaufen"
    # Rueckgaengig holt den Block zurueck, ohne das Kind wieder anzuwerfen;
    # das Show-Ende raeumt weiter sauber auf.
    from src.core.undo import get_undo_stack
    assert get_undo_stack().undo()
    assert block in show.tracks[0].show_functions
    show.write({}, [], 0.1, {kind.id: kind})
    assert not kind.is_running
    show.stop()
    assert not kind.is_running


def test_gleiches_kind_in_einem_anderen_laufenden_block_laeuft_weiter():
    view, show, block, zweiter, kind = _aufbau(zweiter_block_gleiches_kind=True)
    assert view._timeline.block_loeschen(block)
    assert kind.is_running, "der zweite Block spielt dasselbe Kind noch"
    show.stop()
    assert not kind.is_running


def test_loeschen_bei_gestoppter_show_fasst_nichts_an():
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.show_engine import Show, ShowFunction
    from src.ui.views import show_manager_view as smv
    kind = get_function_manager().new_scene("CDX-75 fremd")
    kind.start()                       # z. B. per VC-Taste, nicht ueber die Show
    show = Show("CDX-75 aus")
    block = ShowFunction(function_id=kind.id, start_time=0.0, duration=5.0)
    show.add_track("S1").add_function(block)
    view = smv.ShowManagerView()
    view._load_show(show)
    assert view._timeline.block_loeschen(block)
    assert kind.is_running

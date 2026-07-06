"""UXT-03: „Als Szene(n) übernehmen" — Brücke Snap → Szenen-Funktion.

Ein markierter Snap (``{fid:{attr:val}}``) wird über ``programmer_to_scene_values``
in eine wiederverwendbare Scene-Funktion gewandelt, die danach im Chaser-Editor
als Schritt wählbar ist (der bisher fehlende Weg von Snap zu Chaser-Baustein).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from src.core.engine.function import FunctionType


def _app():
    return QApplication.instance() or QApplication([])


def _panel(monkeypatch, snap_ids):
    """SnapFilePanel mit fester Snap-Auswahl + stumm geschalteten Dialogen."""
    from src.ui.views.snap_file_panel import SnapFilePanel
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: None))
    panel = SnapFilePanel()
    monkeypatch.setattr(panel, "_selected_snap_ids", lambda: list(snap_ids))
    return panel


def _scenes(fm):
    return [f for f in fm.all() if f.function_type == FunctionType.Scene]


def test_snap_becomes_scene(monkeypatch):
    _app()
    from src.core.engine.snap_library import get_snap_library
    from src.core.engine.function_manager import get_function_manager
    import src.ui.views.programmer_view as pv

    lib = get_snap_library(); lib.clear()
    fm = get_function_manager()
    snap = lib.add_snap("Sunset", "", {7: {"color_r": 255, "dimmer": 200}})

    # Brücke deterministisch stubben (keine echten Fixtures nötig).
    monkeypatch.setattr(pv, "programmer_to_scene_values",
                        lambda prog, fx: [(7, 1, 255), (7, 5, 200)])

    panel = _panel(monkeypatch, [snap.id])
    before = len(_scenes(fm))
    panel._create_scene_from_selection()

    scenes = [s for s in _scenes(fm) if s.name == "Sunset (Szene)"]
    assert len(scenes) == 1, "genau eine Szene aus dem Snap"
    assert len(_scenes(fm)) == before + 1
    sc = scenes[0]
    assert sc.get_value(7, 1) == 255
    assert sc.get_value(7, 5) == 200


def test_multiple_snaps_become_multiple_scenes(monkeypatch):
    _app()
    from src.core.engine.snap_library import get_snap_library
    from src.core.engine.function_manager import get_function_manager
    import src.ui.views.programmer_view as pv

    lib = get_snap_library(); lib.clear()
    fm = get_function_manager()
    a = lib.add_snap("A", "", {1: {"dimmer": 100}})
    b = lib.add_snap("B", "", {1: {"dimmer": 50}})
    monkeypatch.setattr(pv, "programmer_to_scene_values",
                        lambda prog, fx: [(1, 1, 128)])

    panel = _panel(monkeypatch, [a.id, b.id])
    panel._create_scene_from_selection()
    names = {s.name for s in _scenes(fm)}
    assert {"A (Szene)", "B (Szene)"} <= names


def test_snap_without_patched_channels_creates_nothing(monkeypatch):
    _app()
    from src.core.engine.snap_library import get_snap_library
    from src.core.engine.function_manager import get_function_manager
    import src.ui.views.programmer_view as pv

    lib = get_snap_library(); lib.clear()
    fm = get_function_manager()
    snap = lib.add_snap("Ghost", "", {99: {"dimmer": 100}})
    # Kein gepatchter Kanal -> Brücke liefert nichts -> keine Szene.
    monkeypatch.setattr(pv, "programmer_to_scene_values", lambda prog, fx: [])

    panel = _panel(monkeypatch, [snap.id])
    before = len(_scenes(fm))
    panel._create_scene_from_selection()
    assert len(_scenes(fm)) == before, "leere Brücke legt keine Szene an"


def test_empty_selection_is_noop(monkeypatch):
    _app()
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    panel = _panel(monkeypatch, [])
    before = len(_scenes(fm))
    panel._create_scene_from_selection()          # darf nicht werfen
    assert len(_scenes(fm)) == before

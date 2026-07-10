"""QA-10: CollectionEditor baut mit Minimal-Funktionen und bearbeitet die Liste."""
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from src.core.engine.collection import Collection
from src.core.engine.function import FunctionType
from src.ui.views import collection_editor as collection_ui


class _FakeFunctionManager:
    def __init__(self):
        self.functions = {
            1: SimpleNamespace(name="Scene A", function_type=FunctionType.Scene),
            2: SimpleNamespace(name="Chaser B", function_type=FunctionType.Chaser),
        }
        self.started = []
        self.stopped = []

    def get(self, fid):
        return self.functions.get(fid)

    def start(self, fid):
        self.started.append(fid)

    def stop(self, fid):
        self.stopped.append(fid)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_collection_editor_renames_reorders_removes_and_controls_members(monkeypatch):
    """Die sichtbare Reihenfolge muss die gespeicherte Collection repräsentieren."""
    _app()
    manager = _FakeFunctionManager()
    monkeypatch.setattr(collection_ui, "get_function_manager", lambda: manager)
    collection = Collection("Parallel", fid=99)
    collection.function_ids = [1, 2]
    view = collection_ui.CollectionEditor(collection)
    view.show()

    try:
        assert view._lst.count() == 2
        assert "Scene A" in view._lst.item(0).text()

        view._edit_name.setText("Parallel Neu")
        view._on_name_changed()
        assert collection.name == "Parallel Neu"

        view._lst.setCurrentRow(0)
        view._move_selected(1)
        assert collection.function_ids == [2, 1]

        view._remove_selected()
        assert collection.function_ids == [2]
        assert view._lst.count() == 1

        view._play()
        view._stop()
        assert manager.started == [99]
        assert manager.stopped == [99, 2]
    finally:
        view.close()

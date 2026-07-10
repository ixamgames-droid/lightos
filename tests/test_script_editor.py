"""QA-10: ScriptEditor bearbeitet ein Minimal-Script und steuert es."""
from PySide6.QtWidgets import QApplication

from src.core.engine.script_func import ScriptFunction
from src.ui.views import script_editor as script_ui


class _FakeFunctionManager:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, fid):
        self.started.append(fid)

    def stop(self, fid):
        self.stopped.append(fid)


def _app():
    return QApplication.instance() or QApplication([])


def test_script_editor_updates_script_and_runs_through_manager(monkeypatch):
    _app()
    manager = _FakeFunctionManager()
    monkeypatch.setattr(script_ui, "get_function_manager", lambda: manager)
    script = ScriptFunction("Cue Script", fid=12)
    view = script_ui.ScriptEditor(script)
    view.show()
    try:
        view._name_edit.setText("Cue Script Neu")
        view._editor.setPlainText("setdmx 1 4 200\nwait 0.5")
        assert script.name == "Cue Script Neu"
        assert script.script == "setdmx 1 4 200\nwait 0.5"
        assert view._highlighter.document() is view._editor.document()
        view._run()
        view._stop()
        assert manager.started == [12]
        assert manager.stopped == [12]
    finally:
        view.close()

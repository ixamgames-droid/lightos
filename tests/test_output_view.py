"""QA-10: OutputView baut headless und zeigt auch hohe Universen an."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.dmx.universe import Universe
from src.core.show.show_file import reset_show
from src.ui.views.output_view import OutputView


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_output_view_keyboard_selects_universe_32_and_refreshes_cells():
    """U32 ist im gesamten Patch gültig und muss im Monitor erreichbar sein."""
    _app()
    reset_show()
    state = get_state()
    universe = Universe(32)
    universe.set_channel(1, 173)
    state.universes[32] = universe
    view = OutputView()
    view.show()

    try:
        # Echter Tastaturpfad im QSpinBox: Pfeil hoch erreicht das obere Limit.
        view._spin_univ.setFocus()
        for _ in range(31):
            QTest.keyClick(view._spin_univ, Qt.Key.Key_Up)
        assert view._spin_univ.value() == 32
        assert len(view._cells[32]) == 512

        view._refresh()
        assert view._cells[32][0]._value == 173
    finally:
        view.close()
        reset_show()

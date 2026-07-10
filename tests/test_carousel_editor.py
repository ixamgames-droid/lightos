"""QA-10: CarouselEditor exposes the engine's color opt-in."""
from PySide6.QtWidgets import QApplication

from src.core.engine.carousel import Carousel, CarouselPattern
from src.ui.views.carousel_editor import CarouselEditor


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_carousel_editor_builds_with_color_opt_in():
    _app()
    carousel = Carousel("Pulse")
    view = CarouselEditor(carousel)
    try:
        assert not carousel.paint_color
        assert view._paint_color_chk.isChecked() is False
        view._paint_color_chk.setChecked(True)
        assert carousel.paint_color

        view._pattern_combo.setCurrentIndex(
            view._pattern_combo.findData(CarouselPattern.CHASE))
        assert carousel.pattern == CarouselPattern.CHASE

        view._fixtures_edit.setText("2, invalid, 7")
        view._apply_fixture_ids()
        assert carousel.fixture_ids == [2, 7]

        for _ in range(3):
            view._toggle_editor_popout()
            assert view._editor_window is not None
            view._toggle_editor_popout()
            assert view._editor_window is None
            assert view._editor_scroll.widget() is view._editor_body
    finally:
        view.close()

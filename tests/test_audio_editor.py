"""QA-10: AudioEditor ist headless bedienbar und übersteht Popout-Zyklen."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.engine.audio_func import AudioFunction
from src.ui.views.audio_editor import AudioEditor


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_audio_editor_edits_model_and_redocks_popout_repeatedly():
    """Zentrale Controls und das gesamte Editor-Reparenting bleiben funktionsfähig."""
    app = _app()
    audio = AudioFunction("Intro")
    audio.volume = 0.4
    view = AudioEditor(audio)
    view.show()

    try:
        view._slider_vol.setFocus()
        QTest.keyClick(view._slider_vol, Qt.Key.Key_Right)
        assert audio.volume == 0.41
        assert view._lbl_vol.text() == "41%"

        QTest.mouseClick(view._chk_loop, Qt.MouseButton.LeftButton)
        assert audio.loop is True

        view._edit_name.setFocus()
        view._edit_name.clear()
        QTest.keyClicks(view._edit_name, "Intro Neu")
        QTest.keyClick(view._edit_name, Qt.Key.Key_Return)
        assert audio.name == "Intro Neu"

        for _ in range(3):
            QTest.mouseClick(view._btn_editor_popout, Qt.MouseButton.LeftButton)
            app.processEvents()
            assert view._editor_window is not None
            assert view._editor_placeholder.isVisible()

            QTest.mouseClick(view._btn_editor_popout, Qt.MouseButton.LeftButton)
            app.processEvents()
            assert view._editor_window is None
            assert view._editor_scroll.widget() is view._editor_body
    finally:
        view.close()

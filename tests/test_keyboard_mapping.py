"""Tests für das VC-Keyboard-Mapping (Feature 8).

Abdeckung:
- sequence_from_event: Sequenz-Strings inkl. Modifier, reine Modifier = None
- KeyboardHotkeyFilter: Dispatch, Textfeld-Schutz, Release-Zustellung
- VCButton: handle_key (Toggle-/Flash-Semantik), Serialisierungs-Roundtrip
- VCCanvas: key_binding_owners (Konfliktprüfung)
"""
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from src.core.input.keyboard_hotkeys import (KeyboardHotkeyFilter,
                                             _is_text_input,
                                             sequence_from_event)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def key_event(key, mods=Qt.KeyboardModifier.NoModifier,
              etype=QEvent.Type.KeyPress, autorep=False):
    return QKeyEvent(etype, key, mods, "", autorep)


class TestSequenceFromEvent:
    def test_plain_key(self):
        assert sequence_from_event(key_event(Qt.Key.Key_B)) == "B"

    def test_function_key(self):
        assert sequence_from_event(key_event(Qt.Key.Key_F5)) == "F5"

    def test_with_ctrl(self):
        seq = sequence_from_event(
            key_event(Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier))
        assert seq == "Ctrl+B"

    def test_with_ctrl_shift(self):
        seq = sequence_from_event(
            key_event(Qt.Key.Key_F5, Qt.KeyboardModifier.ControlModifier
                      | Qt.KeyboardModifier.ShiftModifier))
        assert "Ctrl" in seq and "Shift" in seq and "F5" in seq

    def test_pure_modifier_returns_none(self):
        assert sequence_from_event(key_event(Qt.Key.Key_Control)) is None
        assert sequence_from_event(key_event(Qt.Key.Key_Shift)) is None


class TestTextInputDetection:
    def test_line_edit_is_text_input(self):
        w = QLineEdit()
        assert _is_text_input(w) is True

    def test_none_is_not(self):
        assert _is_text_input(None) is False


class TestHotkeyFilter:
    def test_dispatch_press_and_release(self):
        f = KeyboardHotkeyFilter()
        got = []
        f.subscribe(lambda seq, pressed: got.append((seq, pressed)) or True)
        ev = key_event(Qt.Key.Key_F6)
        assert f.eventFilter(None, ev) is True   # konsumiert
        rel = key_event(Qt.Key.Key_F6, etype=QEvent.Type.KeyRelease)
        f.eventFilter(None, rel)
        assert got == [("F6", True), ("F6", False)]

    def test_release_uses_press_sequence_even_without_modifier(self):
        """Modifier zuerst losgelassen → Release liefert trotzdem 'Ctrl+B'."""
        f = KeyboardHotkeyFilter()
        got = []
        f.subscribe(lambda seq, pressed: got.append((seq, pressed)) or True)
        f.eventFilter(None, key_event(Qt.Key.Key_B,
                                      Qt.KeyboardModifier.ControlModifier))
        # Release OHNE Ctrl (Nutzer hat Strg zuerst losgelassen)
        f.eventFilter(None, key_event(Qt.Key.Key_B,
                                      etype=QEvent.Type.KeyRelease))
        assert got == [("Ctrl+B", True), ("Ctrl+B", False)]

    def test_unconsumed_key_not_blocked(self):
        f = KeyboardHotkeyFilter()
        f.subscribe(lambda seq, pressed: False)  # niemand will die Taste
        assert f.eventFilter(None, key_event(Qt.Key.Key_X)) is False

    def test_autorepeat_swallowed_for_active_key(self):
        f = KeyboardHotkeyFilter()
        got = []
        f.subscribe(lambda seq, pressed: got.append((seq, pressed)) or True)
        f.eventFilter(None, key_event(Qt.Key.Key_F7))
        # Auto-Repeat-Press darf NICHT erneut dispatchen
        assert f.eventFilter(None, key_event(Qt.Key.Key_F7, autorep=True)) is True
        assert got == [("F7", True)]

    def test_no_subscribers_passthrough(self):
        f = KeyboardHotkeyFilter()
        assert f.eventFilter(None, key_event(Qt.Key.Key_A)) is False


class TestVCButtonKeyBinding:
    def _button(self):
        from src.ui.virtualconsole.vc_button import VCButton
        return VCButton()

    def test_default_no_binding(self):
        b = self._button()
        assert b.current_key_binding() == ""
        assert b.handle_key("F5", True) is False

    def test_apply_and_match(self):
        b = self._button()
        b.apply_key_binding("Ctrl+F5")
        assert b.current_key_binding() == "Ctrl+F5"
        assert b.handle_key("Ctrl+F5", True) is True
        assert b.handle_key("F5", True) is False

    def test_press_release_sets_pressed_state(self):
        b = self._button()
        b.apply_key_binding("B")
        b.handle_key("B", True)
        assert b._pressed is True
        b.handle_key("B", False)
        assert b._pressed is False

    def test_serialization_roundtrip(self):
        from src.ui.virtualconsole.vc_button import VCButton
        b = self._button()
        b.apply_key_binding("Shift+F2")
        d = b.to_dict()
        assert d["key_binding"] == "Shift+F2"
        b2 = VCButton()
        b2.apply_dict(d)
        assert b2.current_key_binding() == "Shift+F2"

    def test_remove_binding(self):
        b = self._button()
        b.apply_key_binding("F3")
        b.apply_key_binding("")
        assert b.current_key_binding() == ""
        assert b.handle_key("F3", True) is False

    def test_supports_key_teach(self):
        assert self._button().supports_key_teach() is True


class TestCanvasConflicts:
    def test_key_binding_owners(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_button import VCButton
        canvas = VCCanvas()
        try:
            b1 = VCButton(parent=canvas)
            b1.caption = "Blackout"
            b1.apply_key_binding("F12")
            b2 = VCButton(parent=canvas)
            b2.caption = "Strobe"
            owners = canvas.key_binding_owners("F12")
            assert owners == ["Blackout"]
            # exclude-Filter (eigenes Widget zählt nicht als Konflikt)
            assert canvas.key_binding_owners("F12", exclude=b1) == []
            assert canvas.key_binding_owners("F1") == []
        finally:
            canvas._teardown_midi()
            canvas._teardown_keyboard()
            canvas.deleteLater()

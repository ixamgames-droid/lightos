"""Smoke-test the full-editor popout/redock cycle for an editor widget.

Constructs the widget, calls _toggle_editor_popout() (or the editor's popout
toggle), verifies the editor body actually moved into a separate window, then
redocks and verifies it came back — catching reparenting/takeWidget crashes.

Usage:
    python docs/_walkthrough/smoke_popout.py <target>
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication

# reuse the same factory as the render harness
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_editor import build


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "efx"
    app = QApplication.instance() or QApplication(sys.argv)
    w = build(target)
    w.resize(700, 640)
    w.show()
    app.processEvents()

    if not hasattr(w, "_toggle_editor_popout"):
        print(f"{target}: NO _toggle_editor_popout method")
        return 2

    # open
    w._toggle_editor_popout()
    app.processEvents()
    win = getattr(w, "_editor_window", None)
    if win is None:
        print(f"{target}: FAIL — popout window not created")
        return 1
    body_in_win = win.isVisible() and len(win.findChildren(object)) > 0
    placeholder_shown = getattr(w, "_editor_placeholder", None) is not None and \
        w._editor_placeholder.isVisible()
    # Mechanism-agnostic "body moved out" check: either the Matrix _editor_scroll
    # is now empty, or (ColorPicker) the reparented _tabs no longer sits in self.
    inline_scroll = getattr(w, "_editor_scroll", None)
    if inline_scroll is not None:
        moved_out = inline_scroll.widget() is None
    else:
        tabs = getattr(w, "_tabs", None)
        moved_out = tabs is not None and tabs.window() is win

    # close -> redock
    win.close()
    app.processEvents()
    redocked = getattr(w, "_editor_window", "x") is None
    if inline_scroll is not None:
        body_back = inline_scroll.widget() is not None
    else:
        tabs = getattr(w, "_tabs", None)
        body_back = tabs is not None and tabs.window() is w.window()

    ok = body_in_win and moved_out and placeholder_shown and redocked and body_back
    print(f"{target}: popout_visible={body_in_win} moved_out={moved_out} "
          f"placeholder={placeholder_shown} redocked={redocked} body_back={body_back} "
          f"=> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

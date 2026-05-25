"""Layout-State Persistenz pro Show."""
from __future__ import annotations


def collect_layout(main_window) -> dict:
    """Sammelt aktuellen Layout-State."""
    data = {}
    try:
        data["window"] = {
            "width": main_window.width(),
            "height": main_window.height(),
            "x": main_window.x(),
            "y": main_window.y(),
            "maximized": main_window.isMaximized(),
        }
    except Exception as e:
        print(f"[layout_state] collect window error: {e}")
    try:
        data["current_section"] = main_window._stack.currentIndex()
    except Exception as e:
        print(f"[layout_state] collect section error: {e}")
    try:
        # Sub-Tab-Indizes pro Sektion
        sub_tabs = {}
        for i in range(main_window._stack.count()):
            w = main_window._stack.widget(i)
            if hasattr(w, "currentIndex"):
                try:
                    sub_tabs[str(i)] = w.currentIndex()
                except Exception:
                    continue
        data["sub_tabs"] = sub_tabs
    except Exception as e:
        print(f"[layout_state] collect sub_tabs error: {e}")
    return data


def apply_layout(main_window, data: dict):
    """Wendet gespeicherten Layout-State an."""
    if not data:
        return
    try:
        w = data.get("window", {})
        if w:
            if w.get("maximized"):
                main_window.showMaximized()
            else:
                main_window.resize(w.get("width", 1400), w.get("height", 900))
                main_window.move(w.get("x", 100), w.get("y", 100))
    except Exception as e:
        print(f"[layout_state] apply window error: {e}")
    try:
        idx = data.get("current_section")
        if isinstance(idx, int) and 0 <= idx < main_window._stack.count():
            main_window._stack.setCurrentIndex(idx)
            if hasattr(main_window, "_section_btns") and idx < len(main_window._section_btns):
                main_window._section_btns[idx].setChecked(True)
    except Exception as e:
        print(f"[layout_state] apply section error: {e}")
    try:
        sub_tabs = data.get("sub_tabs", {})
        for k, v in sub_tabs.items():
            try:
                sect_idx = int(k)
                tab_idx = int(v)
                w = main_window._stack.widget(sect_idx)
                if hasattr(w, "setCurrentIndex"):
                    w.setCurrentIndex(tab_idx)
            except Exception:
                continue
    except Exception as e:
        print(f"[layout_state] apply sub_tabs error: {e}")

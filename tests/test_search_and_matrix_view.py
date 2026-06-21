"""F-1: Such-/Filterfeld in Paletten + Programmer-Gruppen; Gruppenklick öffnet
direkt die Matrix-Ansicht."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidgetItem
from PySide6.QtCore import Qt

from src.core.engine.palette import PaletteType
import src.ui.views.palette_view as PV


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── F-1 (a): Paletten-Suchfeld ────────────────────────────────────────────────

class _FakePalette:
    def __init__(self, name, folder="", ptype=PaletteType.COLOR):
        self.name = name
        self.folder = folder
        self.type = ptype
        self.values = {"color_r": 180, "color_g": 120, "color_b": 60}


class _FakeManager:
    def __init__(self, palettes):
        self._palettes = list(palettes)

    def get_by_type(self, ptype):
        return list(self._palettes)


# Rendering ueber einen Recorder pruefen statt ueber Qt-Widget-Lebenszeit:
# _refresh() instanziiert pro sichtbarer Palette genau einen PaletteButton.
# Das vermeidet deleteLater/sendPostedEvents — Letzteres wuerde app-weit
# Alt-Objekte anderer Tests anfassen und die Gesamt-Suite zum Absturz bringen.
_rendered: list[str] = []


class _RecordingButton(PV.PaletteButton):
    def __init__(self, palette, parent=None):
        _rendered.append(palette.name)
        super().__init__(palette, parent)


def _names(page, search_text) -> list[str]:
    page._search.setText(search_text)
    _rendered.clear()
    page._refresh()
    return sorted(_rendered)


def test_palette_search_filters_by_name_and_folder(monkeypatch):
    _app()
    monkeypatch.setattr(PV, "PaletteButton", _RecordingButton)
    page = PV.PalettePage(PaletteType.COLOR, _FakeManager([
        _FakePalette("Rot Warm"),
        _FakePalette("Blau Kalt"),
        _FakePalette("Gruen", folder="Buehne"),
    ]))
    assert _names(page, "") == ["Blau Kalt", "Gruen", "Rot Warm"]
    assert _names(page, "rot") == ["Rot Warm"]
    # Der Ordnername zählt ebenfalls als Treffer.
    assert _names(page, "buehne") == ["Gruen"]
    assert _names(page, "") == ["Blau Kalt", "Gruen", "Rot Warm"]


# ── F-1 (b): Gruppenklick öffnet Matrix + Gruppen-Suchfeld ────────────────────

def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def test_group_click_opens_matrix_tab(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    view = ProgrammerView()
    # Matrix-Tab-Index ist gemerkt und zeigt wirklich auf die Matrix-Seite.
    assert view._matrix_tab_index >= 0
    assert view._main_tabs.tabText(view._matrix_tab_index) == "Matrix"

    # Auf einen anderen Tab stellen, dann eine Gruppe (kein Ordner) anklicken.
    view._main_tabs.setCurrentIndex(0)
    item = QListWidgetItem("Gruppe X")
    item.setData(Qt.ItemDataRole.UserRole, [])        # fids
    item.setData(Qt.ItemDataRole.UserRole + 1, 1)     # gid
    view._on_group_clicked(item)
    assert view._main_tabs.currentIndex() == view._matrix_tab_index


def test_folder_header_click_does_not_switch_tab(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    view = ProgrammerView()
    view._main_tabs.setCurrentIndex(0)
    header = QListWidgetItem("📁 Ordner")
    header.setData(Qt.ItemDataRole.UserRole + 2, "Ordner")   # Ordner-Kopfzeile
    view._on_group_clicked(header)
    assert view._main_tabs.currentIndex() == 0               # kein Tab-Wechsel


def test_group_search_field_triggers_refresh(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView

    view = ProgrammerView()
    assert hasattr(view, "_group_search")
    calls = []
    view._refresh_group_list = lambda: calls.append(1)   # vom Lambda zur Laufzeit aufgelöst
    view._group_search.setText("egal")
    assert calls, "textChanged des Gruppen-Suchfelds muss _refresh_group_list auslösen"

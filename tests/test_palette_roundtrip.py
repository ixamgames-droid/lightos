"""QA-LIVE: Palette im echten Qt-Workflow aufzeichnen, anwenden und persistieren.

Der Test deckt den verbliebenen Paletten-Klickpfad aus dem Verifikationsplan ab:
eine Color-Palette wird aus der Auswahl aufgezeichnet, ihr Button wird wirklich
geklickt und die Werte einer zweiten Spider-Farb-Bank muessen anschliessend auch
nach Save/Load noch vorhanden sein.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.database.fixture_db import engine as fixture_engine
from src.core.database.models import FixtureProfile, PatchedFixture
from src.core.engine.palette import PaletteType, get_palette_manager
from src.core.show.show_file import load_show, reset_show, save_show
from src.ui.views import palette_view as palette_ui


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _profile_id(short_name: str) -> int:
    with Session(fixture_engine()) as session:
        return int(session.execute(
            select(FixtureProfile.id).where(FixtureProfile.short_name == short_name)
        ).scalar_one())


def _color_page(view: palette_ui.PaletteView) -> palette_ui.PalettePage:
    return next(page for page in view._pages if page.ptype == PaletteType.COLOR)


def test_record_click_apply_and_show_roundtrip_preserves_multihead_palette(
        tmp_path, monkeypatch):
    """Der UI-Button muss beide Spider-Baenke aufzeichnen und wiederherstellen."""
    _app()
    reset_show()
    manager = get_palette_manager()
    manager.from_dict({})
    state = get_state()
    state.add_fixture(PatchedFixture(
        fid=1, label="Spider", fixture_profile_id=_profile_id("SPIDER14"),
        mode_name="14-Kanal", universe=1, address=1, channel_count=14,
        manufacturer_name="U King", fixture_name="Spider 14ch",
        fixture_type="moving_head"), undoable=False)
    state._rebuild_render_plan()
    state.set_selected_fids([1])
    state.set_programmer_value(1, "color_r", 210)
    state.set_programmer_value(1, "color_g", 25)
    state.set_programmer_value(1, "color_r", 70, head=1)
    state.set_programmer_value(1, "color_g", 180, head=1)
    # Darf nicht als Color-Palette gespeichert werden.
    state.set_programmer_value(1, "dimmer", 255)

    view = palette_ui.PaletteView()
    view.show()
    page = _color_page(view)
    monkeypatch.setattr(
        palette_ui.QInputDialog, "getText",
        staticmethod(lambda *_args, **_kwargs: ("Spider zweifarbig", True)),
    )

    try:
        page._record_new()
        palette = manager.find("Spider zweifarbig")
        assert palette is not None
        assert palette.fixture_values[1] == {
            "color_r": 210, "color_g": 25,
            "color_r#1": 70, "color_g#1": 180,
        }

        state.clear_programmer()
        button = next(button for button in page.findChildren(palette_ui.PaletteButton)
                      if button.palette is palette)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert state.programmer[1] == {
            "color_r": 210, "color_g": 25,
            "color_r#1": 70, "color_g#1": 180,
        }

        path = tmp_path / "palette-roundtrip.lshow"
        save_show(path)
        assert path.exists()
        reset_show()
        ok, message = load_show(path)
        assert ok, message

        restored = manager.find("Spider zweifarbig")
        assert restored is not None
        assert restored.fixture_values[1] == palette.fixture_values[1]
        # SHOW_LOADED/REFRESH_ALL muss die offene Palette-Ansicht wirklich erneuern.
        assert any(button.palette.name == "Spider zweifarbig"
                   for button in page.findChildren(palette_ui.PaletteButton))
    finally:
        view.close()
        manager.from_dict({})
        reset_show()

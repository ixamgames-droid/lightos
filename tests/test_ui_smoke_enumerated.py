"""Enumerierender Headless-Smoke fuer Views und Virtual-Console-Widgets.

QA-09/QA-10: Ein Einzel-Smoke pro handverlesener View wird schnell unvollstaendig.
Dieses Modul inventarisiert deshalb alle no-arg ``*View``-Klassen direkt aus
``src.ui.views``. Eine neue oder umbenannte no-arg View macht den Inventar-Test
rot, bis sie bewusst in die Smoke-Liste aufgenommen wurde. Editoren mit einem
fachlichen Pflichtobjekt erhalten jeweils ein minimales reales Objekt.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from src.ui import views


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# Nur oeffentliche, direkt navigierbare no-arg Views. Helfer-Widgets (z. B.
# DmxGrid, TimelineCanvas) und Editoren mit Pflichtobjekt gehoeren bewusst nicht
# in dieses Inventar; die acht bisher ungetesteten Editoren stehen weiter unten.
PUBLIC_NO_ARG_VIEWS = {
    "audio_input_view": "AudioInputView",
    "bpm_generator_view": "BpmGeneratorView",
    "bpm_manager_view": "BpmManagerView",
    "channel_groups_view": "ChannelGroupsView",
    "curve_library_view": "CurveLibraryView",
    "dmx_monitor_view": "DmxMonitorView",
    "efx_view": "EfxView",
    "fixture_group_view": "FixtureGroupView",
    "function_manager_view": "FunctionManagerView",
    "laser_view": "LaserView",
    "live_view": "LiveView",
    "midi_view": "MidiView",
    "music_view": "MusicView",
    "output_view": "OutputView",
    "palette_view": "PaletteView",
    "patch_view": "PatchView",
    "playback_view": "PlaybackView",
    "preset_browser_view": "PresetBrowserView",
    "programmer_view": "ProgrammerView",
    "rgb_matrix_view": "RgbMatrixView",
    "show_manager_view": "ShowManagerView",
    "simple_desk": "SimpleDeskView",
    "snapshots_view": "SnapshotsView",
    "virtual_console_view": "VirtualConsoleView",
}


def _required_init_args(cls: type[QWidget]) -> list[inspect.Parameter]:
    """Gibt Pflichtargumente ausser ``self`` zurueck."""
    return [
        param for param in inspect.signature(cls).parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]


def _discover_no_arg_views() -> dict[str, str]:
    found: dict[str, str] = {}
    for info in pkgutil.iter_modules(views.__path__):
        if info.name.startswith("_"):
            continue
        module_name = f"{views.__name__}.{info.name}"
        module = importlib.import_module(module_name)
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if (
                cls.__module__ == module_name
                and name.endswith("View")
                and not name.startswith("_")
                and issubclass(cls, QWidget)
                and not _required_init_args(cls)
            ):
                found[info.name] = name
    return found


def _destroy(widget: QWidget) -> None:
    widget.close()
    widget.deleteLater()
    _app().processEvents()


def test_no_arg_view_inventory_is_complete():
    """Neue/umbenannte navigierbare Views brauchen einen expliziten Smoke-Eintrag."""
    assert _discover_no_arg_views() == PUBLIC_NO_ARG_VIEWS


@pytest.mark.parametrize("module_name,class_name", PUBLIC_NO_ARG_VIEWS.items())
def test_every_no_arg_view_builds(module_name: str, class_name: str):
    _app()
    view_cls = getattr(importlib.import_module(f"{views.__name__}.{module_name}"), class_name)
    widget = view_cls()
    try:
        assert isinstance(widget, QWidget)
    finally:
        _destroy(widget)


def test_every_virtual_console_widget_roundtrips():
    """Alle registrierten VC-Widgets muessen ihre Konfiguration lesen/schreiben."""
    _app()
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY

    for type_name, widget_cls in WIDGET_REGISTRY.items():
        widget = widget_cls()
        restored = widget_cls()
        try:
            data = widget.to_dict()
            restored.apply_dict(data)
            assert isinstance(restored.to_dict(), dict), type_name
        finally:
            _destroy(restored)
            _destroy(widget)


def _audio_editor():
    from src.core.engine.audio_func import AudioFunction
    from src.ui.views.audio_editor import AudioEditor
    return AudioEditor(AudioFunction())


def _carousel_editor():
    from src.core.engine.carousel import Carousel
    from src.ui.views.carousel_editor import CarouselEditor
    return CarouselEditor(Carousel())


def _collection_editor():
    from src.core.engine.collection import Collection
    from src.ui.views.collection_editor import CollectionEditor
    return CollectionEditor(Collection())


def _effect_layer_editor():
    from src.core.engine.effect_func import LayeredEffect
    from src.ui.views.effect_layer_editor import EffectLayerEditor
    return EffectLayerEditor(LayeredEffect())


def _scene_editor():
    from src.core.engine.scene import Scene
    from src.ui.views.scene_editor import SceneEditor
    return SceneEditor(Scene())


def _script_editor():
    from src.core.engine.script_func import ScriptFunction
    from src.ui.views.script_editor import ScriptEditor
    return ScriptEditor(ScriptFunction())


@pytest.mark.parametrize(
    "factory,central_attr",
    [
        (_audio_editor, "_edit_path"),
        (_carousel_editor, "_pattern_combo"),
        (_collection_editor, "_lst"),
        (_effect_layer_editor, "_list"),
        (lambda: __import__("src.ui.views.midi_view", fromlist=["MidiView"]).MidiView(), "_map_table"),
        (lambda: __import__("src.ui.views.output_view", fromlist=["OutputView"]).OutputView(), "_grid_layout"),
        (_scene_editor, "_table"),
        (_script_editor, "_editor"),
    ],
)
def test_previously_uncovered_editor_builds(factory, central_attr: str):
    """QA-10: Jeder zuvor ungetestete Editor hat ein echtes Kern-Widget."""
    _app()
    widget = factory()
    try:
        assert getattr(widget, central_attr) is not None
    finally:
        _destroy(widget)

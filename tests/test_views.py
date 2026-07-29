"""Headless smoke tests for key UI views/widgets."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_widget, destroy_all_top_level_widgets  # XPLAT-14


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _drop_view(view, app: QApplication) -> None:
    """View schliessen UND wirklich abbauen.

    Ein nur ``close()``-ter VirtualConsoleView bleibt am Leben: sein
    400-ms-Statusticker, die MIDI-Abos und der Canvas haengen weiter in
    ``QApplication.allWidgets()``. Ueber eine Testdatei summiert sich das und
    macht den nativen Qt-Abbau am Suite-Ende messbar instabiler
    (Windows/Py3.11: STATUS_HEAP_CORRUPTION).

    XPLAT-14: hier stand ``close(); deleteLater(); processEvents()`` — das wollte
    deterministisch abraeumen und tat es nicht, weil ``processEvents()``
    ``DeferredDelete`` nicht zustellt. Die Views ueberlebten also samt Ticker und
    Abos, und auf Linux starb der Prozess beim finalen Abbau mit Exitcode 139,
    nachdem alle Tests bestanden hatten. Der geteilte Helfer erzwingt die
    Zustellung; Herleitung in ``tests/_qt_lifecycle.py``.
    """
    destroy_widget(view, app)


@pytest.fixture(autouse=True)
def _no_leaked_views():
    """XPLAT-14: nach JEDEM Test alle uebrig gebliebenen Top-Level-Widgets abbauen.

    Der explizite ``_drop_view``-Aufruf deckte nur 5 der 13 View-Erzeugungen in
    dieser Datei ab — ``test_core_views_smoke`` allein liess vier Views stehen.
    Eine Fixture statt acht Einzelaufrufe, damit auch kuenftige Tests hier nicht
    zurueckfallen koennen: die Invariante steht an einer Stelle, nicht in der
    Disziplin des naechsten Autors.
    """
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def test_virtualconsole_widgets_and_canvas():
    _app()
    from src.ui.virtualconsole import (
        VCButton, VCSlider, VCXYPad, VCLabel,
        VCCueList, VCSpeedDial, VCFrame, VCCanvas,
    )

    VCButton()
    VCSlider()
    VCXYPad()
    VCLabel()
    VCCueList()
    VCSpeedDial()
    VCFrame()
    canvas = VCCanvas()

    canvas._add_widget("VCButton", QPoint(10, 10))
    dumped = canvas.to_dict()
    assert len(dumped["widgets"]) == 1


def test_virtualconsole_bank_assignment():
    _app()
    from src.ui.virtualconsole import VCCanvas

    canvas = VCCanvas()
    # Neu angelegtes Widget landet auf der aktiven Bank.
    canvas.set_active_bank(0)
    w0 = canvas._add_widget("VCButton", QPoint(0, 0))
    assert w0.bank == 0
    canvas.set_active_bank(1)
    w1 = canvas._add_widget("VCButton", QPoint(0, 0))
    assert w1.bank == 1

    # Aktiv = Bank 1: nur w1 ist auf der Bank / sichtbar.
    assert canvas.on_active_bank(w1) is True
    assert canvas.on_active_bank(w0) is False
    assert w1.isVisibleTo(canvas) is True
    assert w0.isVisibleTo(canvas) is False

    # Bank-Wechsel dreht die Sichtbarkeit um.
    canvas.set_active_bank(0)
    assert canvas.on_active_bank(w0) is True
    assert canvas.on_active_bank(w1) is False

    # "Alle Banks" (-1) ist auf jeder Bank aktiv.
    w0._set_bank(-1)
    canvas.set_active_bank(7)
    assert canvas.on_active_bank(w0) is True


def test_virtualconsole_bank_roundtrip():
    _app()
    from src.ui.virtualconsole import VCCanvas
    from src.ui.virtualconsole.vc_widget import VCWidget

    canvas = VCCanvas()
    canvas.set_active_bank(2)
    canvas._add_widget("VCButton", QPoint(5, 5))      # -> Bank 2
    canvas._add_widget("VCLabel", QPoint(9, 9))       # -> Bank 2
    d = canvas.to_dict()
    assert all(w["bank"] == 2 for w in d["widgets"])

    canvas2 = VCCanvas()
    canvas2.from_dict(d)
    banks = [c.bank for c in canvas2.findChildren(VCWidget)]
    assert banks and all(b == 2 for b in banks)


def test_core_views_smoke():
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView
    from src.ui.views.simple_desk import SimpleDeskView
    from src.ui.views.efx_view import EfxView
    from src.ui.views.rgb_matrix_view import RgbMatrixView

    VirtualConsoleView()

    desk = SimpleDeskView()
    assert len(desk._faders) == 512

    # EFX/RGB-Matrix sind echte Funktionen im (geteilten) FunctionManager-
    # Singleton; daher Delta statt Absolutwert pruefen.
    efx = EfxView()
    n0 = len(efx._instances)
    efx._add_efx()
    assert len(efx._instances) == n0 + 1

    rgb = RgbMatrixView()
    m0 = len(rgb._instances)
    rgb._add()
    assert len(rgb._instances) == m0 + 1


def test_qxf_import_dialog_smoke():
    _app()
    from src.ui.widgets.qxf_import_dialog import QxfImportDialog

    QxfImportDialog()


def test_virtualconsole_popout_then_edit_no_crash():
    """Regression: Popout auf/zu darf den Canvas nicht zerstoeren, sonst kracht
    der naechste 'Bearbeiten'-Klick (VCCanvas already deleted)."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v._popout_canvas()
    assert v._popout_window is not None
    v._popout_window.close()                 # closeEvent -> Canvas zurueck
    assert v._canvas_alive()                 # Canvas lebt noch

    # Bearbeiten + Widget hinzufuegen funktioniert nach dem Popout-Zyklus.
    v._btn_edit.setChecked(True)
    v._add_widget("VCButton")
    assert len(v.to_dict()["widgets"]) == 1

    # Mehrfaches Popout auf/zu bleibt stabil.
    v._popout_canvas(); v._popout_window.close()
    v._popout_canvas(); v._popout_window.close()
    assert v._canvas_alive()


def test_virtualconsole_canvas_fills_wide_viewport():
    """Regression: Der 1200px-Minimum-Canvas darf auf einem breiten Touchscreen
    nicht starr 1200px bleiben und rechts eine unbenutzbare schwarze Flaeche
    erzeugen.

    Geprueft wird die WIRKUNG (Canvas fuellt den Viewport), nicht das Mittel:
    ``setWidgetResizable(True)`` ist hier bewusst NICHT erlaubt, weil es den
    Popout-Wechsel desselben Canvas zwischen zwei QScrollAreas destabilisiert
    (Windows/Py3.11: STATUS_HEAP_CORRUPTION im Teardown). Stattdessen waechst
    ``GrowingScrollArea`` den Inhalt selbst mit.
    """
    app = _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v.resize(1800, 900)
    v.show()
    app.processEvents()

    assert v._main_scroll.widgetResizable() is False, (
        "widgetResizable=True bricht den Popout-Wechsel (Heap-Corruption)")
    assert v._canvas.width() >= v._main_scroll.viewport().width()
    # Mindestgroesse bleibt erhalten -> kleine Fenster bleiben scrollbar.
    assert v._canvas.width() >= 1200

    v._popout_canvas()
    app.processEvents()
    assert v._pop_scroll is not None
    assert v._pop_scroll.widgetResizable() is False
    assert v._canvas.width() >= v._pop_scroll.viewport().width()
    v._popout_window.close()
    _drop_view(v, app)


def test_virtualconsole_canvas_stays_scrollable_on_small_window():
    """Gegenprobe: unter 1200x800 darf der Canvas NICHT schrumpfen — sonst
    waeren Widgets am rechten/unteren Rand unerreichbar statt scrollbar."""
    app = _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v.resize(900, 600)
    v.show()
    app.processEvents()

    assert v._canvas.width() >= 1200
    assert v._canvas.height() >= 800
    _drop_view(v, app)


def test_vc_widget_beyond_base_area_stays_scrollable():
    """Portabilitaet: ein auf dem breiten Touchscreen jenseits von 1200 px
    abgelegtes Widget muss auf einem KLEINEN Fenster erscrollbar bleiben.

    Sonst ist es dort weder sichtbar noch erreichbar (die QScrollArea kennt als
    Scrollweg nur die Mindestgroesse des Inhalts) — die auf Linux gebaute VC
    waere auf dem Windows-Laptop halb unbedienbar.
    """
    app = _app()
    from PySide6.QtCore import QPoint
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v.resize(1800, 900)
    v.show()
    app.processEvents()

    w = v._canvas._add_widget("VCButton", QPoint(1560, 120))
    assert w is not None
    app.processEvents()

    # Fenster schrumpfen (Laptop/Beamer) -> Canvas darf NICHT unter die
    # rechte Kante des Widgets fallen.
    v.resize(1000, 700)
    app.processEvents()
    assert v._canvas.width() >= w.geometry().right(), (
        "Widget jenseits 1200 px ist nicht mehr erscrollbar")
    _drop_view(v, app)


def test_virtualconsole_sidebar_detects_in_place_function_move():
    """Regression: Eine Funktion wird erst angelegt und danach benannt/in einen
    Ordner verschoben. Auch ohne zweites FUNCTION_CHANGED muss die VC den
    geaenderten Katalog beim naechsten 400-ms-Abgleich neu einlesen."""
    _app()
    from src.core.engine.function_manager import get_function_manager
    from src.ui.views.virtual_console_view import VirtualConsoleView

    fm = get_function_manager()
    effect = fm.new_chaser("Strobe")
    view = VirtualConsoleView()
    try:
        view._update_active_fx()  # Ausgangssignatur merken
        refreshes = []
        view._sidebar.refresh_functions = lambda: refreshes.append(True)

        # Absichtlich KEIN Sync-Event: exakt der bisher haengende Editor-Pfad.
        effect.folder = "Hintergrund/Dimmer"
        view._update_active_fx()

        assert refreshes == [True]
        assert any(row[2] == "Hintergrund/Dimmer"
                   for row in view._last_function_catalog_signature)
    finally:
        fm.remove(effect.id)
        _drop_view(view, _app())


def test_virtualconsole_refreshes_library_when_tab_becomes_visible():
    app = _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    view = VirtualConsoleView()
    refreshes = []
    view._sidebar.refresh = lambda: refreshes.append(True)
    view.show()
    app.processEvents()

    assert refreshes
    _drop_view(view, app)


def test_virtualconsole_tab_switch_without_changes_keeps_library():
    """Gegenprobe zum Vorherigen: ohne Katalog-Aenderung darf der Tabwechsel den
    Bibliotheksbaum NICHT neu bauen — sonst geht bei jedem kurzen Blick in eine
    andere Ansicht die Auswahl und die Scrollposition verloren."""
    app = _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    view = VirtualConsoleView()
    view.show()
    app.processEvents()

    refreshes = []
    view._sidebar.refresh = lambda: refreshes.append(True)
    view.hide()
    view.show()                       # Tabwechsel hin und zurueck
    app.processEvents()

    assert refreshes == [], "Bibliothek wurde ohne Aenderung neu aufgebaut"
    _drop_view(view, app)


def test_toolbar_add_cascades_and_selects():
    """UXT-06: Zwei Toolbar-Klicks legen VERSETZTE Widgets an (nicht deckungs-
    gleich in der Mitte) und wählen das jeweils neue aus."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    selected = []
    v._canvas.widget_selected.connect(lambda w: selected.append(w))
    v._btn_edit.setChecked(True)

    v._add_widget("VCButton")
    v._add_widget("VCButton")
    v._add_widget("VCButton")

    widgets = v.to_dict()["widgets"]
    assert len(widgets) == 3
    positions = {(w["x"], w["y"]) for w in widgets}
    assert len(positions) == 3, f"Widgets überlappen: {positions}"

    # Jeder Add wählt das neue Widget aus (Inspector-Bindung).
    assert selected and selected[-1] is not None

    # Kaskade startet je Bearbeiten-Sitzung neu.
    v._btn_edit.setChecked(False)
    v._btn_edit.setChecked(True)
    assert v._add_cascade == 0


def test_toolbar_add_cascade_wraps_on_canvas():
    """UXT-06: Die Kaskade wächst nicht endlos aus dem Canvas — nach `span`
    Stufen fängt sie wieder vorn an, alle Positionen bleiben >= 0."""
    _app()
    from src.ui.views.virtual_console_view import VirtualConsoleView

    v = VirtualConsoleView()
    v._btn_edit.setChecked(True)
    for _ in range(20):
        v._add_widget("VCButton")
    for w in v.to_dict()["widgets"]:
        assert w["x"] >= 0 and w["y"] >= 0

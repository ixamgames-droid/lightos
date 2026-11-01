"""VIZ-76: „Position & Ausrichtung" ohne gewaehltes Geraet.

Vorher standen ohne Auswahl der Startwert Y 6.50 oder die Werte des zuletzt
gewaehlten Geraets in AKTIVEN Feldern — leicht fuer die Lage eines Geraets zu
halten. Jetzt: ohne Auswahl ist der Bereich gesperrt und sagt das im Titel; bei
einem noch nicht platzierten Geraet heissen die Werte ausdruecklich
„Platzierungswerte". „Im Raum platzieren" nimmt sie weiter wie bisher.

Das Fenster wird echt gebaut, nur Chromium bleibt draussen (wie VIZ-109).
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QListWidget, QListWidgetItem,
                               QPushButton, QWidget)

import src.ui.views.programmer_view as PV
from _qt_lifecycle import destroy_all_top_level_widgets

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


class _AnsichtOhneWebEngine(QWidget):
    def page(self):
        return MagicMock()

    def settings(self):
        return MagicMock()


@pytest.fixture
def fenster(tmp_path, monkeypatch):
    import src.ui.visualizer.visualizer_window as VW
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    monkeypatch.setattr(VW, "QWebEngineView", _AnsichtOhneWebEngine)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_channel", lambda self: None)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_service_target",
                        lambda self: None)
    win = VW.VisualizerWindow()
    win._bridge = MagicMock()
    st = win._state
    alt_pos = dict(st.visualizer_positions)
    alt_rot = dict(st.visualizer_rotations)
    alt_sel = list(st.get_selected_fids())
    st.visualizer_positions.clear()
    st.visualizer_rotations.clear()
    # Eigene Zeilen statt echtem Patch: 901 platziert, 902 noch nicht.
    win._patch_list.blockSignals(True)
    win._patch_list.clear()
    for fid in (901, 902):
        it = QListWidgetItem(f"[{fid}] Testgeraet")
        it.setData(Qt.ItemDataRole.UserRole, fid)
        win._patch_list.addItem(it)
    win._patch_list.blockSignals(False)
    st.visualizer_positions[901] = (1.0, 3.0, -2.0)
    win.show()
    _app.processEvents()
    yield win
    st.visualizer_positions.clear()
    st.visualizer_positions.update(alt_pos)
    st.visualizer_rotations.clear()
    st.visualizer_rotations.update(alt_rot)
    st.set_selected_fids(alt_sel)


def _felder(win):
    return (win._spin_x, win._spin_y, win._spin_z,
            win._spin_rot_x, win._spin_rot_y, win._spin_rot_z)


def _box(win):
    return win._spin_x.parentWidget()


def test_ohne_auswahl_gesperrt(fenster):
    fenster._patch_list.clearSelection()
    fenster._on_patch_list_selected()
    assert fenster._patch_list.selectedItems() == []
    for sp in _felder(fenster):
        assert not sp.isEnabled(), "Feld ohne gewaehltes Geraet bearbeitbar"
    assert "kein Gerät gewählt" in _box(fenster).title()


def test_frisch_gebaut_gesperrt(tmp_path, monkeypatch):
    """Direkt nach dem Aufbau (Startwert Y 6.50) — noch niemand gewaehlt."""
    import src.ui.visualizer.visualizer_window as VW
    monkeypatch.setattr(PV, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(PV, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    monkeypatch.setattr(VW, "QWebEngineView", _AnsichtOhneWebEngine)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_channel", lambda self: None)
    monkeypatch.setattr(VW.VisualizerWindow, "_setup_service_target",
                        lambda self: None)
    st = VW.get_state()
    alt_sel = list(st.get_selected_fids())
    st.set_selected_fids([])
    try:
        win = VW.VisualizerWindow()
        win._bridge = MagicMock()
        assert win._patch_list.currentItem() is None
        assert win._spin_y.value() == pytest.approx(6.5)   # Startwert steht da …
        assert not win._spin_y.isEnabled()                  # … aber gesperrt
    finally:
        st.set_selected_fids(alt_sel)


def test_auswahl_entsperrt_und_abwahl_sperrt_wieder(fenster):
    fenster._patch_list.setCurrentRow(0)          # 901, platziert
    _app.processEvents()
    for sp in _felder(fenster):
        assert sp.isEnabled()
    assert fenster._spin_y.value() == pytest.approx(3.0)
    assert _box(fenster).title() == "Position && Ausrichtung"
    fenster._patch_list.clearSelection()           # Signal laeuft echt
    _app.processEvents()
    for sp in _felder(fenster):
        assert not sp.isEnabled(), "nach Abwahl stehen die alten Werte aktiv da"


def test_unplatziert_heisst_platzierungswerte(fenster):
    fenster._patch_list.setCurrentRow(1)          # 902, noch nicht im Raum
    _app.processEvents()
    assert fenster._spin_x.isEnabled()
    assert "Platzierungswerte" in _box(fenster).title()


def test_markierung_aus_3d_ohne_signal_zieht_sperre_nach(fenster):
    """`_mark_patch_list` blockiert die Signale — die Sperre muss trotzdem folgen."""
    fenster._mark_patch_list([902])
    assert fenster._spin_x.isEnabled()
    fenster._mark_patch_list([])
    assert not fenster._spin_x.isEnabled()


def test_im_raum_platzieren_nimmt_die_feldwerte(fenster):
    fenster._patch_list.setCurrentRow(1)          # 902
    _app.processEvents()
    fenster._spin_x.setValue(4.0)
    fenster._spin_y.setValue(5.5)
    fenster._spin_z.setValue(-1.0)
    fenster._dock_enabled = lambda: False
    fenster._place_selected()
    fenster._bridge.place_fixture_at.assert_called_once_with(902, 4.0, 5.5, -1.0, None)


def test_stub_ohne_box_bleibt_heil():
    """Die Chirurgie-Tests (VIZ-14) rufen den Handler mit einem Stub ohne Felder."""
    from src.ui.visualizer.visualizer_window import VisualizerWindow
    from src.core.app_state import get_state
    st = get_state()
    alt = list(st.get_selected_fids())
    lst = QListWidget()
    it = QListWidgetItem("x")
    it.setData(Qt.ItemDataRole.UserRole, 903)
    lst.addItem(it)
    lst.setCurrentRow(0)
    s = SimpleNamespace(_state=st, _patch_list=lst, _btn_align=QPushButton(),
                        _applying_selection=False)
    try:
        VisualizerWindow._on_patch_list_selected(s)
        assert st.selected_fids == [903]
    finally:
        st.set_selected_fids(alt)


def test_auswahl_von_aussen_fuellt_die_werte_des_neuen_geraets(fenster):
    """Review-Befund: Auswahl aus Programmer/anderer Ansicht laeuft ueber
    `_on_global_selection` -> `_mark_patch_list` und verschiebt das currentItem
    OHNE Signal (NoUpdate). Ohne Nachfuellen stuenden die Werte des vorigen
    Geraets entsperrt da — eine Eingabe haette das neue Geraet verschoben."""
    st = fenster._state
    st.visualizer_positions[902] = (7.0, 2.0, 4.0)
    fenster._patch_list.setCurrentRow(0)          # 901 -> (1, 3, -2)
    _app.processEvents()
    assert fenster._spin_x.value() == pytest.approx(1.0)
    fenster._on_global_selection(None, [902])     # SELECTION_CHANGED-Pfad
    _app.processEvents()
    assert fenster._patch_list.currentItem().data(Qt.ItemDataRole.UserRole) == 902
    assert fenster._spin_x.isEnabled()
    assert (fenster._spin_x.value(), fenster._spin_y.value(),
            fenster._spin_z.value()) == pytest.approx((7.0, 2.0, 4.0))


def test_neuaufbau_mit_gleicher_fid_holt_neue_lage(fenster):
    """Show-Wechsel/Resync: gleiche fid, andere Lage -> Felder zeigen die neue."""
    st = fenster._state
    fenster._patch_list.setCurrentRow(0)          # 901 -> (1, 3, -2)
    _app.processEvents()
    st.visualizer_positions[901] = (-5.0, 8.0, 6.0)   # neue Show, gleiche fid
    fenster._mark_patch_list([])                       # Liste neu, leer markiert
    fenster._mark_patch_list([901])                    # Auswahl kommt zurueck
    assert (fenster._spin_x.value(), fenster._spin_y.value(),
            fenster._spin_z.value()) == pytest.approx((-5.0, 8.0, 6.0))

"""UI-101: sechs Kleinigkeiten aus der Sichtpruefung.

(1) Patch-Tabelle „Typ" zeigt lesbare Namen statt interner Schluessel.
(2) Preset-Browser: „1 Gerät" statt „1 Geräte".
(3) Tempo-Buses: die Bus-Auswahl wird nicht mehr auf Kopfbreite gekappt.
(4) Show Manager: Leerhinweis spricht von der Timeline-Show, nicht von „Keine
    Show geladen".
(5) Submaster/Kanal-Gruppen: Leerhinweis statt leerer Tabelle.
(6) DMX-Monitor: zu lange Kuerzel rechts mit „…" gekuerzt.
"""
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontMetrics, QIcon                # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,  # noqa: E402
                               QVBoxLayout, QWidget)

_app = QApplication.instance() or QApplication([])

from src.core.paths import programm_datei                            # noqa: E402

_QSS = programm_datei("assets", "themes", "dark.qss")


def _mit_theme(view) -> QWidget:
    """View in ein Fenster mit dem echten dunklen Theme setzen (wie im Hauptfenster)."""
    w = QWidget()
    with open(_QSS, encoding="utf-8") as f:
        w.setStyleSheet(f.read())
    QVBoxLayout(w).addWidget(view)
    return w


# ── (1) Patch-Tabelle ─────────────────────────────────────────────────────────

def test_patch_tabelle_typ_spalte_lesbar():
    from src.ui.views import patch_view as pv
    view = pv.PatchView()
    fixtures = [
        SimpleNamespace(fid=i + 1, label=f"G{i}", manufacturer_name="Generic",
                        fixture_name="X", mode_name="M", universe=1,
                        address=1 + 10 * i, channel_count=4, fixture_type=t)
        for i, t in enumerate(("par", "led_bar", "strobe", "moving_head"))
    ]
    with mock.patch.object(view._state, "get_patched_fixtures", return_value=fixtures), \
            mock.patch.object(view, "_refresh_univ_bar"), \
            mock.patch.object(view, "_find_conflicts", return_value=set()), \
            mock.patch.object(pv._mini, "fixture_icon_for", return_value=QIcon()):
        view._refresh_table()
    spalte = pv.COLS.index("Typ")
    texte = [view._table.item(r, spalte).text() for r in range(len(fixtures))]
    assert texte == ["PAR", "LED-Bar", "Strobe", "Moving Head"]


# ── (2) Preset-Browser ────────────────────────────────────────────────────────

def test_preset_browser_einzahl_bei_einem_geraet():
    from src.core.engine.preset_search import group_entries
    e = group_entries([("Hazer", "", [7]), ("Alle", "", [1, 2]), ("Leer", "", [])])
    assert e[0].subtitle == "1 Gerät"
    assert e[1].subtitle == "2 Geräte"
    assert e[2].subtitle == "0 Geräte"


# ── (3) Tempo-Buses ───────────────────────────────────────────────────────────

def test_tempo_bus_auswahl_nicht_gekappt():
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.tempo_bus import reset_tempo_bus_manager
    from src.ui.views.tempo_bus_view import TempoBusView
    reset_tempo_bus_manager()
    fm = get_function_manager()
    fm.from_dict({"functions": []})
    try:
        m = fm.new_rgb_matrix("Regenbogen")
        m.tempo_bus_id = "default"
        view = TempoBusView()
        fenster = _mit_theme(view)
        fenster.resize(1000, 900)
        fenster.show()
        view._refresh_effects_panel()
        _app.processEvents()
        combo = view._fx_tree.findChildren(QComboBox)[0]
        spin = view._fx_tree.findChildren(QDoubleSpinBox)[0]
        assert combo.currentText() == "Haupt-BPM (Global)"
        # Die Combo bekommt mindestens ihre eigene Wunschbreite — sonst steht
        # „Haupt-BPM (Globa" im Feld.
        assert combo.width() >= combo.sizeHint().width(), (combo.width(), combo.sizeHint())
        assert spin.width() >= spin.sizeHint().width(), (spin.width(), spin.sizeHint())
        fenster.close()
    finally:
        fm.from_dict({"functions": []})
        reset_tempo_bus_manager()


# ── (4) Show Manager ──────────────────────────────────────────────────────────

def test_show_manager_leertext_meint_timeline_show():
    from src.ui.views import show_manager_view as smv
    assert "Keine Show geladen" not in smv.LEER_TEXT
    assert "Timeline-Show" in smv.LEER_TEXT
    assert "„+ Neue Show“" in smv.LEER_TEXT
    # Und er wird tatsaechlich gezeichnet (kein toter Text).
    import inspect
    assert "LEER_TEXT" in inspect.getsource(smv.TimelineCanvas.paintEvent)


# ── (5) Kanal-Gruppen ─────────────────────────────────────────────────────────

def test_kanal_gruppen_leerhinweis(tmp_path):
    from src.ui.views import channel_groups_view as cgv
    with mock.patch.object(cgv, "_PERSIST_PATH", str(tmp_path / "channel_groups.json")):
        view = cgv.ChannelGroupsView()
        assert view._groups == []
        assert not view._lbl_leer.isHidden()
        assert view._table.isHidden()
        assert "+ Neue Gruppe" in view._lbl_leer.text()
        view.load_data([{"name": "Front", "universe": 1, "channels": [1, 2], "value": 0}])
        assert view._lbl_leer.isHidden()
        assert not view._table.isHidden()
        view.load_data([])
        assert not view._lbl_leer.isHidden()


# ── (6) DMX-Monitor ───────────────────────────────────────────────────────────

def test_dmx_monitor_kuerzel_rechts_gekuerzt():
    from src.ui.views.dmx_monitor_view import kuerzel_zeile, CELL_W
    fm = QFontMetrics(QFont("Segoe UI", 7))
    breite = CELL_W - 2
    lang = "PAR 10 Dim"
    assert fm.horizontalAdvance(lang) > breite      # Voraussetzung: passt nicht
    k = kuerzel_zeile(lang, fm, breite)
    assert k.endswith("…")
    assert k.startswith("PA")                        # Anfang bleibt erhalten
    assert fm.horizontalAdvance(k) <= breite
    assert kuerzel_zeile("1 R", fm, breite) == "1 R"  # passt -> unveraendert


def test_dmx_monitor_zeichnet_gekuerzt():
    """Der Zeichenweg nutzt den Helfer (sonst wieder beidseitig gekappt)."""
    import inspect
    from src.ui.views import dmx_monitor_view as dmv
    assert "kuerzel_zeile(" in inspect.getsource(dmv.DmxGrid.paintEvent)

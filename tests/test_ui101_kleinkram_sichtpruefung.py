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


def _maler_spion(modul):
    """QPainter-Ersatz fuer ``modul``, der jeden drawText-Aufruf mitschreibt."""
    texte: list[tuple] = []
    basis = modul.QPainter

    class _Spion(basis):
        def drawText(self, *args):
            texte.append(args)
            return super().drawText(*args)

    return _Spion, texte


def test_show_manager_zeichnet_leertext_ohne_show():
    """Ohne Timeline-Show zeichnet das Canvas genau LEER_TEXT (kein toter Text)."""
    from src.ui.views import show_manager_view as smv
    canvas = smv.TimelineCanvas(SimpleNamespace(_current_show=None))
    canvas.resize(900, 200)
    spion, texte = _maler_spion(smv)
    with mock.patch.object(smv, "QPainter", spion):
        canvas.grab()
    gezeichnet = [a[-1] for a in texte if isinstance(a[-1], str)]
    assert smv.LEER_TEXT in gezeichnet, gezeichnet
    assert not any("Keine Show geladen" in t for t in gezeichnet)


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


def _rel_luminanz(c) -> float:
    def k(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * k(c.red()) + 0.7152 * k(c.green()) + 0.0722 * k(c.blue())


def test_kanal_gruppen_leerhinweis_lesbar(tmp_path):
    """Leerhinweis-Schrift hat auf dem echten Theme-Hintergrund >= 4,5:1 Kontrast."""
    import re
    from PySide6.QtGui import QColor
    from src.ui.views import channel_groups_view as cgv
    with mock.patch.object(cgv, "_PERSIST_PATH", str(tmp_path / "channel_groups.json")):
        view = cgv.ChannelGroupsView()
        fenster = _mit_theme(view)
        fenster.resize(1000, 640)
        fenster.show()
        _app.processEvents()
        # Hintergrund aus dem ganzen Fenster lesen (das Label selbst ist
        # transparent, sein eigener grab() waere schwarz).
        ecke = view._lbl_leer.mapTo(fenster, view._lbl_leer.rect().topLeft())
        hg = fenster.grab().toImage().pixelColor(ecke.x() + 2, ecke.y() + 2)
        m = re.search(r"color:\s*(#[0-9a-fA-F]{3,6})", view._lbl_leer.styleSheet())
        schrift = QColor(m.group(1))
        hell, dunkel = sorted((_rel_luminanz(hg), _rel_luminanz(schrift)), reverse=True)
        kontrast = (hell + 0.05) / (dunkel + 0.05)
        fenster.close()
    assert kontrast >= 4.5, (hg.name(), schrift.name(), round(kontrast, 2))


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
    """Der Zeichenweg kuerzt lange Kuerzel rechts mit „…" auf Zellbreite."""
    from src.ui.views import dmx_monitor_view as dmv
    grid = dmv.DmxGrid()
    grid.resize(dmv.COLS * dmv.CELL_W, dmv.ROWS * dmv.CELL_H)
    grid.set_cell_info({10: ("PAR 10", "dimmer", "PAR 10 · Dimmer"),
                        11: ("P1", "", "P1")})
    fm = QFontMetrics(QFont("Segoe UI", 7))
    spion, texte = _maler_spion(dmv)
    with mock.patch.object(dmv, "QPainter", spion):
        grid.grab()
    # Kuerzel-Zeile = drawText(x, y, w, h, flags, text) mit h == 10
    zeilen = [a for a in texte if len(a) == 6 and a[3] == 10]
    lang = [a[5] for a in zeilen if a[5].startswith("PA")]
    assert lang and lang[0].endswith("…"), lang
    assert fm.horizontalAdvance(lang[0]) <= dmv.CELL_W - 2, lang[0]
    assert all(a[2] <= dmv.CELL_W - 2 for a in zeilen)
    assert any(a[5] == "P1" for a in zeilen)          # kurzes bleibt unveraendert

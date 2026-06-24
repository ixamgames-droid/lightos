"""Regression: Umschalten zwischen gespeicherten Effekten im Programmer.

Beim Auswählen einer anderen RGB-Matrix / eines anderen EFX befüllt der Editor
seine Widgets aus dem Modell. Einige Widgets werden dabei mit blockierten
Signalen gesetzt, andere (cols/rows/speed bzw. Algo/Geometrie) nicht. Ohne
Schutz feuert das erste nicht-blockierte Widget ``_param_change`` /
``_on_param_change`` BEVOR die übrigen Widgets geladen sind — und schreibt deren
noch-alte Werte (von der zuvor angezeigten Instanz) zurück ins frisch gewählte
Modell.

Folge ohne Fix:
- die neu gewählte Instanz erbt fremde Werte (Daten-Korruption) und
- die Matrix gilt sofort als „● ungespeicherte Änderungen".

Diese Tests stellen sicher, dass das Befüllen der UI keine Werte zurückschreibt.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ── RGB-Matrix ────────────────────────────────────────────────────────────────

def test_switching_matrix_does_not_corrupt_or_dirty():
    """Zurück zur ersten Matrix: keine fremden Werte, kein sofortiges Dirty."""
    _app()
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    view = RgbMatrixView()
    # Zwei frische Matrizen anlegen und die LETZTEN beiden Listenzeilen nutzen
    # (der FunctionManager ist global und kann aus anderen Tests gefüllt sein).
    view._add()
    view._add()
    row_b = view._list.count() - 1
    row_a = row_b - 1
    assert row_a >= 0

    # Matrix A: rows=4, speed=1.0 -> speichern
    view._list.setCurrentRow(row_a)
    view._rows_spin.setValue(4)
    view._speed_spin.setValue(1.0)
    view._param_change()
    view._save_edit()
    rows_a = view._saved.rows
    speed_a = view._saved.matrix_speed
    assert (rows_a, speed_a) == (4, 1.0)

    # Matrix B: deutlich andere Werte -> speichern
    view._list.setCurrentRow(row_b)
    view._rows_spin.setValue(8)
    view._speed_spin.setValue(5.0)
    view._param_change()
    view._save_edit()

    # Zurück zu A: darf NICHT B's Werte erben und NICHT sofort dirty sein.
    view._list.setCurrentRow(row_a)
    assert view._current.rows == rows_a, (
        f"Matrix A erbt rows von B: {view._current.rows} statt {rows_a}"
    )
    assert view._current.matrix_speed == speed_a, (
        f"Matrix A erbt speed von B: {view._current.matrix_speed} statt {speed_a}"
    )
    assert not view._btn_save.isEnabled(), (
        "Frisch gewählte Matrix darf nicht sofort als geändert gelten"
    )
    assert view._dirty_lbl.text() == ""


# ── EFX ─────────────────────────────────────────────────────────────────────

def test_switching_efx_does_not_corrupt_params():
    """Zurück zum ersten EFX: spread/open_beam/width bleiben erhalten."""
    _app()
    from src.ui.views.efx_view import EfxView
    view = EfxView()  # follow_selection=False -> kein Auswahl-Override
    # „Entwurf bis Speichern": „+ Neu" erzeugt nur EINEN fluechtigen Entwurf pro
    # View (ein zweites „+ Neu" verwirft den ersten). Fuer den Lade-Guard-Test
    # zwei BLEIBENDE EFX brauchen -> jeden Entwurf sofort speichern (committed).
    view._add_efx()
    view._save_efx()
    view._add_efx()
    view._save_efx()
    row_b = view._list.count() - 1
    row_a = row_b - 1
    assert row_a >= 0

    # EFX A: spread=0.0, open_beam=True, width=50
    view._list.setCurrentRow(row_a)
    view._spread_spin.setValue(0.0)
    view._open_beam_chk.setChecked(True)
    view._width_spin.setValue(50)
    view._on_param_change()
    efx_a = view._current
    assert (efx_a.spread, efx_a.open_beam, efx_a.width) == (0.0, True, 50)

    # EFX B: gegenteilige Werte
    view._list.setCurrentRow(row_b)
    view._spread_spin.setValue(1.0)
    view._open_beam_chk.setChecked(False)
    view._width_spin.setValue(200)
    view._on_param_change()

    # Zurück zu A: Werte müssen unverändert sein (kein Erben von B).
    view._list.setCurrentRow(row_a)
    assert view._current is efx_a
    assert view._current.spread == 0.0, f"spread korrupt: {view._current.spread}"
    assert view._current.open_beam is True, f"open_beam korrupt: {view._current.open_beam}"
    assert view._current.width == 50, f"width korrupt: {view._current.width}"

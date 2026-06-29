"""Regression: RGB-Matrix Style-/Farb-Sichtbarkeit darf nie mit AttributeError crashen.

Historischer Crash (crash.log 2026-06-20): `_apply_color_visibility` verwies auf ein
nicht (mehr) existentes Widget `self._white_form_label` -> AttributeError beim
Style-Wechsel (`_on_style_change` -> `_apply_style_visibility` -> `_apply_color_visibility`).
Heute heisst das Widget `_shut_form_label`; der Prod-Code ist also bereits gefixt.

Dieser Test sperrt die Regression: KEIN Style/Algorithmus-Pfad darf je ein fehlendes
Attribut anfassen. Er iteriert ueber die ECHTEN Enums -> deckt auch kuenftige
Umbenennungen/neue Styles automatisch ab.
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


def test_style_visibility_never_raises_across_all_styles_and_algos():
    _app()
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    from src.core.engine.rgb_matrix import MatrixStyle, RgbAlgorithm

    view = RgbMatrixView()
    # Ein Draft -> self._current gesetzt, damit auch die params-abhaengigen Zweige
    # (color_cycle / dimmer_cycle) in _apply_color_visibility durchlaufen werden.
    view._add()

    for style in MatrixStyle:
        for algo in RgbAlgorithm:
            # Realer Pfad: Combos setzen -> _on_algo_change/_on_style_change feuern.
            view._algo_combo.setCurrentText(algo.value)
            view._style_combo.setCurrentText(style.value)
            # Plus direkter Aufruf der Sichtbarkeits-Logik (der historische
            # Crash-Ort). Ein fehlendes Attribut wuerde hier sofort werfen.
            view._apply_style_visibility(style)
            view._apply_color_visibility(style)

    # Bis hierher = kein Style/Algo-Paar hat ein fehlendes Attribut angefasst.
    # Sanity: alle Enum-Werte waren im jeweiligen Combo auswaehlbar.
    assert view._style_combo.count() == len(list(MatrixStyle))
    assert view._algo_combo.count() == len(list(RgbAlgorithm))

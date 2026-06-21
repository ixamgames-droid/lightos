"""Gemeinsame Build-Boilerplate für tools/build_*.py — ersetzt das ~95% copy-
paste (sys.path/offscreen/QApplication + profile_id + Patch-Schleife).

Ein Build-Skript schrumpft damit auf:

    from _builder import ShowBuilder, RgbAlgorithm, ButtonAction
    b = ShowBuilder()
    fids = b.patch("ZQ01424", count=8, channel_count=8, mode_name="8-Kanal RGBW")
    mx = b.matrix("Farbe", algorithm=RgbAlgorithm.CHASE, fixtures=fids,
                  colors=[(255,0,0),(0,0,255)])
    b.button("An/Aus", action=ButtonAction.FUNCTION_TOGGLE, function=mx, bank=0)
    build_and_verify(b, "shows/Mini.lshow", render=[mx])

Alles, was ``b`` baut, ist garantiert „nur echte Bausteine" (save() validiert
statisch + live; jeder fake Algo/Action/Param/Fixture wirft schon am Aufruf).
"""
from __future__ import annotations

import os
import sys

# src importierbar machen (innerer Root) + headless Qt — VOR den src-Imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
except Exception:
    _app = None

from src.core.show.showbuilder import ShowBuilder, Handle, BuildError  # noqa: E402
# Echte Enum-Member bequem zur Hand (falscher NAME wirft sofort AttributeError):
from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle      # noqa: E402
from src.core.engine.efx import EfxAlgorithm                          # noqa: E402
from src.core.engine.function import RunOrder, Direction              # noqa: E402
from src.ui.virtualconsole.vc_button import ButtonAction              # noqa: E402

__all__ = ["ShowBuilder", "Handle", "BuildError", "RgbAlgorithm", "MatrixStyle",
           "EfxAlgorithm", "RunOrder", "Direction", "ButtonAction",
           "build_and_verify"]


def build_and_verify(builder: ShowBuilder, out: str, *, render=None, name=None) -> str:
    """Speichert + validiert die Show (statisch + live) und macht optional einen
    Render-Smoke über ``render`` (Liste von Handles/IDs). Wirft bei Problemen."""
    builder.save(out, name=name)
    if render:
        lit, moved, _changed = builder.verify_render(render)
        if not (lit or moved):
            raise SystemExit(f"Render-Smoke fehlgeschlagen: {out} erzeugt kein DMX")
    print(f"OK: {os.path.basename(out)} gebaut + validiert "
          f"({len(builder._widgets)} Widgets)")
    return out

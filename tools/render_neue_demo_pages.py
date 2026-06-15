"""Rendert die 5 Banks der Neue_Demo_2026-Show als PNG (für die Doku/Vorschau)."""
from __future__ import annotations
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

from src.ui.virtualconsole.vc_canvas import VCCanvas

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "Neue_Demo_2026.lshow")
OUT_DIR = os.path.join(_ROOT, "docs", "images")
PAGE_NAMES = ["quadranten", "matrix-looks", "builder", "moving-heads", "playback"]
W, H = 1180, 812


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with zipfile.ZipFile(SHOW) as z:
        layout = json.loads(z.read("show.json"))["virtual_console"]
    canvas = VCCanvas()
    canvas.resize(W, H)
    canvas.from_dict(layout)
    canvas.resize(W, H)
    for bank, name in enumerate(PAGE_NAMES):
        canvas.set_active_bank(bank)
        _app.processEvents()
        pix = canvas.grab()
        path = os.path.join(OUT_DIR, f"neue_demo_{bank+1}_{name}.png")
        ok = pix.save(path, "PNG")
        print(f"{'OK ' if ok else 'ERR'} {path}  ({pix.width()}x{pix.height()})")
    print("FERTIG")


if __name__ == "__main__":
    main()

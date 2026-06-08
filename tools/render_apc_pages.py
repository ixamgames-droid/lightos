"""Rendert jede Seite (VC-Bank) der APC-Test-Show als PNG — fuer die Anleitung.

Baut die ECHTEN Virtual-Console-Widgets offscreen auf einem VCCanvas auf, schaltet
nacheinander jede Bank aktiv und macht von jeder einen Screenshot. So sieht man
1:1, welches Pad / welcher Fader auf welcher Seite was tut.

Aufruf:  venv/Scripts/python.exe tools/render_apc_pages.py
Ergebnis: docs/images/apc_page_0_farben.png … apc_page_5_color-chase.png
"""
from __future__ import annotations
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Native Plattform: das offscreen-Plugin hat keine Schrift-Glyphen (Text wuerde als
# Kaestchen erscheinen). Auf einem Windows-Desktop rendert "windows" mit echten Fonts.
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize

_app = QApplication.instance() or QApplication([])

from src.ui.virtualconsole.vc_canvas import VCCanvas

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOW = os.path.join(_ROOT, "shows", "APC_Test_Komplett.lshow")
OUT_DIR = os.path.join(_ROOT, "docs", "images")
PAGE_NAMES = ["farben", "dimmer", "matrix", "mix", "rgbw", "color-chase"]
W, H = 760, 812


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
        path = os.path.join(OUT_DIR, f"apc_page_{bank}_{name}.png")
        ok = pix.save(path, "PNG")
        print(f"{'OK ' if ok else 'ERR'} {path}  ({pix.width()}x{pix.height()})")
    print("FERTIG")


if __name__ == "__main__":
    main()

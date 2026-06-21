"""Erzeugt den Agenten-Vertrag aus dem Code: docs/CAPABILITIES.md +
docs/capability_manifest.json.

    venv/Scripts/python.exe tools/gen_capabilities.py

Nach jeder Code-Änderung an Widgets/Enums/Algos/Params neu laufen lassen
(test_capability_manifest erzwingt das per Diff-Test).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
except Exception:
    _app = None

from src.core.capability.manifest import write_manifest  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "docs")


def main() -> int:
    json_path, md_path = write_manifest(OUT_DIR)
    print(f"Geschrieben:\n  {json_path}\n  {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI-Wrapper: QLC+-Inputprofil (.qxi) → LightOS-Controller-Profil (JSON).

Aufruf:
    venv\\Scripts\\python tools\\import_qlc_input_profile.py <datei.qxi> [...]
    (optional: --dry-run  → nur anzeigen, nichts schreiben)

Konverter-Kern: src/core/controllers/qxi_import.py (auch von der UI genutzt).
Quellen/Lizenz: data/controller_library/README.md
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.controllers.qxi_import import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

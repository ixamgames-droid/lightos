"""tools/_archiv — ausgemusterte Werkzeuge (Begruendungen: ``README.md``).

Zweck dieses ``__init__`` ist derselbe wie beim Eltern-Paket ``tools/`` (DEMO-06):
den Modul-Import-Pfad gangbar halten.

Beim DIREKTSTART (``python tools/_archiv/build_x.py``) legt Python den
Skript-Ordner ohnehin auf ``sys.path[0]`` — ``import _bootstrap`` resolved dort
von selbst, und dieses ``__init__`` laeuft gar nicht (das Skript ist
``__main__``, nicht ``tools._archiv.build_x``).

Beim MODUL-IMPORT (``python -c "import tools._archiv.build_x"``) ist das anders:
``tools/__init__.py`` legt nur ``tools/`` auf ``sys.path``, nicht
``tools/_archiv/`` — ``import _bootstrap`` waere ein
``ModuleNotFoundError``. Darum legt dieses ``__init__`` zusaetzlich den eigenen
Ordner dazu.
"""
import os as _os
import sys as _sys

_ARCHIV_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _ARCHIV_DIR not in _sys.path:
    _sys.path.insert(0, _ARCHIV_DIR)

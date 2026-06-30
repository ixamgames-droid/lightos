"""tools-Paket — Show-Generatoren + Build-Helfer.

DEMO-06 (Single-Point): Sobald ein Generator als MODUL importiert wird
(``python -c "import tools.build_x"``), laeuft zuerst dieses ``__init__`` — es legt
das ``tools/``-Verzeichnis auf ``sys.path``. Dadurch resolved das ``import _gen_env``
der Generatoren (spawn-sichere Bootstrap-Schicht, siehe ``tools/_gen_env.py``) auch
im Modul-Import-Pfad. Bei direkter Ausfuehrung (``python tools/build_x.py``) legt
Python ``tools/`` ohnehin auf ``sys.path[0]`` — dort war das ``import _gen_env`` nie
ein Problem; dieses ``__init__`` wird in dem Fall gar nicht ausgefuehrt (das Skript
laeuft als ``__main__``, nicht als ``tools.build_x``).
"""
import os as _os
import sys as _sys

_TOOLS_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _TOOLS_DIR not in _sys.path:
    _sys.path.insert(0, _TOOLS_DIR)

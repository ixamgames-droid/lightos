"""Pfad-Bootstrap fuer ausgemusterte Werkzeuge in ``tools/_archiv/``.

Warum es das gibt (TOOLS-ALTGEN, 2026-07-27):
    Ein Skript in ``tools/`` loest Repo-Root und Show-Pfade ueber die Zeile
    ``os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`` auf — aus
    ``tools/`` heraus ist das genau der Repo-Root. Wandert dasselbe Skript per
    ``git mv`` nach ``tools/_archiv/``, zeigt die identische Zeile eine Ebene zu
    tief: auf ``tools/``. Zwei stille Folgen, beide beim Werkzeug-Audit
    2026-07-19 unbemerkt eingetreten:

      * ``sys.path.insert(0, <dirname-dirname>)`` legt ``tools/`` statt des
        Repo-Roots auf den Pfad -> **jeder** ``from src.core… import`` bricht
        mit ``ModuleNotFoundError``. Die archivierten Skripte waren dadurch
        nicht nur ausgemustert, sondern schlicht nicht mehr startbar.
      * ``_ROOT``/``OUT`` zeigen auf ``tools/shows/<Name>.lshow`` statt auf
        ``shows/<Name>.lshow`` — ein reaktiviertes Skript haette seine Show
        klammheimlich in den Werkzeug-Ordner geschrieben.

Loesung: den Repo-Root nicht ueber die Verschachtelungstiefe raten, sondern
ueber einen **Marker** finden (der erste Ordner aufwaerts, der ``src/`` UND
``tools/`` enthaelt). Damit ist der Bootstrap unabhaengig davon, ob das Skript
in ``tools/`` oder ``tools/_archiv/`` liegt — ein kuenftiges Archivieren ist
wieder ein reines ``git mv``.

Verwendung — als erste Import-Zeile eines archivierten Skripts::

    import _bootstrap                  # Repo-Root + tools/ auf sys.path
    import _gen_env  # noqa: F401      # spawn-sichere Env-Schalter (tools/)
    from src.core.app_state import get_state
    ...
    _ROOT = _bootstrap.REPO_ROOT       # statt dirname(dirname(__file__))

``tests/test_tools_archiv_paths.py`` haelt die Regel gruen: kein Skript in
``tools/_archiv/`` darf den Repo-Root noch ueber die Tiefe raten.
"""
from __future__ import annotations

import os
import sys


def find_repo_root(start: str) -> str:
    """Ersten Ordner aufwaerts von ``start`` liefern, der ``src/`` + ``tools/`` hat.

    Faellt auf den zwei Ebenen ueber ``start`` liegenden Ordner zurueck, wenn
    kein Marker gefunden wird (z. B. wenn jemand nur den Werkzeug-Ordner ohne
    Repo herauskopiert hat) — dann verhaelt sich der Bootstrap wie die alte
    Zeile, statt einen leeren Pfad zu liefern.
    """
    cur = os.path.abspath(start)
    while True:
        if (os.path.isdir(os.path.join(cur, "src"))
                and os.path.isdir(os.path.join(cur, "tools"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.dirname(os.path.dirname(os.path.abspath(start)))
        cur = parent


#: Repo-Root (der Ordner mit ``src/`` und ``tools/``).
REPO_ROOT = find_repo_root(os.path.dirname(os.path.abspath(__file__)))
#: ``tools/`` — Heimat von ``_gen_env.py``/``_builder.py``/``_showpath.py``.
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")

# Repo-Root zuerst (``src.…``), danach ``tools/`` (``_gen_env``, ``_builder``).
for _p in (TOOLS_DIR, REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

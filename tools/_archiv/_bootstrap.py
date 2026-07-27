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

Der Bootstrap zieht ausserdem ``_gen_env`` mit (Show-DB-Isolation, s. u.) —
ein archiviertes Skript braucht die Zeile also nicht mehr selbst.

Verwendung — als erste Import-Zeile eines archivierten Skripts::

    import _bootstrap                  # Repo-Root + tools/ auf sys.path
                                       # + isolierte LIGHTOS_SHOW_DB via _gen_env
    from src.core.app_state import get_state
    ...
    _ROOT = _bootstrap.REPO_ROOT       # statt dirname(dirname(__file__))

Show-Pfade zum LESEN nicht selbst zusammenbauen, sondern ueber ``_showpath``
aufloesen — die Ziel-Shows archivierter Werkzeuge liegen naemlich meist in
``shows/_archiv/``, nicht in ``shows/``::

    from _showpath import find_show
    SHOW = find_show("Buehnen_Show.lshow")   # prueft shows/ UND shows/_archiv/

``tests/test_tools_archiv_paths.py`` haelt die Pfad-Regel gruen,
``tests/test_tools_db_isolation.py`` die Isolations-Regel.
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

# Reihenfolge DETERMINISTISCH erzwingen: Repo-Root (fuer ``src.…``) vor
# ``tools/`` (fuer ``_gen_env``/``_builder``/``_showpath``). Ein blosses
# ``if _p not in sys.path: insert(0, _p)`` kippt die Reihenfolge, sobald einer
# der beiden Pfade schon drinsteht (z. B. Repo-Root via PYTHONPATH — genau der
# dokumentierte Aufruf mehrerer Archiv-Skripte).
for _p in (REPO_ROOT, TOOLS_DIR):
    while _p in sys.path:
        sys.path.remove(_p)
sys.path[:0] = [REPO_ROOT, TOOLS_DIR]

# ── Show-DB-Isolation (STAB-CURSHOW (a)) ─────────────────────────────────────
# Der Pfad-Fix oben macht die archivierten Skripte wieder STARTBAR. Damit lebt
# auch ihr urspruenglicher Footgun wieder auf: fuenf von ihnen fassen den
# App-State an (``reset_show``/``load_show``/``get_state``), ohne selbst
# ``import _gen_env`` zu haben — sie wuerden auf Davids geteilter
# ``data/current_show.db`` arbeiten (bei ``verify_matrix_group_scope.py`` sogar
# mit ``reset_show()`` + ``delete(FixtureGroup)``; siehe README-Tabelle).
# ``tests/test_tools_db_isolation.py`` nimmt ``tools/_archiv/`` aus, deckt das
# also NICHT ab. Darum zieht der Bootstrap ``_gen_env`` selbst mit: jedes
# Skript, das ``import _bootstrap`` hat, ist damit automatisch isoliert
# (Wegwerf-``LIGHTOS_SHOW_DB``, kein Output-Thread, kein Audio-Autostart).
# Alles per ``setdefault`` — eine bewusst gesetzte Umgebung gewinnt weiterhin.
import _gen_env  # noqa: E402,F401  (Import-Seiteneffekt ist der Zweck)

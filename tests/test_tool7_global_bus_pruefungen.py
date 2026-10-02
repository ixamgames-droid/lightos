"""TOOL-7: kein Werkzeug sucht den „Global"-Bus unter ``named_buses()``.

Seit ENG-26 ist ``"Global"`` ein ALIAS des Default-Bus
(``TempoBusManager.kanonische_bus_id``); ``named_buses()`` listet den
Default-Bus per Konstruktion nie. TOOL-5 hat das in
``build_demo_show_full.py`` behoben (``AssertionError: Global-Bus fehlt: []``).
Derselbe Fehler steckte in ``build_mega_arena_2026.py``:
``named = {b.bus_id: b for b in …named_buses()}; named[BUS]`` mit
``BUS = "Global"`` war ein ``KeyError`` — NACHDEM die Show gespeichert war,
der Generator kam nie bei „FERTIG" an. Gefunden bei der ENG-28-Gegenprobe
(#848), gegen eine frisch geseedete Bibliothek.

Der Waechter prueft ALLE Werkzeuge, nicht nur diesen Generator.
"""
import ast
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
GENERATOR = os.path.join(TOOLS, "build_mega_arena_2026.py")
STANDARD_ZIEL = os.path.join(REPO, "shows", "Mega_Arena_2026.lshow")


def _ist_global_text(knoten):
    return (isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)
            and knoten.value.strip().lower() == "global")


def _ruft_named_buses(knoten):
    return any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
               and c.func.attr == "named_buses" for c in ast.walk(knoten))


def _global_unter_named_buses(quelltext, name="<quelle>"):
    """Stellen, die „Global" in einer aus ``named_buses()`` gebauten Sammlung
    suchen: ``named["Global"]``, ``named[BUS]``, ``named.get(BUS)``,
    ``BUS in named`` oder ``"Global" in [b.bus_id for b in …named_buses()]``."""
    try:
        baum = ast.parse(quelltext, filename=name)
    except SyntaxError:
        return []
    zuweisungen = [k for k in ast.walk(baum) if isinstance(k, ast.Assign)]
    global_namen = {t.id for k in zuweisungen for t in k.targets
                    if isinstance(t, ast.Name) and _ist_global_text(k.value)}
    named_namen = {t.id for k in zuweisungen for t in k.targets
                   if isinstance(t, ast.Name) and _ruft_named_buses(k.value)}

    def ist_global(e):
        return _ist_global_text(e) or (isinstance(e, ast.Name) and e.id in global_namen)

    def ist_named(e):
        return (isinstance(e, ast.Name) and e.id in named_namen) or _ruft_named_buses(e)

    treffer = []
    for k in ast.walk(baum):
        fund = (
            (isinstance(k, ast.Subscript) and ist_named(k.value) and ist_global(k.slice))
            or (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                and k.func.attr == "get" and ist_named(k.func.value)
                and k.args and ist_global(k.args[0]))
            or (isinstance(k, ast.Compare) and ist_global(k.left)
                and any(isinstance(o, (ast.In, ast.NotIn)) for o in k.ops)
                and any(ist_named(c) for c in k.comparators)))
        if fund:
            treffer.append(f"{name}:{k.lineno}  {ast.unparse(k)}")
    return sorted(set(treffer), key=lambda z: int(z.split(":")[1].split()[0]))


def _werkzeuge():
    for wurzel, ordner, dateien in os.walk(TOOLS):
        ordner[:] = sorted(o for o in ordner if o not in ("_archiv", "__pycache__"))
        for d in sorted(dateien):
            if d.endswith(".py"):
                yield os.path.join(wurzel, d)


class KeinWerkzeugSuchtGlobalUnterNamedBuses(unittest.TestCase):

    def test_alle_werkzeuge(self):
        treffer = []
        for pfad in _werkzeuge():
            with open(pfad, encoding="utf-8", errors="replace") as f:
                treffer += _global_unter_named_buses(f.read(), os.path.relpath(pfad, REPO))
        self.assertEqual(treffer, [], (
            "„Global“ ist der Default-Bus und steht nie in named_buses() — "
            "tbm.get(BUS) / bus_for_effect benutzen (s. TOOL-5):\n  "
            + "\n  ".join(treffer)))

    def test_der_scanner_erkennt_die_formen(self):
        """Positivkontrolle — sonst waere der Waechter oben leer gruen."""
        quelle = (
            'BUS = "Global"\n'                                                # 1
            'named = {b.bus_id: b for b in tbm.named_buses()}\n'              # 2
            'a = named[BUS]\n'                                                # 3
            'b = named.get("global")\n'                                       # 4
            'assert BUS in named\n'                                           # 5
            'assert "Global" in [b.bus_id for b in tbm.named_buses()]\n'      # 6
            'c = named["A"]\n'                                                # ok: echter Name
            'd = tbm.get(BUS)\n'                                              # ok
            'assert "A" in named\n')                                          # ok
        zeilen = [int(t.split(":")[1].split()[0]) for t in _global_unter_named_buses(quelle)]
        self.assertEqual(zeilen, [3, 4, 5, 6])


def _sha(pfad):
    if not os.path.isfile(pfad):
        return None
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class MegaArenaLaeuftBisFertig(unittest.TestCase):
    """Der Generator selbst, im Unterprozess, bis zu seiner letzten Zeile —
    Show und Musikordner umgelenkt, ``shows/`` bleibt unberuehrt."""

    def test_selbstpruefung_laeuft_durch(self):
        vorher = _sha(STANDARD_ZIEL)
        with tempfile.TemporaryDirectory(prefix="lightos_tool7_") as tmp:
            ziel = os.path.join(tmp, "Mega_Arena_2026.lshow")
            musik = os.path.join(tmp, "musik")
            os.mkdir(musik)
            env = dict(os.environ)
            env.update({
                "LIGHTOS_GEN_OUT": ziel,
                "LIGHTOS_SHOW_DB": os.path.join(tmp, "show.db"),
                "LIGHTOS_MEGA_MUSIC_DIR": musik,      # leer -> Platzhalter-Playlist
                "QT_QPA_PLATFORM": "offscreen",
                "PYTHONIOENCODING": "utf-8",
            })
            lauf = subprocess.run([sys.executable, GENERATOR], cwd=REPO, env=env,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            ausgabe = lauf.stdout + lauf.stderr
            self.assertNotIn("KeyError", ausgabe)
            self.assertEqual(lauf.returncode, 0,
                             f"Generator endete mit rc={lauf.returncode}:\n{ausgabe[-3000:]}")
            self.assertIn("FERTIG", lauf.stdout)
            self.assertTrue(os.path.isfile(ziel), "LIGHTOS_GEN_OUT wurde nicht beachtet")
        self.assertEqual(_sha(STANDARD_ZIEL), vorher, "der Test hat shows/ veraendert")


if __name__ == "__main__":
    unittest.main()

"""TOOLS-ALTGEN Lint-Gate: archivierte Werkzeuge duerfen den Repo-Root nicht raten.

Hintergrund (2026-07-27): Skripte in ``tools/`` loesen den Repo-Root ueber die
Verschachtelungstiefe auf::

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

Aus ``tools/`` heraus stimmt das. Wandert das Skript per ``git mv`` nach
``tools/_archiv/``, zeigt exakt dieselbe Zeile eine Ebene zu tief — auf
``tools/``. Genau das passierte beim Werkzeug-Audit 2026-07-19 mit allen neun
damals archivierten Skripten, unbemerkt, weil sie danach nie wieder liefen:

  * der Repo-Root stand nicht mehr auf ``sys.path`` -> jeder ``from src.core…``
    haette mit ``ModuleNotFoundError`` abgebrochen;
  * ``_ROOT``/``SHOW``/``OUT`` zeigten auf ``tools/shows/<Name>.lshow`` statt auf
    ``shows/<Name>.lshow``.

Regel seither: archivierte Skripte holen sich den Repo-Root ueber
``tools/_archiv/_bootstrap.py`` (Marker-Suche statt Tiefen-Raten). Dieses Gate
haelt das gruen — damit bleibt Archivieren ein reines ``git mv``.
"""
import ast
import io
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIV = os.path.join(REPO, "tools", "_archiv")
BOOTSTRAP = "_bootstrap.py"

# Das Tiefen-Raten in seinen beiden Schreibweisen.
DEPTH_GUESS = re.compile(
    r"os\.path\.dirname\(\s*os\.path\.dirname\(\s*os\.path\.abspath\(\s*__file__"
    r"|os\.path\.join\(\s*os\.path\.dirname\(\s*__file__\s*\)\s*,\s*[\"']\.\.[\"']"
)
HINT = ("-> Repo-Root ueber tools/_archiv/_bootstrap.py aufloesen "
        "(import _bootstrap; _bootstrap.REPO_ROOT), nicht ueber die Ordnertiefe")


def _archived_scripts():
    if not os.path.isdir(ARCHIV):
        return
    for name in sorted(os.listdir(ARCHIV)):
        if not name.endswith(".py") or name == BOOTSTRAP:
            continue
        path = os.path.join(ARCHIV, name)
        if os.path.isfile(path):
            yield name, path


def _read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


class ArchivPathLintTest(unittest.TestCase):
    def test_bootstrap_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(ARCHIV, BOOTSTRAP)),
            f"tools/_archiv/{BOOTSTRAP} fehlt {HINT}")

    def test_no_depth_guessing(self):
        """Kein archiviertes Skript darf den Repo-Root aus der Tiefe ableiten."""
        offenders = []
        for name, path in _archived_scripts():
            for lineno, line in enumerate(_read(path).splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if DEPTH_GUESS.search(line):
                    offenders.append(f"{name}:{lineno}")
        self.assertEqual(offenders, [], f"Tiefen-Raten in tools/_archiv/: {offenders} {HINT}")

    def test_src_importing_scripts_bootstrap(self):
        """Wer ``src.…`` importiert, braucht den Bootstrap (sonst ModuleNotFoundError)."""
        offenders = []
        for name, path in _archived_scripts():
            text = _read(path)
            if not re.search(r"^\s*(?:from|import)\s+src\.", text, re.M):
                continue
            if not re.search(r"^\s*import _bootstrap\b", text, re.M):
                offenders.append(name)
        self.assertEqual(
            offenders, [],
            f"Archiv-Skripte mit src.-Import ohne `import _bootstrap`: {offenders} {HINT}")

    def test_bootstrap_import_precedes_src_and_tools_imports(self):
        """``import _bootstrap`` muss VOR ``src.…``/``_gen_env`` stehen."""
        offenders = []
        for name, path in _archived_scripts():
            try:
                tree = ast.parse(_read(path))
            except SyntaxError as exc:
                offenders.append(f"{name} (SyntaxError: {exc})")
                continue
            boot = dep = None
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name == "_bootstrap" and boot is None:
                            boot = node.lineno
                        elif a.name in ("_gen_env", "_builder") and dep is None:
                            dep = node.lineno
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in ("src", "_builder", "_showpath") and dep is None:
                        dep = node.lineno
            if dep is not None and (boot is None or boot > dep):
                offenders.append(f"{name} (_bootstrap={boot}, abhaengiger Import={dep})")
        self.assertEqual(
            offenders, [],
            f"`import _bootstrap` steht zu spaet: {offenders} {HINT}")

    def test_bootstrap_resolves_real_repo_root(self):
        """Der Bootstrap muss aus tools/_archiv/ heraus den echten Repo-Root treffen."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_archiv_bootstrap_under_test", os.path.join(ARCHIV, BOOTSTRAP))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(
            os.path.normcase(os.path.abspath(mod.REPO_ROOT)),
            os.path.normcase(os.path.abspath(REPO)),
            "REPO_ROOT zeigt nicht auf den Repo-Root")
        # Der eigentliche Regressionspunkt: NICHT auf tools/.
        self.assertNotEqual(
            os.path.normcase(os.path.abspath(mod.REPO_ROOT)),
            os.path.normcase(os.path.join(REPO, "tools")),
            "REPO_ROOT zeigt auf tools/ — genau der Bug von 2026-07-19")
        self.assertTrue(os.path.isdir(os.path.join(mod.REPO_ROOT, "shows")),
                        "shows/ unter REPO_ROOT nicht gefunden")


if __name__ == "__main__":
    unittest.main()

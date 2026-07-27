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

HINT = ("-> Repo-Root ueber tools/_archiv/_bootstrap.py aufloesen "
        "(import _bootstrap; _bootstrap.REPO_ROOT), nicht ueber die Ordnertiefe")


def _refs_file(node):
    """Enthaelt der Teilbaum eine ``__file__``-Referenz?"""
    return any(isinstance(n, ast.Name) and n.id == "__file__"
               for n in ast.walk(node))


def _is_attr_chain(node, *names):
    """Passt ``node`` auf einen Attribut-Pfad wie ``os.path.dirname``?"""
    for name in reversed(names[1:]):
        if not (isinstance(node, ast.Attribute) and node.attr == name):
            return False
        node = node.value
    return ((isinstance(node, ast.Name) and node.id == names[0])
            or (isinstance(node, ast.Attribute) and node.attr == names[0]))


def _dirname_depth(node):
    """Wie viele ``os.path.dirname(...)`` sind hier ineinander geschachtelt?"""
    depth = 0
    while (isinstance(node, ast.Call)
           and _is_attr_chain(node.func, "os", "path", "dirname")
           and node.args):
        depth += 1
        node = node.args[0]
    return depth, node


def find_depth_guesses(tree):
    """Alle Stellen liefern, die den Repo-Root aus der ORDNERTIEFE ableiten.

    AST statt Zeilen-Regex, damit auch mehrzeilige Schreibweisen und die
    pathlib-Variante auffallen (die reine Regex-Fassung war blind fuer
    ``Path(__file__).resolve().parents[1]`` — Review-Fund 2026-07-27).
    Erkannt werden:
      * ``os.path.dirname(os.path.dirname(...__file__...))`` (Tiefe >= 2)
      * ``os.path.join(os.path.dirname(__file__), "..", ...)``
      * ``Path(__file__)...parents[N]`` mit N >= 1
    """
    hits = []
    for node in ast.walk(tree):
        # os.path.dirname(os.path.dirname(<... __file__ ...>))
        if isinstance(node, ast.Call) and _is_attr_chain(node.func, "os", "path", "dirname"):
            depth, inner = _dirname_depth(node)
            if depth >= 2 and _refs_file(inner):
                hits.append((node.lineno, f"dirname-Kette (Tiefe {depth})"))
        # os.path.join(<... __file__ ...>, "..", …)
        if isinstance(node, ast.Call) and _is_attr_chain(node.func, "os", "path", "join"):
            if node.args and _refs_file(node.args[0]) and any(
                    isinstance(a, ast.Constant) and a.value == ".." for a in node.args[1:]):
                hits.append((node.lineno, 'os.path.join(__file__-Pfad, "..")'))
        # Path(__file__)....parents[N]
        if isinstance(node, ast.Subscript):
            val = node.value
            if (isinstance(val, ast.Attribute) and val.attr == "parents"
                    and _refs_file(val)):
                idx = node.slice
                n = idx.value if isinstance(idx, ast.Constant) else None
                if isinstance(n, int) and n >= 1:
                    hits.append((node.lineno, f"Path(__file__).parents[{n}]"))
        # Path(__file__).parent.parent (>= 2 Ebenen ueber der eigenen Datei)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            depth, inner = 0, node
            while isinstance(inner, ast.Attribute) and inner.attr == "parent":
                depth += 1
                inner = inner.value
            if depth >= 2 and _refs_file(inner):
                hits.append((node.lineno, f".parent-Kette (Tiefe {depth})"))
    return hits


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
            try:
                tree = ast.parse(_read(path))
            except SyntaxError as exc:
                offenders.append(f"{name} (SyntaxError: {exc})")
                continue
            for lineno, what in find_depth_guesses(tree):
                offenders.append(f"{name}:{lineno} ({what})")
        self.assertEqual(offenders, [], f"Tiefen-Raten in tools/_archiv/: {offenders} {HINT}")

    def test_detector_catches_all_known_spellings(self):
        """Der Detektor selbst braucht Zaehne — sonst ist das Gate oben wertlos.

        Positiv-Proben = die real im Repo vorkommenden Schreibweisen des
        Tiefen-Ratens; Negativ-Proben = die korrekten Formen. Ohne diesen Test
        koennte man den Detektor entschaerfen, ohne dass etwas rot wird
        (Scheinabdeckung, Checkliste §7 / Lehre CDX-18).
        """
        must_catch = [
            'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))',
            '_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))',
            '_ROOT = os.path.dirname(os.path.dirname(__file__))',       # ohne abspath
            'SHOW = os.path.join(os.path.dirname(__file__), "..", "shows", "X.lshow")',
            'REPO = Path(__file__).resolve().parents[1]',               # pathlib-Variante
            'REPO = Path(__file__).parent.parent',                      # (via parents-Alias)
            '_ROOT = os.path.dirname(\n    os.path.dirname(os.path.abspath(__file__)))',  # mehrzeilig
        ]
        must_pass = [
            'import _bootstrap',
            '_ROOT = _bootstrap.REPO_ROOT',
            'OUT = os.path.join(_bootstrap.REPO_ROOT, "shows", "X.lshow")',
            'from _showpath import find_show\nSHOW = find_show("X.lshow")',
            'HERE = os.path.dirname(os.path.abspath(__file__))',  # eigener Ordner = ok
            'p = Path(__file__).parents[0]',                      # eigener Ordner = ok
        ]
        for src in must_catch:
            with self.subTest(src=src):
                self.assertTrue(find_depth_guesses(ast.parse(src)),
                                f"Detektor blind fuer: {src!r}")
        for src in must_pass:
            with self.subTest(src=src):
                self.assertEqual(find_depth_guesses(ast.parse(src)), [],
                                 f"Detektor meldet korrekten Code faelschlich: {src!r}")

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
            # Plain- und from-Import symmetrisch behandeln: `import src.core.x`
            # und `import _showpath` sind genauso abhaengig wie ihre
            # from-Varianten (Review-Fund 2026-07-27 — vorher nur _gen_env/_builder).
            DEPS = ("src", "_gen_env", "_builder", "_showpath")
            boot = dep = None
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name == "_bootstrap" and boot is None:
                            boot = node.lineno
                        elif a.name.split(".")[0] in DEPS and dep is None:
                            dep = node.lineno
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in DEPS and dep is None:
                        dep = node.lineno
            if dep is not None and (boot is None or boot > dep):
                offenders.append(f"{name} (_bootstrap={boot}, abhaengiger Import={dep})")
        self.assertEqual(
            offenders, [],
            f"`import _bootstrap` steht zu spaet: {offenders} {HINT}")

    def test_bootstrap_resolves_real_repo_root(self):
        """Der Bootstrap muss aus tools/_archiv/ heraus den echten Repo-Root treffen."""
        import importlib.util
        import sys

        # HERMETIK: _bootstrap.py hat einen Import-Seiteneffekt (es schreibt
        # Repo-Root + tools/ auf sys.path). Der darf NICHT in die restliche
        # pytest-Session lecken — sonst waeren ab hier ~60 tools/-Module unter
        # ihrem blossen Stem importierbar und koennten spaetere Tests
        # beeinflussen bzw. ein fehlendes sys.path-Setup maskieren.
        name = "_archiv_bootstrap_under_test"
        saved_path = list(sys.path)
        saved_mod = sys.modules.get(name)
        try:
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(ARCHIV, BOOTSTRAP))
            self.assertIsNotNone(spec, f"{BOOTSTRAP} nicht ladbar")
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            repo_root = mod.REPO_ROOT
            # Vertrag: Repo-Root VOR tools/ auf sys.path — und zwar unabhaengig
            # davon, ob einer der beiden vorher schon drinstand (PYTHONPATH,
            # conftest, vorheriger Test). Deshalb Positionen vergleichen, nicht
            # "was ist neu dazugekommen".
            path_after = list(sys.path)
            idx_repo = path_after.index(mod.REPO_ROOT)
            idx_tools = path_after.index(mod.TOOLS_DIR)
        finally:
            sys.path[:] = saved_path
            if saved_mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved_mod

        # Der Bootstrap MUSS beide Pfade platzieren, Repo-Root zuerst — sonst
        # koennte tools/ ein gleichnamiges src-Modul verschatten, und dieser
        # Test bewiese nur, dass ein paar Konstanten stimmen.
        self.assertLess(idx_repo, idx_tools,
                        "sys.path-Reihenfolge falsch: tools/ steht vor dem Repo-Root")

        norm = lambda p: os.path.normcase(os.path.abspath(p))  # noqa: E731
        self.assertEqual(norm(repo_root), norm(REPO),
                         "REPO_ROOT zeigt nicht auf den Repo-Root")
        # Der eigentliche Regressionspunkt: NICHT auf tools/.
        self.assertNotEqual(norm(repo_root), norm(os.path.join(REPO, "tools")),
                            "REPO_ROOT zeigt auf tools/ — genau der Bug von 2026-07-19")
        self.assertTrue(os.path.isdir(os.path.join(repo_root, "shows")),
                        "shows/ unter REPO_ROOT nicht gefunden")

    def test_marker_search_beats_depth_fallback(self):
        """Die Marker-Suche muss sich vom Fallback UNTERSCHEIDBAR bewaehren.

        Aus ``tools/_archiv/`` liefert der Tiefen-Fallback zufaellig denselben
        Wert wie die Marker-Suche — der Test oben kann beide also nicht
        auseinanderhalten (man koennte die Marker-Suche entfernen und er bliebe
        gruen; Review-Fund 2026-07-27, Scheinabdeckung nach Checkliste §7).
        Hier wird eine Ablage gebaut, in der sich beide GARANTIERT
        unterscheiden: eine Ebene TIEFER als tools/_archiv/.
        """
        import importlib.util
        import sys
        import tempfile

        name = "_archiv_bootstrap_marker_test"
        saved_path, saved_mod = list(sys.path), sys.modules.get(name)
        try:
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(ARCHIV, BOOTSTRAP))
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            find_repo_root = mod.find_repo_root
        finally:
            sys.path[:] = saved_path
            if saved_mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved_mod

        with tempfile.TemporaryDirectory() as tmp:
            fake_root = os.path.realpath(tmp)
            deep = os.path.join(fake_root, "tools", "_archiv", "tief")
            os.makedirs(deep)
            os.makedirs(os.path.join(fake_root, "src"))

            got = os.path.normcase(os.path.realpath(find_repo_root(deep)))
            want = os.path.normcase(fake_root)
            fallback = os.path.normcase(os.path.realpath(
                os.path.dirname(os.path.dirname(deep))))  # = <fake>/tools

            self.assertNotEqual(want, fallback,
                                "Testaufbau kaputt: Marker und Fallback muessten hier differieren")
            self.assertEqual(got, want,
                             "find_repo_root faellt auf das Tiefen-Raten zurueck, "
                             "statt den Marker (src/ + tools/) zu suchen")

    def test_fallback_used_when_no_marker(self):
        """Ohne Marker muss der dokumentierte Fallback greifen (nicht crashen)."""
        import importlib.util
        import sys
        import tempfile

        name = "_archiv_bootstrap_fallback_test"
        saved_path, saved_mod = list(sys.path), sys.modules.get(name)
        try:
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(ARCHIV, BOOTSTRAP))
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            find_repo_root = mod.find_repo_root
        finally:
            sys.path[:] = saved_path
            if saved_mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved_mod

        with tempfile.TemporaryDirectory() as tmp:
            # Ordner OHNE src/+tools/ irgendwo aufwaerts (tempdir-Wurzel hat keins).
            lonely = os.path.join(os.path.realpath(tmp), "a", "b")
            os.makedirs(lonely)
            got = find_repo_root(lonely)
            self.assertTrue(got, "Fallback liefert leeren Pfad")
            self.assertEqual(
                os.path.normcase(os.path.realpath(got)),
                os.path.normcase(os.path.realpath(os.path.dirname(os.path.dirname(lonely)))),
                "Fallback verhaelt sich nicht wie die dokumentierte alte Zeile")


if __name__ == "__main__":
    unittest.main()

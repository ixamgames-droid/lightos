"""``weak_slot`` VERWIRFT Signal-Argumente — die Zielmethode muss ohne sie auskommen.

Real abgestürzt (crash.log 2026-07-06):

    TypeError: LaserView._on_figure_changed() missing 1 required positional
               argument: '_idx'

`laser_view.py` verband `currentIndexChanged` per ``weak_slot(self._on_figure_changed)``,
die Methode verlangte aber ein ``_idx``. ``weak_slot`` ruft laut eigenem Docstring
mit ``func(obj, *args)`` auf und lässt die Signal-Argumente bewusst fallen — der
Aufruf kam also ohne ``_idx`` an. Wer die Signal-Argumente BRAUCHT, nimmt
``weak_slot_fwd``.

Der Fehler fällt nur auf, wenn das Signal wirklich feuert: beim Bauen der Ansicht
passiert nichts, erst das erste Umschalten der Auswahl kracht. Genau darum hier ein
STATISCHER Scan über den ganzen Quellbaum statt eines Einzeltests — die Fehlerklasse
kann in jeder der ~70 ``weak_slot``-Verwendungen erneut entstehen.

Geprüft wird die Arität: ``weak_slot(self.m, a, b)`` ruft ``self.m(a, b)`` auf, also
muss ``m`` mit **genau** so vielen Positionsargumenten aufrufbar sein.
"""
from __future__ import annotations

import ast
import inspect
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")


def _iter_py_files():
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(base, fn)


def _method_defs(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    """``ClassName.method`` -> FunctionDef (inkl. async)."""
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub
    return out


def _enclosing_class(tree: ast.AST, target: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in ast.walk(node):
                if sub is target:
                    return node.name
    return None


def _accepts(fn: ast.FunctionDef, n_args: int) -> bool:
    """Kann ``fn`` (Methode) mit ``n_args`` Positionsargumenten nach ``self``
    aufgerufen werden?"""
    a = fn.args
    positional = a.posonlyargs + a.args
    if positional and positional[0].arg in ("self", "cls"):
        positional = positional[1:]
    required = len(positional) - len(a.defaults)
    if a.vararg is not None:
        return n_args >= required
    return required <= n_args <= len(positional)


def _weak_slot_calls():
    """(datei, zeile, funktionsname, anzahl_gebundener_args) je ``weak_slot(...)``."""
    for path in _iter_py_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if "weak_slot(" not in src:
            continue
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError:                      # pragma: no cover - Schutz
            continue
        defs = _method_defs(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if fname != "weak_slot" or not node.args:
                continue
            first = node.args[0]
            # Nur `weak_slot(self.methode, ...)` ist statisch aufloesbar.
            if not (isinstance(first, ast.Attribute)
                    and isinstance(first.value, ast.Name)
                    and first.value.id == "self"):
                continue
            cls = _enclosing_class(tree, node)
            if cls is None:
                continue
            fn = defs.get(f"{cls}.{first.attr}")
            if fn is None:
                continue                          # geerbt/anderswo definiert
            yield (os.path.relpath(path, REPO), node.lineno,
                   f"{cls}.{first.attr}", len(node.args) - 1, fn)


class WeakSlotArityTest(unittest.TestCase):
    def test_every_weak_slot_target_survives_dropped_signal_args(self):
        bad = []
        checked = 0
        for rel, lineno, name, n_bound, fn in _weak_slot_calls():
            checked += 1
            if not _accepts(fn, n_bound):
                bad.append(f"{rel}:{lineno} weak_slot(self.{name.split('.')[-1]}"
                           f"{', …' if n_bound else ''}) -> {name} verlangt mehr "
                           f"Argumente als es bekommt")
        self.assertGreater(checked, 20,
                           "Scan hat kaum etwas gefunden — Testaufbau kaputt")
        self.assertEqual(bad, [], "weak_slot verwirft Signal-Argumente; wer sie "
                                  "braucht, nimmt weak_slot_fwd:\n  " + "\n  ".join(bad))


class ArityHelperTest(unittest.TestCase):
    """Der Prüfer selbst — sonst kann der Scan stillschweigend nichts prüfen."""

    def _fn(self, src: str) -> ast.FunctionDef:
        return ast.parse(src).body[0]           # type: ignore[return-value]

    def test_required_arg_is_rejected(self):
        self.assertFalse(_accepts(self._fn("def m(self, idx): pass"), 0))

    def test_default_makes_it_acceptable(self):
        self.assertTrue(_accepts(self._fn("def m(self, idx=0): pass"), 0))

    def test_no_extra_args_is_fine(self):
        self.assertTrue(_accepts(self._fn("def m(self): pass"), 0))

    def test_varargs_accept_anything(self):
        self.assertTrue(_accepts(self._fn("def m(self, *a): pass"), 0))
        self.assertTrue(_accepts(self._fn("def m(self, *a): pass"), 3))

    def test_too_many_bound_args_is_rejected(self):
        self.assertFalse(_accepts(self._fn("def m(self): pass"), 1))

    def test_bound_args_are_counted(self):
        self.assertTrue(_accepts(self._fn("def m(self, a, b): pass"), 2))
        self.assertFalse(_accepts(self._fn("def m(self, a, b): pass"), 1))

    def test_matches_real_signature_semantics(self):
        """Gegenprobe gegen inspect: der AST-Pruefer darf nicht abweichen."""
        def m(self, a, b=1):                      # noqa: ANN001
            pass
        sig = inspect.signature(m)
        for n in (0, 1, 2):
            try:
                sig.bind(None, *range(n))
                ok = True
            except TypeError:
                ok = False
            self.assertEqual(
                ok, _accepts(self._fn("def m(self, a, b=1): pass"), n),
                f"AST-Pruefer weicht bei {n} Argument(en) von inspect ab")


if __name__ == "__main__":
    unittest.main()

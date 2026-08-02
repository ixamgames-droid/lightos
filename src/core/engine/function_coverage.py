"""Welche Geraete schreibt eine Funktion? — eine Quelle, bewusst konservativ.

BUG-FBW (David 2026-08-01): „Alles Weiß macht nicht alles weiß." Der Knopf
``ButtonAction.ALL_WHITE`` setzt nichts selbst, sondern startet die an ihn
gebundene Szene — „die Szene weiss das, nicht der Button" (``vc_button.py``).
Daraus folgen zwei Arten, wie er stillschweigend zu wenig tut:

1. **gar keine Bindung** → der Druck macht nichts, ohne jede Rueckmeldung;
2. **eine Weiss-Szene aus einer Zeit mit weniger Geraeten** → sie deckt nur die
   damaligen ab, die spaeter dazugepatchten bleiben dunkel.

Beides ist dieselbe Frage: *wie viele der gepatchten Geraete erreicht das, was
an dem Knopf haengt?* Dieses Modul beantwortet sie — oder sagt ehrlich, dass es
sie nicht beantworten kann.

**Die Regel, an der alles haengt: im Zweifel ``None``.** Eine geratene Abdeckung
waere schlimmer als gar keine, denn sie erschiene als geprueft. ``None`` heisst
„nicht bestimmbar", und der Aufrufer zeigt dann keinen Hinweis an, statt einen
falschen. Deshalb liefert schon EIN unbekanntes Mitglied einer Sammlung
``None`` fuer das Ganze.

Leaf-Modul ohne Qt-/DB-Importe (Lehre aus der Review-Checkliste Klasse 3):
Persistenz-, UI- und Testpfade koennen es gemeinsam importieren, auch wenn ein
Test die schwereren Module ausstubbt.
"""
from __future__ import annotations

from typing import Callable, Iterable

# Wie tief Sammlungen/Chaser aufgeloest werden. Schuetzt gegen einen Zyklus
# (Collection A enthaelt B enthaelt A) und gegen absurd tiefe Verschachtelung.
_MAX_TIEFE = 8


def covered_fixture_ids(func, aufloesen: Callable[[int], object | None],
                        _tiefe: int = 0) -> set[int] | None:
    """Geraete-IDs, die ``func`` beim Laufen schreibt.

    ``aufloesen`` bildet eine Funktions-ID auf die Funktion ab (in der App
    ``FunctionManager.get``). ``None`` als Rueckgabe heisst **nicht bestimmbar** —
    nie „keine".

    Bestimmbar sind heute Szenen (die tragen ihre ``(fixture_id, channel)``-Werte
    direkt) und Sammlungen/Chaser daraus. Alles andere — Matrix-Effekte, EFX,
    Skripte — rechnet seine Ziele erst zur Laufzeit aus bzw. haengt an der
    Auswahl; dafuer gibt es hier bewusst keine Schaetzung.
    """
    if func is None or _tiefe > _MAX_TIEFE:
        return None

    # Szene: die Werte tragen die Geraete-ID mit.
    werte = getattr(func, "values", None)
    if isinstance(werte, list):
        ids: set[int] = set()
        for sv in werte:
            fid = getattr(sv, "fixture_id", None)
            if fid is None:
                return None            # unbekannte Werte-Form -> nicht raten
            ids.add(int(fid))
        return ids

    # Sammlung: Vereinigung ihrer Mitglieder.
    mitglieder = getattr(func, "function_ids", None)
    if isinstance(mitglieder, list):
        return _vereinigen(mitglieder, aufloesen, _tiefe)

    # Chaser: Vereinigung ueber die Schritt-Funktionen.
    steps = getattr(func, "steps", None)
    if isinstance(steps, list):
        return _vereinigen([getattr(s, "function_id", None) for s in steps],
                           aufloesen, _tiefe)

    return None


def _vereinigen(ids: Iterable, aufloesen, tiefe: int) -> set[int] | None:
    """Vereinigung der Abdeckungen — ``None``, sobald ein Mitglied unklar ist."""
    gesamt: set[int] = set()
    for fid in ids:
        if fid is None:
            return None
        teil = covered_fixture_ids(aufloesen(int(fid)), aufloesen, tiefe + 1)
        if teil is None:
            return None
        gesamt |= teil
    return gesamt


def coverage_of_bindings(function_ids: Iterable[int],
                         aufloesen: Callable[[int], object | None]) -> set[int] | None:
    """Abdeckung MEHRERER gebundener Funktionen (ein Knopf kann mehrere tragen).

    Leere Bindungsliste → leere Menge (nicht ``None``): „nichts gebunden" ist
    eine sichere Aussage, keine Unsicherheit. Genau daran haengt die Warnung
    „nicht belegt".
    """
    gesamt: set[int] = set()
    for fid in function_ids:
        teil = covered_fixture_ids(aufloesen(int(fid)), aufloesen)
        if teil is None:
            return None
        gesamt |= teil
    return gesamt

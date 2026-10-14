"""Undo/Redo - Command-Pattern mit UndoStack.

Verwendung:
    from src.core.undo import get_undo_stack, Command
    stack = get_undo_stack()
    stack.push(Command(label="Fixture +", do=lambda: state.add_fixture(f),
                       undo=lambda: state.remove_fixture(f.fid)))

Im Main Menue: Ctrl+Z (stack.undo()) / Ctrl+Y (stack.redo()).

UI-93 (Nachtrag): Es gibt mehr als einen Verlauf — diesen Stapel und den
Layout-Verlauf der Virtual Console (Schnappschuesse in ``VCCanvas``). Fuer den
Bediener ist es EIN Verlauf: Strg+Z nimmt den zuletzt gemachten Schritt
zurueck, egal aus welchem Stapel. Dafuer traegt jeder Eintrag eine
Schrittnummer aus EINEM gemeinsamen Zaehler:

* ``neuer_schritt()``      — beim Ablegen eines neuen Schritts. Ein neuer
  Schritt verwirft den Wiederholen-Zweig ALLER Verlaeufe (wie in jedem
  Programm mit einem einzigen Verlauf).
* ``ruecknahme_marke()``   — beim Zuruecknehmen. Wiederholt wird zuerst, was
  zuletzt zurueckgenommen wurde.
* ``wiederholen_verworfen(marke)`` — True, wenn seit dieser Ruecknahme
  irgendwo ein neuer Schritt abgelegt wurde.

Die Stapel pruefen das selbst (``UndoStack._redo_pruefen``,
``VCCanvas._redo_pruefen``) — sie muessen einander dafuer nicht kennen.
"""
from __future__ import annotations
import itertools
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable

_schritt_zaehler = itertools.count(1)
_letzter_neuer_schritt = 0


def neuer_schritt() -> int:
    """Nummer fuer einen NEU gemachten Schritt (verwirft jedes Wiederholen)."""
    global _letzter_neuer_schritt
    _letzter_neuer_schritt = next(_schritt_zaehler)
    return _letzter_neuer_schritt


def ruecknahme_marke() -> int:
    """Nummer fuer eine Ruecknahme (ordnet die Wiederholen-Zweige zeitlich)."""
    return next(_schritt_zaehler)


def wiederholen_verworfen(marke: int) -> bool:
    """Wurde nach der Ruecknahme ``marke`` irgendwo ein neuer Schritt gemacht?"""
    return marke < _letzter_neuer_schritt


@dataclass
class Command:
    """Eine atomare, rueckgaengig-machbare Aktion."""
    label: str
    do: Callable[[], None]
    undo: Callable[[], None]
    # Optional Redo, falls do() Seiteneffekte hat die nicht wiederholbar sind
    redo: Callable[[], None] | None = None
    # UI-93: Platz im gemeinsamen Verlauf (setzt der Stapel, nicht der Aufrufer).
    schritt: int = 0     # wann der Schritt gemacht wurde
    zurueck: int = 0     # wann er zuletzt zurueckgenommen wurde

    def execute(self):
        self.do()

    def revert(self):
        self.undo()

    def reexecute(self):
        if self.redo is not None:
            self.redo()
        else:
            self.do()


def _sammel_command(label: str, teile: list[Command]) -> Command:
    """Ein Command aus mehreren. Ein Teil, das wirft, haelt die uebrigen
    nicht auf — sonst bliebe nach einem Rueckgaengig die Haelfte stehen."""
    def _jedes(folge, aufruf):
        for teil in folge:
            try:
                aufruf(teil)
            except Exception as e:
                print(f"[UndoStack] Teil '{teil.label}' fehlgeschlagen: {e}")

    return Command(
        label=label,
        do=lambda: None,
        undo=lambda: _jedes(list(reversed(teile)), Command.revert),
        redo=lambda: _jedes(list(teile), Command.reexecute),
    )


class UndoStack:
    """Stack mit Undo/Redo. MAX_SIZE Eintraege als FIFO."""

    MAX_SIZE = 100

    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._listeners: list[Callable[[], None]] = []
        self._suspended: int = 0   # waehrend undo()/redo() keine push
        # IMP-1: waehrend ``gruppe()`` sammelt push() hier statt auf dem Stack.
        self._sammler: list[Command] | None = None

    # ── Push / Execute ───────────────────────────────────────────────────────

    def push(self, cmd: Command, execute: bool = True):
        """Pusht ein Command auf den Stack und fuehrt es (optional) aus."""
        if self._suspended:
            return
        if execute:
            try:
                cmd.execute()
            except Exception as e:
                print(f"[UndoStack] execute error: {e}")
                return
        if self._sammler is not None:
            # IMP-1: Teile einer Gruppe bekommen keine eigene Schrittnummer —
            # erst der Sammelschritt am Ende der Gruppe (UI-93).
            self._sammler.append(cmd)
            return
        cmd.schritt = neuer_schritt()
        self._undo.append(cmd)
        # Cap
        if len(self._undo) > self.MAX_SIZE:
            self._undo = self._undo[-self.MAX_SIZE:]
        self._redo.clear()
        self._notify()

    def push_simple(self, label: str, do, undo):
        """Shortcut: push(Command(label, do, undo))."""
        self.push(Command(label=label, do=do, undo=undo))

    @contextmanager
    def gruppe(self, label: str):
        """IMP-1: alles, was innerhalb des Blocks gepusht wird, landet als EIN
        Schritt auf dem Stack — ein Rueckgaengig nimmt alles zurueck (in
        umgekehrter Reihenfolge), ein Wiederholen stellt alles wieder her.

        Gedacht fuer Sammelvorgaenge, die N-mal denselben Einzelweg gehen
        (Patch-Import: N-mal ``add_fixture``) — so bleibt der Einzelweg samt
        seinem eigenen Undo/Redo die einzige Wahrheit. Wird nichts gepusht,
        entsteht kein Schritt. Verschachtelt zaehlt die aeusserste Gruppe.
        Wirft der Block, bleibt das bis dahin Gesammelte als ein Schritt
        ruecknehmbar."""
        if self._sammler is not None or self._suspended:
            yield
            return
        self._sammler = []
        try:
            yield
        finally:
            teile, self._sammler = self._sammler, None
            if teile:
                self.push(_sammel_command(label, teile), execute=False)

    # ── Undo / Redo ──────────────────────────────────────────────────────────

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        self._suspended += 1
        try:
            cmd.revert()
        except Exception as e:
            print(f"[UndoStack] undo error: {e}")
        finally:
            self._suspended -= 1
        cmd.zurueck = ruecknahme_marke()
        self._redo.append(cmd)
        self._notify()
        return True

    def _redo_pruefen(self) -> None:
        """UI-93: Wiederholen-Zweig verwerfen, wenn seit der Ruecknahme in
        einem ANDEREN Verlauf ein neuer Schritt gemacht wurde (der eigene
        ``push`` leert ihn ohnehin). Der oberste Eintrag ist der zuletzt
        zurueckgenommene — ist er verworfen, sind es alle darunter auch."""
        if self._redo and wiederholen_verworfen(self._redo[-1].zurueck):
            self._redo.clear()

    def redo(self) -> bool:
        self._redo_pruefen()
        if not self._redo:
            return False
        cmd = self._redo.pop()
        self._suspended += 1
        try:
            cmd.reexecute()
        except Exception as e:
            print(f"[UndoStack] redo error: {e}")
        finally:
            self._suspended -= 1
        self._undo.append(cmd)
        self._notify()
        return True

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        self._redo_pruefen()
        return len(self._redo) > 0

    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    def redo_label(self) -> str | None:
        self._redo_pruefen()
        return self._redo[-1].label if self._redo else None

    def undo_schritt(self) -> int | None:
        """UI-93: Schrittnummer des naechsten Rueckgaengig (None = leer)."""
        return self._undo[-1].schritt if self._undo else None

    def redo_marke(self) -> int | None:
        """UI-93: Ruecknahme-Marke des naechsten Wiederholen (None = leer)."""
        self._redo_pruefen()
        return self._redo[-1].zurueck if self._redo else None

    def clear(self):
        self._undo.clear()
        self._redo.clear()
        self._notify()

    # ── Listener ─────────────────────────────────────────────────────────────

    def subscribe(self, cb):
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify(self):
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass


_stack: UndoStack | None = None


def get_undo_stack() -> UndoStack:
    global _stack
    if _stack is None:
        _stack = UndoStack()
    return _stack

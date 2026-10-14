"""Undo/Redo - Command-Pattern mit UndoStack.

Verwendung:
    from src.core.undo import get_undo_stack, Command
    stack = get_undo_stack()
    stack.push(Command(label="Fixture +", do=lambda: state.add_fixture(f),
                       undo=lambda: state.remove_fixture(f.fid)))

Im Main Menue: Ctrl+Z (stack.undo()) / Ctrl+Y (stack.redo()).
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable


@dataclass
class Command:
    """Eine atomare, rueckgaengig-machbare Aktion."""
    label: str
    do: Callable[[], None]
    undo: Callable[[], None]
    # Optional Redo, falls do() Seiteneffekte hat die nicht wiederholbar sind
    redo: Callable[[], None] | None = None

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
            self._sammler.append(cmd)
            return
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
        self._redo.append(cmd)
        self._notify()
        return True

    def redo(self) -> bool:
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
        return len(self._redo) > 0

    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    def redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

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
